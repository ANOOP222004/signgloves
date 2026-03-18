# processing/processing_thread.py
#
# Processing Thread — the pipeline between serial data and the UI.
#
# Why this exists:
#   Raw frames arrive from serial_thread via a Queue at 30 Hz.
#   Each frame needs filtering, normalization, and drop detection
#   before the UI can display it or the recorder can save it.
#   This work happens on a dedicated thread so the UI never stutters.
#
# What this thread does per frame:
#   1. Pull Raw Frame from Queue
#   2. Apply EMA filter (smooths ADC noise)
#   3. Apply calibration normalization (maps to 0.0-1.0)
#   4. Detect frame drops via frame_id gaps
#   5. Emit Processed Frame to UI via Qt Signal
#
# Thread communication rules (never break these):
#   serial_thread  -> Queue         -> this thread  (raw frames in)
#   this thread    -> Qt Signal     -> main thread  (processed frames out)
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
        thread.frame_ready.connect(some_function)
        thread.start()
    """

    # Qt Signal — emitted every time a clean processed frame is ready.
    # Carries the processed frame dict as its payload.
    # 'object' type means it can carry any Python object (our dict).
    frame_ready = pyqtSignal(object)

    # Qt Signal — emitted when a frame drop is detected during recording.
    # Carries the number of dropped frames as an integer.
    # The gesture recorder (Phase 4) listens to this to discard the sample.
    frame_drop_detected = pyqtSignal(int)

    # Qt Signal — emitted for status messages (warnings, errors).
    # The UI status bar (Phase 3) listens to this.
    status_message = pyqtSignal(str)

    def __init__(self, frame_queue: queue.Queue, calibration_data: CalibrationData):
        """
        Args:
            frame_queue:      Queue fed by serial_thread with Raw Frame dicts
            calibration_data: CalibrationData with min/max per finger channel
        """
        super().__init__()

        self.frame_queue = frame_queue
        self.calibrator = Calibrator(calibration_data)

        # Create one EMAFilter instance per sensor channel.
        # 5 fingers x 2 hands = 10 finger filters
        # 3 IMU values x 2 hands = 6 IMU filters
        # Total: 16 independent filter instances
        # Each holds its own previous_filtered state — they never share state.
        self.filters = {
            hand: {ch: EMAFilter() for ch in FINGER_CHANNELS + IMU_CHANNELS}
            for hand in ['right', 'left']
        }

        # Track the last seen frame_id for drop detection.
        # None = no frame received yet — first frame seeds it.
        self.last_frame_id = None

        # Recording state flag.
        # When True, any frame drop triggers frame_drop_detected signal.
        # Set by gesture recorder (Phase 4) via set_recording().
        self.is_recording = False

        # Running flag — controls the main loop.
        # Set to False by stop() to cleanly exit the thread.
        self._running = False

    def set_recording(self, recording: bool):
        """
        Tell the processing thread whether a gesture recording is active.

        Called by the gesture recorder (Phase 4):
            thread.set_recording(True)   # recording started
            thread.set_recording(False)  # recording stopped

        Why this matters: frame drops are only fatal during recording.
        Outside recording, a drop is just a logged warning.
        During recording, a drop means the 60-frame window is corrupted
        and the sample must be discarded immediately.
        """
        self.is_recording = recording

    def reset_filters(self):
        """
        Reset all 16 EMA filters to uninitialised state.

        Call this when:
        - Serial connection drops and reconnects
        - A new calibration profile is loaded
        - A new recording session begins

        Why: stale filter state from a previous session bleeds into
        the first few frames of a new session, producing incorrect
        normalized values at the start of a gesture recording.
        """
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS + IMU_CHANNELS:
                self.filters[hand][ch].reset()

    def stop(self):
        """
        Signal the thread to stop cleanly.

        Sets _running = False. The run() loop checks this flag and exits.
        Always call thread.wait() after stop() to block until fully stopped.
        """
        self._running = False

    def run(self):
        """
        Main thread loop — runs until stop() is called.

        Called automatically by QThread.start().
        Never call run() directly — always call start().
        """
        self._running = True

        while self._running:
            try:
                # Block up to 0.1 seconds waiting for a frame.
                # Timeout prevents hanging forever when stop() is called.
                raw_frame = self.frame_queue.get(timeout=0.1)

            except queue.Empty:
                # No frame in 0.1s — normal during startup or pause.
                # Loop back and check _running flag.
                continue

            # Frame received — process it
            self._process_frame(raw_frame)

    def _process_frame(self, raw_frame: dict):
        """
        Process one raw frame through the full pipeline.

        Steps:
            1. Detect frame drops via frame_id gap
            2. Apply EMA filter to all 16 channels
            3. Apply calibration normalization
            4. Emit processed frame via Qt Signal

        Args:
            raw_frame: Raw Frame dict from serial_thread:
                {
                    'frame_id': int,
                    'right': {'thumb': int, ..., 'pitch': float, ...},
                    'left':  {'thumb': int, ..., 'pitch': float, ...}
                }
        """
        current_id = raw_frame['frame_id']

        # Step 1: Frame drop detection
        if self.last_frame_id is not None:
            # FRAME_ID_MAX = 9999 (max value the ID reaches).
            # Modulo must be FRAME_ID_MAX + 1 = 10000 so that:
            #   (9999 + 1) % 10000 = 0  (correct rollover)
            #   (9999 + 1) % 9999  = 1  (wrong — skips frame 9999)
            expected_id = (self.last_frame_id + 1) % (FRAME_ID_MAX + 1)

            if current_id != expected_id:
                # Calculate how many frames were dropped
                if current_id > expected_id:
                    dropped = current_id - expected_id
                else:
                    # Rollover case: e.g. last=9998, current=1
                    dropped = (FRAME_ID_MAX + 1 - expected_id) + current_id

                self.status_message.emit(
                    f"WARNING: {dropped} frame(s) dropped "
                    f"(expected {expected_id}, got {current_id})"
                )

                # If recording is active, sample is corrupted — discard it
                if self.is_recording:
                    self.frame_drop_detected.emit(dropped)

        # Update last seen frame_id
        self.last_frame_id = current_id

        # Step 2: Apply EMA filter to all 16 channels
        # Must happen BEFORE normalization — filtering raw ADC integers
        # first prevents clipping artifacts at the 0.0/1.0 boundaries.
        filtered_frame = {
            'frame_id': current_id,
            'right': {},
            'left': {},
        }

        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS + IMU_CHANNELS:
                raw_value = raw_frame[hand][ch]
                filtered_value = self.filters[hand][ch].update(raw_value)
                filtered_frame[hand][ch] = filtered_value

        # Step 3: Apply calibration normalization
        # Finger channels: maps filtered ADC to 0.0-1.0
        # IMU channels:    passes filtered degrees through unchanged
        processed_frame = self.calibrator.normalize_frame(filtered_frame)

        # Step 4: Emit processed frame
        # Qt routes this safely to the main thread.
        # Phase 2 test: connected to a print function
        # Phase 3+:     connected to UI labels and signal plots
        self.frame_ready.emit(processed_frame)
