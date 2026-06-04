#!/usr/bin/env python3.11
"""
Kre8 Clips v2 — AI-Powered YouTube Video Clipper

Transform long-form YouTube videos into engaging short-form clips using AI.
Features: Speaker tracking, virality scoring, dynamic aspect ratios, styled captions.
"""

import argparse
import importlib.util
import subprocess
import sys
import signal
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

_shutdown_requested = False

def _handle_signal(signum, frame):
    global _shutdown_requested
    print("\n[yellow]Shutdown requested... finishing current operation.[/yellow]")
    _shutdown_requested = True

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

from rich.console import Console
from rich.table import Table

from config.settings import (
    OUTPUT_DIR, TEMP_DIR, DEEPGRAM_API_KEY, GEMINI_API_KEY,
    DEFAULT_ASPECT_RATIO, ENABLE_CAPTIONS, CAPTION_STYLE,
    ENABLE_SPEAKER_TRACKING, NARRATIVE_MODE, CROSSFADE_DURATION, TEST_MODE,
    ENABLE_TRACKING_DEBUG,
    ENABLE_BEAT_SYNC, BEAT_SNAP_TOLERANCE,
    ENABLE_WORD_LEVEL_CAPTIONS,
    ENABLE_RELIABILITY_SCORING, RELIABILITY_WEIGHTS,
    DEFAULT_PLATFORM, TITLE_MAX_CHARS, MAX_HASHTAGS,
    ADAPTIVE_CROSSFADE,
    ENABLE_QUALITY_DASHBOARD,
    ENABLE_CLIP_FADES, CLIP_FADE_IN_DURATION, CLIP_FADE_OUT_DURATION,
    CLIP_FADE_IN_CURVE, CLIP_FADE_OUT_CURVE,
)
from utils.progress import print_header, print_step, print_success, print_error, print_info, print_warning, set_progress_sink, console
from utils.validators import validate_youtube_url, sanitize_filename
from core.downloader import download_video, check_dependencies
from core.extractor import extract_audio
from core.transcriber import transcribe_audio, transcribe_audio_with_words, format_transcript_for_analysis
from core.analyzer import analyze_transcript, assemble_smart_narrative, compute_clip_reliability_score, optimize_title_for_platform, generate_hashtags, generate_quality_dashboard, call_gemini_api_cached
from core import cache as api_cache
from core.clipper import generate_clip, generate_clip_with_tracking, burn_captions, get_target_dimensions, get_clip_duration as get_clip_dur, generate_concatenated_clip, snap_boundaries_to_pauses, apply_clip_fades
from core.narrative import concatenate_segments
from core.speaker_tracker import SpeakerTracker
from core.caption_generator import CaptionGenerator, CaptionStyle
from core.boundary_snapper import SmartBoundarySnapper
from core.viral_model import ViralPredictor

console = Console()


def print_banner():
    """Print the Kre8 Clips banner."""
    banner = """
╔══════════════════════════════════════════════════════════╗
║                    CLIPGEN v2.0.0                        ║
║         AI-Powered Viral Clip Generator                   ║
║     Speaker Tracking • Virality • Dynamic Aspect          ║
╚══════════════════════════════════════════════════════════╝
    """
    console.print(banner[1:-1], style="bold violet")


def check_api_keys():
    """Check if required API keys are set."""
    missing = []
    if not DEEPGRAM_API_KEY:
        missing.append("DEEPGRAM_API_KEY")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if missing:
        print_error(f"Missing API keys: {', '.join(missing)}")
        console.print("\n[dim]Create a .env file based on .env.example:[/dim]")
        console.print("[dim]  cp .env.example .env[/dim]")
        console.print("[dim]Then add your API keys to .env[/dim]\n")
        return False
    return True


def check_python_modules(module_names: list[str]) -> list[str]:
    """Return a list of missing importable Python modules."""
    missing = []
    for module_name in module_names:
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    return missing


def ensure_speaker_tracking_ready() -> bool:
    """Validate optional dependencies required for smart speaker tracking."""
    missing_modules = check_python_modules(["numpy", "cv2", "mediapipe"])
    if missing_modules:
        print_error(f"Speaker tracking dependencies missing: {', '.join(missing_modules)}")
        console.print("[dim]Install with:[/dim] [bold]pip install -r requirements.txt[/bold]")
        return False

    asset_path = Path(__file__).parent / "assets" / "face_landmarker_v2_with_blendshapes.task"
    if not asset_path.exists():
        print_error(f"Missing MediaPipe face model: {asset_path}")
        return False

    return True


def run_regression_suite() -> bool:
    """Run the lightweight speaker-tracking regression tests."""
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print_success("Speaker tracking regression tests passed")
        return True

    print_error("Speaker tracking regression tests failed")
    if result.stdout.strip():
        console.print(result.stdout.strip())
    if result.stderr.strip():
        console.print(result.stderr.strip())
    return False


def run_doctor() -> int:
    """Run an environment and regression health check."""
    print_banner()
    print_step(1, 4, "Checking external dependencies")
    try:
        check_dependencies()
        print_success("yt-dlp and ffmpeg are installed")
    except Exception as exc:
        print_error(str(exc))
        return 1

    print_step(2, 4, "Checking API configuration")
    if not check_api_keys():
        return 1
    print_success("Required API keys are configured")

    print_step(3, 4, "Checking speaker tracking stack")
    tracking_ready = ensure_speaker_tracking_ready()
    if tracking_ready:
        print_success("Speaker tracking dependencies and model asset are ready")
    else:
        print_warning("Speaker tracking is not fully available")

    print_step(4, 4, "Running regression tests")
    regressions_ok = run_regression_suite()
    if regressions_ok:
        print_success("Doctor checks completed successfully")
        return 0
    return 1


def cleanup_temp_files(*paths):
    """Clean up temporary files."""
    for path in paths:
        if path and path.exists():
            try:
                path.unlink()
            except:
                pass


def ensure_output_dir(output_dir: Optional[Path]) -> Path:
    """Resolve and create the output directory."""
    resolved = Path(output_dir).expanduser() if output_dir else OUTPUT_DIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def trim_clip_segments(
    segments: list[dict],
    max_duration: int,
    *,
    snapper: Optional[SmartBoundarySnapper] = None,
) -> list[dict]:
    """Trim clip segments so total runtime does not exceed max_duration.

    When ``snapper`` is provided, the candidate end point of each segment is
    passed through ``SmartBoundarySnapper.snap_segment`` so that cuts land on
    natural boundaries (sentence ends, audio pauses, speaker changes) instead
    of being chopped mid-word. The budget cap is still enforced: a snapped end
    may be moved earlier but never past ``start + remaining``. If no snapper
    is supplied, the historical blunt-chop behavior is preserved.
    """
    if max_duration <= 0:
        return segments

    trimmed = []
    remaining = float(max_duration)
    for segment in segments:
        start = parse_timestamp_str(segment.get("start", "0"))
        end = parse_timestamp_str(segment.get("end", start))
        segment_duration = max(0.0, end - start)
        if segment_duration <= 0 or remaining <= 0:
            continue

        trimmed_end = min(end, start + remaining)

        if snapper is not None and trimmed_end > start:
            # Guard against the snapper collapsing the segment to nothing
            # when start and trimmed_end sit on the same anchor.
            desired_min = min(1.0, trimmed_end - start)
            try:
                snap = snapper.snap_segment(
                    start, trimmed_end, min_duration=desired_min,
                )
                snapped_end = float(snap.get("end", trimmed_end))
                if snapped_end > trimmed_end:
                    snapped_end = trimmed_end
                if snapped_end > start:
                    trimmed_end = snapped_end
            except Exception:
                # Snapper is best-effort; fall back to blunt trim.
                pass

        trimmed.append({
            "start": segment.get("start", "0"),
            "end": format_seconds_for_segments(trimmed_end),
        })
        remaining -= (trimmed_end - start)
        if remaining <= 0:
            break

    return trimmed


def calculate_total_segment_duration(segments: list[dict]) -> float:
    """Total duration across segments."""
    total = 0.0
    for segment in segments:
        start = parse_timestamp_str(segment.get("start", "0"))
        end = parse_timestamp_str(segment.get("end", start))
        total += max(0.0, end - start)
    return total


def clip_text_segments(
    clip: dict,
    transcript_segments: list[dict],
    *,
    padding: float = 0.5,
) -> list[dict]:
    """Return the transcript segments that fall within the clip's time range.

    The AI returns a clip with `segments` that only carry start/end/duration
    metadata (no `text`). The viral predictor needs the actual `text` to
    compute hook/payoff/emotion features, so we filter the full transcript
    to the clip's window. A small `padding` (default 0.5s) absorbs the
    boundary-snapping shifts that move the clip slightly off the original
    segment boundaries.
    """
    clip_segs = clip.get("segments") or []
    if not clip_segs or not transcript_segments:
        return []

    starts = []
    ends = []
    for seg in clip_segs:
        if not isinstance(seg, dict):
            continue
        s = parse_timestamp_str(seg.get("start", "0"))
        e = parse_timestamp_str(seg.get("end", "0"))
        if e > s:
            starts.append(s)
            ends.append(e)
    if not starts:
        return []

    clip_start = min(starts) - padding
    clip_end = max(ends) + padding

    matched = []
    for t in transcript_segments:
        if not isinstance(t, dict):
            continue
        text = (t.get("text") or "").strip()
        if not text:
            continue
        t_start = t.get("start", 0.0)
        t_end = t.get("end", t_start)
        try:
            t_start = float(t_start)
            t_end = float(t_end)
        except (TypeError, ValueError):
            continue
        # Segment overlaps the clip window
        if t_end >= clip_start and t_start <= clip_end:
            matched.append({"text": text, "speaker": t.get("speaker")})
    return matched


def expand_or_trim_clips(
    clips: list[dict],
    narrative_mode: bool,
    max_duration: int,
    *,
    snapper: Optional[SmartBoundarySnapper] = None,
) -> list[dict]:
    """Normalize clip list for the selected mode and duration budget.

    ``snapper`` is forwarded to :func:`trim_clip_segments` so multi-segment
    narrative clips are trimmed onto natural boundaries rather than being
    chopped mid-word. ``None`` preserves the original blunt behavior.
    """
    normalized = []
    for clip in clips:
        segments = clip.get("segments", [])
        if not segments:
            continue

        if not narrative_mode and len(segments) > 1:
            for seg_index, segment in enumerate(segments, 1):
                segment_duration = calculate_total_segment_duration([segment])
                if segment_duration <= 0:
                    continue
                normalized.append({
                    **clip,
                    "segments": [segment],
                    "duration_seconds": segment_duration,
                    "title": f"{clip.get('title', 'Clip')} Part {seg_index}",
                })
            continue

        trimmed_segments = trim_clip_segments(segments, max_duration, snapper=snapper)
        trimmed_duration = calculate_total_segment_duration(trimmed_segments)
        if trimmed_segments and trimmed_duration > 0:
            normalized.append({
                **clip,
                "segments": trimmed_segments,
                "duration_seconds": trimmed_duration,
            })

    return normalized


def format_seconds_for_segments(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for downstream segment consumers."""
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def run_clipgen(
    url: str,
    user_prompt: str,
    narrative_mode: bool = False,
    smart_narrative_mode: bool = False,
    verbose: bool = False,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    enable_speaker_tracking: bool = ENABLE_SPEAKER_TRACKING,
    enable_captions: bool = ENABLE_CAPTIONS,
    caption_style: str = CAPTION_STYLE,
    min_clip_duration: int = 30,
    max_clip_duration: int = 120,
    num_clips: int = 5,
    output_format: str = "mp4",
    output_dir: Optional[Path] = None,
    job_output_dir: Optional[Path] = None,
):
    """Main clipping workflow with all features enabled."""
    total_steps = 7
    video_path = None
    audio_path = None

    try:
        tracker = None
        resolved_output_dir = Path(job_output_dir).expanduser() if job_output_dir else (Path(output_dir).expanduser() if output_dir else OUTPUT_DIR)
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        job_download_dir = Path(job_output_dir).expanduser() if job_output_dir else TEMP_DIR
        job_download_dir.mkdir(parents=True, exist_ok=True)

        if job_output_dir:
            job_id_for_save = Path(job_output_dir).name
            if not job_id_for_save:
                job_id_for_save = str(uuid.uuid4())[:8]
        else:
            job_id_for_save = str(uuid.uuid4())[:8]

        # Set up structured progress sidecar: each print_step emits a JSON
        # line to .jobs/{job_id}.progress.jsonl. The Next.js API route reads
        # the last line as the source of truth for step/progress/step_detail
        # instead of regex-parsing Rich console output.
        progress_sink_path = Path(".jobs") / f"{job_id_for_save}.progress.jsonl"
        try:
            progress_sink_path.parent.mkdir(parents=True, exist_ok=True)
            progress_sink_path.unlink(missing_ok=True)
        except OSError:
            pass
        set_progress_sink(str(progress_sink_path))

        # Step 1: Validate and check
        print_step(1, total_steps, "Validating URL and dependencies")
        if not validate_youtube_url(url):
            print_error("Invalid YouTube URL format")
            console.print("[dim]Supported formats:[/dim]")
            console.print("[dim]  - https://youtube.com/watch?v=...[/dim]")
            console.print("[dim]  - https://youtu.be/...[/dim]")
            console.print("[dim]  - https://youtube.com/shorts/...[/dim]")
            return False

        check_dependencies()

        if not check_api_keys():
            return False

        print_success("All checks passed")

        # Step 2: Download video
        if _shutdown_requested:
            print_warning("Shutdown requested, stopping")
            return False
        print_step(2, total_steps, "Downloading video")
        video_path = download_video(url, output_dir=job_download_dir)
        video_title = video_path.stem
        print_success(f"Downloaded: {video_title}")

        # Step 3: Extract audio
        if _shutdown_requested:
            print_warning("Shutdown requested, stopping")
            return False
        print_step(3, total_steps, "Extracting audio")
        max_audio = 180 if TEST_MODE else None  # 3 min max in test mode
        audio_path = extract_audio(video_path, max_duration=max_audio)
        print_success(f"Audio extracted: {audio_path.name}")

        # Step 4: Transcribe with speaker diarization
        if _shutdown_requested:
            print_warning("Shutdown requested, stopping")
            return False
        print_step(4, total_steps, "Transcribing with speaker detection")

        # Word-level transcription for precision captions
        if ENABLE_WORD_LEVEL_CAPTIONS:
            segments, words = transcribe_audio_with_words(audio_path)
            transcript = format_transcript_for_analysis(segments)
            print_success(f"Transcribed {len(segments)} segments with word-level timing")
        else:
            segments = transcribe_audio(audio_path)
            transcript = format_transcript_for_analysis(segments)
            print_success(f"Transcribed {len(segments)} segments")
            words = None

        # Count unique speakers
        speakers = set(s.get("speaker", "UNKNOWN") for s in segments if s.get("speaker"))
        if speakers:
            print_info(f"Detected {len(speakers)} speakers: {', '.join(sorted(speakers))}")
        else:
            print_warning("No speaker labels detected (video may be single-speaker or audio quality issues)")

        portrait_output = aspect_ratio in {"9:16", "4:5"}
        if portrait_output and len(speakers) >= 2 and not enable_speaker_tracking:
            enable_speaker_tracking = True
            print_info("Auto-enabled speaker tracking for multi-speaker portrait output")

        if enable_speaker_tracking and not ensure_speaker_tracking_ready():
            return False

        # Beat-synchronized cutting: find natural pause points for smart boundary snapping
        beat_pauses = []
        if ENABLE_BEAT_SYNC:
            from core.virality import ViralityAnalyzer
            try:
                va = ViralityAnalyzer()
                beat_pauses = va.find_beat_pauses(str(audio_path))
                print_info(f"Beat sync: found {len(beat_pauses)} natural cut points")
            except Exception as e:
                print_warning(f"Beat sync analysis skipped: {e}")

        viral_predictor = ViralPredictor()
        boundary_snapper = SmartBoundarySnapper(
            beat_pauses=beat_pauses,
            transcript_segments=segments,
        )

        # Step 5: Analyze with AI (narrative mode)
        if _shutdown_requested:
            print_warning("Shutdown requested, stopping")
            return False
        print_step(5, total_steps, "Analyzing for narrative clips")
        from core.analyzer import load_system_prompt, parse_clip_response
        gemini_fingerprint = api_cache.make_fingerprint([
            url,
            user_prompt,
            transcript,
            aspect_ratio,
            min_clip_duration,
            max_clip_duration,
            num_clips,
        ])
        raw_response, _gemini_cache_hit = call_gemini_api_cached(
            load_system_prompt(viral=True),
            f"TASK: {user_prompt}\n\nTRANSCRIPT:\n{transcript}",
            gemini_fingerprint,
        )
        clips = parse_clip_response(raw_response)

        try:
            from core.job_data_manager import save_job_data, update_job_clips
            from core.job_data_schema import (
                create_job_data, TranscriptSegment, WordTimestamp, GeneratedClip,
                ClipSegment, ContextReference, AIGramSegment, AIGramSegmentScores,
                BrollSuggestion
            )

            job_data = create_job_data(job_id_for_save, url, video_title)

            if segments:
                job_data.transcript = [
                    TranscriptSegment(
                        start=s.get("start", 0.0),
                        end=s.get("end", 0.0),
                        text=s.get("text", ""),
                        speaker=s.get("speaker")
                    )
                    for s in segments
                ]
            if words:
                job_data.word_timestamps = [
                    WordTimestamp(
                        word=w.get("word", ""),
                        start=w.get("start", 0.0),
                        end=w.get("end", 0.0),
                        speaker=w.get("speaker"),
                        confidence=w.get("confidence", 1.0)
                    )
                    for w in words
                ]
            job_data.video_duration = float(get_clip_dur(video_path)) if video_path.exists() else 0.0
            job_data.video_path = str(video_path)
            job_data.audio_path = str(audio_path)
            job_data.raw_ai_response = raw_response if 'raw_response' in dir() else ""

            beat_timestamps = beat_pauses if 'beat_pauses' in dir() else []
            all_scores = []

            ai_segments = []
            for clip in clips:
                for seg in clip.get("segments", []):
                    start = seg.get("start_seconds", seg.get("start", 0))
                    end = seg.get("end_seconds", seg.get("end", 0))

                    hook = clip.get("hook_score", 5)
                    tone = clip.get("emotional_tone", "neutral").lower()
                    tone_scores = {
                        "controversial": 8.5, "inspiring": 8.0, "surprising": 8.5,
                        "funny": 7.5, "educational": 6.5, "motivational": 8.0, "neutral": 5.0
                    }
                    emotion = tone_scores.get(tone, 5.0)

                    reason_lower = clip.get("reason", "").lower()
                    curiosity_indicators = ["surprising", "secret", "mistake", "truth", "problem", "imagine", "what if"]
                    curiosity = 5.0
                    for indicator in curiosity_indicators:
                        if indicator in reason_lower:
                            curiosity += 1.0
                    curiosity = min(10, curiosity)

                    shareability = hook
                    clarity = 7.0
                    authority = 6.0

                    all_scores.append(hook)
                    all_scores.append(emotion)

                    hook_phrases = ["you know", "here's the thing", "most important", "the secret", "the problem", "imagine", "what if", "here's why", "first", "actually", "honestly", "trust me", "believe me"]
                    text_lower = clip.get("title", "").lower() + " " + clip.get("reason", "").lower()
                    viral_indicators = [phrase for phrase in hook_phrases if phrase in text_lower]

                    scores = AIGramSegmentScores(
                        hook_score=hook,
                        emotion_score=emotion,
                        curiosity_score=curiosity,
                        authority_score=authority,
                        story_score=clip.get("story_score", 7.0) if "story_score" in clip else 7.0,
                        shareability_score=shareability,
                        clarity_score=clarity,
                        platform_match={
                            "tiktok": hook,
                            "linkedin": min(10, hook * 0.8),
                            "youtube_shorts": min(10, hook * 0.9)
                        },
                        emotional_tone=clip.get("emotional_tone", "neutral"),
                        topic=clip.get("topic", ""),
                        main_speaker=clip.get("main_speaker", "UNKNOWN"),
                        contains_cta=False,
                        contains_hook_phrase=any(phrase in text_lower for phrase in hook_phrases),
                        viral_indicators=viral_indicators
                    )

                    ai_segments.append(AIGramSegment(
                        start=start,
                        end=end,
                        scores=scores,
                        beat_synced=seg.get("_snapped", False)
                    ))

            emotional_density = []
            for i, score in enumerate(all_scores):
                time = i * 5.0
                label = "spike" if score >= 8 else "medium" if score >= 6 else "low"
                emotional_density.append({"time": time, "score": score / 10.0, "type": label})

            job_data.ai_analysis = {
                "segments": [
                    {
                        "start": s.start,
                        "end": s.end,
                        "hook_score": s.scores.hook_score,
                        "emotion_score": s.scores.emotion_score,
                        "curiosity_score": s.scores.curiosity_score,
                        "authority_score": s.scores.authority_score,
                        "story_score": s.scores.story_score,
                        "shareability_score": s.scores.shareability_score,
                        "clarity_score": s.scores.clarity_score,
                        "platform_match": s.scores.platform_match,
                        "emotional_tone": s.scores.emotional_tone,
                        "topic": s.scores.topic,
                        "main_speaker": s.scores.main_speaker,
                        "contains_cta": s.scores.contains_cta,
                        "contains_hook_phrase": s.scores.contains_hook_phrase,
                        "viral_indicators": s.scores.viral_indicators
                    }
                    for s in ai_segments
                ],
                "beat_timestamps": beat_timestamps,
                "emotional_density": emotional_density
            }

            clips_to_process = clips[:num_clips] if num_clips > 0 else clips
            generated_clips = []
            for i, clip in enumerate(clips_to_process):
                clip_segs = []

                # Boundary snap preview: compute start/end confidence for the
                # whole clip from its narrative segments, so we can persist it
                # to the GeneratedClip even before the render loop.
                boundary_confidence = 0.0
                boundary_start_reason = ""
                boundary_end_reason = ""
                try:
                    seg_times = []
                    for seg in clip.get("segments", []):
                        if not isinstance(seg, dict):
                            continue
                        s = parse_timestamp_str(seg.get("start", "0"))
                        e = parse_timestamp_str(seg.get("end", "0"))
                        seg_times.append((s, e))
                    if seg_times:
                        clip_s = seg_times[0][0]
                        clip_e = seg_times[-1][1]
                        snap = boundary_snapper.snap_segment(
                            clip_s, clip_e,
                            min_duration=min_clip_duration * 0.5,
                        )
                        boundary_confidence = snap["confidence"]
                        boundary_start_reason = snap["start_reason"]
                        boundary_end_reason = snap["end_reason"]
                except Exception:
                    pass

                for seg in clip.get("segments", []):
                    if isinstance(seg, dict):
                        clip_segs.append(ClipSegment(
                            start=seg.get("start", "0"),
                            end=seg.get("end", "0"),
                            start_seconds=seg.get("start_seconds", 0.0),
                            end_seconds=seg.get("end_seconds", 0.0),
                            duration=seg.get("duration", 0.0),
                            segment_role=seg.get("segment_role", "body"),
                            viral_potential=seg.get("viral_potential", 5),
                            opening_strength=seg.get("opening_strength", 5),
                            closing_strength=seg.get("closing_strength", 5)
                        ))

                context_ref = clip.get("context_needed")
                context_needed = None
                if context_ref:
                    context_needed = ContextReference(
                        start=context_ref.get("start", "0"),
                        end=context_ref.get("end", "0"),
                        reason=context_ref.get("reason", "")
                    )

                viral_pred = None
                try:
                    duration = float(clip.get("duration_seconds") or 0.0)
                    # Use the clip's own time range to slice the transcript,
                    # not the full transcript — otherwise the hook/payoff
                    # features get computed from the wrong segment.
                    clip_segments = clip_text_segments(clip, segments)
                    if not clip_segments:
                        clip_segments = [{"text": clip.get("title", "")}]
                    viral_pred = viral_predictor.predict(
                        segments=clip_segments,
                        duration=duration,
                        clip_id=f"{job_id_for_save}_clip_{i+1}",
                        job_id=job_id_for_save,
                        video_id=url,
                        metadata={"title": clip.get("title", "")},
                    )
                except Exception as pred_err:
                    import traceback
                    print_warning(
                        f"Viral prediction failed for clip {i+1} "
                        f"({clip.get('title', '?')[:40]}): {pred_err}"
                    )
                    print_warning(traceback.format_exc())

                generated_clips.append(GeneratedClip(
                    id=f"clip_{i+1}",
                    title=clip.get("title", f"Clip {i+1}"),
                    original_title=clip.get("original_title", ""),
                    priority=clip.get("priority", 5),
                    hook_score=clip.get("hook_score", 5.0),
                    emotional_tone=clip.get("emotional_tone", "neutral"),
                    main_speaker=clip.get("main_speaker", "UNKNOWN"),
                    topic=clip.get("topic", ""),
                    reason=clip.get("reason", ""),
                    quote_potential=clip.get("quote_potential", ""),
                    hashtags=clip.get("hashtags", []),
                    segments=clip_segs,
                    reliability_score=clip.get("reliability_score"),
                    context_needed=context_needed,
                    output_path=clip.get("path", ""),
                    duration_seconds=clip.get("duration_seconds", clip.get("duration", 0.0)),
                    viral_share_prob=viral_pred.share if viral_pred else 0.0,
                    viral_save_prob=viral_pred.save if viral_pred else 0.0,
                    viral_comment_prob=viral_pred.comment if viral_pred else 0.0,
                    viral_composite=viral_pred.composite if viral_pred else 0.0,
                    viral_model_version=viral_pred.model_version if viral_pred else "",
                    viral_features=viral_pred.features.to_dict() if viral_pred else {},
                    boundary_confidence=boundary_confidence,
                    boundary_start_reason=boundary_start_reason,
                    boundary_end_reason=boundary_end_reason,
                ))

            job_data.generated_clips = generated_clips
            job_data.completed_at = datetime.utcnow().isoformat() + "Z"

            if segments:
                broll_keywords = {
                    "money": ["money_stock_1.mp4", "money_stock_2.mp4"],
                    "startup": ["startup_stock_1.mp4"],
                    "success": ["success_stock_1.mp4"],
                    "failure": ["failure_stock_1.mp4"],
                    "team": ["team_stock_1.mp4"],
                    "meeting": ["meeting_stock_1.mp4"],
                    "city": ["city_stock_1.mp4"],
                    "growth": ["growth_stock_1.mp4"],
                    "technology": ["tech_stock_1.mp4"],
                    "data": ["data_stock_1.mp4"],
                }

                suggestions = []
                for seg in segments:
                    text = seg.get("text", "").lower()
                    for keyword, stock_files in broll_keywords.items():
                        if keyword in text:
                            suggestions.append(BrollSuggestion(
                                time=seg.get("start", 0.0),
                                keyword=keyword,
                                suggestions=stock_files,
                                confidence=0.7
                            ))

                job_data.broll_suggestions = suggestions

            save_job_data(job_data)
        except Exception as save_err:
            import traceback
            print_error(f"SAVE JOB DATA FAILED: {save_err}")
            print_error(traceback.format_exc())
            raise save_err

        if not clips:
            print_warning("No clips identified by AI. Try a different prompt.")
            return False

        # Sort clips by priority, then by duration
        clips.sort(key=lambda x: (x.get("priority", 0), x.get("duration_seconds", 0)), reverse=True)

        # Smart narrative assembly: select best hook/body/payoff from different clips
        if smart_narrative_mode and len(clips) >= 2:
            console.print(f"  [dim]Smart narrative: assembling optimal clip from {len(clips)} candidates[/dim]")
            assembled = assemble_smart_narrative(
                clips,
                min_duration=min_clip_duration,
                max_duration=max_clip_duration,
                main_speaker=None,
            )
            if assembled and assembled.get("assembled"):
                # Replace clips with the single assembled narrative clip
                clips = [assembled]
                console.print(f"  [dim]Smart narrative assembled: {assembled.get('title', 'Assembled Clip')}[/dim]")
            else:
                console.print(f"  [dim]Smart narrative assembly failed, using standard clips[/dim]")

        # Limit to top 2 clips in test mode
        if TEST_MODE:
            clips = clips[:2]
            console.print(f"[dim]TEST_MODE: Limiting to top 2 clips[/dim]")

        # Limit to requested number of clips
        if num_clips > 0:
            clips = clips[:num_clips]
            console.print(f"[dim]Limiting to top {num_clips} clips[/dim]")

        clips = expand_or_trim_clips(
            clips,
            narrative_mode=narrative_mode,
            max_duration=max_clip_duration,
            snapper=boundary_snapper,
        )

        # Filter by minimum duration
        original_count = len(clips)
        clips = [c for c in clips if c.get("duration_seconds", 0) >= min_clip_duration]
        if len(clips) < original_count:
            console.print(f"[dim]Filtered {original_count - len(clips)} clips under {min_clip_duration}s minimum[/dim]")

        print_success(f"AI identified {len(clips)} narrative clips")

        if verbose:
            console.print("\n[bold]Clip Analysis:[/bold]")
            for i, clip in enumerate(clips[:5]):
                duration = clip.get('duration_seconds', 0)
                hook_score = clip.get('hook_score', 5)
                emotional = clip.get('emotional_tone', 'neutral')
                main_speaker = clip.get('main_speaker', 'UNKNOWN')
                console.print(f"  [dim]{i+1}.[/dim] {clip.get('title', 'Untitled')[:50]}")
                console.print(f"      Duration: {duration:.0f}s | Hook: {hook_score}/10 | Tone: {emotional} | Speaker: {main_speaker}")

        # Step 6: Generate clips
        print_step(6, total_steps, "Generating clips")

        output_clips = []
        safe_filename = sanitize_filename(video_title)

        target_w, target_h = get_target_dimensions(aspect_ratio)
        console.print(f"  [dim]Output:[/dim] {output_format} • {aspect_ratio} ({target_w}x{target_h})")

        # Initialize speaker tracker if enabled
        speaker_timeline = None
        if enable_speaker_tracking:
            console.print(f"  [dim]Speaker tracking:[/dim] enabled")
            tracking_interval = 0.25 if portrait_output and len(speakers) >= 2 else 0.5
            tracker = SpeakerTracker(
                smoothing_window=0.3,
                face_detection_interval=tracking_interval,
            )
            console.print(f"  [dim]Tracking sample interval:[/dim] {tracking_interval:.2f}s")
            clip_segments = []
            for clip in clips:
                for seg in clip.get("segments", []):
                    clip_segments.append({
                        "start": parse_timestamp_str(seg.get("start", "0")),
                        "end": parse_timestamp_str(seg.get("end", "0"))
                    })
            speaker_timeline = tracker.generate_position_track(
                video_path, segments, clip_segments=clip_segments
            )
            console.print(f"  [dim]Generated {len(speaker_timeline)} position samples[/dim]")
            if ENABLE_TRACKING_DEBUG:
                debug_path = resolved_output_dir / f"{safe_filename}_tracking_debug.json"
                tracker.export_debug_snapshot(debug_path, diarization_segments=segments)
                console.print(f"  [dim]Tracking debug:[/dim] {debug_path.name}")

        for i, clip in enumerate(clips):
            if _shutdown_requested:
                print_warning("Shutdown requested, stopping clip generation")
                break

            clip_title = clip.get("title", f"clip_{i+1}")
            segments_data = clip.get("segments", [])

            # Smart boundary snapping: combines audio pauses + sentence ends + speaker switches
            smart_boundary_log = []
            try:
                snapped_segments = []
                for seg in segments_data:
                    s = parse_timestamp_str(seg.get("start", "0"))
                    e = parse_timestamp_str(seg.get("end", "0"))
                    snap = boundary_snapper.snap_segment(s, e, min_duration=min_clip_duration * 0.5)
                    new_seg = dict(seg)
                    new_seg["start_seconds"] = snap["start"]
                    new_seg["end_seconds"] = snap["end"]
                    new_seg["_snapped"] = snap["start_snapped"] or snap["end_snapped"]
                    new_seg["_boundary_confidence"] = snap["confidence"]
                    new_seg["_start_reason"] = snap["start_reason"]
                    new_seg["_end_reason"] = snap["end_reason"]
                    snapped_segments.append(new_seg)
                    smart_boundary_log.append(
                        f"{s:.1f}→{e:.1f} snapped to {snap['start']:.1f}→{snap['end']:.1f} ({snap['start_reason']} | {snap['end_reason']})"
                    )
                segments_data = snapped_segments
                if any(seg.get("_snapped", False) for seg in segments_data):
                    console.print(f"      [dim]Smart boundaries:[/dim]")
                    for log in smart_boundary_log:
                        console.print(f"        [dim]{log}[/dim]")
            except Exception as snap_err:
                print_warning(f"Smart boundary snapping failed: {snap_err}")

            clip_duration = clip.get("duration_seconds", 0)

            # Cap at max duration
            if clip_duration > max_clip_duration:
                console.print(f"  [dim]Clip {i+1}/{len(clips)}:[/dim] {clip_title[:40]} [CAPPED from {clip_duration:.0f}s]")
            else:
                console.print(f"  [dim]Clip {i+1}/{len(clips)}:[/dim] {clip_title[:40]} [{clip_duration:.0f}s]")

            try:
                if len(segments_data) > 1:
                    # Non-contiguous segments - narrative mode
                    console.print(f"      [dim]Narrative clip with {len(segments_data)} segments[/dim]")
                    output_path = generate_concatenated_clip(
                        video_path=video_path,
                        segments=segments_data,
                        output_filename=safe_filename,
                        clip_index=i + 1,
                        crossfade_duration=CROSSFADE_DURATION,
                        speaker_timeline=speaker_timeline if enable_speaker_tracking else None,
                        aspect_ratio=aspect_ratio,
                        output_dir=resolved_output_dir,
                        output_format=output_format,
                        smart_assembly=smart_narrative_mode,
                    )
                elif len(segments_data) == 1:
                    # Single continuous segment
                    seg = segments_data[0]
                    start = parse_timestamp_str(seg.get("start", "0"))
                    end = parse_timestamp_str(seg.get("end", "0"))

                    if speaker_timeline:
                        output_path = generate_clip_with_tracking(
                            video_path, start, end, safe_filename, i + 1,
                            speaker_timeline=speaker_timeline,
                            aspect_ratio=aspect_ratio,
                            output_dir=resolved_output_dir,
                            output_format=output_format,
                        )
                    else:
                        output_path = generate_clip(
                            video_path, start, end, safe_filename, i + 1,
                            aspect_ratio=aspect_ratio,
                            output_dir=resolved_output_dir,
                            output_format=output_format,
                        )
                else:
                    continue

                # Title optimization for platform
                optimized_title = optimize_title_for_platform(
                    clip_title,
                    platform=DEFAULT_PLATFORM,
                    emotional_tone=clip.get("emotional_tone", "neutral"),
                )
                hashtags = generate_hashtags(
                    optimized_title,
                    topic=clip.get("topic", ""),
                    emotional_tone=clip.get("emotional_tone", "neutral"),
                    max_count=MAX_HASHTAGS,
                )

                # Add captions if enabled
                if enable_captions and output_path.exists():
                    try:
                        srt_path = generate_clip_srt(
                            segments,
                            segments_data,
                            TEMP_DIR / f"caption_{i}.srt",
                        )
                        if srt_path:
                            output_path = burn_captions(output_path, srt_path, caption_style=caption_style)
                    except Exception as e:
                        print_warning(f"Caption error: {str(e)}")

                # Apply audio + video fade-in/out for a smoother start and end
                if ENABLE_CLIP_FADES and output_path and output_path.exists():
                    try:
                        apply_clip_fades(
                            output_path,
                            fade_in_duration=CLIP_FADE_IN_DURATION,
                            fade_out_duration=CLIP_FADE_OUT_DURATION,
                            fade_in_curve=CLIP_FADE_IN_CURVE,
                            fade_out_curve=CLIP_FADE_OUT_CURVE,
                        )
                    except Exception as fade_err:
                        print_warning(f"Clip fade skipped: {fade_err}")

                # Get actual clip duration
                actual_duration = get_clip_dur(output_path)

                # If ffprobe can't read the file (stub/corrupt render), fall back
                # to the planned segment span. This used to silently emit 0.0.
                if not actual_duration or actual_duration <= 0:
                    actual_duration = recompute_duration_from_segments(segments_data)

                # Post-render size check — catches the silent-render-failure
                # pattern (262-byte stub MP4) where ffmpeg exits 0 without
                # writing a real file. Treat as a hard render failure so the
                # caller sees the error rather than a "success" with an empty
                # video. Threshold: 50 KB (see MIN_RENDER_BYTES).
                render_error_msg = ""
                if not is_render_healthy(output_path):
                    size = output_path.stat().st_size if output_path.exists() else 0
                    render_error_msg = (
                        f"Rendered file is {size} bytes (suspicious; possible "
                        "ffmpeg crash with empty output). Re-encode the clip."
                    )
                    print_warning(f"Clip {i+1} render looks broken: {render_error_msg}")
                    output_clips.append({
                        "id": f"clip_{i+1}",
                        "path": str(output_path) if output_path.exists() else "",
                        "title": optimized_title,
                        "original_title": clip_title,
                        "priority": clip.get("priority", 0),
                        "hook_score": clip.get("hook_score", 5),
                        "emotional_tone": clip.get("emotional_tone", "neutral"),
                        "duration": 0.0,
                        "output_format": output_format,
                        "main_speaker": clip.get("main_speaker", "UNKNOWN"),
                        "reason": clip.get("reason", ""),
                        "hashtags": hashtags,
                        "segments": segments_data,
                        "render_error": render_error_msg,
                        "render_traceback": "",
                    })
                    continue

                output_clips.append({
                    "id": f"clip_{i+1}",
                    "path": str(output_path),
                    "title": optimized_title,
                    "original_title": clip_title,
                    "priority": clip.get("priority", 0),
                    "hook_score": clip.get("hook_score", 5),
                    "emotional_tone": clip.get("emotional_tone", "neutral"),
                    "duration": actual_duration,
                    "output_format": output_format,
                    "main_speaker": clip.get("main_speaker", "UNKNOWN"),
                    "reason": clip.get("reason", ""),
                    "hashtags": hashtags,
                    "segments": segments_data,
                })

                # Reliability scoring (if speaker tracking enabled)
                if enable_speaker_tracking and ENABLE_RELIABILITY_SCORING:
                    try:
                        clip_start = parse_timestamp_str(segments_data[0].get("start", "0"))
                        clip_end = parse_timestamp_str(segments_data[-1].get("end", "0"))
                        signals = tracker.get_clip_reliability_signals(clip_start, clip_end)
                        score = compute_clip_reliability_score(signals, RELIABILITY_WEIGHTS)
                        output_clips[-1]["reliability_score"] = score
                        output_clips[-1]["reliability_signals"] = signals
                        console.print(f"      [dim]Reliability: {score:.0%}[/dim]")
                    except Exception as e:
                        print_warning(f"Reliability scoring skipped: {e}")

            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                print_warning(f"Failed to generate clip {i+1}: {str(e)}")
                console.print(f"[dim]{tb}[/dim]")
                output_clips.append({
                    "id": f"clip_{i+1}",
                    "path": "",
                    "title": clip.get("title", f"Clip {i+1}"),
                    "original_title": clip.get("original_title", ""),
                    "priority": clip.get("priority", 0),
                    "hook_score": clip.get("hook_score", 0.0),
                    "emotional_tone": clip.get("emotional_tone", "neutral"),
                    "main_speaker": clip.get("main_speaker", "UNKNOWN"),
                    "topic": clip.get("topic", ""),
                    "reason": clip.get("reason", ""),
                    "quote_potential": clip.get("quote_potential", ""),
                    "hashtags": clip.get("hashtags", []),
                    "duration_seconds": clip.get("duration_seconds", clip.get("duration", 0.0)),
                    "render_error": str(e),
                    "render_traceback": tb,
                })
                continue

        # Cleanup
        cleanup_temp_files(video_path, audio_path)

        # Persist actual clip paths to job data
        if output_clips:
            update_job_clips(job_id_for_save, output_clips, segments)

        # Final output
        console.print("\n")
        if output_clips:
            # Emit a final step-7 "Complete" progress entry to the JSONL
            # sidecar. Without this, the Next.js SSE consumer would hang
            # on the last step ("Generating Clips") until the timeout —
            # the sidecar's last entry was step 6 with no terminal line.
            print_step(7, 7, "Complete")
            print_success(f"Generated {len(output_clips)} clips successfully!")

            # Display results table
            table = Table(title="Generated Clips", show_header=True, header_style="bold violet")
            table.add_column("#", style="dim", width=3)
            table.add_column("Title", style="bold")
            table.add_column("Priority", justify="center")
            table.add_column("Hook", justify="center")
            table.add_column("Reliability", justify="center")
            table.add_column("Duration", justify="right")
            table.add_column("Format", justify="center")

            for i, clip in enumerate(output_clips, 1):
                reliability = clip.get("reliability_score", None)
                reliability_str = f"{reliability:.0%}" if reliability is not None else "-"
                table.add_row(
                    str(i),
                    clip["title"][:40],
                    str(clip["priority"]),
                    f"{clip.get('hook_score', 5)}/10",
                    reliability_str,
                    f"{clip.get('duration', 0):.0f}s",
                    clip.get("output_format", output_format),
                )

            console.print(table)
            console.print(f"\n[dim]Output directory:[/dim] {resolved_output_dir}")

            # Quality dashboard
            if ENABLE_QUALITY_DASHBOARD and output_clips:
                try:
                    quality_report = generate_quality_dashboard(output_clips)
                    if quality_report:
                        console.print("\n[bold]Quality Report:[/bold]")
                        for item in quality_report:
                            clip_idx = item["clip_index"]
                            scores = item["scores"]
                            recommendations = item["recommendations"]
                            clip_obj = output_clips[clip_idx]
                            console.print(f"\n  [bold]Clip {clip_idx + 1}:[/bold] {clip_obj['title'][:50]}")
                            console.print(f"    Face Stability: {scores.get('face_stability', 'N/A')} | "
                                        f"Audio Quality: {scores.get('audio_quality', 'N/A')} | "
                                        f"Hook Score: {scores.get('hook_score', 'N/A')}")
                            for rec in recommendations:
                                console.print(f"    • {rec}")
                except Exception as e:
                    print_warning(f"Quality dashboard skipped: {e}")
        else:
            print_error("No clips were generated")
            return False

        return True

    except Exception as e:
        print_error(f"Error: {str(e)}")
        cleanup_temp_files(video_path, audio_path)
        return False
    finally:
        set_progress_sink(None)


def generate_clip_srt(all_segments, clip_segments_data, output_path):
    """Generate SRT file for a rendered clip, including narrative concatenations."""
    remapped_segments = []
    local_offset = 0.0

    for clip_segment in clip_segments_data:
        clip_start = parse_timestamp_str(clip_segment.get("start", "0"))
        clip_end = parse_timestamp_str(clip_segment.get("end", "0"))
        if clip_end <= clip_start:
            continue

        overlapping_segments = [
            segment for segment in all_segments
            if segment.get("start", 0) < clip_end and segment.get("end", 0) > clip_start
        ]

        for segment in overlapping_segments:
            seg_start = max(float(segment.get("start", 0)), clip_start)
            seg_end = min(float(segment.get("end", seg_start)), clip_end)
            if seg_end <= seg_start:
                continue

            remapped_segments.append({
                "start": local_offset + (seg_start - clip_start),
                "end": local_offset + (seg_end - clip_start),
                "text": segment.get("text", ""),
                "speaker": segment.get("speaker"),
            })

        local_offset += (clip_end - clip_start)

    if not remapped_segments:
        return None

    gen = CaptionGenerator()
    srt_content = gen.generate_srt(remapped_segments, include_speaker=True)
    gen.save_srt(srt_content, output_path)
    return output_path


# Minimum rendered file size (bytes) below which we treat a render as broken.
# 50 KB is a conservative lower bound for a 5-second portrait clip encoded at
# 8 Mbps. Stub files (the 2026-06-04 silent-failure pattern: ffmpeg exits 0
# without writing real content) are typically 100-500 bytes; legitimate
# clips are 100s of KB minimum. Tune if a platform produces smaller valid
# output (e.g. very low bitrate).
MIN_RENDER_BYTES = 50_000


def is_render_healthy(path, min_bytes: int = MIN_RENDER_BYTES) -> bool:
    """True iff `path` exists and is at least `min_bytes` bytes.

    A ffmpeg crash that exits 0 without writing real content produces a
    100-500 byte stub MP4. This is the post-render size check that catches
    the silent-failure pattern from 2026-06-04.
    """
    if path is None:
        return False
    try:
        return path.exists() and path.stat().st_size >= min_bytes
    except OSError:
        return False


def recompute_duration_from_segments(segments_data, fallback: float = 0.0) -> float:
    """If `get_clip_dur` returns 0 (stub file / corrupt header), fall back
    to the planned segment span. This is the 2026-06-04 fix for the final
    summary table showing `Duration: 0s` for a real 30s clip.
    """
    if not segments_data:
        return fallback
    try:
        seg_start = parse_timestamp_str(segments_data[0].get("start", "0"))
        seg_end = parse_timestamp_str(segments_data[-1].get("end", "0"))
        if seg_end > seg_start:
            return seg_end - seg_start
    except Exception:
        pass
    return fallback


def parse_timestamp_str(ts) -> float:
    """Parse timestamp string to float seconds."""
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


def get_clip_duration(path: Path) -> float:
    """Get duration of a clip file."""
    return get_clip_dur(path)


def main():
    parser = argparse.ArgumentParser(
        description="Kre8 Clips v2 — AI-Powered Viral Clip Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  clipgen "https://youtube.com/watch?v=..."
  clipgen "https://youtube.com/watch?v=..." --prompt "Leadership advice"
  clipgen "https://youtube.com/watch?v=..." --min-duration 45 --max-duration 90
  clipgen "https://youtube.com/watch?v=..." --aspect-ratio 16:9

Features:
  --speaker-tracking  Track and frame active speaker (future)
  --aspect-ratio      Output format: 9:16, 16:9, 1:1 (default: 9:16)
  --captions          Burn in styled captions
  --min-duration      Minimum clip duration in seconds (default: 30)
  --max-duration      Maximum clip duration in seconds (default: 120)
  --narrative         Reorder non-contiguous segments for better narrative
        """
    )

    parser.add_argument("url", nargs="?", help="YouTube video URL")

    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run environment and regression health checks"
    )

    parser.add_argument(
        "--prune-jobs",
        type=int,
        default=None,
        metavar="DAYS",
        help="Delete .jobs/ entries older than DAYS days, then exit"
    )

    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete all cached API responses, then exit"
    )

    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="Print API cache statistics, then exit"
    )

    parser.add_argument(
        "--training-stats",
        action="store_true",
        help="Print viral predictor training data statistics, then exit"
    )

    parser.add_argument(
        "--corpus-stats",
        action="store_true",
        help="Print viral corpus statistics and patterns, then exit"
    )

    parser.add_argument(
        "--analyze-viral-reel",
        type=str,
        metavar="VIDEO",
        help="Analyze a viral reel (local video path) and add it to the corpus"
    )

    parser.add_argument(
        "--reel-views",
        type=int,
        default=0,
        help="Engagement: view count for the reel being ingested"
    )

    parser.add_argument(
        "--reel-likes",
        type=int,
        default=0,
        help="Engagement: like count for the reel being ingested"
    )

    parser.add_argument(
        "--reel-comments",
        type=int,
        default=0,
        help="Engagement: comment count for the reel being ingested"
    )

    parser.add_argument(
        "--reel-shares",
        type=int,
        default=0,
        help="Engagement: share count for the reel being ingested"
    )

    parser.add_argument(
        "--reel-saves",
        type=int,
        default=0,
        help="Engagement: save count for the reel being ingested"
    )

    parser.add_argument(
        "--reel-watch-pct",
        type=float,
        default=0.0,
        help="Engagement: average watch percentage (0-1) for the reel being ingested"
    )

    parser.add_argument(
        "--reel-platform",
        type=str,
        default="tiktok",
        choices=["tiktok", "reels", "shorts"],
        help="Platform for the reel being ingested"
    )

    parser.add_argument(
        "--why-viral",
        type=str,
        default="",
        help="Free-form note on why this reel went viral"
    )

    parser.add_argument(
        "--reel-category",
        type=str,
        default="",
        help="Category/niche for the reel being ingested (e.g. finance, comedy)"
    )

    parser.add_argument(
        "--prompt", "-p",
        default="Find the most engaging, complete narrative moments. Look for stories with a beginning, middle, and end. Find lessons, insights, or powerful stories that can stand alone.",
        help="Custom prompt for AI clip analysis"
    )

    parser.add_argument(
        "--narrative", "-n",
        action=argparse.BooleanOptionalAction,
        default=NARRATIVE_MODE,
        help="Enable narrative mode (combine non-contiguous segments)"
    )

    parser.add_argument(
        "--smart-narrative",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable smart narrative assembly (AI selects best hook/body/payoff from different clips)"
    )

    parser.add_argument(
        "--aspect-ratio", "-a",
        choices=["9:16", "16:9", "1:1", "4:5"],
        default=DEFAULT_ASPECT_RATIO,
        help="Output aspect ratio (default: 9:16 for Reels)"
    )

    parser.add_argument(
        "--speaker-tracking",
        action=argparse.BooleanOptionalAction,
        default=ENABLE_SPEAKER_TRACKING,
        help="Enable speaker tracking (requires face detection model)"
    )

    parser.add_argument(
        "--captions", "-c",
        action=argparse.BooleanOptionalAction,
        default=ENABLE_CAPTIONS,
        help="Burn in styled captions"
    )

    parser.add_argument(
        "--caption-style",
        choices=["pop", "fade", "typewriter", "none"],
        default=CAPTION_STYLE,
        help="Caption animation style (default: pop)"
    )

    parser.add_argument(
        "--min-duration",
        type=int,
        default=30,
        help="Minimum clip duration in seconds (default: 30)"
    )

    parser.add_argument(
        "--max-duration",
        type=int,
        default=120,
        help="Maximum clip duration in seconds (default: 120)"
    )

    parser.add_argument(
        "--num-clips",
        type=int,
        default=5,
        help="Number of clips to generate (default: 5)"
    )

    parser.add_argument(
        "--job-dir",
        type=str,
        default=None,
        help="Job-specific output directory"
    )

    parser.add_argument(
        "--format", "-f",
        choices=["mp4", "mov"],
        default="mp4",
        help="Output video format (default: mp4)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    parser.add_argument(
        "--output", "-o",
        help="Custom output directory"
    )

    args = parser.parse_args()

    if args.doctor:
        return run_doctor()

    if args.clear_cache:
        removed = api_cache.clear_cache()
        console.print(f"[bold green]✓[/bold green] Cleared {removed} cached API responses")
        return 0

    if args.cache_stats:
        stats = api_cache.cache_stats()
        from utils.progress import print_info
        print_info(
            f"API cache: {stats['transcripts']} transcripts + {stats['responses']} responses "
            f"= {stats['total_bytes'] / 1024:.1f} KB"
        )
        return 0

    if args.training_stats:
        from core.viral_model import training_stats
        from utils.progress import print_info
        stats = training_stats()
        print_info(
            f"Training corpus: {stats['total_records']} clips, "
            f"{stats['with_outcomes']} with outcomes "
            f"({stats['storage_path']})"
        )
        if stats['outcome_breakdown']:
            print_info(f"Outcomes: {stats['outcome_breakdown']}")
        return 0

    if args.corpus_stats:
        from core.viral_corpus import corpus_stats, get_patterns
        from utils.progress import print_info
        stats = corpus_stats()
        print_info(f"Viral corpus: {stats['corpus_size']} reels indexed at {stats['patterns_path']}")
        if stats['hook_distribution']:
            print_info(f"Hook types: {stats['hook_distribution']}")
        if stats['insights']:
            print_info("Insights:")
            for line in stats['insights']:
                print_info(f"  • {line}")
        patterns = get_patterns()
        correlations = patterns.get("correlations") or {}
        for target, by_key in correlations.items():
            sig = {k: v for k, v in (by_key or {}).items() if isinstance(v, (int, float))}
            if sig:
                top = sorted(sig.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
                print_info(f"  Top correlations {target}: {top}")
        return 0

    if args.analyze_viral_reel:
        from core.viral_corpus import add_reel, EngagementMetrics
        from utils.progress import print_info, print_error
        video = Path(args.analyze_viral_reel).expanduser()
        if not video.exists():
            print_error(f"Reel not found: {video}")
            return 1
        engagement = EngagementMetrics(
            views=args.reel_views,
            likes=args.reel_likes,
            comments=args.reel_comments,
            shares=args.reel_shares,
            saves=args.reel_saves,
            avg_watch_pct=args.reel_watch_pct,
            platform=args.reel_platform,
        )
        print_info(f"Analyzing viral reel: {video.name}")
        try:
            reel_id = add_reel(
                video,
                engagement=engagement,
                why_viral=args.why_viral,
                category=args.reel_category,
            )
            print_info(f"Ingested as: {reel_id}")
            print_info(
                f"Engagement: {engagement.views} views, {engagement.likes} likes, "
                f"{engagement.shares} shares, {engagement.saves} saves"
            )
        except Exception as e:
            print_error(f"Failed to analyze reel: {e}")
            return 1
        return 0

    if args.prune_jobs is not None:
        from core.job_data_manager import JOBS_DIR
        from datetime import datetime, timedelta
        cutoff = time.time() - args.prune_jobs * 24 * 3600
        if not JOBS_DIR.exists():
            console.print("[dim].jobs/ directory does not exist[/dim]")
            return 0
        removed = 0
        for entry in JOBS_DIR.iterdir():
            try:
                if entry.stat().st_mtime < cutoff:
                    if entry.is_dir():
                        import shutil
                        shutil.rmtree(entry)
                    else:
                        entry.unlink()
                    removed += 1
            except OSError:
                pass
        console.print(f"[bold green]✓[/bold green] Pruned {removed} entries older than {args.prune_jobs} days from .jobs/")
        return 0

    # Interactive mode if no URL provided
    if not args.url:
        print_banner()
        console.print("\n[bold]Welcome to Kre8 Clips v2![/bold]\n")
        console.print("[dim]Paste a YouTube video URL:[/dim]")
        url = console.input("> ").strip()

        if not url:
            console.print("\n[dim]No URL provided. Run with --help for usage information.[/dim]\n")
            return 0

        console.print("[dim]Enter a custom prompt (or press Enter for default):[/dim]")
        custom_prompt = console.input("> ").strip()
        user_prompt = custom_prompt if custom_prompt else args.prompt

        console.print("[dim]Enable captions? y/N:[/dim]")
        caption_input = console.input("> ").strip().lower()
        enable_captions = caption_input in ["y", "yes"]

        console.print(f"[dim]Select aspect ratio (9:16/16:9/1:1) [default: {args.aspect_ratio}]:[/dim]")
        aspect_input = console.input("> ").strip() or args.aspect_ratio
        aspect_ratio = aspect_input if aspect_input in ["9:16", "16:9", "1:1", "4:5"] else "9:16"

        console.print("[dim]Enable narrative mode? y/N:[/dim]")
        narrative_input = console.input("> ").strip().lower()
        narrative_mode = narrative_input in ["y", "yes"]

        console.print()
    else:
        url = args.url
        effective_prompt = args.prompt if args.prompt and args.prompt.strip() else "Find the most engaging, complete narrative moments. Look for stories with a beginning, middle, and end. Find lessons, insights, or powerful stories that can stand alone."
        user_prompt = effective_prompt
        enable_captions = args.captions
        aspect_ratio = args.aspect_ratio
        narrative_mode = args.narrative

    # Run
    print_banner()

    if enable_captions:
        console.print(f"[dim]Captions:[/dim] [bold green]enabled[/bold green] (style: {args.caption_style})")
    console.print(f"[dim]Aspect ratio:[/dim] [bold]{aspect_ratio}[/bold]")
    console.print(f"[dim]Duration range:[/dim] [bold]{args.min_duration}s - {args.max_duration}s[/bold]")
    console.print(f"[dim]Clip count:[/dim] [bold]{args.num_clips}[/bold]\n")

    success = run_clipgen(
        url, user_prompt,
        narrative_mode=narrative_mode,
        smart_narrative_mode=args.smart_narrative,
        verbose=args.verbose,
        aspect_ratio=aspect_ratio,
        enable_speaker_tracking=args.speaker_tracking,
        enable_captions=enable_captions,
        caption_style=args.caption_style,
        min_clip_duration=args.min_duration,
        max_clip_duration=args.max_duration,
        num_clips=args.num_clips,
        output_format=args.format,
        output_dir=Path(args.output).expanduser() if args.output else None,
        job_output_dir=Path(args.job_dir).expanduser() if args.job_dir else None,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
