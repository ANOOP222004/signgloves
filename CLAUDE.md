# Smart Glove Dataset Studio — CLAUDE.md

> **START OF EVERY SESSION:** Read `CURRENT_STATUS.md` first. Anoop updates it at the end
> of every phase. It is the single source of truth for what is done and what is next.

---

## 1. PROJECT OVERVIEW

AI Sign-to-Speech Smart Glove for Indian Sign Language (ISL). Two gloves equipped with
Hall-effect sensors and an MPU6050 IMU capture hand gestures. A BiLSTM ML model will
eventually run on the ESP32-S3 to recognize gestures and convert them to text/speech
(Edge AI, no phone required).

The current software effort is **Smart Glove Dataset Studio** — a Python desktop app
(PyQt5) for recording, managing, visualizing, and exporting a labeled gesture dataset.

**Target vocabulary:** 10 ISL signs — HELLO, STOP, YES, NO, THANKYOU, SORRY, HELP,
WATER, PLEASE, MORE.

---

## 2. HARDWARE

### Right Hand Glove — Master (ESP32-S3 N16R8)
- Hall sensors: GPIO 1=Thumb, 2=Index, 3=Middle, 4=Ring, 5=Little (**ADC1 only**)
- IMU MPU6050: SDA=GPIO8, SCL=GPIO9, AD0=GND → I2C address 0x68
- 4.7 kΩ pull-ups on SDA and SCL to 3V3
- Connects to PC via USB-C **UART port** (right USB-C on DevKitC-1) → `/dev/ttyACM0`
- USB description: "USB Single Serial" — auto-detected by `select_port()` in `main.py`
- Firmware: `firmware/master_esp32s3/master_esp32s3.ino` (FLASHED ✅)
- 16 MB flash, 8 MB PSRAM — supports larger BiLSTM and longer vocabulary

### Left Hand Glove — Slave (ESP32 DevKit V1)
- Hall sensors: GPIO 32=Thumb, 33=Index, 34=Middle, 35=Ring, 25=Little
- **No IMU** — sends 0.0 for pitch/roll/yaw (correct, not a bug)
- Communicates to master via ESP-NOW at 30 Hz
- Firmware: `firmware/slave_esp32/slave_esp32.ino` (FLASHED ✅)
- USB description: "CP2102..." → `/dev/ttyUSB0` (not used by Python app)

### Wiring Safety Rule — READ BEFORE POWERING
Before connecting power: multimeter in resistance mode across 3V3 rail and GND rail.
Result **must be > 10 kΩ**. If < 500 Ω → short circuit → chip will burn.
(Two chips were already destroyed by reversed SS49E sensors — VCC/GND swapped.)

### ESP-NOW Data Flow
```
Left Glove (Slave)  ──ESP-NOW──►  Right Glove (Master)  ──USB Serial──►  Python App
  5 Hall ADC values                5 Hall + MPU6050                       frame_queue
  (pitch/roll/yaw = 0)             combines both hands
                                   → 19-field CSV packet at 30 Hz
```

### Packet Format (DO NOT CHANGE — parser built around this)
```
F,<frame_id>,<R_T>,<R_I>,<R_M>,<R_R>,<R_L>,<R_P>,<R_RL>,<R_Y>,
<L_T>,<L_I>,<L_M>,<L_R>,<L_L>,<L_P>,<L_RL>,<L_Y>,<checksum>
```
19 fields. `frame_id` wraps at 9999 (modulo 10000).
Checksum = `sum(finger_ints) + sum(round(imu_float * 10))` — use `round()` not `int()`.

---

## 3. SOFTWARE STACK

| Layer | Technology |
|---|---|
| Language | Python 3 (always `python3`, never `python`) |
| GUI | PyQt5 5.15+ |
| Real-time plots | PyQtGraph 0.14+ |
| 3D skeleton | PyQtGraph GL (OpenGL via xcb_egl backend) |
| Serial | pyserial 3.5+ |
| Audio / voice | sounddevice + Vosk (offline, no internet) |
| Data | NumPy, pandas |
| ML export (Phase 8) | TensorFlow / Keras (not yet) |

**Environment:**
- venv: `~/signgloves/venv/`
- Project: `~/signgloves/smart_dataset_studio/`
- OS: Ubuntu 22.04 (Anoop) + Windows (some teammates)
- GitHub: https://github.com/ANOOP222004/signgloves (Private)

**Critical OpenGL fix** — must appear at top of `main.py` BEFORE any Qt import:
```python
os.environ['QT_XCB_GL_INTEGRATION'] = 'xcb_egl'
os.environ['PYOPENGL_PLATFORM']      = 'egl'
```
Use direct assignment `[]`, not `setdefault()` — `setdefault` silently does nothing if
the variable already exists in the environment.

---

## 4. PHASE STATUS

| Phase | Status | Description |
|---|---|---|
| 0 | ✅ Complete | Hardware prototype + firmware baseline |
| 1 | ✅ Complete | Serial communication + packet parser |
| 2 | ✅ Complete | Processing pipeline (EMA filter + normalize) |
| 3 | ✅ Complete | Sensor dashboard UI |
| 4 | ✅ Complete | Gesture recorder + dataset manager + voice commands |
| 5 | ✅ Complete | Signal plots + tabbed UI + calibration tab + dark theme |
| 6 | ✅ Complete | Dual glove ESP-NOW + 3D hand skeleton |
| 7 | ✅ Complete | Dataset analysis tools (analyzer + analysis tab) |
| 8 | ⬜ Next | ML export — X.npy (N,60,16), y.npy, label_map.json, TFLite INT8 |

Phase 8 is blocked until enough samples are collected (target: ≥20 per gesture).

---

## 5. KEY CONSTANTS (`config.py`)

```python
BAUD_RATE            = 115200
QUEUE_MAX_SIZE       = 100          # DO NOT rename — used everywhere as QUEUE_MAX_SIZE
SAMPLE_RATE          = 30           # Hz
WINDOW_SIZE          = 60           # frames per gesture sample
FRAME_PERIOD_MS      = 33           # ms
EMA_ALPHA            = 0.25
FRAME_ID_MAX         = 9999         # max value; modulo = 10000
NUM_FEATURES         = 16
PLOT_HISTORY_FRAMES  = 90           # 3 seconds at 30 Hz
PLOT_TIMER_MS        = 50           # render at 20 Hz, ingest at 30 Hz
DATASET_PATH         = "data/dataset/"
CALIBRATION_PATH     = "data/calibration/"
SKELETON_TUNING_PATH = "data/skeleton_tuning.json"

FEATURE_ORDER = ["R_T","R_I","R_M","R_R","R_L","R_P","R_RL","R_Y",
                 "L_T","L_I","L_M","L_R","L_L","L_P","L_RL","L_Y"]

GESTURE_LABELS = ['HELLO','STOP','YES','NO','THANKYOU',
                  'SORRY','HELP','WATER','PLEASE','MORE']

FINGER_CHANNELS = ['thumb','index','middle','ring','little']
IMU_CHANNELS    = ['pitch','roll','yaw']
```

Never use magic numbers — every constant must come from `config.py`.

---

## 6. BUGS FIXED

### Session bug 1 — Checksum false-drops (`packet_parser.py`)
**Symptom:** ~70% of valid packets rejected as checksum failures.
**Cause:** Python used `int(float * 10)` which truncates toward zero, but firmware
used integer arithmetic equivalent to rounding. E.g. `-25.6 * 10 = -255.9999...` →
`int()` gives `-255`, firmware gives `-256`.
**Fix:** Changed `int(float(f) * 10)` → `round(float(f) * 10)` in `verify_checksum()`.

### Session bug 2 — Frame rate 5 Hz instead of 30 Hz (`hand_skeleton.py`)
**Symptom:** Studio ran at ~5 Hz despite firmware sending 30.4 Hz.
**Cause:** `HandSkeletonWidget._update_skeleton()` was creating 40 new OpenGL sphere
mesh objects on every frame (every 33 ms). Each `GLMeshItem` allocates GPU buffers.
This blocked the Qt main thread ~200 ms per call.
**Fix:** Create all sphere `GLMeshItem` objects once at GL init time; each frame call
only updates `setTransform()` with the new joint position — zero allocation per frame.

**Pipeline now measures 30.2 Hz confirmed by `serial_diagnostic.py`.**

### Other notable bugs fixed across phases
- `serial_thread.py` 10 Hz→30 Hz: switched from `readline()` to `read(in_waiting)` +
  5 ms sleep to drain 64-byte kernel USB-CDC buffer before overflow.
- Phase 3: `TypeError` on calibration wizard — catch `(RuntimeError, TypeError)`.
- Phase 4: Recorder stuck in COMPLETE state — call `recorder.discard()` after save.
- Phase 5: Record button disabled after auto-load — use `QTimer.singleShot(0)` deferred emit.
- Phase 6: Black 3D viewport on Ubuntu — `os.environ` OpenGL fix before all imports.
- Phase 6: Skeleton invisible on startup — `QTimer.singleShot(500)` delays GL item creation.

---

## 7. HOW TO RUN

```bash
cd ~/signgloves/smart_dataset_studio
source ~/signgloves/venv/bin/activate
python3 main.py
```

The app auto-detects the master ESP32-S3 port by USB description ("USB Single Serial"
→ `/dev/ttyACM0`). If it can't detect, it shows a numbered menu to choose manually.

Startup prints "Unknown packet prefix" lines briefly — **this is normal ESP32 boot noise,
do not fix it.**

---

## 8. FOLDER STRUCTURE

```
~/signgloves/
├── CLAUDE.md                          ← this file
├── CURRENT_STATUS.md                  ← READ FIRST every session
├── smart_dataset_studio/
│   ├── main.py                        ← entry point
│   ├── config.py                      ← ALL constants
│   ├── requirements.txt
│   ├── communication/
│   │   ├── serial_thread.py           ← chunk-read serial → frame_queue
│   │   └── packet_parser.py           ← parse + checksum validation
│   ├── processing/
│   │   ├── frame.py                   ← make_raw_frame(), frame dict keys
│   │   ├── filter.py                  ← EMA filter
│   │   ├── calibration.py             ← normalize + profiles
│   │   └── processing_thread.py       ← QThread: filter→normalize→emit
│   ├── ui/
│   │   ├── main_window.py             ← tabbed window; plot_widget, skeleton_widget
│   │   ├── recorder_panel.py
│   │   ├── dataset_panel.py
│   │   ├── calibration_tab.py
│   │   └── style.py                   ← dark theme
│   ├── visualization/
│   │   ├── signal_plot.py             ← PyQtGraph scrolling plots
│   │   └── hand_skeleton.py           ← 3D GL hand renderer
│   ├── recording/
│   │   └── gesture_recorder.py        ← 60-frame state machine
│   ├── dataset/
│   │   ├── dataset_manager.py         ← CSV save/load/count
│   │   └── dataset_analyzer.py        ← Phase 7: stats + outlier detection
│   └── voice/
│       └── voice_listener.py          ← Vosk QThread
├── firmware/
│   ├── master_esp32s3/master_esp32s3.ino
│   └── slave_esp32/slave_esp32.ino
├── docs/                              ← .docx phase documentation
└── venv/
```

Runtime-created (git-ignored):
```
smart_dataset_studio/data/
├── calibration/<profile>/calibration_YYYYMMDD.json
├── dataset/<LABEL>/<profile>_sample_NNN.csv
└── skeleton_tuning.json
```

---

## 9. KEY DESIGN RULES

These are non-negotiable decisions made for specific reasons. Do not change without
understanding the reason.

| Rule | Reason |
|---|---|
| `QUEUE_MAX_SIZE` — do not rename | Used by name throughout the codebase |
| Frame drop policy: discard entire sample | Corrupted windows poison BiLSTM training |
| Padding policy: repeat final frame | Never zero-pad — zeros are not real gesture data |
| Filter THEN normalize | Filtering on 0–1 causes clipping artifacts |
| IMU passed through raw degrees | Already in universal units, no scaling needed |
| Connect signals BEFORE `QThread.start()` | Prevents race condition on first frame |
| `QApplication` not `QCoreApplication` | Required for any window/widget |
| `apply_style(app)` before any widget | Style must be set before widget construction |
| Catch `(RuntimeError, TypeError)` on PyQt5 disconnect | Version differences across installs |
| Calibration stored per-profile + date | Multi-user support |
| Dataset filenames: `<profile>_sample_NNN.csv` | Per-person traceability |
| ADC pins GPIO 1–5 (ADC1 only) on ESP32-S3 | ADC2 conflicts with WiFi/ESP-NOW |
| Slave MAC via `esp_read_mac()` | `WiFi.macAddress()` returns `00:00:00:00:00:00` |
| `HandSkeletonWidget._gl_ready` guard | GL context not ready during `__init__` |
| Left hand IMU = 0.0 always | Only one IMU available; correct, not a bug |

---

## 10. SIGNAL MAP (complete, Phase 7)

```
processing_thread.raw_frame_ready     → calibration_tab.on_raw_frame
processing_thread.frame_ready         → window.on_frame_ready
processing_thread.frame_ready         → recorder.on_frame
processing_thread.frame_ready         → window.plot_widget.on_frame
processing_thread.frame_ready         → window.skeleton_widget.on_frame
processing_thread.frame_drop_detected → recorder.on_frame_drop
processing_thread.status_message      → window.on_status_message
calibration_tab.calibration_updated   → processing_thread.update_calibration
calibration_tab.calibration_updated   → recorder_panel.on_calibration_done
calibration_tab.calibration_updated   → [lambda: update dataset_manager.profile_name]
recorder_panel.recording_started      → processing_thread.set_recording(True)
recorder_panel.recording_started      → processing_thread.reset_filters
recorder_panel.recording_started      → window.plot_widget.on_recording_started
recorder_panel.recording_stopped      → processing_thread.set_recording(False)
recorder_panel.recording_stopped      → window.plot_widget.on_recording_stopped
recorder_panel.sample_saved           → dataset_panel.refresh
recorder_panel.sample_saved           → analysis_tab.refresh  (if not None)
recorder.progress_updated             → window.plot_widget.on_recording_progress
voice_listener.command_detected       → recorder_panel.on_voice_command
voice_listener.error_occurred         → recorder_panel.on_voice_error
```

---

## 11. CODING RULES FOR THIS PROJECT

1. `python3` not `python`
2. All constants from `config.py` — no magic numbers
3. Check `frame.py` for exact dict key names before accessing frame data
4. Never share mutable state between threads
5. `raw_frame_ready` = raw ADC values; `frame_ready` = processed 0.0–1.0
6. `update_calibration()` is GIL-safe (called across threads)
7. After recording save: always call `recorder.discard()` to reset the state machine
8. `CalibrationTab` emits `calibration_updated` via `QTimer.singleShot(0)` (deferred)
9. Explain reasoning — Anoop wants to understand, not just copy-paste code
10. No comments unless the WHY is non-obvious; no docstrings on obvious methods
