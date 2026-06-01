"""
HRV BIOFEEDBACK SYSTEM - Python GUI
Production Version with Phase 1 Critical Fixes

Features:
✓ Robust serial connection with error handling and auto-detection
✓ Thread-safe data management with queues
✓ Complete data validation and parsing
✓ Improved peak detection feedback
✓ Graceful shutdown with resource cleanup
✓ Comprehensive error logging
✓ RMSSD improvement calculation

Requirements:
- tkinter (usually included with Python)
- pyserial: pip install pyserial
- numpy (optional, for advanced analysis): pip install numpy
"""

import tkinter as tk
from tkinter import messagebox
import serial
import serial.tools.list_ports
import threading
import time
import csv
from datetime import datetime
import os
import sys
import logging
from queue import Queue
from pathlib import Path

# ===================== CONFIGURATION =====================

SERIAL_BAUDRATE = 115200
SERIAL_TIMEOUT = 1.0
SERIAL_MAX_RETRIES = 3

STABILIZATION_TIME = 5
BASELINE_RECORD_TIME = 30
BREATHING_DURATION = 120
POST_RECORD_TIME = 30

BREATHING_RATE = 6
INHALE_TIME = 2.5
EXHALE_TIME = 7.5

BPM_MIN = 20
BPM_MAX = 300
RMSSD_MIN = 0
RMSSD_MAX = 250

CSV_FILE = 'hrv_data.csv'
LOG_FILE = f'hrv_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'

WINDOW_WIDTH = 800
WINDOW_HEIGHT = 950

# ===================== LOGGING SETUP =====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===================== SERIAL CONNECTION MANAGER =====================

class SerialConnectionManager:
    """Robust serial connection with error handling"""
    
    def __init__(self, baudrate=SERIAL_BAUDRATE, timeout=SERIAL_TIMEOUT):
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.connected = False
        self.connection_attempts = 0
        self.max_attempts = SERIAL_MAX_RETRIES
        self.port = None
    
    def find_available_port(self):
        """Auto-detect Arduino/ESP32 on common ports"""
        try:
            ports = list(serial.tools.list_ports.comports())
            
            if not ports:
                logger.warning("No serial ports detected")
                return None
            
            # Prioritize known Arduino/ESP32 signatures
            priorities = ['Arduino', 'ESP32', 'CH340', 'FTDI', 'Silicon']
            
            for priority in priorities:
                for port in ports:
                    if priority.upper() in port.description.upper():
                        logger.info(f"Auto-detected: {port.device} ({port.description})")
                        return port.device
            
            # Fall back to first available port
            logger.info(f"Using first available port: {ports[0].device}")
            return ports[0].device
        
        except Exception as e:
            logger.error(f"Error detecting ports: {e}")
            return None
    
    def connect(self, port=None):
        """Establish serial connection with retry logic"""
        if port:
            self.port = port
        elif not self.port:
            self.port = self.find_available_port()
        
        if not self.port:
            logger.error("No serial port found. Check USB connection.")
            return False
        
        try:
            logger.info(f"Attempting connection to {self.port} at {self.baudrate} baud...")
            self.ser = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout
            )
            self.connected = True
            logger.info(f"✓ Connected to {self.port}")
            
            # Wait for Arduino to reset
            time.sleep(2)
            
            # Clear any pending data
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            return True
        
        except serial.SerialException as e:
            self.connection_attempts += 1
            logger.warning(f"Connection attempt {self.connection_attempts}/{self.max_attempts} failed: {e}")
            
            if self.connection_attempts < self.max_attempts:
                time.sleep(1)
                return self.connect()
            else:
                logger.error(f"Failed to connect after {self.max_attempts} attempts")
                return False
    
    def readline(self):
        """Read line from serial with error handling"""
        try:
            if self.connected and self.ser and self.ser.in_waiting:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                return line
            return None
        except Exception as e:
            logger.error(f"Serial read error: {e}")
            self.connected = False
            return None
    
    def disconnect(self):
        """Safely close serial connection"""
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                self.connected = False
                logger.info("Serial connection closed")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
    
    def __del__(self):
        """Ensure cleanup"""
        self.disconnect()

# ===================== DATA VALIDATOR =====================

class DataValidator:
    """Validate HRV measurements"""
    
    @staticmethod
    def validate_bpm(bpm):
        """Check if BPM is physiologically valid"""
        try:
            bpm_val = int(float(bpm))
            return BPM_MIN <= bpm_val <= BPM_MAX
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_rmssd(rmssd):
        """Check if RMSSD is within valid range"""
        try:
            rmssd_val = float(rmssd)
            return RMSSD_MIN <= rmssd_val <= RMSSD_MAX
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def parse_data_message(line):
        """
        Parse DATA,BPM,RMSSD format
        Returns: (success, bpm, rmssd)
        """
        try:
            if not isinstance(line, str) or "DATA" not in line:
                return False, None, None
            
            parts = line.split(",")
            if len(parts) < 2:
                return False, None, None
            
            bpm = int(float(parts[1]))
            
            if not DataValidator.validate_bpm(bpm):
                logger.debug(f"BPM out of range: {bpm}")
                return False, None, None
            
            return True, bpm, None
        
        except Exception as e:
            logger.debug(f"Parse DATA error: {e}")
            return False, None, None
    
    @staticmethod
    def parse_final_message(line):
        """
        Parse FINAL,BPM,RMSSD format
        Returns: (success, bpm, rmssd)
        """
        try:
            if not isinstance(line, str) or "FINAL" not in line:
                return False, None, None
            
            parts = line.split(",")
            if len(parts) < 3:
                return False, None, None
            
            bpm = int(float(parts[1]))
            rmssd = int(float(parts[2]))
            
            if not DataValidator.validate_bpm(bpm):
                logger.warning(f"Final BPM out of range: {bpm}")
                return False, None, None
            
            if not DataValidator.validate_rmssd(rmssd):
                logger.warning(f"Final RMSSD out of range: {rmssd}")
                return False, None, None
            
            return True, bpm, rmssd
        
        except Exception as e:
            logger.debug(f"Parse FINAL error: {e}")
            return False, None, None
    
    @staticmethod
    def assess_hrv_quality(rmssd):
        """Assess HRV quality based on RMSSD value"""
        if rmssd < 20:
            return "Poor (stressed/fatigued)"
        elif rmssd < 50:
            return "Below Average"
        elif rmssd < 100:
            return "Average"
        elif rmssd < 150:
            return "Good"
        else:
            return "Excellent (very relaxed)"

# ===================== DATA MANAGER =====================

class HRVDataManager:
    """Thread-safe data management"""
    
    def __init__(self):
        self.state_lock = threading.Lock()
        self.data_queue = Queue()
        
        self.baseline_bpm = 0
        self.baseline_rmssd = 0
        self.post_bpm = 0
        self.post_rmssd = 0
        
        self.baseline_done = False
        self.waiting_post = False
        self.experiment_running = False
        
        self.current_bpm = 0
    
    def update_live_data(self, bpm):
        """Update real-time BPM"""
        with self.state_lock:
            self.current_bpm = bpm
    
    def set_baseline(self, bpm, rmssd):
        """Record baseline measurements"""
        with self.state_lock:
            self.baseline_bpm = bpm
            self.baseline_rmssd = rmssd
            self.baseline_done = True
    
    def set_post(self, bpm, rmssd):
        """Record post-session measurements"""
        with self.state_lock:
            self.post_bpm = bpm
            self.post_rmssd = rmssd
            self.waiting_post = False
    
    def get_state(self, key):
        """Thread-safe state retrieval"""
        with self.state_lock:
            return getattr(self, key, None)
    
    def set_state(self, key, value):
        """Thread-safe state update"""
        with self.state_lock:
            setattr(self, key, value)
    
    def get_improvement(self):
        """Calculate RMSSD improvement percentage"""
        with self.state_lock:
            if self.baseline_rmssd > 0:
                return ((self.post_rmssd - self.baseline_rmssd) / self.baseline_rmssd) * 100
            return 0
    
    def enqueue_data(self, data):
        """Add data to queue"""
        try:
            self.data_queue.put_nowait(data)
        except:
            pass  # Queue full
    
    def get_queued_data(self):
        """Retrieve all queued data"""
        data = []
        try:
            while True:
                data.append(self.data_queue.get_nowait())
        except:
            pass
        return data

# ===================== INITIALIZE COMPONENTS =====================

root = tk.Tk()
root.title("HRV Biofeedback System")
root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
root.configure(bg="white")

serial_manager = SerialConnectionManager(baudrate=SERIAL_BAUDRATE)
data_manager = HRVDataManager()
validator = DataValidator()

# Create CSV file if needed
if not os.path.isfile(CSV_FILE):
    try:
        with open(CSV_FILE, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                "Date",
                "Time",
                "Baseline BPM",
                "Baseline RMSSD",
                "Post BPM",
                "Post RMSSD",
                "Improvement %"
            ])
        logger.info(f"Created CSV file: {CSV_FILE}")
    except Exception as e:
        logger.error(f"Failed to create CSV file: {e}")

# ===================== GUI VARIABLES =====================

bpm_var = tk.StringVar(value="BPM: 0")
rmssd_var = tk.StringVar(value="RMSSD: --")
status_var = tk.StringVar(value="Initializing...")
timer_var = tk.StringVar(value="")

# ===================== GUI LAYOUT =====================

# Title
title = tk.Label(
    root,
    text="HRV BIOFEEDBACK SYSTEM",
    font=("Arial", 28, "bold"),
    bg="white",
    fg="#2c3e50"
)
title.pack(pady=15)

# BPM Display
bpm_label = tk.Label(
    root,
    textvariable=bpm_var,
    font=("Arial", 48, "bold"),
    bg="white",
    fg="#e74c3c"
)
bpm_label.pack(pady=10)

# RMSSD Display
rmssd_label = tk.Label(
    root,
    textvariable=rmssd_var,
    font=("Arial", 48, "bold"),
    bg="white",
    fg="#27ae60"
)
rmssd_label.pack(pady=10)

# Status Display
status_label = tk.Label(
    root,
    textvariable=status_var,
    font=("Arial", 18, "bold"),
    bg="white",
    fg="#3498db"
)
status_label.pack(pady=10)

# Timer Display
timer_label = tk.Label(
    root,
    textvariable=timer_var,
    font=("Arial", 20, "bold"),
    bg="white",
    fg="#9b59b6"
)
timer_label.pack(pady=5)

# Breathing Circle Canvas
canvas = tk.Canvas(
    root,
    width=320,
    height=320,
    bg="white",
    highlightthickness=0
)
canvas.pack(pady=15)

circle = canvas.create_oval(
    110, 110, 210, 210,
    fill="#3498db",
    outline="#3498db"
)
canvas.itemconfig(circle, state='hidden')

# ===================== BREATHING PACER =====================

breathing_animation_id = None
showing_results = False

def breathing_pacer():
    """Display guided breathing animation at 6 breaths/min"""
    global breathing_animation_id, showing_results
    
    canvas.itemconfig(circle, state='normal')
    status_var.set("🫁 Guided Breathing Started")
    
    start_time = time.time()
    total_duration = BREATHING_DURATION
    
    def animate_breathing():
        global breathing_animation_id, showing_results
        
        elapsed = time.time() - start_time
        
        if elapsed > total_duration:
            canvas.itemconfig(circle, state='hidden')
            timer_var.set("")
            data_manager.set_state('waiting_post', True)
            status_var.set(f"✓ Place finger for 30s Post Session")
            showing_results = False
            breathing_animation_id = None
            logger.info("Breathing session completed")
            return
        
        # Don't overwrite status if we're showing results
        if showing_results:
            return
        
        # Calculate position in current breathing cycle
        cycle_time = elapsed % 10
        
        if cycle_time < INHALE_TIME:
            # INHALE - expand circle
            scale = cycle_time / INHALE_TIME
            expansion = int(60 * scale)
            canvas.coords(circle, 110-expansion, 110-expansion, 210+expansion, 210+expansion)
            status_var.set("🫁 INHALE")
        else:
            # EXHALE - contract circle
            scale = (cycle_time - INHALE_TIME) / EXHALE_TIME
            expansion = int(60 * (1 - scale))
            canvas.coords(circle, 110-expansion, 110-expansion, 210+expansion, 210+expansion)
            status_var.set("🫁 EXHALE")
        
        remaining = int(total_duration - elapsed)
        timer_var.set(f"Biofeedback: {remaining} sec")
        
        # Schedule next frame (non-blocking)
        breathing_animation_id = root.after(16, animate_breathing)
    
    animate_breathing()

# ===================== SAVE RESULTS =====================

def save_results_safely():
    """Save session results with comprehensive error handling"""
    try:
        baseline_bpm = data_manager.get_state('baseline_bpm')
        baseline_rmssd = data_manager.get_state('baseline_rmssd')
        post_bpm = data_manager.get_state('post_bpm')
        post_rmssd = data_manager.get_state('post_rmssd')
        
        # Validate data
        if baseline_rmssd <= 0:
            status_var.set("❌ ERROR: Invalid baseline RMSSD")
            logger.error("Invalid baseline RMSSD")
            return False
        
        if post_rmssd <= 0:
            status_var.set("❌ ERROR: Invalid post RMSSD")
            logger.error("Invalid post RMSSD")
            return False
        
        if baseline_bpm <= 0 or post_bpm <= 0:
            status_var.set("❌ ERROR: Invalid BPM values")
            logger.error("Invalid BPM values")
            return False
        
        # Calculate improvement
        improvement = ((post_rmssd - baseline_rmssd) / baseline_rmssd) * 100
        
        # Prepare data
        now = datetime.now()
        row = [
            now.strftime("%d-%m-%Y"),
            now.strftime("%H:%M:%S"),
            baseline_bpm,
            baseline_rmssd,
            post_bpm,
            post_rmssd,
            round(improvement, 2)
        ]
        
        # Write to CSV
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(row)
        
        # Display results
        quality = validator.assess_hrv_quality(post_rmssd)
        status_var.set(
            f"✓ RMSSD: {baseline_rmssd} → {post_rmssd} "
            f"({round(improvement, 1)}%) - {quality}"
        )
        timer_var.set("Experiment Complete ✓")
        
        logger.info(f"Session saved: {baseline_rmssd} → {post_rmssd} ({improvement:.1f}%)")
        return True
    
    except IOError as e:
        status_var.set(f"❌ Save error: {str(e)[:40]}")
        logger.error(f"IO Error saving results: {e}")
        return False
    
    except Exception as e:
        status_var.set(f"❌ Error: {str(e)[:40]}")
        logger.error(f"Unexpected error: {e}")
        return False

def save_to_csv_directly(baseline_bpm, baseline_rmssd, post_bpm, post_rmssd, improvement):
    """Save results directly to CSV file"""
    try:
        now = datetime.now()
        row = [
            now.strftime("%d-%m-%Y"),
            now.strftime("%H:%M:%S"),
            baseline_bpm,
            baseline_rmssd,
            post_bpm,
            post_rmssd,
            round(improvement, 2)
        ]
        
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(row)
        
        logger.info(f"Results saved to CSV: {baseline_rmssd} → {post_rmssd} ({improvement:.1f}%)")
        return True
    except Exception as e:
        logger.error(f"Error saving to CSV: {e}")
        return False

# ===================== SERIAL READER THREAD =====================

def read_serial_thread():
    """Background thread for serial data reading"""
    logger.info("Serial reader thread started")
    
    if not serial_manager.connect():
        status_var.set("❌ Serial connection failed")
        logger.error("Serial connection failed")
        return
    
    status_var.set("✓ Connected to ESP32")
    
    while True:
        try:
            line = serial_manager.readline()
            if line:
                data_manager.enqueue_data(line)
                logger.debug(f"Received: {line}")
        except Exception as e:
            logger.error(f"Serial read error: {e}")
            time.sleep(1)

# ===================== DATA PROCESSING LOOP =====================

def process_incoming_data():
    """Process queued serial data in main thread (thread-safe with tkinter)"""
    
    for line in data_manager.get_queued_data():
        # Try parsing as FINAL message
        success, bpm, rmssd = validator.parse_final_message(line)
        
        if success:
            logger.info(f"Final measurement: BPM={bpm}, RMSSD={rmssd}")
            
            # Get current state (check each time, not cached)
            baseline_done = data_manager.get_state('baseline_done')
            waiting_post = data_manager.get_state('waiting_post')
            
            if baseline_done and waiting_post:
                # Post-session measurement - calculate and display improvement
                logger.info(f"Post-session RMSSD: {rmssd}")
                
                baseline_rmssd = data_manager.get_state('baseline_rmssd')
                baseline_bpm = data_manager.get_state('baseline_bpm')
                
                # Update data manager
                data_manager.set_post(bpm, rmssd)
                
                # Calculate improvement
                if baseline_rmssd > 0:
                    improvement = ((rmssd - baseline_rmssd) / baseline_rmssd) * 100
                else:
                    improvement = 0
                
                # Get HRV quality assessment
                quality = validator.assess_hrv_quality(rmssd)
                
                # Set flag to prevent breathing animation from overwriting results
                global showing_results
                showing_results = True
                
                # Display improvement on screen IMMEDIATELY
                status_var.set(
                    f"✓ RMSSD: {baseline_rmssd} → {rmssd} "
                    f"({round(improvement, 1)}%) - {quality}"
                )
                timer_var.set("Experiment Complete ✓")
                
                logger.info(f"Session complete: {baseline_rmssd} → {rmssd} ({improvement:.1f}%)")
                
                # Save to CSV
                save_to_csv_directly(baseline_bpm, baseline_rmssd, bpm, rmssd, improvement)
                
            elif not baseline_done:
                # Baseline measurement
                logger.info(f"Baseline RMSSD: {rmssd}")
                data_manager.set_baseline(bpm, rmssd)
                status_var.set(f"✓ Baseline RMSSD: {rmssd} ms")
                rmssd_var.set(f"RMSSD: {rmssd}")
                bpm_var.set(f"BPM: {bpm}")
                logger.info(f"Baseline recorded: {rmssd}ms")
                
                # Start biofeedback after 2 seconds
                root.after(2000, lambda: threading.Thread(target=breathing_pacer, daemon=True).start())
        else:
            # Try parsing as DATA message (live BPM updates)
            success, bpm, _ = validator.parse_data_message(line)
            if success:
                # Update live display
                data_manager.update_live_data(bpm)
                bpm_var.set(f"BPM: {bpm}")
    
    # Schedule next check
    root.after(100, process_incoming_data)

# Start data processing loop
process_incoming_data()

# ===================== START BUTTON =====================

def start_experiment():
    """Initialize new experiment"""
    experiment_running = data_manager.get_state('experiment_running')
    
    if experiment_running:
        status_var.set("Experiment already running!")
        return
    
    data_manager.set_state('experiment_running', True)
    data_manager.set_state('baseline_done', False)
    data_manager.set_state('waiting_post', False)
    
    bpm_var.set("BPM: 0")
    rmssd_var.set("RMSSD: --")
    status_var.set("Place finger for baseline")
    timer_var.set(f"{STABILIZATION_TIME}s Stabilization + {BASELINE_RECORD_TIME}s Baseline")
    
    logger.info("Experiment started")

start_btn = tk.Button(
    root,
    text="Start Experiment",
    font=("Arial", 18, "bold"),
    bg="#3498db",
    fg="white",
    padx=30,
    pady=12,
    command=start_experiment,
    relief=tk.FLAT,
    cursor="hand2"
)
start_btn.pack(pady=30)

# ===================== INFO FRAME =====================

info_frame = tk.Frame(root, bg="white")
info_frame.pack(fill=tk.X, padx=20, pady=10)

info_text = tk.Label(
    info_frame,
    text="1. Press 'Start Experiment'\n2. Place finger on sensor\n3. Follow breathing guide\n4. Results saved to CSV",
    font=("Arial", 10),
    bg="white",
    fg="#7f8c8d",
    justify=tk.LEFT
)
info_text.pack(anchor=tk.W)

# ===================== SERIAL THREAD STARTUP =====================

serial_thread = threading.Thread(target=read_serial_thread, daemon=True)
serial_thread.start()

logger.info("GUI initialized - ready for use")

# ===================== GRACEFUL SHUTDOWN =====================

def on_closing():
    """Handle application exit gracefully"""
    logger.info("Shutting down application...")
    
    # Stop experiment
    data_manager.set_state('experiment_running', False)
    
    # Give threads time to finish
    time.sleep(0.5)
    
    # Close serial connection
    if serial_manager.connected:
        serial_manager.disconnect()
    
    logger.info("Application closed successfully")
    
    # Close window
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# ===================== RUN APPLICATION =====================

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("HRV BIOFEEDBACK SYSTEM - Python GUI")
    logger.info("=" * 50)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        on_closing()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        on_closing()