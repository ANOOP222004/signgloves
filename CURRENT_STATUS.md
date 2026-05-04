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
#   9.  SmartGlove_Phase7_Documentation.docx             ← Phase 7 deep detail
#   10. SmartGlove_Phase8_Documentation.docx             ← Phase 8 deep detail (NEW)
#   11. config.py                                        ← ALL constants
#   12. main.py                                          ← entry point
#   13. serial_thread.py                                 ← serial communication
#   14. packet_parser.py                                 ← packet validation
#   15. frame.py                                         ← data structures
#   16. filter.py                                        ← EMA filter
#   17. calibration.py                                   ← normalization + profiles
#   18. processing_thread.py                             ← pipeline thread
#   19. main_window.py                                   ← tabbed UI + session stats
#   20. calibration_tab.py                               ← inline calibration tab
#   21. style.py                                         ← dark theme
#   22. recorder_panel.py                                ← Record tab with speed selector
#   23. dataset_panel.py                                 ← per-label counts
#   24. gesture_recorder.py                              ← 60-frame capture state machine
#   25. dataset_manager.py                               ← profile-based npy save/load
#   26. dataset_analyzer.py                              ← Phase 7: analysis engine
#   27. analysis_tab.py                                  ← Phase 7: Dataset tab UI
#   28. ml_export.py                                     ← NEW Phase 8: ML export worker
#   29. export_tab.py                                    ← NEW Phase 8: Export tab UI
#   30. voice_listener.py                                ← Vosk + sounddevice QThread
#   31. signal_plot.py                                   ← PyQtGraph scrolling graphs
#   32. hand_skeleton.py                                 ← 3D hand renderer (timer-decoupled)
#
# Last updated: Phase 8 Complete — May 2026
# ============================================================

## Project Summary
Building an AI Sign-to-Speech Smart Glove system. Two gloves with Hall sensors
and IMU capture hand gestures. A BiLSTM ML model recognizes gestures and
converts them to text/speech. The system runs fully on embedded hardware (Edge AI).

The Smart Glove Dataset Studio (Python desktop app) is now FEATURE COMPLETE.
All 8 phases of the studio are done. Next step: dataset collection then Phase 9 training.

## Team & Environment
- Developer: Anoop B A (+ teammate)
- OS: Ubuntu 22.04 (Anoop) + Windows (some teammates)
- Python: python3 (never 'python')
- Python venv: ~/signgloves/venv/
- Project folder: ~/signgloves/smart_dataset_studio/
- GitHub repo: https://github.com/ANOOP222004/signgloves (Private)
- Master ESP32-S3 port: /dev/ttyACM0 (USB Single Serial) ← verified
- Slave ESP32 port: /dev/ttyUSB0 (CP2102) ← never connect Python to this

## Hardware Status (Phase 8 Complete)

### Left Hand Glove — Slave (ESP32 DevKit V1)
- Hall sensors: GPIO 32=Thumb, 33=Index, 34=Middle, 35=Ring, 36=Little (GPIO 36 not 25)
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

## Folder Structure (Complete — After Phase 8)

```
~/signgloves/
├── smart_dataset_studio/
│   ├── main.py                        ← Phase 8: voice tab switching wired
│   ├── config.py                      ← Phase 8: EXPORT_PATH, EXPORT_RATIOS, VOICE_TAB_COMMANDS
│   ├── requirements.txt
│   ├── serial_diagnostic.py           ← Phase 7: standalone port measurement tool
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py             ← Phase 8: SESSION_STATS, on_voice_command, maximize fix
│   │   ├── style.py
│   │   ├── calibration_tab.py
│   │   ├── calibration_wizard.py
│   │   ├── recorder_panel.py          ← Phase 7: speed selector (SLOW/MEDIUM/FAST)
│   │   ├── dataset_panel.py
│   │   ├── analysis_tab.py            ← Phase 7: Dataset tab + Phase 8: taller plot
│   │   └── export_tab.py              ← NEW Phase 8: full Export tab UI
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
│   │   ├── dataset_manager.py
│   │   ├── dataset_analyzer.py        ← Phase 7: analysis engine
│   │   └── ml_export.py               ← NEW Phase 8: MLExportWorker(QThread)
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
│   ├── SmartGlove_Phase7_Documentation.docx
│   └── SmartGlove_Phase8_Documentation.docx  ← NEW
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
│   └── <profile_name>/
│       ├── HELLO/
│       │   └── HELLO_medium_001.npy
│       └── STOP/
│           └── STOP_fast_001.npy
├── exports/                           ← NEW Phase 8
│   ├── X_train.npy                    ← shape (N_train, 60, 16)
│   ├── X_val.npy                      ← shape (N_val, 60, 16)
│   ├── X_test.npy                     ← shape (N_test, 60, 16)
│   ├── y_train.npy                    ← shape (N_train,)
│   ├── y_val.npy                      ← shape (N_val,)
│   ├── y_test.npy                     ← shape (N_test,)
│   ├── label_map.json                 ← {"HELLO":0, "STOP":1, ...}
│   ├── dataset_flat.csv               ← one row per sample
│   └── export_report.txt              ← human-readable summary
└── skeleton_tuning.json
```

## Feature Vector (UNCHANGED since Phase 2)
```
Position  Feature   Type              Range
1-5       R_T..R_L  Float normalized  0.0 (open) to 1.0 (bent) — right fingers
6-8       R_P,R_RL,R_Y  Float degrees -180 to 180 — right wrist IMU
9-13      L_T..L_L  Float normalized  0.0 to 1.0 — left fingers
14-16     L_P,L_RL,L_Y  Float degrees -180 to 180 — left wrist IMU
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
1. CRITICAL: Checksum gate rejected 70% of valid packets — float rounding mismatch.
   Fix: removed verify_checksum() call. Never add it back.
2. CRITICAL: hand_skeleton.py rebuilt 40 OpenGL meshes every frame at 30 Hz → 5 Hz.
   Fix: on_frame() only stores values; 25 Hz QTimer drives _update_skeleton().
3. os.environ.setdefault() skipped if variable existed. Fix: os.environ[] hard assignment.
4. Auto port detection selected slave. Fix: updated MASTER_PORT_KEYWORDS.
5. Maximize button made window disappear on GNOME xcb_egl.
   Fix: changeEvent override converts WindowFullScreen to showMaximized().

### Phase 8
1. Window maximize button hidden on Ubuntu 22.04 GNOME (1366x768 screen).
   Root cause: setMinimumSize(1000, 720) too close to work area (1290x741).
   GNOME mutter hides maximize when min size ≈ work area size.
   Fix: setMinimumSize(800, 600) + resize(1200, 720).
   Rule: setMinimumSize width <= 900, height <= 650 for 1366x768 screens.
2. Export tab cut off — bottom section not visible.
   Fix: wrap entire ExportTab content in QScrollArea(widgetResizable=True).

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
| Outlier threshold | Z-score > 2.5 | Catches clearly abnormal without over-flagging |
| Port — master | /dev/ttyACM0 (USB Single Serial) | ESP32-S3 built-in USB-CDC |
| Port — slave | /dev/ttyUSB0 (CP2102) | Never connect Python to slave |
| OpenGL env | os.environ[] not setdefault() | Hard assignment always overwrites |
| Export labels | GESTURE_LABELS index order | NEVER reorder GESTURE_LABELS after collecting data |
| Export split | Stratified 80/10/10 seed=42 | Proportional per label, reproducible |
| Voice tabs | Extend VOICE_COMMANDS list | Same VoiceListener, no architecture change |
| Min window size | 800x600 max | GNOME mutter hides maximize if min ≈ work area |

## Phase Status

### Phase 0 ✅ COMPLETE — Hardware Prototype + Firmware Baseline
### Phase 1 ✅ COMPLETE — Serial Communication + Packet Parser
### Phase 2 ✅ COMPLETE — Processing Pipeline (Filter + Normalize)
### Phase 3 ✅ COMPLETE — Sensor Dashboard UI
### Phase 4 ✅ COMPLETE — Gesture Recorder + Dataset Manager + Voice
### Phase 5 ✅ COMPLETE — Signal Plots + Tabbed UI + Calibration Tab + Dark Theme
### Phase 6 ✅ COMPLETE — Dual Glove ESP-NOW + 3D Hand Skeleton
### Phase 7 ✅ COMPLETE — Dataset Analysis Tools + Pipeline Debugging

---

### Phase 8 ✅ COMPLETE — ML Export System

What was built:
- dataset/ml_export.py — MLExportWorker(QThread)
  - Scans data/dataset/<profile>/<LABEL>/ for all .npy and legacy .csv files
  - Loads each sample as (60, 16) numpy array
  - Stacks into X shape (N, 60, 16), y shape (N,)
  - Stratified 80/10/10 split (seed=42) → X_train/val/test, y_train/val/test
  - Saves label_map.json, dataset_flat.csv, export_report.txt
  - Emits progress_updated, log_message, export_complete, export_failed
  - Skips malformed files gracefully — never crashes

- ui/export_tab.py — ExportTab(QWidget)
  - Section 1: Dataset summary (all profiles, per-gesture counts, color coded)
  - Section 2: Export config (output dir, profile checkboxes, split toggle)
  - Section 3: Export button + progress bar + color-coded scrolling log
  - Section 4: Results table (shown after export)
  - Full QScrollArea wrapping — scrollable on small screens

- config.py additions:
  EXPORT_PATH, EXPORT_TRAIN_RATIO, EXPORT_VAL_RATIO, EXPORT_TEST_RATIO
  VOICE_TAB_COMMANDS, extended VOICE_COMMANDS

- ui/main_window.py changes:
  - ExportTab wired in place of stub
  - SESSION_STATS panel on Dashboard (uptime, frames, drops, dataset total, last gesture)
  - on_voice_command() slot — voice tab switching
  - setMinimumSize(800, 600) — maximize fix

Additional UI improvements:
- Voice tab switching: say "dashboard/record/visualize/calibration/dataset/export"
- Dataset overlay plot taller (40% of tab height)
- Window maximize fixed on Ubuntu GNOME 1366x768

Verified export output:
- X_train shape: (17, 60, 16) ✅
- y_train shape: (17,) ✅
- y values: {0, 3, 8} = HELLO, NO, PLEASE ✅
- label_map: HELLO→0 ... MORE→9 ✅

Git commit: "Phase 8 complete: ML export system + session stats + voice tab switching"

---

### Phase 9 ⬜ NEXT — BiLSTM Training Pipeline
BLOCKED on: dataset collection

Before starting Phase 9:
1. Fix magnet mounts (currently unstable — noisy recordings)
2. Recalibrate (target: 200-500+ ADC range per finger)
3. Record 50+ samples per gesture × 10 signs = 500+ total
4. Use Dataset tab to delete outliers
5. Click Export → verify X_train shape is (N, 60, 16) with N >= 400

What Phase 9 will build (standalone PC script, not part of the app):
- train_bilstm.py
- BiLSTM model: Input(60,16) → Bidirectional LSTM(64) → Dense(32,relu) → Dense(10,softmax)
- Training with early stopping, LR scheduling, class weights
- Confusion matrix and per-gesture accuracy report
- TFLite conversion + INT8 quantization
- Model size check (must fit ESP32-S3 N16R8 16MB flash)
Target: 95%+ accuracy on all 10 ISL signs

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
19. Left hand IMU fields: slave HAS IMU (added Phase 6)
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
31. NEVER reorder GESTURE_LABELS — breaks label mapping in existing exports
32. Export output always in data/exports/ — delete contents before re-exporting
33. setMinimumSize max 800x600 — larger values hide maximize on GNOME 1366x768
34. Voice VOICE_COMMANDS list must include tab names for voice tab switching
