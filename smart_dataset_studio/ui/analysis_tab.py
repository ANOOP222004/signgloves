# ui/analysis_tab.py
#
# AnalysisTab — dataset quality inspection panel for the DATASET tab.
#
# Phase 7 redesign layout:
#
#   TOP ROW
#     Gesture dropdown | Speed filter (ALL/SLOW/MEDIUM/FAST) | Profile label
#     ANALYZE button | REFRESH button
#
#   MAIN AREA (horizontal splitter)
#     LEFT — Sample count list (text, color-coded by total count)
#       HELLO        17  (slow: 5  medium: 8  fast: 4)
#       STOP          3  (slow: 0  medium: 3  fast: 0)
#       ...
#
#     RIGHT — Single combined overlay graph
#       Per sample: mean of the 10 finger channels per frame (one line each)
#       Speed colors: slow=blue, medium=yellow, fast=green
#       Alpha 0.3 for individual curves, thick white mean line on top
#       Vertical dashed zone boundary lines for selected speed (not ALL)
#
#   BOTTOM (unchanged from Phase 7 original)
#     Outlier detection table + stats table
#
# Threading: all analysis on main thread. Fast enough for Phase 7 dataset sizes.

import os
import logging

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QMessageBox, QScrollArea,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from dataset.dataset_analyzer import DatasetAnalyzer
from dataset.dataset_manager import DatasetManager
from config import (
    GESTURE_LABELS, FEATURE_ORDER, NUM_FEATURES,
    WINDOW_SIZE, SPEED_ZONES, SPEED_TAGS,
)

logger = logging.getLogger(__name__)

# Finger channels only: right indices 0-4, left indices 8-12.
# IMU channels are in degrees (not 0-1) so they would corrupt the overlay scale.
_FINGER_INDICES = [0, 1, 2, 3, 4, 8, 9, 10, 11, 12]

# Target sample count for color thresholds in the count list
_TARGET_SAMPLES = 50
_WARN_SAMPLES   = 20

# Speed display colors — used in both speed filter buttons and overlay lines
_SPEED_COLORS = {
    'slow':   (80,  120, 255),   # blue
    'medium': (230, 210,   0),   # yellow
    'fast':   (50,  220,  80),   # green
}

_FRAME_X = list(range(WINDOW_SIZE))


class AnalysisTab(QWidget):
    """
    Dataset quality inspection panel for the DATASET tab.

    Usage (in main_window.py):
        self.analysis_tab = AnalysisTab(dataset_manager)
        tabs.addTab(self.analysis_tab, "📁  DATASET")

    Call refresh() after any recording session to update counts and
    recreate the analyzer (picks up profile changes automatically).
    """

    def __init__(self, dataset_manager: DatasetManager, parent=None):
        super().__init__(parent)

        self.dm       = dataset_manager
        self.analyzer = DatasetAnalyzer(dataset_manager.dataset_path)

        self._current_label     = GESTURE_LABELS[0]
        self._current_samples   = None    # shape (N, 60, 16) or None
        self._current_filenames = []
        self._speed_filter      = 'all'   # 'all' / 'slow' / 'medium' / 'fast'

        self._build_ui()
        self.refresh()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addLayout(self._build_top_row())

        # Main splitter: count list (left) | overlay graph (right)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_count_list_panel())
        splitter.addWidget(self._build_overlay_panel())
        splitter.setSizes([280, 720])
        root.addWidget(splitter, stretch=3)

        root.addWidget(self._build_outlier_panel(), stretch=1)
        root.addWidget(self._build_stats_panel(),   stretch=1)

    def _build_top_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        # Gesture selector
        row.addWidget(QLabel("Gesture:"))
        self._label_combo = QComboBox()
        for label in GESTURE_LABELS:
            self._label_combo.addItem(label)
        self._label_combo.setMinimumHeight(28)
        self._label_combo.currentTextChanged.connect(self._on_label_changed)
        row.addWidget(self._label_combo, stretch=1)

        # Speed filter toggle buttons (ALL / SLOW / MEDIUM / FAST)
        row.addWidget(QLabel("Speed:"))
        self._speed_filter_btns = {}
        for tag in ['all'] + SPEED_TAGS:
            btn = QPushButton(tag.upper())
            btn.setCheckable(True)
            btn.setMinimumHeight(28)
            btn.setMinimumWidth(60)
            btn.setFont(QFont("Courier", 8, QFont.Bold))
            btn.clicked.connect(lambda _checked, t=tag: self._on_speed_filter(t))
            self._speed_filter_btns[tag] = btn
            row.addWidget(btn)
        self._apply_speed_filter_style('all')

        row.addSpacing(12)

        # Active profile label (read-only)
        self._profile_label = QLabel()
        self._profile_label.setStyleSheet("color: #5A6A5A; font-size: 9px;")
        self._profile_label.setFont(QFont("Courier", 9))
        row.addWidget(self._profile_label)

        row.addStretch()

        # Analyze button
        self._analyze_btn = QPushButton("📊  Analyze")
        self._analyze_btn.setMinimumHeight(28)
        self._analyze_btn.setMinimumWidth(100)
        self._analyze_btn.clicked.connect(self._run_analysis)
        row.addWidget(self._analyze_btn)

        # Refresh button
        self._refresh_btn = QPushButton("⟳  Refresh")
        self._refresh_btn.setMinimumHeight(28)
        self._refresh_btn.setMinimumWidth(90)
        self._refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self._refresh_btn)

        return row

    def _build_count_list_panel(self) -> QGroupBox:
        """
        Left panel: plain text list of sample counts per gesture.

        Color-codes the total count:
          red    < 20  — needs significantly more samples
          yellow 20-49 — usable but more is better
          green  >= 50 — ready for ML training
        """
        group = QGroupBox("SAMPLE COUNTS")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(6, 8, 6, 8)
        outer.setSpacing(2)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(scroll_area.NoFrame)

        container = QWidget()
        self._count_list_layout = QVBoxLayout(container)
        self._count_list_layout.setSpacing(2)
        self._count_list_layout.setContentsMargins(0, 0, 0, 0)
        self._count_list_layout.addStretch()

        scroll_area.setWidget(container)
        outer.addWidget(scroll_area)

        # Legend
        legend = QLabel("red<20  yellow<50  green≥50")
        legend.setStyleSheet("color: #3A4A3A; font-size: 8px;")
        legend.setAlignment(Qt.AlignCenter)
        outer.addWidget(legend)

        return group

    def _build_overlay_panel(self) -> QGroupBox:
        """
        Right panel: single overlay plot — mean of 10 finger channels per frame.

        One line per sample, colored by speed (blue/yellow/green), alpha 0.3.
        Thick white mean line on top. Zone boundaries as dashed verticals.
        """
        group = QGroupBox("GESTURE OVERLAY  (finger channels mean — click Analyze)")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        # Count label
        self._sample_count_label = QLabel("No data")
        self._sample_count_label.setStyleSheet("color: #5A6A5A; font-size: 10px;")
        layout.addWidget(self._sample_count_label)

        # Single overlay plot
        pg.setConfigOptions(antialias=True, useOpenGL=False)
        self._overlay_plot = pg.PlotWidget(background='#0A0C0A')
        self._overlay_plot.setLabel('left',   'MEAN BEND',  color='#5A6A5A', size='8pt')
        self._overlay_plot.setLabel('bottom', 'FRAMES',     color='#5A6A5A', size='8pt')
        self._overlay_plot.getAxis('left').setTextPen('#5A6A5A')
        self._overlay_plot.getAxis('bottom').setTextPen('#5A6A5A')
        self._overlay_plot.setYRange(-0.05, 1.05)
        self._overlay_plot.setXRange(0, WINDOW_SIZE - 1)
        self._overlay_plot.showGrid(x=False, y=True, alpha=0.3)
        self._overlay_plot.hideButtons()
        # ~40% of a 720-px tall window. Without this the outlier/stats
        # tables' minimum heights squeeze the splitter below its 3:1:1 share.
        self._overlay_plot.setMinimumHeight(280)
        layout.addWidget(self._overlay_plot, stretch=1)

        # Speed color legend below the plot
        legend_row = QHBoxLayout()
        for speed, (r, g, b) in _SPEED_COLORS.items():
            lbl = QLabel(f"■ {speed}")
            lbl.setStyleSheet(f"color: rgb({r},{g},{b}); font-size: 9px;")
            lbl.setFont(QFont("Courier", 9))
            legend_row.addWidget(lbl)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        return group

    def _build_outlier_panel(self) -> QGroupBox:
        group = QGroupBox("OUTLIER DETECTION")
        layout = QVBoxLayout(group)

        self._outlier_table = QTableWidget()
        self._outlier_table.setColumnCount(5)
        self._outlier_table.setHorizontalHeaderLabels([
            "File", "Feature", "Z-Score", "Sample Mean", "Gesture Mean"
        ])
        self._outlier_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._outlier_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._outlier_table.setAlternatingRowColors(True)
        self._outlier_table.verticalHeader().setVisible(False)
        self._outlier_table.setMinimumHeight(120)
        self._outlier_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._outlier_table)

        btn_row = QHBoxLayout()
        self._delete_outlier_btn = QPushButton("🗑  Delete Selected Sample")
        self._delete_outlier_btn.setObjectName("discard_btn")
        self._delete_outlier_btn.clicked.connect(self._delete_selected_outlier)
        btn_row.addWidget(self._delete_outlier_btn)
        btn_row.addStretch()

        self._outlier_status = QLabel("")
        self._outlier_status.setStyleSheet("color: #5A6A5A; font-size: 9px;")
        btn_row.addWidget(self._outlier_status)
        layout.addLayout(btn_row)

        return group

    def _build_stats_panel(self) -> QGroupBox:
        group = QGroupBox("FEATURE STATISTICS  (mean ± std across all samples)")
        layout = QVBoxLayout(group)

        self._stats_table = QTableWidget()
        self._stats_table.setColumnCount(3)
        self._stats_table.setHorizontalHeaderLabels(["Feature", "Mean", "Std Dev"])
        self._stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._stats_table.setAlternatingRowColors(True)
        self._stats_table.verticalHeader().setVisible(False)
        self._stats_table.setRowCount(NUM_FEATURES)
        self._stats_table.setMinimumHeight(100)
        layout.addWidget(self._stats_table)

        for i, feat in enumerate(FEATURE_ORDER):
            self._stats_table.setItem(i, 0, QTableWidgetItem(feat))
            self._stats_table.setItem(i, 1, QTableWidgetItem("—"))
            self._stats_table.setItem(i, 2, QTableWidgetItem("—"))

        return group

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self):
        """
        Re-read sample counts from disk and update the count list.

        Also recreates the DatasetAnalyzer from dm.dataset_path so that
        profile changes (from CalibrationTab) are automatically picked up.
        Call this after every recording session.
        """
        self.analyzer = DatasetAnalyzer(self.dm.dataset_path)
        self._update_count_list()
        self._profile_label.setText(f"profile: {self.dm.current_profile}")

    # ── Top-row slots ─────────────────────────────────────────────────────────

    def _on_label_changed(self, label: str):
        """Clear analysis when user selects a different gesture."""
        self._current_label     = label
        self._current_samples   = None
        self._current_filenames = []
        self._sample_count_label.setText("Click Analyze to inspect this gesture.")
        self._overlay_plot.clear()
        self._clear_outlier_table()
        self._clear_stats_table()

    def _on_speed_filter(self, tag: str):
        """Switch the speed filter and update button styles."""
        self._speed_filter = tag
        self._apply_speed_filter_style(tag)
        self._sample_count_label.setText("Click Analyze to apply new filter.")

    def _apply_speed_filter_style(self, active_tag: str):
        _active = (
            "QPushButton { background-color: #1A2A3A; color: #4090FF; "
            "font-weight: bold; border: 1px solid #4090FF; border-radius: 4px; }"
        )
        for tag, btn in self._speed_filter_btns.items():
            btn.setChecked(tag == active_tag)
            btn.setStyleSheet(_active if tag == active_tag else "")

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _run_analysis(self):
        """Load data for the selected gesture + speed filter and update all panels."""
        label = self._label_combo.currentText()

        # For overlay: load filtered by speed
        samples, filenames = self.analyzer.load_label_filtered_with_filenames(
            label, speed=self._speed_filter
        )
        self._current_samples   = samples
        self._current_filenames = filenames

        if samples is None:
            n_total = self.analyzer.all_counts().get(label, 0)
            if n_total > 0 and self._speed_filter != 'all':
                self._sample_count_label.setText(
                    f"No {self._speed_filter} samples — {n_total} total (other speeds)"
                )
            else:
                self._sample_count_label.setText("No samples recorded yet.")
            self._overlay_plot.clear()
            self._clear_outlier_table()
            self._clear_stats_table()
            return

        n = len(samples)
        filter_str = '' if self._speed_filter == 'all' else f' ({self._speed_filter})'
        self._sample_count_label.setText(f"{n} sample{'s' if n != 1 else ''} loaded{filter_str}")

        self._update_overlay_plot(samples, filenames)
        self._update_outlier_table(label)
        self._update_stats_table(label)

    # ── Count list ────────────────────────────────────────────────────────────

    def _update_count_list(self):
        """Rebuild the count list from disk counts for the current profile."""
        # Clear existing rows (except the trailing stretch)
        while self._count_list_layout.count() > 1:
            item = self._count_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total_counts = self.analyzer.all_counts()
        speed_counts = self.analyzer.all_speed_counts()

        for label in GESTURE_LABELS:
            total = total_counts.get(label, 0)
            sc    = speed_counts.get(label, {'slow': 0, 'medium': 0, 'fast': 0})

            # Color for total count
            if total >= _TARGET_SAMPLES:
                count_color = "#39FF14"    # green
            elif total >= _WARN_SAMPLES:
                count_color = "#E8E000"    # yellow
            else:
                count_color = "#FF4444"    # red

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 1, 4, 1)
            row_layout.setSpacing(0)

            # Gesture name
            name_lbl = QLabel(f"{label:<10}")
            name_lbl.setFont(QFont("Courier New", 9))
            name_lbl.setStyleSheet("color: #A0B0A0;")
            row_layout.addWidget(name_lbl)

            # Total count (colored)
            total_lbl = QLabel(f"{total:>3}")
            total_lbl.setFont(QFont("Courier New", 9, QFont.Bold))
            total_lbl.setStyleSheet(f"color: {count_color};")
            row_layout.addWidget(total_lbl)

            # Per-speed breakdown
            detail_lbl = QLabel(
                f"  (slow:{sc['slow']}  med:{sc['medium']}  fast:{sc['fast']})"
            )
            detail_lbl.setFont(QFont("Courier New", 8))
            detail_lbl.setStyleSheet("color: #4A5A4A;")
            row_layout.addWidget(detail_lbl)
            row_layout.addStretch()

            self._count_list_layout.insertWidget(
                self._count_list_layout.count() - 1,   # before the trailing stretch
                row_widget
            )

    # ── Overlay plot ──────────────────────────────────────────────────────────

    def _update_overlay_plot(self, samples: np.ndarray, filenames: list):
        """
        Rebuild the overlay plot from loaded samples.

        For each sample: compute mean of the 10 finger channels per frame →
        one scalar per frame → one line on the plot.
        Color by speed tag extracted from filename.
        Alpha 0.3 for individual lines, thick white mean on top.
        Zone boundary lines for the active speed filter (not for 'all').
        """
        self._overlay_plot.clear()

        n     = len(samples)
        alpha = max(30, min(150, int(200 / max(n, 1))))

        all_combined = []   # collect per-sample combined arrays for mean line

        for i_sample, (sample, fname) in enumerate(zip(samples, filenames)):
            # Mean of 10 finger channels per frame: shape (60,)
            combined = sample[:, _FINGER_INDICES].mean(axis=1)
            all_combined.append(combined)

            # Color by speed
            from dataset.dataset_manager import _extract_speed
            speed = _extract_speed(fname)
            r, g, b = _SPEED_COLORS.get(speed, (180, 180, 180))
            pen = pg.mkPen(color=(r, g, b, alpha), width=1.2)
            self._overlay_plot.plot(x=_FRAME_X, y=combined.tolist(), pen=pen)

        # Thick white mean line on top
        if all_combined:
            mean_combined = np.mean(np.stack(all_combined, axis=0), axis=0)
            mean_pen = pg.mkPen(color=(255, 255, 255, 255), width=2.5)
            self._overlay_plot.plot(x=_FRAME_X, y=mean_combined.tolist(), pen=mean_pen)

        # Zone boundary dashed lines (only when a specific speed is selected)
        if self._speed_filter != 'all' and self._speed_filter in SPEED_ZONES:
            zones = SPEED_ZONES[self._speed_filter]
            # Boundary between start and transition
            x1 = zones['start'][1]       # = zones['transition'][0]
            # Boundary between transition and end
            x2 = zones['transition'][1]  # = zones['end'][0]

            dash_pen = pg.mkPen(color='#6A6A6A', width=1, style=Qt.DashLine)
            for x_pos, label_text in [(x1, "start|transition"), (x2, "transition|end")]:
                line = pg.InfiniteLine(
                    pos=x_pos, angle=90, pen=dash_pen,
                    label=label_text,
                    labelOpts={'color': '#6A6A6A', 'position': 0.92, 'rotateAxis': (1, 0)}
                )
                self._overlay_plot.addItem(line)

    # ── Outlier table ─────────────────────────────────────────────────────────

    def _update_outlier_table(self, label: str):
        """Run outlier detection on ALL samples (ignores speed filter) and populate table."""
        self._clear_outlier_table()
        outliers = self.analyzer.detect_outliers(label)

        if not outliers:
            self._outlier_status.setText("No outliers detected.")
            return

        self._outlier_status.setText(f"{len(outliers)} outlier(s) flagged.")
        self._outlier_table.setRowCount(len(outliers))

        for row, o in enumerate(outliers):
            items = [
                QTableWidgetItem(o['filename']),
                QTableWidgetItem(o['feature']),
                QTableWidgetItem(f"{o['z_score']:.2f}"),
                QTableWidgetItem(f"{o['value']:.3f}"),
                QTableWidgetItem(f"{o['mean']:.3f}"),
            ]
            if o['z_score'] >= 3.5:
                items[2].setForeground(QColor("#FF2A2A"))
            else:
                items[2].setForeground(QColor("#FF8C00"))

            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self._outlier_table.setItem(row, col, item)

    def _clear_outlier_table(self):
        self._outlier_table.setRowCount(0)
        self._outlier_status.setText("")

    def _delete_selected_outlier(self):
        """Delete the file corresponding to the selected outlier row."""
        selected_rows = self._outlier_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Select a row to delete.")
            return

        row = self._outlier_table.currentRow()
        if row < 0:
            return

        filename = self._outlier_table.item(row, 0).text()
        label    = self._label_combo.currentText().upper()

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete this sample?\n\n"
            f"Label:   {label}\n"
            f"File:    {filename}\n\n"
            f"This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # dm.dataset_path is the profile path; file is in LABEL subfolder
        filepath = os.path.join(self.dm.dataset_path, label, filename)
        try:
            os.remove(filepath)
            logger.info(f"Deleted outlier sample: {filepath}")
        except OSError as e:
            QMessageBox.critical(self, "Delete Failed", f"Could not delete file:\n{e}")
            return

        self.refresh()
        self._run_analysis()

    # ── Stats table ───────────────────────────────────────────────────────────

    def _update_stats_table(self, label: str):
        """Compute and display per-feature statistics across all samples."""
        stats = self.analyzer.compute_stats(label)
        if stats is None:
            self._clear_stats_table()
            return

        mean = stats['mean']
        std  = stats['std']

        for i in range(NUM_FEATURES):
            self._stats_table.setItem(i, 0, QTableWidgetItem(FEATURE_ORDER[i]))
            self._stats_table.setItem(i, 1, QTableWidgetItem(f"{mean[i]:.4f}"))

            std_item = QTableWidgetItem(f"{std[i]:.4f}")
            if std[i] > 0.15:
                std_item.setForeground(QColor("#39FF14"))
            elif std[i] > 0.05:
                std_item.setForeground(QColor("#E8E000"))
            else:
                std_item.setForeground(QColor("#5A6A5A"))

            for col in range(3):
                item = self._stats_table.item(i, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)
            self._stats_table.setItem(i, 2, std_item)
            std_item.setTextAlignment(Qt.AlignCenter)

    def _clear_stats_table(self):
        for i in range(NUM_FEATURES):
            for col in range(1, 3):
                self._stats_table.setItem(i, col, QTableWidgetItem("—"))
