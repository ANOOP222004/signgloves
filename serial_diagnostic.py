#!/usr/bin/env python3
# =============================================================
# serial_diagnostic.py
#
# Standalone diagnostic tool — no Qt, no threads, no parsing.
# Just opens /dev/ttyACM0 and counts raw lines per second for 10s.
#
# This tells us ONE thing definitively:
#   How fast is the ESP32-S3 actually sending packets?
#
# If this shows 30 Hz → the firmware is fine, the problem is in Python.
# If this shows 10 Hz → the firmware is the problem (or USB is).
#
# Run this AFTER closing the Smart Glove studio (only one program can
# own the serial port at a time).
#
# Usage:
#   python3 serial_diagnostic.py
#   python3 serial_diagnostic.py /dev/ttyACM0
# =============================================================

import sys
import time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
BAUD = 115200
DURATION = 10.0


def main():
    print(f"Opening {PORT} at {BAUD} baud...")
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    ser.reset_input_buffer()
    print(f"Port open. Counting lines for {DURATION} seconds...\n")

    line_count      = 0
    f_packet_count  = 0
    other_count     = 0
    bytes_total     = 0
    first_f_seen    = False
    first_sample_lines = []

    start = time.time()

    while time.time() - start < DURATION:
        try:
            raw = ser.readline()
        except serial.SerialException as e:
            print(f"Serial error: {e}")
            break

        if not raw:
            continue

        bytes_total += len(raw)
        line_count  += 1

        try:
            line = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            other_count += 1
            continue

        if line.startswith("F,"):
            f_packet_count += 1
            if not first_f_seen:
                first_f_seen = True
                print(f"[t={time.time()-start:.2f}s] First F, packet seen.")
            # Save first 3 F packets for field-count check
            if len(first_sample_lines) < 3:
                first_sample_lines.append(line)
        else:
            other_count += 1
            # Print non-F lines — these tell us if startup noise is still coming
            if other_count <= 20:
                print(f"  NON-F: {line[:80]}")

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Duration:              {elapsed:.2f} seconds")
    print(f"Total lines received:  {line_count}")
    print(f"F, packets:            {f_packet_count}")
    print(f"Other/noise lines:     {other_count}")
    print(f"Bytes received:        {bytes_total}")
    print(f"")
    print(f"Line rate (total):     {line_count/elapsed:.1f} lines/sec")
    print(f"F, packet rate:        {f_packet_count/elapsed:.1f} packets/sec")
    print(f"Byte rate:             {bytes_total/elapsed:.0f} bytes/sec")
    print(f"")
    print(f"Expected F rate:       30 Hz")
    print(f"Expected byte rate:    ~4500 bytes/sec  (150 bytes × 30 Hz)")
    print("=" * 60)

    if first_sample_lines:
        print("\nFirst 3 F packets (verify 19 comma-separated fields):")
        for line in first_sample_lines:
            fields = line.split(",")
            print(f"  [{len(fields)} fields] {line[:120]}")

    ser.close()

    # Diagnosis
    print("\n" + "=" * 60)
    print("DIAGNOSIS")
    print("=" * 60)
    rate = f_packet_count / elapsed
    if rate >= 28:
        print("✓ Firmware is sending at 30 Hz. Problem is in Python pipeline.")
    elif rate >= 8 and rate <= 15:
        print("✗ Firmware is sending at ~10 Hz (not 30 Hz).")
        print("  Possible causes:")
        print("    - SAMPLE_PERIOD_MS in firmware is set to 100 instead of 33")
        print("    - IMU I2C transaction is blocking the loop")
        print("    - Slow Serial.print() is throttling the loop")
    elif rate < 5:
        print("✗ Firmware sending almost no packets.")
        print("  Possible causes:")
        print("    - Wrong port (this is the slave, not master)")
        print("    - Firmware stuck in setup() (check ESP-NOW init)")
        print("    - Firmware not flashed")
    else:
        print(f"✗ Unusual rate: {rate:.1f} Hz")


if __name__ == "__main__":
    main()
