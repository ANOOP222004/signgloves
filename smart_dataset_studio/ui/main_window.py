# ui/main_window.py
# Phase 7 — DATASET tab now live (AnalysisTab replaces stub)
#
# Changes from Phase 6:
#   - AnalysisTab imported and added to Dataset tab
#   - self.analysis_tab exposed as public attribute
#   - _build_dataset_stub() removed (AnalysisTab is the real widget now)
#   - dataset_manager passed to MainWindow so AnalysisTab can use it
#   - MainWindow.__init__ signature updated: dataset_manager param added

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QGroupBox, QTabWidget,
)
from PyQt5.QtCore import QEvent, QTimer, Qt
from PyQt5.QtGui import QFont

from config import FINGER_CHANNELS, IMU_CHANNELS
from ui.recorder_panel import RecorderPanel
from ui.dataset_panel import DatasetPanel
from ui.calibration_tab import CalibrationTab
from ui.analysis_tab import AnalysisTab
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
    Main application window — Phase 7 tabbed layout.

    Six tabs:
        📊 Dashboard   — live sensor value labels, color-coded by bend
        ⏺  Record      — RecorderPanel + DatasetPanel + SignalPlotWidget
        🖐  Visualize   — HandSkeletonWidget + tuning sliders (Phase 6)
        ⚙  Calibration — CalibrationTab (inline, always accessible)
        📁  Dataset     — AnalysisTab — Phase 7 LIVE (was stub in Phase 6)
        🚀  Export      — stub for Phase 8 ML export

    Public attributes wired in main.py:
        self.plot_widget      — SignalPlotWidget   (Record tab)
        self.calibration_tab  — CalibrationTab    (Calibration tab)
        self.skeleton_widget  — HandSkeletonWidget (Visualize tab)
        self.analysis_tab     — AnalysisTab        (Dataset tab) ← NEW Phase 7
    """

    def __init__(self, recorder_panel=None, dataset_panel=None, dataset_manager=None):
        super().__init__()

        self.setWindowTitle("Smart Glove Dataset Studio")
        self.setMinimumSize(1000, 720)

        self._dataset_manager      = dataset_manager   # stored for AnalysisTab
        self._skeleton_initialized = False             # lazy GL init on first tab select

        # FPS counter
        self._frame_count = 0
        self._fps_timer = QTimer()
        self._fps_timer.setInterval(1000)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start()

        self._build_ui(recorder_panel, dataset_panel)

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
        tabs.currentChanged.connect(self._on_tab_changed)

        # Tab 0 — Dashboard
        tabs.addTab(self._build_dashboard_tab(), "📊  DASHBOARD")

        # Tab 1 — Record
        self.plot_widget = SignalPlotWidget()
        tabs.addTab(
            self._build_record_tab(recorder_panel, dataset_panel),
            "⏺  RECORD"
        )

        # Tab 2 — Visualize
        self.skeleton_widget = HandSkeletonWidget()
        tabs.addTab(self.skeleton_widget, "🖐  VISUALIZE")

        # Tab 3 — Calibration
        self.calibration_tab = CalibrationTab()
        tabs.addTab(self.calibration_tab, "⚙  CALIBRATION")

        # Tab 4 — Dataset Analysis — Phase 7 LIVE
        # Requires dataset_manager to access the dataset path and delete files.
        # Falls back to a placeholder if not provided (shouldn't happen in normal use).
        if self._dataset_manager is not None:
            self.analysis_tab = AnalysisTab(self._dataset_manager)
            tabs.addTab(self.analysis_tab, "📁  DATASET")
        else:
            self.analysis_tab = None
            tabs.addTab(self._build_stub("DATASET_ANALYSIS", "dataset_manager not provided"), "📁  DATASET")

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

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(
            recorder_panel if recorder_panel
            else self._build_stub("RECORDER", "RecorderPanel not provided"),
            stretch=1
        )
        top_row.addWidget(
            dataset_panel if dataset_panel
            else self._build_stub("DATASET", "DatasetPanel not provided"),
            stretch=1
        )

        layout.addLayout(top_row, stretch=0)
        layout.addWidget(self.plot_widget, stretch=2)
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

    def _build_stub(self, title: str, msg_text: str) -> QGroupBox:
        g = QGroupBox(title)
        l = QVBoxLayout(g)
        msg = QLabel(msg_text)
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color: #5A6A5A;")
        l.addWidget(msg)
        return g

    # ── Sensor panel (Dashboard) ──────────────────────────────────────────────

    def _build_sensor_panel(self) -> QGroupBox:
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

            bend_header = QLabel("FINGER_BEND  (0.0 - 1.0)")
            bend_header.setStyleSheet("color: #5A6A5A; font-size: 9px; letter-spacing: 1px;")
            hl.addWidget(bend_header)

            for ch in FINGER_CHANNELS:
                row = QHBoxLayout()
                nl  = QLabel(FINGER_DISPLAY_NAMES[ch])
                nl.setMinimumWidth(65)
                nl.setStyleSheet("color: #5A6A5A; font-size: 11px;")
                vl  = QLabel("0.00")
                vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                vl.setMinimumWidth(55)
                vl.setFont(QFont("Courier New", 11))
                self._finger_labels[hand][ch] = vl
                row.addWidget(nl)
                row.addWidget(vl)
                hl.addLayout(row)

            imu_header = QLabel("WRIST_ORIENTATION  (DEG)")
            imu_header.setStyleSheet("color: #5A6A5A; font-size: 9px; letter-spacing: 1px; margin-top: 6px;")
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

    # ── Public slots ──────────────────────────────────────────────────────────

    def on_frame_ready(self, processed_frame: dict):
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                value = processed_frame[hand][ch]
                label = self._finger_labels[hand][ch]
                label.setText(f"{value:.2f}")
                label.setStyleSheet(f"color: {bend_color(value)};")
            for ch in IMU_CHANNELS:
                self._imu_labels[hand][ch].setText(
                    f"{processed_frame[hand][ch]:>6.1f}"
                )
        self._frame_count += 1

    def on_status_message(self, message: str):
        self.statusBar().showMessage(message)

    def set_connected(self, connected: bool):
        msg = "STATUS: CONNECTED" if connected else "STATUS: DISCONNECTED"
        self.statusBar().showMessage(msg)

    def _on_tab_changed(self, index: int):
        # Visualize tab is index 2. Initialize GL only on first select so the
        # GLViewWidget surface is fully visible before any GL context is created.
        if index == 2 and not self._skeleton_initialized:
            self._skeleton_initialized = True
            self.skeleton_widget.initialize()

    def changeEvent(self, event):
        # On Ubuntu GNOME + xcb_egl, the title-bar maximize button sometimes
        # triggers WindowFullScreen instead of WindowMaximized. In fullscreen
        # mode the xcb_egl compositor makes the window invisible. Intercept the
        # fullscreen state and convert it to maximize, which composites correctly.
        if event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowFullScreen:
                QTimer.singleShot(0, self.showMaximized)
                return
        super().changeEvent(event)

    def closeEvent(self, event):
        self.skeleton_widget.stop()
        self.plot_widget.stop()
        super().closeEvent(event)

    def _update_fps(self):
        fps = self._frame_count
        self._frame_count = 0
        self._fps_label.setText(f"RATE: {fps} Hz")
