# =============================================================
# Smart Glove Dataset Studio - communication/serial_thread.py
# Reads raw lines from serial port on a dedicated thread.
# Pushes validated Raw Frame dicts into a thread-safe Queue.
# Never blocks the UI thread.
# =============================================================

import threading
import queue
import logging
import serial
import serial.tools.list_ports

from config import BAUD_RATE, QUEUE_MAX_SIZE
from communication.packet_parser import parse_packet

logger = logging.getLogger(__name__)


class SerialThread(threading.Thread):
    def __init__(self, port, frame_queue):
        super().__init__(daemon=True)
        self.port        = port
        self.frame_queue = frame_queue
        self._running    = False
        self._serial     = None

    def run(self):
        """Main thread loop — reads lines and pushes to queue."""
        self._running = True
        logger.info(f"Serial thread starting on {self.port} at {BAUD_RATE} baud")

        try:
            self._serial = serial.Serial(self.port, BAUD_RATE, timeout=1)
            logger.info(f"Serial port {self.port} opened successfully")
        except serial.SerialException as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")
            self._running = False
            return

        while self._running:
            try:
                raw_line = self._serial.readline()

                if not raw_line:
                    # Timeout — no data received within 1 second
                    continue

                # Decode bytes to string
                try:
                    line_str = raw_line.decode("utf-8")
                except UnicodeDecodeError:
                    logger.warning("Unicode decode error on serial line — discarding")
                    continue

                # Parse the line
                frame = parse_packet(line_str)

                if frame is None:
                    # Parser returned None — invalid/control packet, already logged
                    continue

                # Push to queue — drop oldest if full
                try:
                    self.frame_queue.put_nowait(frame)
                except queue.Full:
                    # Drop oldest frame to make room
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self.frame_queue.put_nowait(frame)
                    logger.warning("Queue full — oldest frame dropped")

            except serial.SerialException as e:
                logger.error(f"Serial read error: {e}")
                self._running = False
                break

        # Cleanup
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serial port closed")

    def stop(self):
        """Signal the thread to stop."""
        self._running = False

    @staticmethod
    def list_ports():
        """Returns list of available serial port names."""
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]
