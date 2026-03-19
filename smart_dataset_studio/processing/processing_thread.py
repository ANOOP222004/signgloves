# processing/processing_thread.py
#
# Processing Thread — the pipeline between serial data and the UI.
#
# Phase 5 (tabbed UI) additions vs Phase 4:
#   - raw_frame_ready signal: emits the raw frame BEFORE filtering/normalization.
#     Used by CalibrationTab to capture open/closed hand ADC values without
#     needing direct Queue access or pausing the thread.
#   - update_calibration(): swaps in new CalibrationData at runtime.
#     Called by CalibrationTab after the user saves a new calibration.
#     Thread-safe via Python's GIL — object reference assignment is atomic.
#
# Everything else is identical to Phase 4.
#
# Thread communication rules (never break these):
#   serial_thread  -> Queue              -> this thread  (raw frames in)
#   this thread    -> raw_frame_ready    -> CalibrationTab (raw ADC for capture)
#   this thread    -> frame_ready        -> UI / recorder (processed frames out)
#   this thread    -> frame_drop_detected -> GestureRecorder (drop alert)
#   this thread    -> status_message     -> MainWindow status bar
#   Never touch UI directly from this thread.

import queue
from PyQt5.QtCore import QThread, pyqtSignal
from processing.filter import EMAFilter
from processing.calibration import Calibrator, CalibrationData
from config import (
    FINGER_CHANNELS,
    IMU_CHANNELS,
    FRAME_ID_MAX,
)


class ProcessingThread(QThread):
    """
    Dedicated thread that filters, normalizes, and validates raw sensor frames.

    Inherits from QThread (not Python's threading.Thread) because:
    - QThread integrates with PyQt5's signal/slot system
    - Signals emitted from QThread are automatically routed to the main
      thread safely — this is PyQt5's built-in thread safety mechanism
    - Python's threading.Thread cannot emit Qt Signals safely

    Usage:
        thread = ProcessingThread(frame_queue, calibration_data)
        thread.raw_frame_ready.connect(calibration_tab.on_raw_frame)
        thread.frame_ready.connect(some_function)
        thread.start()
    """

    # Emitted BEFORE filtering/normalization — carries raw ADC integers.
    # Used by CalibrationTab to record open/closed hand positions.
    # Why emit raw? Calibration needs to see the sensor's actual ADC output
    # to record min/max ranges. After normalization those values would
    # already be mapped through the OLD calibration — useless for recording a new one.
    raw_frame_ready = pyqtSignal(object)

    # Emitted AFTER filtering and normalization — carries processed floats 0.0-1.0.
    # Used by everything else: sensor labels, signal plots, gesture recorder.
    frame_ready = pyqtSignal(object)

    # Emitted when a frame drop is detected during recording.
    # Carries the number of dropped frames as an integer.
    frame_drop_detected = pyqtSignal(int)

    # Emitted for status messages (warnings, errors).
    # The UI status bar listens to this.
    status_message = pyqtSignal(str)

    def __init__(self, frame_queue: queue.Queue, calibration_data: CalibrationData):
        """
        Args:
            frame_queue:      Queue fed by serial_thread with Raw Frame dicts
            calibration_data: CalibrationData with min/max per finger channel.
                              Can be an empty CalibrationData() at startup —
                              the Calibrator handles uncalibrated channels
                              safely by returning 0.0 (dummy channel protection).
        """
        super().__init__()

        self.frame_queue = frame_queue
        self.calibrator  = Calibrator(calibration_data)

        # Create one EMAFilter instance per sensor channel.
        # 5 fingers x 2 hands = 10 finger filters
        # 3 IMU values x 2 hands = 6 IMU filters
        # Total: 16 independent filter instances
        self.filters = {
            hand: {ch: EMAFilter() for ch in FINGER_CHANNELS + IMU_CHANNELS}
            for hand in ['right', 'left']
        }

        self.last_frame_id = None
        self.is_recording  = False
        self._running      = False

    # ── Public API ────────────────────────────────────────────────────

    def set_recording(self, recording: bool):
        """
        Tell the processing thread whether a gesture recording is active.

        Frame drops are only fatal during recording — outside recording,
        a drop is just a logged warning.
        """
        self.is_recording = recording

    def reset_filters(self):
        """
        Reset all 16 EMA filters to uninitialised state.

        Call when:
        - Serial connection drops and reconnects
        - A new calibration profile is loaded
        - A new recording session begins
        """
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS + IMU_CHANNELS:
                self.filters[hand][ch].reset()

    def update_calibration(self, calibration_data: CalibrationData):
        """
        Swap in new calibration data at runtime.

        Called by CalibrationTab after the user saves a new calibration.

        Thread safety:
            This method is called from the main thread.
            ProcessingThread reads self.calibrator on every frame (its own thread).
            Python's GIL guarantees that object reference assignment is atomic —
            self.calibrator = Calibrator(new_data) is a single bytecode operation.
            The processing thread either sees the old calibrator or the new one,
            never a half-constructed state. No mutex or lock needed.

        Why also reset filters?
            When calibration changes, the filter state holds smoothed values
            from the old calibration range. These stale values would blend
            with the new calibration for the first few frames, producing a
            brief incorrect output. Resetting filters ensures a clean start
            immediately after calibration is updated.

        Args:
            calibration_data: new CalibrationData with updated min/max values
        """
        self.calibrator = Calibrator(calibration_data)
        self.reset_filters()

    def stop(self):
        """Signal the thread to stop cleanly."""
        self._running = False

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self):
        """
        Main thread loop — runs until stop() is called.
        Never call run() directly — always call start().
        """
        self._running = True

        while self._running:
            try:
                raw_frame = self.frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self._process_frame(raw_frame)

    def _process_frame(self, raw_frame: dict):
        """
        Process one raw frame through the full pipeline.

        Steps:
            0. Emit raw frame for calibration capture (NEW — Phase 5 tabs)
            1. Detect frame drops via frame_id gap
            2. Apply EMA filter to all 16 channels
            3. Apply calibration normalization
            4. Emit processed frame

        Args:
            raw_frame: Raw Frame dict from serial_thread:
                {
                    'frame_id': int,
                    'right': {'thumb': int, ..., 'pitch': float, ...},
                    'left':  {'thumb': int, ..., 'pitch': float, ...}
                }
        """
        current_id = raw_frame['frame_id']

        # Step 0: Emit raw frame BEFORE any processing.
        # CalibrationTab connects to this to capture ADC min/max values.
        # All other consumers use frame_ready (the processed signal).
        # Cost: one additional signal emit per frame — negligible at 30 Hz.
        self.raw_frame_ready.emit(raw_frame)

        # Step 1: Frame drop detection
        if self.last_frame_id is not None:
            expected_id = (self.last_frame_id + 1) % (FRAME_ID_MAX + 1)

            if current_id != expected_id:
                if current_id > expected_id:
                    dropped = current_id - expected_id
                else:
                    dropped = (FRAME_ID_MAX + 1 - expected_id) + current_id

                self.status_message.emit(
                    f"WARNING: {dropped} frame(s) dropped "
                    f"(expected {expected_id}, got {current_id})"
                )

                if self.is_recording:
                    self.frame_drop_detected.emit(dropped)

        self.last_frame_id = current_id

        # Step 2: EMA filter — must happen BEFORE normalization
        filtered_frame = {
            'frame_id': current_id,
            'right': {},
            'left': {},
        }

        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS + IMU_CHANNELS:
                raw_value      = raw_frame[hand][ch]
                filtered_value = self.filters[hand][ch].update(raw_value)
                filtered_frame[hand][ch] = filtered_value

        # Step 3: Calibration normalization
        processed_frame = self.calibrator.normalize_frame(filtered_frame)

        # Step 4: Emit processed frame to all consumers
        self.frame_ready.emit(processed_frame)
