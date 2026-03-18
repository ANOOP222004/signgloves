# processing/filter.py
#
# EMA (Exponential Moving Average) filter for smoothing raw ADC sensor readings.
#
# Why this exists:
#   Hall sensors produce noisy ADC readings even when the finger is completely
#   still (typically +-10-20 counts of random electrical fluctuation). This noise
#   is not real finger movement. If fed directly into ML training, the model
#   learns to treat noise as signal — harming accuracy.
#
#   EMA smooths this noise by blending each new reading with the previous
#   filtered value. Real movement (sustained change across many frames) passes
#   through. Random spikes (one-frame anomalies) are absorbed.
#
# Rule: Always filter BEFORE normalizing. See calibration.py for why.

from config import EMA_ALPHA


class EMAFilter:
    """
    One EMA filter instance for one sensor channel.

    Create a separate instance for each channel:
        thumb_filter  = EMAFilter()
        index_filter  = EMAFilter()
        ... and so on for all 16 channels.

    Why a class and not a function?
    A function has no memory between calls. EMA requires remembering the
    previous filtered value. A class holds that state cleanly per instance.
    """

    def __init__(self, alpha: float = EMA_ALPHA):
        """
        alpha: smoothing factor (0.0 to 1.0)
            - Higher alpha = less smoothing, tracks signal faster
            - Lower alpha  = more smoothing, slower to respond
            - 0.25 chosen: balances noise reduction vs responsiveness at 30 Hz
        """
        self.alpha = alpha

        # previous_filtered starts as None because we have no history yet.
        # On the very first call, we use the raw value directly as the
        # starting point — there is nothing to blend with yet.
        self.previous_filtered = None

    def update(self, new_value: float) -> float:
        """
        Apply EMA to a new raw sensor reading.

        Formula: filtered = alpha * new_value + (1 - alpha) * previous_filtered

        Args:
            new_value: raw ADC integer (0-4095) or IMU float (degrees)

        Returns:
            smoothed value in the same units as new_value
        """
        if self.previous_filtered is None:
            # First reading — no history exists yet.
            # Seed the filter with the raw value so the first output
            # is reasonable rather than blending toward zero.
            self.previous_filtered = new_value
            return new_value

        # Core EMA formula.
        # new_value  contributes 25% — the "what just happened"
        # previous   contributes 75% — the "what we already believed"
        # A one-frame noise spike only shifts the output by 25% of its size.
        # Sustained real movement shifts the output fully within ~4 frames.
        filtered = self.alpha * new_value + (1 - self.alpha) * self.previous_filtered

        # Store result so next call can use it as "previous"
        self.previous_filtered = filtered

        return filtered

    def reset(self):
        """
        Clear filter state back to uninitialised.

        Call this when:
        - A new recording session starts
        - The serial connection drops and reconnects
        - Calibration is re-run

        Why: if the filter holds stale state from a previous session,
        the first few frames of the new session will be blended with
        old data — producing incorrect normalized values at the start
        of a gesture recording.
        """
        self.previous_filtered = None
