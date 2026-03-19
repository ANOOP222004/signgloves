# ui/dataset_panel.py
#
# DatasetPanel — displays sample counts per gesture label, broken down by profile.
#
# What this shows:
#   For each gesture label, shows total count and per-profile breakdown:
#
#     HELLO      12  [anoop:8  teammate1:4]
#     STOP        9  [anoop:5  teammate1:4]
#     YES         0
#     ...
#
#   This gives you full visibility into who recorded what.
#   Labels with 0 samples shown in gray. Labels with samples show
#   the profile breakdown in a smaller line below.
#
# Refresh policy:
#   refresh() re-reads all counts from disk after every save.
#   Reading from disk (not an in-memory counter) is the ground truth —
#   catches samples added by other sessions or deleted outside the app.

from PyQt5.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QWidget,
    QFrame,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from dataset.dataset_manager import DatasetManager
from config import GESTURE_LABELS


class DatasetPanel(QGroupBox):
    """
    Read-only panel showing sample counts per gesture label with profile breakdown.

    Usage:
        panel = DatasetPanel(dataset_manager)
        layout.addWidget(panel)
        panel.refresh()    # call after every successful save
    """

    def __init__(self, dataset_manager: DatasetManager):
        """
        Args:
            dataset_manager: shared DatasetManager instance (owns profile_name).
        """
        super().__init__("Dataset")

        self.dm = dataset_manager

        # Two label references per gesture:
        #   _count_labels[label]   → QLabel showing total count (e.g. "12")
        #   _detail_labels[label]  → QLabel showing profile breakdown (e.g. "anoop:8  t1:4")
        self._count_labels  = {}
        self._detail_labels = {}

        self._build_ui()
        self.refresh()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self):
        """
        Build the panel layout.

        Structure:
            QGroupBox ("Dataset")
            └── QVBoxLayout
                ├── scroll area
                │   └── one block per GESTURE_LABELS entry
                │       ├── row: label name (left) + total count (right)
                │       └── detail line: "anoop:8  teammate1:4" (gray, small)
                └── total count label (bottom)
        """
        outer_layout = QVBoxLayout(self)
        outer_layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(6)
        content_layout.setContentsMargins(0, 0, 0, 0)

        for label in GESTURE_LABELS:
            # ── Main count row ────────────────────────────────────────
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)

            name_label = QLabel(label)
            name_label.setMinimumWidth(78)
            name_label.setFont(QFont("Arial", 9))

            count_label = QLabel("0")
            count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            count_label.setMinimumWidth(28)
            count_label.setFont(QFont("Courier", 9))
            count_label.setStyleSheet("color: gray;")

            self._count_labels[label] = count_label

            row.addWidget(name_label)
            row.addWidget(count_label)

            # ── Profile detail line ───────────────────────────────────
            # Shows "anoop:8  teammate1:4" below the main row.
            # Hidden when count is 0 — only appears when samples exist.
            detail_label = QLabel("")
            detail_label.setFont(QFont("Arial", 7))
            detail_label.setStyleSheet("color: #888888; padding-left: 4px;")
            detail_label.setVisible(False)

            self._detail_labels[label] = detail_label

            # Wrap both rows in a block
            block_layout = QVBoxLayout()
            block_layout.setSpacing(1)
            block_layout.setContentsMargins(0, 0, 0, 2)
            block_layout.addLayout(row)
            block_layout.addWidget(detail_label)

            # Thin separator line between labels
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setStyleSheet("color: #e0e0e0;")

            content_layout.addLayout(block_layout)
            content_layout.addWidget(separator)

        content_layout.addStretch()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

        # ── Bottom total ──────────────────────────────────────────────
        self._total_label = QLabel("Total: 0 samples")
        self._total_label.setAlignment(Qt.AlignCenter)
        self._total_label.setFont(QFont("Arial", 9))
        self._total_label.setStyleSheet("color: gray; border-top: 1px solid #ccc;")
        outer_layout.addWidget(self._total_label)

    # ── Public API ────────────────────────────────────────────────────

    def refresh(self):
        """
        Re-read all sample counts from disk and update every label.

        Reads two things from DatasetManager:
          all_counts()         → total per label (for the count badge)
          all_profile_counts() → per-profile breakdown (for the detail line)

        Call this after every successful save.
        """
        totals   = self.dm.all_counts()
        profiles = self.dm.all_profile_counts()
        grand_total = 0

        for label in GESTURE_LABELS:
            total = totals.get(label, 0)
            grand_total += total

            count_widget  = self._count_labels[label]
            detail_widget = self._detail_labels[label]

            # ── Update count badge ────────────────────────────────────
            count_widget.setText(str(total))

            if total == 0:
                count_widget.setStyleSheet("color: gray;")
                detail_widget.setVisible(False)
            else:
                count_widget.setStyleSheet("color: black; font-weight: bold;")

                # ── Build profile detail string ───────────────────────
                # Format: "anoop:8  teammate1:4  teammate2:2"
                # Highlight current profile's count in green so the active
                # user can immediately see their own contribution.
                breakdown = profiles.get(label, {})
                parts = []
                for profile, count in sorted(breakdown.items()):
                    if profile == self.dm.profile_name:
                        # Current user's count — bold green
                        parts.append(f"[{profile}:{count}]")
                    else:
                        parts.append(f"{profile}:{count}")

                detail_widget.setText("  ".join(parts))
                detail_widget.setVisible(True)

        # ── Update grand total ────────────────────────────────────────
        self._total_label.setText(
            f"Total: {grand_total} sample{'s' if grand_total != 1 else ''}"
        )
        style = "border-top: 1px solid #ccc; "
        style += "color: black;" if grand_total > 0 else "color: gray;"
        self._total_label.setStyleSheet(style)
