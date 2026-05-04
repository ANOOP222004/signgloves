# ui/calibration_tab.py
#
# CalibrationTab — inline calibration UI, replacing the startup wizard.
#
# What this does:
#   - Profile management: create, select, and load named user profiles
#   - Guides user through open-hand and closed-hand capture steps
#   - Shows current calibration values (min ADC, max ADC, range per finger)
#   - Saves calibration to disk and notifies ProcessingThread via signal
#   - Blocks recording (via calibration_updated signal) until calibrated
#
# How it gets raw ADC values:
#   ProcessingThread emits raw_frame_ready before filtering/normalization.
#   CalibrationTab connects to this signal and collects frames when
#   the user clicks a Capture button. No direct Queue access needed.
#   ProcessingThread keeps running normally during capture — no pausing.
#
# Why not reuse CalibrationWizard?
#   CalibrationWizard is a blocking QDialog designed for startup.
#   CalibrationTab is a persistent QWidget that lives inside the tab bar.
#   They share the same underlying logic (CalibrationData, save/load from
#   calibration.py) but have different UI lifecycles.
#   CalibrationWizard is kept in the codebase — just no longer called at startup.

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from processing.calibration import (
    CalibrationData,
    save_calibration,
    load_calibration,
    get_today_calibration_path,
    list_profiles,
    create_profile,
)
from config import FINGER_CHANNELS

# How many raw frames to average per calibration step.
# 30 frames at 30 Hz = 1 second of data.
# Averaging smooths out ADC noise — more reliable than a single reading.
CALIBRATION_FRAMES = 30

# Sentinel string in the profile dropdown meaning "create a new profile"
CREATE_NEW_OPTION = "+ Create new profile"


class CalibrationTab(QWidget):
    """
    Inline calibration panel with profile management and live capture.

    Signals:
        calibration_updated(CalibrationData):
            Emitted after a successful save.
            main.py connects this to:
              - processing_thread.update_calibration()  ← swaps in new data
              - recorder_panel.set_calibrated(True)     ← enables Record button

    Usage (from main.py):
        cal_tab = CalibrationTab()
        processing_thread.raw_frame_ready.connect(cal_tab.on_raw_frame)
        cal_tab.calibration_updated.connect(processing_thread.update_calibration)
        cal_tab.calibration_updated.connect(recorder_panel.on_calibration_done)
    """

    # Carries the new CalibrationData after a successful save.
    calibration_updated = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Accumulates raw frames during a capture step.
        # None = not currently capturing.
        self._collecting       = False
        self._collected_frames = []
        self._collect_target   = CALIBRATION_FRAMES
        self._collect_step     = None   # 'open' or 'closed'

        # Holds min/max values as they are recorded.
        self._calibration_data = CalibrationData()

        # Track which step is done — both must complete before Save is enabled.
        self._open_done   = False
        self._closed_done = False

        # Current profile name — set when user confirms profile selection.
        self._profile_name = None

        self._build_ui()
        self._refresh_profile_dropdown()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self):
        """
        Layout:
            ├── Profile section
            ├── Status banner
            ├── Capture section (Step 1 + Step 2)
            ├── Current values table
            └── Save button
        """
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        root.addWidget(self._build_profile_section())
        root.addWidget(self._build_status_banner())
        root.addWidget(self._build_capture_section())
        root.addWidget(self._build_values_table())
        root.addWidget(self._build_save_section())
        root.addStretch()

    def _build_profile_section(self) -> QGroupBox:
        group = QGroupBox("Profile")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        # Dropdown row
        combo_row = QHBoxLayout()
        combo_row.addWidget(QLabel("Profile:"))

        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumHeight(28)
        self._profile_combo.currentTextChanged.connect(self._on_profile_changed)
        combo_row.addWidget(self._profile_combo, stretch=1)

        self._load_btn = QPushButton("Load")
        self._load_btn.setMinimumWidth(70)
        self._load_btn.clicked.connect(self._on_load_profile)
        combo_row.addWidget(self._load_btn)

        layout.addLayout(combo_row)

        # New profile name input — only visible when CREATE_NEW_OPTION selected
        self._new_name_input = QLineEdit()
        self._new_name_input.setPlaceholderText("Enter new profile name  (e.g. anoop)")
        self._new_name_input.setMinimumHeight(28)
        self._new_name_input.setVisible(False)
        layout.addWidget(self._new_name_input)

        return group

    def _build_status_banner(self) -> QFrame:
        """
        Prominent banner showing calibration state.

        Not calibrated → orange warning background
        Calibrated     → green success background
        """
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setMinimumHeight(44)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 6, 12, 6)

        self._status_label = QLabel("⚠  Not calibrated — complete Steps 1 and 2, then Save.")
        self._status_label.setFont(QFont("Arial", 10, QFont.Bold))
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)

        self._banner_frame = frame
        self._set_banner_uncalibrated()

        return frame

    def _build_capture_section(self) -> QGroupBox:
        group = QGroupBox("Capture")
        layout = QHBoxLayout(group)
        layout.setSpacing(16)

        # Step 1 — Open hand
        step1 = QVBoxLayout()
        step1_title = QLabel("Step 1 — Open Hand")
        step1_title.setFont(QFont("Arial", 9, QFont.Bold))
        step1.addWidget(step1_title)

        step1_desc = QLabel(
            "Spread all fingers fully open.\n"
            "Hold the position, then click Capture."
        )
        step1_desc.setWordWrap(True)
        step1_desc.setStyleSheet("color: #555555;")
        step1.addWidget(step1_desc)

        self._open_status = QLabel("Not captured")
        self._open_status.setStyleSheet("color: gray; font-style: italic;")
        step1.addWidget(self._open_status)

        self._open_btn = QPushButton("⏺  Capture Open Hand")
        self._open_btn.setMinimumHeight(34)
        self._open_btn.clicked.connect(self._on_capture_open)
        step1.addWidget(self._open_btn)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setStyleSheet("color: #cccccc;")

        # Step 2 — Closed hand
        step2 = QVBoxLayout()
        step2_title = QLabel("Step 2 — Closed Hand")
        step2_title.setFont(QFont("Arial", 9, QFont.Bold))
        step2.addWidget(step2_title)

        step2_desc = QLabel(
            "Bend all fingers fully closed.\n"
            "Hold the position, then click Capture."
        )
        step2_desc.setWordWrap(True)
        step2_desc.setStyleSheet("color: #555555;")
        step2.addWidget(step2_desc)

        self._closed_status = QLabel("Not captured")
        self._closed_status.setStyleSheet("color: gray; font-style: italic;")
        step2.addWidget(self._closed_status)

        self._closed_btn = QPushButton("⏺  Capture Closed Hand")
        self._closed_btn.setMinimumHeight(34)
        self._closed_btn.clicked.connect(self._on_capture_closed)
        step2.addWidget(self._closed_btn)

        layout.addLayout(step1)
        layout.addWidget(divider)
        layout.addLayout(step2)

        return group

    def _build_values_table(self) -> QGroupBox:
        """
        Table showing current calibration values per finger.

        Columns: Finger | Min ADC (open) | Max ADC (closed) | Range
        One row per finger per hand (10 rows total).

        Why show this table?
            It makes calibration transparent. You can immediately see if a
            sensor has a suspiciously small range (bad mounting) or if one
            finger's values look wrong compared to the others.
            It also confirms that the capture worked — values update live
            after each step.
        """
        group = QGroupBox("Current Calibration Values")
        layout = QVBoxLayout(group)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Finger", "Min ADC (open)", "Max ADC (closed)", "Range"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setMinimumHeight(200)

        # Build rows — 5 fingers × 2 hands = 10 rows
        hands   = ['right', 'left']
        rows    = []
        for hand in hands:
            for ch in FINGER_CHANNELS:
                rows.append((hand, ch))

        self._table.setRowCount(len(rows))
        self._table_rows = rows   # store for updates

        for i, (hand, ch) in enumerate(rows):
            display = f"{hand.capitalize()} {ch.capitalize()}"
            self._table.setItem(i, 0, QTableWidgetItem(display))
            self._table.setItem(i, 1, QTableWidgetItem("—"))
            self._table.setItem(i, 2, QTableWidgetItem("—"))
            self._table.setItem(i, 3, QTableWidgetItem("—"))

        layout.addWidget(self._table)
        return group

    def _build_save_section(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self._save_btn = QPushButton("💾  Save Calibration")
        self._save_btn.setMinimumHeight(38)
        self._save_btn.setFont(QFont("Arial", 10, QFont.Bold))
        self._save_btn.setEnabled(False)   # enabled only when both steps done
        self._save_btn.clicked.connect(self._on_save)

        layout.addStretch()
        layout.addWidget(self._save_btn)
        layout.addStretch()

        return widget

    # ── Profile logic ─────────────────────────────────────────────────

    def _refresh_profile_dropdown(self):
        """
        Reload the dropdown from disk.

        Auto-load behaviour:
          - If profiles exist on disk, select the first one and immediately
            set self._profile_name — no Load click required.
          - If today's calibration exists for that profile, load it and
            emit calibration_updated so the pipeline is live immediately.
          - If no profiles exist yet, show CREATE_NEW_OPTION and the name input.

        Why auto-load?
          The user sees their profile name already selected in the dropdown
          and reasonably expects it to be active. Requiring a Load click
          before Capture works is confusing and unnecessary on subsequent runs.
        """
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        profiles = list_profiles()
        for name in profiles:
            self._profile_combo.addItem(name)
        self._profile_combo.addItem(CREATE_NEW_OPTION)
        self._profile_combo.blockSignals(False)

        if profiles:
            # Profiles exist — auto-select and auto-load the first one.
            # This means on every app start, the first profile is immediately
            # active without requiring any user interaction.
            first_profile = profiles[0]
            self._profile_combo.setCurrentIndex(0)
            self._profile_name = first_profile
            self._new_name_input.setVisible(False)

            # Check for today's calibration — load silently if found.
            today_path = get_today_calibration_path(first_profile)
            if today_path:
                self._calibration_data = load_calibration(today_path)
                self._mark_both_captured()
                self._update_table()
                self._set_banner_calibrated(first_profile)
                # Use QTimer.singleShot(0) to defer the emit until AFTER
                # main.py has finished wiring all signal connections.
                # If we emit here during __init__, the connections don't exist
                # yet — ProcessingThread and RecorderPanel would never receive it.
                # singleShot(0) posts the emit to the event loop queue.
                # It fires on the very first event loop tick after app.exec_()
                # starts — by which time all connections in main.py are live.
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0, lambda: self.calibration_updated.emit(self._calibration_data))
            else:
                # Profile exists but no today's calibration — ready to capture.
                self._reset_capture_state()
                self._set_banner_uncalibrated()
        else:
            # No profiles yet — first run. Show create-new input immediately.
            self._new_name_input.setVisible(True)

    def _on_profile_changed(self, text: str):
        """Show/hide new-name input depending on selection."""
        self._new_name_input.setVisible(text == CREATE_NEW_OPTION)
        self._new_name_input.clear()

    def _on_load_profile(self):
        """
        Load button clicked.

        Three cases:
          1. CREATE_NEW_OPTION selected → validate name → create folder → reset steps
          2. Existing profile, today's calibration exists → load it → mark calibrated
          3. Existing profile, no today's calibration → reset steps, ready to capture
        """
        selected = self._profile_combo.currentText()

        if selected == CREATE_NEW_OPTION:
            name = self._new_name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "Name Required", "Please enter a profile name.")
                return
            forbidden = set('/\\:*?"<>|')
            if any(ch in forbidden for ch in name):
                QMessageBox.warning(self, "Invalid Name",
                                    "Profile name cannot contain:  / \\ : * ? \" < > |")
                return
            if name in list_profiles():
                QMessageBox.warning(self, "Already Exists",
                                    f"Profile '{name}' already exists. Select it from the dropdown.")
                return
            create_profile(name)
            self._profile_name = name
            self._refresh_profile_dropdown()
            # Select the new profile in the dropdown
            idx = self._profile_combo.findText(name)
            if idx >= 0:
                self._profile_combo.setCurrentIndex(idx)
            self._reset_capture_state()
            self._set_banner_uncalibrated()

        else:
            self._profile_name = selected
            today_path = get_today_calibration_path(self._profile_name)

            if today_path:
                reply = QMessageBox.question(
                    self,
                    "Calibration Found",
                    f"Today's calibration exists for profile '{self._profile_name}'.\n\n"
                    f"Load it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    self._calibration_data = load_calibration(today_path)
                    self._mark_both_captured()
                    self._update_table()
                    self._set_banner_calibrated(self._profile_name)
                    # Notify pipeline immediately — user doesn't need to press Save again
                    self.calibration_updated.emit(self._calibration_data)
                    return

            # No today's calibration — ready for fresh capture
            self._reset_capture_state()
            self._set_banner_uncalibrated()

    # ── Voice command public slot ─────────────────────────────────────

    def on_voice_command(self, command: str):
        if command == "open":
            self._on_capture_open()
        elif command == "closed":
            self._on_capture_closed()
        elif command == "calibrate":
            self._on_save()

    # ── Raw frame intake ──────────────────────────────────────────────

    def on_raw_frame(self, raw_frame: dict):
        """
        Slot connected to ProcessingThread.raw_frame_ready signal.

        Called 30 Hz on the main thread. When _collecting is True,
        accumulates frames until _collect_target is reached, then
        computes averages and completes the capture step.

        When _collecting is False (the normal state), this returns
        immediately — zero cost, one boolean check.
        """
        if not self._collecting:
            return

        self._collected_frames.append(raw_frame)

        remaining = self._collect_target - len(self._collected_frames)

        if self._collect_step == 'open':
            self._open_status.setText(
                f"Collecting… {len(self._collected_frames)}/{self._collect_target}"
            )
        else:
            self._closed_status.setText(
                f"Collecting… {len(self._collected_frames)}/{self._collect_target}"
            )

        if len(self._collected_frames) >= self._collect_target:
            self._finish_capture()

    # ── Capture logic ─────────────────────────────────────────────────

    def _on_capture_open(self):
        """User clicked Capture Open Hand — begin collecting frames."""
        if self._profile_name is None:
            QMessageBox.warning(self, "No Profile",
                                "Please load or create a profile first.")
            return

        self._collected_frames = []
        self._collect_step     = 'open'
        self._collecting       = True

        self._open_btn.setEnabled(False)
        self._closed_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._open_status.setText("Collecting…  0/30")
        self._open_status.setStyleSheet("color: blue;")

    def _on_capture_closed(self):
        """User clicked Capture Closed Hand — begin collecting frames."""
        if self._profile_name is None:
            QMessageBox.warning(self, "No Profile",
                                "Please load or create a profile first.")
            return

        self._collected_frames = []
        self._collect_step     = 'closed'
        self._collecting       = True

        self._open_btn.setEnabled(False)
        self._closed_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._closed_status.setText("Collecting…  0/30")
        self._closed_status.setStyleSheet("color: blue;")

    def _finish_capture(self):
        """
        Called when enough frames have been collected.

        Averages all collected frames per channel → sets min or max
        in CalibrationData → updates the table → re-enables buttons.
        """
        self._collecting = False
        frames = self._collected_frames

        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                avg = sum(f[hand][ch] for f in frames) / len(frames)
                if self._collect_step == 'open':
                    self._calibration_data.set_min(hand, ch, avg)
                else:
                    self._calibration_data.set_max(hand, ch, avg)

        if self._collect_step == 'open':
            self._open_done = True
            r_thumb_avg = sum(f['right']['thumb'] for f in frames) / len(frames)
            self._open_status.setText(f"✓ Captured  (R_Thumb ≈ {r_thumb_avg:.0f} ADC)")
            self._open_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self._closed_done = True
            r_thumb_avg = sum(f['right']['thumb'] for f in frames) / len(frames)
            self._closed_status.setText(f"✓ Captured  (R_Thumb ≈ {r_thumb_avg:.0f} ADC)")
            self._closed_status.setStyleSheet("color: green; font-weight: bold;")

        self._update_table()

        # Re-enable buttons — allow re-capturing either step if needed
        self._open_btn.setEnabled(True)
        self._closed_btn.setEnabled(True)

        # Enable Save only when BOTH steps are done
        if self._open_done and self._closed_done:
            self._save_btn.setEnabled(True)

    # ── Save ──────────────────────────────────────────────────────────

    def _on_save(self):
        """
        Save calibration to disk and notify the pipeline.

        After this:
          - JSON file written to data/calibration/<profile>/calibration_<date>.json
          - calibration_updated signal emitted with new CalibrationData
          - ProcessingThread swaps in new calibration immediately
          - Record button becomes enabled
          - Banner turns green
        """
        if not self._profile_name:
            return

        saved_path = save_calibration(self._calibration_data, self._profile_name)
        self._set_banner_calibrated(self._profile_name)
        self.calibration_updated.emit(self._calibration_data)

        QMessageBox.information(
            self,
            "Calibration Saved",
            f"Calibration saved for profile '{self._profile_name}'.\n\n"
            f"File: {saved_path}\n\n"
            f"Recording is now enabled."
        )

    # ── Table update ──────────────────────────────────────────────────

    def _update_table(self):
        """
        Refresh the calibration values table from current CalibrationData.

        Rows are in the same order as self._table_rows (right then left, all 5 fingers).
        Range column shows max-min in ADC counts — a quick quality indicator.
        A range below ~200 counts usually means the sensor isn't moving much,
        which may indicate a mounting problem.
        """
        for i, (hand, ch) in enumerate(self._table_rows):
            min_val = self._calibration_data.min_values[hand][ch]
            max_val = self._calibration_data.max_values[hand][ch]

            if min_val is None or max_val is None:
                self._table.setItem(i, 1, QTableWidgetItem("—"))
                self._table.setItem(i, 2, QTableWidgetItem("—"))
                self._table.setItem(i, 3, QTableWidgetItem("—"))
            else:
                rng = abs(max_val - min_val)

                item_min   = QTableWidgetItem(f"{min_val:.0f}")
                item_max   = QTableWidgetItem(f"{max_val:.0f}")
                item_range = QTableWidgetItem(f"{rng:.0f}")

                # Colour-code range: green = good, orange = marginal, red = poor
                if rng >= 500:
                    item_range.setForeground(QColor("#006600"))   # green — good range
                elif rng >= 200:
                    item_range.setForeground(QColor("#cc6600"))   # orange — marginal
                else:
                    item_range.setForeground(QColor("#cc0000"))   # red — poor range

                self._table.setItem(i, 1, item_min)
                self._table.setItem(i, 2, item_max)
                self._table.setItem(i, 3, item_range)

    # ── Banner helpers ────────────────────────────────────────────────

    def _set_banner_calibrated(self, profile_name: str):
        from datetime import datetime
        date_str = datetime.now().strftime('%d %b %Y')
        self._status_label.setText(
            f"✓  Calibrated  —  profile: {profile_name}  —  {date_str}"
        )
        self._banner_frame.setStyleSheet(
            "QFrame { background-color: #d4edda; border: 1px solid #28a745; border-radius: 4px; }"
        )
        self._status_label.setStyleSheet("color: #155724;")

    def _set_banner_uncalibrated(self):
        self._status_label.setText(
            "⚠  Not calibrated — complete Steps 1 and 2, then Save."
        )
        self._banner_frame.setStyleSheet(
            "QFrame { background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; }"
        )
        self._status_label.setStyleSheet("color: #856404;")

    # ── State helpers ─────────────────────────────────────────────────

    def _reset_capture_state(self):
        """Reset both capture steps to 'not captured' state."""
        self._calibration_data = CalibrationData()
        self._open_done        = False
        self._closed_done      = False
        self._collecting       = False
        self._collected_frames = []

        self._open_status.setText("Not captured")
        self._open_status.setStyleSheet("color: gray; font-style: italic;")
        self._closed_status.setText("Not captured")
        self._closed_status.setStyleSheet("color: gray; font-style: italic;")

        self._open_btn.setEnabled(True)
        self._closed_btn.setEnabled(True)
        self._save_btn.setEnabled(False)

        self._update_table()

    def _mark_both_captured(self):
        """Mark both steps as done — used when loading existing calibration."""
        self._open_done   = True
        self._closed_done = True
        self._open_status.setText("✓ Loaded from file")
        self._open_status.setStyleSheet("color: green; font-weight: bold;")
        self._closed_status.setText("✓ Loaded from file")
        self._closed_status.setStyleSheet("color: green; font-weight: bold;")
        self._save_btn.setEnabled(True)
