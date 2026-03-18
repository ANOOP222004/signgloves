# test_calibration.py
#
# Standalone test script for processing/calibration.py
# Run this from inside smart_dataset_studio/ folder:
#     python3 test_calibration.py
#
# No ESP32 needed. No serial port needed.
# Verifies normalization math, dummy channel handling,
# clamping, and save/load to disk.

import sys
import os

# Add smart_dataset_studio to Python path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from processing.calibration import (
    CalibrationData,
    Calibrator,
    save_calibration,
    load_calibration,
    get_today_calibration_path,
)

print("=" * 55)
print("Calibration Test")
print("=" * 55)

# ─────────────────────────────────────────────────────────
# Helper — build a fully calibrated CalibrationData
# Right Thumb: real sensor  min=1650, max=2900
# All others:  dummy        min=2048, max=2048
# ─────────────────────────────────────────────────────────
def make_calibration():
    cal = CalibrationData()
    fingers = ['thumb', 'index', 'middle', 'ring', 'little']

    for hand in ['right', 'left']:
        for ch in fingers:
            if hand == 'right' and ch == 'thumb':
                # Real sensor — actual range from Phase 0 measurements
                cal.set_min(hand, ch, 1650)
                cal.set_max(hand, ch, 2900)
            else:
                # Dummy channel — both open and closed read 2048
                cal.set_min(hand, ch, 2048)
                cal.set_max(hand, ch, 2048)

    return cal


# ─────────────────────────────────────────────────────────
# TEST 1 — Open hand normalizes to 0.0
# Right Thumb at min value (2900) should output 0.0
# Wait — which end is open and which is closed?
# From CURRENT_STATUS.md:
#   Finger open:   ~2900 ADC (magnet close to sensor)
#   Finger closed: ~1650 ADC (magnet moves away)
# So min=1650 (closed), max=2900 (open)
# open hand  = 2900 → (2900-1650)/(2900-1650) = 1.0
# Hmm — that gives 1.0 for open, 0.0 for closed.
# That means bend=1.0 means OPEN, bend=0.0 means CLOSED.
# BUT our convention is: 0.0=open, 1.0=bent.
# So we need min=2900 (open), max=1650 (closed).
# The calibration wizard records min when open, max when closed.
# Let's correct the calibration accordingly.
# ─────────────────────────────────────────────────────────

def make_calibration_correct():
    """
    Correct calibration matching physical reality:
        Open hand  → higher ADC (~2900) → should normalize to 0.0
        Closed hand → lower ADC (~1650) → should normalize to 1.0

    So: min_value = 2900 (open), max_value = 1650 (closed)
    Then: bend = (2900 - 2900) / (1650 - 2900) = 0.0  ✅ open = 0.0
          bend = (1650 - 2900) / (1650 - 2900) = 1.0  ✅ closed = 1.0
    """
    cal = CalibrationData()
    fingers = ['thumb', 'index', 'middle', 'ring', 'little']

    for hand in ['right', 'left']:
        for ch in fingers:
            if hand == 'right' and ch == 'thumb':
                # Open hand recorded as min, closed hand as max
                # Open = 2900 ADC, Closed = 1650 ADC
                cal.set_min(hand, ch, 2900)  # open hand position
                cal.set_max(hand, ch, 1650)  # closed hand position
            else:
                cal.set_min(hand, ch, 2048)
                cal.set_max(hand, ch, 2048)

    return cal


cal_data = make_calibration_correct()
calibrator = Calibrator(cal_data)

# ─────────────────────────────────────────────────────────
# TEST 1 — Open hand reads 0.0
# ─────────────────────────────────────────────────────────
print("\nTEST 1 — Open hand normalizes to 0.0")

result = calibrator.normalize_finger('right', 'thumb', 2900)
print(f"  Filtered value: 2900  (open hand)")
print(f"  Output:         {result:.2f}")
print(f"  Expected:       0.00")
print(f"  {'✅ PASS' if abs(result - 0.0) < 0.01 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# TEST 2 — Closed hand reads 1.0
# ─────────────────────────────────────────────────────────
print("\nTEST 2 — Closed hand normalizes to 1.0")

result = calibrator.normalize_finger('right', 'thumb', 1650)
print(f"  Filtered value: 1650  (closed hand)")
print(f"  Output:         {result:.2f}")
print(f"  Expected:       1.00")
print(f"  {'✅ PASS' if abs(result - 1.0) < 0.01 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# TEST 3 — Midpoint reads ~0.5
# ─────────────────────────────────────────────────────────
print("\nTEST 3 — Midpoint normalizes to ~0.5")

midpoint = (2900 + 1650) / 2  # = 2275
result = calibrator.normalize_finger('right', 'thumb', midpoint)
print(f"  Filtered value: {midpoint}  (halfway bent)")
print(f"  Output:         {result:.2f}")
print(f"  Expected:       0.50")
print(f"  {'✅ PASS' if abs(result - 0.5) < 0.01 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# TEST 4 — Dummy channel returns 0.0 safely (no crash)
# ─────────────────────────────────────────────────────────
print("\nTEST 4 — Dummy channel returns 0.0 safely")

result = calibrator.normalize_finger('right', 'index', 2048)
print(f"  Channel:        right index  (dummy — min=2048, max=2048)")
print(f"  Filtered value: 2048")
print(f"  Output:         {result:.2f}")
print(f"  Expected:       0.00  (no division by zero crash)")
print(f"  {'✅ PASS' if result == 0.0 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# TEST 5 — Clamping prevents out-of-range values
# ─────────────────────────────────────────────────────────
print("\nTEST 5 — Clamping keeps values within 0.0–1.0")

# Value slightly beyond open position — can happen at session start
result_low = calibrator.normalize_finger('right', 'thumb', 2950)
# Value slightly beyond closed position
result_high = calibrator.normalize_finger('right', 'thumb', 1600)

print(f"  Value beyond open  (2950): {result_low:.2f}  (should be clamped to 0.00)")
print(f"  Value beyond closed (1600): {result_high:.2f}  (should be clamped to 1.00)")
print(f"  {'✅ PASS' if result_low == 0.0 and result_high == 1.0 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# TEST 6 — Full frame normalization
# ─────────────────────────────────────────────────────────
print("\nTEST 6 — Full frame normalized correctly")

# Build a fake raw frame — same structure as frame.py Raw Frame
fake_raw_frame = {
    'frame_id': 42,
    'right': {
        'thumb':  2900,   # open — should become 0.0
        'index':  2048,   # dummy — should become 0.0
        'middle': 2048,   # dummy
        'ring':   2048,   # dummy
        'little': 2048,   # dummy
        'pitch':  12.4,   # IMU — should pass through unchanged
        'roll':   -5.2,   # IMU — should pass through unchanged
        'yaw':    0.0,    # IMU — should pass through unchanged
    },
    'left': {
        'thumb':  2048,   # dummy
        'index':  2048,   # dummy
        'middle': 2048,   # dummy
        'ring':   2048,   # dummy
        'little': 2048,   # dummy
        'pitch':  0.0,    # IMU
        'roll':   0.0,    # IMU
        'yaw':    0.0,    # IMU
    },
}

processed = calibrator.normalize_frame(fake_raw_frame)

print(f"  frame_id preserved:        {processed['frame_id']}  (expected 42)")
print(f"  right thumb (real sensor): {processed['right']['thumb']:.2f}  (expected 0.00)")
print(f"  right index (dummy):       {processed['right']['index']:.2f}  (expected 0.00)")
print(f"  right pitch (IMU):         {processed['right']['pitch']}  (expected 12.4 unchanged)")
print(f"  right roll  (IMU):         {processed['right']['roll']}  (expected -5.2 unchanged)")

all_pass = (
    processed['frame_id'] == 42 and
    abs(processed['right']['thumb'] - 0.0) < 0.01 and
    processed['right']['index'] == 0.0 and
    processed['right']['pitch'] == 12.4 and
    processed['right']['roll'] == -5.2
)
print(f"  {'✅ PASS' if all_pass else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# TEST 7 — Save and load calibration file
# ─────────────────────────────────────────────────────────
print("\nTEST 7 — Save and reload calibration from disk")

saved_path = save_calibration(cal_data)
print(f"  Saved to: {saved_path}")

loaded_cal = load_calibration(saved_path)
loaded_calibrator = Calibrator(loaded_cal)

result = loaded_calibrator.normalize_finger('right', 'thumb', 2900)
print(f"  After reload — right thumb open: {result:.2f}  (expected 0.00)")
print(f"  {'✅ PASS' if abs(result - 0.0) < 0.01 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# TEST 8 — get_today_calibration_path finds saved file
# ─────────────────────────────────────────────────────────
print("\nTEST 8 — Today's calibration file is detected")

path = get_today_calibration_path()
print(f"  Found: {path}")
print(f"  {'✅ PASS' if path is not None else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("If all tests show ✅ PASS — calibration.py is correct.")
print("If any show ❌ FAIL — check calibration.py and config.py.")
print("=" * 55)
