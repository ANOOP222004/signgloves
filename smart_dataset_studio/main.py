#!/usr/bin/env python3
# =============================================================
# Smart Glove Dataset Studio - main.py
# Phase 3 Entry Point — Sensor Dashboard UI
#
# Startup sequence (order is critical — do not change):
#   1. Create QApplication        ← must exist before any widget
#   2. Install Ctrl+C handler     ← before event loop starts
#   3. select_port()              ← input() safe, serial not started
#   4. Start serial thread        ← NO MORE input() after this point
#   5. time.sleep(2.0)            ← ESP32 stabilise
#   6. drain_queue()              ← discard startup noise
#   7. CalibrationWizard          ← GUI dialog, reads Queue directly
#   8. Start processing thread    ← connects signals to MainWindow
#   9. Show MainWindow            ← live sensor display
#  10. app.exec_()                ← Qt event loop runs
#  11. Stop processing thread     ← .stop() then .wait()
#  12. Stop serial thread         ← .stop() then .join()
#
# Phase 3 is complete when:
#   [ ] App opens → calibration wizard runs → main window appears
#   [ ] Bend prototype finger → R_T value updates live on screen
#   [ ] Status bar shows ~30 Hz
# =============================================================

import queue
import time
import logging
import sys
import signal

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from config import QUEUE_MAX_SIZE
from communication.serial_thread import SerialThread
from processing.processing_thread import ProcessingThread
from ui.main_window import MainWindow
from ui.calibration_wizard import CalibrationWizard
from ui.recorder_panel import RecorderPanel
from ui.dataset_panel import DatasetPanel
from recording.gesture_recorder import GestureRecorder
from dataset.dataset_manager import DatasetManager
from voice.voice_listener import VoiceListener

# --- Logging ---
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("main")


def select_port():
    """Lists available ports and asks user to select one."""
    ports = SerialThread.list_ports()

    if not ports:
        print("\n[ERROR] No serial ports found.")
        print("  -> Make sure ESP32 is plugged in via USB")
        sys.exit(1)

    print("\nAvailable serial ports:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p}")

    if len(ports) == 1:
        print(f"\nAuto-selecting only available port: {ports[0]}")
        return ports[0]

    while True:
        try:
            choice = int(input("\nSelect port number: "))
            if 0 <= choice < len(ports):
                return ports[choice]
        except (ValueError, KeyboardInterrupt):
            pass
        print("Invalid choice, try again.")


def countdown(seconds: int, message: str):
    """
    Print a countdown timer without blocking the Queue.
    Uses time.sleep(1) per second — serial thread keeps running freely.
    """
    for i in range(seconds, 0, -1):
        print(f"  {message} — {i}...", end='\r')
        time.sleep(1)
    print(f"  {message} — Recording!   ")


def drain_queue(frame_queue: queue.Queue):
    """Discard all frames currently in the queue."""
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except queue.Empty:
            break


def main():
    # QApplication required for any window/widget to render.
    # Phase 2 used QCoreApplication (no UI). Phase 3 upgrades to QApplication.
    # Must be created before any QWidget, QDialog, or QThread that uses signals.
    app = QApplication(sys.argv)

    # ── Clean Ctrl+C shutdown ─────────────────────────────────────────
    # Qt catches SIGINT internally and doesn't pass it to Python cleanly.
    # Fix: route SIGINT → app.quit(), which exits the event loop cleanly.
    # QTimer fires every 200ms to give Python a chance to check for signals
    # (Python signal handlers only run when Python bytecode is executing,
    # not while Qt's C++ event loop is blocking).
    signal.signal(signal.SIGINT, lambda *args: app.quit())
    ctrlc_timer = QTimer()
    ctrlc_timer.start(200)
    ctrlc_timer.timeout.connect(lambda: None)

    # ── Step 1: Select serial port ────────────────────────────────────
    # input() is safe here — serial thread not started yet.
    # QApplication exists but no window is showing yet.
    port = select_port()

    # ── Step 2: Start serial thread ───────────────────────────────────
    # NO MORE input() calls after this point.
    # Once the serial thread is running, the Queue starts filling.
    # Any blocking input() would stall the main thread, cause Queue
    # overflow, and flood the console with "Queue full" warnings.
    frame_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)
    serial_thread = SerialThread(port, frame_queue)
    serial_thread.start()
    logger.info(f"Serial thread started on {port}")

    # ── Step 3: Wait for ESP32 to stabilise ──────────────────────────
    # ESP32 sends garbage bytes on startup before settling into the
    # packet protocol. sleep(2.0) lets it stabilise, then drain_queue()
    # discards any noise frames that arrived during that window.
    time.sleep(2.0)
    drain_queue(frame_queue)

    # ── Step 4: Calibration wizard ────────────────────────────────────
    # QDialog.exec_() blocks here until the user finishes calibration.
    # The wizard reads from frame_queue directly (ProcessingThread hasn't
    # started yet — calibration needs raw ADC values, not processed ones).
    # Returns (profile_name, CalibrationData) on success, (None, None) on cancel.
    wizard = CalibrationWizard(frame_queue)
    profile_name, calibration_data = wizard.run_wizard()

    if calibration_data is None:
        # User cancelled calibration — exit cleanly
        serial_thread.stop()
        serial_thread.join(timeout=2)
        sys.exit(0)

    # ── Step 5: Build Phase 4 objects ─────────────────────────────────
    # DatasetManager now takes profile_name so every saved file is tagged
    # with who recorded it: anoop_sample_001.csv, teammate1_sample_001.csv etc.
    dataset_manager = DatasetManager(profile_name=profile_name)
    recorder        = GestureRecorder()

    # VoiceListener is constructed here but NOT started.
    # It starts only when the user clicks the 🎤 Voice OFF button in the UI.
    # Constructing it here (not inside RecorderPanel) keeps threading concerns
    # in main.py — the same pattern used for SerialThread and ProcessingThread.
    voice_listener = VoiceListener()

    # ── Step 5b: Build panels ─────────────────────────────────────────
    recorder_panel = RecorderPanel(recorder, dataset_manager, voice_listener)
    dataset_panel  = DatasetPanel(dataset_manager)

    # Wire sample_saved → dataset_panel.refresh()
    recorder_panel.sample_saved.connect(dataset_panel.refresh)

    # Wire voice listener signals → recorder_panel slots
    # Done here (not inside RecorderPanel) so VoiceListener stays
    # decoupled from RecorderPanel — same reason ProcessingThread
    # signals are wired in main.py rather than inside the panels.
    voice_listener.command_detected.connect(recorder_panel.on_voice_command)
    voice_listener.error_occurred.connect(recorder_panel.on_voice_error)

    # ── Step 5c: Build main window ────────────────────────────────────
    window = MainWindow(recorder_panel=recorder_panel, dataset_panel=dataset_panel)
    window.set_connected(True)

    # ── Step 6: Start processing thread ──────────────────────────────
    # Connect signals BEFORE start() — avoids a race condition where the
    # thread emits a signal before the slot is connected.
    processing_thread = ProcessingThread(frame_queue, calibration_data)
    processing_thread.frame_ready.connect(window.on_frame_ready)
    processing_thread.status_message.connect(window.on_status_message)

    # Phase 4 — frame intake for gesture recorder
    # GestureRecorder.on_frame() is called on every processed frame.
    # It ignores frames when not recording (is_idle state) — no cost.
    processing_thread.frame_ready.connect(recorder.on_frame)

    # Phase 4 — frame drop detection during recording
    # If a drop occurs while recording, GestureRecorder discards the buffer
    # and emits capture_failed → RecorderPanel shows warning.
    processing_thread.frame_drop_detected.connect(recorder.on_frame_drop)

    # Phase 4 — RecorderPanel tells ProcessingThread when recording starts/stops
    # set_recording(True/False) controls whether frame drops are fatal.
    recorder_panel.recording_started.connect(
        lambda: processing_thread.set_recording(True)
    )
    recorder_panel.recording_stopped.connect(
        lambda: processing_thread.set_recording(False)
    )

    # Phase 4 — reset EMA filters at the start of each recording
    # Prevents stale filter state from a previous gesture bleeding into
    # the first few frames of the new capture.
    recorder_panel.recording_started.connect(processing_thread.reset_filters)

    processing_thread.start()

    # ── Step 7: Show window and run event loop ────────────────────────
    window.setWindowTitle(
        f"Smart Glove Dataset Studio  —  {profile_name}"
    )
    window.show()

    # app.exec_() runs until app.quit() is called (by Ctrl+C or window close)
    app.exec_()

    # ── Step 8: Clean shutdown ────────────────────────────────────────
    # Stop voice listener first — it has no dependencies on other threads.
    voice_listener.stop()
    voice_listener.wait()

    # Stop processing thread before serial thread.
    processing_thread.stop()
    processing_thread.wait()
    serial_thread.stop()
    serial_thread.join(timeout=2)
    logger.info("All threads stopped. Goodbye.")


if __name__ == "__main__":
    main()
