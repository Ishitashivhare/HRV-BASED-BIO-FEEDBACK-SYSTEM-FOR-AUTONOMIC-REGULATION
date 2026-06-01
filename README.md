# HRV Biofeedback System for Autonomic Regulation

A complete biofeedback system that measures Heart Rate Variability (HRV) and guides users through a breathing exercise to improve their autonomic nervous system balance and stress resilience.

## 🎯 System Overview

This system consists of:
- **Hardware**: ESP32 microcontroller with MAX30102 pulse oximeter sensor and 16x2 LCD display
- **Software**: Python GUI application with real-time visualization and biofeedback guidance
- **Communication**: Serial communication at 115200 baud for real-time data streaming

The system measures baseline RMSSD (Heart Rate Variability metric), guides 2-minute breathing at 6 breaths/minute, then measures post-session RMSSD to show improvement percentage.

## ✨ Features

### Python GUI (`save_bpm.py`)
- ✓ Real-time BPM and RMSSD display
- ✓ Automated serial port detection and connection
- ✓ Guided breathing visualization (animated circle)
- ✓ Live data processing with thread-safe operations
- ✓ Comprehensive error logging and validation
- ✓ CSV data export with timestamps
- ✓ Improvement percentage calculation
- ✓ HRV quality assessment
- ✓ Graceful shutdown with resource cleanup

### Arduino Firmware (`hrv.ino`)
- ✓ MAX30102 sensor with I2C communication
- ✓ Advanced peak detection with hysteresis
- ✓ Adaptive threshold filtering
- ✓ RR interval validation and RMSSD calculation
- ✓ Moving average BPM filtering
- ✓ Outlier rejection for signal noise
- ✓ LCD display feedback
- ✓ Session state management
- ✓ Robust error tracking

## 📋 Requirements

### Hardware
- ESP32 WROOM microcontroller
- MAX30102 Pulse Oximeter Sensor
- 16x2 I2C LCD Display (address: 0x27)
- Jumper wires and breadboard

### Hardware Connections (ESP32)
```
MAX30102 (I2C):
  SDA → GPIO 21
  SCL → GPIO 22
  VCC → 3.3V
  GND → GND

LCD Display (I2C):
  SDA → GPIO 21
  SCL → GPIO 22
  VCC → 5V
  GND → GND
```

### Software Dependencies

**Arduino IDE Libraries:**
- MAX30105 by SparkFun (v1.0+)
- Wire (built-in)
- LiquidCrystal_I2C (v1.1.2)

**Python 3.7+**
```bash
pip install pyserial numpy
```

Tkinter is typically included with Python installation.

## 🚀 Installation & Setup

### 1. Arduino Setup

1. Open Arduino IDE and install required libraries:
   - Sketch → Include Library → Manage Libraries
   - Search for "MAX30105" by SparkFun and install
   - Search for "LiquidCrystal I2C" and install

2. Connect ESP32 to your computer via USB

3. Select Board: Tools → Board → ESP32 → "ESP32 WROOM DA Module"

4. Select Port: Tools → Port → COM port for ESP32

5. Copy `hrv.ino` content into Arduino IDE

6. Upload the sketch to ESP32

7. Open Serial Monitor (Ctrl+Shift+M) at 115200 baud to verify:
   - Should see "=== HRV BIOFEEDBACK SYSTEM STARTING ==="
   - LCD should display "Ready" and "Place Finger"

### 2. Python GUI Setup

1. Install dependencies:
```bash
pip install pyserial
```

2. Save `save_bpm.py` in your project directory

3. Run the application:
```bash
python save_bpm.py
```

4. The GUI will auto-detect the ESP32 serial connection

## 📖 User Guide

### Starting a Session

1. Click **"Start Experiment"** button
2. Place your finger on the MAX30102 sensor
3. Keep your finger steady on the sensor

### System Phases

**Phase 1: Stabilization (5 seconds)**
- LCD shows countdown timer
- Allows signal to stabilize

**Phase 2: Baseline Recording (30 seconds)**
- Sensor reads baseline HRV
- GUI shows "Place finger for baseline"

**Phase 3: Guided Breathing (120 seconds)**
- Animated breathing circle guides 6 breaths/minute
- Follow the expanding/contracting circle
- Keep finger on sensor

**Phase 4: Post-Session Recording (30 seconds)**
- GUI prompts "Place finger for 30s Post Session"
- Final HRV measurement taken

**Phase 5: Results Display**
- Shows: `✓ RMSSD: [baseline] → [post] ([improvement]%) - [quality]`
- Data automatically saved to CSV

## 📊 Understanding Results

### RMSSD (Root Mean Square of Successive Differences)
A heart rate variability metric indicating parasympathetic (relaxation) activity.

**Quality Assessment:**
- **< 20 ms**: Poor (very stressed/fatigued)
- **20-50 ms**: Below Average
- **50-100 ms**: Average
- **100-150 ms**: Good
- **> 150 ms**: Excellent (very relaxed)

### Improvement Percentage
Calculated as: `((Post RMSSD - Baseline RMSSD) / Baseline RMSSD) × 100`

Positive values indicate improved HRV after biofeedback.

## 📁 Data Output

### CSV File (`hrv_data.csv`)
Automatically saves session data:
- Date and Time
- Baseline BPM and RMSSD
- Post-session BPM and RMSSD
- Improvement percentage

### Log File (`hrv_log_*.log`)
Detailed debug information for troubleshooting

## 🔧 Technical Details

### Serial Protocol

**Messages from Arduino to Python:**

```
SESSION_RESET
  - Session has been reset

DATA,<BPM>,0
  - Live heart rate data during baseline
  - <BPM>: Current averaged BPM

FINAL,<BPM>,<RMSSD>
  - Session complete
  - <BPM>: Average heart rate for session
  - <RMSSD>: Root Mean Square of Successive Differences (ms)
```

### Arduino Signal Processing Pipeline

1. **Raw Sensor Read**: Get IR value from MAX30102
2. **Low-Pass Filter**: Remove high-frequency noise (α=0.85)
3. **Adaptive Threshold**: Track signal baseline (α=0.95)
4. **Peak Detection**: Hysteresis-based R-peak detection
5. **RR Interval Validation**: Reject physiologically impossible intervals
6. **RMSSD Calculation**: Compute from valid RR intervals
7. **Moving Average**: Smooth BPM values (5-sample buffer)
8. **Outlier Rejection**: Remove noisy RR intervals (>160ms difference)

### Python Thread Architecture

- **Main Thread**: Tkinter GUI and data visualization
- **Serial Reader Thread**: Reads incoming data from Arduino
- **Data Queue**: Thread-safe queue for data passing
- **Data Processing Loop**: Parses messages every 100ms
- **Animation Thread**: Manages breathing circle animation

## 🐛 Troubleshooting

### Serial Connection Issues
- Ensure USB cable is connected properly
- Check device manager for COM port
- Verify Arduino IDE can see the port
- Try different USB cable or port

### No Sensor Detection
- Verify MAX30102 I2C connections (SDA=GPIO21, SCL=GPIO22)
- Check I2C address with Arduino I2C Scanner
- Ensure proper pull-up resistors on I2C lines
- Check power supply (3.3V for sensor)

### Finger Not Detected
- Clean sensor lens and finger
- Ensure steady finger contact (no movement)
- Check sensor brightness in Arduino code
- Verify IR LED is working (red light visible)

### Inconsistent RMSSD Values
- Keep finger completely still during recording
- Avoid talking or moving
- Ensure dark room or cover sensor
- Repeat measurement 2-3 times for consistency

### High BPM Values (>150)
- May indicate signal noise or motion artifact
- Keep finger steady
- Ensure proper sensor contact
- Try different finger or hand position

## 📈 Calibration & Tuning

### Arduino Configuration (hrv.ino)

**Timing Constants** (in milliseconds):
```c
STABILIZE_TIME = 5000      // Stabilization period
RECORD_TIME = 30000        // Baseline recording duration
```

**Peak Detection Parameters**:
```c
IR_FILTER_ALPHA = 0.85     // Low-pass filter coefficient
THRESHOLD_ALPHA = 0.95     // Adaptive threshold coefficient
PEAK_THRESHOLD = 150       // Peak detection sensitivity
MIN_BEAT_INTERVAL = 350    // Minimum RR interval (171 bpm max)
MAX_BEAT_INTERVAL = 2000   // Maximum RR interval (30 bpm min)
```

### Python GUI Configuration (save_bpm.py)

**System Timing**:
```python
STABILIZATION_TIME = 5     # Stabilization duration (seconds)
BASELINE_RECORD_TIME = 30  # Baseline recording (seconds)
BREATHING_DURATION = 120   # Guided breathing (seconds)
POST_RECORD_TIME = 30      # Post-session recording (seconds)
```

**Breathing Guidance**:
```python
BREATHING_RATE = 6         # Breaths per minute
INHALE_TIME = 2.5          # Inhale duration (seconds)
EXHALE_TIME = 7.5          # Exhale duration (seconds)
```

**Validation Ranges**:
```python
BPM_MIN = 20, BPM_MAX = 300
RMSSD_MIN = 0, RMSSD_MAX = 250
```

## 📝 Code Structure

### Arduino (hrv.ino)
- **Setup Phase**: Sensor and LCD initialization
- **Main Loop**: Continuous sensor reading and processing
- **State Management**: Tracks stabilization, measuring, and completion phases
- **Peak Detection**: Hysteresis-based heartbeat detection
- **RMSSD Calculation**: Computes HRV metric from RR intervals
- **Serial Output**: Sends live and final measurements to Python

### Python (save_bpm.py)
- **SerialConnectionManager**: Handles ESP32 communication
- **DataValidator**: Validates BPM and RMSSD values
- **HRVDataManager**: Thread-safe data storage
- **GUI Layout**: Tkinter widgets for display
- **Breathing Pacer**: Animated guidance animation
- **Data Processing**: Parses incoming serial data
- **CSV Export**: Saves results with timestamps

## 📄 License

This project is provided for educational and research purposes.

## 🤝 Contributing

For improvements or bug fixes, please test thoroughly with hardware before submitting changes.





**Version**: 2.0  
**Last Updated**: June 2026  

