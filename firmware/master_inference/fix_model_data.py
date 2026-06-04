#!/usr/bin/env python3
# =============================================================
# fix_model_data.py  —  Split model_data.h into .h + .cpp
#
# PROBLEM: On Windows, cc1plus.exe runs out of memory when
# compiling a 99 KB array inline in a header file.
# SOLUTION: Move the array definition to model_data.cpp so it
# compiles in its own translation unit. The header keeps only
# the extern declarations (tiny, no memory issue).
#
# Place this script in the same folder as model_data.h
# (your firmware folder: master_inference/).
# Run: python3 fix_model_data.py
#
# BEFORE:   model_data.h  (613 KB — all data inline)
# AFTER:    model_data.h  (tiny — extern declarations only)
#           model_data.cpp (613 KB — actual array data)
# Both files go in the same firmware folder. Arduino IDE
# compiles .cpp files automatically.
# =============================================================

import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
H_PATH     = os.path.join(SCRIPT_DIR, "model_data.h")
CPP_PATH   = os.path.join(SCRIPT_DIR, "model_data.cpp")

def main():
    if not os.path.exists(H_PATH):
        print(f"ERROR: model_data.h not found at {H_PATH}")
        sys.exit(1)

    with open(H_PATH, 'r') as f:
        content = f.read()

    # Check if already split (already has extern, no array data)
    if 'extern' in content and '{' not in content:
        print("model_data.h is already in split format — nothing to do.")
        return

    # Check it has the expected structure
    if 'g_model' not in content:
        print("ERROR: model_data.h does not contain 'g_model'")
        print("Make sure you ran: xxd -i model_v6.tflite > model_data.h")
        print("and edited the variable names to g_model and g_model_len.")
        sys.exit(1)

    # Extract g_model_len value
    len_match = re.search(r'g_model_len\s*=\s*(\d+)', content)
    if not len_match:
        print("ERROR: could not find g_model_len in model_data.h")
        sys.exit(1)
    model_len = int(len_match.group(1))

    print(f"Found model_data.h: {os.path.getsize(H_PATH)//1024} KB")
    print(f"g_model_len = {model_len} bytes ({model_len/1024:.1f} KB)")
    print()

    # ── Write model_data.cpp — has the full array ─────────────
    # Use __attribute__((aligned(16))) instead of alignas(16)
    # for maximum compatibility with older Arduino/GCC toolchains.
    cpp_content = (
        "// model_data.cpp — Auto-generated array storage.\n"
        "// Do not edit. Regenerate from model_v6.tflite:\n"
        "//   xxd -i model_v6.tflite > model_data_raw.h\n"
        "//   then rename variables, then run fix_model_data.py\n"
        "#include \"model_data.h\"\n\n"
    )

    # Replace alignas(16) with __attribute__((aligned(16))) for compatibility
    data_section = content
    data_section = re.sub(
        r'alignas\s*\(\s*16\s*\)\s*const unsigned char',
        '__attribute__((aligned(16))) const unsigned char',
        data_section
    )
    # Remove the g_model_len line from the data section
    # (it will be in the .cpp too, but only the array definition is critical)
    cpp_content += data_section

    with open(CPP_PATH, 'w') as f:
        f.write(cpp_content)
    print(f"Written: model_data.cpp  ({os.path.getsize(CPP_PATH)//1024} KB)")

    # ── Write model_data.h — declarations only ────────────────
    h_content = (
        "// model_data.h — extern declarations for TFLite model.\n"
        "// The actual array lives in model_data.cpp\n"
        "// (split to avoid cc1plus.exe out-of-memory on Windows).\n"
        "#ifndef MODEL_DATA_H\n"
        "#define MODEL_DATA_H\n\n"
        "extern const unsigned char g_model[];\n"
        "extern const unsigned int  g_model_len;\n\n"
        "#endif // MODEL_DATA_H\n"
    )

    with open(H_PATH, 'w') as f:
        f.write(h_content)
    print(f"Written: model_data.h   ({os.path.getsize(H_PATH)} bytes — declarations only)")

    print()
    print("Done. Your firmware folder now has:")
    print(f"  model_data.h    — tiny extern declarations (no memory issue)")
    print(f"  model_data.cpp  — full array, compiled separately by Arduino IDE")
    print()
    print("Reopen Arduino IDE and compile again.")

if __name__ == '__main__':
    main()
