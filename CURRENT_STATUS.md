# Smart Glove Project — Current Status
# ============================================================
# CRITICAL: Read this file FIRST in every new Claude session.
#
# FILES IN PROJECT KNOWLEDGE (read all of them):
#   1.  CURRENT_STATUS.md                                ← this file
#   2.  SmartGlove_ProjectDocumentation_Updated.docx     ← full project overview
#   3.  SmartGlove_Phase2_Documentation.docx             ← Phase 2 deep technical detail
#   4.  SmartGlove_Phase3_Documentation.docx             ← Phase 3 deep technical detail
#   5.  SmartGlove_Phase4_Documentation.docx             ← Phase 4 deep technical detail
#   6.  SmartGlove_Phase5_Documentation.docx             ← Phase 5 deep technical detail (NEW)
#   7.  config.py                                        ← ALL constants
#   8.  main.py                                          ← Phase 5 entry point (current)
#   9.  serial_thread.py                                 ← serial communication
#   10. packet_parser.py                                 ← packet validation
#   11. frame.py                                         ← data structures
#   12. filter.py                                        ← EMA filter
#   13. calibration.py                                   ← normalization + profiles
#   14. processing_thread.py                             ← pipeline thread (Phase 5: raw_frame_ready + update_calibration)
#   15. main_window.py                                   ← main window (Phase 5: tabbed layout)
#   16. calibration_wizard.py                            ← Phase 3 (kept as fallback, NOT called at startup)
#   17. calibration_tab.py                               ← NEW Phase 5: inline calibration tab
#   18. style.py                                         ← NEW Phase 5: APP_STYLESHEET + apply_style() + bend_color()
#   19. recorder_panel.py                                ← Phase 5: Record button disabled at startup
#   20. dataset_panel.py                                 ← per-label, per-profile count display
#   21. gesture_recorder.py                              ← 60-frame capture state machine
#   22. dataset_manager.py                               ← CSV save/load/count with profile tags
#   23. voice_listener.py                                ← Vosk + sounddevice QThread
#   24. signal_plot.py                                   ← NEW Phase 5: PyQtGraph scrolling graphs
#
# Last updated: Phase 5 Complete
# ============================================================

## Project Summary
Building an AI Sign-to-Speech Smart Glove system. Two gloves with Hall sensors
and IMU capture hand gestures. A BiLSTM ML model recognizes gestures and
converts them to text/speech. The system runs fully on embedded hardware (Edge AI).

The current software effort is the Smart Glove Dataset Studio — a Python desktop
application for recording, managing, and exporting a labeled gesture dataset.

## Team & Environment
- Developer: Anoop (+ teammate)
- OS: Ubuntu 22.04 (Anoop) + Windows (some teammates)
- Python: python3 (never 'python')
- Python venv: ~/signgloves/venv/ (auto-activates when cd into ~/signgloves)
- Project folder: ~/signgloves/smart_dataset_studio/
- GitHub repo: https://github.com/ANOOP222004/signgloves (Private)
- ESP32 port: /dev/ttyUSB0 (appears as option 32 in port list)

## Folder Structure (Complete — After Phase 5)

```
~/signgloves/
├── smart_dataset_studio/
│   ├── main.py                        ← Phase 5 entry point (current)
│   ├── config.py                      ← ALL constants (Phase 5: plot constants + FINGER_COLORS)
│   ├── requirements.txt               ← includes pyqtgraph>=0.14.0 (added Phase 5)
│   ├── test_filter.py                 ← Phase 2 test (PASSING)
│   ├── test_calibration.py            ← Phase 2 test (PASSING)
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py             ← Phase 5: QTabWidget 6 tabs, bend_color() on labels
│   │   ├── style.py                   ← NEW Phase 5: dark theme stylesheet + bend_color()
│   │   ├── calibration_tab.py         ← NEW Phase 5: inline calibration, auto-load, raw frame capture
│   │   ├── calibration_wizard.py      ← Phase 3 (KEPT as fallback, not called at startup)
│   │   ├── recorder_panel.py          ← Phase 5: Record disabled at startup, on_calibration_done()
│   │   └── dataset_panel.py           ← Phase 4: per-label, per-profile counts
│   │
│   ├── visualization/                 ← NEW Phase 5
│   │   ├── __init__.py
│   │   └── signal_plot.py             ← SignalPlotWidget: PyQtGraph, deques, 20 Hz timer, marker
│   │
│   ├── recording/                     ← Phase 4
│   │   ├── __init__.py
│   │   └── gesture_recorder.py        ← 60-frame capture state machine
│   │
│   ├── dataset/                       ← Phase 4
│   │   ├── __init__.py
│   │   └── dataset_manager.py         ← CSV save/load/count, profile-tagged filenames
│   │
│   ├── voice/                         ← Phase 4
│   │   ├── __init__.py
│   │   ├── voice_listener.py          ← Vosk + sounddevice QThread
│   │   └── vosk-model-small-en-us-0.15/  ← downloaded separately (in .gitignore)
│   │
│   ├── communication/                 ← Phase 1 (unchanged)
│   │   ├── __init__.py
│   │   ├── serial_thread.py
│   │   └── packet_parser.py
│   │
│   └── processing/                    ← Phases 2–5
│       ├── __init__.py
│       ├── frame.py
│       ├── filter.py
│       ├── calibration.py
│       └── processing_thread.py       ← Phase 5: raw_frame_ready signal + update_calibration()
│
├── firmware/
│   └── phase1_slave_esp32/
│       └── phase1_slave_esp32.ino     ← CURRENTLY FLASHED, do not reflash
│
├── docs/
│   ├── SmartGlove_ProjectDocumentation_Updated.docx
│   ├── SmartGlove_Phase1_Documentation.docx
│   ├── SmartGlove_Phase2_Documentation.docx
│   ├── SmartGlove_Phase3_Documentation.docx
│   ├── SmartGlove_Phase4_Documentation.docx
│   └── SmartGlove_Phase5_Documentation.docx  ← NEW
│
├── venv/
├── .gitignore                         ← includes voice/vosk-model-small-en-us-0.15/
└── CURRENT_STATUS.md
```

data/ folder (git-ignored, created at runtime):
```
smart_dataset_studio/data/
├── calibration/
│   ├── anoop/
│   │   └── calibration_YYYYMMDD.json
│   └── <teammate>/
│       └── calibration_YYYYMMDD.json
└── dataset/
    ├── HELLO/
    │   ├── anoop_sample_001.csv
    │   └── teammate1_sample_001.csv
    └── STOP/
        └── anoop_sample_001.csv
```

## config.py Constants (Complete — After Phase 5)

```python
BAUD_RATE       = 115200
QUEUE_MAX_SIZE  = 100          # NOT QUEUE_SIZE
SAMPLE_RATE     = 30
WINDOW_SIZE     = 60
FRAME_PERIOD_MS = 33
EMA_ALPHA       = 0.25
FRAME_ID_MAX    = 9999         # max VALUE — modulo = FRAME_ID_MAX + 1 = 10000
DATASET_PATH     = "data/dataset/"
CALIBRATION_PATH = "data/calibration/"
NUM_FEATURES = 16
FEATURE_ORDER = ["R_T","R_I","R_M","R_R","R_L","R_P","R_RL","R_Y",
                 "L_T","L_I","L_M","L_R","L_L","L_P","L_RL","L_Y"]
CALIBRATION_DIR  = 'data/calibration'
FINGER_CHANNELS  = ['thumb','index','middle','ring','little']
IMU_CHANNELS     = ['pitch','roll','yaw']

# Phase 4:
GESTURE_LABELS  = ['HELLO','STOP','YES','NO','THANKYOU',
                   'SORRY','HELP','WATER','PLEASE','MORE']
VOICE_MODEL_PATH  = "voice/vosk-model-small-en-us-0.15"
VOICE_COMMANDS    = ["start", "stop", "save", "discard"]
VOICE_SAMPLE_RATE = 16000
VOICE_BLOCK_SIZE  = 8000

# Phase 5 additions:
PLOT_HISTORY_FRAMES = 90       # frames of scroll history (90 / 30Hz = 3 seconds)
PLOT_TIMER_MS       = 50       # redraw interval = 20 Hz
FINGER_COLORS = {
    'thumb':  (220,  50,  50),  # red
    'index':  ( 50, 200,  50),  # green
    'middle': ( 50, 130, 255),  # blue
    'ring':   (255, 165,   0),  # orange
    'little': (180,  80, 220),  # purple
}
```

## Key API Signatures

### frame.py (unchanged)
```python
make_raw_frame(frame_id, r_t, r_i, r_m, r_r, r_l, r_p, r_rl, r_y,
               l_t, l_i, l_m, l_r, l_l, l_p, l_rl, l_y) -> dict
frame_to_feature_vector(processed_frame) -> list  # 16-element, FEATURE_ORDER
# Keys: 'frame_id', 'right'/'left' -> 'thumb','index','middle','ring','little','pitch','roll','yaw'
```

### calibration.py (unchanged from Phase 3)
```python
list_profiles() -> list
create_profile(profile_name: str) -> str
save_calibration(calibration_data, profile_name: str) -> str
get_today_calibration_path(profile_name: str) -> str | None
load_calibration(filepath: str) -> CalibrationData
```

### processing/processing_thread.py (Phase 5 additions)
```python
class ProcessingThread(QThread):
    raw_frame_ready     = pyqtSignal(object)   # NEW Phase 5: raw ADC before filtering
    frame_ready         = pyqtSignal(object)   # processed 0.0-1.0 floats
    frame_drop_detected = pyqtSignal(int)
    status_message      = pyqtSignal(str)
    def set_recording(self, recording: bool)
    def reset_filters(self)
    def update_calibration(self, calibration_data: CalibrationData)  # NEW Phase 5
    def stop(self)
```

### ui/main_window.py (Phase 5 — tabbed layout)
```python
class MainWindow(QMainWindow):
    # Public attributes for signal wiring in main.py:
    self.plot_widget      # SignalPlotWidget (Record tab)
    self.calibration_tab  # CalibrationTab (Calibration tab)
    def __init__(self, recorder_panel=None, dataset_panel=None)
    def on_frame_ready(self, processed_frame: dict)   # updates Dashboard labels + bend_color
    def on_status_message(self, message: str)
    def set_connected(self, connected: bool)
    def closeEvent(self, event)                        # stops plot_widget timer
```

### ui/calibration_tab.py (NEW Phase 5)
```python
class CalibrationTab(QWidget):
    calibration_updated = pyqtSignal(object)   # emits CalibrationData after save
    # Slots:
    def on_raw_frame(self, raw_frame: dict)    # connected to raw_frame_ready
    # Internal: _profile_name — current active profile (auto-set on startup)
    # Auto-load: _refresh_profile_dropdown() called in __init__()
    #   → sets _profile_name, loads today's cal, emits via QTimer.singleShot(0)
```

### ui/style.py (NEW Phase 5)
```python
APP_STYLESHEET: str              # complete Qt stylesheet string
def apply_style(app): ...        # call once after QApplication(), before any widget
def bend_color(value: float) -> str:  # 0.0=gray, 0.1-0.4=blue, 0.4-0.7=amber, 0.7+=teal
```

### visualization/signal_plot.py (NEW Phase 5)
```python
class SignalPlotWidget(QWidget):
    # Slots:
    def on_frame(self, processed_frame: dict)          # appends to deques, no drawing
    def on_recording_started(self)                     # shows progress marker
    def on_recording_stopped(self)                     # hides marker
    def on_recording_progress(self, captured, total)   # moves marker position
    def stop(self)                                     # stops QTimer (call in closeEvent)
    # Internal: deques[hand][ch] — 10 deques, maxlen=PLOT_HISTORY_FRAMES
    # Redraw: QTimer every PLOT_TIMER_MS calls _redraw() → setData() on all curves
```

### ui/recorder_panel.py (Phase 5 change)
```python
class RecorderPanel(QGroupBox):
    # NEW Phase 5:
    def on_calibration_done(self, calibration_data=None)
    # Record button starts DISABLED — enabled by on_calibration_done()
    # All other API unchanged from Phase 4
```

### recording/gesture_recorder.py (unchanged from Phase 4)
```python
class GestureRecorder(QObject):
    progress_updated = pyqtSignal(int, int)
    capture_complete = pyqtSignal(list)
    capture_failed   = pyqtSignal(str)
    def start_recording(self)
    def stop_recording(self)
    def discard(self)             # MUST call after save to reset to IDLE
    def on_frame(self, processed_frame: dict)
    def on_frame_drop(self, dropped_count: int)
    def is_idle(self) -> bool
    def is_recording(self) -> bool
    def is_complete(self) -> bool
```

### dataset/dataset_manager.py (unchanged from Phase 4)
```python
class DatasetManager:
    def __init__(self, profile_name: str, dataset_path: str = DATASET_PATH)
    def save_sample(self, label: str, frames: list) -> str
    def sample_count(self, label: str) -> int
    def profile_sample_count(self, label: str) -> int
    def profile_counts(self, label: str) -> dict
    def all_counts(self) -> dict
    def all_profile_counts(self) -> dict
    def list_labels(self) -> list
    def delete_sample(self, label: str, profile: str, sample_num: int) -> bool
```

## Thread Architecture (Never Break)

```
serial_thread  → queue.Queue  → processing_thread → Qt Signals → main thread (UI)
voice_listener (QThread)      → Qt Signals         → RecorderPanel.on_voice_command()
```

Rules (unchanged from all previous phases):
1. UI never touches Queue directly
2. Processing thread never calls any UI method directly
3. Always connect signals BEFORE QThread.start()
4. Always call processing_thread.wait() after .stop()
5. SerialThread daemon=True
6. VoiceListener: always call .stop() then .wait() on shutdown

## Complete Signal Map (Phase 5)

```
processing_thread.raw_frame_ready    → calibration_tab.on_raw_frame
processing_thread.frame_ready        → window.on_frame_ready
processing_thread.frame_ready        → recorder.on_frame
processing_thread.frame_ready        → window.plot_widget.on_frame
processing_thread.frame_drop_detected → recorder.on_frame_drop
processing_thread.status_message     → window.on_status_message
calibration_tab.calibration_updated  → processing_thread.update_calibration
calibration_tab.calibration_updated  → recorder_panel.on_calibration_done
calibration_tab.calibration_updated  → [lambda: update dataset_manager.profile_name]
recorder_panel.recording_started     → processing_thread.set_recording(True)
recorder_panel.recording_started     → processing_thread.reset_filters
recorder_panel.recording_started     → window.plot_widget.on_recording_started
recorder_panel.recording_stopped     → processing_thread.set_recording(False)
recorder_panel.recording_stopped     → window.plot_widget.on_recording_stopped
recorder_panel.sample_saved          → dataset_panel.refresh
recorder.progress_updated            → window.plot_widget.on_recording_progress
voice_listener.command_detected      → recorder_panel.on_voice_command
voice_listener.error_occurred        → recorder_panel.on_voice_error
```

## main.py Startup Sequence (Phase 5)

```
1.  QApplication(sys.argv)
2.  apply_style(app)                    ← MUST be before any widget
3.  Ctrl+C handler + QTimer 200ms
4.  select_port()                       ← input() safe here
5.  SerialThread.start()                ← NO input() after this
6.  time.sleep(2.0) + drain_queue()
7.  DatasetManager(profile_name='default')
8.  GestureRecorder()
9.  VoiceListener()                     ← NOT started yet
10. RecorderPanel(recorder, dm, voice)  ← Record button DISABLED at construction
11. DatasetPanel(dm)
12. Wire: sample_saved → dataset_panel.refresh
13. Wire: voice_listener signals → recorder_panel slots
14. MainWindow(recorder_panel, dataset_panel)
    └── creates CalibrationTab (auto-loads today's cal via QTimer.singleShot)
    └── creates SignalPlotWidget
15. ProcessingThread(frame_queue, CalibrationData())  ← empty cal at startup
16. Wire ALL signals (see Complete Signal Map above)
17. ProcessingThread.start()
18. window.show() + app.exec_()
19. voice_listener.stop() + .wait()
20. processing_thread.stop() + .wait()
21. serial_thread.stop() + .join(timeout=2)
```

## Profile-Tagged Dataset Filenames

Every saved CSV: data/dataset/<LABEL>/<profile>_sample_<NNN>.csv
Counter is per-profile per-label — independent for each person.
Merging: ML export reads ALL .csv files in each label folder.
Exclusion: move/delete specific profile's files before ML export.

## Gesture Vocabulary (10 Signs — Final)
HELLO, STOP, YES, NO, THANKYOU, SORRY, HELP, WATER, PLEASE, MORE
Defined in config.py GESTURE_LABELS.

## Dependencies (requirements.txt)
pyserial>=3.5
PyQt5>=5.15
numpy>=1.24
pandas>=2.0
sounddevice>=0.4.6
vosk>=0.3.45
pyqtgraph>=0.14.0    ← added Phase 5

## Known Bugs Fixed

### Phase 3
1. TypeError on wizard open: catch (RuntimeError, TypeError) not just RuntimeError
2. Profile name input hidden on first run: check currentText() at construction

### Phase 4
1. Recorder stuck in COMPLETE after first save: add recorder.discard() in _on_save_clicked()

### Phase 5
1. CalibrationTab showing 'No Profile' despite profile shown in dropdown.
   Root cause: _profile_name only set on Load button click.
   Fix: _refresh_profile_dropdown() auto-sets _profile_name when profiles exist.

2. Record button stayed disabled despite today's calibration auto-loading.
   Root cause: calibration_updated emitted inside __init__() before signal connections wired.
   Fix: QTimer.singleShot(0, lambda: self.calibration_updated.emit(...))
   This defers the emit to first event loop tick after all connections are live.

## Key Design Decisions

| Decision | Value | Reason |
|----------|-------|--------|
| Queue name | QUEUE_MAX_SIZE | Do NOT rename |
| Frame drop policy | DISCARD entire sample | Corrupted windows poison BiLSTM |
| Padding policy | Repeat final frame | Never zero-pad (zero = real physical state) |
| Filter order | Filter THEN normalize | Filtering 0-1 causes clipping |
| IMU treatment | Pass through raw degrees | Already universal |
| Qt class | QApplication | Required for any window/widget |
| Signal connection | Before start() | Prevents race condition |
| PyQt5 disconnect | catch (RuntimeError, TypeError) | PyQt5 raises TypeError |
| Calibration storage | Per-profile subdir + date file | Multi-user support |
| Dataset filenames | <profile>_sample_<NNN>.csv | Permanent per-person traceability |
| Voice library | vosk + sounddevice | Offline, cross-platform (Ubuntu + Windows) |
| Voice vocabulary | Fixed 4-word grammar | Faster + more accurate than full English |
| After save | call recorder.discard() | Resets state machine to IDLE |
| Plot library | PyQtGraph (not Matplotlib) | Real-time updates, Qt-native, no full redraw |
| Plot data rate | 30 Hz capture, 20 Hz draw | Decouple ingestion from render; 20Hz smooth to eye |
| Plot buffer | deque(maxlen=90) | O(1) append, auto-drop oldest, 3s history |
| Calibration UI | Inline tab, not blocking dialog | Access anytime without restart |
| Raw frame signal | raw_frame_ready in ProcessingThread | CalibrationTab needs ADC values before normalization |
| Calibration auto-emit | QTimer.singleShot(0) | Defers emit until after signal connections are live |
| Style location | ui/style.py only | Single source of truth; one file to retheme |
| Startup calibration | Empty CalibrationData(), auto-load via tab | No blocking wizard; tab handles everything |
| Hardware expansion | Deferred until confusion matrix inspected | No evidence of problem yet |

## Phase Status

### Phase 0 ✅ COMPLETE — Hardware Prototype + Firmware Baseline
- VCC/GND swapped on SS49E initially — corrected
- Sensor reads ~1.65V with no magnet (correct baseline)
- ADC range: ~1550 counts (38% of 12-bit range)
- GPIO pin: 32 (NOT 23)
- Sensor INVERTED: open hand ~2900 ADC, closed hand ~1650 ADC
- Calibration: min=open(2900), max=closed(1650)

---

### Phase 1 ✅ COMPLETE — Serial Communication + Packet Parser
Packet format (DO NOT CHANGE):
F,<frame_id>,<R_T>,<R_I>,<R_M>,<R_R>,<R_L>,<R_P>,<R_RL>,<R_Y>,
<L_T>,<L_I>,<L_M>,<L_R>,<L_L>,<L_P>,<L_RL>,<L_Y>,<checksum>
19 fields. Checksum = sum(finger ints) + sum(int(imu*10))
Results: 1506 frames, 0 drops, 100% checksum pass, 30 Hz.
"Unknown packet prefix" on startup = NORMAL (ESP32 boot noise).

---

### Phase 2 ✅ COMPLETE — Processing Pipeline (Filter + Normalize)
EMAFilter (alpha=0.25), CalibrationData/Calibrator, processing_thread.py.
Tests: test_filter.py and test_calibration.py both PASSING.

---

### Phase 3 ✅ COMPLETE — Sensor Dashboard UI
main_window.py (3 panels), calibration_wizard.py (Phase 3 — kept as fallback).
calibration.py: profile support added.

---

### Phase 4 ✅ COMPLETE — Gesture Recorder + Dataset Manager + Voice Commands
gesture_recorder.py (state machine), dataset_manager.py (profile-tagged CSVs),
recorder_panel.py, dataset_panel.py, voice_listener.py.
Git commit: "Phase 4 complete: gesture recorder + dataset manager + voice commands + profile tagging"

---

### Phase 5 ✅ COMPLETE — Signal Plots + Tabbed UI + Calibration Tab + Dark Theme

Goal: Real-time scrolling graphs, tabbed layout, inline calibration, dark theme.
Hardware: 1-finger prototype + ESP32 (current hardware sufficient).

What was built:
- visualization/signal_plot.py — PyQtGraph scrolling graphs.
  Two PlotItems (Right + Left hand), 5 color-coded curves each.
  Data capture 30 Hz (on_frame → deque append), redraw 20 Hz (QTimer → setData).
  Recording progress marker: dashed InfiniteLine moves from x=30 to x=90.
- ui/calibration_tab.py — inline calibration replacing startup wizard.
  Auto-loads today's calibration on startup via QTimer.singleShot(0).
  Gets raw ADC via raw_frame_ready signal (ProcessingThread new feature).
  Calibration values table with color-coded range quality indicator.
- ui/style.py — dark theme stylesheet. apply_style(app) + bend_color(value).
  All colors defined as constants. Single file to retheme the entire app.
- processing_thread.py updated:
  raw_frame_ready signal — emits raw ADC frame before filtering.
  update_calibration() — swaps CalibrationData at runtime (GIL-safe), resets filters.
- ui/main_window.py rewritten — QTabWidget 6 tabs.
  Tab 0 Dashboard, Tab 1 Record, Tab 2 Visualize stub,
  Tab 3 Calibration, Tab 4 Dataset stub, Tab 5 Export stub.
  Sensor value labels colored by bend_color(). closeEvent stops plot timer.
- ui/recorder_panel.py — Record button starts disabled, on_calibration_done() enables it.
- config.py — PLOT_HISTORY_FRAMES=90, PLOT_TIMER_MS=50, FINGER_COLORS dict.
- requirements.txt — pyqtgraph>=0.14.0 added.

Bugs fixed:
1. 'No Profile' on Capture despite profile shown — auto-set _profile_name in dropdown refresh.
2. Record button stayed disabled after auto-load — QTimer.singleShot(0) deferred emit.

Completion criteria: ALL PASSED.
Git commit: "Phase 5 complete: signal plots + tabbed UI + calibration tab + dark theme"

---

### Phase 6 ⬜ NEXT — 3D Hand Skeleton + Visualize Tab
Hardware required: FULL GLOVE ASSEMBLY (3D printed, all 10 sensors)
Status: BLOCKED — waiting for full hardware

What will be built:
- visualization/hand_skeleton.py — PyQtGraph GL 3D hand renderer.
  Maps bend values (0.0-1.0) to joint rotation angles.
  Both hands rendered side by side. IMU data rotates entire hand model.
- Tuning panel on Visualize tab:
  Per-finger max rotation sliders (how far virtual finger bends at 1.0)
  Global scale slider (hand size in 3D view)
  Wrist sensitivity slider (IMU rotation scale)
  Save/load tuning JSON to config path

Hardware expansion (2 sensors per finger) is DEFERRED until confusion matrix
from first trained model is inspected. See HARDWARE_EXPANSION.md.

---

### Phase 7 ⬜ UPCOMING — Dataset Analysis Tools
Hardware required: FULL GLOVE ASSEMBLY
Status: BLOCKED — waiting for full hardware
What it does: per-gesture signal overlays, outlier detection, dataset statistics.

---

### Phase 8 ⬜ UPCOMING — ML Export System
Hardware required: FULL GLOVE ASSEMBLY (complete dataset needed)
Status: BLOCKED — waiting for full hardware
Files: dataset/ml_export.py
Export: X.npy (N, 60, 16), y.npy (N,), labels.json, TF Dataset format.

## Instructions for New Claude Sessions

1.  Read this file completely — especially phase status and key decisions
2.  Read all Python files listed at the top of this file
3.  Confirm current phase with Anoop before starting any work
4.  Check config.py for exact constant names before any imports
5.  Check frame.py for exact dict key names before accessing frame data
6.  Never use magic numbers — all constants in config.py only
7.  Never share mutable state between threads
8.  Connect signals BEFORE QThread.start()
9.  Use QApplication not QCoreApplication
10. apply_style(app) must be called BEFORE any widget is created
11. After save: always call recorder.discard() to reset state machine to IDLE
12. Profile-tagged filenames: <profile>_sample_<NNN>.csv — never plain sample_NNN.csv
13. CalibrationTab emits calibration_updated via QTimer.singleShot(0) on auto-load
14. raw_frame_ready carries raw ADC; frame_ready carries processed 0.0-1.0
15. update_calibration() is GIL-safe — no mutex needed for the reference swap
16. Explain reasoning — Anoop wants to learn, not just copy-paste
17. Analogies first, then technical detail, then connection to this project
18. Be direct and honest — negative feedback is welcome
19. python3 not python
20. "Unknown packet prefix" warnings on startup = NORMAL, do not fix
21. calibration_wizard.py is KEPT but NOT called at startup — do not delete it
22. visualization/ folder EXISTS now (Phase 5 created it)
23. Phase 6 requires FULL GLOVE HARDWARE — do not start without it
