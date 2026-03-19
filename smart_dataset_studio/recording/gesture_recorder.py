# recording/gesture_recorder.py
#
# GestureRecorder — state machine for capturing exactly 60-frame gesture samples.
#
# What this does:
#   Manages the lifecycle of one gesture recording:
#     IDLE → CAPTURING → COMPLETE (or back to IDLE on drop/discard)
#
#   - Receives every processed frame from ProcessingThread via on_frame()
#   - Accumulates frames into an internal buffer when CAPTURING
#   - Emits progress updates so the UI can show "Frames: 12 / 60"
#   - Emits capture_complete when 60 frames are collected
#   - Discards immediately on frame_drop_detected signal
#   - Handles early stop: pads buffer to WINDOW_SIZE by repeating last frame
#
# What this does NOT do:
#   - Never saves to disk (that is DatasetManager's job)
#   - Never touches the UI directly (communicates only via Qt Signals)
#   - Never reads from the Queue (it receives frames via on_frame() slot)
#
# State machine:
#   IDLE      → start_recording() → CAPTURING
#   CAPTURING → 60 frames received → emit capture_complete → COMPLETE
#   CAPTURING → frame drop detected → emit capture_failed → IDLE
#   CAPTURING → stop_recording() called early → pad → emit capture_complete → COMPLETE
#   COMPLETE  → discard() → IDLE
#   COMPLETE  → (RecorderPanel calls DatasetManager.save_sample) → IDLE
#
# Why a class with Qt Signals rather than a plain function?
#   Recording takes ~2 seconds. The UI must remain live during that time
#   (sensor values still update, status bar still works). A blocking loop
#   would freeze everything. Qt Signals let the recorder send results back
#   to the UI without the UI ever having to wait.

from PyQt5.QtCore import QObject, pyqtSignal
from config import WINDOW_SIZE


# Recording states — used internally to gate which operations are valid.
# Using string constants instead of an Enum keeps the code readable without
# requiring an import. The values are never used externally — only the
# is_recording() and is_complete() methods are public.
_STATE_IDLE      = "IDLE"
_STATE_CAPTURING = "CAPTURING"
_STATE_COMPLETE  = "COMPLETE"


class GestureRecorder(QObject):
    """
    State machine that captures exactly WINDOW_SIZE frames per gesture sample.

    Inherits from QObject (not QThread) because GestureRecorder does NOT
    run on its own thread — it is driven by incoming Qt Signals from
    ProcessingThread. It lives on the main thread and reacts to events.

    Why QObject and not a plain class?
        QObject is required to define and emit Qt Signals. Plain Python
        classes cannot have pyqtSignal attributes.

    Signals:
        progress_updated(int, int):    (frames_captured, total_frames)
                                       emitted on every frame while CAPTURING
        capture_complete(list):        emitted when WINDOW_SIZE frames collected
                                       carries the full frame buffer
        capture_failed(str):           emitted when recording is aborted
                                       carries a human-readable reason string

    Usage:
        recorder = GestureRecorder()
        recorder.progress_updated.connect(panel.on_progress)
        recorder.capture_complete.connect(panel.on_capture_complete)
        recorder.capture_failed.connect(panel.on_capture_failed)

        # When ProcessingThread emits frame_ready:
        processing_thread.frame_ready.connect(recorder.on_frame)

        # When ProcessingThread detects a drop during recording:
        processing_thread.frame_drop_detected.connect(recorder.on_frame_drop)

        # To start a recording:
        recorder.start_recording()

        # To stop early (user pressed Stop before 60 frames):
        recorder.stop_recording()

        # After capture_complete fires and user presses Discard:
        recorder.discard()
    """

    # Emitted every frame while CAPTURING.
    # Carries (frames_captured, total_needed) — UI shows "Frames: 12 / 60"
    progress_updated = pyqtSignal(int, int)

    # Emitted when exactly WINDOW_SIZE frames have been collected.
    # Carries the complete list of processed frame dicts.
    # RecorderPanel receives this and offers Save / Discard.
    capture_complete = pyqtSignal(list)

    # Emitted when recording is aborted (frame drop or explicit discard).
    # Carries a human-readable reason string for display in the UI.
    capture_failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self._state  = _STATE_IDLE
        self._buffer = []    # accumulates processed frame dicts during CAPTURING

    # ── State queries ─────────────────────────────────────────────────

    def is_idle(self) -> bool:
        return self._state == _STATE_IDLE

    def is_recording(self) -> bool:
        return self._state == _STATE_CAPTURING

    def is_complete(self) -> bool:
        return self._state == _STATE_COMPLETE

    # ── Control methods ───────────────────────────────────────────────

    def start_recording(self):
        """
        Begin a new recording session.

        Transitions: IDLE → CAPTURING

        Raises:
            RuntimeError if called when not IDLE (prevents double-starts).
            The caller (RecorderPanel) must disable the Record button while
            CAPTURING or COMPLETE to prevent this in normal use.
        """
        if self._state != _STATE_IDLE:
            raise RuntimeError(
                f"start_recording() called in state {self._state}. "
                f"Must be IDLE."
            )

        self._buffer = []           # clear any leftover state
        self._state  = _STATE_CAPTURING

    def stop_recording(self):
        """
        Stop recording early — before WINDOW_SIZE frames have been collected.

        Pads the buffer to exactly WINDOW_SIZE by repeating the final frame,
        then emits capture_complete with the padded buffer.

        Transitions: CAPTURING → COMPLETE

        Why repeat the final frame instead of zero-padding?
            Zero (0.0 for all fingers) means "fully open hand, neutral IMU" —
            a real physical state. Zero-padding teaches the model that every
            gesture ends with an open hand, which is wrong.
            Repeating the final frame means "the gesture held this position" —
            a realistic approximation. The model learns to ignore the held pose
            at the end of a gesture naturally.

        Why allow early stop at all?
            Signs naturally vary in duration. Some gestures complete their
            motion in 30 frames. Forcing the user to hold a fixed pose for
            the remaining 30 frames just to fill the window produces stiff,
            unnatural training data. Stopping early and padding is better.

        Raises:
            RuntimeError if called when not CAPTURING.
            RuntimeError if buffer is empty (nothing was captured at all —
            this would produce a sample of 60 identical frames with no information).
        """
        if self._state != _STATE_CAPTURING:
            raise RuntimeError(
                f"stop_recording() called in state {self._state}. "
                f"Must be CAPTURING."
            )

        if not self._buffer:
            # No frames at all — can't pad from nothing.
            # This shouldn't happen in normal use (Record button → user
            # immediately presses Stop), but guard it explicitly.
            self._state = _STATE_IDLE
            self.capture_failed.emit("Stopped before any frames were captured.")
            return

        # Pad to exactly WINDOW_SIZE by repeating the last frame.
        last_frame = self._buffer[-1]
        while len(self._buffer) < WINDOW_SIZE:
            self._buffer.append(last_frame)   # same dict reference — no deep copy needed

        self._state = _STATE_COMPLETE
        self.capture_complete.emit(list(self._buffer))   # send a copy

    def discard(self):
        """
        Discard the current buffer and return to IDLE.

        Called by RecorderPanel when:
        - User presses Discard after a capture completes
        - A frame drop is detected during recording (via on_frame_drop)

        Transitions: any state → IDLE
        """
        self._buffer = []
        self._state  = _STATE_IDLE

    # ── Frame intake slots ────────────────────────────────────────────

    def on_frame(self, processed_frame: dict):
        """
        Slot connected to ProcessingThread.frame_ready signal.

        Called 30 times per second from the main thread (Qt routes signals
        to the main thread by default). Appends the frame to the buffer
        when CAPTURING, ignores frames otherwise.

        Args:
            processed_frame: Processed Frame dict from processing_thread
                             {'frame_id': int, 'right': {...}, 'left': {...}}
        """
        if self._state != _STATE_CAPTURING:
            return    # not recording — ignore this frame silently

        self._buffer.append(processed_frame)
        captured = len(self._buffer)

        # Emit progress so UI can show "Frames: N / 60"
        self.progress_updated.emit(captured, WINDOW_SIZE)

        # Auto-stop at exactly WINDOW_SIZE frames
        if captured >= WINDOW_SIZE:
            self._state = _STATE_COMPLETE
            self.capture_complete.emit(list(self._buffer))   # send a copy

    def on_frame_drop(self, dropped_count: int):
        """
        Slot connected to ProcessingThread.frame_drop_detected signal.

        A frame drop during recording means the 60-frame window has a gap.
        The temporal pattern the BiLSTM would train on is corrupted.
        Immediate discard is the only correct response.

        Why not just skip the gap and keep recording?
            The BiLSTM trains on sequences where time is continuous — frame N+1
            always follows frame N by exactly 33ms. A gap breaks this assumption.
            If gap-skipping were allowed, the model would occasionally train on
            samples where time jumps — producing confusing gradient signals.
            The accuracy hit from a few corrupted samples is subtle and hard
            to diagnose. Discarding is simple, honest, and correct.

        Args:
            dropped_count: number of frames dropped (from ProcessingThread)
        """
        if self._state != _STATE_CAPTURING:
            return    # drop outside recording — not our problem, ignore

        # Discard buffer
        self._buffer = []
        self._state  = _STATE_IDLE

        reason = (
            f"{dropped_count} frame(s) dropped during recording. "
            f"Sample discarded — please try again."
        )
        self.capture_failed.emit(reason)
