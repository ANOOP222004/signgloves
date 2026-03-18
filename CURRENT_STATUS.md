# Smart Glove Project — Current Status
# ============================================================
# CRITICAL: Read this file FIRST in every new Claude session.
#
# FILES UPLOADED TO PROJECT KNOWLEDGE (read all of them):
#   1. CURRENT_STATUS.md                            ← this file
#   2. SmartGlove_ProjectDocumentation_Updated.docx ← full project overview
#   3. SmartGlove_Phase2_Documentation.docx         ← Phase 2 deep technical detail
#   4. config.py                                    ← ALL constants
#   5. main.py                                      ← Phase 2 entry point
#   6. serial_thread.py                             ← serial communication
#   7. packet_parser.py                             ← packet validation
#   8. frame.py                                     ← data structures
#   9. filter.py                                    ← EMA filter
#   10. calibration.py                              ← normalization
#   11. processing_thread.py                        ← pipeline thread
#
# These files represent the COMPLETE codebase as of Phase 2.
# Do NOT assume anything not stated here or visible in these files.
# Last updated: Phase 2 Complete
# ============================================================

---

## Project Summary
Building an AI Sign-to-Speech Smart Glove system. Two gloves with Hall sensors
and IMU capture hand gestures. A BiLSTM ML model recognizes gestures and
converts them to text/speech. The system runs fully on embedded hardware (Edge AI).

The current software effort is the Smart Glove Dataset Studio — a Python desktop
application for recording, managing, and exporting a labeled gesture dataset.

---

## Team & Environment
- Developer: Anoop
- OS: Ubuntu 22.04
- Python: python3 (never 'python' — Ubuntu 22.04 has no 'python' command)
- Python venv: ~/signgloves/venv/ (auto-activates when cd into ~/signgloves)
- Project folder: ~/signgloves/
- GitHub repo: https://github.com/ANOOP222004/signgloves (Private)
- Arduino IDE: installed on Ubuntu 22.04
- ESP32 port: /dev/ttyUSB0 (appears as option 32 in port list)

---

## Folder Structure (Exact — Do Not Assume Differently)

```
~/signgloves/                                    ← git repo root
├── smart_dataset_studio/                        ← ALL Python software
│   ├── main.py                                  ← Phase 2 entry point (current)
│   ├── config.py                                ← ALL constants (single source of truth)
│   ├── requirements.txt                         ← pyserial>=3.5, pyqt5>=5.15
│   ├── test_filter.py                           ← Phase 2 standalone test (PASSING)
│   ├── test_calibration.py                      ← Phase 2 standalone test (PASSING)
│   ├── communication/
│   │   ├── __init__.py                          ← empty, marks package
│   │   ├── serial_thread.py                     ← reads serial port, pushes to Queue
│   │   └── packet_parser.py                     ← 5-layer validation, returns frame dict
│   └── processing/
│       ├── __init__.py                          ← empty, marks package
│       ├── frame.py                             ← make_raw_frame(), make_processed_frame()
│       ├── filter.py                            ← EMAFilter class (Phase 2)
│       ├── calibration.py                       ← CalibrationData, Calibrator (Phase 2)
│       └── processing_thread.py                 ← ProcessingThread(QThread) (Phase 2)
├── firmware/
│   └── phase1_slave_esp32/
│       └── phase1_slave_esp32.ino               ← CURRENTLY FLASHED, do not reflash
├── docs/
│   ├── SmartGlove_ProjectDocumentation_Updated.docx
│   ├── SmartGlove_Phase1_Documentation.docx
│   └── SmartGlove_Phase2_Documentation.docx
├── venv/                                        ← Python virtual environment
├── .gitignore                                   ← excludes venv/, __pycache__/, data/
└── CURRENT_STATUS.md                            ← this file
```

NOTE: data/ folder is git-ignored. Created at runtime by the application:
```
smart_dataset_studio/data/
├── calibration/    ← named user profile JSON files (e.g. anoop.json)
└── dataset/        ← gesture CSV files (Phase 4+, not yet created)
```

NOTE: ui/ and visualization/ folders do NOT exist yet — Phase 3 will create them.
NOTE: recording/ and dataset/ module folders do NOT exist yet — Phase 4 will create them.

---

## config.py — Exact Contents (Verified)

```python
# ============================================================
# Smart Glove Dataset Studio - config.py
# Single source of truth for all constants
# Never use magic numbers anywhere else in the codebase
# ============================================================

# --- Serial ---
BAUD_RATE      = 115200
QUEUE_MAX_SIZE = 100        # ~3.3 seconds buffer at 30 Hz

# --- Sampling ---
SAMPLE_RATE     = 30        # Hz
WINDOW_SIZE     = 60        # frames per gesture sample
FRAME_PERIOD_MS = 33        # milliseconds per frame

# --- Filter ---
EMA_ALPHA = 0.25            # balances noise smoothing vs responsiveness at 30 Hz

# --- Frame ID ---
FRAME_ID_MAX = 9999         # max value frame_id reaches before rollover to 0
                            # IMPORTANT: modulo in processing_thread uses (FRAME_ID_MAX + 1)
                            # i.e. % 10000 — NOT % 9999

# --- Paths ---
DATASET_PATH    = "data/dataset/"
CALIBRATION_PATH = "data/calibration/"

# --- Features ---
NUM_FEATURES = 16
FEATURE_ORDER = [
    "R_T", "R_I", "R_M", "R_R", "R_L", "R_P", "R_RL", "R_Y",
    "L_T", "L_I", "L_M", "L_R", "L_L", "L_P", "L_RL", "L_Y"
]

# Calibration
CALIBRATION_DIR = 'data/calibration'

# Channel name lists — used by calibration and processing
FINGER_CHANNELS = ['thumb', 'index', 'middle', 'ring', 'little']
IMU_CHANNELS    = ['pitch', 'roll', 'yaw']
```

IMPORTANT NOTES ON CONFIG:
- QUEUE_MAX_SIZE = 100 (NOT QUEUE_SIZE — serial_thread.py uses QUEUE_MAX_SIZE)
- FRAME_ID_MAX = 9999 (the max VALUE, NOT the modulo)
- Modulo for rollover = (FRAME_ID_MAX + 1) = 10000
- processing_thread.py imports: FINGER_CHANNELS, IMU_CHANNELS, FRAME_ID_MAX only
- CALIBRATION_DIR and CALIBRATION_PATH both exist (slight redundancy — use CALIBRATION_DIR)

---

## Key API / Function Signatures (Exact — From Uploaded Files)

### frame.py
```python
make_raw_frame(frame_id, r_t, r_i, r_m, r_r, r_l, r_p, r_rl, r_y,
                          l_t, l_i, l_m, l_r, l_l, l_p, l_rl, l_y) -> dict
# Returns: {'frame_id': int, 'right': {'thumb': int, 'index': int, 'middle': int,
#            'ring': int, 'little': int, 'pitch': float, 'roll': float, 'yaw': float},
#           'left': {same structure}}

make_processed_frame(frame_id, ...) -> dict
# Same structure but finger values are floats 0.0-1.0

frame_to_feature_vector(processed_frame) -> list
# Returns flat 16-element list matching FEATURE_ORDER
```

### filter.py
```python
class EMAFilter:
    def __init__(self, alpha: float = EMA_ALPHA)
    def update(self, new_value: float) -> float
    def reset(self)
    # previous_filtered starts as None (not 0 — seeded on first call)
```

### calibration.py
```python
class CalibrationData:
    def __init__(self)
    def set_min(self, hand: str, channel: str, value: float)
    def set_max(self, hand: str, channel: str, value: float)
    def is_complete(self) -> bool

class Calibrator:
    def __init__(self, calibration_data: CalibrationData)
    def normalize_finger(self, hand: str, channel: str, filtered_value: float) -> float
    def normalize_frame(self, raw_frame: dict) -> dict

# File functions:
save_calibration(calibration_data: CalibrationData) -> str  # returns filepath
load_calibration(filepath: str) -> CalibrationData
get_today_calibration_path() -> str | None
```

### processing_thread.py
```python
class ProcessingThread(QThread):
    # Signals:
    frame_ready = pyqtSignal(object)       # emits processed_frame dict
    frame_drop_detected = pyqtSignal(int)  # emits drop count (during recording)
    status_message = pyqtSignal(str)       # emits warning strings

    def __init__(self, frame_queue: queue.Queue, calibration_data: CalibrationData)
    def set_recording(self, recording: bool)  # call from Phase 4 recorder
    def reset_filters(self)                    # call on reconnect or new session
    def stop(self)                             # then call thread.wait()
    def run(self)                              # called by start(), never call directly
```

### serial_thread.py
```python
class SerialThread(threading.Thread):  # NOTE: plain threading.Thread, NOT QThread
    def __init__(self, port: str, frame_queue: queue.Queue)
    def run(self)
    def stop(self)
    @staticmethod
    def list_ports() -> list  # returns list of port name strings
```

### packet_parser.py
```python
def parse_packet(raw_line: str) -> dict | None
# Returns Raw Frame dict on success, None on any validation failure
# Handles: READY, ERR,1 ERR,2 ERR,3, comment lines (#), unknown prefix
```

---

## Hardware Details

### One-Finger Prototype (Current Hardware)
- Board: ESP32 DevKit (standard, NOT S3)
- Hall sensor: SS49E on GPIO 32 (Right Thumb only — all others are dummy)
- IMU: MPU6050 — available but NOT yet integrated into firmware
- All other 15 channels: dummy values (2048 ADC, 0.0 IMU)

### SS49E Sensor Physical Details
- Pin layout (flat face toward you): Pin1=VCC(3.3V), Pin2=GND, Pin3=OUTPUT→GPIO32
- Sensor position: middle phalanx (PIP joint) — NOT the knuckle
- Magnet position: distal phalanx (fingertip side)
- No magnet baseline: ~1.65V (midpoint of 3.3V — correct)
- Finger OPEN:   ~2900 ADC (magnet close → higher voltage)
- Finger CLOSED: ~1650 ADC (magnet moves away → lower voltage)
- ADC range: ~1550 counts (38% of 4095) — sufficient for ML
- Sensor is INVERTED: higher ADC = more open (not more bent)

### Calibration Direction (Critical)
- set_min() = open hand position (ADC ~2900) — records HIGHER value as min
- set_max() = closed hand position (ADC ~1650) — records LOWER value as max
- Formula: bend = (filtered - min) / (max - min) → negative/negative = positive
- Open hand → 0.0, Closed hand → 1.0 ✅

### Master Glove (Future)
- Board: ESP32-S3 DevKit — NOT yet programmed
- Will run TensorFlow Lite for Microcontrollers
- Waiting for full 3D-printed glove assembly

### Full Glove Transition (Phases 6-8)
- 3D printer currently being repaired
- When ready: ONLY the .ino firmware file changes (real analogRead calls)
- ALL Python files work unchanged — pipeline processes all 16 channels already
- Just re-run calibration wizard with real sensors attached

---

## Completed Phases

### Phase 0 ✅ — Hardware Prototype + Firmware Baseline
What was done:
- Built rigid one-finger prototype with cardboard strip
- Found and fixed SS49E wiring bug (VCC/GND were swapped)
- Validated sensor range: 1550 ADC counts
- Documented correct sensor placement (PIP joint, not knuckle)
Key finding: Sensor reads inverted — open hand = higher ADC

### Phase 1 ✅ — Serial Communication + Packet Parser
What was done:
- ESP32 firmware upgraded to full 19-field CSV packet with frame ID + checksum
- Built complete Python serial pipeline

Test results (verified on real hardware):
- Total frames received: 1506
- Total frame drops: 0
- Checksum pass rate: 100%
- Frame rate: consistent 30 Hz

Files created (all in Project Knowledge):
- firmware/phase1_slave_esp32/phase1_slave_esp32.ino
- smart_dataset_studio/config.py
- smart_dataset_studio/communication/serial_thread.py
- smart_dataset_studio/communication/packet_parser.py
- smart_dataset_studio/communication/__init__.py
- smart_dataset_studio/processing/frame.py
- smart_dataset_studio/processing/__init__.py
- smart_dataset_studio/requirements.txt

### Phase 2 ✅ — Processing Pipeline (Filter + Normalize)
What was done:
- Built EMA filter, calibration system, and processing thread
- Tested standalone (no hardware) and on real hardware
- Normalized values confirmed: 0.0 (open) → 1.0 (closed) on real sensor
- Dummy channels correctly output 0.0 (division-by-zero protection working)
- Qt Signal pipeline working end-to-end
- Clean Ctrl+C shutdown implemented

Test results (verified):
- test_filter.py: 4/4 tests PASS
- test_calibration.py: 8/8 tests PASS
- Live hardware: R_T moves smoothly 0.00 → 1.00 as finger bends

Files created (all in Project Knowledge):
- smart_dataset_studio/processing/filter.py
- smart_dataset_studio/processing/calibration.py
- smart_dataset_studio/processing/processing_thread.py
- smart_dataset_studio/main.py (Phase 2 version — replaces Phase 1 version)
- smart_dataset_studio/test_filter.py
- smart_dataset_studio/test_calibration.py

Known cosmetic issue (NOT a bug):
- On startup, packet_parser logs "Unknown packet prefix" warnings for ~1 second
- This is ESP32 boot noise — self-corrects once valid packets start flowing
- Suppress by setting logging level to WARNING (already done in main.py)
- Do NOT investigate this in new sessions — it is expected and harmless

---

## Current Phase

### Phase 3 ⬜ — Sensor Dashboard UI
Status: NOT started. This is what the next Claude session should build.

Goal: First visual milestone — PyQt5 desktop window showing all 16 sensor
values updating live at 30 Hz. User can see the glove data without a terminal.

New folders to create:
- smart_dataset_studio/ui/
- smart_dataset_studio/visualization/

Files to build:
- ui/__init__.py
- ui/main_window.py          ← PyQt5 QMainWindow, tab layout, status bar
- ui/calibration_wizard.py   ← named profile selection + open/close hand steps
- ui/recorder_panel.py       ← placeholder only (Phase 4 fills this)
- ui/dataset_panel.py        ← placeholder only (Phase 4 fills this)
- visualization/__init__.py
- visualization/dashboard.py ← live sensor value display widget (QWidget)

Key architectural change from Phase 2:
- QCoreApplication → QApplication (required for UI windows)
- on_frame_received() → updates QLabel widgets instead of print()
- ProcessingThread.frame_ready signal connects to dashboard update method
- Calibration wizard replaces console countdown calibration

Calibration wizard UI flow:
1. App opens → check for existing calibration profiles
2. Show list of existing profiles (e.g. anoop.json, teammate1.json)
3. User selects profile OR clicks "New Profile" → enters name
4. If new: Open hand step → system records min values via countdown
5. If new: Close hand step → system records max values via countdown
6. Save → writes to data/calibration/<name>.json
7. Recalibrate button always visible on main window (for hardware module swaps)

UI Layout (target):
```
┌─────────────────────────────────────────────────┐
│  Smart Glove Dataset Studio   [Connected ✓]     │
├──────────────┬──────────────┬───────────────────┤
│ Sensor Values│   Recorder   │     Dataset       │
│              │              │                   │
│ R Thumb 0.42 │ Label: HELLO │  HELLO: 32        │
│ R Index 0.71 │              │  STOP:  28        │
│ R Middle 0.83│ [Record]     │                   │
│ R Ring  0.55 │ [Save]       │  [Export ML]      │
│ R Little 0.21│              │                   │
│              │              │                   │
│ Pitch   12.4°│              │                   │
└──────────────┴──────────────┴───────────────────┘
│ Status: 30 Hz | Port: /dev/ttyUSB0 | Profile: anoop │
```

Phase 3 completion criteria:
- App opens → calibration wizard runs → sensor values appear on screen
- Bend prototype finger → R_T value updates live (not just in terminal)
- Status bar shows frame rate ~30 Hz and connection status
- Recalibrate button works and saves new profile
- Window close or Ctrl+C exits cleanly (no crash)

---

## Upcoming Phases (Not Started)

### Phase 4 ⬜ — Gesture Recorder + Dataset Manager
Files to build: recording/gesture_recorder.py, dataset/dataset_manager.py,
ui/recorder_panel.py (fill in), ui/dataset_panel.py (fill in)
Key: capture exactly 60 frames per sample, save as CSV, discard on frame drop

### Phase 5 ⬜ — Signal Plots
Files to build: visualization/signal_plot.py
Matplotlib scrolling graphs embedded in PyQt5, showing last 90 frames (3 seconds)

### Phase 6 ⬜ — 3D Hand Skeleton [BLOCKED — needs full hardware]
Requires: 3D printed glove assembly, all 10 sensors connected
Files to build: visualization/hand_skeleton.py

### Phase 7 ⬜ — Dataset Analysis Tools [BLOCKED — needs full hardware]
Per-gesture signal overlays, outlier detection, dataset statistics

### Phase 8 ⬜ — ML Export System [BLOCKED — needs full hardware]
Files to build: dataset/ml_export.py
Exports NumPy arrays shape (N, 60, 16) for BiLSTM training

---

## Packet Format (ESP32 → Python) — DO NOT CHANGE

```
F,<frame_id>,<R_T>,<R_I>,<R_M>,<R_R>,<R_L>,<R_P>,<R_RL>,<R_Y>,
<L_T>,<L_I>,<L_M>,<L_R>,<L_L>,<L_P>,<L_RL>,<L_Y>,<checksum>\n
```

- 19 fields total (index 0-18)
- Field 0: "F" (prefix)
- Field 1: frame_id (int, 0-9999)
- Fields 2-6: R fingers (int ADC 0-4095): thumb, index, middle, ring, little
- Fields 7-9: R IMU (float, 1dp, degrees): pitch, roll, yaw
- Fields 10-14: L fingers (int ADC 0-4095)
- Fields 15-17: L IMU (float, 1dp, degrees)
- Field 18: checksum (int)

Checksum formula (must match firmware exactly):
- sum of all 10 int finger fields
- plus sum of int(each float IMU field * 10) for all 6 IMU values

Example packet:
F,0042,2134,2048,2048,2048,2048,0.0,0.0,0.0,2048,2048,2048,2048,2048,0.0,0.0,0.0,20533

---

## Key Design Decisions (Do Not Change Without Discussion)

| Decision | Value | Reason |
|----------|-------|--------|
| Baud rate | 115200 | 8x headroom over data requirement (14,400 bits/sec needed) |
| Sample rate | 30 Hz | Minimum to capture fastest finger motion (~100ms flick) |
| Window size | 60 frames | 2 seconds — captures longest common sign |
| Frame ID max | 9999 | 5.5 min before rollover, 4 chars compact in packet |
| Modulo for rollover | 10000 = (FRAME_ID_MAX + 1) | 10000 possible IDs: 0 through 9999 |
| Queue name | QUEUE_MAX_SIZE | Do NOT rename — serial_thread.py uses this exact name |
| Queue size | 100 | 3.3 seconds buffer — enough for processing jitter |
| EMA alpha | 0.25 | Noise absorbed, real movement tracked in 3-4 frames at 30 Hz |
| Frame drop policy | DISCARD sample | Corrupted 60-frame windows poison BiLSTM training |
| Padding policy | Repeat final frame | Never zero-pad — zero is not a natural sign pose |
| Calibration storage | Named user profiles (.json) | Hardware is modular — different users + module swaps |
| Calibration direction | min=open(~2900), max=closed(~1650) | Sensor is inverted — higher ADC = more open |
| Filter order | Filter THEN normalize | Filtering 0.0-1.0 causes clipping at boundaries |
| IMU treatment | Pass through raw degrees | Degrees are already universal — no normalization needed |
| Dummy channels | Output 0.0 when min==max | Safe division-by-zero — no code change when real sensors arrive |

---

## Thread Architecture (Never Break These Rules)

| Thread | Class | Role | Communicates Via |
|--------|-------|------|-----------------|
| Main Thread | — | PyQt5 UI rendering | Receives Qt Signals from Processing Thread |
| Serial Thread | threading.Thread | Reads serial port, parses packets | Pushes Frame dicts into queue.Queue |
| Processing Thread | QThread | Filters, normalizes, detects drops | Consumes queue.Queue, emits Qt Signals |

Hard rules — violating any causes race conditions or crashes:
1. serial_thread → Queue → processing_thread ONLY (never direct memory access)
2. processing_thread → Qt Signal → main thread ONLY (never direct UI access)
3. Never call QLabel.setText() or any UI method from processing_thread
4. Never share a Python list or dict between threads without a lock
5. Always call processing_thread.wait() after processing_thread.stop()
6. SerialThread uses daemon=True — dies automatically when main exits

---

## main.py Architecture (Phase 2 — Current)

The Phase 2 main.py startup sequence (critical — do not break this order):
```
1. Create QCoreApplication  ← must exist before any QThread
2. Install signal handler    ← Ctrl+C → app.quit() (not KeyboardInterrupt)
3. Start QTimer 200ms       ← lets Python check for Ctrl+C while Qt runs
4. select_port()            ← input() SAFE here, serial not started
5. decide calibration (y/n) ← input() SAFE here, serial not started
6. Start serial thread      ← NO MORE input() after this point
7. time.sleep(2.0)          ← ESP32 stabilise
8. drain_queue()            ← discard startup noise
9. run calibration or load  ← countdown timers only, no input()
10. Start processing thread ← connects signals
11. app.exec_()             ← Qt event loop runs until app.quit()
12. Stop processing thread  ← processing_thread.stop() then .wait()
13. Stop serial thread      ← serial_thread.stop() then .join(timeout=2)
```

Why countdown instead of input() during calibration:
- input() blocks the main thread
- While blocked, serial thread keeps producing frames
- Queue fills up (100 frames = 3.3 seconds)
- Queue overflows → frames dropped → "Queue full" warnings flood console
- Fix: use time.sleep(1) countdown — serial thread runs freely, no blocking

---

## Git Status

Repository: https://github.com/ANOOP222004/signgloves (Private)
Branch: main
Commits so far:
- "Phase 1 complete: serial communication + packet parser"
- "Project restructured: smart_dataset_studio, firmware, docs folders"

TODO after reading this file: Push Phase 2 commit:
```bash
cd ~/signgloves
git add .
git commit -m "Phase 2 complete: filter + normalize pipeline"
git push
```

---

## Instructions for New Claude Sessions

READ THESE BEFORE WRITING ANY CODE:

1. Read this file completely
2. Read all Python files in Project Knowledge (config.py, frame.py, etc.)
   — these are the ACTUAL code, not summaries
3. Read SmartGlove_ProjectDocumentation_Updated.docx
4. Read SmartGlove_Phase2_Documentation.docx
5. Ask Anoop to confirm current phase before starting work
6. Check the exact import names in config.py before writing any imports
   — use QUEUE_MAX_SIZE not QUEUE_SIZE
   — use CALIBRATION_DIR not CALIBRATION_PATH (both exist, use DIR)
7. Check frame.py for exact dict key names before accessing frame data
   — keys are: 'thumb', 'index', 'middle', 'ring', 'little', 'pitch', 'roll', 'yaw'
   — NOT 'r_thumb', NOT 'fingers[0]', NOT any other format
8. Never use magic numbers — all constants in config.py only
9. Never share mutable state between threads
10. Always explain reasoning behind every decision — Anoop wants to learn
11. Use analogies first, then technical detail — he responds well to this
12. Be direct and honest — if something is wrong, say so clearly
13. After phase completes: remind Anoop to update this file and push to GitHub
14. Run Python as: python3 (not python)
15. Venv activates automatically when cd into ~/signgloves
16. Phase 1 firmware is already flashed — do not reflash unless asked
17. The "Unknown packet prefix" warning on startup is NORMAL — do not fix it
18. Phase 3 starts with QApplication (not QCoreApplication) — UI needs this

---

## Suggestions for Anoop (From Current Session)

These are things worth doing to keep the project healthy:

1. PUSH PHASE 2 TO GITHUB NOW before starting Phase 3
   ```bash
   cd ~/signgloves
   git add .
   git commit -m "Phase 2 complete: filter + normalize pipeline"
   git push
   ```

2. UPDATE PROJECT KNOWLEDGE after every phase
   - Replace CURRENT_STATUS.md with the new version
   - Add new phase documentation .docx
   - Upload new Python files created in that phase

3. PLANNED GESTURE VOCABULARY (10 signs decided this session):
   HELLO, STOP, YES, NO, THANKYOU, SORRY, HELP, WATER, PLEASE, MORE
   These 10 are maximally distinguishable — different finger patterns AND
   different wrist orientations (IMU). Good starting vocabulary.

4. SENTENCE CONSTRUCTION APPROACH decided:
   ML model → recognizes individual signs → outputs label
   Rule-based engine → combines labels into sentences → outputs text/speech
   This is the correct approach for a 10-sign vocabulary.

5. WHEN FULL GLOVE ARRIVES — only two things change:
   - Flash updated .ino firmware with real analogRead() calls per finger
   - Re-run calibration wizard to record real min/max per finger
   - Zero Python file changes needed

6. REGENERATE TOKEN: The GitHub Personal Access Token was visible in a
   screenshot during this session. Generate a new token and delete the old one.
   GitHub → Settings → Developer settings → Personal access tokens
