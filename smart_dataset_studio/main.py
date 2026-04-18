#!/usr/bin/env python3
# =============================================================
# Smart Glove Dataset Studio - main.py
# Phase 7 FINAL — verified by serial_diagnostic.py
#
# All fixes from the debugging session consolidated:
#   1. os.environ[] not setdefault() — forces OpenGL env override
#   2. Auto-select master port by USB-CDC description (ttyACM0)
#   3. 2-second sleep + drain (buffer flush in serial_thread handles
#      the startup noise, no need for 10s)
# =============================================================

import os
import sys

# ── PERMANENT OPENGL FIX ──────────────────────────────────────
# CRITICAL: Must be set BEFORE any Qt or PyQtGraph import.
# Direct assignment [] always overwrites — unlike setdefault()
# which silently does nothing if the variable already exists.
os.environ['QT_XCB_GL_INTEGRATION'] = 'xcb_egl'
os.environ['PYOPENGL_PLATFORM']      = 'egl'
# ─────────────────────────────────────────────────────────────

import queue
import time
import logging
import signal

import serial.tools.list_ports
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

# ── Master port detection ─────────────────────────────────────
# Verified by diagnostic script:
#   /dev/ttyACM0 → "USB Single Serial"  = ESP32-S3 master ✓
#   /dev/ttyUSB0 → "CP2102..."           = ESP32 DevKit V1 slave
MASTER_PORT_KEYWORDS = ["usb single serial", "usb serial", "cdc"]


def select_port() -> str:
    all_ports = list(serial.tools.list_ports.comports())

    if not all_ports:
        print("\n[ERROR] No serial ports found.")
        print("Check that the ESP32-S3 master is connected via USB.")
        sys.exit(1)

    print("\nAll available serial ports:")
    for p in all_ports:
        print(f"  {p.device:<20} — {p.description}")

    master_ports = [
        p for p in all_ports
        if any(kw in p.description.lower() for kw in MASTER_PORT_KEYWORDS)
    ]

    if len(master_ports) == 1:
        chosen = master_ports[0]
        print(f"\n✓ Auto-selected master port: {chosen.device}  ({chosen.description})")
        return chosen.device

    if len(master_ports) > 1:
        print(f"\nMultiple master-candidate ports — select the ESP32-S3:")
        for i, p in enumerate(master_ports):
            print(f"  [{i}] {p.device:<20} — {p.description}")
        while True:
            try:
                choice = int(input("Select: "))
                if 0 <= choice < len(master_ports):
                    return master_ports[choice].device
            except (ValueError, KeyboardInterrupt):
                pass
            print("Invalid choice, try again.")

    print("\n[WARNING] Could not auto-detect master port.")
    for i, p in enumerate(all_ports):
        print(f"  [{i}] {p.device:<20} — {p.description}")
    while True:
        try:
            choice = int(input("\nSelect port number: "))
            if 0 <= choice < len(all_ports):
                return all_ports[choice].device
        except (ValueError, KeyboardInterrupt):
            pass
        print("Invalid choice, try again.")


def drain_queue(frame_queue: queue.Queue):
    """Discard all frames currently in the queue."""
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except queue.Empty:
            break


def main():
    # ── Qt Application ────────────────────────────────────────────────
    app = QApplication(sys.argv)
    apply_style(app)

    signal.signal(signal.SIGINT, lambda *args: app.quit())
    ctrlc_timer = QTimer()
    ctrlc_timer.start(200)
    ctrlc_timer.timeout.connect(lambda: None)

    # ── Serial port selection ─────────────────────────────────────────
    port = select_port()

    # ── Serial thread ─────────────────────────────────────────────────
    frame_queue   = queue.Queue(maxsize=QUEUE_MAX_SIZE)
    serial_thread = SerialThread(port, frame_queue)
    serial_thread.start()

    # 2 seconds is plenty — serial_thread flushes the kernel buffer
    # the moment it opens the port, and the firmware is always ready
    # (it's been running since boot). drain_queue() clears any frames
    # that arrived while we built the UI, so processing starts clean.
    print("Initialising serial connection (2 seconds)...")
    time.sleep(2.0)
    drain_queue(frame_queue)
    print("Ready.")

    # ── Build objects ─────────────────────────────────────────────────
    dataset_manager = DatasetManager(profile_name='default')
    recorder        = GestureRecorder()
    voice_listener  = VoiceListener()

    recorder_panel = RecorderPanel(recorder, dataset_manager, voice_listener)
    dataset_panel  = DatasetPanel(dataset_manager)

    recorder_panel.sample_saved.connect(dataset_panel.refresh)
    voice_listener.command_detected.connect(recorder_panel.on_voice_command)
    voice_listener.error_occurred.connect(recorder_panel.on_voice_error)

    window = MainWindow(
        recorder_panel=recorder_panel,
        dataset_panel=dataset_panel,
        dataset_manager=dataset_manager,
    )
    window.set_connected(True)

    processing_thread = ProcessingThread(frame_queue, CalibrationData())

    # ── Wire ALL signals BEFORE start() ──────────────────────────────
    processing_thread.frame_ready.connect(window.on_frame_ready)
    processing_thread.status_message.connect(window.on_status_message)

    processing_thread.frame_ready.connect(recorder.on_frame)
    processing_thread.frame_drop_detected.connect(recorder.on_frame_drop)

    recorder_panel.recording_started.connect(
        lambda: processing_thread.set_recording(True)
    )
    recorder_panel.recording_stopped.connect(
        lambda: processing_thread.set_recording(False)
    )
    recorder_panel.recording_started.connect(processing_thread.reset_filters)

    processing_thread.frame_ready.connect(window.plot_widget.on_frame)
    recorder_panel.recording_started.connect(window.plot_widget.on_recording_started)
    recorder_panel.recording_stopped.connect(window.plot_widget.on_recording_stopped)
    recorder.progress_updated.connect(window.plot_widget.on_recording_progress)

    processing_thread.frame_ready.connect(window.skeleton_widget.on_frame)

    processing_thread.raw_frame_ready.connect(window.calibration_tab.on_raw_frame)
    window.calibration_tab.calibration_updated.connect(
        processing_thread.update_calibration
    )
    window.calibration_tab.calibration_updated.connect(
        recorder_panel.on_calibration_done
    )
    window.calibration_tab.calibration_updated.connect(
        lambda _cal: setattr(
            dataset_manager,
            'profile_name',
            window.calibration_tab._profile_name or 'default'
        )
    )

    if window.analysis_tab is not None:
        recorder_panel.sample_saved.connect(window.analysis_tab.refresh)

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
