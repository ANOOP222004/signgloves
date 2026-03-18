# processing/calibration.py
#
# Calibration module — maps raw ADC sensor values to normalized 0.0–1.0 range.
#
# Why this exists:
#   Every Hall sensor has slightly different characteristics. The same finger
#   bend angle produces different ADC values on different sensors. Calibration
#   records each sensor's personal range (open hand = min, closed hand = max)
#   and maps that range to a universal 0.0–1.0 scale.
#
#   Without calibration:
#       Thumb open  = 2900 ADC   Thumb closed  = 1650 ADC
#       Index open  = 2800 ADC   Index closed  = 1700 ADC
#       These numbers mean different things on different sensors.
#
#   After calibration:
#       Any finger open  = 0.0
#       Any finger closed = 1.0
#       Universal language — the ML model trains on meaning, not hardware quirks.
#
# Rule: Always filter BEFORE normalizing. This module receives already-filtered
#       values from filter.py, never raw ADC integers directly.

import json
import os
from datetime import datetime
from config import (
    CALIBRATION_DIR,
    FINGER_CHANNELS,
    IMU_CHANNELS,
)


class CalibrationData:
    """
    Holds the min/max calibration values for all 10 finger channels.

    One instance per session. Created by the calibration wizard (Phase 3)
    and passed to the processing thread for use during normalization.

    IMU channels (pitch, roll, yaw) are NOT calibrated — their range is
    already universal (degrees, -180 to 180). They pass through unchanged.
    """

    def __init__(self):
        # Store min and max per finger channel.
        # Structure mirrors the frame structure — right and left hand dicts.
        # Initialised to None — means "not yet calibrated".
        self.min_values = {
            'right': {ch: None for ch in FINGER_CHANNELS},
            'left':  {ch: None for ch in FINGER_CHANNELS},
        }
        self.max_values = {
            'right': {ch: None for ch in FINGER_CHANNELS},
            'left':  {ch: None for ch in FINGER_CHANNELS},
        }

    def set_min(self, hand: str, channel: str, value: float):
        """
        Record the open-hand ADC value for one finger channel.
        Called by calibration wizard when user opens hand fully.
        """
        self.min_values[hand][channel] = value

    def set_max(self, hand: str, channel: str, value: float):
        """
        Record the closed-hand ADC value for one finger channel.
        Called by calibration wizard when user closes hand fully.
        """
        self.max_values[hand][channel] = value

    def is_complete(self) -> bool:
        """
        Returns True only if every finger channel has been calibrated.
        The processing thread checks this before starting normalization.
        """
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                if self.min_values[hand][ch] is None:
                    return False
                if self.max_values[hand][ch] is None:
                    return False
        return True


class Calibrator:
    """
    Performs normalization of filtered sensor values using calibration data.

    Receives already-filtered ADC values from filter.py.
    Returns normalized bend values (0.0–1.0) for fingers.
    Returns raw degree values unchanged for IMU channels.
    """

    def __init__(self, calibration_data: CalibrationData):
        """
        calibration_data: CalibrationData instance with min/max per channel.
        Must be complete (is_complete() == True) before normalize() is called.
        """
        self.calibration_data = calibration_data

    def normalize_finger(self, hand: str, channel: str, filtered_value: float) -> float:
        """
        Normalize one filtered finger ADC value to 0.0–1.0.

        Args:
            hand:           'right' or 'left'
            channel:        finger name e.g. 'thumb', 'index'
            filtered_value: already EMA-filtered ADC value (0–4095)

        Returns:
            float: 0.0 (open) to 1.0 (fully bent)

        The dummy channel detection:
            If max == min, the sensor never moved during calibration.
            This means it's a dummy channel (always sending same ADC value).
            Dividing by zero would crash Python — return 0.0 safely instead.
            When real sensors arrive, max != min and this branch never triggers.
        """
        min_val = self.calibration_data.min_values[hand][channel]
        max_val = self.calibration_data.max_values[hand][channel]

        # Dummy channel detection — safe division by zero handling.
        # Also handles the edge case where calibration was done incorrectly
        # and both readings happened to be identical.
        if max_val == min_val:
            return 0.0

        # Core normalization formula.
        # Maps the sensor's personal range to universal 0.0–1.0.
        bend = (filtered_value - min_val) / (max_val - min_val)

        # Clamp to 0.0–1.0.
        # Why clamp? Filtered values can occasionally exceed the calibrated
        # range slightly — especially at the very start of a session before
        # the EMA filter has fully settled. Clamping prevents values like
        # -0.02 or 1.03 from entering the dataset.
        return max(0.0, min(1.0, bend))

    def normalize_frame(self, raw_frame: dict) -> dict:
        """
        Normalize an entire raw frame — all 16 channels.

        Takes a Raw Frame dict (from frame.py) and returns a Processed Frame
        dict with finger values normalized to 0.0–1.0 and IMU values unchanged.

        Args:
            raw_frame: Raw Frame dict with structure:
                {
                    'frame_id': int,
                    'right': {'thumb': int, 'index': int, ..., 'pitch': float, ...},
                    'left':  {'thumb': int, 'index': int, ..., 'pitch': float, ...}
                }

        Returns:
            Processed Frame dict with same structure but:
                - finger values: float 0.0–1.0
                - IMU values: float degrees (unchanged)
        """
        processed = {
            'frame_id': raw_frame['frame_id'],
            'right': {},
            'left': {},
        }

        for hand in ['right', 'left']:
            # Normalize finger channels — apply calibration formula
            for ch in FINGER_CHANNELS:
                processed[hand][ch] = self.normalize_finger(
                    hand, ch, raw_frame[hand][ch]
                )

            # IMU channels — pass through unchanged
            # Degrees are already universal — no calibration needed
            for ch in IMU_CHANNELS:
                processed[hand][ch] = raw_frame[hand][ch]

        return processed


# ─────────────────────────────────────────────────────────────────────────────
# Profile management
# ─────────────────────────────────────────────────────────────────────────────

def list_profiles() -> list:
    """
    Return a sorted list of existing profile names.

    Scans CALIBRATION_DIR for subdirectories — each subdirectory is one
    profile (e.g. 'anoop', 'teammate').

    Returns [] if no profiles exist yet (first run).

    Why subdirectories, not filename prefixes?
        Subdirectories scale cleanly. Each profile gets its own folder
        containing multiple date-stamped files. Prefixed filenames
        (anoop_calibration_20250318.json) are harder to list, filter,
        and reason about as the file count grows.
    """
    if not os.path.isdir(CALIBRATION_DIR):
        return []

    profiles = [
        entry for entry in os.listdir(CALIBRATION_DIR)
        if os.path.isdir(os.path.join(CALIBRATION_DIR, entry))
    ]
    return sorted(profiles)   # alphabetical order for consistent dropdown


def create_profile(profile_name: str) -> str:
    """
    Create a new profile folder under CALIBRATION_DIR.

    Args:
        profile_name: name chosen by the user (e.g. 'anoop', 'teammate')
                      Stored as-is — no forced lowercase, caller should
                      normalise if needed.

    Returns:
        The path of the created folder.

    Why exist_ok=True?
        If the folder already exists (user typed an existing name),
        this is silent — not an error. The caller (wizard) checks for
        duplicates before calling this.
    """
    profile_dir = os.path.join(CALIBRATION_DIR, profile_name)
    os.makedirs(profile_dir, exist_ok=True)
    return profile_dir


# ─────────────────────────────────────────────────────────────────────────────
# Calibration file save / load
# ─────────────────────────────────────────────────────────────────────────────

def save_calibration(calibration_data: CalibrationData, profile_name: str) -> str:
    """
    Save calibration data to a date-stamped JSON file under the profile folder.

    File is saved to:
        data/calibration/<profile_name>/calibration_<YYYYMMDD>.json

    Why per-profile folders?
        Each team member has different hand geometry and sensor placement.
        A calibration file is only valid for the person who recorded it.
        Separate folders prevent one person's calibration from overwriting
        another's on the same day.

    Args:
        calibration_data: CalibrationData with min/max per finger channel
        profile_name:     name of the user profile (e.g. 'anoop')

    Returns:
        Full filepath of the saved file.
    """
    # Ensure the profile folder exists
    # (create_profile was called by wizard, but exist_ok=True is safe insurance)
    profile_dir = os.path.join(CALIBRATION_DIR, profile_name)
    os.makedirs(profile_dir, exist_ok=True)

    # Date-stamped filename — one file per day per profile
    date_str = datetime.now().strftime('%Y%m%d')
    filename  = f'calibration_{date_str}.json'
    filepath  = os.path.join(profile_dir, filename)

    data = {
        'date':       date_str,
        'profile':    profile_name,
        'min_values': calibration_data.min_values,
        'max_values': calibration_data.max_values,
    }

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    return filepath


def load_calibration(filepath: str) -> CalibrationData:
    """
    Load calibration data from a JSON file.

    Unchanged from Phase 2 — takes a full filepath.
    Profile awareness is handled by get_today_calibration_path(),
    not here. This function doesn't need to know about profiles.

    Args:
        filepath: full path to calibration JSON file

    Returns:
        CalibrationData instance with min/max values loaded
    """
    with open(filepath, 'r') as f:
        data = json.load(f)

    cal = CalibrationData()
    cal.min_values = data['min_values']
    cal.max_values = data['max_values']

    return cal


def get_today_calibration_path(profile_name: str) -> str | None:
    """
    Check if a calibration file exists for today under the given profile.

    Args:
        profile_name: name of the user profile to check

    Returns:
        Full filepath if today's calibration exists for this profile.
        None if not found — caller should run the calibration wizard.
    """
    date_str = datetime.now().strftime('%Y%m%d')
    filename  = f'calibration_{date_str}.json'
    filepath  = os.path.join(CALIBRATION_DIR, profile_name, filename)

    return filepath if os.path.exists(filepath) else None
