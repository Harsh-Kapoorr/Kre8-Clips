"""
Text-aware cropping for vertical video clips.

Detects text regions (UI, captions, code, lower thirds) in video frames
and provides zoom hints so the crop can include text without cutting it.

Architecture:
- Lightweight pre-filter: OpenCV contour detection for fast text region proposals
- Deep detection: only on frames where pre-filter finds candidates
- Text region caching since text doesn't change frame-to-frame
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math

import cv2
import numpy as np


@dataclass
class TextRegion:
    """A detected text region in a video frame."""
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in pixel coords
    confidence: float = 1.0
    text: str = ""
    area: float = 0.0

    def __post_init__(self):
        x1, y1, x2, y2 = self.bbox
        self.area = float((x2 - x1) * (y2 - y1))


class TextDetector:
    """Detects text regions in video frames for text-aware cropping.

    Uses OpenCV contour-based detection as fast pre-filter.
    Text regions are cached per timestamp (text doesn't change rapidly).
    """

    def __init__(self, min_area: float = 500.0, aspect_range: Tuple[float, float] = (0.05, 10.0)):
        self.min_area = min_area
        self.aspect_range = aspect_range  # min/max width/height ratio
        self._cache: Dict[float, List[TextRegion]] = {}
        self._cache_ttl = 0.5  # seconds to cache text regions
        self._last_detect_time = -1.0

    def detect_frame(self, frame: np.ndarray, timestamp: float) -> List[TextRegion]:
        """Detect text regions in a single frame.

        Args:
            frame: BGR image (OpenCV format)
            timestamp: Video time in seconds

        Returns:
            List of TextRegion objects with pixel bounding boxes
        """
        regions = self._detect_regions_fast(frame)

        cached_regions = self._get_cached_regions(timestamp)
        if cached_regions is not None and len(regions) <= len(cached_regions):
            return cached_regions

        if regions:
            self._cache[timestamp] = regions
            self._prune_old_cache(timestamp)

        return regions

    def _detect_regions_fast(self, frame: np.ndarray) -> List[TextRegion]:
        """Fast contour-based text region detection using OpenCV.

        Detects connected components that match text geometry:
        - Rectangular with moderate aspect ratio
        - Sufficient area (not noise)
        - Not too large (likely a background region)
        """
        h, w = frame.shape[:2]
        frame_area = h * w

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=15,
            C=2
        )

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(binary, kernel, iterations=1)

        contours, hierarchy = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        regions = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch

            if area < self.min_area:
                continue

            if area > frame_area * 0.4:
                continue

            aspect = cw / ch if ch > 0 else 0
            if not (self.aspect_range[0] <= aspect <= self.aspect_range[1]):
                continue

            aspect_h = ch / cw if cw > 0 else 0
            if not (0.05 <= aspect_h <= 10.0):
                continue

            rect = cv2.minAreaRect(cnt)
            box = cv2.boxPoints(rect)
            box = np.round(box).astype(int)
            area_rect = cv2.contourArea(box)
            if area_rect > 0:
                solidity = area / area_rect
                if solidity < 0.3:
                    continue

            confidence = min(1.0, (area / (w * h)) * 50)
            regions.append(TextRegion(
                bbox=(x, y, x + cw, y + ch),
                confidence=confidence,
                area=float(area)
            ))

        return sorted(regions, key=lambda r: r.area, reverse=True)

    def _get_cached_regions(self, timestamp: float) -> Optional[List[TextRegion]]:
        """Return cached regions if timestamp is within TTL of a cache entry."""
        for cached_ts, regions in self._cache.items():
            if abs(cached_ts - timestamp) <= self._cache_ttl:
                return regions
        return None

    def _prune_old_cache(self, current_time: float):
        """Remove cache entries older than 2 * TTL."""
        cutoff = current_time - (self._cache_ttl * 2)
        self._cache = {
            ts: regs for ts, regs in self._cache.items() if ts >= cutoff
        }

    def zoom_factor_for_regions(
        self,
        regions: List[TextRegion],
        source_w: int,
        source_h: int,
        face_x: float,
        face_y: float,
        base_crop_w: int,
        base_crop_h: int,
    ) -> float:
        """Compute zoom factor needed to include text regions in crop.

        Args:
            regions: Detected text regions in pixel coords
            source_w, source_h: Source video dimensions
            face_x, face_y: Normalized face position (0-1)
            base_crop_w, base_crop_h: Base crop dimensions (no zoom)

        Returns:
            Zoom factor: 1.0 = no zoom, >1 = zoom out
        """
        if not regions:
            return 1.0

        face_px_x = face_x * source_w
        face_px_y = face_y * source_h

        crop_margin_x = base_crop_w * 0.15
        crop_margin_y = base_crop_h * 0.15

        needs_zoom_out = False
        max_required = 1.0

        for region in regions:
            x1, y1, x2, y2 = region.bbox

            text_center_x = (x1 + x2) / 2.0
            text_center_y = (y1 + y2) / 2.0

            text_left_in_crop = x1 >= (face_px_x - base_crop_w / 2 + crop_margin_x)
            text_right_in_crop = x2 <= (face_px_x + base_crop_w / 2 - crop_margin_x)
            text_top_in_crop = y1 >= (face_px_y - base_crop_h / 2 + crop_margin_y)
            text_bottom_in_crop = y2 <= (face_px_y + base_crop_h / 2 - crop_margin_y)

            if not (text_left_in_crop and text_right_in_crop and text_top_in_crop and text_bottom_in_crop):
                needs_zoom_out = True

                dx_left = max(0, (face_px_x - base_crop_w / 2) - x1)
                dx_right = max(0, x2 - (face_px_x + base_crop_w / 2))
                dy_top = max(0, (face_px_y - base_crop_h / 2) - y1)
                dy_bottom = max(0, y2 - (face_px_y + base_crop_h / 2))

                dx_needed = max(dx_left, dx_right)
                dy_needed = max(dy_top, dy_bottom)

                x_zoom = (base_crop_w + dx_needed * 2) / base_crop_w if dx_needed > 0 else 1.0
                y_zoom = (base_crop_h + dy_needed * 2) / base_crop_h if dy_needed > 0 else 1.0

                candidate = max(x_zoom, y_zoom)
                max_required = max(max_required, candidate)

        zoom = max_required if needs_zoom_out else 1.0
        return min(zoom, 1.25)

    def text_regions_outside_crop(
        self,
        regions: List[TextRegion],
        source_w: int,
        source_h: int,
        crop_x: int,
        crop_y: int,
        crop_w: int,
        crop_h: int,
        face_x: float,
        face_y: float,
    ) -> List[TextRegion]:
        """Return text regions that extend outside the crop window."""
        if not regions:
            return []

        face_px_x = face_x * source_w
        face_px_y = face_y * source_h

        outside = []
        for region in regions:
            x1, y1, x2, y2 = region.bbox

            in_crop = (
                x1 >= crop_x and x2 <= crop_x + crop_w and
                y1 >= crop_y and y2 <= crop_y + crop_h
            )
            if not in_crop:
                outside.append(region)

        return outside

    def reset(self):
        """Clear cache and state."""
        self._cache.clear()
        self._last_detect_time = -1.0