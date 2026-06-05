import subprocess
from pathlib import Path
from typing import Optional, List, Tuple, Dict, TYPE_CHECKING
import numpy as np
from config.settings import (
    OUTPUT_DIR, DEFAULT_FORMAT, VIDEO_CODEC, AUDIO_CODEC,
    VIDEO_BITRATE, AUDIO_BITRATE, DEFAULT_ASPECT_RATIO
)
from utils.progress import console, print_success, print_warning
from utils.validators import sanitize_filename
from core.smoothing import CropSmoother
from core.text_detector import TextDetector

def snap_boundaries_to_pauses(
    segments: List[dict],
    beat_pauses: List[float],
    tolerance: float = 0.4,
) -> List[dict]:
    """Snap all segment start/end boundaries to nearest beat pauses.

    Args:
        segments: List of dicts with 'start'/'end' keys (HH:MM:SS or float seconds)
        beat_pauses: List of pause center timestamps from ViralityAnalyzer.find_beat_pauses()
        tolerance: Max snap distance in seconds

    Returns:
        Segments with snapped 'start_seconds' and 'end_seconds' keys
    """
    def parse_ts(ts_val):
        """Parse timestamp (HH:MM:SS string or float)."""
        if isinstance(ts_val, (int, float)):
            return float(ts_val)
        # HH:MM:SS format
        parts = ts_val.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(ts_val)

    def snap_to_nearest(ts, pauses, tol):
        if not pauses:
            return ts
        nearest = min(pauses, key=lambda p: abs(p - ts), default=ts)
        return nearest if abs(nearest - ts) <= tol else ts

    snapped = []
    for seg in segments:
        new_seg = dict(seg)
        start_raw = seg.get("start_seconds", seg.get("start", 0))
        end_raw = seg.get("end_seconds", seg.get("end", 0))
        start_val = parse_ts(start_raw) if isinstance(start_raw, str) else start_raw
        end_val = parse_ts(end_raw) if isinstance(end_raw, str) else end_raw
        snapped_start = snap_to_nearest(start_val, beat_pauses, tolerance)
        snapped_end = snap_to_nearest(end_val, beat_pauses, tolerance)
        new_seg["start_seconds"] = snapped_start
        new_seg["end_seconds"] = snapped_end
        new_seg["_snapped"] = (
            abs(snapped_start - start_val) > 0.01 or abs(snapped_end - end_val) > 0.01
        )
        snapped.append(new_seg)
    return snapped


def _can_stream_copy(
    video_path: Path,
    source_w: int,
    source_h: int,
    source_codec: str,
    aspect_ratio: str,
    speaker_position: Optional[Tuple[float, float]],
    output_format: str,
    tolerance: float = 0.005,
) -> bool:
    """Decide whether `generate_clip` can skip re-encoding for this segment.

    All conditions must hold:
      * No speaker-tracking crop is being applied.
      * The source aspect ratio matches the requested aspect ratio within
        `tolerance` (default 0.5%).
      * The source extension and `output_format` live in the same container
        family (exact match, or both in the mp4/mov/m4v family).
      * The source video codec is something mp4 can carry without re-muxing
        pain (h264 / hevc / avc1 / hvc1).

    Caveat: when this returns True, `generate_clip` uses `-ss` *before* `-i`
    to seek. That is keyframe-aligned, so the output may start a few hundred
    ms before the requested `start_time` and end a few hundred ms after
    `end_time` (or earlier if the next cut hits a keyframe). The downstream
    re-encode path has the same property; this is a pre-existing trade-off
    between speed and exact-time accuracy. Caption timing in the rest of the
    pipeline already assumes this behavior.
    """
    if speaker_position is not None:
        return False

    if source_h <= 0 or source_w <= 0:
        return False
    source_ratio = source_w / source_h

    try:
        ratio_w, ratio_h = parse_aspect_ratio(aspect_ratio)
        target_ratio = ratio_w / ratio_h
    except Exception:
        return False
    if target_ratio <= 0:
        return False
    if abs(source_ratio - target_ratio) / target_ratio > tolerance:
        return False

    src_ext = video_path.suffix.lstrip(".").lower()
    out_fmt = (output_format or "").lower()
    mp4_family = {"mp4", "mov", "m4v"}
    same_container = src_ext == out_fmt
    mp4_compatible = src_ext in mp4_family and out_fmt in mp4_family
    if not (same_container or mp4_compatible):
        return False

    codec_ok = {"h264", "avc1", "hevc", "hvc1"}
    if source_codec and source_codec.lower() not in codec_ok:
        return False

    return True


def generate_clip(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_filename: str,
    clip_index: int,
    aspect_ratio: Optional[str] = None,
    speaker_position: Optional[Tuple[float, float]] = None,
    speaker_timeline: Optional[List[Tuple]] = None,
    output_dir: Optional[Path] = None,
    output_format: Optional[str] = None,
) -> Path:
    """Generate a single clip using FFmpeg with optional aspect ratio and speaker tracking."""
    resolved_output_dir = output_dir or OUTPUT_DIR
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    resolved_format = output_format or DEFAULT_FORMAT
    output_path = resolved_output_dir / f"{output_filename}_clip_{clip_index}.{resolved_format}"

    target_w, target_h = get_target_dimensions(aspect_ratio or DEFAULT_ASPECT_RATIO)
    info = get_video_info(video_path)
    source_w, source_h = info["width"], info["height"]
    start_str = format_time(start_time)
    duration = end_time - start_time

    if _can_stream_copy(
        video_path=video_path,
        source_w=source_w,
        source_h=source_h,
        source_codec=info.get("codec", ""),
        aspect_ratio=aspect_ratio or DEFAULT_ASPECT_RATIO,
        speaker_position=speaker_position,
        output_format=resolved_format,
    ):
        cmd = [
            "ffmpeg", "-y",
            "-ss", start_str,
            "-i", str(video_path),
            "-t", str(duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            str(output_path),
        ]
    else:
        crop_w, crop_h = get_crop_window_dimensions(source_w, source_h, aspect_ratio or DEFAULT_ASPECT_RATIO)
        crop_x, crop_y = get_crop_coordinates(
            source_w,
            source_h,
            crop_w,
            crop_h,
            speaker_position[0] if speaker_position else 0.5,
            speaker_position[1] if speaker_position else 0.4,
        )
        video_filter = build_crop_filter(crop_w, crop_h, crop_x, crop_y, target_w, target_h)
        cmd = [
            "ffmpeg", "-y", "-ss", start_str,
            "-i", str(video_path),
            "-t", str(duration),
            "-c:v", VIDEO_CODEC,
            "-c:a", AUDIO_CODEC,
            "-b:v", VIDEO_BITRATE,
            "-b:a", AUDIO_BITRATE,
            "-vf", video_filter,
            "-movflags", "+faststart",
            str(output_path)
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise Exception(
                f"FFmpeg failed (rc={result.returncode}): "
                f"stderr={result.stderr.strip()[:6000]}\n"
                f"stdout={result.stdout.strip()[:1000]}\n"
                f"cmd={' '.join(cmd)}"
            )

        if not output_path.exists():
            raise Exception(f"Clip file was not created: {output_path}")

        if output_path.stat().st_size == 0:
            raise Exception(
                f"FFmpeg returned 0 but produced a 0-byte file: {output_path}\n"
                f"stderr={result.stderr.strip()[:1500]}\n"
                f"cmd={' '.join(cmd)}"
            )

        return output_path

    except FileNotFoundError:
        raise Exception("ffmpeg not found. Install with: brew install ffmpeg")
    except Exception as e:
        raise Exception(f"Clip generation failed: {str(e)}")


def generate_clip_with_tracking(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_filename: str,
    clip_index: int,
    speaker_timeline: List[Tuple],
    aspect_ratio: Optional[str] = None,
    output_dir: Optional[Path] = None,
    output_format: Optional[str] = None,
) -> Path:
    """Generate a clip with speaker tracking using rule of thirds positioning.
    Timeline can be 4-tuples (time, speaker, x, y) or 5-tuples (time, speaker, x, y, track_id).
    Uses rule of thirds: eyes at ~33% from top of frame.
    """
    resolved_output_dir = output_dir or OUTPUT_DIR
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    resolved_format = output_format or DEFAULT_FORMAT
    output_path = resolved_output_dir / f"{output_filename}_clip_{clip_index}_tracked.{resolved_format}"
    target_w, target_h = get_target_dimensions(aspect_ratio or DEFAULT_ASPECT_RATIO)
    info = get_video_info(video_path)
    source_w, source_h = info["width"], info["height"]
    crop_w, crop_h = get_crop_window_dimensions(source_w, source_h, aspect_ratio or DEFAULT_ASPECT_RATIO)
    portrait_mode = (aspect_ratio or DEFAULT_ASPECT_RATIO) in {"9:16", "4:5"}

    if portrait_mode:
        split_layout = detect_two_person_layout(speaker_timeline, start_time, end_time)
        if split_layout is not None:
            return generate_two_person_podcast_clip(
                video_path=video_path,
                start_time=start_time,
                end_time=end_time,
                output_filename=output_filename,
                clip_index=clip_index,
                speaker_timeline=speaker_timeline,
                aspect_ratio=aspect_ratio,
                output_dir=output_dir,
                output_format=output_format,
                layout=split_layout,
            )

        # Debug: explain why two-person layout was not triggered
        # Build the per-timestamp speaker map to compute simultaneous_pct
        clip_duration = end_time - start_time
        num_slots = int(clip_duration / 0.1)
        multi_speaker_slots = 0
        for i in range(num_slots):
            t = start_time + i * 0.1
            speakers_at_t = set()
            for entry in speaker_timeline:
                if len(entry) < 4:
                    continue
                timestamp = float(entry[0])
                if abs(timestamp - t) < 0.15:
                    # Check if entry has valid (non-fallback) face position
                    x_pos = float(entry[2])
                    y_pos = float(entry[3])
                    if not (abs(x_pos - 0.5) < 0.01 and abs(y_pos - 0.4) < 0.01):
                        speakers_at_t.add(entry[1])
            if len(speakers_at_t) >= 2:
                multi_speaker_slots += 1
        simultaneous_pct = multi_speaker_slots / num_slots if num_slots > 0 else 0.0
        print(f"SpeakerTracker: Two-person layout not triggered (simultaneous_pct={simultaneous_pct:.2f} < 0.25)")
        print(f"SpeakerTracker: Falling back to single-speaker tracking")

    text_detector = TextDetector() if portrait_mode else None

    segments = build_tracking_segments_v2(
        video_path, start_time, end_time,
        speaker_timeline,
        target_w, target_h, source_w, source_h,
        text_detector=text_detector,
    )

    if len(segments) == 1:
        crop_x, crop_y, seg_start, seg_end, zoom = segments[0]
        if zoom != 1.0:
            crop_w, crop_h = get_crop_window_dimensions_with_zoom(source_w, source_h, target_w / target_h, zoom)
        video_filter = build_crop_filter(crop_w, crop_h, crop_x, crop_y, target_w, target_h)
        cmd = [
            "ffmpeg", "-y", "-ss", format_time(seg_start), "-i", str(video_path),
            "-t", str(seg_end - seg_start), "-c:v", VIDEO_CODEC, "-c:a", AUDIO_CODEC,
            "-b:v", VIDEO_BITRATE, "-b:a", AUDIO_BITRATE,
            "-vf", video_filter, "-movflags", "+faststart",
            "-loglevel", "quiet", str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return output_path
        print(f"SpeakerTracker: Clip generation failed: {result.stderr[:200]}")

    return _generate_clip_with_tracking_segments(
        video_path, start_time, end_time, output_path,
        speaker_timeline, target_w, target_h, source_w, source_h
    )


def generate_concatenated_clip(
    video_path: Path,
    segments: list[dict],
    output_filename: str,
    clip_index: int,
    crossfade_duration: float = 0.3,
    output_dir: Optional[Path] = None,
    output_format: Optional[str] = None,
    smart_assembly: bool = False,
    speaker_timeline: Optional[List[Tuple]] = None,
    aspect_ratio: Optional[str] = None,
) -> Path:
    """Generate a clip from multiple segments (narrative mode).

    Args:
        smart_assembly: If True, use role-based assembly with xfade transitions
    """
    if smart_assembly:
        from core.narrative import assemble_narrative_with_roles
        return assemble_narrative_with_roles(
            video_path=video_path,
            segments=segments,
            output_filename=output_filename,
            clip_index=clip_index,
            crossfade_duration=crossfade_duration,
            speaker_timeline=speaker_timeline,
            aspect_ratio=aspect_ratio,
            output_dir=output_dir,
            output_format=output_format,
        )

    from core.narrative import concatenate_segments

    return concatenate_segments(
        video_path=video_path,
        segments=segments,
        output_filename=output_filename,
        clip_index=clip_index,
        crossfade_duration=crossfade_duration,
        output_dir=output_dir,
        output_format=output_format,
    )


def burn_captions(
    video_path: Path,
    srt_path: Path,
    output_path: Optional[Path] = None,
    caption_style: str = "pop"
) -> Path:
    """Burn subtitles into video."""
    if output_path is None:
        output_path = video_path.with_name(f"{video_path.stem}_captioned{video_path.suffix}")

    from core.caption_generator import CaptionGenerator, CaptionStyle
    style = CaptionStyle(animation=caption_style)
    gen = CaptionGenerator(style)

    output_path = gen.burn_captions(video_path, srt_path, output_path, style)

    return output_path


def get_target_dimensions(aspect_ratio: str) -> Tuple[int, int]:
    """Get target dimensions for aspect ratio."""
    return {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
        "1:1": (1080, 1080),
        "4:5": (1080, 1350)
    }.get(aspect_ratio, (1080, 1920))


def parse_aspect_ratio(aspect_ratio: str) -> Tuple[float, float]:
    """Parse strings like 9:16 into numeric ratios."""
    width_str, height_str = aspect_ratio.split(":")
    return float(width_str), float(height_str)

def get_crop_window_dimensions(
    source_w: int,
    source_h: int,
    aspect_ratio: str,
) -> Tuple[int, int]:
    """Crop size that preserves the requested aspect ratio inside the source frame."""
    ratio_w, ratio_h = parse_aspect_ratio(aspect_ratio)
    return get_crop_window_dimensions_for_ratio(source_w, source_h, ratio_w / ratio_h)

def get_crop_window_dimensions_for_ratio(
    source_w: int,
    source_h: int,
    target_ratio: float,
) -> Tuple[int, int]:
    """Crop size for a numeric width/height ratio."""
    source_ratio = source_w / source_h
    if source_ratio > target_ratio:
        crop_h = source_h
        crop_w = int(round(source_h * target_ratio))
    else:
        crop_w = source_w
        crop_h = int(round(source_w / target_ratio))

    crop_w = max(2, min(crop_w, source_w))
    crop_h = max(2, min(crop_h, source_h))
    return crop_w, crop_h


def get_crop_window_dimensions_with_zoom(
    source_w: int,
    source_h: int,
    target_ratio: float,
    zoom_factor: float = 1.0,
) -> Tuple[int, int]:
    """Crop size with optional zoom factor (>1 = zoom out)."""
    crop_w, crop_h = get_crop_window_dimensions_for_ratio(source_w, source_h, target_ratio)
    if zoom_factor != 1.0:
        new_w = int(crop_w * zoom_factor)
        new_h = int(crop_h * zoom_factor)
        new_w = min(new_w, source_w)
        new_h = min(new_h, source_h)
        crop_w, crop_h = new_w, new_h
    return crop_w, crop_h


def get_crop_coordinates(
    source_w: int,
    source_h: int,
    crop_w: int,
    crop_h: int,
    x_norm: float,
    y_norm: float,
    eye_line: float = 0.33,
) -> Tuple[int, int]:
    """Map a normalized face center to a valid crop window."""
    x_norm = float(np.clip(x_norm, 0.0, 1.0))
    y_norm = float(np.clip(y_norm, 0.0, 1.0))

    crop_center_x = x_norm * source_w
    crop_top_y = (y_norm * source_h) - crop_h * eye_line

    crop_x = int(round(crop_center_x - crop_w / 2))
    crop_y = int(round(crop_top_y))

    crop_x = max(0, min(crop_x, source_w - crop_w))
    crop_y = max(0, min(crop_y, source_h - crop_h))

    crop_x = round(crop_x / 2) * 2
    crop_y = round(crop_y / 2) * 2
    return crop_x, crop_y


def build_crop_filter(
    crop_w: int,
    crop_h: int,
    crop_x: int,
    crop_y: int,
    output_w: int,
    output_h: int,
) -> str:
    """Build FFmpeg crop+scale filter."""
    return f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={output_w}:{output_h}"


def detect_two_person_layout(
    speaker_timeline: List[Tuple],
    start_time: float,
    end_time: float,
    min_simultaneous_pct: float = 0.25,
    min_samples: int = 3,
    multi_face_ratio: float = 1.0,
) -> Optional[dict]:
    """Detect stable two-person side-by-side layout from a speaker timeline.

    Only triggers when both speakers are VISIBLE SIMULTANEOUSLY at least
    min_simultaneous_pct (default 25%) of the time slots in the clip.

    Step 1: Build per-timestamp map of which speakers are visible (valid position)
    Step 2: Count timestamps where 2+ speakers are visible simultaneously
    Step 3: Only trigger if simultaneous_pct >= min_simultaneous_pct
    Step 4: When triggered, compute layout using only simultaneous frames
    """
    if not speaker_timeline:
        return None

    clip_duration = end_time - start_time
    num_slots = int(clip_duration / 0.1)
    if num_slots <= 0:
        return None

    # Step 1: Build per-timestamp map of visible speakers
    # A speaker is "present" at time t if timeline has entry with abs(time-t) < 0.15
    # AND that entry has a valid face position (not fallback 0.5, 0.4)
    slot_speakers: List[set] = []
    for i in range(num_slots):
        t = start_time + i * 0.1
        speakers_at_t = set()
        for entry in speaker_timeline:
            if len(entry) < 4:
                continue
            timestamp = float(entry[0])
            if abs(timestamp - t) < 0.15:
                x_pos = float(entry[2])
                y_pos = float(entry[3])
                # Reject fallback positions (0.5, 0.4 is the default fallback)
                if abs(x_pos - 0.5) < 0.01 and abs(y_pos - 0.4) < 0.01:
                    continue
                speakers_at_t.add(entry[1])
        slot_speakers.append(speakers_at_t)

    # Step 2: Count how many timestamps have MULTIPLE speakers simultaneously visible
    multi_speaker_slots = sum(1 for spkr_set in slot_speakers if len(spkr_set) >= 2)
    simultaneous_pct = multi_speaker_slots / num_slots

    # Step 3: Only trigger if enough simultaneous visibility
    if simultaneous_pct < min_simultaneous_pct:
        return None

    # Also require that actual multi-face detections met the 20% threshold
    # (unless multi_face_ratio is 1.0, which means the check is disabled)
    if multi_face_ratio < 1.0 and multi_face_ratio < 0.20:
        return None

    # Step 4: Collect simultaneous frames only and compute two-person layout from those
    simultaneous_entries_by_speaker: dict = {}
    for i, speakers_at_t in enumerate(slot_speakers):
        if len(speakers_at_t) < 2:
            continue
        t = start_time + i * 0.1
        for entry in speaker_timeline:
            if len(entry) < 4:
                continue
            timestamp = float(entry[0])
            if abs(timestamp - t) >= 0.15:
                continue
            speaker = entry[1]
            if speaker not in speakers_at_t:
                continue
            x_pos = float(entry[2])
            y_pos = float(entry[3])
            if abs(x_pos - 0.5) < 0.01 and abs(y_pos - 0.4) < 0.01:
                continue
            simultaneous_entries_by_speaker.setdefault(speaker, []).append((x_pos, y_pos))

    # Need at least 2 speakers with enough samples
    if len(simultaneous_entries_by_speaker) < 2:
        return None

    ranked = sorted(
        simultaneous_entries_by_speaker.items(),
        key=lambda item: len(item[1]),
        reverse=True
    )
    if len(ranked) < 2:
        return None

    # Check min_samples for top 2 speakers
    if len(ranked[0][1]) < min_samples or len(ranked[1][1]) < min_samples:
        return None

    left = {
        "speaker": ranked[0][0],
        "samples": ranked[0][1],
        "avg_x": float(np.mean([s[0] for s in ranked[0][1]])),
        "avg_y": float(np.mean([s[1] for s in ranked[0][1]])),
    }
    right = {
        "speaker": ranked[1][0],
        "samples": ranked[1][1],
        "avg_x": float(np.mean([s[0] for s in ranked[1][1]])),
        "avg_y": float(np.mean([s[1] for s in ranked[1][1]])),
    }

    if left["avg_x"] > right["avg_x"]:
        left, right = right, left

    separation = right["avg_x"] - left["avg_x"]

    # Relaxed threshold: 0.10 since we are only using simultaneous frames now
    if separation < 0.10:
        return None

    return {
        "left": left,
        "right": right,
        "separation": separation,
    }


def build_panel_crop(
    source_w: int,
    source_h: int,
    panel_w: int,
    panel_h: int,
    x_norm: float,
    y_norm: float,
) -> Tuple[int, int, int, int]:
    """Calculate a stable crop for one speaker panel."""
    target_ratio = panel_w / panel_h
    crop_w, crop_h = get_crop_window_dimensions_for_ratio(source_w, source_h, target_ratio)
    crop_x, crop_y = get_crop_coordinates(source_w, source_h, crop_w, crop_h, x_norm, y_norm)
    return crop_w, crop_h, crop_x, crop_y


def _compute_podcast_panel_crop(source_w: int, source_h: int, face_x: float, face_y: float, panel_w: int, panel_h: int) -> Tuple[int, int, int, int]:
    """Compute stable crop for one speaker panel.

    Face should be at 50% horizontal center of panel, eyes at ~33% from top.
    Returns (crop_w, crop_h, crop_x, crop_y).
    """
    target_ratio = panel_w / panel_h
    crop_w, crop_h = get_crop_window_dimensions_for_ratio(source_w, source_h, target_ratio)
    # Face at 50% horizontal center of panel
    face_center_x = face_x * source_w
    # Eyes at ~33% from top
    crop_center_x = face_center_x
    crop_top_y = (face_y * source_h) - (crop_h * 0.33)

    crop_x = int(round(crop_center_x - crop_w / 2))
    crop_y = int(round(crop_top_y))

    crop_x = max(0, min(crop_x, source_w - crop_w))
    crop_y = max(0, min(crop_y, source_h - crop_h))
    crop_x = round(crop_x / 2) * 2
    crop_y = round(crop_y / 2) * 2

    return crop_w, crop_h, crop_x, crop_y


def _validate_crop_segment(crop_x: int, crop_y: int, crop_w: int, crop_h: int, source_w: int, source_h: int, face_x: float, face_y: float) -> bool:
    """Return True if crop keeps face mostly in frame (>60% visible)."""
    face_center_x = face_x * source_w
    face_center_y = face_y * source_h
    # Check if face center is within the crop
    if crop_x <= face_center_x <= crop_x + crop_w and crop_y <= face_center_y <= crop_y + crop_h:
        # Face is within crop, compute how much of face would be visible
        visible_left = max(crop_x, face_center_x - crop_w * 0.3)
        visible_right = min(crop_x + crop_w, face_center_x + crop_w * 0.3)
        visible_width = visible_right - visible_left

        visible_top = max(crop_y, face_center_y - crop_h * 0.2)
        visible_bottom = min(crop_y + crop_h, face_center_y + crop_h * 0.2)
        visible_height = visible_bottom - visible_top

        # Assume face is ~20% of crop width in normalized terms
        face_width_norm = 0.2
        face_height_norm = 0.25

        visible_frac_w = visible_width / (crop_w * face_width_norm) if crop_w * face_width_norm > 0 else 0
        visible_frac_h = visible_height / (crop_h * face_height_norm) if crop_h * face_height_norm > 0 else 0

        return visible_frac_w >= 0.6 and visible_frac_h >= 0.6
    return False


def generate_two_person_podcast_clip(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_filename: str,
    clip_index: int,
    speaker_timeline: List[Tuple],
    aspect_ratio: Optional[str] = None,
    output_dir: Optional[Path] = None,
    output_format: Optional[str] = None,
    layout: Optional[dict] = None,
) -> Path:
    """Render a dynamic stacked portrait layout for two-person podcasts.

    Samples speaker_timeline at 0.25s intervals and dynamically adjusts crops
    when speakers move significantly (>8% of frame width).

    Falls back to single-speaker crop if one speaker dominates (>70% of time).
    Uses two-person stacked layout only if both speakers appear for >30% of clip.
    """
    import tempfile
    from pathlib import Path as TempPath

    resolved_output_dir = output_dir or OUTPUT_DIR
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    resolved_format = output_format or DEFAULT_FORMAT
    output_path = resolved_output_dir / f"{output_filename}_clip_{clip_index}_tracked.{resolved_format}"

    target_w, target_h = get_target_dimensions(aspect_ratio or DEFAULT_ASPECT_RATIO)
    panel_h = target_h // 2
    info = get_video_info(video_path)
    source_w, source_h = info["width"], info["height"]

    layout = layout or detect_two_person_layout(speaker_timeline, start_time, end_time)
    if layout is None:
        raise ValueError("Two-person podcast layout could not be inferred")

    # Check if one speaker dominates (>70% of time) -> fall back to single-speaker crop
    clip_duration = end_time - start_time
    per_speaker_time: dict[str, float] = {}
    per_speaker: dict[str, list] = {}
    for entry in speaker_timeline:
        if len(entry) < 4:
            continue
        timestamp = float(entry[0])
        if timestamp < start_time or timestamp > end_time:
            continue
        speaker = entry[1]
        per_speaker.setdefault(speaker, []).append(entry)
        per_speaker_time[speaker] = per_speaker_time.get(speaker, 0.0) + 0.1

    if len(per_speaker) == 2:
        speakers = list(per_speaker.keys())
        time_1 = per_speaker_time.get(speakers[0], 0.0)
        time_2 = per_speaker_time.get(speakers[1], 0.0)
        total_time = time_1 + time_2

        if total_time > 0:
            # Check if one speaker dominates (>70% of active time)
            if time_1 / total_time > 0.7:
                # Speaker 1 dominates - fall back to single-speaker crop
                dominant_speaker = speakers[0]
                avg_x = sum(e[2] for e in per_speaker[dominant_speaker]) / len(per_speaker[dominant_speaker])
                avg_y = sum(e[3] for e in per_speaker[dominant_speaker]) / len(per_speaker[dominant_speaker])
                crop_w, crop_h = get_crop_window_dimensions(source_w, source_h, aspect_ratio or DEFAULT_ASPECT_RATIO)
                crop_x, crop_y = get_crop_coordinates(source_w, source_h, crop_w, crop_h, avg_x, avg_y)
                video_filter = build_crop_filter(crop_w, crop_h, crop_x, crop_y, target_w, target_h)
                cmd = [
                    "ffmpeg", "-y", "-ss", format_time(start_time), "-i", str(video_path),
                    "-t", str(clip_duration), "-c:v", VIDEO_CODEC, "-c:a", AUDIO_CODEC,
                    "-b:v", VIDEO_BITRATE, "-b:a", AUDIO_BITRATE,
                    "-vf", video_filter, "-movflags", "+faststart",
                    "-loglevel", "quiet", str(output_path)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    return output_path
            elif time_2 / total_time > 0.7:
                # Speaker 2 dominates - fall back to single-speaker crop
                dominant_speaker = speakers[1]
                avg_x = sum(e[2] for e in per_speaker[dominant_speaker]) / len(per_speaker[dominant_speaker])
                avg_y = sum(e[3] for e in per_speaker[dominant_speaker]) / len(per_speaker[dominant_speaker])
                crop_w, crop_h = get_crop_window_dimensions(source_w, source_h, aspect_ratio or DEFAULT_ASPECT_RATIO)
                crop_x, crop_y = get_crop_coordinates(source_w, source_h, crop_w, crop_h, avg_x, avg_y)
                video_filter = build_crop_filter(crop_w, crop_h, crop_x, crop_y, target_w, target_h)
                cmd = [
                    "ffmpeg", "-y", "-ss", format_time(start_time), "-i", str(video_path),
                    "-t", str(clip_duration), "-c:v", VIDEO_CODEC, "-c:a", AUDIO_CODEC,
                    "-b:v", VIDEO_BITRATE, "-b:a", AUDIO_BITRATE,
                    "-vf", video_filter, "-movflags", "+faststart",
                    "-loglevel", "quiet", str(output_path)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    return output_path
        # If both speakers appear for >30% of clip, use two-person stacked layout
        # (continue with current logic)

    left_speaker = layout["left"]["speaker"]
    right_speaker = layout["right"]["speaker"]

    # Movement threshold: 8% of frame width
    movement_threshold = source_w * 0.08

    def get_speaker_position_at_time(t: float, speaker: str):
        """Get the position of a speaker at a given time."""
        matching = [e for e in speaker_timeline if abs(e[0] - t) < 0.15 and e[1] == speaker]
        if matching:
            return matching[0][2], matching[0][3]
        # Fallback: find nearest entry for this speaker
        speaker_entries = [(e, abs(e[0] - t)) for e in speaker_timeline if e[1] == speaker]
        if speaker_entries:
            speaker_entries.sort(key=lambda x: x[1])
            return speaker_entries[0][0][2], speaker_entries[0][0][3]
        return 0.5, 0.4

    # Build segments by sampling at 0.25s intervals
    segments = []  # (seg_start, seg_end, left_x, left_y, right_x, right_y)
    sample_interval = 0.25

    t = start_time
    current_seg_start = start_time
    prev_left_x, prev_left_y = None, None
    prev_right_x, prev_right_y = None, None

    while t <= end_time:
        left_x, left_y = get_speaker_position_at_time(t, left_speaker)
        right_x, right_y = get_speaker_position_at_time(t, right_speaker)

        should_cut = False
        if prev_left_x is not None and prev_left_y is not None:
            left_moved = abs(left_x - prev_left_x) > 0.08 or abs(left_y - prev_left_y) > 0.08
            right_moved = abs(right_x - prev_right_x) > 0.08 or abs(right_y - prev_right_y) > 0.08
            if left_moved or right_moved:
                should_cut = True

        if should_cut and t - current_seg_start >= 0.3:
            segments.append((current_seg_start, t, prev_left_x, prev_left_y, prev_right_x, prev_right_y))
            current_seg_start = t

        prev_left_x, prev_left_y = left_x, left_y
        prev_right_x, prev_right_y = right_x, right_y
        t += sample_interval

    # Add final segment
    if current_seg_start < end_time:
        segments.append((current_seg_start, end_time, prev_left_x, prev_left_y, prev_right_x, prev_right_y))

    if not segments:
        # Fallback: use layout averages
        left_avg_x = layout["left"]["avg_x"]
        left_avg_y = layout["left"]["avg_y"]
        right_avg_x = layout["right"]["avg_x"]
        right_avg_y = layout["right"]["avg_y"]
        segments.append((start_time, end_time, left_avg_x, left_avg_y, right_avg_x, right_avg_y))

    # Extract and concatenate segments
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = TempPath(temp_dir)
        segment_files = []
        for i, (seg_start, seg_end, left_x, left_y, right_x, right_y) in enumerate(segments):
            seg_duration = seg_end - seg_start
            if seg_duration <= 0:
                continue

            left_crop_w, left_crop_h, left_crop_x, left_crop_y = _compute_podcast_panel_crop(
                source_w, source_h, left_x, left_y, target_w, panel_h
            )
            right_crop_w, right_crop_h, right_crop_x, right_crop_y = _compute_podcast_panel_crop(
                source_w, source_h, right_x, right_y, target_w, panel_h
            )

            # Validate crops, fallback to center if invalid
            if not _validate_crop_segment(left_crop_x, left_crop_y, left_crop_w, left_crop_h, source_w, source_h, left_x, left_y):
                left_crop_x = (source_w - left_crop_w) // 2
                left_crop_y = (source_h - left_crop_h) // 2

            if not _validate_crop_segment(right_crop_x, right_crop_y, right_crop_w, right_crop_h, source_w, source_h, right_x, right_y):
                right_crop_x = (source_w - right_crop_w) // 2
                right_crop_y = (source_h - right_crop_h) // 2

            seg_path = temp_path / f"seg_{i:03d}.mp4"
            filter_complex = (
                f"[0:v]crop={left_crop_w}:{left_crop_h}:{left_crop_x}:{left_crop_y},"
                f"scale={target_w}:{panel_h}[top];"
                f"[0:v]crop={right_crop_w}:{right_crop_h}:{right_crop_x}:{right_crop_y},"
                f"scale={target_w}:{panel_h}[bottom];"
                f"[top][bottom]vstack=inputs=2[v]"
            )

            cmd = [
                "ffmpeg", "-y",
                "-ss", format_time(seg_start),
                "-i", str(video_path),
                "-t", str(seg_duration),
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "0:a?",
                "-c:v", VIDEO_CODEC,
                "-c:a", AUDIO_CODEC,
                "-b:v", VIDEO_BITRATE,
                "-b:a", AUDIO_BITRATE,
                "-movflags", "+faststart",
                "-loglevel", "quiet",
                str(seg_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and seg_path.exists():
                segment_files.append(seg_path)

        if not segment_files:
            raise Exception("No segments could be extracted for two-person clip")

        if len(segment_files) == 1:
            if output_path.exists():
                output_path.unlink()
            segment_files[0].rename(output_path)
            return output_path

        # Concatenate all segments
        concat_file = temp_path / "concat.txt"
        with open(concat_file, "w") as f:
            for seg_file in segment_files:
                f.write(f"file '{seg_file}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c:v", VIDEO_CODEC,
            "-c:a", AUDIO_CODEC,
            "-movflags", "+faststart",
            "-loglevel", "quiet",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"Two-person composite concatenation failed: {result.stderr}")

    if not output_path.exists():
        raise Exception(f"Composite clip file was not created: {output_path}")
    return output_path


def get_video_info(video_path: Path) -> dict:
    """Get video information using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,codec_type",
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


def format_time(seconds: float) -> str:
    """Format seconds to HH:MM:SS.mmm for FFmpeg."""
    seconds = float(seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def build_tracking_segments_v2(
    video_path: Path,
    start_time: float,
    end_time: float,
    speaker_timeline: List[Tuple],
    target_w: int,
    target_h: int,
    source_w: int,
    source_h: int,
    text_detector=None,
    min_segment_duration: float = 1.5
) -> List[Tuple[int, int, float, float, float]]:
    """Build list of (crop_x, crop_y, start_time, end_time, zoom) segments.

    Timeline entries are at 0.1s resolution with direct positions (no re-interpolation).
    Uses simple nearest-sample lookup to avoid double interpolation drift.

    Cuts when movement exceeds threshold (8% of frame width/height).
    Minimum pixels threshold: 30px horizontal or 20px vertical.
    ALSO cuts when the active speaker changes, so portrait crops follow each speaker.

    Args:
        video_path: Path to video for text detection
        text_detector: TextDetector instance for text-aware zoom
        Returns: List of (crop_x, crop_y, start_time, end_time, zoom_factor)
    """
    base_crop_w, base_crop_h = get_crop_window_dimensions_for_ratio(
        source_w,
        source_h,
        target_w / target_h,
    )

    crop_w = base_crop_w
    crop_h = base_crop_h

    if not speaker_timeline:
        crop_x = (source_w - crop_w) // 2
        crop_y = (source_h - crop_h) // 2
        return [(crop_x, crop_y, start_time, end_time, 1.0)]

    # Text detection pass: sample at 0.5s intervals, cache results
    text_timestamps: Dict[float, List] = {}
    if text_detector is not None:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS)
            sample_times = []
            tt = start_time
            while tt <= end_time + 0.01:
                sample_times.append(round(tt, 3))
                tt += 0.5
            for ts in sample_times:
                frame_num = int(ts * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ok, frame = cap.read()
                if ok:
                    regions = text_detector.detect_frame(frame, ts)
                    if regions:
                        text_timestamps[round(ts, 3)] = regions
            cap.release()

    def get_position_and_speaker_at_time(t):
        """Find nearest timeline entry, returning (x, y, speaker)."""
        if not speaker_timeline:
            return 0.5, 0.4, None

        timeline_times = [e[0] for e in speaker_timeline]
        if not timeline_times:
            return 0.5, 0.4, None

        t_min, t_max = min(timeline_times), max(timeline_times)

        if t < t_min:
            entry = min(speaker_timeline, key=lambda e: abs(e[0] - t_min))
            return entry[2], entry[3], entry[1] if len(entry) > 1 else None
        elif t > t_max:
            entry = min(speaker_timeline, key=lambda e: abs(e[0] - t_max))
            return entry[2], entry[3], entry[1] if len(entry) > 1 else None

        nearest = min(speaker_timeline, key=lambda e: abs(e[0] - t), default=None)
        if nearest is None:
            return 0.5, 0.4, None

        return nearest[2], nearest[3], nearest[1] if len(nearest) > 1 else None

    def calculate_crop(x_norm, y_norm):
        """Calculate crop position to center the face in the output frame.

        For 9:16 portrait output from 16:9 landscape source:
        - Face should be at 50% horizontal center
        - Eyes should be at ~33% from top (rule of thirds)

        Applies horizontal bias adjustment to ensure face appears centered.
        Rounds to 10-pixel increments for stability.
        """
        x_norm = float(np.clip(x_norm, 0.0, 1.0))
        y_norm = float(np.clip(y_norm, 0.0, 1.0))

        x_norm_adjusted = x_norm

        crop_center_x = x_norm_adjusted * source_w
        crop_top_y = (y_norm * source_h) - (crop_h * 0.33)

        crop_x = int(round(crop_center_x - crop_w / 2))
        crop_y = int(round(crop_top_y))

        crop_x = max(0, min(crop_x, source_w - crop_w))
        crop_y = max(0, min(crop_y, source_h - crop_h))

        crop_x = round(crop_x / 10) * 10
        crop_y = round(crop_y / 10) * 10

        crop_x = max(0, min(crop_x, source_w - crop_w))
        crop_y = max(0, min(crop_y, source_h - crop_h))

        return crop_x, crop_y

    def is_valid_crop(crop_x, crop_y, x_norm, y_norm):
        """Return True if crop keeps face mostly in frame (>60% visible)."""
        face_center_x = x_norm * source_w
        face_center_y = y_norm * source_h

        # Check face visibility within crop
        if crop_x <= face_center_x <= crop_x + crop_w and crop_y <= face_center_y <= crop_y + crop_h:
            visible_left = max(crop_x, face_center_x - crop_w * 0.3)
            visible_right = min(crop_x + crop_w, face_center_x + crop_w * 0.3)
            visible_width = visible_right - visible_left

            visible_top = max(crop_y, face_center_y - crop_h * 0.2)
            visible_bottom = min(crop_y + crop_h, face_center_y + crop_h * 0.2)
            visible_height = visible_bottom - visible_top

            face_width_in_crop = crop_w * 0.2
            face_height_in_crop = crop_h * 0.25

            visible_frac_w = visible_width / face_width_in_crop if face_width_in_crop > 0 else 0
            visible_frac_h = visible_height / face_height_in_crop if face_height_in_crop > 0 else 0

            return visible_frac_w >= 0.6 and visible_frac_h >= 0.6

        return False

    # Pre-compute unique face positions per speaker from timeline
    # This gives each speaker their own stable face position for cropping
    speaker_face_positions: dict = {}
    for entry in speaker_timeline:
        if len(entry) < 4:
            continue
        ts = float(entry[0])
        if not (start_time <= ts <= end_time):
            continue
        sp = entry[1]
        x = float(entry[2])
        y = float(entry[3])
        if sp not in speaker_face_positions:
            speaker_face_positions[sp] = []
        speaker_face_positions[sp].append((x, y))

    # Compute average position per speaker
    speaker_avg_pos: dict = {}
    for sp, positions in speaker_face_positions.items():
        if positions:
            speaker_avg_pos[sp] = (
                sum(p[0] for p in positions) / len(positions),
                sum(p[1] for p in positions) / len(positions),
            )

    segments = []
    current_crop = None
    current_x_norm, current_y_norm = None, None
    current_speaker = None
    current_zoom = 1.0
    seg_start = start_time

    movement_threshold_x = source_w * 0.08
    movement_threshold_y = source_h * 0.08
    min_pixel_threshold_x = 30
    min_pixel_threshold_y = 20

    t = start_time
    while t < end_time:
        x_norm, y_norm, speaker = get_position_and_speaker_at_time(t)

        # Get text regions for this timestamp
        rounded_t = round(t, 3)
        text_regions = text_timestamps.get(rounded_t, [])

        # If speaker changed, cut immediately so new speaker gets their own crop
        if current_speaker is not None and speaker != current_speaker:
            # Use the speaker's average face position (from when THEY were on screen)
            if speaker in speaker_avg_pos:
                x_norm, y_norm = speaker_avg_pos[speaker]
            crop_x, crop_y = calculate_crop(x_norm, y_norm)

            # Apply text-aware zoom
            zoom = 1.0
            if text_regions and text_detector:
                zoom = text_detector.zoom_factor_for_regions(
                    text_regions, source_w, source_h, x_norm, y_norm, crop_w, crop_h
                )
            if zoom != 1.0:
                zoomed_w, zoomed_h = get_crop_window_dimensions_with_zoom(source_w, source_h, target_w / target_h, zoom)
                zoom_offset_x = (zoomed_w - crop_w) // 2
                zoom_offset_y = (zoomed_h - crop_h) // 2
                crop_x = max(0, min(crop_x - zoom_offset_x, source_w - zoomed_w))
                crop_y = max(0, min(crop_y - zoom_offset_y, source_h - zoomed_h))

            if current_crop is not None and (t - seg_start) >= 0.3:
                segments.append((current_crop[0], current_crop[1], seg_start, t, current_zoom))
                current_crop = (crop_x, crop_y)
                current_x_norm, current_y_norm = x_norm, y_norm
                current_speaker = speaker
                current_zoom = zoom
                seg_start = t
        else:
            crop_x, crop_y = calculate_crop(x_norm, y_norm)
            current_pos = (crop_x, crop_y)

            zoom = current_zoom
            if text_regions:
                zoom = text_detector.zoom_factor_for_regions(
                    text_regions, source_w, source_h, x_norm, y_norm, crop_w, crop_h
                )
                current_zoom = zoom

            if zoom != 1.0:
                zoomed_w, zoomed_h = get_crop_window_dimensions_with_zoom(source_w, source_h, target_w / target_h, zoom)
                zoom_offset_x = (zoomed_w - crop_w) // 2
                zoom_offset_y = (zoomed_h - crop_h) // 2
                adjusted_crop_x = crop_x - zoom_offset_x
                adjusted_crop_y = crop_y - zoom_offset_y
                adjusted_crop_x = max(0, min(adjusted_crop_x, source_w - zoomed_w))
                adjusted_crop_y = max(0, min(adjusted_crop_y, source_h - zoomed_h))
                if current_crop is None:
                    current_crop = (adjusted_crop_x, adjusted_crop_y)
                    current_x_norm, current_y_norm = x_norm, y_norm
                    current_speaker = speaker
                    seg_start = t
                else:
                    # Check pixel movement first (prevents micro-cuts)
                    pixel_moved_x = abs(adjusted_crop_x - current_crop[0])
                    pixel_moved_y = abs(adjusted_crop_y - current_crop[1])
                    pixels_ok = pixel_moved_x >= min_pixel_threshold_x or pixel_moved_y >= min_pixel_threshold_y

                    # Check normalized movement threshold (8% of frame)
                    moved = (abs(adjusted_crop_x - current_crop[0]) > movement_threshold_x or
                            abs(adjusted_crop_y - current_crop[1]) > movement_threshold_y)

                    if moved and pixels_ok and (t - seg_start) >= min_segment_duration:
                        # Additional check: if movement is under 2% of frame, suppress cut
                        small_move = (pixel_moved_x < source_w * 0.02) and (pixel_moved_y < source_h * 0.02)
                        if small_move:
                            t += 0.1
                            continue

                        # Validate current crop before adding
                        if not is_valid_crop(current_crop[0], current_crop[1], current_x_norm, current_y_norm):
                            # Replace with frame center crop
                            current_crop = ((source_w - crop_w) // 2, (source_h - crop_h) // 2)

                        segments.append((current_crop[0], current_crop[1], seg_start, t, current_zoom))
                        current_crop = (adjusted_crop_x, adjusted_crop_y)
                        current_x_norm, current_y_norm = x_norm, y_norm
                        current_speaker = speaker
                        seg_start = t
            else:
                if current_crop is None:
                    current_crop = (crop_x, crop_y)
                    current_x_norm, current_y_norm = x_norm, y_norm
                    current_speaker = speaker
                    seg_start = t
                else:
                    # Check pixel movement first (prevents micro-cuts)
                    pixel_moved_x = abs(crop_x - current_crop[0])
                    pixel_moved_y = abs(crop_y - current_crop[1])
                    pixels_ok = pixel_moved_x >= min_pixel_threshold_x or pixel_moved_y >= min_pixel_threshold_y

                    # Check normalized movement threshold (8% of frame)
                    moved = (abs(crop_x - current_crop[0]) > movement_threshold_x or
                            abs(crop_y - current_crop[1]) > movement_threshold_y)

                    if moved and pixels_ok and (t - seg_start) >= min_segment_duration:
                        # Additional check: if movement is under 2% of frame, suppress cut
                        small_move = (pixel_moved_x < source_w * 0.02) and (pixel_moved_y < source_h * 0.02)
                        if small_move:
                            t += 0.1
                            continue

                        # Validate current crop before adding
                        if not is_valid_crop(current_crop[0], current_crop[1], current_x_norm, current_y_norm):
                            # Replace with frame center crop
                            current_crop = ((source_w - crop_w) // 2, (source_h - crop_h) // 2)

                        segments.append((current_crop[0], current_crop[1], seg_start, t, current_zoom))
                        current_crop = current_pos
                        current_x_norm, current_y_norm = x_norm, y_norm
                        current_speaker = speaker
                        seg_start = t

        t += 0.1

    if current_crop is not None:
        # Validate final crop
        if current_x_norm is not None and not is_valid_crop(current_crop[0], current_crop[1], current_x_norm, current_y_norm):
            current_crop = ((source_w - crop_w) // 2, (source_h - crop_h) // 2)
        segments.append((current_crop[0], current_crop[1], seg_start, end_time, current_zoom if current_crop is not None else 1.0))

    if not segments:
        crop_x = (source_w - crop_w) // 2
        crop_y = (source_h - crop_h) // 2
        segments.append((crop_x, crop_y, start_time, end_time, 1.0))

    print(f"SpeakerTracker: Built {len(segments)} crop segments (rule of thirds)")
    return segments


def build_tracking_segments(
    speaker_timeline: List[Tuple[float, str, float, float]],
    start_time: float,
    end_time: float,
    target_w: int,
    target_h: int,
    source_w: int,
    source_h: int
) -> List[Tuple[int, int, float, float]]:
    """Build list of (crop_x, crop_y, start_time, end_time) segments from speaker timeline."""
    return build_tracking_segments_v2(
        speaker_timeline, start_time, end_time,
        target_w, target_h, source_w, source_h
    )


def get_per_second_positions(
    speaker_timeline: List[Tuple],
    start_time: float,
    end_time: float
) -> List[Tuple[float, float, float, str]]:
    """Extract per-second position snapshots from speaker timeline."""
    def extract_tuple(e):
        if len(e) >= 4:
            return (e[0], e[1], e[2], e[3])
        return (e[0], e[1], e[2], e[3] if len(e) > 3 else 0.4)

    clip_entries = [extract_tuple(e) for e in speaker_timeline
                     if len(e) >= 2 and start_time <= e[0] <= end_time]
    if not clip_entries:
        return []

    result = []
    current_x, current_y = clip_entries[0][2], clip_entries[0][3] if len(clip_entries[0]) > 3 else 0.4
    current_speaker = clip_entries[0][1]

    for t in range(int(start_time), int(end_time) + 1):
        matching = [(e[2], e[3]) for e in clip_entries if len(e) >= 4 and abs(e[0] - t) < 0.5]
        if not matching:
            matching = [(e[2],) for e in clip_entries if abs(e[0] - t) < 0.5]

        if matching:
            if len(matching[0]) >= 2:
                current_x, current_y = matching[0][0], matching[0][1]
            else:
                current_x = matching[0][0]
            speaker_entries = [(e[1], abs(e[0] - t)) for e in clip_entries if abs(e[0] - t) < 0.5]
            if speaker_entries:
                speaker_entries.sort(key=lambda x: x[1])
                current_speaker = speaker_entries[0][0]

        result.append((float(t), current_x, current_y, current_speaker))

    return result


def _generate_clip_with_tracking_segments(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_path: Path,
    speaker_timeline: List[Tuple],
    target_w: int,
    target_h: int,
    source_w: int,
    source_h: int
) -> Path:
    """Fallback segment-based tracking with rule of thirds positioning."""
    import tempfile
    from pathlib import Path as TempPath

    crop_w, crop_h = get_crop_window_dimensions_for_ratio(
        source_w,
        source_h,
        target_w / target_h,
    )

    per_second = get_per_second_positions(speaker_timeline, start_time, end_time)

    if not per_second:
        crop_x = (source_w - crop_w) // 2
        crop_y = (source_h - crop_h) // 2
        video_filter = build_crop_filter(crop_w, crop_h, crop_x, crop_y, target_w, target_h)
        cmd = [
            "ffmpeg", "-y", "-ss", format_time(start_time), "-i", str(video_path),
            "-t", str(end_time - start_time), "-c:v", VIDEO_CODEC, "-c:a", AUDIO_CODEC,
            "-b:v", VIDEO_BITRATE, "-b:a", AUDIO_BITRATE,
            "-vf", video_filter, "-movflags", "+faststart",
            "-loglevel", "quiet", str(output_path)
        ]
        subprocess.run(cmd, capture_output=True, text=True)
        return output_path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = TempPath(temp_dir)
        segment_files = []

        segments = []
        current_speaker = None
        segment_start = None
        segment_x_sum = 0.0
        segment_y_sum = 0.0
        segment_count = 0

        for t, x, y, speaker in per_second:
            if current_speaker is None:
                current_speaker = speaker
                segment_start = t
                segment_x_sum = x
                segment_y_sum = y
                segment_count = 1
            elif speaker != current_speaker or t - segment_start >= 2.0:
                avg_x = segment_x_sum / segment_count if segment_count > 0 else x
                avg_y = segment_y_sum / segment_count if segment_count > 0 else y
                segments.append((segment_start, t, current_speaker, avg_x, avg_y))
                current_speaker = speaker
                segment_start = t
                segment_x_sum = x
                segment_y_sum = y
                segment_count = 1
            else:
                segment_x_sum += x
                segment_y_sum += y
                segment_count += 1

        if current_speaker is not None:
            avg_x = segment_x_sum / segment_count if segment_count > 0 else per_second[-1][1]
            avg_y = segment_y_sum / segment_count if segment_count > 0 else per_second[-1][2]
            segments.append((segment_start, per_second[-1][0], current_speaker, avg_x, avg_y))

        for i, (seg_start, seg_end, speaker, x_norm, y_norm) in enumerate(segments):
            seg_duration = seg_end - seg_start
            if seg_duration <= 0:
                continue

            crop_x, crop_y = get_crop_coordinates(
                source_w, source_h, crop_w, crop_h, x_norm, y_norm
            )

            seg_path = temp_path / f"seg_{i:03d}{output_path.suffix}"
            video_filter = build_crop_filter(crop_w, crop_h, crop_x, crop_y, target_w, target_h)

            cmd = [
                "ffmpeg", "-y",
                "-ss", format_time(seg_start),
                "-i", str(video_path),
                "-t", str(seg_duration),
                "-c:v", VIDEO_CODEC,
                "-c:a", AUDIO_CODEC,
                "-b:v", VIDEO_BITRATE,
                "-b:a", AUDIO_BITRATE,
                "-vf", video_filter,
                "-movflags", "+faststart",
                "-loglevel", "quiet",
                str(seg_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and seg_path.exists():
                segment_files.append(seg_path)

        if not segment_files:
            raise Exception("No segments could be extracted")

        if len(segment_files) == 1:
            if output_path.exists():
                output_path.unlink()
            segment_files[0].rename(output_path)
            return output_path

        if len(segment_files) >= 2:
            try:
                from .narrative import concatenate_with_xfade
                return concatenate_with_xfade(
                    segment_files=segment_files,
                    output_path=output_path,
                    crossfade_duration=0.25,
                )
            except Exception:
                pass

        concat_file = temp_path / "concat.txt"
        with open(concat_file, "w") as f:
            for seg_file in segment_files:
                f.write(f"file '{seg_file}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c:v", VIDEO_CODEC,
            "-c:a", AUDIO_CODEC,
            "-movflags", "+faststart",
            "-loglevel", "quiet",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"Concatenation failed: {result.stderr}\nStdout: {result.stdout}")
        return output_path


def get_clip_duration(output_path: Path) -> float:
    """Get duration of a clip file."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(output_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except:
        return 0.0


def _has_audio_stream(video_path: Path) -> bool:
    """Return True if the file has at least one audio stream."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout.strip() == "audio"
    except Exception:
        return False


# Curves accepted by ffmpeg's `afade` filter. The same names are valid in
# the `geq` expression we build for the video path.
# See ffmpeg-filters.html#afade-1
VALID_FADE_CURVES = {
    "tri", "qua", "cub", "squ", "cbr", "par", "exp", "lin", "sin", "cos",
    "log", "ipar", "qua", "cbr",
}


def _sanitize_curve(curve: Optional[str]) -> str:
    """Return a valid ffmpeg fade curve name, or "" for linear.

    Invalid input falls back to linear so a typo doesn't kill the render.
    """
    if not curve:
        return ""
    c = curve.strip()
    if c in VALID_FADE_CURVES:
        return c
    return ""


def _build_geq_alpha_expr(
    fade_in_duration: float,
    fade_out_duration: float,
    duration: float,
) -> str:
    """Build a `geq` alpha expression (0-255) for fade-in + fade-out.

    The piecewise expression computes a quadratic ease-in for the fade-in
    (slow start, fast finish) and a quadratic ease-out for the fade-out
    (fast start, slow settle to black). Replace with other curves by
    editing the math here if the user wants a different shape.
    """
    if fade_in_duration > 0 and fade_out_duration > 0:
        return (
            f"if(lt(T,{fade_in_duration:.3f}),"
            f"255*(T/{fade_in_duration:.3f})*(T/{fade_in_duration:.3f}),"
            f"if(gt(T,{duration - fade_out_duration:.3f}),"
            f"255*(1-((T-({duration - fade_out_duration:.3f}))/{fade_out_duration:.3f})*"
            f"((T-({duration - fade_out_duration:.3f}))/{fade_out_duration:.3f})),"
            f"255))"
        )
    if fade_in_duration > 0:
        return (
            f"if(lt(T,{fade_in_duration:.3f}),"
            f"255*(T/{fade_in_duration:.3f})*(T/{fade_in_duration:.3f}),"
            f"255)"
        )
    return (
        f"if(gt(T,{duration - fade_out_duration:.3f}),"
        f"255*(1-((T-({duration - fade_out_duration:.3f}))/{fade_out_duration:.3f})*"
        f"((T-({duration - fade_out_duration:.3f}))/{fade_out_duration:.3f})),"
        f"255)"
    )


def apply_clip_fades(
    video_path: Path,
    fade_in_duration: float = 0.3,
    fade_out_duration: float = 0.5,
    fade_in_curve: str = "",
    fade_out_curve: str = "qua",
) -> Optional[Path]:
    """Apply a soft audio + video fade-in at the start and fade-out at the end.

    Replaces the input file in place. Safe to call on clips that were produced
    by any pipeline path (single segment, narrative concat, smart-narrative
    xfade, speaker-tracked, two-person stacked). Audio fades are skipped
    automatically when the file has no audio stream.

    Curves:
      - fade_in_curve: "" (linear) or a name from ffmpeg's `afade` curve list
        (tri, qua, cub, squ, cbr, par, exp, lin, sin, cos, log, ipar).
      - fade_out_curve: same options, default "qua" for a quadratic ease-out
        (cinematic settle-into-black).
    Invalid curve names silently fall back to linear so a typo doesn't break
    the render.

    Implementation note: ffmpeg's `fade` filter is linear only, so when a
    curve is requested we build a `geq` expression that applies the alpha
    curve per-frame, then composite over a black background. This is slower
    than the linear `fade` filter (about 3x) but produces the actual curve.

    Returns the path on success, or None if the operation failed (caller can
    keep the original file in that case).
    """
    import shutil
    import tempfile

    if video_path is None or not Path(video_path).exists():
        return None

    video_path = Path(video_path)
    duration = get_clip_duration(video_path)
    if duration <= 0:
        return None

    fade_in_duration = max(0.0, float(fade_in_duration))
    fade_out_duration = max(0.0, float(fade_out_duration))
    if fade_in_duration == 0 and fade_out_duration == 0:
        return video_path

    max_each = duration / 2.0
    fade_in_duration = min(fade_in_duration, max_each)
    fade_out_duration = min(fade_out_duration, max_each)
    fade_out_start = max(0.0, duration - fade_out_duration)

    in_curve = _sanitize_curve(fade_in_curve)
    out_curve = _sanitize_curve(fade_out_curve)
    has_video_curve = bool(in_curve or out_curve)
    has_audio = _has_audio_stream(video_path)

    tmp_path = Path(tempfile.mkstemp(
        suffix=video_path.suffix, prefix=video_path.stem + ".",
        dir=str(video_path.parent),
    )[1])

    try:
        cmd = ["ffmpeg", "-y", "-loglevel", "quiet", "-i", str(video_path)]

        if has_video_curve:
            try:
                info = get_video_info(video_path)
                width = int(info.get("width", 1920))
                height = int(info.get("height", 1080))
            except Exception:
                width, height = 1920, 1080

            alpha_expr = _build_geq_alpha_expr(
                fade_in_duration, fade_out_duration, duration,
            )
            # Make sure dimensions are even (H.264 requires this).
            width = max(2, width - (width % 2))
            height = max(2, height - (height % 2))

            filter_complex = (
                f"[0:v]format=rgba,"
                f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{alpha_expr}'"
                f"[fg];"
                f"color=c=black:s={width}x{height}:d={duration:.3f}:r=30[bg];"
                f"[bg][fg]overlay=format=auto[v]"
            )
            cmd.extend(["-filter_complex", filter_complex, "-map", "[v]"])
        else:
            # Fast path: linear fade using ffmpeg's built-in filter.
            video_filter_parts = []
            if fade_in_duration > 0:
                video_filter_parts.append(
                    f"fade=t=in:st=0:d={fade_in_duration:.3f}"
                )
            if fade_out_duration > 0:
                video_filter_parts.append(
                    f"fade=t=out:st={fade_out_start:.3f}:d={fade_out_duration:.3f}"
                )
            if video_filter_parts:
                cmd.extend(["-vf", ",".join(video_filter_parts)])

        # Audio: afade with optional curve (afade supports curves natively).
        if has_audio:
            afade_parts = []
            if fade_in_duration > 0:
                afade_parts.append(
                    f"afade=t=in:st=0:d={fade_in_duration:.3f}"
                    + (f":c={in_curve}" if in_curve else "")
                )
            if fade_out_duration > 0:
                afade_parts.append(
                    f"afade=t=out:st={fade_out_start:.3f}:d={fade_out_duration:.3f}"
                    + (f":c={out_curve}" if out_curve else "")
                )
            if afade_parts:
                cmd.extend(["-af", ",".join(afade_parts), "-map", "0:a?"])
        else:
            cmd.extend(["-map", "0:a?"])

        cmd.extend([
            "-c:v", VIDEO_CODEC,
            "-c:a", AUDIO_CODEC,
            "-b:v", VIDEO_BITRATE,
            "-b:a", AUDIO_BITRATE,
            "-movflags", "+faststart",
            str(tmp_path),
        ])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            return None

        shutil.move(str(tmp_path), str(video_path))
        return video_path
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        return None