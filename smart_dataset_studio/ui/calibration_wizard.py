# ui/calibration_wizard.py
#
# Calibration Wizard — GUI calibration dialog with multi-user profile support.
#
# What this does:
#   - Shows a profile selector (dropdown of existing profiles + "Create new")
#   - If today's calibration exists for selected profile: ask use/redo
#   - Guides user through open-hand and closed-hand calibration steps
#   - Saves calibration to data/calibration/<profile>/calibration_<date>.json
#   - Returns (profile_name, CalibrationData) to main.py
#
# Why profiles matter:
#   Each team member has different hand geometry and sensor placement.
#   A calibration from one person applied to another produces wrong
#   normalized values — the model sees garbage. Named profiles ensure
#   each person always uses their own calibration data.
#
# Why a QDialog with exec_():
#   Blocks the caller (main.py) until calibration is complete.
#   Nothing else should happen until we have valid calibration data.
#
# Why a worker QThread for frame collection:
#   Collecting 30 frames takes ~1 second. Running this in a button slot
#   would freeze the Qt event loop. The worker collects in the background
#   and signals the result back to the dialog on the main thread.
#
# Why this reads the Queue directly (not via ProcessingThread):
#   ProcessingThread hasn't started yet at calibration time.
#   Calibration needs raw ADC values to record min/max ranges.

import queue

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QFrame,
    QStackedWidget,
    QWidget,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from processing.calibration import (
    CalibrationData,
    save_calibration,
    load_calibration,
    get_today_calibration_path,
    list_profiles,
    create_profile,
)
from config import FINGER_CHANNELS

# How many frames to average per calibration step (1 second at 30 Hz)
CALIBRATION_FRAMES = 30

# Timeout waiting for one frame — if exceeded, ESP32 is likely disconnected
FRAME_TIMEOUT_SECONDS = 2.0

# Sentinel value in dropdown meaning "I want to create a new profile"
CREATE_NEW_OPTION = "+ Create new profile"


# ─────────────────────────────────────────────────────────────────────────────
# Worker thread — collects frames without blocking the UI
# ─────────────────────────────────────────────────────────────────────────────

class FrameCollectorThread(QThread):
    """
    Background thread that collects a fixed number of frames from the Queue.

    Why this exists:
        Collecting 30 frames takes ~1 second. Running this in a button
        slot would freeze the Qt event loop (window goes white).
        This thread collects in the background and signals the result
        back to the dialog on the main thread.

    Signals:
        collection_done(list):  all frames collected, carries frame list
        collection_error(str):  timeout occurred, carries error message
    """

    collection_done  = pyqtSignal(object)
    collection_error = pyqtSignal(str)

    def __init__(self, frame_queue: queue.Queue, num_frames: int):
        super().__init__()
        self.frame_queue = frame_queue
        self.num_frames  = num_frames

    def run(self):
        frames = []
        for _ in range(self.num_frames):
            try:
                frame = self.frame_queue.get(timeout=FRAME_TIMEOUT_SECONDS)
                frames.append(frame)
            except queue.Empty:
                self.collection_error.emit(
                    "No data received from ESP32.\n\n"
                    "Check that the ESP32 is connected and the\n"
                    "serial thread is running."
                )
                return
        self.collection_done.emit(frames)


# ─────────────────────────────────────────────────────────────────────────────
# Calibration Wizard Dialog
# ─────────────────────────────────────────────────────────────────────────────

class CalibrationWizard(QDialog):
    """
    Multi-step calibration dialog with profile selection.

    Usage from main.py:
        wizard = CalibrationWizard(frame_queue)
        profile_name, cal_data = wizard.run_wizard()
        # Returns (None, None) if user cancelled

    Pages (managed by QStackedWidget):
        0 — Profile selector
        1 — Open hand step
        2 — Closed hand step
        3 — Done summary
    """

    def __init__(self, frame_queue: queue.Queue):
        super().__init__()

        self.frame_queue      = frame_queue
        self.calibration_data = CalibrationData()
        self._collector       = None
        self._profile_name    = None    # set when user confirms profile

        self.setWindowTitle("Calibration Wizard")
        self.setMinimumWidth(440)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

        self._build_ui()

    # ── Public API ────────────────────────────────────────────────────

    def run_wizard(self):
        """
        Entry point called from main.py.

        Returns:
            (profile_name: str, CalibrationData) on success
            (None, None) if user cancelled
        """
        result_code = self.exec_()
        if result_code == QDialog.Accepted:
            return self._profile_name, self.calibration_data
        return None, None

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self):
        """
        Build the dialog with a shared title, QStackedWidget for page content,
        and a shared button row at the bottom.

        Why QStackedWidget?
            We need four different content views (profile select, open hand,
            closed hand, done). QStackedWidget holds all four and shows
            only one at a time — much cleaner than hiding/showing widgets.
        """
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Title — fixed, never changes
        title = QLabel("Calibration Wizard")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # Page content area
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_profile_page())   # index 0
        self._stack.addWidget(self._build_open_page())      # index 1
        self._stack.addWidget(self._build_closed_page())    # index 2
        self._stack.addWidget(self._build_done_page())      # index 3
        self._stack.setCurrentIndex(0)
        main_layout.addWidget(self._stack)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(divider)

        # Shared button row
        button_row = QHBoxLayout()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setMinimumWidth(100)
        self._cancel_btn.clicked.connect(self._on_cancel)

        self._action_btn = QPushButton("Continue")
        self._action_btn.setMinimumWidth(120)
        self._action_btn.setDefault(True)   # responds to Enter key

        button_row.addWidget(self._cancel_btn)
        button_row.addStretch()
        button_row.addWidget(self._action_btn)
        main_layout.addLayout(button_row)

    def _build_profile_page(self) -> QWidget:
        """
        Page 0: Profile selection.

        Dropdown contains all existing profiles (from list_profiles())
        plus CREATE_NEW_OPTION at the bottom.
        When CREATE_NEW_OPTION is selected, a name input field appears.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        instruction = QLabel(
            "Select your profile to load your personal calibration,\n"
            "or create a new profile if this is your first time."
        )
        instruction.setWordWrap(True)
        instruction.setAlignment(Qt.AlignCenter)
        layout.addWidget(instruction)

        # Profile dropdown
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumHeight(30)
        self._populate_profile_dropdown()
        self._profile_combo.currentTextChanged.connect(
            self._on_profile_selection_changed
        )
        layout.addWidget(self._profile_combo)

        # New profile name input — hidden unless CREATE_NEW_OPTION is selected.
        # On first run (no profiles exist), CREATE_NEW_OPTION is the default
        # selection so currentTextChanged never fires — show input immediately.
        self._new_profile_input = QLineEdit()
        self._new_profile_input.setPlaceholderText(
            "Enter profile name  (e.g. anoop)"
        )
        # Show immediately if CREATE_NEW_OPTION is already selected (first run)
        is_create_new = (self._profile_combo.currentText() == CREATE_NEW_OPTION)
        self._new_profile_input.setVisible(is_create_new)
        self._new_profile_input.setMinimumHeight(30)
        layout.addWidget(self._new_profile_input)

        layout.addStretch()
        return page

    def _build_open_page(self) -> QWidget:
        """Page 1: Open-hand instruction + live status."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        self._open_instruction = QLabel(
            "Step 1 of 2\n\n"
            "Open your hand fully.\n"
            "Spread all fingers as wide as possible.\n\n"
            "Hold that position, then click Ready."
        )
        self._open_instruction.setWordWrap(True)
        self._open_instruction.setAlignment(Qt.AlignCenter)
        self._open_instruction.setFont(QFont("Arial", 11))
        layout.addWidget(self._open_instruction)

        self._open_status = QLabel("")
        self._open_status.setAlignment(Qt.AlignCenter)
        self._open_status.setStyleSheet("color: gray;")
        layout.addWidget(self._open_status)

        # Shows R_Thumb ADC reading during collection — visual confirmation
        # that the sensor is actually responding
        self._open_thumb_label = QLabel("")
        self._open_thumb_label.setAlignment(Qt.AlignCenter)
        self._open_thumb_label.setFont(QFont("Courier", 10))
        self._open_thumb_label.setVisible(False)
        layout.addWidget(self._open_thumb_label)

        layout.addStretch()
        return page

    def _build_closed_page(self) -> QWidget:
        """Page 2: Closed-hand instruction + live status."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        self._closed_instruction = QLabel(
            "Step 2 of 2\n\n"
            "Close your hand fully.\n"
            "Bend all fingers as far as they will go.\n\n"
            "Hold that position, then click Ready."
        )
        self._closed_instruction.setWordWrap(True)
        self._closed_instruction.setAlignment(Qt.AlignCenter)
        self._closed_instruction.setFont(QFont("Arial", 11))
        layout.addWidget(self._closed_instruction)

        self._closed_status = QLabel("")
        self._closed_status.setAlignment(Qt.AlignCenter)
        self._closed_status.setStyleSheet("color: gray;")
        layout.addWidget(self._closed_status)

        self._closed_thumb_label = QLabel("")
        self._closed_thumb_label.setAlignment(Qt.AlignCenter)
        self._closed_thumb_label.setFont(QFont("Courier", 10))
        self._closed_thumb_label.setVisible(False)
        layout.addWidget(self._closed_thumb_label)

        layout.addStretch()
        return page

    def _build_done_page(self) -> QWidget:
        """Page 3: Completion summary — filled in when calibration finishes."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        self._done_label = QLabel("")
        self._done_label.setWordWrap(True)
        self._done_label.setAlignment(Qt.AlignCenter)
        self._done_label.setFont(QFont("Arial", 11))
        layout.addWidget(self._done_label)

        layout.addStretch()
        return page

    # ── Profile page logic ────────────────────────────────────────────

    def _populate_profile_dropdown(self):
        """
        Fill the dropdown with existing profiles + CREATE_NEW_OPTION.

        On first run (no profiles exist): only CREATE_NEW_OPTION appears.
        On subsequent runs: profiles listed alphabetically, then create option.
        """
        self._profile_combo.clear()
        for name in list_profiles():
            self._profile_combo.addItem(name)
        self._profile_combo.addItem(CREATE_NEW_OPTION)

        # If profiles exist, first profile is the default selection
        # If no profiles, CREATE_NEW_OPTION is selected — correct for first run
        if self._profile_combo.count() > 1:
            self._profile_combo.setCurrentIndex(0)

    def _on_profile_selection_changed(self, text: str):
        """Show the name input field when CREATE_NEW_OPTION is selected."""
        is_creating = (text == CREATE_NEW_OPTION)
        self._new_profile_input.setVisible(is_creating)
        self._new_profile_input.clear()
        self.adjustSize()    # resize dialog to accommodate shown/hidden input

    def _on_continue_from_profile(self):
        """
        [Continue] clicked on profile page.

        Three outcomes:
            1. New profile name entered → validate → create folder → open-hand step
            2. Existing profile, today's cal exists → ask use/redo
            3. Existing profile, no today's cal → go straight to open-hand step
        """
        selected = self._profile_combo.currentText()

        if selected == CREATE_NEW_OPTION:
            new_name = self._new_profile_input.text().strip()

            if not new_name:
                QMessageBox.warning(self, "Profile Name Required",
                                    "Please enter a name for the new profile.")
                return

            # Block characters that would break folder creation
            forbidden = set('/\\:*?"<>|')
            if any(ch in forbidden for ch in new_name):
                QMessageBox.warning(self, "Invalid Name",
                                    "Profile name cannot contain these characters:\n"
                                    "/  \\  :  *  ?  \"  <  >  |")
                return

            if new_name in list_profiles():
                QMessageBox.warning(self, "Profile Already Exists",
                                    f"A profile named '{new_name}' already exists.\n"
                                    f"Select it from the dropdown instead.")
                return

            create_profile(new_name)         # makes data/calibration/<name>/
            self._profile_name = new_name
            self._go_to_open_step()

        else:
            # Existing profile
            self._profile_name = selected
            today_path = get_today_calibration_path(self._profile_name)

            if today_path:
                reply = QMessageBox.question(
                    self,
                    "Calibration Found",
                    f"Profile:  {self._profile_name}\n\n"
                    f"A calibration file exists for today.\n"
                    f"Use existing calibration?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    self.calibration_data = load_calibration(today_path)
                    self.accept()    # skip wizard steps, return immediately
                    return

            self._go_to_open_step()

    # ── Wizard step logic ─────────────────────────────────────────────

    def _go_to_open_step(self):
        """Switch to Page 1 and wire button to collect open-hand frames."""
        self._stack.setCurrentIndex(1)
        self._action_btn.setText("Ready")
        self._wire_action_btn(self._collect_open_frames)

    def _collect_open_frames(self):
        """Disable button, start FrameCollectorThread for open-hand step."""
        self._action_btn.setEnabled(False)
        self._open_status.setText("Collecting frames...")
        self._open_thumb_label.setVisible(True)
        self._open_thumb_label.setText("R_Thumb: reading...")

        self._collector = FrameCollectorThread(self.frame_queue, CALIBRATION_FRAMES)
        self._collector.collection_done.connect(self._on_open_frames_done)
        self._collector.collection_error.connect(self._on_collection_error)
        self._collector.start()

    def _on_open_frames_done(self, frames: list):
        """
        Average 30 open-hand frames → set_min() for all finger channels.
        Advance to closed-hand step.

        Why average 30 frames?
            Any single frame has ADC noise (±10–20 counts).
            Averaging 30 frames at rest gives a stable baseline.
            The same approach used in the Phase 2 console calibration.
        """
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                avg = sum(f[hand][ch] for f in frames) / len(frames)
                self.calibration_data.set_min(hand, ch, avg)

        r_thumb_open = sum(f['right']['thumb'] for f in frames) / len(frames)
        self._open_thumb_label.setText(f"R_Thumb open: {r_thumb_open:.1f} ADC")
        self._open_status.setText(f"✓ Open hand recorded ({len(frames)} frames)")

        self._stack.setCurrentIndex(2)
        self._action_btn.setText("Ready")
        self._action_btn.setEnabled(True)
        self._wire_action_btn(self._collect_closed_frames)

    def _collect_closed_frames(self):
        """Disable button, start FrameCollectorThread for closed-hand step."""
        self._action_btn.setEnabled(False)
        self._closed_status.setText("Collecting frames...")
        self._closed_thumb_label.setVisible(True)
        self._closed_thumb_label.setText("R_Thumb: reading...")

        self._collector = FrameCollectorThread(self.frame_queue, CALIBRATION_FRAMES)
        self._collector.collection_done.connect(self._on_closed_frames_done)
        self._collector.collection_error.connect(self._on_collection_error)
        self._collector.start()

    def _on_closed_frames_done(self, frames: list):
        """
        Average 30 closed-hand frames → set_max() → save → show done page.
        """
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                avg = sum(f[hand][ch] for f in frames) / len(frames)
                self.calibration_data.set_max(hand, ch, avg)

        r_thumb_closed = sum(f['right']['thumb'] for f in frames) / len(frames)
        self._closed_thumb_label.setText(
            f"R_Thumb closed: {r_thumb_closed:.1f} ADC"
        )
        self._closed_status.setText(
            f"✓ Closed hand recorded ({len(frames)} frames)"
        )

        # Save to data/calibration/<profile>/calibration_<date>.json
        saved_path = save_calibration(self.calibration_data, self._profile_name)

        self._done_label.setText(
            f"✓ Calibration complete!\n\n"
            f"Profile:  {self._profile_name}\n"
            f"Saved:  {saved_path}\n\n"
            f"Click Finish to open the dashboard."
        )
        self._stack.setCurrentIndex(3)
        self._action_btn.setText("Finish")
        self._action_btn.setEnabled(True)
        self._wire_action_btn(self.accept)

    def _on_collection_error(self, message: str):
        """Show error popup and re-enable Ready button for retry."""
        QMessageBox.critical(self, "Collection Error", message)

        if self._stack.currentIndex() == 1:
            self._open_status.setText("Error — check connection and try again.")
            self._open_thumb_label.setVisible(False)
        else:
            self._closed_status.setText("Error — check connection and try again.")
            self._closed_thumb_label.setVisible(False)

        self._action_btn.setEnabled(True)

    # ── Helpers ───────────────────────────────────────────────────────

    def _wire_action_btn(self, slot):
        """
        Disconnect previous slot then connect new slot to action button.

        The action button changes role at every step:
            Profile page  → _on_continue_from_profile
            Open hand     → _collect_open_frames
            Closed hand   → _collect_closed_frames
            Done          → self.accept

        Without disconnecting first, Qt stacks connections and every
        previous handler fires on every subsequent click.
        """
        try:
            self._action_btn.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass    # no previous connection — PyQt5 raises TypeError, PyQt6 raises RuntimeError
        self._action_btn.clicked.connect(slot)

    def showEvent(self, event):
        """Wire the initial Continue button when dialog first appears."""
        super().showEvent(event)
        if self._stack.currentIndex() == 0:
            self._wire_action_btn(self._on_continue_from_profile)

    def _on_cancel(self):
        """Confirm before cancelling — exits the application if confirmed."""
        reply = QMessageBox.question(
            self,
            "Cancel Calibration",
            "Cancelling calibration will close the application.\n\n"
            "Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.reject()
