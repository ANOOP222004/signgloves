# ui/prediction_tab.py
# Phase 10 — Live Prediction Tab for Smart Glove Dataset Studio
#
# Receives processed frames from the existing ProcessingThread
# (same signal as the dashboard uses — no separate serial connection).
# Runs RestGate + StabilityFilter + TFLite inference inline.
# Speaks predictions aloud via pyttsx3 (optional, falls back silently).
#
# Wire in main.py (one line, after all other signal connections):
#   processing_thread.frame_ready.connect(window.prediction_tab.on_frame_ready)

import os
import queue
import threading
import time
from collections import deque
from datetime import datetime

import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QFileDialog, QProgressBar, QFrame,
)

# ── TFLite (same import order as live_inference.py) ────────────
try:
    from tensorflow.lite.python.interpreter import Interpreter as _TFLiteInterpreter
except ImportError:
    try:
        from tflite_runtime.interpreter import Interpreter as _TFLiteInterpreter
    except ImportError:
        _TFLiteInterpreter = None

# ── pyttsx3 (optional — graceful fallback if not installed) ────
try:
    import pyttsx3 as _pyttsx3
    _SPEECH_AVAILABLE = True
except ImportError:
    _SPEECH_AVAILABLE = False

from config import (
    WINDOW_SIZE, GESTURE_LABELS,
    FINGER_CHANNELS, IMU_CHANNELS,
)
from processing.frame import frame_to_feature_vector
from ui.style import (
    BG_DARK, BG_PANEL, BG_INPUT, ACCENT, ACCENT_DIM,
    SUCCESS, STOP_COLOR, DANGER, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_ACCENT, BORDER, SUCCESS_DIM, SUCCESS_BORDER,
    STOP_DIM, STOP_BORDER,
)

# ════════════════════════════════════════════════════════════════
# INFERENCE CONSTANTS
# ════════════════════════════════════════════════════════════════
V6_FEATURE_IDX       = [0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14]
V6_NUM_FEATURES      = 14
FINGER_ONLY_IDX      = [0, 1, 2, 3, 4, 8, 9, 10, 11, 12]

STRIDE               = 5
CONFIDENCE_THRESHOLD = 0.80
REST_CAPTURE_FRAMES  = 75      # 2.5s × 30Hz
REST_MARGIN          = 3.0
GATE_HYSTERESIS      = 0.6
DEVIATION_SMOOTH     = 8
STABILITY_COUNT      = 3
COMMIT_COOLDOWN_SEC  = 1.2

# Pronunciation map — maps raw gesture labels to natural spoken phrases.
# pyttsx3 mispronounces run-together words like THANKYOU as one unknown word.
# Add any new signs here if pronunciation is off.
_SPEECH_MAP = {
    'THANKYOU': 'thank you',
    'HELLO':    'hello',
    'YES':      'yes',
    'NO':       'no',
    'SORRY':    'sorry',
    'HELP':     'help',
    'WATER':    'water',
    'PLEASE':   'please',
    'STUDY':    'study',
    'FRIENDS':  'friends',
    'STOP':     'stop',
    'MORE':     'more',
}

MAX_HISTORY          = 50

# States
_STOPPED    = "STOPPED"
_CALIBRATING = "CALIBRATING"
_RUNNING    = "RUNNING"


# ── RestGate ───────────────────────────────────────────────────
class _RestGate:
    def __init__(self):
        self.rest_pose = None
        self.open_th   = None
        self.close_th  = None
        self.is_open   = False
        self._hist     = deque(maxlen=DEVIATION_SMOOTH)

    def calibrate(self, frames):
        arr  = np.array(frames)
        self.rest_pose = arr.mean(axis=0)
        devs = np.abs(arr - self.rest_pose).mean(axis=1)
        nf   = float(devs.max())
        self.open_th  = max(nf * REST_MARGIN, 0.02)
        self.close_th = self.open_th * GATE_HYSTERESIS
        return nf

    def update(self, finger_vec):
        raw = float(np.abs(np.array(finger_vec) - self.rest_pose).mean())
        self._hist.append(raw)
        sm = float(np.mean(self._hist))
        if self.is_open:
            if sm < self.close_th:
                self.is_open = False
        else:
            if sm > self.open_th:
                self.is_open = True
        return self.is_open, sm


# ── StabilityFilter ────────────────────────────────────────────
class _StabilityFilter:
    def __init__(self):
        self.history   = deque(maxlen=STABILITY_COUNT)
        self.committed = None

    def update(self, label):
        self.history.append(label)
        if (len(self.history) == STABILITY_COUNT
                and len(set(self.history)) == 1):
            c = self.history[0]
            if c != self.committed:
                self.committed = c
                return c
        return None

    def reset(self):
        self.history.clear()
        self.committed = None


# ── Speech worker (daemon thread) ──────────────────────────────
class _SpeechWorker(threading.Thread):
    """
    Speaks committed sign labels aloud.
    Runs in a daemon thread so pyttsx3's blocking runAndWait()
    never stalls the Qt main thread or the UI.
    If the queue backs up (fast signing), skips stale items and
    only speaks the most recent one.
    """
    def __init__(self):
        super().__init__(daemon=True)
        self._q = queue.Queue()

    def speak(self, text: str):
        self._q.put(text)

    def stop(self):
        self._q.put(None)

    def run(self):
        if not _SPEECH_AVAILABLE:
            return
        try:
            engine = _pyttsx3.init()
            engine.setProperty('rate', 140)   # slightly slower = clearer
            engine.setProperty('volume', 1.0)
        except Exception:
            return
        while True:
            text = self._q.get()
            if text is None:
                break
            # Drain queue — speak only the latest if multiple queued
            while not self._q.empty():
                try:
                    text = self._q.get_nowait()
                except queue.Empty:
                    break
            if text is None:
                break
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════
# PredictionTab
# ══════════════════════════════════════════════════════════════════
class PredictionTab(QWidget):
    """
    Tab 6 — Live gesture recognition with voice output.

    The tab is passive by default (ignores incoming frames).
    Click START INFERENCE to activate. The first 2.5 seconds
    captures the rest pose baseline; then live prediction begins.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state         = _STOPPED
        self._model_path    = "model_v6.tflite"
        self._interpreter   = None
        self._inp           = None
        self._out           = None
        self._window        = deque(maxlen=WINDOW_SIZE)
        self._gate          = _RestGate()
        self._stab          = _StabilityFilter()
        self._speech        = _SpeechWorker()
        self._speech.start()
        self._rest_buf      = []
        self._stride_ctr    = 0
        self._prev_gate     = False
        self._cooldown_until = 0.0
        self._history_count  = 0

        # Timer used during REST_CALIBRATING to show countdown
        self._calib_timer = QTimer()
        self._calib_timer.setInterval(100)
        self._calib_timer.timeout.connect(self._update_calib_display)
        self._calib_start = 0.0

        self._build_ui()

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addWidget(self._build_control_bar())

        body = QHBoxLayout()
        body.setSpacing(8)
        body.addWidget(self._build_prediction_panel(), stretch=2)
        body.addWidget(self._build_history_panel(),    stretch=1)
        root.addLayout(body, stretch=1)

    def _build_control_bar(self) -> QGroupBox:
        g  = QGroupBox("INFERENCE_CONTROL")
        hl = QHBoxLayout(g)
        hl.setSpacing(10)

        # Model path display
        path_lbl = QLabel("MODEL:")
        path_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; letter-spacing:1px;")
        hl.addWidget(path_lbl)

        self._model_path_lbl = QLabel(os.path.basename(self._model_path))
        self._model_path_lbl.setStyleSheet(
            f"color: {TEXT_ACCENT}; font-family: 'Courier New'; font-size: 11px;"
        )
        hl.addWidget(self._model_path_lbl, stretch=1)

        browse_btn = QPushButton("BROWSE")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_model)
        hl.addWidget(browse_btn)

        hl.addSpacing(20)

        # Start button (green style)
        self._start_btn = QPushButton("▶  START INFERENCE")
        self._start_btn.setObjectName("save_btn")
        self._start_btn.setFixedWidth(180)
        self._start_btn.clicked.connect(self._start_inference)
        hl.addWidget(self._start_btn)

        # Stop button (amber style)
        self._stop_btn = QPushButton("■  STOP")
        self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.setFixedWidth(100)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_inference)
        hl.addWidget(self._stop_btn)

        hl.addSpacing(20)

        # Voice toggle
        self._voice_chk = QCheckBox("🔊  VOICE")
        self._voice_chk.setChecked(_SPEECH_AVAILABLE)
        self._voice_chk.setEnabled(_SPEECH_AVAILABLE)
        if not _SPEECH_AVAILABLE:
            self._voice_chk.setToolTip(
                "Install pyttsx3:  pip install pyttsx3\n"
                "and espeak:       sudo apt install espeak-ng"
            )
        hl.addWidget(self._voice_chk)

        # Status indicator (right-aligned)
        hl.addStretch()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 18px;")
        hl.addWidget(self._status_dot)
        self._status_lbl = QLabel("STOPPED")
        self._status_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; "
            f"letter-spacing: 1.5px; font-weight: 700;"
        )
        hl.addWidget(self._status_lbl)

        return g

    def _build_prediction_panel(self) -> QGroupBox:
        g  = QGroupBox("LIVE_PREDICTION")
        vl = QVBoxLayout(g)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        # Gate state pill (small label at top)
        self._gate_lbl = QLabel("[ ●  IDLE ]")
        self._gate_lbl.setAlignment(Qt.AlignCenter)
        self._gate_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; "
            f"letter-spacing: 2px; font-weight: 700;"
        )
        vl.addWidget(self._gate_lbl)

        # ── BIG prediction label ──────────────────────────────
        self._pred_lbl = QLabel("—")
        self._pred_lbl.setAlignment(Qt.AlignCenter)
        font = QFont("Courier New", 72, QFont.Bold)
        self._pred_lbl.setFont(font)
        self._pred_lbl.setMinimumHeight(140)
        self._pred_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        vl.addWidget(self._pred_lbl, stretch=1)

        # Confidence bar + percentage
        conf_row = QHBoxLayout()
        self._conf_bar = QProgressBar()
        self._conf_bar.setRange(0, 100)
        self._conf_bar.setValue(0)
        self._conf_bar.setTextVisible(False)
        self._conf_bar.setFixedHeight(12)
        self._conf_bar.setStyleSheet(self._conf_bar_style(0))
        conf_row.addWidget(self._conf_bar, stretch=1)

        self._conf_pct_lbl = QLabel("  0%")
        self._conf_pct_lbl.setFixedWidth(48)
        self._conf_pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._conf_pct_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: 700;"
        )
        conf_row.addWidget(self._conf_pct_lbl)
        vl.addLayout(conf_row)

        # Top-3 runner-up hints
        self._top3_lbl = QLabel("")
        self._top3_lbl.setAlignment(Qt.AlignCenter)
        self._top3_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; letter-spacing: 0.5px;"
        )
        vl.addWidget(self._top3_lbl)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {BORDER};")
        line.setFixedHeight(1)
        vl.addWidget(line)

        # Deviation meter (small, bottom)
        dev_row = QHBoxLayout()
        dev_lbl = QLabel("DEVIATION:")
        dev_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 9px; letter-spacing:1px;")
        dev_row.addWidget(dev_lbl)
        self._dev_lbl = QLabel("0.000")
        self._dev_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-family: 'Courier New'; font-size: 10px;"
        )
        dev_row.addWidget(self._dev_lbl)
        dev_row.addStretch()
        self._thresh_lbl = QLabel("threshold: —")
        self._thresh_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 9px;")
        dev_row.addWidget(self._thresh_lbl)
        vl.addLayout(dev_row)

        return g

    def _build_history_panel(self) -> QGroupBox:
        g  = QGroupBox("PREDICTION_HISTORY")
        vl = QVBoxLayout(g)
        vl.setSpacing(6)

        # Column headers
        hdr = QLabel("  #    SIGN          CONF    TIME")
        hdr.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 9px; "
            f"letter-spacing: 1px; font-family: 'Courier New';"
        )
        vl.addWidget(hdr)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {BORDER};")
        line.setFixedHeight(1)
        vl.addWidget(line)

        self._history_list = QListWidget()
        self._history_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {BG_INPUT};
                border: 1px solid {BORDER};
                font-family: 'Courier New';
                font-size: 11px;
                color: {TEXT_PRIMARY};
            }}
            QListWidget::item {{
                padding: 4px 6px;
                border-bottom: 1px solid {BORDER};
            }}
            QListWidget::item:selected {{
                background-color: {BG_INPUT};
                color: {ACCENT};
            }}
        """)
        vl.addWidget(self._history_list, stretch=1)

        clear_btn = QPushButton("CLEAR HISTORY")
        clear_btn.setFixedHeight(28)
        clear_btn.clicked.connect(self._clear_history)
        vl.addWidget(clear_btn)

        return g

    # ── Style helpers ────────────────────────────────────────────

    def _conf_bar_style(self, pct: int) -> str:
        if pct >= 85:
            chunk_color = SUCCESS
        elif pct >= 70:
            chunk_color = ACCENT
        else:
            chunk_color = STOP_COLOR
        return f"""
            QProgressBar {{
                background-color: {BG_INPUT};
                border: 1px solid {BORDER};
                border-radius: 0px;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_color};
            }}
        """

    def _pred_label_color(self, conf: float) -> str:
        if conf >= 0.85:
            return SUCCESS
        elif conf >= 0.70:
            return ACCENT
        else:
            return STOP_COLOR

    # ── Control actions ──────────────────────────────────────────

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select TFLite model", ".", "TFLite models (*.tflite)"
        )
        if path:
            self._model_path = path
            self._model_path_lbl.setText(os.path.basename(path))

    def _start_inference(self):
        if _TFLiteInterpreter is None:
            self._set_status("NO TFLITE", DANGER)
            return

        if not os.path.exists(self._model_path):
            self._set_status("MODEL NOT FOUND", DANGER)
            return

        # Load model
        try:
            self._interpreter = _TFLiteInterpreter(model_path=self._model_path)
            self._interpreter.allocate_tensors()
            self._inp = self._interpreter.get_input_details()
            self._out = self._interpreter.get_output_details()
            expected = self._inp[0]['shape']
            if expected[2] != V6_NUM_FEATURES:
                self._set_status(f"SHAPE ERR: {expected}", DANGER)
                self._interpreter = None
                return
        except Exception as e:
            self._set_status(f"LOAD ERR", DANGER)
            self._interpreter = None
            return

        # Reset all state
        self._gate          = _RestGate()
        self._stab          = _StabilityFilter()
        self._window        = deque(maxlen=WINDOW_SIZE)
        self._rest_buf      = []
        self._stride_ctr    = 0
        self._prev_gate     = False
        self._cooldown_until = 0.0

        self._state     = _CALIBRATING
        self._calib_start = time.monotonic()

        # Buttons
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

        # Reset displays
        self._pred_lbl.setText("—")
        self._pred_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._conf_bar.setValue(0)
        self._conf_bar.setStyleSheet(self._conf_bar_style(0))
        self._conf_pct_lbl.setText("  0%")
        self._top3_lbl.setText("")
        self._gate_lbl.setText("[ ●  CALIBRATING... ]")
        self._gate_lbl.setStyleSheet(
            f"color: {STOP_COLOR}; font-size: 11px; letter-spacing: 2px; font-weight: 700;"
        )

        self._set_status("CALIBRATING", STOP_COLOR)
        self._calib_timer.start()

    def _stop_inference(self):
        self._state = _STOPPED
        self._calib_timer.stop()
        self._interpreter = None

        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

        self._pred_lbl.setText("—")
        self._pred_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._conf_bar.setValue(0)
        self._conf_bar.setStyleSheet(self._conf_bar_style(0))
        self._conf_pct_lbl.setText("  0%")
        self._top3_lbl.setText("")
        self._gate_lbl.setText("[ ●  IDLE ]")
        self._gate_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; letter-spacing: 2px; font-weight: 700;"
        )
        self._dev_lbl.setText("0.000")
        self._thresh_lbl.setText("threshold: —")
        self._set_status("STOPPED", TEXT_SECONDARY)

    def _update_calib_display(self):
        elapsed = time.monotonic() - self._calib_start
        remain  = max(0.0, (REST_CAPTURE_FRAMES / 30.0) - elapsed)
        self._gate_lbl.setText(
            f"[ ●  HOLD STILL — CALIBRATING...  {remain:.1f}s ]"
        )

    def _clear_history(self):
        self._history_list.clear()
        self._history_count = 0

    def _set_status(self, text: str, color: str):
        self._status_dot.setStyleSheet(f"color: {color}; font-size: 18px;")
        self._status_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; "
            f"letter-spacing: 1.5px; font-weight: 700;"
        )
        self._status_lbl.setText(text)

    # ── Main inference slot ──────────────────────────────────────

    def on_frame_ready(self, processed_frame: dict):
        """
        Connected to processing_thread.frame_ready in main.py.
        Receives the same already-filtered + calibrated frames
        that the rest of the app uses — no separate serial connection.
        """
        if self._state == _STOPPED or self._interpreter is None:
            return

        # Build 16-element feature vector and extract fingers
        full_vec   = np.array(frame_to_feature_vector(processed_frame))
        finger_vec = full_vec[FINGER_ONLY_IDX]

        # ── REST CALIBRATION PHASE ────────────────────────────
        if self._state == _CALIBRATING:
            self._rest_buf.append(finger_vec)
            if len(self._rest_buf) >= REST_CAPTURE_FRAMES:
                noise = self._gate.calibrate(self._rest_buf)
                self._state = _RUNNING
                self._calib_timer.stop()
                self._gate_lbl.setText("[ ●  IDLE ]")
                self._gate_lbl.setStyleSheet(
                    f"color: {TEXT_SECONDARY}; font-size: 11px; "
                    f"letter-spacing: 2px; font-weight: 700;"
                )
                self._thresh_lbl.setText(
                    f"threshold: {self._gate.open_th:.3f}"
                )
                self._set_status("RUNNING", SUCCESS)
            return

        # ── RUNNING PHASE ─────────────────────────────────────
        self._window.append(processed_frame)
        gate_open, deviation = self._gate.update(finger_vec)

        # Cooldown overrides gate
        now         = time.monotonic()
        in_cooldown = now < self._cooldown_until
        if in_cooldown:
            gate_open = False

        # Gate just closed → reset stability
        if self._prev_gate and not gate_open:
            self._stab.reset()
        self._prev_gate = gate_open

        # Update gate display
        self._dev_lbl.setText(f"{deviation:.3f}")
        if in_cooldown:
            remain = self._cooldown_until - now
            self._gate_lbl.setText(f"[ ●  COOLDOWN  {remain:.1f}s ]")
            self._gate_lbl.setStyleSheet(
                f"color: {STOP_COLOR}; font-size: 11px; "
                f"letter-spacing: 2px; font-weight: 700;"
            )
        elif gate_open:
            self._gate_lbl.setText("[ ●  ACTIVE ]")
            self._gate_lbl.setStyleSheet(
                f"color: {ACCENT}; font-size: 11px; "
                f"letter-spacing: 2px; font-weight: 700;"
            )
        else:
            self._gate_lbl.setText("[ ●  IDLE ]")
            self._gate_lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 11px; "
                f"letter-spacing: 2px; font-weight: 700;"
            )

        if not gate_open:
            return

        # Stride gate
        self._stride_ctr += 1
        if len(self._window) < WINDOW_SIZE or self._stride_ctr < STRIDE:
            return
        self._stride_ctr = 0

        # ── Run TFLite inference ──────────────────────────────
        X = np.array(
            [frame_to_feature_vector(f) for f in self._window],
            dtype=np.float32
        )
        X    = X[:, V6_FEATURE_IDX]
        mean = X.mean(axis=0, keepdims=True)
        std  = X.std(axis=0,  keepdims=True)
        X    = (X - mean) / (std + 1e-6)
        X    = np.expand_dims(X, axis=0).astype(np.float32)

        self._interpreter.set_tensor(self._inp[0]['index'], X)
        self._interpreter.invoke()
        probs   = self._interpreter.get_tensor(self._out[0]['index'])[0]
        top_idx = int(np.argmax(probs))
        conf    = float(probs[top_idx])
        label   = GESTURE_LABELS[top_idx]

        # Confidence gate
        if conf < CONFIDENCE_THRESHOLD:
            return

        # Stability filter
        committed = self._stab.update(label)
        if committed is None:
            return

        # ── COMMITTED — update all displays ──────────────────
        pct   = int(conf * 100)
        color = self._pred_label_color(conf)

        self._pred_lbl.setText(committed)
        self._pred_lbl.setStyleSheet(f"color: {color}; font-size: 72px; font-weight: bold;")

        self._conf_bar.setValue(pct)
        self._conf_bar.setStyleSheet(self._conf_bar_style(pct))
        self._conf_pct_lbl.setText(f"{pct:3d}%")
        self._conf_pct_lbl.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 700;"
        )

        # Top-3 runner-up hints
        top3_idx = np.argsort(probs)[::-1][:3]
        top3_str = "   ".join(
            f"{GESTURE_LABELS[i]}: {probs[i]*100:.0f}%"
            for i in top3_idx
        )
        self._top3_lbl.setText(top3_str)

        # ── History panel ─────────────────────────────────────
        self._history_count += 1
        ts      = datetime.now().strftime("%H:%M:%S")
        bar_len = min(12, int(conf * 12))
        bar_str = "█" * bar_len + "░" * (12 - bar_len)
        row_txt = (
            f"  {self._history_count:>3}   "
            f"{committed:<12}  {pct:3d}%  "
            f"{bar_str}  {ts}"
        )
        item = QListWidgetItem(row_txt)
        item.setForeground(
            __import__('PyQt5.QtGui', fromlist=['QColor']).QColor(color)
        )
        # Insert at top so newest is first
        self._history_list.insertItem(0, item)
        # Keep history bounded
        while self._history_list.count() > MAX_HISTORY:
            self._history_list.takeItem(self._history_list.count() - 1)

        # ── Cooldown ──────────────────────────────────────────
        self._cooldown_until = now + COMMIT_COOLDOWN_SEC
        self._stab.reset()
        self._stride_ctr = 0

        # ── Voice output ──────────────────────────────────────
        if self._voice_chk.isChecked() and _SPEECH_AVAILABLE:
            self._speech.speak(_SPEECH_MAP.get(committed, committed.lower()))

    def closeEvent(self, event):
        self._speech.stop()
        super().closeEvent(event)
