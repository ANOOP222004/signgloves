# =============================================================
# Smart Glove Dataset Studio - communication/packet_parser.py
# Parses and validates raw serial line strings into Frame dicts
# Returns a Raw Frame dict on success, None on any failure
# =============================================================

import logging
from processing.frame import make_raw_frame

logger = logging.getLogger(__name__)

EXPECTED_FIELD_COUNT = 19


def verify_checksum(fields):
    """
    Recomputes checksum from fields and compares to received value.
    Formula matches ESP32 firmware exactly:
      sum of all int finger fields
    + sum of int(each float IMU field * 10)
    """
    try:
        # Right fingers: fields[2:7]
        values  = [int(f) for f in fields[2:7]]
        # Right IMU: fields[7:10]
        values += [int(float(f) * 10) for f in fields[7:10]]
        # Left fingers: fields[10:15]
        values += [int(f) for f in fields[10:15]]
        # Left IMU: fields[15:18]
        values += [int(float(f) * 10) for f in fields[15:18]]

        computed = sum(values)
        received = int(fields[18])
        return computed == received
    except (ValueError, IndexError):
        return False


def parse_packet(raw_line):
    """
    Parses one raw serial line into a Raw Frame dict.

    Returns Raw Frame dict on success.
    Returns None on any validation failure.
    """
    # --- Strip whitespace ---
    line = raw_line.strip()

    # --- Handle control packets (not data frames) ---
    if line == "READY":
        logger.info("ESP32 ready signal received")
        return None
    if line.startswith("ERR,"):
        _handle_error(line)
        return None
    if line.startswith("#"):
        # Comment line — ignore silently
        return None

    # --- Check prefix ---
    if not line.startswith("F,"):
        logger.warning(f"Unknown packet prefix: {line[:20]}")
        return None

    # --- Split fields ---
    fields = line.split(",")

    # --- Check field count ---
    if len(fields) != EXPECTED_FIELD_COUNT:
        logger.warning(
            f"Wrong field count: expected {EXPECTED_FIELD_COUNT}, "
            f"got {len(fields)} | line: {line[:60]}"
        )
        return None

    # --- Verify checksum ---
    if not verify_checksum(fields):
        logger.warning(f"Checksum failure on frame {fields[1]}")
        return None

    # --- Parse all fields ---
    try:
        frame_id = int(fields[1])

        r_t  = int(fields[2])
        r_i  = int(fields[3])
        r_m  = int(fields[4])
        r_r  = int(fields[5])
        r_l  = int(fields[6])
        r_p  = float(fields[7])
        r_rl = float(fields[8])
        r_y  = float(fields[9])

        l_t  = int(fields[10])
        l_i  = int(fields[11])
        l_m  = int(fields[12])
        l_r  = int(fields[13])
        l_l  = int(fields[14])
        l_p  = float(fields[15])
        l_rl = float(fields[16])
        l_y  = float(fields[17])

    except ValueError as e:
        logger.warning(f"Field parse error: {e} | line: {line[:60]}")
        return None

    return make_raw_frame(
        frame_id,
        r_t, r_i, r_m, r_r, r_l, r_p, r_rl, r_y,
        l_t, l_i, l_m, l_r, l_l, l_p, l_rl, l_y
    )


def _handle_error(line):
    """Logs ESP32 error packets."""
    if line == "ERR,1":
        logger.error("ESP32: Right IMU not responding")
    elif line == "ERR,2":
        logger.error("ESP32: Left IMU not responding")
    elif line == "ERR,3":
        logger.error("ESP32: Slave glove not responding")
    else:
        logger.error(f"ESP32 error: {line}")
