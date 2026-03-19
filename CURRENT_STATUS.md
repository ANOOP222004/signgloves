# Smart Glove Project — Current Status
# ============================================================
# CRITICAL: Read this file FIRST in every new Claude session.
#
# FILES UPLOADED TO PROJECT KNOWLEDGE (read all of them):
#   1. CURRENT_STATUS.md                                ← this file
#   2. SmartGlove_ProjectDocumentation_Updated.docx     ← full project overview
#   3. SmartGlove_Phase2_Documentation.docx             ← Phase 2 deep technical detail
#   4. SmartGlove_Phase3_Documentation.docx             ← Phase 3 deep technical detail
#   5. config.py                                        ← ALL constants
#   6. main.py                                          ← Phase 3 entry point (current)
#   7. serial_thread.py                                 ← serial communication
#   8. packet_parser.py                                 ← packet validation
#   9. frame.py                                         ← data structures
#   10. filter.py                                       ← EMA filter
#   11. calibration.py                                  ← normalization + profiles
#   12. processing_thread.py                            ← pipeline thread
#   13. main_window.py                                  ← Phase 3 main window
#   14. calibration_wizard.py                           ← Phase 3 calibration dialog
#
# Last updated: Phase 3 Complete
# ============================================================

## Project Summary
Building an AI Sign-to-Speech Smart Glove system. Two gloves with Hall sensors
and IMU capture hand gestures. A BiLSTM ML model recognizes gestures and
converts them to text/speech. The system runs fully on embedded hardware (Edge AI).

The current software effort is the Smart Glove Dataset Studio — a Python desktop
application for recording, managing, and exporting a labeled gesture dataset.

## Team & Environment
- Developer: Anoop (+ teammate)
- OS: Ubuntu 22.04
- Python: python3 (never 'python')
- Python venv: ~/signgloves/venv/ (auto-activates when cd into ~/signgloves)
- Project folder: ~/signgloves/
- GitHub repo: https://github.com/ANOOP222004/signgloves (Private)
- ESP32 port: /dev/ttyUSB0 (appears as option 32 in port list)

## Folder Structure (Exact)

```
~/signgloves/
├── smart_dataset_studio/
│   ├── main.py                    ← Phase 3 entry point (current)
│   ├── config.py                  ← ALL constants
│   ├── requirements.txt
│   ├── test_filter.py             ← Phase 2 test (PASSING)
│   ├── test_calibration.py        ← Phase 2 test (PASSING)
│   ├── ui/                        ← NEW in Phase 3
│   │   ├── __init__.py
│   │   ├── main_window.py         ← MainWindow(QMainWindow)
│   │   └── calibration_wizard.py  ← CalibrationWizard(QDialog)
│   ├── communication/
│   │   ├── __init__.py
│   │   ├── serial_thread.py
│   │   └── packet_parser.py
│   └── processing/
│       ├── __init__.py
│       ├── frame.py
│       ├── filter.py
│       ├── calibration.py         ← updated Phase 3: profile support
│       └── processing_thread.py
├── firmware/
│   └── phase1_slave_esp32/
│       └── phase1_slave_esp32.ino ← CURRENTLY FLASHED, do not reflash
├── docs/
│   ├── SmartGlove_ProjectDocumentation_Updated.docx
│   ├── SmartGlove_Phase1_Documentation.docx
│   ├── SmartGlove_Phase2_Documentation.docx
│   └── SmartGlove_Phase3_Documentation.docx
├── venv/
├── .gitignore
└── CURRENT_STATUS.md
```

NOTE: recording/ and dataset/ module folders do NOT exist yet — Phase 4 creates them.
NOTE: visualization/ folder does NOT exist yet — Phase 5/6 creates it.

data/ folder (git-ignored, created at runtime):
```
smart_dataset_studio/data/
├── calibration/
│   ├── anoop/
│   │   └── calibration_YYYYMMDD.json
│   └── <teammate>/
│       └── calibration_YYYYMMDD.json
└── dataset/   ← Phase 4, not yet created
```

## config.py Constants (Exact)

```python
BAUD_RATE       = 115200
QUEUE_MAX_SIZE  = 100          # NOT QUEUE_SIZE
SAMPLE_RATE     = 30
WINDOW_SIZE     = 60
FRAME_PERIOD_MS = 33
EMA_ALPHA       = 0.25
FRAME_ID_MAX    = 9999         # max VALUE, NOT modulo
                               # modulo = FRAME_ID_MAX + 1 = 10000
DATASET_PATH     = "data/dataset/"
CALIBRATION_PATH = "data/calibration/"
NUM_FEATURES = 16
FEATURE_ORDER = ["R_T","R_I","R_M","R_R","R_L","R_P","R_RL","R_Y",
                 "L_T","L_I","L_M","L_R","L_L","L_P","L_RL","L_Y"]
CALIBRATION_DIR  = 'data/calibration'   # use this, not CALIBRATION_PATH
FINGER_CHANNELS  = ['thumb','index','middle','ring','little']
IMU_CHANNELS     = ['pitch','roll','yaw']
```

## Key API Signatures

### frame.py
```python
make_raw_frame(frame_id, r_t, r_i, r_m, r_r, r_l, r_p, r_rl, r_y,
               l_t, l_i, l_m, l_r, l_l, l_p, l_rl, l_y) -> dict
# Keys: 'frame_id', 'right'/'left' -> 'thumb','index','middle','ring','little','pitch','roll','yaw'
# NEVER use 'r_thumb', 'fingers[0]' etc.
```

### calibration.py (Phase 3 — profile-aware)
```python
list_profiles() -> list
create_profile(profile_name: str) -> str
save_calibration(calibration_data, profile_name: str) -> str
get_today_calibration_path(profile_name: str) -> str | None
load_calibration(filepath: str) -> CalibrationData   # unchanged, takes full path
```

### ui/main_window.py
```python
class MainWindow(QMainWindow):
    def on_frame_ready(self, processed_frame: dict)   # slot: frame_ready signal
    def on_status_message(self, message: str)         # slot: status_message signal
    def set_connected(self, connected: bool)          # call once after serial starts
```

### ui/calibration_wizard.py
```python
class CalibrationWizard(QDialog):
    def __init__(self, frame_queue: queue.Queue)
    def run_wizard(self) -> tuple   # (profile_name, CalibrationData) or (None, None)
```

### processing_thread.py
```python
class ProcessingThread(QThread):
    frame_ready        = pyqtSignal(object)  # processed frame dict
    frame_drop_detected = pyqtSignal(int)    # Phase 4 uses this
    status_message     = pyqtSignal(str)
    def set_recording(self, recording: bool) # Phase 4 uses this
    def reset_filters(self)
    def stop(self)
```

## Thread Architecture (Never Break)

serial_thread -> Queue -> processing_thread -> Qt Signal -> main thread (UI)

Rules:
1. UI never touches Queue directly
2. Processing thread never calls any UI method directly
3. Always connect signals BEFORE QThread.start()
4. Always call processing_thread.wait() after .stop()
5. SerialThread daemon=True

## main.py Startup Sequence (Phase 3)

```
1. QApplication(sys.argv)          ← NOT QCoreApplication
2. Ctrl+C handler + QTimer 200ms
3. select_port()                   ← input() safe here
4. SerialThread.start()            ← NO input() after this
5. time.sleep(2.0) + drain_queue()
6. CalibrationWizard.run_wizard()  ← reads Queue directly (ProcessingThread not started)
7. MainWindow()
8. Connect signals THEN ProcessingThread.start()
9. window.show() + app.exec_()
10. processing_thread.stop() + .wait()
11. serial_thread.stop() + .join(timeout=2)
```

## Calibration Profile System

```
data/calibration/<profile_name>/calibration_<YYYYMMDD>.json
```

JSON contains: date, profile, min_values, max_values

## Known Bugs Fixed in Phase 3

1. TypeError on wizard open:
   _wire_action_btn caught RuntimeError but PyQt5 raises TypeError on
   disconnect() with no existing connections.
   Fix: except (RuntimeError, TypeError)

2. Profile name input hidden on first run:
   Input field visibility relied on currentTextChanged which never fires
   if CREATE_NEW_OPTION was already selected at construction.
   Fix: check currentText() at construction, set setVisible() directly.

## Gesture Vocabulary (10 Signs — Decided)
HELLO, STOP, YES, NO, THANKYOU, SORRY, HELP, WATER, PLEASE, MORE

Hardware note: MCP sensors (2 per finger) would improve accuracy. Decision:
do not change now. Record dataset, train model, check confusion matrix first.
If specific sign pairs show poor accuracy, revisit then.

## Phase Status — All Phases

---

### Phase 0 ✅ COMPLETE — Hardware Prototype + Firmware Baseline

Goal: Validate sensor physics before writing any software.

What was built:
- Rigid one-finger prototype using SS49E Hall sensor + magnet on cardboard strip
- Minimal ESP32 firmware streaming raw ADC at 30 Hz
- Sensor behaviour validated (noise, range, polarity, distance sensitivity)

Key finding: Initial wiring had VCC/GND swapped on SS49E. After correction:
- Sensor reads ~1.65V with no magnet (correct baseline)
- Achieved 1550 ADC count range (38% of full 12-bit range)
- Noise at rest: below ±15 counts

Hardware facts locked in:
- Hall sensor GPIO pin: 32 (NOT 23 — that was wrong initial wiring)
- Sensor is INVERTED: open hand ~2900 ADC, closed hand ~1650 ADC
- min=open, max=closed in calibration

Completion criteria verified:
- [x] ADC values stream at 30 Hz in Serial Monitor
- [x] Clear monotonic change from open to closed finger
- [x] Noise at rest below ±15 counts

---

### Phase 1 ✅ COMPLETE — Serial Communication + Packet Parser

Goal: Python receives, validates, and parses structured packets from ESP32.

What was built:
- ESP32 firmware upgraded to 19-field CSV packet with frame_id and checksum
- communication/serial_thread.py — dedicated thread, pushes to queue.Queue
- communication/packet_parser.py — 5-layer validation (prefix, field count,
  type checks, checksum, range checks)
- processing/frame.py — make_raw_frame(), make_processed_frame(),
  frame_to_feature_vector()
- config.py — all constants, no magic numbers anywhere

Packet format (DO NOT CHANGE):
F,<frame_id>,<R_T>,<R_I>,<R_M>,<R_R>,<R_L>,<R_P>,<R_RL>,<R_Y>,
<L_T>,<L_I>,<L_M>,<L_R>,<L_L>,<L_P>,<L_RL>,<L_Y>,<checksum>\n

19 fields total. Checksum = sum(10 finger ints) + sum(int(imu*10) for 6 IMU values)

Test results:
- 1506 frames received, 0 drops, 100% checksum pass rate, consistent 30 Hz

"Unknown packet prefix" warnings on startup = NORMAL. ESP32 sends garbage bytes
before settling into protocol. drain_queue() clears them. Do not fix this.

Completion criteria verified:
- [x] Parsed frame dicts print to console at 30 Hz
- [x] Deliberate checksum error → Python logs warning and discards
- [x] Frame drop detection logs correctly when frame_id skips

---

### Phase 2 ✅ COMPLETE — Processing Pipeline (Filter + Normalize)

Goal: Raw ADC values (0-4095) become clean normalized values (0.0-1.0)
ready for ML training and UI display.

What was built:
- processing/filter.py — EMAFilter class, alpha=0.25, 16 independent instances
  (one per sensor channel), seeded on first call (NOT initialized to 0)
- processing/calibration.py — CalibrationData, Calibrator, save/load functions
  (Phase 2 version — profile support added in Phase 3)
- processing/processing_thread.py — QThread that consumes Queue, applies filter
  then normalize, detects frame drops, emits Qt Signals

Key design decisions:
- Filter THEN normalize (never normalize then filter — causes clipping at 0/1)
- EMA alpha=0.25: noise absorbed, real movement tracked in 3-4 frames at 30 Hz
- Frame drop outside recording: log warning only
- Frame drop during recording: emit frame_drop_detected signal (Phase 4 uses this)
- Dummy channels (min==max): return 0.0 safely (no crash)
- IMU channels: pass through raw degrees unchanged (already universal)

Both standalone tests passing:
- test_filter.py
- test_calibration.py

Completion criteria verified:
- [x] Open hand reads ~0.0, fully bent reads ~1.0 after calibration
- [x] EMA smoothing visibly reduces noise vs Phase 1 raw values
- [x] Frame drop during test logs warning correctly
- [x] Ctrl+C exits cleanly with no crash

---

### Phase 3 ✅ COMPLETE — Sensor Dashboard UI

Goal: Live desktop window showing all 16 sensor values updating in real time.
First visual milestone — see glove data on screen without a terminal.

What was built:
- ui/__init__.py — empty package marker
- ui/main_window.py — QMainWindow with 3 panels:
    Sensor Values panel (active): 10 finger labels (0.00-1.00) + 6 IMU labels (degrees)
    Recorder panel (stub): placeholder, Phase 4 fills this in
    Dataset panel (stub): placeholder, Phase 4 fills this in
    Status bar: connection status (left) + live frame rate Hz (right)
- ui/calibration_wizard.py — QDialog with 4 pages (QStackedWidget):
    Page 0: Profile selector (dropdown + create new option)
    Page 1: Open hand step
    Page 2: Closed hand step
    Page 3: Done summary
    Uses FrameCollectorThread (QThread) for non-blocking frame collection
- processing/calibration.py — UPDATED with profile support:
    list_profiles() -> list
    create_profile(profile_name) -> str
    save_calibration(data, profile_name) -> str  ← signature changed
    get_today_calibration_path(profile_name) -> str | None  ← signature changed
    load_calibration(filepath) -> CalibrationData  ← unchanged
- main.py — UPDATED:
    QApplication instead of QCoreApplication
    CalibrationWizard replaces terminal calibration
    Signals connected to window methods instead of standalone functions
    Window title includes profile name

Calibration file path format:
data/calibration/<profile_name>/calibration_<YYYYMMDD>.json

Bugs fixed during Phase 3:
1. _wire_action_btn() caught RuntimeError but PyQt5 raises TypeError on
   disconnect() with no existing connections.
   Fix: except (RuntimeError, TypeError)
2. Profile name input hidden on first run because currentTextChanged never
   fires when CREATE_NEW_OPTION is already the default selection.
   Fix: check currentText() at construction time, set visibility directly.

Completion criteria verified:
- [x] App opens → wizard runs → main window appears with profile name in title
- [x] Bend prototype finger → R_T updates live on screen (0.00 to 1.00)
- [x] Status bar shows ~30 Hz

Git commit: "Phase 3 complete: sensor dashboard UI"

---

### Phase 4 ⬜ NEXT — Gesture Recorder + Dataset Manager

Goal: Record labeled gesture samples and save them to disk in a structured
format ready for ML training. This is the PRIMARY PURPOSE of the entire
application — without this phase, no dataset exists and no model can be trained.

Hardware required: 1-finger prototype + ESP32 (current hardware is sufficient)

Files to create:
- recording/__init__.py                 ← empty package marker
- recording/gesture_recorder.py        ← captures exactly 60 frames per sample
- dataset/__init__.py                  ← empty package marker
- dataset/dataset_manager.py           ← saves/loads CSV files, manages folder structure
- ui/recorder_panel.py                 ← replaces Recorder stub in MainWindow
- ui/dataset_panel.py                  ← replaces Dataset stub in MainWindow

Key behaviours:
- User enters gesture label (e.g. HELLO) → presses Record
- System captures exactly 60 frames automatically
- Progress shown live in UI: "Frames: 12/60"
- Auto-stops at 60 frames
- Frame drop during recording → DISCARD entire sample immediately, warn user
  (ProcessingThread.frame_drop_detected signal already exists — connect to it)
- Early stop by user → repeat final frame to fill 60 (NEVER zero-pad)
- After 60 frames → user reviews → Save or Discard
- Save as: data/dataset/<LABEL>/sample_NNN.csv
  60 rows × 16 columns, header = FEATURE_ORDER from config.py
  NNN auto-increments per label

ProcessingThread integration:
- processing_thread.set_recording(True)  ← call when recording starts
- processing_thread.set_recording(False) ← call when recording stops/discards
- processing_thread.frame_drop_detected  ← connect to discard handler
- processing_thread.reset_filters()      ← call at start of each recording session

MainWindow integration:
- recorder_panel.py replaces the stub QGroupBox returned by _build_recorder_panel()
- dataset_panel.py replaces the stub QGroupBox returned by _build_dataset_panel()
- Do NOT restructure MainWindow layout — the 3-panel structure is already correct

Dataset folder structure:
data/dataset/
├── HELLO/
│   ├── sample_001.csv
│   ├── sample_002.csv
│   └── ...
├── STOP/
│   └── sample_001.csv
└── ...

CSV file format (60 rows × 16 columns):
Header row: R_T,R_I,R_M,R_R,R_L,R_P,R_RL,R_Y,L_T,L_I,L_M,L_R,L_L,L_P,L_RL,L_Y
Data rows: one row per frame, values are normalized floats (0.0-1.0 for fingers,
           degrees for IMU — matching FEATURE_ORDER exactly)

Completion criteria:
- [ ] Record one gesture → sample_001.csv saved to data/dataset/HELLO/
- [ ] Open CSV → verify 60 rows × 16 columns with correct header
- [ ] Cause frame drop during recording → sample discarded, UI warning shown
- [ ] Dataset panel shows correct sample count per label
- [ ] Stop recording early → final frame repeated in saved CSV (not zeros)

---

### Phase 5 ⬜ UPCOMING — Signal Plots

Goal: Real-time scrolling graphs of finger bend signals — visual confirmation
of sensor quality and gesture shape.

Hardware required: 1-finger prototype + ESP32 (current hardware is sufficient)

Files to create:
- visualization/__init__.py
- visualization/signal_plot.py  ← Matplotlib embedded in PyQt5

What it does:
- Two scrolling graphs: Right Hand (5 colored lines) + Left Hand (5 colored lines)
- Shows last 90 frames (3 seconds) of history
- Each finger color-coded for easy identification
- During recording: progress indicator shown alongside graph
- EMA smoothing visibly reduces noise spikes compared to raw signal

Integration: signal_plot.py widget added to MainWindow layout (below or beside
sensor values panel). Receives data from frame_ready signal.

Completion criteria:
- [ ] Bend prototype finger → smooth curve appears on graph
- [ ] EMA smoothing visibly reduces noise spikes
- [ ] During recording → progress indicator shown alongside graph

---

### Phase 6 ⬜ UPCOMING — 3D Hand Skeleton

Goal: 3D virtual hand that mirrors glove movement in real time.
Visual tool for verifying sensor coverage and gesture distinctiveness.

Hardware required: FULL GLOVE ASSEMBLY (3D printed, all 10 sensors connected)
Status: BLOCKED — waiting for full hardware

Files to create:
- visualization/hand_skeleton.py  ← PyQtGraph 3D rendering

What it does:
- 3D skeleton of both hands rendered in real time
- Finger joint angles driven by normalized sensor values
- Wrist orientation driven by IMU pitch/roll/yaw
- Lets you visually verify that each gesture looks distinct

---

### Phase 7 ⬜ UPCOMING — Dataset Analysis Tools

Goal: Tools for reviewing dataset quality before ML training.

Hardware required: FULL GLOVE ASSEMBLY
Status: BLOCKED — waiting for full hardware

What it does:
- Per-gesture signal overlays (all samples of one gesture on one graph)
- Outlier detection — flag samples that look different from the rest
- Dataset statistics: sample count per label, class balance, temporal coverage
- Lets you identify and delete bad samples before training

---

### Phase 8 ⬜ UPCOMING — ML Export System

Goal: Export the collected dataset as NumPy arrays ready for BiLSTM training.

Hardware required: FULL GLOVE ASSEMBLY (to have a complete dataset)
Status: BLOCKED — waiting for full hardware

Files to create:
- dataset/ml_export.py

Export format:
- X.npy — shape (N, 60, 16) — N samples, 60 frames, 16 features
- y.npy — shape (N,) — integer class labels
- labels.json — maps integer label to gesture name

After export:
1. Train BiLSTM on PC with GPU (TensorFlow/Keras)
2. Evaluate: confusion matrix, per-gesture accuracy
3. Convert to TFLite format
4. Quantize to INT8 for embedded deployment
5. Flash to ESP32-S3

Completion criteria:
- [ ] Export button → X.npy and y.npy written to disk
- [ ] X.npy shape = (N, 60, 16), y.npy shape = (N,)
- [ ] Load in Python and verify shapes and value ranges

## Packet Format (DO NOT CHANGE)

F,<frame_id>,<R_T>,<R_I>,<R_M>,<R_R>,<R_L>,<R_P>,<R_RL>,<R_Y>,
<L_T>,<L_I>,<L_M>,<L_R>,<L_L>,<L_P>,<L_RL>,<L_Y>,<checksum>

19 fields. Checksum = sum(finger ints) + sum(int(imu*10))

## Key Design Decisions

| Decision | Value | Reason |
|----------|-------|--------|
| Queue name | QUEUE_MAX_SIZE | Do NOT rename |
| Frame drop policy | DISCARD | Corrupted windows poison BiLSTM |
| Padding policy | Repeat final frame | Never zero-pad |
| Filter order | Filter THEN normalize | Filtering 0-1 causes clipping |
| IMU treatment | Pass through raw degrees | Already universal |
| Qt class | QApplication | Required for any window/widget |
| Signal connection | Before start() | Prevents race condition |
| PyQt5 disconnect | catch (RuntimeError, TypeError) | PyQt5 raises TypeError |
| Calibration storage | Per-profile subdir + date file | Multi-user support |

## Instructions for New Claude Sessions

1. Read this file completely
2. Read all Python files in Project Knowledge (actual code, not summaries)
3. Confirm current phase with Anoop before starting
4. Check config.py for exact constant names before any imports
5. Check frame.py for exact dict key names before accessing frame data
6. Never use magic numbers
7. Never share mutable state between threads
8. Connect signals BEFORE QThread.start()
9. Use QApplication not QCoreApplication
10. Explain reasoning — Anoop wants to learn
11. Analogies first, then technical detail
12. Be direct and honest
13. python3 not python
14. "Unknown packet prefix" warnings on startup = NORMAL, ignore
15. recorder_panel.py, dataset_panel.py, recording/, dataset/ do NOT exist yet
