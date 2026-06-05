"""
One Euro Filter for smooth video crop stabilization.
Based on: https://hal.inria.fr/hal-00670496/document

The filter smooths jittery face detection positions while
maintaining responsiveness to sudden movements.
"""

import math
from typing import Tuple


class OneEuroFilter:
    """One Euro Filter for 2D position smoothing.
    
    Parameters:
    - min_cutoff: Minimum cutoff frequency (Hz). Lower = smoother.
      - 0.5 for very smooth (more lag)
      - 1.0 for balanced
      - 1.5+ for responsive
    
    - beta: Velocity smoothing coefficient.
      - 0.0 for no velocity response
      - 0.3 for balanced
      - 0.5+ for responsive to fast movement
    
    - d_cutoff: Derivative cutoff frequency (Hz)
    """
    
    def __init__(self, min_cutoff=1.0, beta=0.3, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        
        self.prev_raw = None
        self.prev_filtered = None
        self.prev_dx = 0.0
        
    def _alpha(self, cutoff: float, dt: float) -> float:
        """Compute exponential smoothing factor."""
        if dt <= 0:
            return 0.0
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)
    
    def filter(self, raw_value: float, dt: float = 0.03) -> float:
        """Filter a single value.
        
        Args:
            raw_value: Raw input value (e.g., x or y coordinate)
            dt: Time delta since last update (seconds). Default 0.03s (~30fps)
            
        Returns:
            Filtered value
        """
        if self.prev_raw is None:
            self.prev_raw = raw_value
            self.prev_filtered = raw_value
            return raw_value
        
        # Compute filtered derivative
        d_raw = (raw_value - self.prev_raw) / dt if dt > 0 else 0
        ed_alpha = self._alpha(self.d_cutoff, dt)
        ed_value = ed_alpha * d_raw + (1 - ed_alpha) * self.prev_dx
        
        # Compute dynamic cutoff based on velocity
        cutoff = self.min_cutoff + self.beta * abs(ed_value)
        
        # Apply low-pass filter
        alpha = self._alpha(cutoff, dt)
        filtered = alpha * raw_value + (1 - alpha) * self.prev_filtered
        
        # Update state
        self.prev_raw = raw_value
        self.prev_filtered = filtered
        self.prev_dx = ed_value
        
        return filtered


class LeadAwareOneEuroFilter(OneEuroFilter):
    """One Euro Filter with anticipatory lead for cinematic camera movement.

    Adds a 'lead' offset that positions the crop slightly ahead of the
    subject's movement direction, mimicking how a camera operator anticipates.
    """

    def __init__(self, min_cutoff=1.0, beta=0.3, d_cutoff=1.0, lead_factor=0.15):
        super().__init__(min_cutoff, beta, d_cutoff)
        self.lead_factor = lead_factor
        self._vx = 0.0
        self._vy = 0.0

    def filter_with_lead(self, raw_value: float, dt: float = 0.03) -> Tuple[float, float]:
        """Returns (filtered_value, lead_position).

        lead_position is where the camera should anticipatorily position.
        """
        if self.prev_raw is None:
            self.prev_raw = raw_value
            self.prev_filtered = raw_value
            return raw_value, raw_value

        d_raw = (raw_value - self.prev_raw) / dt if dt > 0 else 0
        ed_alpha = self._alpha(self.d_cutoff, dt)
        ed_value = ed_alpha * d_raw + (1 - ed_alpha) * self.prev_dx

        cutoff = self.min_cutoff + self.beta * abs(ed_value)
        alpha = self._alpha(cutoff, dt)
        filtered = alpha * raw_value + (1 - alpha) * self.prev_filtered

        self._vx = self._vx * 0.7 + d_raw * 0.3
        lead_offset = self.lead_factor * self._vx * dt
        lead = filtered + lead_offset

        self.prev_raw = raw_value
        self.prev_filtered = filtered
        self.prev_dx = ed_value

        return filtered, lead


class CinematicCropSmoother:
    """Crop smoother with lead/anticipation for cinematic camera movement.

    Uses two OneEuro filters: one for normal smoothing, one with lead for
    anticipatory positioning. This creates the "camera operator" feel where
    the crop leads slightly ahead of fast movement rather than following.
    """

    def __init__(self, min_cutoff=0.8, beta=0.2, lead_factor=0.15):
        self.filter_x = LeadAwareOneEuroFilter(min_cutoff=min_cutoff, beta=beta, lead_factor=lead_factor)
        self.filter_y = LeadAwareOneEuroFilter(min_cutoff=min_cutoff, beta=beta, lead_factor=lead_factor)
        self.lead_factor = lead_factor
        self.last_time = None

    def update(self, x: float, y: float, time: float = None) -> Tuple[float, float, float, float]:
        """Update with new raw position, return (smoothed_x, smoothed_y, lead_x, lead_y).

        Args:
            x: Raw x position (normalized 0-1)
            y: Raw y position (normalized 0-1)
            time: Current timestamp (optional, for dt calculation)

        Returns:
            Tuple of (smoothed_x, smoothed_y, lead_x, lead_y)
        """
        if self.last_time is not None and time is not None:
            dt = time - self.last_time
            dt = max(0.001, min(dt, 0.5))
        else:
            dt = 0.03

        smooth_x, lead_x = self.filter_x.filter_with_lead(x, dt)
        smooth_y, lead_y = self.filter_y.filter_with_lead(y, dt)

        self.last_time = time
        return smooth_x, smooth_y, lead_x, lead_y

    def update_simple(self, x: float, y: float, time: float = None) -> Tuple[float, float]:
        """Compatibility wrapper: returns only (smoothed_x, smoothed_y)."""
        smooth_x, smooth_y, _, _ = self.update(x, y, time)
        return smooth_x, smooth_y

    def reset(self):
        self.filter_x = LeadAwareOneEuroFilter(min_cutoff=self.filter_x.min_cutoff, beta=self.filter_x.beta, lead_factor=self.lead_factor)
        self.filter_y = LeadAwareOneEuroFilter(min_cutoff=self.filter_y.min_cutoff, beta=self.filter_y.beta, lead_factor=self.lead_factor)
        self.last_time = None


class CropSmoother:
    """Smooths crop positions using One Euro Filter for x and y separately."""

    def __init__(self, min_cutoff=1.0, beta=0.3):
        self.filter_x = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.filter_y = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.last_time = None

    def update(self, x: float, y: float, time: float = None) -> Tuple[float, float]:
        """Update with new raw position, return smoothed position.

        Args:
            x: Raw x position (normalized 0-1)
            y: Raw y position (normalized 0-1)
            time: Current timestamp (optional, for dt calculation)

        Returns:
            Tuple of (smoothed_x, smoothed_y)
        """
        if self.last_time is not None and time is not None:
            dt = time - self.last_time
            dt = max(0.001, min(dt, 0.5))  # Clamp dt to reasonable range
        else:
            dt = 0.03  # Default to 30fps

        smooth_x = self.filter_x.filter(x, dt)
        smooth_y = self.filter_y.filter(y, dt)

        self.last_time = time
        return smooth_x, smooth_y

    def reset(self):
        """Reset filter state."""
        self.filter_x = OneEuroFilter(min_cutoff=self.filter_x.min_cutoff, beta=self.filter_x.beta)
        self.filter_y = OneEuroFilter(min_cutoff=self.filter_y.min_cutoff, beta=self.filter_y.beta)
        self.last_time = None


def create_smoother(smoothness='medium'):
    """Factory function to create smoother with preset configurations.

    Args:
        smoothness: 'smooth' (cinematic), 'medium' (balanced), 'responsive' (fast)
    """
    presets = {
        'smooth': {'min_cutoff': 0.5, 'beta': 0.1},
        'medium': {'min_cutoff': 1.0, 'beta': 0.3},
        'responsive': {'min_cutoff': 1.5, 'beta': 0.5}
    }
    config = presets.get(smoothness, presets['medium'])
    return CropSmoother(**config)
