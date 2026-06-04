"""
Video processing with FFmpeg - dynamic crop, aspect ratio, speaker tracking.
"""

import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Callable
import numpy as np


class VideoProcessor:
    """FFmpeg-based video processing for dynamic reframing and aspect ratio conversion."""

    @staticmethod
    def get_video_info(video_path: Path) -> dict:
        """Get video dimensions and duration using ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "stream=width,height,codec_name",
            "-show_entries", "format=duration,size",
            "-of", "json",
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        import json
        data = json.loads(result.stdout)

        streams = data.get("streams", [{}])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        format_info = data.get("format", {})

        return {
            "width": video_stream.get("width", 1920),
            "height": video_stream.get("height", 1080),
            "codec": video_stream.get("codec_name", "h264"),
            "duration": float(format_info.get("duration", 0)),
            "size": int(format_info.get("size", 0))
        }

    @staticmethod
    def build_crop_filter(
        target_w: int,
        target_h: int,
        source_w: int,
        source_h: int,
        offset_x: float = 0.5,
        offset_y: float = 0.4
    ) -> str:
        """Build a static crop filter with given offsets.

        Args:
            target_w, target_h: Target dimensions
            source_w, source_h: Source dimensions
            offset_x, offset_y: Normalized (0-1) crop position

        Returns:
            FFmpeg filter string
        """
        # Calculate crop position from normalized offsets
        crop_x = int((source_w - target_w) * offset_x)
        crop_y = int((source_h - target_h) * offset_y)

        # Clamp to valid range
        crop_x = max(0, min(crop_x, source_w - target_w))
        crop_y = max(0, min(crop_y, source_h - target_h))

        return f"crop={target_w}:{target_h}:{crop_x}:{crop_y},scale={target_w}:{target_h}"

    @staticmethod
    def calculate_aspect_ratio_crop(
        source_w: int,
        source_h: int,
        target_ratio: str
    ) -> Tuple[int, int, int, int]:
        """Calculate crop dimensions for target aspect ratio.

        Args:
            source_w, source_h: Source video dimensions
            target_ratio: Target ratio like "9:16", "16:9", "1:1"

        Returns:
            (crop_x, crop_y, crop_w, crop_h)
        """
        ratio_map = {
            "9:16": (9/16, 16/9),
            "16:9": (16/9, 9/16),
            "1:1": (1.0, 1.0),
            "4:5": (4/5, 5/4)
        }

        target_w_ratio, target_h_ratio = ratio_map.get(target_ratio, (9/16, 16/9))

        # Calculate what the source ratio is
        source_ratio = source_w / source_h

        if source_ratio > target_w_ratio:
            # Video is wider than target - crop width
            crop_w = int(source_h * target_w_ratio)
            crop_h = source_h
            crop_x = (source_w - crop_w) // 2
            crop_y = 0
        else:
            # Video is taller than target - crop height
            crop_w = source_w
            crop_h = int(source_w / target_h_ratio)
            crop_x = 0
            crop_y = (source_h - crop_h) // 2

        return (crop_x, crop_y, crop_w, crop_h)

    @staticmethod
    def generate_dynamic_crop_script(
        position_track: List[Tuple[float, str, float, float]],  # (time, speaker, x, y)
        target_w: int,
        target_h: int,
        source_w: int,
        source_h: int,
        output_path: Path
    ) -> str:
        """Generate a filter script for dynamic crop based on speaker positions.

        Args:
            position_track: List of (time, speaker_id, x, y)
            target_w, target_h: Target dimensions
            source_w, source_h: Source dimensions

        Returns:
            Path to filter script
        """
        # Build LUT (lookup table) for position interpolation
        times = [p[0] for p in position_track]
        xs = [p[3] for p in position_track]
        ys = [p[4] for p in position_track]

        # Create a simple text-based filter script
        # Format: time x_offset y_offset (space-separated)
        filter_lines = []
        for t, speaker, x, y in position_track:
            # Calculate pixel offsets
            offset_x = int((source_w - target_w) * x)
            offset_y = int((source_h - target_h) * y)
            offset_x = max(0, min(offset_x, source_w - target_w))
            offset_y = max(0, min(offset_y, source_h - target_h))
            filter_lines.append(f"{t:.3f} {offset_x} {offset_y}")

        script_path = output_path.with_suffix(".txt")
        with open(script_path, "w") as f:
            f.write("\n".join(filter_lines))

        return str(script_path)

    @staticmethod
    def build_scale_crop_filter(
        target_w: int,
        target_h: int
    ) -> str:
        """Build a simple scale+crop filter for aspect ratio conversion.

        Returns:
            FFmpeg filter string
        """
        return f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,crop={target_w}:{target_h}"

    @staticmethod
    def apply_dynamic_crop(
        video_path: Path,
        output_path: Path,
        position_track: List[Tuple[float, str, float, float]],
        target_w: int,
        target_h: int
    ) -> Path:
        """Apply dynamic crop to video using position track.

        For simplicity, uses nearest-keyframe approach with interpolated positions.
        """
        if not position_track:
            raise ValueError("Position track is empty")

        # For a simpler implementation, we'll sample at 1-second intervals
        # and use FFmpeg's setpts filter with interpolated expressions

        # Method: Use FFmpeg with zoompan for subtle movement
        # For full dynamic tracking, we'd need to generate frame-accurate position data

        info = VideoProcessor.get_video_info(video_path)
        source_w, source_h = info["width"], info["height"]

        # For now, use a simplified approach: crop to target with speaker-based centering
        # Group by speaker and calculate average positions
        # position_track may be 4-tuple (t,sp,x,y) or 5-tuple (t,sp,x,y,track_id)
        speaker_positions = {}
        for entry in position_track:
            if len(entry) < 4:
                continue
            _, speaker, x, y = entry[0], entry[1], entry[2], entry[3]
            if speaker not in speaker_positions:
                speaker_positions[speaker] = []
            speaker_positions[speaker].append((x, y))

        avg_positions = {
            sp: (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))
            for sp, pts in speaker_positions.items()
        }

        # Build filter using the primary speaker's average position
        primary_speaker = list(avg_positions.keys())[0] if avg_positions else None
        if primary_speaker:
            avg_x, avg_y = avg_positions[primary_speaker]
        else:
            avg_x, avg_y = 0.5, 0.4

        crop_x = int((source_w - target_w) * avg_x)
        crop_y = int((source_h - target_h) * avg_y)
        crop_x = max(0, min(crop_x, source_w - target_w))
        crop_y = max(0, min(crop_y, source_h - target_h))

        filter_str = f"crop={target_w}:{target_h}:{crop_x}:{crop_y},scale={target_w}:{target_h}"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", filter_str,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        return output_path

    @staticmethod
    def convert_aspect_ratio(
        video_path: Path,
        output_path: Path,
        target_ratio: str
    ) -> Path:
        """Convert video to target aspect ratio with smart cropping.

        Args:
            video_path: Input video
            output_path: Output path
            target_ratio: "9:16", "16:9", or "1:1"

        Returns:
            Path to output video
        """
        info = VideoProcessor.get_video_info(video_path)
        source_w, source_h = info["width"], info["height"]

        crop_x, crop_y, crop_w, crop_h = VideoProcessor.calculate_aspect_ratio_crop(
            source_w, source_h, target_ratio
        )

        target_w, target_h = {
            "9:16": (1080, 1920),
            "16:9": (1920, 1080),
            "1:1": (1080, 1080)
        }.get(target_ratio, (1080, 1920))

        filter_str = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={target_w}:{target_h}"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", filter_str,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        return output_path

    @staticmethod
    def extract_segment(
        video_path: Path,
        output_path: Path,
        start_time: float,
        end_time: float,
        target_w: Optional[int] = None,
        target_h: Optional[int] = None
    ) -> Path:
        """Extract a segment with optional resizing.

        Args:
            video_path: Input video
            output_path: Output path
            start_time, end_time: Time range in seconds
            target_w, target_h: Optional target dimensions

        Returns:
            Path to output video
        """
        duration = end_time - start_time

        if target_w and target_h:
            # Resize while extracting
            filter_str = f"scale={target_w}:{target_h}"
            vf_arg = filter_str
        else:
            vf_arg = None

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", str(video_path),
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23"
        ]

        if vf_arg:
            cmd.extend(["-vf", vf_arg])

        cmd.extend([
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        return output_path