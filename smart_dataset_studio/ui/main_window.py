# ui/main_window.py
#
# Main application window for the Smart Glove Dataset Studio.
#
# What this does:
#   - Displays all 16 live sensor values (10 fingers + 6 IMU)
#   - Shows connection status and live frame rate in the status bar
#   - Provides stub panels for Recorder and Dataset (Phase 4 fills these in)
#
# How it fits into the thread architecture:
#   ProcessingThread emits frame_ready signal (carries processed frame dict)
#   → this window's on_frame_ready() slot receives it on the main thread
#   → updates QLabel widgets with new values
#
# Rules this file follows:
#   - Never touches the Queue directly (that belongs to ProcessingThread)
#   - Never calls any ProcessingThread methods directly (only via signals)
#   - All UI updates happen in the main thread only (Qt requirement)
#   - No magic numbers — all constants from config.py

from PyQt5.QtWidgets import (
    QMainWindow,     # Top-level window with menu bar + status bar
    QWidget,         # Base class for all UI elements
    QHBoxLayout,     # Arranges children left-to-right
    QVBoxLayout,     # Arranges children top-to-bottom
    QLabel,          # Displays a text string
    QGroupBox,       # Labelled box that visually groups related widgets
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

from config import FINGER_CHANNELS, IMU_CHANNELS
from ui.recorder_panel import RecorderPanel
from ui.dataset_panel import DatasetPanel


# Human-readable display names for each finger channel.
# These are the labels shown in the UI, not the internal key names.
# Internal keys (from frame dict): 'thumb', 'index', 'middle', 'ring', 'little'
FINGER_DISPLAY_NAMES = {
    'thumb':  'Thumb',
    'index':  'Index',
    'middle': 'Middle',
    'ring':   'Ring',
    'little': 'Little',
}

# Human-readable display names for IMU channels.
IMU_DISPLAY_NAMES = {
    'pitch': 'Pitch',
    'roll':  'Roll',
    'yaw':   'Yaw',
}


class MainWindow(QMainWindow):
    """
    Main window of the Smart Glove Dataset Studio.

    Receives processed sensor frames via Qt Signal and displays them live.

    Usage (from main.py):
        window = MainWindow()
        processing_thread.frame_ready.connect(window.on_frame_ready)
        processing_thread.status_message.connect(window.on_status_message)
        window.show()
    """

    def __init__(self, recorder_panel=None, dataset_panel=None):
        super().__init__()

        self.setWindowTitle("Smart Glove Dataset Studio")
        self.setMinimumSize(900, 400)   # prevents layout from collapsing

        # ── Frame rate tracking ───────────────────────────────────────
        # Count how many frames arrive per second.
        # _frame_count increments every time on_frame_ready() is called.
        # A QTimer fires every 1000ms, reads the count, updates the
        # status bar label, then resets the count to 0.
        # Why a timer rather than computing rate inside on_frame_ready?
        # Because computing rate per-frame requires division and
        # timestamps on every call — expensive at 30 Hz. Counting is O(1).
        self._frame_count = 0
        self._fps_timer = QTimer()
        self._fps_timer.setInterval(1000)           # fire every 1 second
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start()

        # ── Build the UI ──────────────────────────────────────────────
        self._build_ui(recorder_panel, dataset_panel)

        # ── Status bar ────────────────────────────────────────────────
        # QMainWindow has a built-in status bar — we just use it.
        # showMessage() sets the left-side text.
        # We add a permanent right-side widget for frame rate.
        self._fps_label = QLabel("0 Hz")
        self._fps_label.setAlignment(Qt.AlignRight)
        self.statusBar().addPermanentWidget(self._fps_label)
        self.statusBar().showMessage("Connecting...")

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self, recorder_panel=None, dataset_panel=None):
        """
        Construct the full window layout.

        Layout structure:
            QMainWindow
            └── central_widget (QWidget)
                └── root_layout (QHBoxLayout)
                    ├── _build_sensor_panel()  ← live sensor values
                    ├── RecorderPanel or stub  ← Phase 4 real / fallback
                    └── DatasetPanel or stub   ← Phase 4 real / fallback

        Args:
            recorder_panel: RecorderPanel instance, or None for stub
            dataset_panel:  DatasetPanel instance, or None for stub
        """
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setSpacing(10)
        root_layout.setContentsMargins(10, 10, 10, 10)

        root_layout.addWidget(self._build_sensor_panel(), stretch=2)

        if recorder_panel is not None:
            root_layout.addWidget(recorder_panel, stretch=1)
        else:
            root_layout.addWidget(self._build_recorder_panel(), stretch=1)

        if dataset_panel is not None:
            root_layout.addWidget(dataset_panel, stretch=1)
        else:
            root_layout.addWidget(self._build_dataset_panel(), stretch=1)

    def _build_sensor_panel(self) -> QGroupBox:
        """
        Build the live sensor values panel.

        Contains two sub-groups side by side:
            Left sub-group:  Right hand (5 fingers + 3 IMU)
            Right sub-group: Left hand  (5 fingers + 3 IMU)

        Stores label references in:
            self._finger_labels[hand][channel] → QLabel showing 0.00–1.00
            self._imu_labels[hand][channel]    → QLabel showing degrees

        Why store label references?
        on_frame_ready() needs to update these labels every frame.
        Storing references avoids searching the widget tree on every update.
        """
        group = QGroupBox("Sensor Values")
        outer_layout = QHBoxLayout(group)

        # Dicts to hold label references for fast updates
        # Structure: {'right': {'thumb': QLabel, ...}, 'left': {...}}
        self._finger_labels = {}
        self._imu_labels = {}

        for hand in ['right', 'left']:
            self._finger_labels[hand] = {}
            self._imu_labels[hand] = {}

            # QGroupBox for each hand: "Right Hand" / "Left Hand"
            hand_label = hand.capitalize() + " Hand"
            hand_group = QGroupBox(hand_label)
            hand_layout = QVBoxLayout(hand_group)
            hand_layout.setSpacing(4)

            # ── Finger rows ───────────────────────────────────────────
            # Each row: "Thumb    0.00"
            # Label on left, value on right
            for ch in FINGER_CHANNELS:
                row = QHBoxLayout()

                # Channel display name (left side)
                name_label = QLabel(FINGER_DISPLAY_NAMES[ch])
                name_label.setMinimumWidth(60)

                # Value label (right side) — updated every frame
                value_label = QLabel("0.00")
                value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                value_label.setMinimumWidth(50)
                value_label.setFont(QFont("Courier", 10))  # monospace for stable width

                self._finger_labels[hand][ch] = value_label  # store reference

                row.addWidget(name_label)
                row.addWidget(value_label)
                hand_layout.addLayout(row)

            # ── Divider ───────────────────────────────────────────────
            divider = QLabel("── IMU ──")
            divider.setAlignment(Qt.AlignCenter)
            divider.setStyleSheet("color: gray; font-size: 9px;")
            hand_layout.addWidget(divider)

            # ── IMU rows ──────────────────────────────────────────────
            # Each row: "Pitch    0.0°"
            # IMU values are degrees — no normalization, range -180 to 180
            for ch in IMU_CHANNELS:
                row = QHBoxLayout()

                name_label = QLabel(IMU_DISPLAY_NAMES[ch])
                name_label.setMinimumWidth(60)

                value_label = QLabel("  0.0°")
                value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                value_label.setMinimumWidth(60)
                value_label.setFont(QFont("Courier", 10))

                self._imu_labels[hand][ch] = value_label  # store reference

                row.addWidget(name_label)
                row.addWidget(value_label)
                hand_layout.addLayout(row)

            hand_layout.addStretch()           # push rows to top
            outer_layout.addWidget(hand_group)

        return group

    def _build_recorder_panel(self) -> QGroupBox:
        """
        Stub panel for Phase 4 — Gesture Recorder.

        Returns an empty QGroupBox with a placeholder label.
        Phase 4 will replace this stub with real recording controls.
        """
        group = QGroupBox("Recorder")
        layout = QVBoxLayout(group)
        placeholder = QLabel("Gesture recorder\n(Phase 4)")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: gray;")
        layout.addWidget(placeholder)
        return group

    def _build_dataset_panel(self) -> QGroupBox:
        """
        Stub panel for Phase 4 — Dataset Manager.

        Returns an empty QGroupBox with a placeholder label.
        Phase 4 will replace this stub with sample counts and export controls.
        """
        group = QGroupBox("Dataset")
        layout = QVBoxLayout(group)
        placeholder = QLabel("Dataset manager\n(Phase 4)")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: gray;")
        layout.addWidget(placeholder)
        return group

    # ── Signal Slots ──────────────────────────────────────────────────

    def on_frame_ready(self, processed_frame: dict):
        """
        Slot connected to ProcessingThread.frame_ready signal.

        Called on the main thread by Qt's signal routing — safe to update UI.
        Updates all 16 sensor value labels with the latest processed frame.

        Args:
            processed_frame: dict with structure:
                {
                    'frame_id': int,
                    'right': {
                        'thumb': float (0.0-1.0),
                        'index': float (0.0-1.0),
                        'middle': float (0.0-1.0),
                        'ring': float (0.0-1.0),
                        'little': float (0.0-1.0),
                        'pitch': float (degrees),
                        'roll':  float (degrees),
                        'yaw':   float (degrees),
                    },
                    'left': { same structure }
                }
        """
        # Update all finger labels for both hands
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                value = processed_frame[hand][ch]        # float 0.0–1.0
                self._finger_labels[hand][ch].setText(f"{value:.2f}")

            # Update all IMU labels for both hands
            for ch in IMU_CHANNELS:
                value = processed_frame[hand][ch]        # float degrees
                self._imu_labels[hand][ch].setText(f"{value:>6.1f}°")

        # Increment frame counter for FPS tracking
        # _fps_timer reads this every second and resets it
        self._frame_count += 1

    def on_status_message(self, message: str):
        """
        Slot connected to ProcessingThread.status_message signal.

        Displays warnings (e.g. frame drops) in the status bar.
        The message stays visible until the next status update.

        Args:
            message: warning string from processing thread
        """
        self.statusBar().showMessage(message)

    def set_connected(self, connected: bool):
        """
        Update the status bar connection indicator.

        Called from main.py after serial thread confirms connection.
        Not connected to a signal — called directly since it's a
        one-time event, not a recurring data update.

        Args:
            connected: True = show Connected, False = show Disconnected
        """
        if connected:
            self.statusBar().showMessage("Connected")
        else:
            self.statusBar().showMessage("Disconnected")

    # ── Private helpers ───────────────────────────────────────────────

    def _update_fps(self):
        """
        Called every 1000ms by _fps_timer.

        Reads _frame_count (frames received this second),
        displays it in the permanent FPS label,
        then resets the counter.

        Why this approach:
        At 30 Hz we receive 30 signals per second. Computing rate
        inside on_frame_ready() would require timestamps and division
        30 times per second. Counting is O(1) and a 1-second timer
        batch-reads the result once — far more efficient.
        """
        fps = self._frame_count          # frames received in the last second
        self._frame_count = 0            # reset for next second
        self._fps_label.setText(f"{fps} Hz")
