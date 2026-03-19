# dataset/dataset_manager.py
#
# Dataset Manager — the ONLY module that reads/writes gesture CSV files.
#
# Responsibility: manage the dataset folder on disk.
#   - Save a completed 60-frame sample as a profile-tagged CSV file
#   - Count samples per label (total and per-profile breakdown)
#   - List all known labels
#   - Delete a specific sample
#
# Profile-tagged filenames:
#   Every sample filename includes the recorder's profile name as a prefix.
#   This makes every sample permanently traceable to who recorded it.
#
#   Folder structure:
#     data/dataset/
#     ├── HELLO/
#     │   ├── anoop_sample_001.csv
#     │   ├── anoop_sample_002.csv
#     │   └── teammate1_sample_001.csv
#     └── STOP/
#         └── anoop_sample_001.csv
#
#   Benefits:
#     - Per-person sample counts visible at a glance
#     - Selective exclusion before ML export (filter by prefix)
#     - Full audit trail — you always know whose data trained the model
#     - Merging all profiles into one dataset requires no extra work —
#       ML export reads all CSVs in the folder regardless of prefix
#
# CSV format per file (unchanged):
#   Header: R_T,R_I,R_M,R_R,R_L,R_P,R_RL,R_Y,L_T,L_I,L_M,L_R,L_L,L_P,L_RL,L_Y
#   Rows:   60 rows × 16 columns — one row per frame
#   Values: normalized floats (0.0–1.0 for fingers, degrees for IMU)
#   Column order matches FEATURE_ORDER in config.py EXACTLY.

import os
import csv

from config import DATASET_PATH, FEATURE_ORDER, WINDOW_SIZE
from processing.frame import frame_to_feature_vector


class DatasetManager:
    """
    Manages the gesture dataset folder on disk with profile-aware filenames.

    Usage:
        dm = DatasetManager(profile_name="anoop")
        dm.save_sample("HELLO", frames)        # saves anoop_sample_001.csv
        dm.sample_count("HELLO")               # total across all profiles
        dm.profile_counts("HELLO")             # {'anoop': 2, 'teammate1': 1}
        dm.all_counts()                        # {'HELLO': 3, 'STOP': 1, ...}
        dm.all_profile_counts()                # full breakdown per label per profile
    """

    def __init__(self, profile_name: str, dataset_path: str = DATASET_PATH):
        """
        Args:
            profile_name: the calibration profile name of the current user
                          (e.g. 'anoop', 'teammate1'). Used as filename prefix.
                          Comes from CalibrationWizard → main.py → here.
            dataset_path: root folder for all gesture samples.
                          Defaults to DATASET_PATH from config.py.
        """
        # Sanitise profile name — lowercase, strip whitespace.
        # Lowercase keeps filenames consistent regardless of how the profile
        # was named (e.g. 'Anoop' and 'anoop' become the same prefix).
        self.profile_name = profile_name.lower().strip()
        self.dataset_path = dataset_path

        os.makedirs(self.dataset_path, exist_ok=True)

    # ── Core operations ───────────────────────────────────────────────

    def save_sample(self, label: str, frames: list) -> str:
        """
        Save one completed gesture sample as a profile-tagged CSV file.

        Filename format: <profile>_sample_<NNN>.csv
        Example:         anoop_sample_003.csv

        The number NNN is auto-incremented per profile per label.
        So anoop and teammate1 each have their own independent counter:
            anoop_sample_001.csv, anoop_sample_002.csv
            teammate1_sample_001.csv

        Args:
            label:  gesture name e.g. "HELLO" — used as subfolder name
            frames: list of exactly WINDOW_SIZE (60) processed frame dicts

        Returns:
            Full filepath of the saved CSV file.

        Raises:
            ValueError: if frames list is not exactly WINDOW_SIZE long.
        """
        if len(frames) != WINDOW_SIZE:
            raise ValueError(
                f"Expected exactly {WINDOW_SIZE} frames, got {len(frames)}. "
                f"Never save a partial sample — discard and re-record."
            )

        label = label.upper().strip()

        label_dir = self._label_dir(label)
        os.makedirs(label_dir, exist_ok=True)

        # Count only THIS profile's existing files for this label.
        # Each profile has its own independent counter — anoop's 003 and
        # teammate1's 003 are different files, not a conflict.
        next_num = self.profile_sample_count(label) + 1
        filename = f"{self.profile_name}_sample_{next_num:03d}.csv"
        filepath = os.path.join(label_dir, filename)

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(FEATURE_ORDER)
            for frame in frames:
                row = frame_to_feature_vector(frame)
                writer.writerow(row)

        return filepath

    # ── Counting methods ──────────────────────────────────────────────

    def sample_count(self, label: str) -> int:
        """
        Total CSV files across ALL profiles for a given label.

        Used by DatasetPanel to show the grand total per gesture.

        Args:
            label: gesture name (normalised to uppercase internally)

        Returns:
            int: total .csv files in the label folder regardless of profile
        """
        label_dir = self._label_dir(label.upper())
        if not os.path.isdir(label_dir):
            return 0
        return sum(1 for f in os.listdir(label_dir) if f.endswith('.csv'))

    def profile_sample_count(self, label: str) -> int:
        """
        CSV files recorded by the CURRENT profile for a given label.

        Used by save_sample() to compute the next file number for this profile.
        Also useful for showing "your contribution" in the UI.

        Args:
            label: gesture name (normalised to uppercase internally)

        Returns:
            int: number of files matching <profile>_sample_*.csv in label folder
        """
        label_dir = self._label_dir(label.upper())
        if not os.path.isdir(label_dir):
            return 0

        prefix = f"{self.profile_name}_sample_"
        return sum(
            1 for f in os.listdir(label_dir)
            if f.startswith(prefix) and f.endswith('.csv')
        )

    def profile_counts(self, label: str) -> dict:
        """
        Break down sample counts by profile for a given label.

        Reads filenames and extracts the profile prefix from each.
        No assumptions about which profiles exist — reads from disk.

        Example return value:
            {'anoop': 12, 'teammate1': 8, 'teammate2': 3}

        Args:
            label: gesture name

        Returns:
            dict mapping profile_name → sample count, sorted by profile name.
            Empty dict if label folder doesn't exist.
        """
        label_dir = self._label_dir(label.upper())
        if not os.path.isdir(label_dir):
            return {}

        counts = {}
        for filename in os.listdir(label_dir):
            if not filename.endswith('.csv'):
                continue

            # Filename format: <profile>_sample_<NNN>.csv
            # Split on '_sample_' to extract the profile prefix.
            # This handles profile names that themselves contain underscores
            # (e.g. 'team_member1_sample_001.csv' → profile = 'team_member1').
            if '_sample_' not in filename:
                continue   # unexpected filename format — skip safely

            profile = filename.split('_sample_')[0]
            counts[profile] = counts.get(profile, 0) + 1

        return dict(sorted(counts.items()))

    def all_counts(self) -> dict:
        """
        Total sample counts per label across all profiles.

        Used by DatasetPanel for the main count display.

        Returns:
            dict: {'HELLO': 23, 'STOP': 19, ...} sorted by label name.
        """
        if not os.path.isdir(self.dataset_path):
            return {}

        result = {}
        for entry in sorted(os.listdir(self.dataset_path)):
            full_path = os.path.join(self.dataset_path, entry)
            if os.path.isdir(full_path):
                result[entry] = self.sample_count(entry)

        return result

    def all_profile_counts(self) -> dict:
        """
        Full breakdown: per label → per profile → count.

        Used by DatasetPanel to show who recorded what.

        Example return value:
            {
                'HELLO': {'anoop': 12, 'teammate1': 8},
                'STOP':  {'anoop': 10, 'teammate1': 9, 'teammate2': 3},
                'YES':   {'anoop': 7},
            }

        Returns:
            dict of dicts, sorted by label name.
            Only includes labels that have at least one sample on disk.
        """
        if not os.path.isdir(self.dataset_path):
            return {}

        result = {}
        for entry in sorted(os.listdir(self.dataset_path)):
            full_path = os.path.join(self.dataset_path, entry)
            if os.path.isdir(full_path):
                counts = self.profile_counts(entry)
                if counts:   # skip labels with no samples
                    result[entry] = counts

        return result

    def list_labels(self) -> list:
        """
        Sorted list of gesture labels that have at least one sample.

        Returns:
            list of str, e.g. ['HELLO', 'STOP', 'YES']
        """
        if not os.path.isdir(self.dataset_path):
            return []

        labels = []
        for entry in os.listdir(self.dataset_path):
            full_path = os.path.join(self.dataset_path, entry)
            if os.path.isdir(full_path) and self.sample_count(entry) > 0:
                labels.append(entry)

        return sorted(labels)

    def delete_sample(self, label: str, profile: str, sample_num: int) -> bool:
        """
        Delete a specific sample file.

        Args:
            label:      gesture name (e.g. "HELLO")
            profile:    profile name prefix (e.g. "anoop")
            sample_num: 1-indexed sample number

        Returns:
            True if deleted, False if file didn't exist.
        """
        filename = f"{profile.lower()}_sample_{sample_num:03d}.csv"
        filepath = os.path.join(self._label_dir(label.upper()), filename)

        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    # ── Private helpers ───────────────────────────────────────────────

    def _label_dir(self, label: str) -> str:
        """Full path to a label's subfolder. All path logic lives here."""
        return os.path.join(self.dataset_path, label)
