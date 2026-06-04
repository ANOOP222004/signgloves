#!/usr/bin/env python3
# =============================================================
# live_inference.py  —  Smart Glove live prediction (v6 model)
#                       + Method 1 noise gating
#
# Run from: ~/signgloves/smart_dataset_studio/
#   python3 live_inference.py model_v6.tflite
#
# PREPROCESSING (unchanged from working v6 script):
#   - Drops yaw channels (index 7, 15) → 14 features
#   - z-score per channel over the 60-frame window (calibration-robust)
#
# METHOD 1 GATING (new):
#   1. REST GATE  : self-calibrating noise gate. Learns rest pose +
#                   idle noise at startup, only runs the model when the
#                   hand moves clearly away from rest. Kills idle noise.
#   2. STABILITY  : commits a sign only when the model agrees several
#                   frames in a row. Transition blur is auto-rejected.
# =============================================================

import os
import sys
import queue
import time
import signal
import logging
from collections import deque

import numpy as np
import serial.tools.list_ports

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# tensorflow first (NumPy 2.x compatible), then tflite-runtime
try:
    from tensorflow.lite.python.interpreter import Interpreter
    print("[OK] Using tensorflow.lite")
except ImportError:
    try:
        from tflite_runtime.interpreter import Interpreter
        print("[OK] Using tflite-runtime")
    except ImportError:
        print("[ERROR] Install one of:")
        print("  pip install tensorflow")
        print("  pip install tflite-runtime  (requires numpy<2)")
        sys.exit(1)

try:
    from config import (
        BAUD_RATE, QUEUE_MAX_SIZE, WINDOW_SIZE,
        GESTURE_LABELS, FEATURE_ORDER, NUM_FEATURES,
        FINGER_CHANNELS, IMU_CHANNELS,
        CALIBRATION_DIR,
    )
    from communication.serial_thread import SerialThread
    from processing.filter import EMAFilter
    from processing.calibration import load_calibration
    from processing.frame import frame_to_feature_vector
except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    print("  Run from inside smart_dataset_studio/")
    sys.exit(1)

logging.basicConfig(level=logging.WARNING)

# ── v6 model preprocessing constants (UNCHANGED — your working setup) ──
# Drop R_Yaw (index 7) and L_Yaw (index 15) — yaw wraps at ±180°
# causing discontinuous jumps, confirmed harmful by IMU diagnostic.
# After slicing to 14 features, z-score is applied per channel.
V6_FEATURE_IDX  = [0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14]
V6_NUM_FEATURES = len(V6_FEATURE_IDX)  # 14

# ── Finger indices in the 16-feature vector (for the rest gate) ──
# The rest gate measures deviation on finger channels only — they're
# the cleanest signal for "is the hand at rest". This is independent
# of the z-score the model uses; the gate works on calibrated 0-1 values.
FINGER_ONLY_IDX = [0, 1, 2, 3, 4, 8, 9, 10, 11, 12]

# ════════════════════════════════════════════════════════════════
# TUNABLE CONSTANTS — adjust while watching the live output
# ════════════════════════════════════════════════════════════════
STRIDE               = 5      # run inference every N frames (~6/sec at 30 Hz)
CONFIDENCE_THRESHOLD = 0.80   # ignore predictions below this confidence

# ── Rest gate ──
REST_CAPTURE_SECONDS = 2.5    # how long to hold still at startup
REST_MARGIN          = 3.0    # open threshold = idle_noise_floor × this
GATE_HYSTERESIS      = 0.6    # close threshold = open_threshold × this
DEVIATION_SMOOTH     = 8      # smooth deviation over last N frames (anti-flicker)
REST_NOISE_CEILING   = 0.15   # warn if idle noise exceeds this (you moved)

# ── Stability filter ──
# Consecutive identical predictions before committing a sign.
# At 30 Hz / STRIDE=5 ≈ 6 predictions/sec:
#   2 ≈ 0.33s hold (snappy)  3 ≈ 0.50s (balanced)  4 ≈ 0.67s (reliable)
STABILITY_COUNT = 3

# ── Commit cooldown (refractory period) ──
# After a sign is committed, the gate is FORCED SHUT for this many
# seconds, even if the hand is still moving. This gives each sign its
# own clean slot: sign → commit → 1s lock → next sign.
# Set to 0.0 to disable and return to continuous gating.
COMMIT_COOLDOWN_SECONDS = 1.0
# ════════════════════════════════════════════════════════════════


# ── Rest gate: self-calibrating noise gate ──────────────────────
class RestGate:
    """
    Learns rest pose + idle noise floor at startup, then decides each
    frame whether the hand is ACTIVE (away from rest) or IDLE.
    Uses hysteresis (separate open/close thresholds) to avoid chatter.
    """
    def __init__(self):
        self.rest_pose       = None
        self.open_threshold  = None
        self.close_threshold = None
        self.is_open         = False
        self._dev_history    = deque(maxlen=DEVIATION_SMOOTH)

    def calibrate(self, rest_frames) -> float:
        arr = np.array(rest_frames)                  # (N, 10)
        self.rest_pose = arr.mean(axis=0)            # (10,)
        deviations  = np.abs(arr - self.rest_pose).mean(axis=1)
        noise_floor = float(deviations.max())
        self.open_threshold  = noise_floor * REST_MARGIN
        self.close_threshold = self.open_threshold * GATE_HYSTERESIS
        return noise_floor

    def update(self, finger_vector) -> tuple:
        raw_dev = float(np.abs(np.array(finger_vector) - self.rest_pose).mean())
        self._dev_history.append(raw_dev)
        smoothed = float(np.mean(self._dev_history))
        if self.is_open:
            if smoothed < self.close_threshold:
                self.is_open = False
        else:
            if smoothed > self.open_threshold:
                self.is_open = True
        return self.is_open, smoothed


# ── Stability filter: commit a sign only when it repeats ────────
class StabilityFilter:
    """
    Commits a sign only when the same label appears STABILITY_COUNT
    times in a row. Suppresses repeats of a held sign; A→B→A works
    because B resets what is 'committed'.
    """
    def __init__(self, count):
        self.count     = count
        self.history   = deque(maxlen=count)
        self.committed = None

    def update(self, label):
        self.history.append(label)
        if len(self.history) == self.count and len(set(self.history)) == 1:
            candidate = self.history[0]
            if candidate != self.committed:
                self.committed = candidate
                return candidate
        return None

    def reset(self):
        self.history.clear()
        self.committed = None


# ── Port selection ─────────────────────────────────────────────
def select_port() -> str:
    all_ports = list(serial.tools.list_ports.comports())
    if not all_ports:
        print("[ERROR] No serial ports found.")
        sys.exit(1)
    master_kw = ["usb single serial", "usb serial", "cdc"]
    masters   = [p for p in all_ports
                 if any(k in p.description.lower() for k in master_kw)]
    if len(masters) == 1:
        print(f"[OK] Auto-selected: {masters[0].device}  ({masters[0].description})")
        return masters[0].device
    print("\nAvailable ports:")
    for i, p in enumerate(all_ports):
        print(f"  [{i}] {p.device:<20} {p.description}")
    while True:
        try:
            idx = int(input("Select port number: "))
            if 0 <= idx < len(all_ports):
                return all_ports[idx].device
        except (ValueError, KeyboardInterrupt):
            pass


# ── Calibration ────────────────────────────────────────────────
def load_latest_calibration(profile: str):
    profile_dir = os.path.join(CALIBRATION_DIR, profile)
    if not os.path.isdir(profile_dir):
        print(f"[ERROR] Profile not found: {profile_dir}")
        sys.exit(1)
    files = sorted(f for f in os.listdir(profile_dir) if f.endswith('.json'))
    if not files:
        print(f"[ERROR] No calibration files in {profile_dir}")
        sys.exit(1)
    path = os.path.join(profile_dir, files[-1])
    print(f"[OK] Loaded calibration: {path}")
    return load_calibration(path)


# ── Model ──────────────────────────────────────────────────────
def load_model(model_path: str):
    if not os.path.exists(model_path):
        print(f"[ERROR] Model not found: {model_path}")
        print("  Copy model_v6.tflite into smart_dataset_studio/ and retry.")
        sys.exit(1)
    interp = Interpreter(model_path=model_path)
    interp.allocate_tensors()
    inp  = interp.get_input_details()
    out  = interp.get_output_details()
    ishape = inp[0]['shape']
    print(f"[OK] Model: {model_path}")
    print(f"     Input  shape: {ishape}  (expected [1, {WINDOW_SIZE}, {V6_NUM_FEATURES}])")
    print(f"     Output shape: {out[0]['shape']}  (expected [1, {len(GESTURE_LABELS)}])")
    if ishape[1] != WINDOW_SIZE or ishape[2] != V6_NUM_FEATURES:
        print("[ERROR] Shape mismatch — use model_v6.tflite (14-feature model).")
        sys.exit(1)
    return interp, inp, out


# ── Normalization (direct min/max — no Calibrator object) ──────
def _normalize(cal_data, hand: str, ch: str, val: float) -> float:
    mn = cal_data.min_values[hand][ch]
    mx = cal_data.max_values[hand][ch]
    if mn is None or mx is None or mn == mx:
        return 0.0
    return max(0.0, min(1.0, (val - mn) / (mx - mn)))


def make_filters():
    return {
        hand: {ch: EMAFilter() for ch in FINGER_CHANNELS + IMU_CHANNELS}
        for hand in ['right', 'left']
    }


def process_frame(raw_frame: dict, filters: dict, cal_data) -> dict:
    """
    EMA filter → calibration normalize.
    Finger channels normalized to 0-1; IMU channels filtered only.
    """
    out = {'frame_id': raw_frame['frame_id'], 'right': {}, 'left': {}}
    for hand in ['right', 'left']:
        for ch in FINGER_CHANNELS:
            fval = filters[hand][ch].update(raw_frame[hand][ch])
            out[hand][ch] = _normalize(cal_data, hand, ch, fval)
        for ch in IMU_CHANNELS:
            out[hand][ch] = filters[hand][ch].update(raw_frame[hand][ch])
    return out


# ── Inference (UNCHANGED — your working v6 preprocessing) ──────
def run_inference(interp, inp, out, window: deque):
    # Build raw (60, 16) array from frame dicts
    X = np.array(
        [frame_to_feature_vector(f) for f in window],
        dtype=np.float32
    )                                                  # (60, 16)

    # Drop yaw channels → (60, 14)
    X = X[:, V6_FEATURE_IDX]

    # z-score per channel over 60 frames (removes calibration drift)
    mean = X.mean(axis=0, keepdims=True)
    std  = X.std(axis=0,  keepdims=True)
    X    = (X - mean) / (std + 1e-6)

    X = np.expand_dims(X, axis=0).astype(np.float32)   # (1, 60, 14)
    interp.set_tensor(inp[0]['index'], X)
    interp.invoke()
    probs = interp.get_tensor(out[0]['index'])[0]
    idx   = int(np.argmax(probs))
    return GESTURE_LABELS[idx], float(probs[idx]), probs


# ── Rest capture at startup ────────────────────────────────────
def capture_rest(frame_queue, filters, cal_data, gate):
    print(f"\n{'='*56}")
    print(f"  REST CALIBRATION — hold both hands STILL at rest")
    print(f"  (fingers slightly curled, palm down — as during recording)")
    print(f"  Capturing for {REST_CAPTURE_SECONDS} seconds...")
    print(f"{'='*56}")
    time.sleep(0.5)

    rest_frames = []
    start = time.monotonic()
    while time.monotonic() - start < REST_CAPTURE_SECONDS:
        try:
            raw = frame_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        processed  = process_frame(raw, filters, cal_data)
        vec        = np.array(frame_to_feature_vector(processed))
        finger_vec = vec[FINGER_ONLY_IDX]          # 10 finger channels
        rest_frames.append(finger_vec)

    if len(rest_frames) < 10:
        print("[ERROR] Too few frames captured — check glove connection.")
        sys.exit(1)

    noise_floor = gate.calibrate(rest_frames)
    print(f"\n[OK] Rest baseline captured ({len(rest_frames)} frames)")
    print(f"     Idle noise floor : {noise_floor:.4f}")
    print(f"     Gate OPENS above : {gate.open_threshold:.4f}")
    print(f"     Gate CLOSES below: {gate.close_threshold:.4f}")
    if noise_floor > REST_NOISE_CEILING:
        print(f"\n[WARNING] Idle noise high ({noise_floor:.3f}). You may have moved.")
        print(f"          Restart for a cleaner baseline.")


# ── Main ───────────────────────────────────────────────────────
def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 else "model.tflite"

    print("=" * 56)
    print("  Smart Glove — Live Inference (v6 + Method 1 gating)")
    print("=" * 56)

    print("\nCalibration profiles available:")
    try:
        profiles = sorted(
            d for d in os.listdir(CALIBRATION_DIR)
            if os.path.isdir(os.path.join(CALIBRATION_DIR, d))
        )
        for p in profiles:
            print(f"  - {p}")
    except FileNotFoundError:
        print(f"[ERROR] {CALIBRATION_DIR} not found.")
        sys.exit(1)

    profile = input("\nEnter profile name (or press Enter for first): ").strip()
    if not profile:
        profile = profiles[0]
    print(f"Using profile: {profile}")

    cal_data = load_latest_calibration(profile)
    interp, inp, out = load_model(model_path)

    port         = select_port()
    frame_queue  = queue.Queue(maxsize=QUEUE_MAX_SIZE)
    serial_th    = SerialThread(port, frame_queue)
    serial_th.start()

    print("\nWaiting for serial connection to stabilise (2 seconds)...")
    time.sleep(2.0)
    while not frame_queue.empty():       # drain startup noise
        try:
            frame_queue.get_nowait()
        except queue.Empty:
            break

    filters = make_filters()
    gate    = RestGate()
    stab    = StabilityFilter(STABILITY_COUNT)

    # Learn rest pose + gate thresholds
    capture_rest(frame_queue, filters, cal_data, gate)

    window        = deque(maxlen=WINDOW_SIZE)
    running       = [True]
    stride_ctr    = 0
    prev_gate     = False
    cooldown_until = 0.0   # gate forced shut until this timestamp

    signal.signal(signal.SIGINT, lambda *_: running.__setitem__(0, False))

    print("\n" + "=" * 56)
    print("  Ready — sign naturally. Ctrl+C to stop.")
    print(f"  Stability: {STABILITY_COUNT} repeats | Confidence: {CONFIDENCE_THRESHOLD:.0%}")
    print("=" * 56 + "\n")

    while running[0]:
        raw_frame = None
        try:
            raw_frame = frame_queue.get(timeout=1.0)
        except queue.Empty:
            if running[0]:
                print("  [WARNING] No frames — check connection", end='\r')
            continue

        # Process + window every frame (window stays fresh for when gate opens)
        processed  = process_frame(raw_frame, filters, cal_data)
        full_vec   = np.array(frame_to_feature_vector(processed))
        finger_vec = full_vec[FINGER_ONLY_IDX]
        window.append(processed)

        # ── Rest gate (every frame) ───────────────────────────
        gate_open, deviation = gate.update(finger_vec)

        # ── Commit cooldown: force gate shut during refractory window ──
        now          = time.monotonic()
        in_cooldown  = now < cooldown_until
        if in_cooldown:
            gate_open = False        # locked regardless of hand motion

        # Gate just closed → hand back at rest → reset stability
        if prev_gate and not gate_open:
            stab.reset()
        prev_gate = gate_open

        # Live status: gate state + deviation bar
        ratio = deviation / max(gate.open_threshold, 1e-6)
        bar   = '#' * min(20, int(ratio * 10))
        if in_cooldown:
            remain = cooldown_until - now
            state  = f'cooldown {remain:.1f}s'
        elif gate_open:
            state  = 'ACTIVE'
        else:
            state  = ' idle '
        print(f"  [{state}] dev={deviation:.3f} {bar:<20}", end='\r')

        # Gate closed (idle or cooldown) → no inference
        if not gate_open:
            continue

        # Gate open → run inference on schedule
        stride_ctr += 1
        if len(window) < WINDOW_SIZE or stride_ctr < STRIDE:
            continue
        stride_ctr = 0

        label, conf, probs = run_inference(interp, inp, out, window)

        # Confidence gate before stability
        if conf < CONFIDENCE_THRESHOLD:
            continue

        # Stability filter — commit only when repeated
        committed = stab.update(label)
        if committed is not None:
            top3   = np.argsort(probs)[::-1][:3]
            top3_s = "  ".join(f"{GESTURE_LABELS[i]}:{probs[i]:.2f}" for i in top3)
            print(f"\n  >>> {committed}   ({conf:.0%})                                  ")
            print(f"      top3: {top3_s}")
            # ↑ This is where Phase 10 speech / WebSocket output will hook in

            # Start refractory cooldown: lock the gate, reset stability
            # so the next sign begins from a clean slate.
            if COMMIT_COOLDOWN_SECONDS > 0:
                cooldown_until = time.monotonic() + COMMIT_COOLDOWN_SECONDS
                stab.reset()
                stride_ctr = 0

    print(f"\n\nStopped.")
    serial_th.stop()
    serial_th.join(timeout=2)


if __name__ == "__main__":
    main()
