#!/usr/bin/env python3
# =============================================================
# gen_cal_header.py  —  Smart Glove calibration header generator
# Place this script in: ~/signgloves/firmware/master_inference/
# Run it from that same folder: python3 gen_cal_header.py
#
# What it does:
#   1. Finds your calibration folder automatically
#   2. Shows all profiles and lets you pick one (or picks the
#      only one automatically if there is just one)
#   3. Always uses the LATEST calibration JSON in that profile
#   4. Writes calibration_data.h in the same folder as this script
# =============================================================

import os
import sys
import json
from datetime import datetime

# =============================================================
# WHERE TO LOOK FOR CALIBRATION FILES
# The script tries these paths in order. If your folder layout
# is different, add your path to this list.
# =============================================================
SEARCH_PATHS = [
    # Standard layout: firmware and studio both under ~/signgloves/
    os.path.expanduser("~/signgloves/smart_dataset_studio/data/calibration"),
    os.path.expanduser("~/Smart gloves/smartglove_phase1/data/calibration"),
    os.path.expanduser("~/signgloves/data/calibration"),
    # Old layout from Phase 1
    os.path.expanduser("~/smartglove_phase1/data/calibration"),
]

FINGER_CHANNELS = ['thumb', 'index', 'middle', 'ring', 'little']
CHANNEL_ORDER   = [('right', ch) for ch in FINGER_CHANNELS] + \
                  [('left',  ch) for ch in FINGER_CHANNELS]
CHANNEL_LABELS  = ['R_Thumb','R_Index','R_Middle','R_Ring','R_Little',
                   'L_Thumb','L_Index','L_Middle','L_Ring','L_Little']

# Output goes in the same folder as this script (the firmware folder)
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "calibration_data.h")


# ── Step 1: Find the calibration root folder ──────────────────
def find_cal_root():
    for path in SEARCH_PATHS:
        if os.path.isdir(path):
            return path
    print()
    print("ERROR: Could not find your calibration folder.")
    print("Looked in:")
    for p in SEARCH_PATHS:
        print(f"  {p}")
    print()
    print("Fix: open gen_cal_header.py in a text editor and add your")
    print("calibration path to the SEARCH_PATHS list at the top.")
    sys.exit(1)


# ── Step 2: Pick a profile ────────────────────────────────────
def pick_profile(cal_root):
    profiles = sorted(
        d for d in os.listdir(cal_root)
        if os.path.isdir(os.path.join(cal_root, d))
    )
    if not profiles:
        print(f"ERROR: No profile folders found in {cal_root}")
        sys.exit(1)

    if len(profiles) == 1:
        print(f"Profile: {profiles[0]}  (only one found — using automatically)")
        return profiles[0]

    print()
    print("Available profiles:")
    for i, p in enumerate(profiles):
        # Count JSON files in each profile
        pdir = os.path.join(cal_root, p)
        n = len([f for f in os.listdir(pdir) if f.endswith('.json')])
        print(f"  [{i}]  {p}  ({n} calibration file{'s' if n!=1 else ''})")
    print()

    while True:
        try:
            choice = input("Enter profile number: ").strip()
            idx = int(choice)
            if 0 <= idx < len(profiles):
                return profiles[idx]
        except (ValueError, KeyboardInterrupt):
            pass
        print("Please enter a number from the list above.")


# ── Step 3: Pick the latest JSON in that profile ──────────────
def find_latest_json(cal_root, profile):
    profile_dir = os.path.join(cal_root, profile)
    files = sorted(f for f in os.listdir(profile_dir) if f.endswith('.json'))
    if not files:
        print(f"ERROR: No calibration JSON files in {profile_dir}")
        sys.exit(1)
    # Filenames are calibration_YYYYMMDD.json — sort = chronological.
    # Latest = last in sorted order.
    latest = files[-1]
    print(f"Latest calibration: {latest}  ({len(files)} file(s) in this profile)")
    if len(files) > 1:
        print(f"  Older files: {', '.join(files[:-1])}")
    return os.path.join(profile_dir, latest)


# ── Step 4: Load and validate JSON ────────────────────────────
def load_json(path):
    with open(path) as f:
        data = json.load(f)
    for key in ['min_values', 'max_values']:
        if key not in data:
            print(f"ERROR: JSON missing required key: '{key}'")
            sys.exit(1)
        for hand in ['right', 'left']:
            if hand not in data[key]:
                print(f"ERROR: JSON missing {key}['{hand}']")
                sys.exit(1)
            for ch in FINGER_CHANNELS:
                if ch not in data[key][hand]:
                    print(f"ERROR: JSON missing {key}['{hand}']['{ch}']")
                    sys.exit(1)
    return data


# ── Step 5: Print summary and generate header ─────────────────
def generate(cal_data, json_path):
    profile  = cal_data.get('profile', 'unknown')
    date_str = cal_data.get('date', 'unknown')

    mins, maxs, ranges = [], [], []
    for (hand, ch) in CHANNEL_ORDER:
        o = float(cal_data['min_values'][hand][ch])   # open position
        c = float(cal_data['max_values'][hand][ch])   # close position
        mins.append(o)
        maxs.append(c)
        ranges.append(abs(c - o))

    # Print summary table
    print()
    print(f"  {'#':<3} {'Channel':<12} {'Open ADC':<12} {'Close ADC':<12} {'Range':<8} Note")
    print("  " + "-"*68)
    warnings = []
    for i, (label, o, c, r) in enumerate(zip(CHANNEL_LABELS, mins, maxs, ranges)):
        note = ""
        if o > c:
            note = "(inverted sensor — normal)"
        if r < 50:
            note += " ⚠ TINY RANGE"
            warnings.append(f"  Channel {i} {label}: range={r:.0f} — check magnet/sensor position")
        print(f"  {i:<3} {label:<12} {o:<12.1f} {c:<12.1f} {r:<8.0f} {note}")

    if warnings:
        print()
        print("  WARNINGS:")
        for w in warnings:
            print(w)

    # Build header content
    lines = [
        "// ============================================================",
        "// calibration_data.h  —  auto-generated by gen_cal_header.py",
        f"// Profile  : {profile}",
        f"// Date     : {date_str}",
        f"// Source   : {os.path.basename(json_path)}",
        f"// Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "//",
        "// IMPORTANT: cal_min = OPEN hand ADC,  cal_max = CLOSE hand ADC",
        "// For sensors where open > close, cal_min > cal_max (negative range).",
        "// norm_finger() handles this correctly:",
        "//   v = (val - cal_min) / (cal_max - cal_min)  [clamped 0..1]",
        "//   → open hand always = 0.0,  close hand always = 1.0",
        "//",
        "// DO NOT EDIT — regenerate: python3 gen_cal_header.py",
        "// ============================================================",
        "",
        "#ifndef CALIBRATION_DATA_H",
        "#define CALIBRATION_DATA_H",
        "",
        "// Channel order: [0-4] right hand, [5-9] left hand",
        "// Within each hand: 0=thumb, 1=index, 2=middle, 3=ring, 4=little",
        "",
        "// CAL_MIN_DATA[i] = ADC value when hand is FULLY OPEN",
        "static const float CAL_MIN_DATA[10] = {",
    ]
    for i, (v, label) in enumerate(zip(mins, CHANNEL_LABELS)):
        sep = "," if i < 9 else " "
        inv = "  // inverted sensor" if mins[i] > maxs[i] else ""
        lines.append(f"    {v:.2f}f{sep}  // [{i}] {label}{inv}")
    lines += [
        "};",
        "",
        "// CAL_MAX_DATA[i] = ADC value when hand is FULLY CLOSED (fist)",
        "static const float CAL_MAX_DATA[10] = {",
    ]
    for i, (v, label) in enumerate(zip(maxs, CHANNEL_LABELS)):
        sep = "," if i < 9 else " "
        lines.append(f"    {v:.2f}f{sep}  // [{i}] {label}")
    lines += ["};", "", "#endif // CALIBRATION_DATA_H", ""]

    with open(OUTPUT_PATH, 'w') as f:
        f.write('\n'.join(lines))

    print()
    print(f"  Written: {OUTPUT_PATH}")


# =============================================================
# MAIN
# =============================================================
def main():
    print()
    print("Smart Glove — Calibration Header Generator")
    print("=" * 44)

    cal_root = find_cal_root()
    print(f"Calibration folder: {cal_root}")

    profile  = pick_profile(cal_root)
    json_path = find_latest_json(cal_root, profile)

    cal_data = load_json(json_path)
    generate(cal_data, json_path)

    print()
    print("Next steps:")
    print("  1. calibration_data.h is already in your firmware folder")
    print("  2. Compile and flash master_inference.ino")
    print("  3. Firmware boots with calibration loaded — no cal_open/cal_close needed")
    print()


if __name__ == '__main__':
    main()
