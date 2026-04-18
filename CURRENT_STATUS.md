# Smart Glove Project — Current Status
# ============================================================
# CRITICAL: Read this file FIRST in every new Claude session.
#
# FILES IN PROJECT KNOWLEDGE (read all of them):
#   1.  CURRENT_STATUS.md                                ← this file
#   2.  SmartGlove_ProjectDocumentation_Updated.docx     ← full project overview
#   3.  SmartGlove_Phase1_Documentation.docx             ← Phase 1 deep detail
#   4.  SmartGlove_Phase2_Documentation.docx             ← Phase 2 deep detail
#   5.  SmartGlove_Phase3_Documentation.docx             ← Phase 3 deep detail
#   6.  SmartGlove_Phase4_Documentation.docx             ← Phase 4 deep detail
#   7.  SmartGlove_Phase5_Documentation.docx             ← Phase 5 deep detail
#   8.  SmartGlove_Phase6_Documentation.docx             ← Phase 6 deep detail
#   9.  SmartGlove_Phase7_Documentation.docx             ← Phase 7 deep detail (NEW)
#   10. config.py                                        ← ALL constants
#   11. main.py                                          ← entry point
#   12. serial_thread.py                                 ← serial communication
#   13. packet_parser.py                                 ← packet validation
#   14. frame.py                                         ← data structures
#   15. filter.py                                        ← EMA filter
#   16. calibration.py                                   ← normalization + profiles
#   17. processing_thread.py                             ← pipeline thread
#   18. main_window.py                                   ← tabbed UI
#   19. calibration_tab.py                               ← inline calibration tab
#   20. style.py                                         ← dark theme
#   21. recorder_panel.py                                ← Record tab with speed selector
#   22. dataset_panel.py                                 ← per-label counts
#   23. gesture_recorder.py                              ← 60-frame capture state machine
#   24. dataset_manager.py                               ← profile-based npy save/load
#   25. dataset_analyzer.py                              ← NEW Phase 7: analysis engine
#   26. analysis_tab.py                                  ← NEW Phase 7: Dataset tab UI
#   27. voice_listener.py                                ← Vosk + sounddevice QThread
#   28. signal_plot.py                                   ← PyQtGraph scrolling graphs
#   29. hand_skeleton.py                                 ← 3D hand renderer (timer-decoupled)
#
# Last updated: Phase 7 Complete — April 2026
# ============================================================

## Project Summary
Building an AI Sign-to-Speech Smart Glove system. Two gloves with Hall sensors
and IMU capture hand gestures. A BiLSTM ML model recognizes gestures and
converts them to text/speech. The system runs fully on embedded hardware (Edge AI).

The current software effort is the Smart Glove Dataset Studio — a Python desktop
application for recording, managing, and exporting a labeled gesture dataset.

## Team & Environment
- Developer: Anoop B A (+ teammate)
- OS: Ubuntu 22.04 (Anoop) + Windows (some teammates)
- Python: python3 (never 'python')
- Python venv: ~/signgloves/venv/
- Project folder: ~/signgloves/smart_dataset_studio/
- GitHub repo: https://github.com/ANOOP222004/signgloves (Private)
- Master ESP32-S3 port: /dev/ttyACM0 (USB Single Serial) ← verified
- Slave ESP32 port: /dev/ttyUSB0 (CP2102) ← never connect Python to this

## Hardware Status (Phase 7 Complete)

### Left Hand Glove — Slave (ESP32 DevKit V1)
- Hall sensors: GPIO 32=Thumb, 33=Index, 34=Middle, 35=Ring, 25=Little
- IMU MPU6050: SDA=GPIO21, SCL=GPIO22, AD0=GND (address 0x68)
- Communicates via ESP-NOW to master
- Firmware: firmware/slave_esp32/slave_esp32.ino (FLASHED ✅)
- NOTE: Magnet mounts are currently unstable — fix before recording dataset

### Right Hand Glove — Master (ESP32-S3 N16R8)
- Hall sensors: GPIO 1=Thumb, 2=Index, 3=Middle, 4=Ring, 5=Little (ADC1 only)
- IMU MPU6050: SDA=GPIO8, SCL=GPIO9, AD0=GND (address 0x68)
- 4.7kΩ pull-up resistors on SDA and SCL to 3V3
- Communicates via USB Serial (UART port = right USB-C) to PC at /dev/ttyACM0
- Firmware: firmware/master_esp32s3/master_esp32s3.ino (FLASHED ✅)
- Board: ESP32-S3 N16R8 (16MB flash, 8MB PSRAM)

### Hardware Incidents
- Original ESP32 DevKit (slave) burned — reversed SS49E sensor (VCC/GND swapped)
- Original ESP32-S3 (master) burned — same root cause
- LESSON: Always check 3V3→GND resistance (must be >10kΩ) before powering
- New ESP32-S3 N16R8 purchased — 16MB flash, 8MB PSRAM (better than original N8R2)

### Wiring Safety Rule
BEFORE powering: multimeter resistance mode, 3V3 rail to GND rail.
Must read > 10kΩ. If < 500Ω → short circuit → chip will burn.

## Folder Structure (Complete — After Phase 7)

```
~/signgloves/
├── smart_dataset_studio/
│   ├── main.py                        ← Phase 7: force env vars, corrected port detection
│   ├── config.py                      ← Phase 7: SLOW/MEDIUM/FAST_ZONES, SPEED_TAGS added
│   ├── requirements.txt
│   ├── serial_diagnostic.py           ← Phase 7: standalone port measurement tool
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py             ← Phase 7: changeEvent maximize fix added
│   │   ├── style.py
│   │   ├── calibration_tab.py
│   │   ├── calibration_wizard.py      ← fallback only
│   │   ├── recorder_panel.py          ← Phase 7: speed selector (SLOW/MEDIUM/FAST) added
│   │   ├── dataset_panel.py
│   │   └── analysis_tab.py            ← NEW Phase 7: complete Dataset tab UI
│   │
│   ├── visualization/
│   │   ├── __init__.py
│   │   ├── signal_plot.py
│   │   └── hand_skeleton.py           ← Phase 7: fixed GL mesh rebuild bug
│   │
│   ├── recording/
│   │   ├── __init__.py
│   │   └── gesture_recorder.py
│   │
│   ├── dataset/
│   │   ├── __init__.py
│   │   ├── dataset_manager.py         ← Phase 7: profile-based paths, speed tags, npy format
│   │   └── dataset_analyzer.py        ← NEW Phase 7: analysis engine
│   │
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── voice_listener.py
│   │   └── vosk-model-small-en-us-0.15/  ← in .gitignore
│   │
│   ├── communication/
│   │   ├── __init__.py
│   │   ├── serial_thread.py           ← Phase 7: chunk read with in_waiting
│   │   └── packet_parser.py           ← Phase 7: checksum gate REMOVED
│   │
│   └── processing/
│       ├── __init__.py
│       ├── frame.py
│       ├── filter.py
│       ├── calibration.py
│       └── processing_thread.py
│
├── firmware/
│   ├── master_esp32s3/
│   │   └── master_esp32s3.ino
│   └── slave_esp32/
│       └── slave_esp32.ino
│
├── docs/
│   ├── SmartGlove_ProjectDocumentation_Updated.docx
│   ├── SmartGlove_Phase1_Documentation.docx
│   ├── SmartGlove_Phase2_Documentation.docx
│   ├── SmartGlove_Phase3_Documentation.docx
│   ├── SmartGlove_Phase4_Documentation.docx
│   ├── SmartGlove_Phase5_Documentation.docx
│   ├── SmartGlove_Phase6_Documentation.docx
│   └── SmartGlove_Phase7_Documentation.docx  ← NEW
│
├── CLAUDE.md                          ← Claude Code project context
├── venv/
├── .gitignore
└── CURRENT_STATUS.md                  ← this file
```

data/ folder (git-ignored, created at runtime):
```
smart_dataset_studio/data/
├── calibration/
│   └── <profile_name>/
│       └── calibration_YYYYMMDD.json
├── dataset/
│   └── <profile_name>/              ← NEW Phase 7: profile-based structure
│       ├── HELLO/
│       │   └── HELLO_medium_001.npy
│       └── STOP/
│           └── STOP_fast_001.npy
└── skeleton_tuning.json
```

## config.py Constants (Complete — After Phase 7)

```python
BAUD_RATE        = 115200
QUEUE_MAX_SIZE   = 100          # NOT QUEUE_SIZE
SAMPLE_RATE      = 30
WINDOW_SIZE      = 60
FRAME_PERIOD_MS  = 33
EMA_ALPHA        = 0.25
FRAME_ID_MAX     = 9999         # max VALUE — modulo = FRAME_ID_MAX + 1 = 10000
DATASET_PATH     = "data/dataset/"
CALIBRATION_PATH = "data/calibration/"
NUM_FEATURES     = 16
TARGET_SAMPLES   = 50           # NEW Phase 7: green threshold in balance chart
OUTLIER_Z_THRESHOLD = 2.5       # NEW Phase 7: z-score threshold for outlier detection
DEFAULT_SPEED    = "medium"     # NEW Phase 7
SPEED_TAGS       = ["slow", "medium", "fast"]  # NEW Phase 7
SLOW_ZONES   = {'start': (0, 10),  'transition': (10, 50), 'end': (50, 60)}  # NEW
MEDIUM_ZONES = {'start': (0, 8),   'transition': (8,  45), 'end': (45, 60)}  # NEW
FAST_ZONES   = {'start': (0, 5),   'transition': (5,  30), 'end': (30, 60)}  # NEW
FEATURE_ORDER = ["R_T","R_I","R_M","R_R","R_L","R_P","R_RL","R_Y",
                 "L_T","L_I","L_M","L_R","L_L","L_P","L_RL","L_Y"]
FINGER_CHANNELS = ["thumb","index","middle","ring","little"]
IMU_CHANNELS    = ["pitch","roll","yaw"]
GESTURE_LABELS  = ['HELLO','STOP','YES','NO','THANKYOU',
                   'SORRY','HELP','WATER','PLEASE','MORE']
```

## Packet Format (UNCHANGED since Phase 1)
```
F,<frame_id>,<R_T>,<R_I>,<R_M>,<R_R>,<R_L>,<R_P>,<R_RL>,<R_Y>,
<L_T>,<L_I>,<L_M>,<L_R>,<L_L>,<L_P>,<L_RL>,<L_Y>,<checksum>\n
19 fields total.
```
IMPORTANT: Python does NOT verify the checksum (removed in Phase 7 — float
rounding mismatch between firmware and Python caused 70% packet loss).
Field count (19) + "F," prefix is sufficient validation for USB-CDC.

## Known Bugs Fixed

### Phase 3
1. TypeError on wizard: catch (RuntimeError, TypeError)
2. Profile name hidden on first run: check currentText() at construction

### Phase 4
1. Recorder stuck in COMPLETE: add recorder.discard() in _on_save_clicked()

### Phase 5
1. 'No Profile' on capture: auto-set _profile_name in dropdown refresh
2. Record button disabled after auto-load: QTimer.singleShot(0) deferred emit

### Phase 6
1. Black 3D viewport on Ubuntu: os.environ xcb_egl fix at top of main.py
2. Skeleton invisible on startup: QTimer.singleShot(500) delays GL item creation
3. Left/right hand mirroring wrong: fixed x_off and mirror signs in _compute_hand()
4. ESP-NOW callback signature error: use esp_now_recv_info_t* for new core version
5. Slave MAC shows 00:00:00:00:00:00: use esp_read_mac() instead of WiFi.macAddress()
6. Original chips burned: reversed SS49E sensor — VCC/GND swapped

### Phase 7
1. CRITICAL: Checksum gate rejected 70% of valid packets — float rounding mismatch
   between firmware (uses full internal float) and Python (uses rounded string).
   Fix: removed verify_checksum() call from parse_packet(). Never add it back.
2. CRITICAL: hand_skeleton.py rebuilt 40 OpenGL meshes every frame at 30 Hz,
   blocking Qt main thread ~200ms/call → 5 Hz apparent rate.
   Fix: on_frame() only stores values; 25 Hz QTimer drives _update_skeleton().
   Sphere meshes pre-computed once; per-frame uses vectorized numpy.
3. os.environ.setdefault() skipped if variable already existed in environment.
   Fix: changed to os.environ[] (hard assignment, always overwrites).
4. Auto port detection selected slave (CP2102/ttyUSB0) instead of master
   (USB Single Serial/ttyACM0). Fix: updated MASTER_PORT_KEYWORDS.
5. Maximize button made window disappear on Ubuntu GNOME + xcb_egl.
   Root cause: GNOME sends WindowFullScreen (not WindowMaximized); xcb_egl
   makes fullscreen invisible. Fix: changeEvent override converts to showMaximized().

## Key Design Decisions (All Phases)

| Decision | Value | Reason |
|----------|-------|--------|
| QUEUE_MAX_SIZE | 100 | Do NOT rename to QUEUE_SIZE |
| Frame drop policy | DISCARD entire sample | Corrupted windows poison BiLSTM |
| Padding policy | Repeat final frame | Never zero-pad (0.0 = open hand = real state) |
| Filter order | Filter THEN normalize | Filtering 0-1 causes clipping artifacts |
| IMU treatment | Pass through raw degrees | Already universal, not mixed with bend values |
| Qt class | QApplication | Required for any window |
| Signal connection | Before start() | Prevents race condition |
| Checksum | REMOVED from parser | Float rounding mismatch — never add back |
| Skeleton update | 25 Hz QTimer only | Never connect _update_skeleton to frame_ready |
| Dataset path | data/dataset/<profile>/ | Profile-based — never flat data/dataset/ |
| Dataset format | .npy not .csv | Phase 7: changed to numpy binary |
| Speed tag | Embedded in filename | LABEL_SPEED_NNN.npy |
| Combined line | Mean of 10 finger channels | IMU in degrees — cannot average with 0-1 bend |
| Outlier threshold | Z-score > 2.5 | Catches clearly abnormal without over-flagging |
| Port — master | /dev/ttyACM0 (USB Single Serial) | ESP32-S3 built-in USB-CDC |
| Port — slave | /dev/ttyUSB0 (CP2102) | Never connect Python to slave |
| OpenGL env | os.environ[] not setdefault() | Hard assignment always overwrites |

## Phase Status

### Phase 0 ✅ COMPLETE — Hardware Prototype + Firmware Baseline
### Phase 1 ✅ COMPLETE — Serial Communication + Packet Parser
### Phase 2 ✅ COMPLETE — Processing Pipeline (Filter + Normalize)
### Phase 3 ✅ COMPLETE — Sensor Dashboard UI
### Phase 4 ✅ COMPLETE — Gesture Recorder + Dataset Manager + Voice
### Phase 5 ✅ COMPLETE — Signal Plots + Tabbed UI + Calibration Tab + Dark Theme
### Phase 6 ✅ COMPLETE — Dual Glove ESP-NOW + 3D Hand Skeleton

---

### Phase 7 ✅ COMPLETE — Dataset Analysis Tools + Pipeline Debugging

Hardware: Both gloves working. Frame rate: 30 Hz (verified).

Part A — Pipeline Debugging:
- Identified and fixed two critical bugs causing 4-10 Hz frame rate
- Bug 1: packet_parser.py checksum rejecting 70% of valid packets
- Bug 2: hand_skeleton.py blocking Qt main thread 200ms/frame
- Used standalone serial_diagnostic.py to prove firmware was perfect
  and isolate the problem to the Python pipeline
- Result: 30.2 Hz measured, zero frame drops during recording

Part B — Dataset Analysis Tools:
- dataset/dataset_analyzer.py — analysis engine (outliers, stats, overlay)
- ui/analysis_tab.py — complete Dataset tab (was stub in Phase 6)
- Speed tagging: SLOW/MEDIUM/FAST selector in Record tab
- Frame zone constants in config.py for each speed
- Profile-based dataset storage: data/dataset/<profile_name>/
- Combined hand overlay: mean of 10 finger channels per sample
- Vertical zone boundary lines in overlay for selected speed
- Outlier detection with DELETE button
- Feature statistics with std dev color coding

Additional fixes:
- Corrected port auto-detection (master=ttyACM0, slave=ttyUSB0)
- Fixed OpenGL env var (setdefault→hard assignment)
- Fixed maximize button on Ubuntu GNOME + xcb_egl
- serial_thread.py: chunk reading with in_waiting

Completion criteria: ALL PASSED.
Git commit: "Phase 7 complete: dataset analysis tools + 30Hz pipeline fix"

---

### Phase 8 ⬜ NEXT — ML Export System
Hardware required: Both gloves working ✅
Status: BLOCKED on dataset collection

Before starting Phase 8:
1. Fix magnet mounts (currently unstable — causes noisy recordings)
2. Recalibrate with full range (target: finger ranges 200-500+ ADC units)
3. Record 50+ samples per gesture, all 10 ISL signs
4. Use Dataset tab to verify quality and delete outliers
5. All gesture bars should be green (50+) in sample count list

What Phase 8 will build:
- dataset/ml_export.py
- Export: X.npy (N,60,16), y.npy (N,), label_map.json, dataset_flat.csv
- Fills the EXPORT tab (currently a stub)

After Phase 8:
- Train BiLSTM on PC with TensorFlow/Keras
- Convert to TFLite INT8
- Flash to ESP32-S3 N16R8
- Target: 95%+ accuracy on 10-sign ISL vocabulary

## Instructions for New Claude/Claude Code Sessions

1.  Read this file completely — especially phase status and key decisions
2.  Read CLAUDE.md for Claude Code sessions
3.  Confirm current phase with Anoop before starting any work
4.  Check config.py for exact constant names before any imports
5.  Check frame.py for exact dict key names before accessing frame data
6.  Never use magic numbers — all constants in config.py only
7.  Never share mutable state between threads
8.  Connect signals BEFORE QThread.start()
9.  Use QApplication not QCoreApplication
10. apply_style(app) BEFORE any widget is created
11. os.environ[] OpenGL fix BEFORE all imports in main.py — never remove, never setdefault
12. After save: always call recorder.discard() to reset state machine
13. Profile-tagged filenames: LABEL_SPEED_NNN.npy
14. CalibrationTab emits calibration_updated via QTimer.singleShot(0)
15. raw_frame_ready = raw ADC; frame_ready = processed 0.0-1.0
16. update_calibration() is GIL-safe
17. HandSkeletonWidget._gl_ready must be True before any GL update
18. ESP32-S3 ADC: use GPIO 1-5 (ADC1 only) — ADC2 conflicts with ESP-NOW
19. Left hand IMU fields: slave HAS IMU now (added Phase 6)
20. Master uses UART port (right USB-C on DevKitC-1) = /dev/ttyACM0
21. Slave MAC: use esp_read_mac() not WiFi.macAddress()
22. Check 3V3→GND resistance (>10kΩ) before powering any new hardware
23. Explain reasoning — Anoop wants to learn, not just copy-paste
24. python3 not python
25. "Unknown packet prefix" on startup = NORMAL boot noise, do not fix
26. NEVER verify checksum in packet_parser.py — float rounding mismatch
27. NEVER connect _update_skeleton() directly to frame_ready signal
28. NEVER run python3 main.py from Claude Code — always run in separate terminal
29. Dataset path always data/dataset/<profile_name>/ — never flat
30. Master port = /dev/ttyACM0 (USB Single Serial), slave = /dev/ttyUSB0 (CP2102)
