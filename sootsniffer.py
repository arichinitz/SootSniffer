"""
SootSniffer
===========
A low-cost particle counter built on a Raspberry Pi 5 and a Raspberry Pi HQ
Camera with a microscope-style lens.

A backlit slide is imaged by the camera. Particles block the light and show up
as dark spots on a bright background. OpenCV finds the spots, counts them, and
circles them on a live video feed that can be viewed from any browser on the
same network. Counts are logged to a CSV file and annotated images are saved
at a regular interval.

Usage:
    python3 sootsniffer.py

Then open http://localhost:8000 on the Pi, or http://<PI_IP_ADDRESS>:8000 from
another device on the same network (find the IP with `hostname -I`).
Press Ctrl+C to stop.

Requirements:
    sudo apt install -y python3-picamera2 python3-opencv python3-numpy
"""

import csv
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import cv2

# ─── Settings (tweak these once your device is built) ────────────────────────
RESOLUTION        = (1280, 720)   # Camera resolution
FPS               = 10            # Frames per second (lower = less CPU)
SHUTTER_SPEED     = 33333         # Exposure time in microseconds (1/30 s)
MIN_PARTICLE      = 5             # Minimum particle area in pixels (filters noise)
MAX_PARTICLE      = 500           # Maximum particle area in pixels (filters big blobs)
BRIGHTNESS_THRESH = 30            # How much darker than the local background a
                                  # spot must be to count (0-255). Raise it if
                                  # noise is being counted, lower it if
                                  # particles are being missed
BACKGROUND_KERNEL = 51            # Size (pixels, odd number) of the area used to
                                  # estimate the local background brightness.
                                  # Keep it much larger than a particle
PORT              = 8000          # Web stream port
LOG_FILE          = "particle_log.csv"
LOG_INTERVAL      = 1.0           # Seconds between CSV log entries
IMAGE_SAVE_DIR    = "particle_images"
SAVE_IMAGE_EVERY  = 30            # Save an annotated image every X seconds
# ─────────────────────────────────────────────────────────────────────────────


class State:
    """Shared state between the camera thread and the web server."""
    frame_jpeg = None
    particle_count = 0
    condition = threading.Condition()


state = State()


def setup_logging():
    """Create the image folder and the CSV log file if they don't exist."""
    os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(["Timestamp", "Particle Count"])


def count_particles(frame_bgr):
    """Find and count particles in a frame. Returns (annotated frame, count)."""
    # Convert to grayscale
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

    # Blur slightly to reduce sensor noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Estimate the local background brightness. Comparing each pixel to its
    # surroundings (instead of to a fixed value) keeps detection working when
    # the backlight is uneven or the exposure changes
    background = cv2.blur(gray, (BACKGROUND_KERNEL, BACKGROUND_KERNEL))

    # How much darker each pixel is than its background (0 if it is brighter)
    darkness = cv2.subtract(background, blurred)

    # Particles appear as dark spots on a bright background
    _, thresh = cv2.threshold(darkness, BRIGHTNESS_THRESH, 255, cv2.THRESH_BINARY)

    # Find contours (outlines of each spot)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    count = 0
    annotated = frame_bgr.copy()

    for contour in contours:
        area = cv2.contourArea(contour)
        if MIN_PARTICLE < area < MAX_PARTICLE:
            count += 1
            # Draw a green circle around each detected particle
            (x, y), radius = cv2.minEnclosingCircle(contour)
            cv2.circle(annotated, (int(x), int(y)), max(int(radius), 3), (0, 255, 0), 2)

    # Draw the particle count and a timestamp on the frame
    cv2.putText(annotated, f"Particles: {count}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(annotated, ts, (20, annotated.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

    return annotated, count


def camera_thread():
    """Captures frames, counts particles, logs data, and updates shared state."""
    from picamera2 import Picamera2  # imported here so the detection code can be tested off the Pi

    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"size": RESOLUTION, "format": "RGB888"},
        controls={"FrameRate": FPS, "ExposureTime": SHUTTER_SPEED},
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(2)  # Let the camera warm up

    last_save_time = time.time()
    last_log_time = 0.0

    print("Camera started. Processing frames...")

    try:
        while True:
            # Grab a frame. Picamera2's "RGB888" format is already stored in
            # the blue-green-red order OpenCV expects, so no conversion needed
            frame_bgr = picam2.capture_array()

            # Count particles and annotate the frame
            annotated, count = count_particles(frame_bgr)
            now = time.time()

            # Log the count to CSV
            if now - last_log_time >= LOG_INTERVAL:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(LOG_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([ts, count])
                last_log_time = now

            # Save an annotated image periodically
            if now - last_save_time >= SAVE_IMAGE_EVERY:
                name = datetime.now().strftime("particles_%Y%m%d_%H%M%S.jpg")
                path = os.path.join(IMAGE_SAVE_DIR, name)
                cv2.imwrite(path, annotated)
                print(f"Image saved: {path}")
                last_save_time = now

            # Encode the frame as JPEG for streaming
            _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])

            # Update shared state and wake up any viewers
            with state.condition:
                state.frame_jpeg = jpeg.tobytes()
                state.particle_count = count
                state.condition.notify_all()
    finally:
        picam2.stop()


# ─── Web streaming ───────────────────────────────────────────────────────────

INDEX_HTML = b"""
<html>
<head>
    <title>SootSniffer</title>
    <style>
        body {
            background: #111;
            color: white;
            font-family: sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
            margin: 0;
        }
        h1 { color: #00ff88; }
        img { max-width: 100%; border-radius: 8px; border: 2px solid #00ff88; }
        p  { color: #aaa; font-size: 14px; }
    </style>
</head>
<body>
    <h1>SootSniffer</h1>
    <img src="/stream.mjpg"/>
    <p>Green circles = detected particles. Counts are logged to particle_log.csv</p>
</body>
</html>
"""


class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(301)
            self.send_header("Location", "/index.html")
            self.end_headers()

        elif self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", len(INDEX_HTML))
            self.end_headers()
            self.wfile.write(INDEX_HTML)

        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Age", 0)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with state.condition:
                        state.condition.wait()
                        frame = state.frame_jpeg
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except Exception:
                pass  # Viewer closed the page

        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # Suppress noisy access logs


class StreamServer(HTTPServer):
    allow_reuse_address = True
    daemon_threads = True  # Each viewer gets its own thread


# ─── Start everything ────────────────────────────────────────────────────────

def main():
    print("Starting SootSniffer...")
    setup_logging()

    # Start the camera in a background thread
    threading.Thread(target=camera_thread, daemon=True).start()

    # Start the web server
    server = StreamServer(("0.0.0.0", PORT), StreamHandler)
    print(f"On this Pi:      http://localhost:{PORT}")
    print(f"From your Mac:   http://<PI_IP_ADDRESS>:{PORT}  (find it with: hostname -I)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SootSniffer...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
