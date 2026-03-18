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
# Calibration file save / load
# ─────────────────────────────────────────────────────────────────────────────

def save_calibration(calibration_data: CalibrationData) -> str:
    """
    Save calibration data to a JSON file.

    Filename includes today's date so each session has its own file.
    This prevents stale calibration from a previous day being reused —
    Hall sensors drift with temperature and wear.

    Returns the path of the saved file.
    """
    # Create calibration directory if it doesn't exist
    os.makedirs(CALIBRATION_DIR, exist_ok=True)

    # Date-stamped filename — one file per day
    date_str = datetime.now().strftime('%Y%m%d')
    filename = f'calibration_{date_str}.json'
    filepath = os.path.join(CALIBRATION_DIR, filename)

    # Build the dict to save
    data = {
        'date': date_str,
        'min_values': calibration_data.min_values,
        'max_values': calibration_data.max_values,
    }

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    return filepath


def load_calibration(filepath: str) -> CalibrationData:
    """
    Load calibration data from a JSON file.

    Called on startup if a calibration file exists for today.
    If no file exists, the calibration wizard runs instead.

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


def get_today_calibration_path() -> str | None:
    """
    Check if a calibration file exists for today.

    Returns the filepath if found, None if not found.
    Called on startup — if None, run calibration wizard.
    If found, load and skip wizard.
    """
    date_str = datetime.now().strftime('%Y%m%d')
    filename = f'calibration_{date_str}.json'
    filepath = os.path.join(CALIBRATION_DIR, filename)

    return filepath if os.path.exists(filepath) else None
