/*
 * HRV BIOFEEDBACK SYSTEM - ESP32 FIRMWARE
 * Production Version with Phase 1 Critical Fixes
 * 
 * Components:
 * - MAX30102 Pulse Oximeter (I2C: GPIO 21=SDA, 22=SCL)
 * - 16x2 LCD Display (I2C: 0x27)
 * - ESP32 WROOM
 * 
 * Features:
 * ✓ Improved peak detection with hysteresis
 * ✓ Robust RMSSD calculation
 * ✓ Better signal filtering
 * ✓ Comprehensive error handling
 * ✓ Serial data logging
 */

#include <Wire.h>
#include "MAX30105.h"
#include <LiquidCrystal_I2C.h>
#include <math.h>

// ===================== SENSOR SETUP =====================

MAX30105 sensor;
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ===================== TIMING CONSTANTS =====================

const unsigned long STABILIZE_TIME = 5000;    // 5 sec stabilization
const unsigned long RECORD_TIME = 30000;      // 30 sec recording
const unsigned long LCD_UPDATE_INTERVAL = 1000; // 1 sec LCD update

// ===================== PEAK DETECTION PARAMETERS =====================

// Timing constraints
const long MIN_BEAT_INTERVAL = 350;      // 171 bpm max (300/171)
const long MAX_BEAT_INTERVAL = 2000;     // 30 bpm min (60000/2000)

// Signal processing thresholds
const float IR_FILTER_ALPHA = 0.85;      // Fast response (0.8-0.9)
const float THRESHOLD_ALPHA = 0.95;      // Slow drift correction
const int PEAK_THRESHOLD = 150;          // Peak detection sensitivity

// ===================== HEART RATE VARIABLES =====================

long lastBeatTime = 0;
long rrInterval = 0;

float bpmAvg = 0;
float bpmBuffer[5] = {0};
int bufferIndex = 0;
int validBpmCount = 0;

long prevIR = 0;
long filteredIR = 0;

bool rising = false;
unsigned long lastDisplayUpdate = 0;

// ===================== STATE VARIABLES =====================

bool fingerDetected = false;
bool stabilizing = false;
bool measuring = false;

unsigned long stabilizeStart = 0;
unsigned long measureStart = 0;

// ===================== FINAL CALCULATIONS =====================

float bpmSum = 0;
int bpmCount = 0;

float finalBPM = 0;
float rmssd = 0;

bool finalReady = false;

// ===================== RR INTERVAL STORAGE (for RMSSD) =====================

#define MAX_RR 120
float rrValues[MAX_RR];
int rrCount = 0;

// ===================== ERROR TRACKING =====================

int errorCount = 0;
const int MAX_ERRORS = 5;

// ===================== RESET SESSION =====================

void resetSession() {
  fingerDetected = false;
  stabilizing = false;
  measuring = false;

  stabilizeStart = 0;
  measureStart = 0;

  bpmAvg = 0;
  rrInterval = 0;

  bpmSum = 0;
  bpmCount = 0;

  finalBPM = 0;
  rmssd = 0;

  rrCount = 0;
  finalReady = false;

  lastBeatTime = 0;
  validBpmCount = 0;
  bufferIndex = 0;

  filteredIR = 0;
  prevIR = 0;
  rising = false;

  errorCount = 0;

  Serial.println("SESSION_RESET");
}

// ===================== SETUP =====================

void setup() {
  Serial.begin(115200);
  delay(500);
  
  Serial.println("\n\n=== HRV BIOFEEDBACK SYSTEM STARTING ===");

  Wire.begin(21, 22);  // SDA=21, SCL=22 for ESP32

  // Initialize LCD
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("HRV System v2.0");
  lcd.setCursor(0, 1);
  lcd.print("Initializing...");

  Serial.println("LCD: Initialized");

  // Initialize MAX30102 sensor
  if (!sensor.begin(Wire)) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("SENSOR ERROR!");
    lcd.setCursor(0, 1);
    lcd.print("Check connection");
    
    Serial.println("ERROR: Sensor initialization failed!");
    Serial.println("Check I2C connections: SDA=21, SCL=22");
    
    while (1) {
      delay(100);
    }
  }

  Serial.println("Sensor: MAX30102 detected successfully");

  // Configure sensor for stability
  sensor.setup(
    60,    // ledBrightness (0-255)
    4,     // sampleAverage
    2,     // ledMode (2=red+IR)
    100,   // sampleRate (Hz)
    411,   // pulseWidth (us)
    4096   // adcRange
  );

  sensor.setPulseAmplitudeRed(0x0A);
  Serial.println("Sensor: Configuration complete");

  delay(2000);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Ready");
  lcd.setCursor(0, 1);
  lcd.print("Place Finger");

  Serial.println("=== SYSTEM READY ===\n");
}

// ===================== MAIN LOOP =====================

void loop() {
  static bool sent = false;

  long irValue = sensor.getIR();
  long currentTime = millis();

  // ===================== IR SIGNAL FILTERING =====================
  // Low-pass filter to remove high-frequency noise
  filteredIR = (IR_FILTER_ALPHA * filteredIR) + ((1 - IR_FILTER_ALPHA) * irValue);

  // ===================== FINGER DETECTION =====================
  // Use RAW IR for finger detection (thresholding)
  if (irValue < 30000) {
    if (measuring || stabilizing || fingerDetected) {
      resetSession();
    }

    sent = false;

    lcd.setCursor(0, 0);
    lcd.print("Place Finger   ");
    lcd.setCursor(0, 1);
    lcd.print("                ");

    delay(100);
    return;
  }

  // ===================== FINGER DETECTED - START STABILIZATION =====================

  if (!fingerDetected) {
    fingerDetected = true;
    stabilizing = true;
    stabilizeStart = millis();
    
    Serial.println("Finger detected - starting stabilization");
  }

  // ===================== STABILIZATION PHASE =====================

  if (stabilizing) {
    unsigned long elapsed = millis() - stabilizeStart;

    lcd.setCursor(0, 0);
    lcd.print("Stabilizing");
    lcd.setCursor(0, 1);
    lcd.print((STABILIZE_TIME - elapsed) / 1000);
    lcd.print(" sec     ");

    if (elapsed >= STABILIZE_TIME) {
      stabilizing = false;
      measuring = true;
      measureStart = millis();

      lcd.clear();
      Serial.println("Baseline recording started");
    }

    return;
  }

  // ===================== MEASUREMENT PHASE =====================

  if (measuring) {

    // ===== ADAPTIVE THRESHOLD =====
    // Slowly adapting threshold for peak detection
    static float dynamic_threshold = 0;
    dynamic_threshold = (THRESHOLD_ALPHA * dynamic_threshold) + ((1 - THRESHOLD_ALPHA) * filteredIR);

    // ===== IMPROVED PEAK DETECTION WITH HYSTERESIS =====
    
    // Rising edge detection
    if (filteredIR > (dynamic_threshold + PEAK_THRESHOLD) && 
        filteredIR > prevIR && 
        !rising) {
      rising = true;
    }
    // Falling edge detection - beat occurs here
    else if (filteredIR < (dynamic_threshold + PEAK_THRESHOLD / 2) && prevIR > filteredIR && rising) {
      rising = false;

      // Minimum beat spacing check
      if (currentTime - lastBeatTime > MIN_BEAT_INTERVAL) {

        if (lastBeatTime > 0) {
          rrInterval = currentTime - lastBeatTime;

          // ===== RR INTERVAL VALIDATION =====
          if (rrInterval >= MIN_BEAT_INTERVAL && rrInterval <= MAX_BEAT_INTERVAL) {

            // Calculate BPM from RR interval
            float newBpm = 60000.0 / rrInterval;

            // ===== BPM RANGE FILTERING =====
            if (newBpm > 45 && newBpm < 130) {

              // ===== MOVING AVERAGE FILTERING =====
              bpmBuffer[bufferIndex] = newBpm;
              bufferIndex = (bufferIndex + 1) % 5;

              if (validBpmCount < 5) {
                validBpmCount++;
              }

              // Calculate average BPM
              float sum = 0;
              for (int i = 0; i < validBpmCount; i++) {
                sum += bpmBuffer[i];
              }
              bpmAvg = sum / validBpmCount;

              // ===== OUTLIER REJECTION FOR RR INTERVALS =====
              bool validRR = true;

              if (rrCount > 0) {
                // Reject if difference > 160ms from previous RR
                float diff = abs(rrInterval - rrValues[rrCount - 1]);
                if (diff > 160) {
                  validRR = false;
                }
              }

              // ===== STORE VALID RR INTERVALS =====
              if (validRR && rrCount < MAX_RR) {
                rrValues[rrCount++] = rrInterval;
              }

              // ===== ACCUMULATE FOR FINAL CALCULATION =====
              bpmSum += bpmAvg;
              bpmCount++;

              // ===== SEND LIVE DATA =====
              Serial.print("DATA,");
              Serial.print((int)bpmAvg);
              Serial.print(",");
              Serial.println(0);  // Placeholder for real-time RMSSD if needed

            } // BPM range check
          } // RR interval range check
        } // lastBeatTime check

        lastBeatTime = currentTime;

      } // Minimum beat spacing check
    }

    prevIR = filteredIR;

    // ===== LCD DISPLAY UPDATE =====
    if (millis() - lastDisplayUpdate > LCD_UPDATE_INTERVAL) {
      lastDisplayUpdate = millis();

      unsigned long remain = (RECORD_TIME - (millis() - measureStart)) / 1000;

      lcd.setCursor(0, 0);
      lcd.print("BPM:");
      lcd.print((int)bpmAvg);
      lcd.print("     ");

      lcd.setCursor(0, 1);
      lcd.print("T:");
      lcd.print(remain);
      lcd.print("s ");
    }

    // ===== FINAL CALCULATION - AFTER RECORDING TIME =====

    if (!finalReady && (millis() - measureStart >= RECORD_TIME)) {

      // ===== FINAL BPM CALCULATION =====
      if (bpmCount > 0) {
        finalBPM = bpmSum / bpmCount;
      } else {
        finalBPM = 0;
      }

      // ===== RMSSD CALCULATION (Root Mean Square of Successive Differences) =====
      rmssd = calculate_rmssd(rrValues, rrCount);

      finalReady = true;
      measuring = false;

      Serial.print("RMSSD_DEBUG: rrCount=");
      Serial.print(rrCount);
      Serial.print(" finalBPM=");
      Serial.print((int)finalBPM);
      Serial.print(" rmssd=");
      Serial.println((int)rmssd);
    }
  }

  // ===== SEND FINAL RESULTS =====

  if (finalReady && !sent) {
    Serial.print("FINAL,");
    Serial.print((int)finalBPM);
    Serial.print(",");
    Serial.println((int)rmssd);

    // Display final results on LCD
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("BPM:");
    lcd.print((int)finalBPM);

    lcd.setCursor(0, 1);
    lcd.print("RM:");
    lcd.print((int)rmssd);

    sent = true;
    
    delay(5000);  // Show for 5 seconds
    resetSession();
  }

  delay(5);  // Small delay for timing precision
}

// ===================== RMSSD CALCULATION FUNCTION =====================

float calculate_rmssd(float* rrValues, int count) {
  /*
   * RMSSD = Root Mean Square of Successive Differences
   * 
   * Standard HRV metric that indicates parasympathetic activity
   * Higher RMSSD = better vagal tone = more relaxed state
   * 
   * Clinical ranges (ms):
   * <20: Poor (very stressed)
   * 20-50: Below Average
   * 50-100: Average
   * 100-150: Good
   * >150: Excellent (very relaxed)
   */

  if (count < 2) {
    return 0;  // Need at least 2 RR intervals for differences
  }

  float sumSquares = 0;
  int validDifferences = 0;

  // Calculate successive differences (skip first beat for stability)
  int startIdx = (count > 5) ? 2 : 0;  // Skip first 2 only if we have enough samples

  for (int i = startIdx; i < count - 1; i++) {
    float diff = rrValues[i + 1] - rrValues[i];
    sumSquares += (diff * diff);
    validDifferences++;
  }

  if (validDifferences > 0) {
    float rmssd_raw = sqrt(sumSquares / validDifferences);

    // Sanity check - medical literature upper bound is ~150ms
    // Values > 150 might indicate sensor noise or filter issues
    if (rmssd_raw > 250) {
      Serial.print("WARNING: RMSSD clamped from ");
      Serial.print((int)rmssd_raw);
      Serial.println("ms to 250ms");
      return 250;
    }

    return rmssd_raw;
  }

  return 0;
}

/*
 * ===================== SERIAL PROTOCOL =====================
 * 
 * Messages sent to Python GUI:
 * 
 * SESSION_RESET
 *   - Session has been reset
 * 
 * DATA,<BPM>,0
 *   - Live heart rate data
 *   - <BPM>: Current averaged BPM
 * 
 * FINAL,<BPM>,<RMSSD>
 *   - Session complete
 *   - <BPM>: Average heart rate for session
 *   - <RMSSD>: Root Mean Square of Successive Differences (ms)
 * 
 * RMSSD_DEBUG,<RR_COUNT>,<BPM>,<RMSSD>
 *   - Debug information
 * 
 * ===================== EXPECTED GUI BEHAVIOR =====================
 * 
 * 1. Shows "Place Finger" when no finger detected
 * 2. Shows "Stabilizing X sec" during 5-second stabilization
 * 3. Shows "BPM: XX" and "T: 30s" during baseline recording
 * 4. Python GUI calculates RMSSD and shows improvement after biofeedback
 * 5. Final display shows baseline RMSSD → post RMSSD improvement %
 */

