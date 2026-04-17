#!/usr/bin/env python3
# =============================================================
# Smart Glove Dataset Studio - main.py
# Phase 6 Final — with permanent OpenGL fix
#
# Permanent fix for black 3D skeleton on Ubuntu:
#   Sets QT_XCB_GL_INTEGRATION=xcb_egl in os.environ BEFORE
#   any Qt or PyQtGraph import. This is equivalent to running
#   export QT_XCB_GL_INTEGRATION=xcb_egl before python3 main.py
#   but is permanent — no manual export needed ever again.
#
# Startup sequence:
#   1.  Set OpenGL env vars (MUST be before all Qt imports)
#   2.  QApplication + apply_style
#   3.  Ctrl+C handler
#   4.  select_port()
#   5.  SerialThread.start()
#   6.  time.sleep(2.0) + drain_queue()
#   7.  Build all objects
#   8.  Wire ALL signals BEFORE ProcessingThread.start()
#   9.  ProcessingThread.start()
#   10. window.show() + app.exec_()
#   11. Clean shutdown
# =============================================================

import os
import sys

# ── PERMANENT OPENGL FIX ──────────────────────────────────────
# CRITICAL: These must be set BEFORE any Qt or PyQtGraph import.
# On Ubuntu, PyQtGraph GL defaults to a broken XCB GL integration.
# xcb_egl forces the correct EGL backend that works reliably.
# This is the permanent equivalent of:
#   export QT_XCB_GL_INTEGRATION=xcb_egl
#   export PYOPENGL_PLATFORM=egl
os.environ.setdefault('QT_XCB_GL_INTEGRATION', 'xcb_egl')
os.environ.setdefault('PYOPENGL_PLATFORM',     'egl')
# ─────────────────────────────────────────────────────────────

import queue
import time
import logging
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
    """
    Lists available serial ports and asks user to select one.
    Auto-selects if only one port is available.
    Must be called BEFORE starting any threads — uses input().
    """
    ports = SerialThread.list_ports()
    if not ports:
        print("\n[ERROR] No serial ports found.")
        print("Check that ESP32-S3 master is connected via USB.")
        print("Use the UART port (right USB-C port on DevKitC-1).")
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
    """Discard all frames in queue — flushes ESP32 boot noise."""
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except queue.Empty:
            break


def main():
    # ── Qt Application ────────────────────────────────────────────────
    app = QApplication(sys.argv)
    apply_style(app)  # dark theme — MUST be before any widget

    # Clean Ctrl+C shutdown
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
    logger.info(f"Serial thread started on {port}")

    # Wait for ESP32 to stabilise, then flush startup noise
    time.sleep(2.0)
    drain_queue(frame_queue)

    # ── Build objects ─────────────────────────────────────────────────
    dataset_manager = DatasetManager(profile_name='default')
    recorder        = GestureRecorder()
    voice_listener  = VoiceListener()

    recorder_panel = RecorderPanel(recorder, dataset_manager, voice_listener)
    dataset_panel  = DatasetPanel(dataset_manager)

    recorder_panel.sample_saved.connect(dataset_panel.refresh)
    voice_listener.command_detected.connect(recorder_panel.on_voice_command)
    voice_listener.error_occurred.connect(recorder_panel.on_voice_error)

    window = MainWindow(recorder_panel=recorder_panel, dataset_panel=dataset_panel)
    window.set_connected(True)

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

    # Signal plots
    processing_thread.frame_ready.connect(window.plot_widget.on_frame)
    recorder_panel.recording_started.connect(window.plot_widget.on_recording_started)
    recorder_panel.recording_stopped.connect(window.plot_widget.on_recording_stopped)
    recorder.progress_updated.connect(window.plot_widget.on_recording_progress)

    # 3D Skeleton — Phase 6
    processing_thread.frame_ready.connect(window.skeleton_widget.on_frame)

    # Calibration tab — 4 connections
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
