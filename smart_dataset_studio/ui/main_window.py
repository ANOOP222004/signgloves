# ui/main_window.py
#
# Main application window — tabbed layout.
#
# Six tabs:
#   Dashboard   — live sensor value labels
#   Record      — RecorderPanel + DatasetPanel + SignalPlotWidget
#   Visualize   — stub for Phase 6 (3D skeleton + tuning sliders)
#   Calibration — CalibrationTab (profile management + inline capture)
#   Dataset     — stub for Phase 7 (analysis tools)
#   Export      — stub for Phase 8 (ML export)
#
# Status bar stays outside tabs — always visible.

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

FINGER_DISPLAY_NAMES = {
    'thumb': 'Thumb', 'index': 'Index', 'middle': 'Middle',
    'ring':  'Ring',  'little': 'Little',
}
IMU_DISPLAY_NAMES = {
    'pitch': 'Pitch', 'roll': 'Roll', 'yaw': 'Yaw',
}


class MainWindow(QMainWindow):
    """
    Main window of the Smart Glove Dataset Studio — tabbed layout.

    Public attributes (accessed by main.py for signal wiring):
        self.plot_widget      — SignalPlotWidget (Record tab)
        self.calibration_tab  — CalibrationTab  (Calibration tab)

    Full signal wiring in main.py — see main.py for complete list.
    """

    def __init__(self, recorder_panel=None, dataset_panel=None):
        super().__init__()

        self.setWindowTitle("Smart Glove Dataset Studio")
        self.setMinimumSize(960, 700)

        self._frame_count = 0
        self._fps_timer = QTimer()
        self._fps_timer.setInterval(1000)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start()

        self._build_ui(recorder_panel, dataset_panel)

        self._fps_label = QLabel("0 Hz")
        self._fps_label.setAlignment(Qt.AlignRight)
        self.statusBar().addPermanentWidget(self._fps_label)
        self.statusBar().showMessage("Connecting...")

    # ── UI ────────────────────────────────────────────────────────────

    def _build_ui(self, recorder_panel, dataset_panel):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # Tab 0 — Dashboard
        tabs.addTab(self._build_dashboard_tab(), "📊  Dashboard")

        # Tab 1 — Record  (plot_widget created here, stored as self.plot_widget)
        self.plot_widget = SignalPlotWidget()
        tabs.addTab(self._build_record_tab(recorder_panel, dataset_panel), "⏺  Record")

        # Tab 2 — Visualize stub
        tabs.addTab(self._build_visualize_stub(), "🖐  Visualize")

        # Tab 3 — Calibration (stored as self.calibration_tab for signal wiring)
        self.calibration_tab = CalibrationTab()
        tabs.addTab(self.calibration_tab, "⚙  Calibration")

        # Tab 4 — Dataset Analysis stub
        tabs.addTab(self._build_dataset_stub(), "📁  Dataset")

        # Tab 5 — ML Export stub
        tabs.addTab(self._build_export_stub(), "🚀  Export")

        root.addWidget(tabs)

    # ── Tab builders ──────────────────────────────────────────────────

    def _build_dashboard_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self._build_sensor_panel())
        layout.addStretch()
        return page

    def _build_record_tab(self, recorder_panel, dataset_panel) -> QWidget:
        """
        RecorderPanel + DatasetPanel side by side at top.
        SignalPlotWidget fills the rest of the vertical space below.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(
            recorder_panel if recorder_panel else self._stub("Recorder", "RecorderPanel not provided"),
            stretch=1
        )
        top_row.addWidget(
            dataset_panel if dataset_panel else self._stub("Dataset", "DatasetPanel not provided"),
            stretch=1
        )

        layout.addLayout(top_row, stretch=0)
        layout.addWidget(self.plot_widget, stretch=2)

        return page

    def _build_visualize_stub(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        group = QGroupBox("3D Hand Skeleton")
        g_layout = QVBoxLayout(group)
        msg = QLabel(
            "Phase 6 — 3D Hand Skeleton\n\n"
            "Requires full glove assembly (all 10 sensors).\n\n"
            "Will include:\n"
            "  •  Real-time 3D virtual hand mirroring glove movement\n"
            "  •  Per-finger max rotation tuning sliders\n"
            "  •  Global scale and wrist sensitivity controls\n"
            "  •  Save / load tuning profile to JSON"
        )
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color: gray;")
        msg.setFont(QFont("Arial", 10))
        g_layout.addWidget(msg)
        layout.addWidget(group)
        return page

    def _build_dataset_stub(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        group = QGroupBox("Dataset Analysis")
        g_layout = QVBoxLayout(group)
        msg = QLabel(
            "Phase 7 — Dataset Analysis Tools\n\n"
            "Will include:\n"
            "  •  Per-gesture signal overlay plots\n"
            "  •  Outlier detection\n"
            "  •  Dataset statistics (mean, std per feature)\n"
            "  •  Sample count balance chart"
        )
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color: gray;")
        msg.setFont(QFont("Arial", 10))
        g_layout.addWidget(msg)
        layout.addWidget(group)
        return page

    def _build_export_stub(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        group = QGroupBox("ML Export")
        g_layout = QVBoxLayout(group)
        msg = QLabel(
            "Phase 8 — ML Export System\n\n"
            "Will include:\n"
            "  •  dataset.npy  — shape (N, 60, 16)\n"
            "  •  labels.npy   — shape (N,)\n"
            "  •  label_map.json  — {HELLO: 0, STOP: 1, …}\n"
            "  •  Flat CSV with label column\n"
            "  •  TensorFlow Dataset format"
        )
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color: gray;")
        msg.setFont(QFont("Arial", 10))
        g_layout.addWidget(msg)
        layout.addWidget(group)
        return page

    # ── Sensor panel (Dashboard) ──────────────────────────────────────

    def _build_sensor_panel(self) -> QGroupBox:
        group = QGroupBox("Sensor Values")
        outer = QHBoxLayout(group)

        self._finger_labels = {}
        self._imu_labels    = {}

        for hand in ['right', 'left']:
            self._finger_labels[hand] = {}
            self._imu_labels[hand]    = {}

            hg     = QGroupBox(hand.capitalize() + " Hand")
            hl     = QVBoxLayout(hg)
            hl.setSpacing(4)

            for ch in FINGER_CHANNELS:
                row = QHBoxLayout()
                nl  = QLabel(FINGER_DISPLAY_NAMES[ch])
                nl.setMinimumWidth(60)
                vl  = QLabel("0.00")
                vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                vl.setMinimumWidth(50)
                vl.setFont(QFont("Courier", 10))
                self._finger_labels[hand][ch] = vl
                row.addWidget(nl)
                row.addWidget(vl)
                hl.addLayout(row)

            div = QLabel("── IMU ──")
            div.setAlignment(Qt.AlignCenter)
            div.setStyleSheet("color: gray; font-size: 9px;")
            hl.addWidget(div)

            for ch in IMU_CHANNELS:
                row = QHBoxLayout()
                nl  = QLabel(IMU_DISPLAY_NAMES[ch])
                nl.setMinimumWidth(60)
                vl  = QLabel("  0.0°")
                vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                vl.setMinimumWidth(60)
                vl.setFont(QFont("Courier", 10))
                self._imu_labels[hand][ch] = vl
                row.addWidget(nl)
                row.addWidget(vl)
                hl.addLayout(row)

            hl.addStretch()
            outer.addWidget(hg)

        return group

    def _stub(self, title: str, msg: str) -> QGroupBox:
        g = QGroupBox(title)
        l = QVBoxLayout(g)
        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: gray;")
        l.addWidget(lbl)
        return g

    # ── Slots ─────────────────────────────────────────────────────────

    def on_frame_ready(self, processed_frame: dict):
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                value = processed_frame[hand][ch]
                label = self._finger_labels[hand][ch]
                label.setText(f"{value:.2f}")
                # Color the value by bend amount — instant visual feedback
                # 0.0=gray, slight=blue, mid=amber, high=teal
                label.setStyleSheet(f"color: {bend_color(value)};")
            for ch in IMU_CHANNELS:
                self._imu_labels[hand][ch].setText(
                    f"{processed_frame[hand][ch]:>6.1f}°"
                )
        self._frame_count += 1

    def on_status_message(self, message: str):
        self.statusBar().showMessage(message)

    def set_connected(self, connected: bool):
        self.statusBar().showMessage("Connected" if connected else "Disconnected")

    def closeEvent(self, event):
        self.plot_widget.stop()
        super().closeEvent(event)

    def _update_fps(self):
        fps = self._frame_count
        self._frame_count = 0
        self._fps_label.setText(f"{fps} Hz")
