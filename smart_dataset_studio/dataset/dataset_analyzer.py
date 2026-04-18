# dataset/dataset_analyzer.py
#
# DatasetAnalyzer — reads gesture sample files and computes statistics.
#
# Phase 7 update: supports both .npy (new) and .csv (migrated) files,
# reads from a profile-scoped path, and adds speed-filtered loading.
#
# What this does:
#   - Loads samples for a given label into a NumPy array
#   - Optionally filters by speed tag (slow / medium / fast / all)
#   - Computes per-feature mean and std across all samples
#   - Detects outlier samples (z-score > OUTLIER_Z_THRESHOLD)
#   - Returns sample counts per gesture
#
# What this does NOT do:
#   - Never writes to disk — read-only
#   - Never touches the UI — called from AnalysisTab on demand
#
# Path:
#   dataset_path should be the PROFILE path: e.g. "data/dataset/anoop/"
#   so that all operations are automatically scoped to the active profile.
#   AnalysisTab recreates this object in refresh() to pick up profile changes.

import os
import logging

import numpy as np

from config import (
    DATASET_PATH,
    GESTURE_LABELS,
    WINDOW_SIZE,
    NUM_FEATURES,
    FEATURE_ORDER,
)
from dataset.dataset_manager import _load_file, _extract_speed

logger = logging.getLogger(__name__)

OUTLIER_Z_THRESHOLD = 2.5


class DatasetAnalyzer:
    """
    Reads and analyzes gesture sample files from a profile-scoped dataset path.

    Usage:
        analyzer = DatasetAnalyzer(dataset_manager.dataset_path)

        samples = analyzer.load_label("HELLO")
        # samples.shape = (N, WINDOW_SIZE, NUM_FEATURES) or None

        filtered = analyzer.load_label_filtered("HELLO", speed="slow")
        # loads only HELLO_slow_*.npy

        stats = analyzer.compute_stats("HELLO")
        outliers = analyzer.detect_outliers("HELLO")
        counts = analyzer.all_counts()
        speed_counts = analyzer.all_speed_counts()
    """

    def __init__(self, dataset_path: str = DATASET_PATH):
        self.dataset_path = dataset_path

    # ── Core loaders ──────────────────────────────────────────────────────────

    def load_label(self, label: str) -> 'np.ndarray | None':
        """
        Load ALL samples for one gesture label (all speeds).

        Returns:
            NumPy array (N, WINDOW_SIZE, NUM_FEATURES) or None.
        """
        return self._load_filtered(label, speed_filter='all', return_filenames=False)

    def load_label_with_filenames(self, label: str) -> 'tuple[np.ndarray | None, list]':
        """
        Load all samples and return corresponding filenames.

        Used by outlier detection — you need the filename to delete a file.

        Returns:
            (array, filenames) or (None, []).
        """
        return self._load_filtered(label, speed_filter='all', return_filenames=True)

    def load_label_filtered(self, label: str, speed: str = 'all') -> 'np.ndarray | None':
        """
        Load samples for one gesture, optionally filtered by speed.

        Args:
            label: gesture name (case-insensitive)
            speed: 'slow', 'medium', 'fast', or 'all' (no filter)

        Returns:
            NumPy array (N, WINDOW_SIZE, NUM_FEATURES) or None.
        """
        return self._load_filtered(label, speed_filter=speed.lower(), return_filenames=False)

    def load_label_filtered_with_filenames(
        self, label: str, speed: str = 'all'
    ) -> 'tuple[np.ndarray | None, list]':
        """Load filtered samples AND their filenames."""
        return self._load_filtered(label, speed_filter=speed.lower(), return_filenames=True)

    def _load_filtered(self, label: str, speed_filter: str, return_filenames: bool):
        """
        Internal loader — applies speed filter and loads both .npy and .csv.

        speed_filter='all' loads everything.
        speed_filter='slow'/'medium'/'fast' restricts to matching filenames.

        Old CSV files (no speed tag) are treated as 'medium'. When speed_filter
        is 'medium', old CSVs are included so existing data isn't invisible.
        """
        label_dir = os.path.join(self.dataset_path, label.upper())
        if not os.path.isdir(label_dir):
            return (None, []) if return_filenames else None

        all_files = sorted(
            f for f in os.listdir(label_dir)
            if f.endswith('.npy') or f.endswith('.csv')
        )

        if speed_filter != 'all':
            all_files = [f for f in all_files if _extract_speed(f) == speed_filter]

        if not all_files:
            return (None, []) if return_filenames else None

        samples   = []
        filenames = []
        for fname in all_files:
            arr = _load_file(os.path.join(label_dir, fname))
            if arr is not None:
                samples.append(arr)
                filenames.append(fname)

        if not samples:
            return (None, []) if return_filenames else None

        stacked = np.stack(samples, axis=0)   # (N, WINDOW_SIZE, NUM_FEATURES)
        if return_filenames:
            return stacked, filenames
        return stacked

    # ── Statistics ────────────────────────────────────────────────────────────

    def compute_stats(self, label: str) -> 'dict | None':
        """
        Per-feature mean and std across all samples of a gesture (all speeds).

        Flattens time axis before computing: (N, 60, 16) → (N*60, 16) → mean/std.

        Returns:
            {'mean': array(16,), 'std': array(16,), 'n_samples': int} or None.
        """
        samples = self.load_label(label)
        if samples is None:
            return None

        n, t, f = samples.shape
        flat    = samples.reshape(n * t, f)

        return {
            'n_samples': n,
            'mean':      np.mean(flat, axis=0),
            'std':       np.std(flat,  axis=0),
        }

    def compute_all_stats(self) -> dict:
        result = {}
        for label in GESTURE_LABELS:
            stats = self.compute_stats(label)
            if stats is not None:
                result[label] = stats
        return result

    # ── Outlier detection ─────────────────────────────────────────────────────

    def detect_outliers(self, label: str) -> list:
        """
        Flag samples with feature means > OUTLIER_Z_THRESHOLD std devs from global mean.

        Runs on ALL samples for the label (ignores speed filter — outlier
        detection needs the full population to compute meaningful statistics).

        Returns:
            list of dicts: {'filename', 'sample_idx', 'feature', 'z_score',
                            'value', 'mean'}, sorted by z_score descending.
            Empty list if fewer than 3 samples or no outliers found.
        """
        samples, filenames = self.load_label_with_filenames(label)
        if samples is None or len(samples) < 3:
            return []

        # Average each sample over its 60 frames: (N, 60, 16) → (N, 16)
        per_sample_mean = samples.mean(axis=1)

        global_mean = per_sample_mean.mean(axis=0)
        global_std  = per_sample_mean.std(axis=0)

        outliers = []
        for i in range(len(samples)):
            for j, feat_name in enumerate(FEATURE_ORDER):
                std_val = global_std[j]
                if std_val < 1e-6:
                    # Near-zero variance (e.g. left IMU = always 0.0) — skip
                    continue
                z = abs(per_sample_mean[i, j] - global_mean[j]) / std_val
                if z > OUTLIER_Z_THRESHOLD:
                    outliers.append({
                        'filename':   filenames[i],
                        'sample_idx': i,
                        'feature':    feat_name,
                        'z_score':    float(z),
                        'value':      float(per_sample_mean[i, j]),
                        'mean':       float(global_mean[j]),
                    })

        outliers.sort(key=lambda x: x['z_score'], reverse=True)
        return outliers

    # ── Count methods ─────────────────────────────────────────────────────────

    def all_counts(self) -> dict:
        """
        Total sample count per gesture label (all speeds combined).

        Returns:
            dict: {'HELLO': 17, 'STOP': 3, ...} including zero-count gestures.
        """
        result = {}
        for label in GESTURE_LABELS:
            label_dir = os.path.join(self.dataset_path, label.upper())
            if not os.path.isdir(label_dir):
                result[label] = 0
            else:
                result[label] = sum(
                    1 for f in os.listdir(label_dir)
                    if f.endswith('.npy') or f.endswith('.csv')
                )
        return result

    def all_speed_counts(self) -> dict:
        """
        Per-speed breakdown per gesture label.

        Old CSV files (no speed tag) count as 'medium'.

        Returns:
            dict: {'HELLO': {'slow': 5, 'medium': 8, 'fast': 4}, ...}
        """
        result = {}
        for label in GESTURE_LABELS:
            label_dir = os.path.join(self.dataset_path, label.upper())
            counts = {'slow': 0, 'medium': 0, 'fast': 0}
            if os.path.isdir(label_dir):
                for fname in os.listdir(label_dir):
                    if fname.endswith('.npy') or fname.endswith('.csv'):
                        counts[_extract_speed(fname)] += 1
            result[label] = counts
        return result
