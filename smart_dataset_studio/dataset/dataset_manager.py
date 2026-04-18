# dataset/dataset_manager.py
#
# Dataset Manager — the ONLY module that reads/writes gesture sample files.
#
# Phase 7 update: profile-based folder structure + speed tagging + .npy format.
#
# New folder structure:
#   data/dataset/
#   ├── <profile>/
#   │   ├── HELLO/
#   │   │   ├── HELLO_slow_001.npy
#   │   │   ├── HELLO_medium_002.npy
#   │   │   └── HELLO_fast_003.npy
#   │   └── STOP/
#   │       └── STOP_medium_001.npy
#   └── default/
#       └── HELLO/
#           └── anoop_sample_001.csv   ← migrated old-format files
#
# Migration:
#   On first init, any data/dataset/LABEL/ folders (old structure) are moved
#   into data/dataset/default/LABEL/ automatically. Old CSV files are kept
#   as-is and readable by DatasetAnalyzer.
#
# File format:
#   .npy  — numpy array shape (WINDOW_SIZE, NUM_FEATURES), float32
#   .csv  — legacy format from Phase 4-6 (read-only after migration)
#
# Filename format (new):  LABEL_SPEED_NNN.npy  e.g. HELLO_slow_003.npy
# Sample number NNN is per-label per-profile (counts ALL speeds together).

import os
import shutil

import numpy as np

from config import DATASET_PATH, FEATURE_ORDER, WINDOW_SIZE, GESTURE_LABELS
from processing.frame import frame_to_feature_vector


class DatasetManager:
    """
    Manages the gesture dataset folder on disk with profile-based storage.

    The active profile is controlled by setting .profile_name (a plain str
    attribute). The dataset_path property auto-updates when profile_name changes,
    so callers like AnalysisTab always get the correct folder without
    needing to be notified of the change.

    Usage:
        dm = DatasetManager(profile_name="anoop")
        dm.save_sample("HELLO", frames, speed="slow")   # → HELLO_slow_001.npy
        dm.all_counts()        # {'HELLO': 1, 'STOP': 0, ...} for current profile
        dm.all_speed_counts()  # {'HELLO': {'slow': 1, 'medium': 0, 'fast': 0}, ...}
    """

    def __init__(self, profile_name: str, dataset_path: str = DATASET_PATH):
        """
        Args:
            profile_name: calibration profile name of the current user.
                          Used as the top-level subfolder under dataset_path.
            dataset_path: root folder for all gesture samples.
                          Defaults to DATASET_PATH from config.py.
        """
        self.profile_name  = profile_name.lower().strip()
        self._dataset_root = dataset_path    # e.g. "data/dataset/"

        os.makedirs(self._dataset_root, exist_ok=True)
        self._migrate_old_structure()
        os.makedirs(self.dataset_path, exist_ok=True)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def dataset_path(self) -> str:
        """
        Full path to the current profile's dataset folder.

        Evaluates profile_name dynamically — changing profile_name on this
        object automatically changes where files are read and written.
        """
        return os.path.join(self._dataset_root, self.profile_name)

    @property
    def current_profile(self) -> str:
        """Read-only view of the active profile name."""
        return self.profile_name

    # ── Migration ─────────────────────────────────────────────────────────────

    def _migrate_old_structure(self):
        """
        Move old data/dataset/LABEL/ folders to data/dataset/default/LABEL/.

        Old structure: data/dataset/HELLO/anoop_sample_001.csv
        New structure: data/dataset/default/HELLO/anoop_sample_001.csv

        Run at init so existing recordings are never lost.
        Any folder whose name matches a known GESTURE_LABEL is treated as
        an old-format label folder and moved to the 'default' profile.
        """
        for label in GESTURE_LABELS:
            old_dir = os.path.join(self._dataset_root, label)
            if os.path.isdir(old_dir):
                default_label_dir = os.path.join(self._dataset_root, 'default', label)
                os.makedirs(os.path.dirname(default_label_dir), exist_ok=True)
                # shutil.move handles the rename even across filesystems.
                shutil.move(old_dir, default_label_dir)

    # ── Core operations ───────────────────────────────────────────────────────

    def save_sample(self, label: str, frames: list, speed: str = 'medium') -> str:
        """
        Save one completed gesture sample as a speed-tagged .npy file.

        Filename format: LABEL_SPEED_NNN.npy
        Example:         HELLO_slow_003.npy

        NNN is the total count of all files for this label/profile (across
        all speeds), so the number sequence is continuous regardless of speed.
        This means each file has a unique number within its label folder.

        Args:
            label:  gesture name e.g. "HELLO" — used as subfolder name
            frames: list of exactly WINDOW_SIZE (60) processed frame dicts
            speed:  speed tag — 'slow', 'medium', or 'fast'

        Returns:
            Full filepath of the saved .npy file.

        Raises:
            ValueError: if frames list is not exactly WINDOW_SIZE long.
        """
        if len(frames) != WINDOW_SIZE:
            raise ValueError(
                f"Expected exactly {WINDOW_SIZE} frames, got {len(frames)}. "
                f"Never save a partial sample — discard and re-record."
            )

        label = label.upper().strip()
        speed = speed.lower().strip()

        label_dir = self._label_dir(label)
        os.makedirs(label_dir, exist_ok=True)

        # Count all existing files for this label (across all speeds) to get
        # the next sequential number. This keeps numbering continuous even when
        # the user alternates between slow/medium/fast recordings.
        next_num = self._total_sample_count(label) + 1
        filename = f"{label}_{speed}_{next_num:03d}.npy"
        filepath = os.path.join(label_dir, filename)

        # Build (WINDOW_SIZE, NUM_FEATURES) float32 array and save as .npy.
        # numpy's binary format is smaller than CSV, loads faster, and
        # preserves float32 precision exactly — CSV round-trips introduce
        # floating-point representation noise.
        data = np.array(
            [frame_to_feature_vector(f) for f in frames],
            dtype=np.float32
        )
        np.save(filepath, data)

        return filepath

    # ── Counting methods ──────────────────────────────────────────────────────

    def all_counts(self) -> dict:
        """
        Total sample count per gesture label for the CURRENT PROFILE.

        Counts both .npy (new) and .csv (migrated old) files so that
        existing recordings in the 'default' profile are included.

        Returns:
            dict: {'HELLO': 17, 'STOP': 3, ...} for all GESTURE_LABELS.
                  Zero is included for gestures with no samples.
        """
        result = {}
        for label in GESTURE_LABELS:
            result[label] = self._total_sample_count(label)
        return result

    def all_speed_counts(self) -> dict:
        """
        Per-speed breakdown for the CURRENT PROFILE.

        Parses filenames to extract speed tag. Old CSV files (no speed tag)
        are counted as 'medium' for backward compatibility.

        Returns:
            dict: {'HELLO': {'slow': 5, 'medium': 8, 'fast': 4}, ...}
        """
        result = {}
        for label in GESTURE_LABELS:
            label_dir = self._label_dir(label)
            counts = {'slow': 0, 'medium': 0, 'fast': 0}
            if os.path.isdir(label_dir):
                for fname in os.listdir(label_dir):
                    speed = _extract_speed(fname)
                    counts[speed] += 1
            result[label] = counts
        return result

    def profile_sample_count(self, label: str) -> int:
        """
        Total samples for the current profile for a given label (all speeds).

        Used by save_sample() and by DatasetPanel for display.
        """
        return self._total_sample_count(label.upper())

    def profile_counts(self, label: str) -> dict:
        """
        Counts split by speed for the current profile and given label.

        Retained for backward compatibility with DatasetPanel.
        Now returns speed breakdown instead of per-profile breakdown.
        """
        label_dir = self._label_dir(label.upper())
        counts = {'slow': 0, 'medium': 0, 'fast': 0}
        if not os.path.isdir(label_dir):
            return counts
        for fname in os.listdir(label_dir):
            speed = _extract_speed(fname)
            counts[speed] += 1
        return counts

    def all_profile_counts(self) -> dict:
        """
        Speed breakdown per gesture for the current profile.

        Retained for backward compatibility with DatasetPanel.
        """
        result = {}
        for label in GESTURE_LABELS:
            label_dir = self._label_dir(label)
            counts = {'slow': 0, 'medium': 0, 'fast': 0}
            if os.path.isdir(label_dir):
                for fname in os.listdir(label_dir):
                    speed = _extract_speed(fname)
                    counts[speed] += 1
            if any(v > 0 for v in counts.values()):
                result[label] = counts
        return result

    def sample_count(self, label: str) -> int:
        """Total samples for given label across all speeds (current profile)."""
        return self._total_sample_count(label.upper())

    def list_labels(self) -> list:
        """Sorted list of gesture labels that have at least one sample."""
        if not os.path.isdir(self.dataset_path):
            return []
        return sorted(
            label for label in GESTURE_LABELS
            if self._total_sample_count(label) > 0
        )

    def load_label(self, label: str) -> 'np.ndarray | None':
        """
        Load all samples for the current profile and given label.

        Returns:
            NumPy array shape (N, WINDOW_SIZE, NUM_FEATURES) or None if no data.
        """
        label_dir = self._label_dir(label.upper())
        if not os.path.isdir(label_dir):
            return None

        samples = []
        for fname in sorted(os.listdir(label_dir)):
            arr = _load_file(os.path.join(label_dir, fname))
            if arr is not None:
                samples.append(arr)

        if not samples:
            return None
        return np.stack(samples, axis=0)

    def delete_sample(self, label: str, filename: str) -> bool:
        """
        Delete a sample file by label and filename.

        Args:
            label:    gesture name (e.g. "HELLO")
            filename: base filename (e.g. "HELLO_slow_003.npy")

        Returns:
            True if deleted, False if file didn't exist.
        """
        filepath = os.path.join(self._label_dir(label.upper()), filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    # ── Private helpers ───────────────────────────────────────────────────────

    def _label_dir(self, label: str) -> str:
        """Full path to a label's subfolder within the current profile."""
        return os.path.join(self.dataset_path, label.upper())

    def _total_sample_count(self, label: str) -> int:
        """Count all valid sample files (both .npy and .csv) in a label dir."""
        label_dir = self._label_dir(label.upper())
        if not os.path.isdir(label_dir):
            return 0
        return sum(
            1 for f in os.listdir(label_dir)
            if f.endswith('.npy') or f.endswith('.csv')
        )


# ── Module-level helpers ──────────────────────────────────────────────────────

def _extract_speed(filename: str) -> str:
    """
    Extract speed tag from a filename.

    New format: HELLO_slow_001.npy → 'slow'
    Old format: anoop_sample_001.csv → 'medium' (no speed tag → default)
    """
    lower = filename.lower()
    for speed in ('slow', 'medium', 'fast'):
        if f'_{speed}_' in lower:
            return speed
    return 'medium'   # old CSV files have no speed tag → treat as medium


def _load_file(filepath: str) -> 'np.ndarray | None':
    """
    Load one sample file (either .npy or .csv) into a (WINDOW_SIZE, NUM_FEATURES) array.

    Returns None on any error so callers can skip corrupt files safely.
    """
    import logging
    import csv as _csv
    logger = logging.getLogger(__name__)

    try:
        if filepath.endswith('.npy'):
            arr = np.load(filepath)
            if arr.shape != (WINDOW_SIZE, len(FEATURE_ORDER)):
                logger.warning(f"Bad npy shape {arr.shape}: {filepath}")
                return None
            return arr.astype(np.float32)

        if filepath.endswith('.csv'):
            with open(filepath, 'r') as f:
                rows = list(_csv.reader(f))
            data_rows = rows[1:] if rows else []   # skip header
            if len(data_rows) != WINDOW_SIZE:
                logger.warning(f"CSV has {len(data_rows)} rows, expected {WINDOW_SIZE}: {filepath}")
                return None
            arr = np.array([[float(v) for v in row] for row in data_rows], dtype=np.float32)
            if arr.shape != (WINDOW_SIZE, len(FEATURE_ORDER)):
                logger.warning(f"Bad CSV shape {arr.shape}: {filepath}")
                return None
            return arr

    except Exception as e:
        logger.warning(f"Failed to load {filepath}: {e}")

    return None
