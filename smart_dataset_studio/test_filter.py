# test_filter.py
#
# Standalone test script for processing/filter.py
# Run this from inside smart_dataset_studio/ folder:
#     python3 test_filter.py
#
# No ESP32 needed. No serial port needed.
# Just verifies the EMA filter behaves correctly with fake values.

import sys
import os

# Add the smart_dataset_studio folder to Python's path so it can find
# config.py and processing/filter.py — without this, the import fails
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from processing.filter import EMAFilter

print("=" * 55)
print("EMA Filter Test")
print("=" * 55)

# ─────────────────────────────────────────────────────────
# TEST 1 — First call seeds correctly
# Expected: first output equals the input exactly (no blending with zero)
# ─────────────────────────────────────────────────────────
print("\nTEST 1 — First call seeds correctly")

f = EMAFilter()
result = f.update(2100)

print(f"  Input:    2100")
print(f"  Output:   {result}")
print(f"  Expected: 2100")
print(f"  {'✅ PASS' if result == 2100 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# TEST 2 — Noise spike is absorbed
# Finger sitting still at 2100. One spike to 2160.
# Expected: output moves only 25% toward the spike
# Manual calculation: 0.25 * 2160 + 0.75 * 2100 = 540 + 1575 = 2115
# ─────────────────────────────────────────────────────────
print("\nTEST 2 — Noise spike is absorbed")

f = EMAFilter()
f.update(2100)          # seed the filter at 2100
result = f.update(2160) # spike — finger didn't actually move

expected = 0.25 * 2160 + 0.75 * 2100  # = 2115.0

print(f"  Stable value:  2100")
print(f"  Spike value:   2160  (noise — finger didn't move)")
print(f"  Output:        {result:.2f}")
print(f"  Expected:      {expected:.2f}")
print(f"  Spike absorbed by: {((2160 - result) / (2160 - 2100) * 100):.0f}%  (should be 75%)")
print(f"  {'✅ PASS' if abs(result - expected) < 0.01 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# TEST 3 — Sustained movement is tracked
# Finger moves from 2100 to 2800 and holds there.
# Feed 2800 repeatedly and watch the filter converge toward it.
# Expected: reaches very close to 2800 within ~10 frames
# ─────────────────────────────────────────────────────────
print("\nTEST 3 — Sustained movement tracked over frames")

f = EMAFilter()
f.update(2100)  # seed at 2100

print(f"  Starting value: 2100  →  Target: 2800")
print(f"  Feeding 2800 repeatedly:")

prev = 2100
for i in range(1, 11):
    result = f.update(2800)
    print(f"    Frame {i:2d}: {result:.1f}")

print(f"  Final value after 10 frames: {result:.1f}  (should be close to 2800)")
print(f"  {'✅ PASS' if result > 2750 else '❌ FAIL — not converging fast enough'}")

# ─────────────────────────────────────────────────────────
# TEST 4 — Reset clears state
# After filtering some values, reset() should wipe state.
# Next update() should seed fresh, not blend with old history.
# ─────────────────────────────────────────────────────────
print("\nTEST 4 — Reset clears state")

f = EMAFilter()
f.update(2100)
f.update(2200)
f.update(2300)  # filter has history now

f.reset()       # wipe it

result = f.update(1800)  # fresh start — should return 1800 exactly, not blend with 2300

print(f"  Values before reset: 2100, 2200, 2300")
print(f"  After reset, first value: 1800")
print(f"  Output:   {result}")
print(f"  Expected: 1800  (no blending with old state)")
print(f"  {'✅ PASS' if result == 1800 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("If all four tests show ✅ PASS — filter.py is correct.")
print("If any show ❌ FAIL — something is wrong in filter.py.")
print("=" * 55)
