# Raspberry Pi Setup Guide

## One-Time Setup

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd Runtimes-power-efficiency
```

### 2. Install wrk (Load Testing Tool)
```bash
sudo apt update
sudo apt install wrk
```

### 3. Install Python Dependencies (Blinka + INA260)
```bash
sudo apt install python3-pip python3-dev python3-rpi.gpio i2c-tools
pip3 install adafruit-blinka adafruit-circuitpython-ina260
```

### 4. Setup Node.js Server Dependencies (if testing Node)
```bash
cd nodejs
npm install
cd ..
```

### 5. Verify Java is Installed
```bash
java -version  # Should show Java 17 or higher
```

## Running Measurements

### Spring Boot Server
```bash
python3 full_pipeline.py
```
Default config in script: `SERVER_TYPE = "spring"`, `ENDPOINT = "/cpu"`

### Node.js Server
Edit `full_pipeline.py`:
- Change `SERVER_TYPE = "node"`
- Run: `python3 full_pipeline.py`

## What Gets Generated
- `baseline_<timestamp>.csv` - Idle power measurements
- `test_<server>_<timestamp>.csv` - Under-load power measurements  
- `wrk_<server>_<timestamp>.txt` - Load test results
- `results.tex` - LaTeX table with final energy metrics

## Updating Code
```bash
git pull  # Gets latest code + updated JAR if rebuilt on Mac
```

## Notes
- ✅ Spring Boot JAR is pre-built and included in repo
- ✅ Node.js requires `npm install` once (not in repo)
- ✅ Make sure INA260 sensor is connected before running
- ⚠️ Each run takes ~2 minutes (60s baseline + 60s test)

### Troubleshooting
- `ModuleNotFoundError: No module named 'board'`: Install Adafruit Blinka (`pip3 install adafruit-blinka`) and OS prerequisites (`python3-rpi.gpio`, `python3-dev`, `i2c-tools`). Ensure I2C is enabled in `raspi-config`.
- I2C not found: Enable I2C via `sudo raspi-config` → Interfacing Options → I2C, then reboot. Verify with `ls /dev/i2c-1` and `i2cdetect -y 1`.
