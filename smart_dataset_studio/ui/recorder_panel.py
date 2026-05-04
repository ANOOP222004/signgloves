# ui/recorder_panel.py
#
# RecorderPanel — recording controls for the Gesture Recorder.
#
# What this does:
#   - Provides UI controls for recording gesture samples:
#       Label selector (dropdown of GESTURE_LABELS)
#       Record / Stop / Save / Discard buttons
#       Live progress display: "Frames: 12 / 60"
#       Microphone toggle button (🎤 Voice OFF / 🎤 Voice ON)
#   - Voice commands mirror all four buttons — user picks whichever is convenient
#   - Coordinates between GestureRecorder, VoiceListener, and DatasetManager
#   - Notifies DatasetPanel to refresh after every successful save
#
# Voice command design:
#   VoiceListener runs on a background QThread and emits command_detected(word).
#   on_voice_command() routes each word to the existing button handler.
#   Voice and buttons do exactly the same thing — no duplicate logic anywhere.
#
# Phase 5 (tabbed UI) addition:
#   Record button starts DISABLED — enabled only after CalibrationTab emits
#   calibration_updated. This prevents recording before calibration is done.
#   on_calibration_done() is the slot that enables the Record button.
#
# Signal connections made in main.py (not here):
#   processing_thread.frame_ready.connect(recorder.on_frame)
#   processing_thread.frame_drop_detected.connect(recorder.on_frame_drop)
#   voice_listener.command_detected.connect(recorder_panel.on_voice_command)
#   voice_listener.error_occurred.connect(recorder_panel.on_voice_error)
#   cal_tab.calibration_updated.connect(recorder_panel.on_calibration_done)

from PyQt5.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont

from recording.gesture_recorder import GestureRecorder
from dataset.dataset_manager import DatasetManager
from voice.voice_listener import VoiceListener
from config import GESTURE_LABELS, WINDOW_SIZE, SPEED_TAGS, SPEED_ZONES, DEFAULT_SPEED


class RecorderPanel(QGroupBox):
    """
    Recording controls panel with voice command support.

    Inherits from QGroupBox so it can be added directly to the
    MainWindow layout as a drop-in replacement for the stub panel.

    Signals:
        sample_saved(str):      emitted after DatasetManager.save_sample() succeeds.
                                Carries the label name. DatasetPanel.refresh() listens.
        recording_started():    emitted when recording begins.
                                main.py connects to processing_thread.set_recording(True)
                                and processing_thread.reset_filters()
        recording_stopped():    emitted when recording ends (save, discard, or drop).
                                main.py connects to processing_thread.set_recording(False)

    Usage (from main.py):
        recorder_panel = RecorderPanel(recorder, dataset_manager, voice_listener)
        recorder_panel.sample_saved.connect(dataset_panel.refresh)
        recorder_panel.recording_started.connect(lambda: processing_thread.set_recording(True))
        recorder_panel.recording_started.connect(processing_thread.reset_filters)
        recorder_panel.recording_stopped.connect(lambda: processing_thread.set_recording(False))
        voice_listener.command_detected.connect(recorder_panel.on_voice_command)
        voice_listener.error_occurred.connect(recorder_panel.on_voice_error)
    """

    sample_saved      = pyqtSignal(str)
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal()

    def __init__(self, recorder: GestureRecorder,
                 dataset_manager: DatasetManager,
                 voice_listener: VoiceListener):
        """
        Args:
            recorder:        GestureRecorder state machine instance
            dataset_manager: shared DatasetManager for saving samples
            voice_listener:  VoiceListener thread instance (not yet started)
        """
        super().__init__("Recorder")

        self.recorder       = recorder
        self.dm             = dataset_manager
        self.voice_listener = voice_listener

        # Completed frame buffer — held between capture_complete and Save/Discard.
        # None when recorder is not in COMPLETE state.
        self._pending_frames = None

        # Currently selected recording speed — saved into every filename.
        self._selected_speed = DEFAULT_SPEED

        # Tracks whether the VoiceListener thread is currently running.
        self._voice_active = False

        # Wire GestureRecorder signals to our slots
        self.recorder.progress_updated.connect(self._on_progress)
        self.recorder.capture_complete.connect(self._on_capture_complete)
        self.recorder.capture_failed.connect(self._on_capture_failed)

        self._build_ui()
        self._set_state_idle()

        # Auto-start the voice listener so the user doesn't have to remember
        # to click 🎤 every session. QTimer.singleShot(0, ...) defers the
        # toggle until the event loop's first tick — by then main.py has
        # finished wiring command_detected to the recorder panel, the main
        # window (tab nav) and the calibration tab.
        QTimer.singleShot(0, self._on_voice_toggle)

        # Record button starts disabled — CalibrationTab enables it
        # after calibration_updated is emitted.
        self._record_btn.setEnabled(False)
        self._status_label.setText("Go to the Calibration tab first.")
        self._status_label.setStyleSheet("color: #cc6600;")

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self):
        """
        Build the panel layout.

        Structure:
            QGroupBox ("Recorder")
            └── QVBoxLayout
                ├── Label row:        "Label:" + QComboBox
                ├── Speed selector:   SLOW / MEDIUM / FAST buttons + zone info
                ├── Voice toggle:     🎤 Voice OFF / ON button
                ├── Progress label:   "Ready" / "Frames: 12 / 60"
                ├── Record button
                ├── Stop button       (hidden until CAPTURING)
                ├── Save/Discard row  (hidden until COMPLETE)
                └── Status label:     result of last action
        """
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Label selector ────────────────────────────────────────────
        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("Label:"))

        self._label_combo = QComboBox()
        for gesture in GESTURE_LABELS:
            self._label_combo.addItem(gesture)
        self._label_combo.setMinimumHeight(28)
        label_row.addWidget(self._label_combo)
        layout.addLayout(label_row)

        # ── Speed selector ────────────────────────────────────────────
        # Three toggle buttons (SLOW / MEDIUM / FAST). Only one active at a
        # time — like a radio group but styled to match the existing theme.
        # The selected speed is embedded in the filename on every save.
        speed_group = QGroupBox("Recording Speed")
        speed_vbox  = QVBoxLayout(speed_group)
        speed_vbox.setSpacing(4)

        speed_btn_row = QHBoxLayout()
        speed_btn_row.setSpacing(4)
        self._speed_btns = {}
        for speed in SPEED_TAGS:
            btn = QPushButton(speed.upper())
            btn.setCheckable(True)
            btn.setMinimumHeight(28)
            btn.setFont(QFont("Courier", 9, QFont.Bold))
            btn.clicked.connect(lambda _checked, s=speed: self._on_speed_selected(s))
            self._speed_btns[speed] = btn
            speed_btn_row.addWidget(btn)
        speed_vbox.addLayout(speed_btn_row)

        # Small text showing frame zone ranges for the selected speed
        self._zone_label = QLabel()
        self._zone_label.setAlignment(Qt.AlignCenter)
        self._zone_label.setFont(QFont("Courier", 8))
        self._zone_label.setStyleSheet("color: #5A6A5A;")
        speed_vbox.addWidget(self._zone_label)

        layout.addWidget(speed_group)

        # Set default speed visually
        self._on_speed_selected(DEFAULT_SPEED)

        # ── Voice toggle button ───────────────────────────────────────
        # Clicking starts or stops the VoiceListener background thread.
        # Colour and label change to show current state clearly.
        self._voice_btn = QPushButton("🎤  Voice OFF")
        self._voice_btn.setMinimumHeight(30)
        self._voice_btn.setFont(QFont("Arial", 9))
        self._voice_btn.setToolTip(
            "Enable voice commands:\n"
            "  'Start'   → begin recording\n"
            "  'Stop'    → stop early\n"
            "  'Save'    → save sample\n"
            "  'Discard' → discard sample"
        )
        self._voice_btn.clicked.connect(self._on_voice_toggle)
        self._set_voice_btn_off()
        layout.addWidget(self._voice_btn)

        # ── Progress display ──────────────────────────────────────────
        self._progress_label = QLabel("Ready")
        self._progress_label.setAlignment(Qt.AlignCenter)
        self._progress_label.setFont(QFont("Courier", 10))
        self._progress_label.setMinimumHeight(24)
        layout.addWidget(self._progress_label)

        # ── Record button ─────────────────────────────────────────────
        self._record_btn = QPushButton("⏺  Record")
        self._record_btn.setMinimumHeight(36)
        self._record_btn.setFont(QFont("Arial", 10, QFont.Bold))
        self._record_btn.setObjectName("record_btn")   # CSS: QPushButton#record_btn
        self._record_btn.clicked.connect(self._on_record_clicked)
        layout.addWidget(self._record_btn)

        # ── Stop button ───────────────────────────────────────────────
        # Visible only while CAPTURING
        self._stop_btn = QPushButton("⏹  Stop")
        self._stop_btn.setMinimumHeight(30)
        self._stop_btn.setObjectName("stop_btn")       # CSS: QPushButton#stop_btn
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn.setVisible(False)
        layout.addWidget(self._stop_btn)

        # ── Save / Discard row ────────────────────────────────────────
        # Visible only after capture_complete
        save_discard_row = QHBoxLayout()

        self._save_btn = QPushButton("✔  Save")
        self._save_btn.setMinimumHeight(30)
        self._save_btn.setObjectName("save_btn")       # CSS: QPushButton#save_btn
        self._save_btn.setFont(QFont("Arial", 9, QFont.Bold))
        self._save_btn.clicked.connect(self._on_save_clicked)

        self._discard_btn = QPushButton("✖  Discard")
        self._discard_btn.setMinimumHeight(30)
        self._discard_btn.setObjectName("discard_btn") # CSS: QPushButton#discard_btn
        self._discard_btn.clicked.connect(self._on_discard_clicked)

        save_discard_row.addWidget(self._save_btn)
        save_discard_row.addWidget(self._discard_btn)

        self._save_discard_widget = QGroupBox()
        self._save_discard_widget.setFlat(True)
        self._save_discard_widget.setLayout(save_discard_row)
        self._save_discard_widget.setVisible(False)
        layout.addWidget(self._save_discard_widget)

        # ── Status label ──────────────────────────────────────────────
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setFont(QFont("Arial", 8))
        self._status_label.setStyleSheet("color: gray;")
        layout.addWidget(self._status_label)

        layout.addStretch()

    # ── Speed selector ───────────────────────────────────────────────

    def _on_speed_selected(self, speed: str):
        """Update selected speed, highlight the active button, update zone text."""
        self._selected_speed = speed

        # Highlight active button; dim others
        _active_css = (
            "QPushButton { background-color: #1A3A2A; color: #00E676; "
            "font-weight: bold; border: 1px solid #00E676; border-radius: 4px; }"
        )
        _inactive_css = ""
        for s, btn in self._speed_btns.items():
            btn.setChecked(s == speed)
            btn.setStyleSheet(_active_css if s == speed else _inactive_css)

        # Update zone info text below the buttons
        zones = SPEED_ZONES[speed]
        s_s, s_e = zones['start']
        t_s, t_e = zones['transition']
        e_s, e_e = zones['end']
        self._zone_label.setText(
            f"Start: {s_s}-{s_e}  |  Transition: {t_s}-{t_e}  |  End: {e_s}-{e_e}"
        )

    # ── Voice toggle ──────────────────────────────────────────────────

    def _on_voice_toggle(self):
        """
        Called when the 🎤 button is clicked.

        Starts or stops the VoiceListener thread depending on current state.
        The VoiceListener is a QThread — start() begins listening,
        stop() + wait() shuts it down cleanly before returning.
        """
        if not self._voice_active:
            self.voice_listener.start()
            self._voice_active = True
            self._set_voice_btn_on()
            self._status_label.setText("Voice active — say 'Start' to record")
            self._status_label.setStyleSheet("color: #006600;")
        else:
            self.voice_listener.stop()
            self.voice_listener.wait()   # block until thread exits cleanly
            self._voice_active = False
            self._set_voice_btn_off()
            self._status_label.setText("Voice disabled.")
            self._status_label.setStyleSheet("color: gray;")

    def _set_voice_btn_on(self):
        """Style the voice button to show it is active."""
        self._voice_btn.setText("🎤  Voice ON")
        self._voice_btn.setStyleSheet(
            "QPushButton { background-color: #004D40; color: #00BFA5; "
            "font-weight: bold; border: 1px solid #00BFA5; border-radius: 5px; }"
        )

    def _set_voice_btn_off(self):
        """Style the voice button to show it is inactive."""
        self._voice_btn.setText("🎤  Voice OFF")
        self._voice_btn.setStyleSheet("")

    # ── Voice command public slots ────────────────────────────────────

    def on_voice_command(self, command: str):
        """
        Slot connected to VoiceListener.command_detected signal (wired in main.py).

        Routes each recognised word to the corresponding button handler.
        State guards prevent commands from firing in the wrong state —
        e.g. saying 'save' when nothing has been recorded is silently ignored.

        Why state guards here rather than inside the handlers?
            The button handlers are already protected (e.g. _on_save_clicked
            returns early if _pending_frames is None), but explicit guards here
            make the intent clear: voice commands are context-sensitive,
            and the context is the recorder's current state.

        Args:
            command: lowercase word from VoiceListener, one of:
                     "start", "stop", "save", "discard"
        """
        if command == "start":
            if self.recorder.is_idle():
                self._on_record_clicked()

        elif command == "stop":
            if self.recorder.is_recording():
                self._on_stop_clicked()

        elif command == "save":
            if self.recorder.is_complete():
                self._on_save_clicked()

        elif command == "discard":
            if self.recorder.is_complete():
                self._on_discard_clicked()

    def on_voice_error(self, message: str):
        """
        Slot connected to VoiceListener.error_occurred signal (wired in main.py).

        Handles: missing Vosk model, microphone not found, permission denied, etc.
        Resets voice button to OFF state and shows the first line of the error.

        Args:
            message: human-readable error string from VoiceListener
        """
        self._voice_active = False
        self._set_voice_btn_off()
        first_line = message.split('\n')[0]
        self._status_label.setText(f"Voice error: {first_line}")
        self._status_label.setStyleSheet("color: red;")

    # ── Button state managers ─────────────────────────────────────────

    # ── Calibration state ─────────────────────────────────────────────

    def on_calibration_done(self, calibration_data=None):
        """
        Slot connected to CalibrationTab.calibration_updated signal.

        Enables the Record button and clears any 'not calibrated' warning.
        The calibration_data argument is accepted but not used here —
        ProcessingThread.update_calibration() handles the actual data swap.
        This method only handles the UI side: enabling the Record button.

        Called from main.py:
            cal_tab.calibration_updated.connect(recorder_panel.on_calibration_done)
        """
        self._record_btn.setEnabled(True)
        self._status_label.setText("Calibration loaded — ready to record.")
        self._status_label.setStyleSheet("color: green;")

    def _set_state_idle(self):
        """UI state: waiting for Record button or 'Start' voice command."""
        self._label_combo.setEnabled(True)
        self._record_btn.setEnabled(True)
        self._stop_btn.setVisible(False)
        self._save_discard_widget.setVisible(False)
        self._progress_label.setText("Ready")
        self._progress_label.setStyleSheet("color: gray;")
        for btn in self._speed_btns.values():
            btn.setEnabled(True)

    def _set_state_capturing(self):
        """UI state: actively collecting frames."""
        self._label_combo.setEnabled(False)
        self._record_btn.setEnabled(False)
        self._stop_btn.setVisible(True)
        self._save_discard_widget.setVisible(False)
        self._progress_label.setText(f"Frames: 0 / {WINDOW_SIZE}")
        self._progress_label.setStyleSheet("color: blue;")
        # Lock speed during capture — changing it mid-recording would corrupt the filename
        for btn in self._speed_btns.values():
            btn.setEnabled(False)

    def _set_state_complete(self):
        """UI state: 60 frames collected — waiting for Save or Discard."""
        self._label_combo.setEnabled(False)
        self._record_btn.setEnabled(False)
        self._stop_btn.setVisible(False)
        self._save_discard_widget.setVisible(True)
        self._progress_label.setText(f"Complete! ({WINDOW_SIZE} frames)")
        self._progress_label.setStyleSheet("color: green; font-weight: bold;")
        for btn in self._speed_btns.values():
            btn.setEnabled(False)

    def _set_state_failed(self, reason: str):
        """UI state: recording aborted — show reason, return to idle controls."""
        self._label_combo.setEnabled(True)
        self._record_btn.setEnabled(True)
        self._stop_btn.setVisible(False)
        self._save_discard_widget.setVisible(False)
        self._progress_label.setText("⚠ Aborted")
        self._progress_label.setStyleSheet("color: red;")
        self._status_label.setText(reason)
        self._status_label.setStyleSheet("color: red;")
        for btn in self._speed_btns.values():
            btn.setEnabled(True)

    # ── Button click handlers ─────────────────────────────────────────

    def _on_record_clicked(self):
        """User pressed Record — or said 'Start'."""
        self._status_label.setText("")
        self._status_label.setStyleSheet("color: gray;")
        self.recording_started.emit()
        self.recorder.start_recording()
        self._set_state_capturing()

    def _on_stop_clicked(self):
        """User pressed Stop — or said 'Stop'. GestureRecorder pads and fires capture_complete."""
        self.recorder.stop_recording()

    def _on_save_clicked(self):
        """User pressed Save — or said 'Save'."""
        if self._pending_frames is None:
            return

        label = self._label_combo.currentText()

        try:
            filepath = self.dm.save_sample(label, self._pending_frames, speed=self._selected_speed)
        except Exception as e:
            self._status_label.setText(f"Save failed: {e}")
            self._status_label.setStyleSheet("color: red;")
            return

        # Cross-platform: replace backslash (Windows) before splitting
        filename = filepath.replace('\\', '/').split('/')[-1]

        self._pending_frames = None
        self.recorder.discard()        # reset GestureRecorder state machine to IDLE
        self.recording_stopped.emit()
        self._set_state_idle()
        self._status_label.setText(f"Saved: {filename}")
        self._status_label.setStyleSheet("color: green;")
        self.sample_saved.emit(label)

    def _on_discard_clicked(self):
        """User pressed Discard — or said 'Discard'."""
        self._pending_frames = None
        self.recorder.discard()
        self.recording_stopped.emit()
        self._set_state_idle()
        self._status_label.setText("Discarded.")
        self._status_label.setStyleSheet("color: gray;")

    # ── GestureRecorder signal slots ──────────────────────────────────

    def _on_progress(self, captured: int, total: int):
        """GestureRecorder.progress_updated → update frame counter label."""
        self._progress_label.setText(f"Frames: {captured} / {total}")

    def _on_capture_complete(self, frames: list):
        """GestureRecorder.capture_complete → store frames, show Save/Discard."""
        self._pending_frames = frames
        self._set_state_complete()

    def _on_capture_failed(self, reason: str):
        """GestureRecorder.capture_failed → show error, return to idle."""
        self._pending_frames = None
        self.recording_stopped.emit()
        self._set_state_failed(reason)
