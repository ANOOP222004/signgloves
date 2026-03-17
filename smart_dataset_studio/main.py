#!/usr/bin/env python3
# =============================================================
# Smart Glove Dataset Studio - main.py
# Phase 1 Test Entry Point
#
# What this does:
#   - Lists available serial ports
#   - Opens the selected port
#   - Starts serial thread
#   - Prints parsed Frame Objects to console at 30 Hz
#   - Detects and logs frame drops
#
# Phase 1 is complete when:
#   [x] Parsed frames print to console at 30 Hz
#   [x] Deliberate checksum error → warning logged, frame discarded
#   [x] Frame drop (skipped frame_id) → warning logged
# =============================================================

import queue
import time
import logging
import sys

from config import QUEUE_MAX_SIZE, FRAME_ID_MAX
from communication.serial_thread import SerialThread

# --- Logging setup ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("main")


def select_port():
    """Lists available ports and asks user to select one."""
    ports = SerialThread.list_ports()

    if not ports:
        print("\n[ERROR] No serial ports found.")
        print("  → Make sure ESP32 is plugged in via USB")
        print("  → On Ubuntu you may need: sudo usermod -aG dialout $USER")
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


def main():
    print("=" * 60)
    print("  Smart Glove Dataset Studio — Phase 1 Test")
    print("  Serial Communication + Packet Parser")
    print("=" * 60)

    # --- Select serial port ---
    port = select_port()

    # --- Create shared queue ---
    frame_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)

    # --- Start serial thread ---
    serial_thread = SerialThread(port, frame_queue)
    serial_thread.start()

    print(f"\nListening on {port}...")
    print("Bend your finger and watch the R_T value change.")
    print("Press Ctrl+C to stop.\n")
    print(f"{'Frame':>6} | {'R_T':>5} | {'R_I':>5} | {'R_M':>5} | "
          f"{'R_R':>5} | {'R_L':>5} | {'R_P':>7} | Status")
    print("-" * 70)

    last_frame_id  = None
    frame_count    = 0
    drop_count     = 0

    try:
        while True:
            try:
                # Wait up to 2 seconds for a frame
                frame = frame_queue.get(timeout=2.0)
            except queue.Empty:
                print("[WARNING] No frames received for 2 seconds — check ESP32 connection")
                continue

            fid = frame["frame_id"]
            r   = frame["right"]

            # --- Frame drop detection ---
            status = "OK"
            if last_frame_id is not None:
                expected = (last_frame_id + 1) % (FRAME_ID_MAX + 1)
                if fid != expected:
                    dropped = (fid - last_frame_id) % (FRAME_ID_MAX + 1) - 1
                    drop_count += dropped
                    status = f"⚠ DROP ({dropped} missed)"
                    logger.warning(
                        f"Frame drop: expected {expected}, got {fid} "
                        f"({dropped} frame(s) missed)"
                    )

            last_frame_id = fid
            frame_count  += 1

            # --- Print frame to console ---
            print(
                f"{fid:>6} | {r['thumb']:>5} | {r['index']:>5} | "
                f"{r['middle']:>5} | {r['ring']:>5} | {r['little']:>5} | "
                f"{r['pitch']:>7.1f} | {status}"
            )

            # --- Print stats every 90 frames (3 seconds) ---
            if frame_count % 90 == 0:
                print(f"\n  → {frame_count} frames received | {drop_count} drops total\n")

    except KeyboardInterrupt:
        print(f"\n\nStopped by user.")
        print(f"Total frames received : {frame_count}")
        print(f"Total frame drops     : {drop_count}")

    finally:
        serial_thread.stop()
        serial_thread.join(timeout=2)
        print("Serial thread stopped. Goodbye.")


if __name__ == "__main__":
    main()
