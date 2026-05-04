# ui/export_tab.py
#
# ExportTab — Phase 8 ML export panel for the EXPORT tab.
#
# Layout (top to bottom):
#
#   ┌─ DATASET SUMMARY ─────────────────────────────────────────────┐
#   │  Scans ALL profiles in data/dataset/ on load.                 │
#   │  Shows totals, per-gesture counts, warnings for 0-sample      │
#   │  gestures. [⟳ Refresh] re-runs the scan.                     │
#   └───────────────────────────────────────────────────────────────┘
#
#   ┌─ EXPORT CONFIGURATION ────────────────────────────────────────┐
#   │  Output directory    [text field]  [Browse]                   │
#   │  Profiles            QListWidget (checkable, multi-select)    │
#   │  ☑ Stratified 80/10/10 split                                  │
#   │  [🚀 EXPORT]                                                  │
#   └───────────────────────────────────────────────────────────────┘
#
#   ┌─ EXPORT PROGRESS ─────────────────────────────────────────────┐
#   │  QProgressBar                                                 │
#   │  QPlainTextEdit  (scrolling log)                              │
#   └───────────────────────────────────────────────────────────────┘
#
#   ┌─ EXPORT RESULTS ──────────────────────────────────────────────┐
#   │  Shown only after a successful export.                        │
#   │  Output files + sizes; per-label table.                       │
#   └───────────────────────────────────────────────────────────────┘
#
# Threading: MLExportWorker runs the export in a QThread.
# The ExportTab only sends to the worker via constructor args (no shared
# mutable state after start). Signals flow back: progress → UI thread.

import os
import logging

import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QLineEdit,
    QCheckBox, QListWidget, QListWidgetItem,
    QProgressBar, QPlainTextEdit,
    QFileDialog, QSplitter, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from config import (
    DATASET_PATH, EXPORT_PATH,
    GESTURE_LABELS, WINDOW_SIZE, NUM_FEATURES,
    EXPORT_TRAIN_RATIO, EXPORT_VAL_RATIO, EXPORT_TEST_RATIO,
)
from dataset.dataset_manager import DatasetManager
from dataset.ml_export import MLExportWorker, _human_size

logger = logging.getLogger(__name__)

# Color thresholds — same scale used in AnalysisTab for visual consistency.
_COLOR_READY  = "#39FF14"   # green   >= 20 samples
_COLOR_WARN   = "#E8E000"   # yellow  1–19 samples
_COLOR_NONE   = "#FF4444"   # red     0 samples
_COLOR_MUTED  = "#5A6A5A"
_COLOR_NORMAL = "#A0B0A0"

_SPLIT_PCT = (
    f"{int(EXPORT_TRAIN_RATIO * 100)} / "
    f"{int(EXPORT_VAL_RATIO   * 100)} / "
    f"{int(EXPORT_TEST_RATIO  * 100)}"
)


class ExportTab(QWidget):
    """
    ML export control panel.

    Usage (in main_window.py):
        self.export_tab = ExportTab(dataset_manager)
        tabs.addTab(self.export_tab, "🚀  EXPORT")
    """

    def __init__(self, dataset_manager: DatasetManager, parent=None):
        super().__init__(parent)
        self.dm      = dataset_manager
        self._worker = None   # MLExportWorker — None when idle

        self._build_ui()
        self._scan_summary()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Outer layout: a single QScrollArea filling the tab so the user can
        # scroll down to the Results section even on small windows.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addWidget(self._build_summary_section())
        root.addWidget(self._build_config_section())
        root.addWidget(self._build_progress_section())

        self._results_group = self._build_results_section()
        self._results_group.setVisible(False)
        root.addWidget(self._results_group)

        root.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── Section 1: Dataset Summary ────────────────────────────────────────────

    def _build_summary_section(self) -> QGroupBox:
        group = QGroupBox("DATASET SUMMARY")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # Top row: headline stats + refresh button
        top = QHBoxLayout()

        self._lbl_total    = QLabel("Total: —")
        self._lbl_total.setFont(QFont("Courier New", 10, QFont.Bold))
        self._lbl_total.setStyleSheet(f"color: {_COLOR_NORMAL};")
        top.addWidget(self._lbl_total)

        self._lbl_gestures = QLabel("Gestures: —/10")
        self._lbl_gestures.setFont(QFont("Courier New", 10))
        self._lbl_gestures.setStyleSheet(f"color: {_COLOR_NORMAL};")
        top.addWidget(self._lbl_gestures)

        self._lbl_profiles = QLabel("Profiles: —")
        self._lbl_profiles.setFont(QFont("Courier New", 10))
        self._lbl_profiles.setStyleSheet(f"color: {_COLOR_MUTED};")
        top.addWidget(self._lbl_profiles)

        top.addStretch()

        refresh_btn = QPushButton("⟳  Refresh")
        refresh_btn.setMinimumHeight(26)
        refresh_btn.setMinimumWidth(90)
        refresh_btn.clicked.connect(self._scan_summary)
        top.addWidget(refresh_btn)

        outer.addLayout(top)

        # Per-gesture count grid (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setMaximumHeight(180)

        container = QWidget()
        self._gesture_grid = QVBoxLayout(container)
        self._gesture_grid.setSpacing(2)
        self._gesture_grid.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        # Warning banner — hidden when all gestures have data
        self._lbl_warning = QLabel("")
        self._lbl_warning.setStyleSheet(f"color: {_COLOR_NONE}; font-size: 10px;")
        self._lbl_warning.setWordWrap(True)
        self._lbl_warning.setVisible(False)
        outer.addWidget(self._lbl_warning)

        return group

    def _scan_summary(self):
        """Read ALL profiles from data/dataset/ and update the summary section."""
        if not os.path.isdir(DATASET_PATH):
            self._set_summary_empty("Dataset folder not found — run the app first.")
            return

        profiles = sorted(
            d for d in os.listdir(DATASET_PATH)
            if os.path.isdir(os.path.join(DATASET_PATH, d))
        )
        if not profiles:
            self._set_summary_empty("No profiles found — record some gestures first.")
            return

        label_totals: dict = {label: 0 for label in GESTURE_LABELS}
        for profile in profiles:
            for label in GESTURE_LABELS:
                label_dir = os.path.join(DATASET_PATH, profile, label)
                if os.path.isdir(label_dir):
                    label_totals[label] += sum(
                        1 for f in os.listdir(label_dir)
                        if f.endswith('.npy') or f.endswith('.csv')
                    )

        total          = sum(label_totals.values())
        gestures_ready = sum(1 for c in label_totals.values() if c > 0)
        missing        = [lb for lb, c in label_totals.items() if c == 0]

        self._lbl_total.setText(f"Total: {total}")
        self._lbl_gestures.setText(f"Gestures: {gestures_ready}/10")
        self._lbl_profiles.setText(f"Profiles: {', '.join(profiles)}")

        # Per-gesture rows
        self._rebuild_gesture_grid(label_totals)

        # Warning for zero-sample gestures
        if missing:
            self._lbl_warning.setText(
                f"WARNING — 0 samples: {', '.join(missing)}"
            )
            self._lbl_warning.setVisible(True)
        else:
            self._lbl_warning.setVisible(False)

        # Rebuild profile checkboxes in the config section
        self._rebuild_profile_list(profiles)

    def _set_summary_empty(self, msg: str):
        self._lbl_total.setText("Total: 0")
        self._lbl_gestures.setText("Gestures: 0/10")
        self._lbl_profiles.setText("Profiles: none")
        self._lbl_warning.setText(msg)
        self._lbl_warning.setVisible(True)
        self._rebuild_gesture_grid({label: 0 for label in GESTURE_LABELS})
        self._rebuild_profile_list([])

    def _rebuild_gesture_grid(self, label_totals: dict):
        """Replace per-gesture count rows with fresh data."""
        while self._gesture_grid.count():
            item = self._gesture_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for label in GESTURE_LABELS:
            count = label_totals.get(label, 0)
            if count >= 20:
                color = _COLOR_READY
            elif count > 0:
                color = _COLOR_WARN
            else:
                color = _COLOR_NONE

            row = QWidget()
            rl  = QHBoxLayout(row)
            rl.setContentsMargins(2, 0, 2, 0)
            rl.setSpacing(0)

            name_lbl = QLabel(f"{label:<12}")
            name_lbl.setFont(QFont("Courier New", 9))
            name_lbl.setStyleSheet(f"color: {_COLOR_NORMAL};")
            rl.addWidget(name_lbl)

            count_lbl = QLabel(f"{count:>4}")
            count_lbl.setFont(QFont("Courier New", 9, QFont.Bold))
            count_lbl.setStyleSheet(f"color: {color};")
            rl.addWidget(count_lbl)

            hint = ""
            if count == 0:
                hint = "  ✗ no samples — record before exporting"
            elif count < 20:
                hint = f"  ⚠ low ({count}) — aim for 20+"
            rl.addWidget(QLabel(hint) if not hint else _hint_label(hint, _COLOR_MUTED))
            rl.addStretch()

            self._gesture_grid.addWidget(row)

    # ── Section 2: Export Configuration ──────────────────────────────────────

    def _build_config_section(self) -> QGroupBox:
        group = QGroupBox("EXPORT CONFIGURATION")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # Output directory row
        dir_row = QHBoxLayout()
        dir_row.addWidget(_label("Output directory:", width=130))
        self._dir_edit = QLineEdit(EXPORT_PATH)
        self._dir_edit.setFont(QFont("Courier New", 9))
        dir_row.addWidget(self._dir_edit, stretch=1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setMinimumHeight(26)
        browse_btn.clicked.connect(self._on_browse)
        dir_row.addWidget(browse_btn)
        outer.addLayout(dir_row)

        # Profile selection
        prof_row = QHBoxLayout()
        prof_row.addWidget(_label("Include profiles:", width=130))
        self._profile_list = QListWidget()
        self._profile_list.setMaximumHeight(80)
        self._profile_list.setFont(QFont("Courier New", 9))
        self._profile_list.setToolTip("Check profiles to include. Leave all unchecked = include all.")
        prof_row.addWidget(self._profile_list, stretch=1)
        outer.addLayout(prof_row)

        # Split checkbox
        self._split_cb = QCheckBox(
            f"Stratified train / val / test split  ({_SPLIT_PCT})"
        )
        self._split_cb.setChecked(True)
        self._split_cb.setFont(QFont("Courier New", 9))
        outer.addWidget(self._split_cb)

        # Export button
        btn_row = QHBoxLayout()
        self._export_btn = QPushButton("🚀  EXPORT")
        self._export_btn.setMinimumHeight(32)
        self._export_btn.setMinimumWidth(140)
        self._export_btn.setFont(QFont("Courier New", 10, QFont.Bold))
        self._export_btn.setObjectName("record_btn")   # picks up the green style
        self._export_btn.clicked.connect(self._on_export_clicked)
        btn_row.addWidget(self._export_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        return group

    def _rebuild_profile_list(self, profiles: list):
        """Rebuild the checkable profile list widget."""
        self._profile_list.clear()
        for profile in profiles:
            item = QListWidgetItem(profile)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self._profile_list.addItem(item)

    def _on_browse(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Export Output Directory",
            self._dir_edit.text() or EXPORT_PATH,
        )
        if chosen:
            self._dir_edit.setText(chosen)

    # ── Section 3: Export Progress ────────────────────────────────────────────

    def _build_progress_section(self) -> QGroupBox:
        group = QGroupBox("EXPORT PROGRESS")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(4)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setMaximumHeight(20)
        outer.addWidget(self._progress_bar)

        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(130)
        self._log_text.setFont(QFont("Courier New", 8))
        self._log_text.setStyleSheet(
            "background: #060806; color: #7A9A7A; border: 1px solid #1A2A1A;"
        )
        outer.addWidget(self._log_text)

        return group

    # ── Section 4: Export Results ─────────────────────────────────────────────

    def _build_results_section(self) -> QGroupBox:
        group = QGroupBox("EXPORT RESULTS")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # Summary line
        self._lbl_result_summary = QLabel("")
        self._lbl_result_summary.setFont(QFont("Courier New", 9))
        self._lbl_result_summary.setStyleSheet(f"color: {_COLOR_READY};")
        outer.addWidget(self._lbl_result_summary)

        # Two-column splitter: per-label table | output files table
        splitter = QSplitter(Qt.Horizontal)

        # Per-label count table
        self._result_label_table = QTableWidget()
        self._result_label_table.setColumnCount(2)
        self._result_label_table.setHorizontalHeaderLabels(["Gesture", "Samples"])
        self._result_label_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._result_label_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._result_label_table.setAlternatingRowColors(True)
        self._result_label_table.verticalHeader().setVisible(False)
        self._result_label_table.setMaximumHeight(200)
        splitter.addWidget(self._result_label_table)

        # Output files table
        self._result_files_table = QTableWidget()
        self._result_files_table.setColumnCount(2)
        self._result_files_table.setHorizontalHeaderLabels(["File", "Size"])
        self._result_files_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._result_files_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._result_files_table.setAlternatingRowColors(True)
        self._result_files_table.verticalHeader().setVisible(False)
        self._result_files_table.setMaximumHeight(200)
        splitter.addWidget(self._result_files_table)

        outer.addWidget(splitter)
        return group

    # ── Export lifecycle ──────────────────────────────────────────────────────

    def _on_export_clicked(self):
        if self._worker is not None and self._worker.isRunning():
            return   # already running — button is disabled, shouldn't happen

        output_dir = self._dir_edit.text().strip() or EXPORT_PATH

        # Collect checked profiles (empty list = all, handled by worker)
        selected_profiles = []
        for i in range(self._profile_list.count()):
            item = self._profile_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_profiles.append(item.text())

        do_split = self._split_cb.isChecked()

        # Reset progress UI
        self._progress_bar.setValue(0)
        self._progress_bar.setMaximum(1)
        self._log_text.clear()
        self._results_group.setVisible(False)
        self._export_btn.setEnabled(False)
        self._export_btn.setText("⏳  Exporting…")

        self._worker = MLExportWorker(
            output_dir        = output_dir,
            selected_profiles = selected_profiles,
            do_split          = do_split,
            parent            = None,   # no Qt parent — we manage lifetime ourselves
        )
        # Connect BEFORE start() — see project rule
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.log_message.connect(self._on_log_message)
        self._worker.export_complete.connect(self._on_export_complete)
        self._worker.export_failed.connect(self._on_export_failed)

        self._worker.start()

    def _on_progress(self, current: int, total: int):
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_bar.setFormat(f"{current} / {total}  files")

    def _on_log_message(self, msg: str):
        self._log_text.appendPlainText(msg)
        # Auto-scroll to bottom
        sb = self._log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_export_complete(self, result: dict):
        self._export_btn.setEnabled(True)
        self._export_btn.setText("🚀  EXPORT")
        self._progress_bar.setValue(self._progress_bar.maximum())

        n       = result['total_samples']
        dur     = result['duration_seconds']
        n_files = len(result['output_files'])
        self._on_log_message(f"Done — {n} samples  {n_files} files  {dur}s")

        self._populate_results(result)
        self._results_group.setVisible(True)

    def _on_export_failed(self, error: str):
        self._export_btn.setEnabled(True)
        self._export_btn.setText("🚀  EXPORT")
        self._on_log_message(f"ERROR: {error}")

    # ── Results population ────────────────────────────────────────────────────

    def _populate_results(self, result: dict):
        n   = result['total_samples']
        dur = result['duration_seconds']
        self._lbl_result_summary.setText(
            f"Export complete — {n} samples  |  duration: {dur}s"
        )

        # Per-label table
        per_label = result['per_label']
        self._result_label_table.setRowCount(len(GESTURE_LABELS))
        for row, label in enumerate(GESTURE_LABELS):
            count = per_label.get(label, 0)
            color = _COLOR_READY if count >= 20 else (_COLOR_WARN if count > 0 else _COLOR_NONE)

            g_item = QTableWidgetItem(label)
            g_item.setTextAlignment(Qt.AlignCenter)
            c_item = QTableWidgetItem(str(count))
            c_item.setTextAlignment(Qt.AlignCenter)
            c_item.setForeground(QColor(color))

            self._result_label_table.setItem(row, 0, g_item)
            self._result_label_table.setItem(row, 1, c_item)

        # Output files table
        output_files = result['output_files']
        self._result_files_table.setRowCount(len(output_files))
        for row, fpath in enumerate(output_files):
            fname = os.path.basename(fpath)
            size  = _human_size(os.path.getsize(fpath)) if os.path.exists(fpath) else "—"

            f_item = QTableWidgetItem(fname)
            f_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            s_item = QTableWidgetItem(size)
            s_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            s_item.setFont(QFont("Courier New", 8))

            self._result_files_table.setItem(row, 0, f_item)
            self._result_files_table.setItem(row, 1, s_item)


# ── Small UI helpers ──────────────────────────────────────────────────────────

def _label(text: str, width: int = 0) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_COLOR_MUTED}; font-size: 10px;")
    if width:
        lbl.setMinimumWidth(width)
    return lbl


def _hint_label(text: str, color: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Courier New", 8))
    lbl.setStyleSheet(f"color: {color};")
    return lbl
