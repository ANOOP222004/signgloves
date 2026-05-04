# dataset/ml_export.py
#
# MLExportWorker — Phase 8 ML export engine.
#
# Runs in a QThread so the Qt main thread stays responsive during disk I/O.
#
# What it produces:
#   If do_split=True  → X_train.npy, X_val.npy, X_test.npy  (80/10/10)
#                        y_train.npy, y_val.npy, y_test.npy
#   If do_split=False → X.npy  shape (N, 60, 16)
#                        y.npy  shape (N,)
#   Always             → label_map.json
#                        dataset_flat.csv  (one row per sample, mean per feature)
#                        export_report.txt
#
# Split strategy: per-label stratified shuffle, seed=42 for reproducibility.
# A label with 1–2 samples is placed entirely in train — never split below that.

import csv
import json
import logging
import os
import time
from datetime import datetime

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from config import (
    DATASET_PATH,
    EXPORT_PATH,
    EXPORT_TRAIN_RATIO,
    EXPORT_VAL_RATIO,
    FEATURE_ORDER,
    GESTURE_LABELS,
    NUM_FEATURES,
    WINDOW_SIZE,
)
from dataset.dataset_manager import _extract_speed, _load_file

logger = logging.getLogger(__name__)


class MLExportWorker(QThread):
    """
    Scans data/dataset/<profile>/<LABEL>/ for .npy and .csv files,
    stacks them into X (N, WINDOW_SIZE, NUM_FEATURES) float32 and
    y (N,) int32, then writes the export package to output_dir.

    Signals:
        progress_updated(current, total) — file loading progress
        log_message(msg)                 — one-line status strings
        export_complete(result_dict)     — fired on success
        export_failed(error_str)         — fired on any unrecoverable error
    """

    progress_updated = pyqtSignal(int, int)
    log_message      = pyqtSignal(str)
    export_complete  = pyqtSignal(dict)
    export_failed    = pyqtSignal(str)

    def __init__(self, output_dir: str, selected_profiles: list = None,
                 do_split: bool = True, parent=None):
        super().__init__(parent)
        self._output_dir        = output_dir
        self._selected_profiles = list(selected_profiles) if selected_profiles else []
        self._do_split          = do_split

    # ── QThread entry point ───────────────────────────────────────────────────

    def run(self):
        self._t_start = time.time()
        try:
            self._execute()
        except Exception as exc:
            logger.exception("MLExportWorker crashed")
            self.export_failed.emit(str(exc))

    # ── Main export logic ─────────────────────────────────────────────────────

    def _execute(self):
        # 1. Discover profile folders ----------------------------------------
        if not os.path.isdir(DATASET_PATH):
            self.export_failed.emit(f"Dataset folder not found: {DATASET_PATH}")
            return

        all_profiles = sorted(
            d for d in os.listdir(DATASET_PATH)
            if os.path.isdir(os.path.join(DATASET_PATH, d))
        )
        profiles = (
            [p for p in all_profiles if p in self._selected_profiles]
            if self._selected_profiles
            else all_profiles
        )

        if not profiles:
            self.export_failed.emit("No profiles found — nothing to export.")
            return

        self.log_message.emit(f"Profiles: {', '.join(profiles)}")

        # 2. Enumerate all candidate files ------------------------------------
        # Tuple: (filepath, label_str, profile_str, speed_str)
        all_files = []
        for profile in profiles:
            for label in GESTURE_LABELS:
                label_dir = os.path.join(DATASET_PATH, profile, label)
                if not os.path.isdir(label_dir):
                    continue
                for fname in sorted(os.listdir(label_dir)):
                    if fname.endswith('.npy') or fname.endswith('.csv'):
                        all_files.append((
                            os.path.join(label_dir, fname),
                            label, profile, _extract_speed(fname),
                        ))

        total_files = len(all_files)
        if total_files == 0:
            self.export_failed.emit("No sample files found — record some gestures first.")
            return

        self.log_message.emit(f"Found {total_files} files across {len(profiles)} profile(s).")
        self.progress_updated.emit(0, total_files)

        # 3. Load files -------------------------------------------------------
        X_list    = []
        y_list    = []
        meta_rows = []   # (label_str, profile_str, speed_str) parallel to X_list
        skipped   = 0

        label_to_int = {label: i for i, label in enumerate(GESTURE_LABELS)}

        for i, (fpath, label, profile, speed) in enumerate(all_files):
            arr = _load_file(fpath)
            if arr is None or arr.shape != (WINDOW_SIZE, NUM_FEATURES):
                skipped += 1
                self.log_message.emit(f"  SKIP  {os.path.basename(fpath)}  (bad shape)")
            else:
                X_list.append(arr)
                y_list.append(label_to_int[label])
                meta_rows.append((label, profile, speed))
            self.progress_updated.emit(i + 1, total_files)

        if not X_list:
            self.export_failed.emit("All files were skipped — no valid samples loaded.")
            return

        X = np.stack(X_list, axis=0).astype(np.float32)   # (N, 60, 16)
        y = np.array(y_list, dtype=np.int32)               # (N,)
        N = len(X)

        self.log_message.emit(
            f"Loaded {N} valid samples  ({skipped} skipped)"
            f"  X={X.shape}  y={y.shape}"
        )

        # 4. Per-label and per-profile counts (for report) -------------------
        per_label   = {label: int(np.sum(y == label_to_int[label]))
                       for label in GESTURE_LABELS}
        per_profile: dict = {}
        for _, prof, _ in meta_rows:
            per_profile[prof] = per_profile.get(prof, 0) + 1

        # 5. Create output directory -----------------------------------------
        os.makedirs(self._output_dir, exist_ok=True)
        output_files = []

        # 6. label_map.json --------------------------------------------------
        label_map = {label: i for i, label in enumerate(GESTURE_LABELS)}
        lm_path = os.path.join(self._output_dir, 'label_map.json')
        with open(lm_path, 'w') as f:
            json.dump(label_map, f, indent=2)
        output_files.append(lm_path)
        self.log_message.emit("Saved  label_map.json")

        # 7. X / y arrays (with optional stratified split) -------------------
        if self._do_split:
            train_idx, val_idx, test_idx = _stratified_split(
                y, EXPORT_TRAIN_RATIO, EXPORT_VAL_RATIO
            )
            for stem, idx in [('train', train_idx), ('val', val_idx), ('test', test_idx)]:
                for prefix, arr in [('X', X), ('y', y)]:
                    path = os.path.join(self._output_dir, f'{prefix}_{stem}.npy')
                    np.save(path, arr[idx])
                    output_files.append(path)
            self.log_message.emit(
                f"Saved split  train={len(train_idx)}"
                f"  val={len(val_idx)}  test={len(test_idx)}"
            )
        else:
            for stem, arr in [('X', X), ('y', y)]:
                path = os.path.join(self._output_dir, f'{stem}.npy')
                np.save(path, arr)
                output_files.append(path)
            self.log_message.emit(f"Saved  X.npy {X.shape}   y.npy {y.shape}")

        # 8. dataset_flat.csv ------------------------------------------------
        # One row per sample. Feature columns = time-mean of each of the 16
        # channels (shape collapses (60,16) → (16,)). Plus label/profile/speed.
        flat_path = os.path.join(self._output_dir, 'dataset_flat.csv')
        X_flat = X.mean(axis=1)   # (N, 16)
        header = FEATURE_ORDER + ['label_name', 'profile', 'speed']
        with open(flat_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for i in range(N):
                row = [f"{v:.6f}" for v in X_flat[i]] + list(meta_rows[i])
                writer.writerow(row)
        output_files.append(flat_path)
        self.log_message.emit(f"Saved  dataset_flat.csv  ({N} rows)")

        # 9. export_report.txt -----------------------------------------------
        duration = time.time() - self._t_start
        report_path = os.path.join(self._output_dir, 'export_report.txt')
        with open(report_path, 'w') as f:
            f.write("Smart Glove Dataset Studio — ML Export Report\n")
            f.write("=" * 50 + "\n")
            f.write(f"Timestamp     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total samples : {N}\n")
            f.write(f"Skipped files : {skipped}\n")
            f.write(f"Profiles      : {', '.join(sorted(profiles))}\n")
            f.write(
                f"Split         : {'80/10/10 stratified' if self._do_split else 'none'}\n"
            )
            f.write("\nPer-gesture sample counts:\n")
            for label in GESTURE_LABELS:
                f.write(f"  {label:<12} {per_label.get(label, 0):>4}\n")
            f.write("\nPer-profile sample counts:\n")
            for prof, cnt in sorted(per_profile.items()):
                f.write(f"  {prof:<20} {cnt:>4}\n")
            f.write("\nOutput files:\n")
            for path in output_files:
                size = os.path.getsize(path) if os.path.exists(path) else 0
                f.write(f"  {os.path.basename(path):<30} {_human_size(size)}\n")
            f.write(f"\nDuration: {duration:.1f}s\n")
        output_files.append(report_path)
        self.log_message.emit("Saved  export_report.txt")

        # 10. Emit result ----------------------------------------------------
        self.export_complete.emit({
            'total_samples':    N,
            'per_label':        per_label,
            'output_files':     output_files,
            'duration_seconds': round(duration, 1),
        })


# ── Module-level helpers ──────────────────────────────────────────────────────

def _stratified_split(y: np.ndarray, train_ratio: float, val_ratio: float):
    """
    Per-label stratified shuffle split.

    For a label with fewer than 3 samples, all samples go to train.
    Uses a fixed seed (42) so the split is reproducible.

    Returns:
        (train_indices, val_indices, test_indices) as int64 arrays.
    """
    rng = np.random.default_rng(seed=42)
    train_idx, val_idx, test_idx = [], [], []

    for label_int in np.unique(y):
        idx = np.where(y == label_int)[0].copy()
        rng.shuffle(idx)
        n = len(idx)

        if n < 3:
            train_idx.extend(idx.tolist())
            continue

        n_train = max(1, round(n * train_ratio))
        n_val   = max(0, min(round(n * val_ratio), n - n_train))
        # test receives whatever is left (may be 0 for very small labels)

        train_idx.extend(idx[:n_train].tolist())
        val_idx.extend(idx[n_train:n_train + n_val].tolist())
        test_idx.extend(idx[n_train + n_val:].tolist())

    return (
        np.array(train_idx, dtype=np.int64),
        np.array(val_idx,   dtype=np.int64),
        np.array(test_idx,  dtype=np.int64),
    )


def _human_size(n_bytes: int) -> str:
    val = float(n_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if val < 1024.0:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} TB"
