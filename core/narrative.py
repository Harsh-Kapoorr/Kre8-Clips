import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple
from config.settings import OUTPUT_DIR, DEFAULT_FORMAT, VIDEO_CODEC, AUDIO_CODEC, CROSSFADE_DURATION
from utils.progress import console
from core.clipper import (
    build_crop_filter,
    build_panel_crop,
    detect_two_person_layout,
    get_crop_coordinates,
    get_crop_window_dimensions,
)


def parse_timestamp_value(ts) -> float:
    """Parse timestamp to float seconds."""
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        parts = ts.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except ValueError:
            pass
    return 0.0


def get_speaker_position_at_time(
    speaker_timeline: List[Tuple[float, str, float, float]],
    target_time: float
) -> Tuple[float, float, str]:
    """Get speaker position (x, y, speaker_id) at a specific time.

    Args:
        speaker_timeline: List of (time, speaker, x, y) tuples
        target_time: Time to get position for

    Returns:
        Tuple of (normalized_x, normalized_y, speaker_id)
    """
    if not speaker_timeline:
        return (0.5, 0.4, "UNKNOWN")

    # Find the closest entry to target_time
    closest_entry = min(speaker_timeline, key=lambda e: abs(e[0] - target_time))
    return (closest_entry[2], closest_entry[3], closest_entry[1])


def get_dominant_speaker_for_segment(
    speaker_timeline: List[Tuple[float, str, float, float]],
    start_time: float,
    end_time: float
) -> Tuple[float, float, str]:
    """Get dominant speaker position for a segment time range.

    Args:
        speaker_timeline: List of (time, speaker, x, y) tuples
        start_time: Segment start
        end_time: Segment end

    Returns:
        Tuple of (normalized_x, normalized_y, speaker_id)
    """
    if not speaker_timeline:
        return (0.5, 0.4, "UNKNOWN")

    # Get entries within segment time range
    # speaker_timeline entries may be 4-tuple (t,sp,x,y) or 5-tuple (t,sp,x,y,track_id)
    segment_entries = [
        entry for entry in speaker_timeline
        if len(entry) >= 4 and start_time <= float(entry[0]) <= end_time
    ]

    if not segment_entries:
        # Fallback: get closest entry
        return get_speaker_position_at_time(speaker_timeline, (start_time + end_time) / 2)

    # Find dominant speaker (most entries)
    speaker_counts = {}
    speaker_positions = {}
    for entry in segment_entries:
        t, sp, x, y = entry[0], entry[1], entry[2], entry[3]
        speaker_counts[sp] = speaker_counts.get(sp, 0) + 1
        if sp not in speaker_positions:
            speaker_positions[sp] = []
        speaker_positions[sp].append((x, y))

    dominant_speaker = max(speaker_counts.keys(), key=lambda s: speaker_counts[s])
    positions = speaker_positions[dominant_speaker]
    avg_x = sum(p[0] for p in positions) / len(positions)
    avg_y = sum(p[1] for p in positions) / len(positions)

    return (avg_x, avg_y, dominant_speaker)


def concatenate_segments(
    video_path: Path,
    segments: list[dict],
    output_filename: str,
    clip_index: int,
    crossfade_duration: float = 0.1,
    speaker_timeline: Optional[List[Tuple[float, str, float, float]]] = None,
    aspect_ratio: Optional[str] = "9:16",
    output_dir: Optional[Path] = None,
    output_format: Optional[str] = None,
) -> Path:
    """Concatenate multiple video segments into a single clip with crossfades and optional speaker tracking."""
    resolved_output_dir = output_dir or OUTPUT_DIR
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    resolved_format = output_format or DEFAULT_FORMAT
    output_path = resolved_output_dir / f"{output_filename}_clip_{clip_index}_narrative.{resolved_format}"

    # Get target dimensions for aspect ratio
    target_w, target_h = {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
        "1:1": (1080, 1080),
        "4:5": (1080, 1350)
    }.get(aspect_ratio or "9:16", (1080, 1920))

    # Get source dimensions
    source_w, source_h = get_video_source_dimensions(video_path)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Extract each segment with optional speaker tracking crop
        segment_files = []
        for i, segment in enumerate(segments):
            start = parse_timestamp_value(segment.get("start", 0))
            end = parse_timestamp_value(segment.get("end", start))

            segment_path = temp_path / f"segment_{i:03d}.{resolved_format}"

            # Calculate speaker position for this segment
            crop_x, crop_y = 0, 0
            video_filter = None

            crop_w, crop_h = get_crop_window_dimensions(source_w, source_h, aspect_ratio or "9:16")
            split_layout = None
            portrait_mode = (aspect_ratio or "9:16") in {"9:16", "4:5"}
            if speaker_timeline and portrait_mode:
                split_layout = detect_two_person_layout(speaker_timeline, float(start), float(end))

            if split_layout:
                left = split_layout["left"]
                right = split_layout["right"]
                panel_h = target_h // 2
                left_crop_w, left_crop_h, left_crop_x, left_crop_y = build_panel_crop(
                    source_w, source_h, target_w, panel_h, left["avg_x"], left["avg_y"]
                )
                right_crop_w, right_crop_h, right_crop_x, right_crop_y = build_panel_crop(
                    source_w, source_h, target_w, panel_h, right["avg_x"], right["avg_y"]
                )
                video_filter = (
                    f"[0:v]crop={left_crop_w}:{left_crop_h}:{left_crop_x}:{left_crop_y},"
                    f"scale={target_w}:{panel_h}[top];"
                    f"[0:v]crop={right_crop_w}:{right_crop_h}:{right_crop_x}:{right_crop_y},"
                    f"scale={target_w}:{panel_h}[bottom];"
                    f"[top][bottom]vstack=inputs=2"
                )
            elif speaker_timeline:
                avg_x, avg_y, speaker = get_dominant_speaker_for_segment(
                    speaker_timeline, float(start), float(end)
                )
                crop_x, crop_y = get_crop_coordinates(
                    source_w, source_h, crop_w, crop_h, avg_x, avg_y
                )
                video_filter = build_crop_filter(crop_w, crop_h, crop_x, crop_y, target_w, target_h)
            else:
                crop_x, crop_y = get_crop_coordinates(
                    source_w, source_h, crop_w, crop_h, 0.5, 0.4
                )
                video_filter = build_crop_filter(crop_w, crop_h, crop_x, crop_y, target_w, target_h)

            cmd = [
                "ffmpeg",
                "-y",
                "-ss", format_time(float(start)),
                "-i", str(video_path),
                "-t", str(float(end) - float(start)),
                "-c:v", VIDEO_CODEC,
                "-c:a", AUDIO_CODEC,
                "-filter_complex" if split_layout else "-vf",
                video_filter,
                "-movflags", "+faststart",
                "-loglevel", "quiet",
                str(segment_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"Segment extraction failed: {result.stderr}\nCommand: {' '.join(cmd)}")

            if not segment_path.exists():
                raise Exception(f"Segment file was not created: {segment_path}")

            segment_files.append(segment_path)

        if len(segment_files) == 0:
            raise Exception("No segments could be extracted")

        if len(segment_files) == 1:
            # Only one segment, just copy it
            if output_path.exists():
                output_path.unlink()
            segment_files[0].rename(output_path)
            return output_path

        # Create concat file
        concat_file = temp_path / "concat.txt"
        with open(concat_file, "w") as f:
            for seg_file in segment_files:
                f.write(f"file '{seg_file.absolute()}'\n")

        # Re-encode all segments together (handles different crop positions)
        cmd = [
            "ffmpeg",
            "-y",
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
            raise Exception(f"Narrative concatenation failed: {result.stderr}\nStdout: {result.stdout}")

        return output_path


def get_xfade_offset(segment_files: list[Path], crossfade_duration: float) -> float:
    """Calculate crossfade offset positions."""
    offsets = []
    current_offset = 0

    for i, file in enumerate(segment_files[:-1]):
        # Get duration of this segment
        duration = get_duration(file)
        offsets.append(current_offset + duration - crossfade_duration)
        current_offset += duration

    return offsets[0] if offsets else 0


def get_duration(file_path: Path) -> float:
    """Get duration of a video file."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(file_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except:
        return 0.0


def format_time(seconds: float) -> str:
    """Format seconds to HH:MM:SS.mmm for FFmpeg."""
    seconds = float(seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def get_video_dimensions(video_path: Path) -> Optional[Tuple[int, int]]:
    """Get video dimensions."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(video_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip()
        if output:
            parts = output.split(",")
            if len(parts) >= 2:
                return (int(parts[0]), int(parts[1]))
    except:
        pass
    return None


def get_video_source_dimensions(video_path: Path) -> Tuple[int, int]:
    """Get source video dimensions using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(video_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip()
        if output:
            parts = output.split(",")
            if len(parts) >= 2:
                return (int(parts[0]), int(parts[1]))
    except:
        pass
    return (1920, 1080)  # Default fallback


def assemble_narrative_with_roles(
    video_path: Path,
    segments: list[dict],
    output_filename: str,
    clip_index: int,
    crossfade_duration: float = 0.3,
    speaker_timeline: Optional[List[Tuple[float, str, float, float]]] = None,
    aspect_ratio: Optional[str] = "9:16",
    output_dir: Optional[Path] = None,
    output_format: Optional[str] = None,
) -> Path:
    """Assemble segments with role ordering (hook->body->payoff) using xfade transitions.

    Uses FFmpeg xfade filter for smooth crossfade transitions between segments.
    Orders segments by role: hook first, then body, then payoff.
    """
    resolved_output_dir = output_dir or OUTPUT_DIR
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    resolved_format = output_format or DEFAULT_FORMAT
    output_path = resolved_output_dir / f"{output_filename}_clip_{clip_index}_smart.{resolved_format}"

    # Get target dimensions for aspect ratio
    target_w, target_h = {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
        "1:1": (1080, 1080),
        "4:5": (1080, 1350)
    }.get(aspect_ratio or "9:16", (1080, 1920))

    # Get source dimensions
    source_w, source_h = get_video_source_dimensions(video_path)

    # Order segments: hook -> body -> payoff (by segment_role)
    def role_order(seg):
        role = seg.get("segment_role", "body")
        if role == "hook":
            return 0
        elif role == "body":
            return 1
        elif role == "payoff":
            return 2
        return 1

    ordered_segments = sorted(segments, key=role_order)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Extract each segment with optional speaker tracking crop
        segment_files = []
        segment_durations = []

        for i, segment in enumerate(ordered_segments):
            start = parse_timestamp_value(segment.get("start", 0))
            end = parse_timestamp_value(segment.get("end", start))
            duration = end - start
            segment_durations.append(duration)

            segment_path = temp_path / f"segment_{i:03d}.{resolved_format}"

            # Calculate speaker position for this segment
            crop_x, crop_y = 0, 0
            video_filter = None

            crop_w, crop_h = get_crop_window_dimensions(source_w, source_h, aspect_ratio or "9:16")
            split_layout = None
            portrait_mode = (aspect_ratio or "9:16") in {"9:16", "4:5"}
            if speaker_timeline and portrait_mode:
                split_layout = detect_two_person_layout(speaker_timeline, float(start), float(end))

            if split_layout:
                left = split_layout["left"]
                right = split_layout["right"]
                panel_h = target_h // 2
                left_crop_w, left_crop_h, left_crop_x, left_crop_y = build_panel_crop(
                    source_w, source_h, target_w, panel_h, left["avg_x"], left["avg_y"]
                )
                right_crop_w, right_crop_h, right_crop_x, right_crop_y = build_panel_crop(
                    source_w, source_h, target_w, panel_h, right["avg_x"], right["avg_y"]
                )
                video_filter = (
                    f"[0:v]crop={left_crop_w}:{left_crop_h}:{left_crop_x}:{left_crop_y},"
                    f"scale={target_w}:{panel_h}[top];"
                    f"[0:v]crop={right_crop_w}:{right_crop_h}:{right_crop_x}:{right_crop_y},"
                    f"scale={target_w}:{panel_h}[bottom];"
                    f"[top][bottom]vstack=inputs=2"
                )
            elif speaker_timeline:
                avg_x, avg_y, speaker = get_dominant_speaker_for_segment(
                    speaker_timeline, float(start), float(end)
                )
                crop_x, crop_y = get_crop_coordinates(
                    source_w, source_h, crop_w, crop_h, avg_x, avg_y
                )
                video_filter = build_crop_filter(crop_w, crop_h, crop_x, crop_y, target_w, target_h)
            else:
                crop_x, crop_y = get_crop_coordinates(
                    source_w, source_h, crop_w, crop_h, 0.5, 0.4
                )
                video_filter = build_crop_filter(crop_w, crop_h, crop_x, crop_y, target_w, target_h)

            cmd = [
                "ffmpeg",
                "-y",
                "-ss", format_time(float(start)),
                "-i", str(video_path),
                "-t", str(float(end) - float(start)),
                "-c:v", VIDEO_CODEC,
                "-c:a", AUDIO_CODEC,
                "-filter_complex" if split_layout else "-vf",
                video_filter,
                "-movflags", "+faststart",
                "-loglevel", "quiet",
                str(segment_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"Segment extraction failed: {result.stderr}\nCommand: {' '.join(cmd)}")

            if not segment_path.exists():
                raise Exception(f"Segment file was not created: {segment_path}")

            segment_files.append(segment_path)

        if len(segment_files) == 0:
            raise Exception("No segments could be extracted")

        if len(segment_files) == 1:
            # Only one segment, just copy it
            if output_path.exists():
                output_path.unlink()
            segment_files[0].rename(output_path)
            return output_path

        # Build xfade filter chain
        # xfade formula: [v0][v1]xfade=transition=fade:duration=X:offset=T1[v01];
        # where T1 = duration_of_v0 - crossfade_duration
        # For N segments, we need N-1 crossfades

        xfade_inputs = []
        for i, seg_file in enumerate(segment_files):
            xfade_inputs.extend(["-i", str(seg_file)])

        # Build filter_complex for xfade
        # Chain: seg0 + seg1 -> xfade0 -> result01
        # result01 + seg2 -> xfade1 -> result02
        # etc.

        filter_parts = []
        prev_output = "[0:v]"

        for i in range(len(segment_files) - 1):
            # Calculate offset: when does the xfade start?
            # offset = sum of durations of previous segments - crossfade_duration
            offset = sum(segment_durations[:i+1]) - crossfade_duration

            # Current input index is i+1
            curr_input = f"[{i+1}:v]"

            if i == 0:
                # First crossfade
                filter_parts.append(
                    f"{prev_output}{curr_input}xfade=transition=fade:duration={crossfade_duration}:offset={offset:.3f}[v{i+1}]"
                )
            else:
                # Subsequent crossfades chain from previous output
                filter_parts.append(
                    f"[v{i}]{curr_input}xfade=transition=fade:duration={crossfade_duration}:offset={offset:.3f}[v{i+1}]"
                )

            prev_output = f"[v{i+1}]"

        # Final output maps to last vfade result
        last_v = f"[v{len(segment_files)-1}]"

        # Build complete filter_complex string
        filter_complex = ";".join(filter_parts) + f";{last_v}copy[outv]"

        # Audio: mix all audio tracks together with crossfade
        # For simplicity, use the first audio track (main speaker usually there)
        audio_filter = f"[0:a]"

        cmd = [
            "ffmpeg",
            "-y",
        ]
        cmd.extend(xfade_inputs)
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", f"{last_v}",
            "-map", "0:a",
            "-c:v", VIDEO_CODEC,
            "-c:a", AUDIO_CODEC,
            "-shortest",
            "-movflags", "+faststart",
            "-loglevel", "quiet",
            str(output_path)
        ])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            # Fallback to regular concat if xfade fails
            console.print("[dim]xfade failed, falling back to concat[/dim]")
            return concatenate_segments(
                video_path, segments, output_filename, clip_index,
                crossfade_duration=0.0,
                speaker_timeline=speaker_timeline,
                aspect_ratio=aspect_ratio,
                output_dir=output_dir,
                output_format=output_format,
            )

        return output_path


def concatenate_with_xfade(
    segment_files: list[Path],
    output_path: Path,
    crossfade_duration: float = 0.3,
) -> Path:
    """Concatenate multiple pre-extracted video segments using FFmpeg xfade.

    This is a lower-level function that takes already-extracted segment files
    and joins them with crossfade transitions.

    Args:
        segment_files: List of Path objects for extracted segments
        output_path: Final output path
        crossfade_duration: Crossfade transition duration in seconds

    Returns:
        Path to the concatenated output file
    """
    if len(segment_files) == 0:
        raise Exception("No segment files provided")
    if len(segment_files) == 1:
        # Just copy
        if output_path.exists():
            output_path.unlink()
        segment_files[0].rename(output_path)
        return output_path

    # Build ffmpeg command with xfade
    inputs = []
    for seg_file in segment_files:
        inputs.extend(["-i", str(seg_file)])

    # Calculate offsets for each crossfade
    # offset[i] = sum(durations[0:i+1]) - crossfade_duration
    durations = [get_duration(f) for f in segment_files]
    offsets = []
    cumulative = 0.0
    for i in range(len(durations) - 1):
        cumulative += durations[i]
        offsets.append(cumulative - crossfade_duration)

    # Build xfade chain
    filter_parts = []
    for i in range(len(segment_files) - 1):
        offset = offsets[i]
        if i == 0:
            filter_parts.append(
                f"[0:v][{i+1}:v]xfade=transition=fade:duration={crossfade_duration}:offset={offset:.3f}[v{i+1}]"
            )
        else:
            filter_parts.append(
                f"[v{i}][{i+1}:v]xfade=transition=fade:duration={crossfade_duration}:offset={offset:.3f}[v{i+1}]"
            )

    last_v = f"[v{len(segment_files)-1}]"
    filter_complex = ";".join(filter_parts) + f";{last_v}copy[outv]"

    cmd = [
        "ffmpeg", "-y",
    ] + inputs + [
        "-filter_complex", filter_complex,
        "-map", f"{last_v}",
        "-map", "0:a",
        "-c:v", VIDEO_CODEC,
        "-c:a", AUDIO_CODEC,
        "-shortest",
        "-movflags", "+faststart",
        "-loglevel", "quiet",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback: simple concat without xfade
        concat_file = segment_files[0].parent / "concat_temp.txt"
        with open(concat_file, "w") as f:
            for seg_file in segment_files:
                f.write(f"file '{seg_file.absolute()}'\n")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", VIDEO_CODEC, "-c:a", AUDIO_CODEC,
            "-movflags", "+faststart",
            "-loglevel", "quiet",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

    return output_path
