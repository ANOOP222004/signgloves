# ui/main_window.py
# Phase 6 — complete file
# Replace your entire existing ui/main_window.py with this file.
#
# Changes from Phase 5:
#   - HandSkeletonWidget imported and added to Visualize tab
#   - self.skeleton_widget exposed as public attribute for signal wiring
#   - Visualize tab is now real (not a stub)

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QGroupBox, QTabWidget,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

from config import FINGER_CHANNELS, IMU_CHANNELS
from ui.recorder_panel import RecorderPanel
from ui.dataset_panel import DatasetPanel
from ui.calibration_tab import CalibrationTab
from ui.style import bend_color
from visualization.signal_plot import SignalPlotWidget
from visualization.hand_skeleton import HandSkeletonWidget

FINGER_DISPLAY_NAMES = {
    'thumb':  'THUMB',
    'index':  'INDEX',
    'middle': 'MIDDLE',
    'ring':   'RING',
    'little': 'LITTLE',
}
IMU_DISPLAY_NAMES = {
    'pitch': 'PITCH',
    'roll':  'ROLL',
    'yaw':   'YAW',
}


class MainWindow(QMainWindow):
    """
    Main application window — Phase 6 tabbed layout.

    Six tabs:
        📊 Dashboard   — live sensor value labels, color-coded by bend
        ⏺  Record      — RecorderPanel + DatasetPanel + SignalPlotWidget
        🖐  Visualize   — HandSkeletonWidget + tuning sliders (Phase 6 — LIVE)
        ⚙  Calibration — CalibrationTab (inline, always accessible)
        📁  Dataset     — stub for Phase 7 analysis tools
        🚀  Export      — stub for Phase 8 ML export

    Public attributes wired in main.py:
        self.plot_widget      — SignalPlotWidget  (Record tab)
        self.calibration_tab  — CalibrationTab   (Calibration tab)
        self.skeleton_widget  — HandSkeletonWidget (Visualize tab)
    """

    def __init__(self, recorder_panel=None, dataset_panel=None):
        super().__init__()

        self.setWindowTitle("Smart Glove Dataset Studio")
        self.setMinimumSize(1000, 720)

        # FPS counter — counts frames received per second
        self._frame_count = 0
        self._fps_timer = QTimer()
        self._fps_timer.setInterval(1000)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start()

        self._build_ui(recorder_panel, dataset_panel)

        # Status bar — always visible regardless of active tab
        self._fps_label = QLabel("0 Hz")
        self._fps_label.setAlignment(Qt.AlignRight)
        self.statusBar().addPermanentWidget(self._fps_label)
        self.statusBar().showMessage("STATUS: CONNECTED")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self, recorder_panel, dataset_panel):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # Tab 0 — Dashboard
        tabs.addTab(self._build_dashboard_tab(), "📊  DASHBOARD")

        # Tab 1 — Record
        # plot_widget created here, accessed via self.plot_widget in main.py
        self.plot_widget = SignalPlotWidget()
        tabs.addTab(
            self._build_record_tab(recorder_panel, dataset_panel),
            "⏺  RECORD"
        )

        # Tab 2 — Visualize (Phase 6 — now real, not a stub)
        # skeleton_widget created here, accessed via self.skeleton_widget in main.py
        self.skeleton_widget = HandSkeletonWidget()
        tabs.addTab(self.skeleton_widget, "🖐  VISUALIZE")

        # Tab 3 — Calibration
        # calibration_tab created here, accessed via self.calibration_tab in main.py
        self.calibration_tab = CalibrationTab()
        tabs.addTab(self.calibration_tab, "⚙  CALIBRATION")

        # Tab 4 — Dataset Analysis (Phase 7 stub)
        tabs.addTab(self._build_dataset_stub(), "📁  DATASET")

        # Tab 5 — ML Export (Phase 8 stub)
        tabs.addTab(self._build_export_stub(), "🚀  EXPORT")

        root.addWidget(tabs)

    # ── Tab builders ──────────────────────────────────────────────────────────

    def _build_dashboard_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self._build_sensor_panel())
        layout.addStretch()
        return page

    def _build_record_tab(self, recorder_panel, dataset_panel) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Top row: recorder controls (left) + dataset counts (right)
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(
            recorder_panel if recorder_panel
            else self._stub("RECORDER", "RecorderPanel not provided"),
            stretch=1
        )
        top_row.addWidget(
            dataset_panel if dataset_panel
            else self._stub("DATASET", "DatasetPanel not provided"),
            stretch=1
        )

        # Bottom: signal plots take remaining space
        layout.addLayout(top_row, stretch=0)
        layout.addWidget(self.plot_widget, stretch=2)
        return page

    def _build_dataset_stub(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        group = QGroupBox("DATASET_ANALYSIS")
        g_layout = QVBoxLayout(group)
        msg = QLabel(
            "PHASE_07  //  DATASET ANALYSIS TOOLS\n\n"
            "Will include:\n"
            "  >  Per-gesture signal overlay plots\n"
            "  >  Outlier detection\n"
            "  >  Dataset statistics  (mean, std per feature)\n"
            "  >  Sample count balance chart"
        )
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color: #5A6A5A;")
        msg.setFont(QFont("Courier New", 10))
        g_layout.addWidget(msg)
        layout.addWidget(group)
        return page

    def _build_export_stub(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        group = QGroupBox("EXPORT_ENGINE")
        g_layout = QVBoxLayout(group)
        msg = QLabel(
            "PHASE_08  //  ML EXPORT SYSTEM\n\n"
            "Will include:\n"
            "  >  dataset.npy      shape: (N, 60, 16)\n"
            "  >  labels.npy       shape: (N,)\n"
            "  >  label_map.json   { HELLO: 0, STOP: 1, ... }\n"
            "  >  Flat CSV with label column\n"
            "  >  TensorFlow Dataset format"
        )
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color: #5A6A5A;")
        msg.setFont(QFont("Courier New", 10))
        g_layout.addWidget(msg)
        layout.addWidget(group)
        return page

    # ── Sensor panel (Dashboard tab) ──────────────────────────────────────────

    def _build_sensor_panel(self) -> QGroupBox:
        """
        Live sensor value display — all 16 channels.
        Finger labels are color-coded by bend_color() in on_frame_ready().
        Uses monospace font to prevent UI jitter from label resizing at 30 Hz.
        """
        group = QGroupBox("SENSOR_VALUES")
        outer = QHBoxLayout(group)
        outer.setSpacing(16)

        self._finger_labels = {}
        self._imu_labels    = {}

        for hand in ['right', 'left']:
            self._finger_labels[hand] = {}
            self._imu_labels[hand]    = {}

            hand_label = "RIGHT_GLOVE" if hand == 'right' else "LEFT_GLOVE"
            hg  = QGroupBox(hand_label)
            hl  = QVBoxLayout(hg)
            hl.setSpacing(6)

            # Finger section header
            bend_header = QLabel("FINGER_BEND  (0.0 - 1.0)")
            bend_header.setStyleSheet(
                "color: #5A6A5A; font-size: 9px; letter-spacing: 1px;"
            )
            hl.addWidget(bend_header)

            for ch in FINGER_CHANNELS:
                row = QHBoxLayout()
                nl  = QLabel(FINGER_DISPLAY_NAMES[ch])
                nl.setMinimumWidth(65)
                nl.setStyleSheet("color: #5A6A5A; font-size: 11px;")
                vl  = QLabel("0.00")
                vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                vl.setMinimumWidth(55)
                # Monospace: prevents label resizing causing UI jitter at 30 Hz
                vl.setFont(QFont("Courier New", 11))
                self._finger_labels[hand][ch] = vl
                row.addWidget(nl)
                row.addWidget(vl)
                hl.addLayout(row)

            # IMU section header
            imu_header = QLabel("WRIST_ORIENTATION  (DEG)")
            imu_header.setStyleSheet(
                "color: #5A6A5A; font-size: 9px; letter-spacing: 1px; "
                "margin-top: 6px;"
            )
            hl.addWidget(imu_header)

            for ch in IMU_CHANNELS:
                row = QHBoxLayout()
                nl  = QLabel(IMU_DISPLAY_NAMES[ch])
                nl.setMinimumWidth(65)
                nl.setStyleSheet("color: #5A6A5A; font-size: 11px;")
                vl  = QLabel("  0.0")
                vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                vl.setMinimumWidth(60)
                vl.setFont(QFont("Courier New", 11))
                self._imu_labels[hand][ch] = vl
                row.addWidget(nl)
                row.addWidget(vl)
                hl.addLayout(row)

            hl.addStretch()
            outer.addWidget(hg)

        return group

    def _stub(self, title: str, msg: str) -> QGroupBox:
        """Placeholder panel used when a panel object is not provided."""
        g = QGroupBox(title)
        l = QVBoxLayout(g)
        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #5A6A5A;")
        l.addWidget(lbl)
        return g

    # ── Public slots ──────────────────────────────────────────────────────────

    def on_frame_ready(self, processed_frame: dict):
        """
        Connected to processing_thread.frame_ready.
        Called 30 Hz on the main thread.
        Updates all 16 sensor value labels with color coding.
        """
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                value = processed_frame[hand][ch]
                label = self._finger_labels[hand][ch]
                label.setText(f"{value:.2f}")
                # bend_color: gray→blue→yellow→green as bend increases
                label.setStyleSheet(f"color: {bend_color(value)};")
            for ch in IMU_CHANNELS:
                self._imu_labels[hand][ch].setText(
                    f"{processed_frame[hand][ch]:>6.1f}"
                )
        self._frame_count += 1

    def on_status_message(self, message: str):
        """Connected to processing_thread.status_message."""
        self.statusBar().showMessage(message)

    def set_connected(self, connected: bool):
        """Called from main.py after serial thread starts."""
        msg = "STATUS: CONNECTED" if connected else "STATUS: DISCONNECTED"
        self.statusBar().showMessage(msg)

    def closeEvent(self, event):
        """Stop the plot timer when window closes to prevent timer firing on dead widget."""
        self.plot_widget.stop()
        super().closeEvent(event)

    def _update_fps(self):
        """Called every 1 second by _fps_timer. Shows live frame rate."""
        fps = self._frame_count
        self._frame_count = 0
        self._fps_label.setText(f"RATE: {fps} Hz")
