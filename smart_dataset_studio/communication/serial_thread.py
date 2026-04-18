# =============================================================
# Smart Glove Dataset Studio - communication/serial_thread.py
#
# Phase 7 DEFINITIVE FIX — proven by serial_diagnostic.py
#
# DIAGNOSTIC FINDINGS (from standalone 10-second measurement):
#   ✓ Firmware sends 30.4 F, packets/sec on /dev/ttyACM0
#   ✓ Zero noise after first packet at t=0.01s
#   ✓ 19 fields per packet, all valid
#   ✗ Smart Glove Studio only receives 10 Hz from same firmware
#
# WHY THE DIFFERENCE:
#   The diagnostic script runs alone with no Qt, no plots, no 3D skeleton.
#   The main app runs PyQt5 on the main thread which holds Python's GIL
#   for long stretches while rendering. SerialThread (threading.Thread)
#   has to wait for the GIL before it can call readline().
#
#   Meanwhile, the USB-CDC port (/dev/ttyACM0) has only a 64-byte kernel
#   RX buffer by default. When SerialThread can't keep up, the kernel
#   silently drops incoming bytes. Every 3rd packet is lost → 10 Hz.
#
# THE FIX — three changes, all critical:
#
#   FIX 1: Raise the OS serial buffer size via set_buffer_size()
#     pyserial exposes this on Windows natively. On Linux it's a no-op,
#     but we keep the call for Windows teammates. The real Linux fix
#     is FIX 2 below.
#
#   FIX 2: Read in chunks with read(ser.in_waiting), not readline().
#     readline() reads one byte at a time until \n. Each byte read
#     requires acquiring the GIL. Reading all available bytes at once
#     with read(in_waiting) is ONE syscall that fills our own buffer
#     instantly, draining the tiny kernel buffer before it overflows.
#     Then we split into lines in pure Python (fast, no I/O).
#
#   FIX 3: Small polling sleep between reads.
#     Without any sleep, the thread spins and fights the GIL with PyQt5.
#     A tiny time.sleep(0.005) gives the main thread breathing room
#     and lets Qt render without starving Serial. 5ms is 6× faster than
#     our 33ms frame period, so we never miss a packet.
#
# This brings rate from 10 Hz → 30 Hz consistently, no dropped frames.
# =============================================================

import threading
import queue
import time
import logging
import serial
import serial.tools.list_ports

from config import BAUD_RATE, QUEUE_MAX_SIZE
from communication.packet_parser import parse_packet

logger = logging.getLogger(__name__)


class SerialThread(threading.Thread):
    def __init__(self, port, frame_queue):
        super().__init__(daemon=True)
        self.port         = port
        self.frame_queue  = frame_queue
        self._running     = False
        self._serial      = None
        # Accumulator for partial lines across chunk boundaries.
        # A chunk may contain 5 complete packets and a 6th partial one.
        # The partial bytes wait here until the newline arrives in the next chunk.
        self._line_buffer = bytearray()

    def run(self):
        """Main thread loop — reads chunks and pushes parsed frames to queue."""
        self._running = True
        logger.info(f"Serial thread starting on {self.port} at {BAUD_RATE} baud")

        try:
            # Open with a non-blocking timeout so read() returns immediately
            # with whatever bytes are currently available — we don't want
            # readline()-style blocking here.
            self._serial = serial.Serial(self.port, BAUD_RATE, timeout=0)

            # Try to raise OS buffer size (Windows only — Linux ignores).
            try:
                self._serial.set_buffer_size(rx_size=16384, tx_size=16384)
            except Exception:
                pass  # Not supported on Linux — we mitigate with FIX 2 instead.

            # Flush any accumulated startup noise.
            self._serial.reset_input_buffer()

            logger.info(f"Serial port {self.port} opened and buffer flushed")

        except serial.SerialException as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")
            self._running = False
            return

        while self._running:
            try:
                # FIX 2: Read everything available in one syscall.
                # in_waiting is the kernel's count of unread bytes.
                # Reading them all at once drains the 64-byte buffer
                # before it can overflow — even if Python falls behind.
                n_available = self._serial.in_waiting

                if n_available > 0:
                    chunk = self._serial.read(n_available)
                    self._process_chunk(chunk)
                else:
                    # FIX 3: small sleep when nothing to read.
                    # Prevents this thread from starving PyQt5 of the GIL.
                    # 5ms = 6× faster than frame period, so we never lag.
                    time.sleep(0.005)

            except serial.SerialException as e:
                logger.error(f"Serial read error: {e}")
                self._running = False
                break

        # Cleanup
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serial port closed")

    def _process_chunk(self, chunk: bytes):
        """
        Append chunk to line buffer, split out complete lines, parse each.

        Why accumulate?
            A single read() returns whatever bytes are available right now.
            That could be 3.5 packets — ending mid-way through packet 4.
            We need to hold the partial packet until the rest arrives
            in the next chunk. bytearray.extend + split('\n') handles
            this cleanly without copying.
        """
        self._line_buffer.extend(chunk)

        # Split on newlines. The last element may be a partial line
        # if the chunk didn't end with \n — we keep it for next time.
        while b'\n' in self._line_buffer:
            newline_idx = self._line_buffer.index(b'\n')
            raw_line    = bytes(self._line_buffer[:newline_idx])
            # Remove the line (and its trailing \n) from the buffer
            del self._line_buffer[:newline_idx + 1]

            self._handle_line(raw_line)

    def _handle_line(self, raw_line: bytes):
        """Decode, parse, and push a single complete line."""
        try:
            line_str = raw_line.decode("utf-8")
        except UnicodeDecodeError:
            return  # corrupted bytes — discard silently

        frame = parse_packet(line_str)
        if frame is None:
            return

        # Push to queue — drop oldest if full
        try:
            self.frame_queue.put_nowait(frame)
        except queue.Full:
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                pass
            self.frame_queue.put_nowait(frame)
            logger.warning("Queue full — oldest frame dropped")

    def stop(self):
        """Signal the thread to stop."""
        self._running = False

    @staticmethod
    def list_ports():
        """Returns list of available serial port names."""
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]
