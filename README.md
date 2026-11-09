# SootSniffer
A low-cost, DIY particle counter that uses a Raspberry Pi 5 and a microscope-style camera to detect, count, and log airborne soot particles in real time

## Why I Built SootSniffer - the problem
- Soot and other fine airborne particles come from combustion (vehicles, fires, stoves, industry) and are linked to respiratory and cardiovascular health problems
- Most people have no way to see or measure the particles in the air around them
- Commercial particle counters are expensive and are usually closed boxes that give you a number but never show you the particles
- I wanted a counter that is affordable, transparent, and lets you actually see what is being counted

## Features
- Live video feed of the sample, viewable from any device on the network (Pi or Mac)
- Automatic particle detection using computer vision
- Detected particles highlighted on the live feed
- Particle count displayed on every frame
- Timestamped count logging to a CSV file (opens in Excel or Google Sheets)
- Automatic image capture of annotated frames at a set interval
- Adjustable detection settings (minimum size, maximum size, brightness threshold)
- Remote control of the Pi from a laptop, with no keyboard or monitor needed

## Tools Used
### Hardware
- Raspberry Pi 5
- Raspberry Pi HQ Camera (CS mount)
- x100 lens
- Battery-powered LED backlight
- Glass microscope slides and coverslips
- 3D-printed frame (black filament to block stray light)
- Jumper wires, LED, and resistor for the status indicator

### Software
- Python 3
- OpenCV (cv2)
- NumPy
- Picamera2 / libcamera (rpicam-apps)
- Raspberry Pi Connect (remote access)
- Fusion360 (CAD)

## How to Use
1. Clean a microscope slide with isopropyl alcohol so no stray dust is counted
2. Expose the slide to the air you want to sample for a set amount of time
3. Place the coverslip on top and slide it into the holder with the sampled side facing the lens
4. Turn on the backlight and start the program on the Pi:
```bash
python3 particle_counter.py
```
5. Open the live feed in a browser:
   - On the Pi: `http://localhost:8000`
   - On another device: `http://<PI_IP_ADDRESS>:8000` (find the IP with `hostname -I`)
6. Read the live count, then open `particle_log.csv` and the `particle_images` folder for the saved data
7. Press Ctrl+C to stop

## How SootSniffer works
- The frame holds the slide at a fixed distance from the lens so every sample is in focus and in the same position
- The LED backlight shines through the slide, so particles block the light and appear as dark spots on a bright background
- The HQ camera captures frames and Picamera2 passes them to OpenCV
- Each frame is converted to grayscale and blurred slightly to remove sensor noise
- A threshold separates dark particles from the bright background
- Contours are found around each dark spot, and any spot outside the minimum and maximum size limits is rejected as noise or debris
- Each accepted particle is circled in green and counted
- The count and a timestamp are drawn on the frame, which is streamed over the network as MJPEG
- Every count is written to a CSV file, and annotated images are saved at a regular interval
- Exposure is locked to a fixed shutter time so the image brightness stays consistent from frame to frame

## Challenges and Fixes
- **Rolling dark bands across the feed:** I first suspected flicker from the light, but the bands appeared with a battery-powered light and a different light source. The cause was a smudge on the lens, which is hugely magnified at x100. Cleaning the lens and fixing the shutter time reduced the problem
- **Camera not detected:** The ribbon cable has to go in the camera port (CAM/DISP 0) on the Pi 5 and be fully seated
- **Lens too close to the slide:** The slide has to sit at the lens focal distance, not touching it, so the frame is designed around a measured focus distance
- **Low power warning:** The Pi 5 needs the official 5V 5A power supply, or the camera can drop out
- **Slide contamination:** Any dust already on the slide is counted as a particle, so slides are cleaned before every sample

## Results
- Success! Able to accurately track and detect dust particles
  
## Future Improvements
- Calibrate pixels to micrometers with a stage micrometer so particle size can be reported
- Add a small fan to draw air over the slide
- Sort particles by size and shape to tell soot apart from pollen, fibers, and dust
- Add a live graph of particle count over time to the web page
- Make the frame fully enclosed and slide-loading for repeatable, one-handed use
- Train a machine learning model to classify particle types
