#!/usr/bin/env python3
# =============================================================
# Smart Glove Dataset Studio - main.py
# Phase 2 Test Entry Point
#
# What this does:
#   - Lists available serial ports
#   - Handles all user prompts BEFORE serial thread starts
#   - Uses countdown timer for calibration (no blocking input()
#     while serial thread is running — prevents Queue overflow)
#   - Starts serial thread + processing thread
#   - Prints normalized 0.0-1.0 values to console at 30 Hz
#   - Shuts down cleanly on Ctrl+C (no core dump)
#
# Phase 2 is complete when:
#   [ ] Open hand reads ~0.0, fully bent reads ~1.0 after calibration
#   [ ] EMA smoothing visibly reduces noise vs Phase 1 raw values
#   [ ] Frame drop during test logs warning correctly
#   [ ] Ctrl+C exits cleanly with no crash
# =============================================================

import queue
import time
import logging
import sys
import signal

from PyQt5.QtCore import QCoreApplication, QTimer

from config import QUEUE_MAX_SIZE, FINGER_CHANNELS
from communication.serial_thread import SerialThread
from processing.calibration import (
    CalibrationData,
    save_calibration,
    load_calibration,
    get_today_calibration_path,
)
from processing.processing_thread import ProcessingThread

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


def run_console_calibration(frame_queue: queue.Queue) -> CalibrationData:
    """
    Collect open and closed hand readings using countdown timer.
    No input() calls — serial thread runs freely, Queue never overflows.
    """
    cal = CalibrationData()

    print("\n" + "=" * 55)
    print("  CALIBRATION")
    print("=" * 55)

    # --- Step 1: Open hand ---
    print("\nStep 1 of 2: OPEN your hand fully — spread all fingers.")
    print("  You have 3 seconds to position your hand.")
    countdown(3, "Opening hand")

    drain_queue(frame_queue)

    print("  Recording...")
    open_frames = []
    for _ in range(30):
        try:
            frame = frame_queue.get(timeout=2.0)
            open_frames.append(frame)
        except queue.Empty:
            print("[ERROR] No frames received — check ESP32 connection")
            sys.exit(1)

    for hand in ['right', 'left']:
        for ch in FINGER_CHANNELS:
            avg = sum(f[hand][ch] for f in open_frames) / len(open_frames)
            cal.set_min(hand, ch, avg)

    r_thumb_open = sum(
        f['right']['thumb'] for f in open_frames
    ) / len(open_frames)
    print(f"  Open hand recorded.   R_Thumb = {r_thumb_open:.1f} ADC")

    # --- Step 2: Closed hand ---
    print("\nStep 2 of 2: CLOSE your hand fully — bend finger at middle joint.")
    print("  You have 3 seconds to position your hand.")
    countdown(3, "Closing hand")

    drain_queue(frame_queue)

    print("  Recording...")
    closed_frames = []
    for _ in range(30):
        try:
            frame = frame_queue.get(timeout=2.0)
            closed_frames.append(frame)
        except queue.Empty:
            print("[ERROR] No frames received — check ESP32 connection")
            sys.exit(1)

    for hand in ['right', 'left']:
        for ch in FINGER_CHANNELS:
            avg = sum(f[hand][ch] for f in closed_frames) / len(closed_frames)
            cal.set_max(hand, ch, avg)

    r_thumb_closed = sum(
        f['right']['thumb'] for f in closed_frames
    ) / len(closed_frames)
    print(f"  Closed hand recorded. R_Thumb = {r_thumb_closed:.1f} ADC")

    saved_path = save_calibration(cal)
    print(f"\n  Calibration saved: {saved_path}")
    print(f"  Range: {r_thumb_open:.1f} (open) → {r_thumb_closed:.1f} (closed)")
    print("=" * 55)

    return cal


def on_frame_received(processed_frame: dict):
    """
    Slot connected to ProcessingThread.frame_ready signal.
    Prints normalized values to console.
    Phase 3 replaces this with UI label updates.
    """
    r = processed_frame['right']
    fid = processed_frame['frame_id']

    print(
        f"{fid:>6} | "
        f"R_T: {r['thumb']:.2f} | "
        f"R_I: {r['index']:.2f} | "
        f"R_M: {r['middle']:.2f} | "
        f"R_R: {r['ring']:.2f} | "
        f"R_L: {r['little']:.2f} | "
        f"Pitch: {r['pitch']:>6.1f}"
    )


def on_status_message(message: str):
    """Slot for processing thread warnings."""
    logger.warning(message)


def main():
    app = QCoreApplication(sys.argv)

    # ── Clean Ctrl+C shutdown ─────────────────────────────────────
    # Problem: Qt event loop (app.exec_()) catches signals internally
    # and doesn't pass Ctrl+C to Python cleanly → causes core dump.
    #
    # Fix: install a Python signal handler that calls app.quit().
    # app.quit() tells the Qt event loop to exit cleanly.
    # The finally block then stops all threads gracefully.
    #
    # The QTimer trick: Python signal handlers only run when Python
    # is executing — but app.exec_() blocks Python while Qt runs.
    # A QTimer firing every 200ms gives Python a chance to check
    # for signals, so Ctrl+C is caught promptly.
    signal.signal(signal.SIGINT, lambda *args: app.quit())
    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)  # wake Python every 200ms

    print("=" * 55)
    print("  Smart Glove Dataset Studio — Phase 2 Test")
    print("  Filter + Normalize Pipeline")
    print("=" * 55)

    # ── Step 1: Select port ───────────────────────────────────────
    # input() safe here — serial thread not started yet
    port = select_port()

    # ── Step 2: Decide calibration ────────────────────────────────
    # input() safe here — serial thread not started yet
    use_existing = False
    today_path = get_today_calibration_path()
    if today_path:
        print(f"\nFound existing calibration: {today_path}")
        choice = input("Use existing calibration? (y/n): ").strip().lower()
        use_existing = (choice == 'y')

    # ── Step 3: Start serial thread ───────────────────────────────
    # NO MORE input() calls after this point.
    frame_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)
    serial_thread = SerialThread(port, frame_queue)
    serial_thread.start()
    print(f"\nSerial thread started on {port}")

    # Wait for ESP32 to stabilise and flush startup noise
    print("Waiting for ESP32 to stabilise...")
    time.sleep(2.0)
    drain_queue(frame_queue)
    print("Ready.")

    # ── Step 4: Calibration ───────────────────────────────────────
    if use_existing:
        calibration_data = load_calibration(today_path)
        print("Existing calibration loaded.")
    else:
        calibration_data = run_console_calibration(frame_queue)

    # ── Step 5: Start processing thread ──────────────────────────
    processing_thread = ProcessingThread(frame_queue, calibration_data)
    processing_thread.frame_ready.connect(on_frame_received)
    processing_thread.status_message.connect(on_status_message)
    processing_thread.start()

    print(f"\nBend your finger — watch R_T move between 0.00 and 1.00.")
    print("Press Ctrl+C to stop cleanly.\n")
    print(f"{'Frame':>6} | {'R_T':>6} | {'R_I':>6} | "
          f"{'R_M':>6} | {'R_R':>6} | {'R_L':>6} | {'Pitch':>8}")
    print("-" * 65)

    # ── Step 6: Run Qt event loop ─────────────────────────────────
    # app.exec_() runs until app.quit() is called (by Ctrl+C handler)
    app.exec_()

    # ── Step 7: Clean shutdown ────────────────────────────────────
    print("\n\nStopping...")
    processing_thread.stop()
    processing_thread.wait()
    serial_thread.stop()
    serial_thread.join(timeout=2)
    print("All threads stopped. Goodbye.")


if __name__ == "__main__":
    main()
