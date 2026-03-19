#!/usr/bin/env python3
# =============================================================
# Smart Glove Dataset Studio - main.py
# Tabbed UI — no startup wizard, calibration lives in its own tab.
#
# Changes from Phase 5 (signal plots):
#   - CalibrationWizard removed from startup sequence
#   - ProcessingThread starts with empty CalibrationData()
#   - DatasetManager profile starts as 'default', updated on cal save
#   - Four new signal connections for CalibrationTab
#   - RecorderPanel starts with Record button disabled
#
# Startup sequence:
#   1.  QApplication
#   2.  Ctrl+C handler
#   3.  select_port()
#   4.  SerialThread.start()
#   5.  time.sleep(2.0) + drain_queue()
#   6.  Build all objects
#   7.  Wire ALL signals BEFORE ProcessingThread.start()
#   8.  ProcessingThread.start()
#   9.  window.show() + app.exec_()
#   10. Clean shutdown
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
from processing.calibration import CalibrationData
from ui.main_window import MainWindow
from ui.recorder_panel import RecorderPanel
from ui.dataset_panel import DatasetPanel
from ui.style import apply_style
from recording.gesture_recorder import GestureRecorder
from dataset.dataset_manager import DatasetManager
from voice.voice_listener import VoiceListener

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("main")


def select_port():
    ports = SerialThread.list_ports()
    if not ports:
        print("\n[ERROR] No serial ports found. Check ESP32 is plugged in.")
        sys.exit(1)

    print("\nAvailable serial ports:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p}")

    if len(ports) == 1:
        print(f"\nAuto-selecting: {ports[0]}")
        return ports[0]

    while True:
        try:
            choice = int(input("\nSelect port number: "))
            if 0 <= choice < len(ports):
                return ports[choice]
        except (ValueError, KeyboardInterrupt):
            pass
        print("Invalid choice, try again.")


def drain_queue(frame_queue: queue.Queue):
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except queue.Empty:
            break


def main():
    app = QApplication(sys.argv)
    apply_style(app)   # dark theme — must be called before any widgets are created

    # Clean Ctrl+C shutdown
    signal.signal(signal.SIGINT, lambda *args: app.quit())
    ctrlc_timer = QTimer()
    ctrlc_timer.start(200)
    ctrlc_timer.timeout.connect(lambda: None)

    # Serial port selection
    port = select_port()

    # Serial thread
    frame_queue   = queue.Queue(maxsize=QUEUE_MAX_SIZE)
    serial_thread = SerialThread(port, frame_queue)
    serial_thread.start()
    logger.info(f"Serial thread started on {port}")

    time.sleep(2.0)
    drain_queue(frame_queue)

    # ── Build objects ─────────────────────────────────────────────────
    # DatasetManager starts with profile 'default'.
    # Connection #4 below updates this when the user saves a calibration.
    dataset_manager = DatasetManager(profile_name='default')
    recorder        = GestureRecorder()
    voice_listener  = VoiceListener()

    recorder_panel = RecorderPanel(recorder, dataset_manager, voice_listener)
    dataset_panel  = DatasetPanel(dataset_manager)

    recorder_panel.sample_saved.connect(dataset_panel.refresh)
    voice_listener.command_detected.connect(recorder_panel.on_voice_command)
    voice_listener.error_occurred.connect(recorder_panel.on_voice_error)

    # MainWindow creates CalibrationTab and SignalPlotWidget internally.
    # Access them via window.calibration_tab and window.plot_widget.
    window = MainWindow(recorder_panel=recorder_panel, dataset_panel=dataset_panel)
    window.set_connected(True)

    # ProcessingThread starts with EMPTY calibration.
    # All channels output 0.0 safely until calibration is saved.
    processing_thread = ProcessingThread(frame_queue, CalibrationData())

    # ── Wire ALL signals BEFORE start() ──────────────────────────────

    # Dashboard
    processing_thread.frame_ready.connect(window.on_frame_ready)
    processing_thread.status_message.connect(window.on_status_message)

    # Gesture recorder
    processing_thread.frame_ready.connect(recorder.on_frame)
    processing_thread.frame_drop_detected.connect(recorder.on_frame_drop)

    recorder_panel.recording_started.connect(
        lambda: processing_thread.set_recording(True)
    )
    recorder_panel.recording_stopped.connect(
        lambda: processing_thread.set_recording(False)
    )
    recorder_panel.recording_started.connect(processing_thread.reset_filters)

    # Signal plot
    processing_thread.frame_ready.connect(window.plot_widget.on_frame)
    recorder_panel.recording_started.connect(window.plot_widget.on_recording_started)
    recorder_panel.recording_stopped.connect(window.plot_widget.on_recording_stopped)
    recorder.progress_updated.connect(window.plot_widget.on_recording_progress)

    # ── Calibration tab — 4 connections ──────────────────────────────

    # 1. Feed raw ADC frames to CalibrationTab for min/max capture.
    processing_thread.raw_frame_ready.connect(window.calibration_tab.on_raw_frame)

    # 2. When calibration is saved, swap it into ProcessingThread immediately.
    #    update_calibration() replaces self.calibrator and resets all filters.
    window.calibration_tab.calibration_updated.connect(
        processing_thread.update_calibration
    )

    # 3. When calibration is saved, enable the Record button.
    window.calibration_tab.calibration_updated.connect(
        recorder_panel.on_calibration_done
    )

    # 4. When calibration is saved, update DatasetManager's profile name
    #    so CSV files are saved with the correct profile prefix.
    #    We read _profile_name from calibration_tab at emit time.
    #    The lambda ignores the CalibrationData argument (we only need the name).
    window.calibration_tab.calibration_updated.connect(
        lambda _cal: setattr(
            dataset_manager,
            'profile_name',
            window.calibration_tab._profile_name or 'default'
        )
    )

    # ── Start ─────────────────────────────────────────────────────────
    processing_thread.start()

    window.setWindowTitle("Smart Glove Dataset Studio")
    window.show()
    app.exec_()

    # ── Shutdown ──────────────────────────────────────────────────────
    voice_listener.stop()
    voice_listener.wait()
    processing_thread.stop()
    processing_thread.wait()
    serial_thread.stop()
    serial_thread.join(timeout=2)
    logger.info("All threads stopped. Goodbye.")


if __name__ == "__main__":
    main()
