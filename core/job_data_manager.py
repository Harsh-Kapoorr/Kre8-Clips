"""
Job Data Manager — Save/Load comprehensive job data for downstream operations.

After AI analysis, we save:
- Full transcript with word timestamps
- Per-segment AI scores (hook, emotion, curiosity, shareability, etc.)
- Beat timestamps
- Emotional density heatmap
- Speaker info
- All generated clips with full metadata

This allows subsequent operations (web editor, clip variations,
multi-platform exports) to work without re-running AI analysis.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from .job_data_schema import JobData, create_job_data


JOBS_DIR = Path(__file__).parent.parent / ".jobs"


def ensure_jobs_dir():
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def job_file_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def save_job_data(job_data: JobData) -> None:
    """Save comprehensive job data to JSON file.

    Preserves frontend-managed fields (id, step, progress, step_detail,
    status, output_files, started_at, ended_at, error) so the Next.js
    progress UI is not knocked back to "Complete / done" mid-render.
    """
    ensure_jobs_dir()
    path = job_file_path(job_data.job_id)
    payload = job_data.to_dict()
    if path.exists():
        try:
            with open(path) as f:
                existing = json.load(f)
            for k in ("id", "step", "progress", "step_detail", "status",
                      "output_files", "started_at", "ended_at", "error",
                      "options"):
                if k in existing and k not in payload:
                    payload[k] = existing[k]
        except Exception:
            pass
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def load_job_data(job_id: str) -> Optional[JobData]:
    """Load comprehensive job data from JSON file."""
    path = job_file_path(job_id)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            d = json.load(f)
        return JobData.from_dict(d)
    except Exception:
        return None


def _parse_timestamp_value(ts) -> float:
    """Parse HH:MM:SS or seconds value to float seconds."""
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


def _clip_text_segments_for_update(
    clip: dict,
    transcript: list,
    *,
    padding: float = 0.5,
) -> list:
    """Filter the stored transcript to text segments inside the clip's window.

    Mirrors `clipgen.clip_text_segments` but lives here to avoid pulling
    the top-level `clipgen` module into `core/`. The AI's clip
    `segments` carry only start/end metadata, so we look up the actual
    `text` from the job's stored transcript.
    """
    clip_segs = clip.get("segments") or []
    if not clip_segs or not transcript:
        return []

    starts, ends = [], []
    for seg in clip_segs:
        if not isinstance(seg, dict):
            continue
        s = _parse_timestamp_value(seg.get("start", "0"))
        e = _parse_timestamp_value(seg.get("end", "0"))
        if e > s:
            starts.append(s)
            ends.append(e)
    if not starts:
        return []

    clip_start = min(starts) - padding
    clip_end = max(ends) + padding

    matched = []
    for t in transcript:
        if not isinstance(t, dict):
            continue
        text = (t.get("text") or "").strip()
        if not text:
            continue
        try:
            t_start = float(t.get("start", 0.0))
            t_end = float(t.get("end", t_start))
        except (TypeError, ValueError):
            continue
        if t_end >= clip_start and t_start <= clip_end:
            matched.append({"text": text, "speaker": t.get("speaker")})
    return matched


def _compute_viral_prediction(
    clip: dict,
    transcript: list,
    predictor,
) -> Optional[dict]:
    """Compute a viral prediction dict for `clip` using the stored transcript.

    Returns None on failure so the caller can fall back to whatever was
    already in `prior`. Used to repair clips that were added to the job
    AFTER the initial save (e.g., smart-narrative-assembled clips) and
    therefore have no prior viral fields.
    """
    try:
        text_segments = _clip_text_segments_for_update(clip, transcript)
        if not text_segments:
            text_segments = [{"text": clip.get("title", "")}]
        duration = float(
            clip.get("duration_seconds")
            or clip.get("duration")
            or 0.0
        )
        prediction = predictor.predict(
            segments=text_segments,
            duration=duration,
            clip_id=clip.get("id"),
        )
        return prediction.to_dict()
    except Exception as exc:
        print(f"[viral] update_job_clips: failed to compute prediction: {exc}")
        return None


def update_job_clips(job_id: str, clips: list[dict]) -> None:
    """Update generated clips in existing job data.

    Preserves viral prediction fields and boundary snapping fields that the
    first save_job_data() call already wrote. We merge per-clip with whatever
    the previous GeneratedClip held, so render-time info (output_path,
    reliability_score, render_error) is also kept.

    If a clip has no prior viral fields (e.g., it was added by smart-narrative
    assembly AFTER the initial save), we recompute the prediction on the fly
    from the stored transcript so the UI never shows "0%" for a real clip.
    """
    job_data = load_job_data(job_id)
    if not job_data:
        return

    from .job_data_schema import GeneratedClip, ClipSegment, ContextReference
    from .viral_model import ViralPredictor

    existing_by_id = {}
    for c in job_data.generated_clips or []:
        if isinstance(c, dict) and c.get("id"):
            existing_by_id[c["id"]] = c
        elif hasattr(c, "id"):
            existing_by_id[c.id] = {
                "id": c.id, "title": c.title, "original_title": c.original_title,
                "priority": c.priority, "hook_score": c.hook_score,
                "emotional_tone": c.emotional_tone, "main_speaker": c.main_speaker,
                "topic": c.topic, "reason": c.reason, "quote_potential": c.quote_potential,
                "hashtags": c.hashtags, "segments": c.segments,
                "reliability_score": c.reliability_score,
                "context_needed": c.context_needed, "output_path": c.output_path,
                "duration_seconds": c.duration_seconds,
                "viral_share_prob": c.viral_share_prob,
                "viral_save_prob": c.viral_save_prob,
                "viral_comment_prob": c.viral_comment_prob,
                "viral_composite": c.viral_composite,
                "viral_model_version": c.viral_model_version,
                "viral_features": c.viral_features,
                "boundary_confidence": c.boundary_confidence,
                "boundary_start_reason": c.boundary_start_reason,
                "boundary_end_reason": c.boundary_end_reason,
            }

    transcript = []
    for t in job_data.transcript or []:
        if isinstance(t, dict):
            transcript.append({
                "start": t.get("start", 0.0),
                "end": t.get("end", 0.0),
                "text": t.get("text", ""),
                "speaker": t.get("speaker"),
            })
        else:
            transcript.append({
                "start": getattr(t, "start", 0.0),
                "end": getattr(t, "end", 0.0),
                "text": getattr(t, "text", ""),
                "speaker": getattr(t, "speaker", None),
            })

    needs_prediction = any(
        not (existing_by_id.get(f"clip_{i+1}", {}).get("viral_model_version"))
        for i, _ in enumerate(clips)
    )
    predictor = ViralPredictor(persist=False) if needs_prediction else None

    generated_clips = []
    for i, clip in enumerate(clips):
        clip_id = f"clip_{i+1}"
        prior = existing_by_id.get(clip_id, {})

        segments = []
        for seg in clip.get("segments", []):
            if isinstance(seg, dict):
                segments.append(ClipSegment(
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

        viral_share = prior.get("viral_share_prob", 0.0)
        viral_save = prior.get("viral_save_prob", 0.0)
        viral_comment = prior.get("viral_comment_prob", 0.0)
        viral_composite = prior.get("viral_composite", 0.0)
        viral_model_version = prior.get("viral_model_version", "")
        viral_features = prior.get("viral_features", {})

        if not viral_model_version and predictor is not None and transcript:
            computed = _compute_viral_prediction(clip, transcript, predictor)
            if computed:
                viral_share = float(computed.get("share", 0.0))
                viral_save = float(computed.get("save", 0.0))
                viral_comment = float(computed.get("comment", 0.0))
                viral_composite = float(computed.get("composite", 0.0))
                viral_model_version = computed.get("model_version", "")
                viral_features = computed.get("features", {})

        merged = GeneratedClip(
            id=clip_id,
            title=clip.get("title") or prior.get("title", f"Clip {i+1}"),
            original_title=clip.get("original_title", prior.get("original_title", "")),
            priority=clip.get("priority", prior.get("priority", 5)),
            hook_score=clip.get("hook_score", prior.get("hook_score", 5.0)),
            emotional_tone=clip.get("emotional_tone", prior.get("emotional_tone", "neutral")),
            main_speaker=clip.get("main_speaker", prior.get("main_speaker", "UNKNOWN")),
            topic=clip.get("topic", prior.get("topic", "")),
            reason=clip.get("reason", prior.get("reason", "")),
            quote_potential=clip.get("quote_potential", prior.get("quote_potential", "")),
            hashtags=clip.get("hashtags", prior.get("hashtags", [])),
            segments=segments,
            reliability_score=clip.get("reliability_score", prior.get("reliability_score")),
            context_needed=context_needed or prior.get("context_needed"),
            output_path=clip.get("path", "") or prior.get("output_path", ""),
            duration_seconds=clip.get("duration_seconds", clip.get("duration", prior.get("duration_seconds", 0.0))),
            viral_share_prob=viral_share,
            viral_save_prob=viral_save,
            viral_comment_prob=viral_comment,
            viral_composite=viral_composite,
            viral_model_version=viral_model_version,
            viral_features=viral_features,
            boundary_confidence=prior.get("boundary_confidence", 0.0),
            boundary_start_reason=prior.get("boundary_start_reason", ""),
            boundary_end_reason=prior.get("boundary_end_reason", ""),
        )
        if clip.get("render_error"):
            merged.render_error = clip["render_error"]
            merged.render_traceback = clip.get("render_traceback", "")
        generated_clips.append(merged)

    job_data.generated_clips = generated_clips
    job_data.completed_at = datetime.utcnow().isoformat() + "Z"
    save_job_data(job_data)


def update_job_transcript(
    job_id: str,
    segments: list[dict],
    words: Optional[list[dict]] = None,
    video_duration: float = 0.0,
    video_path: str = "",
    audio_path: str = ""
) -> None:
    """Update transcript data in existing job data."""
    job_data = load_job_data(job_id)
    if not job_data:
        return

    from .job_data_schema import TranscriptSegment, WordTimestamp, BeatTimestamp

    transcript = [
        TranscriptSegment(
            start=s.get("start", 0.0),
            end=s.get("end", 0.0),
            text=s.get("text", ""),
            speaker=s.get("speaker")
        )
        for s in segments
    ]

    word_timestamps = []
    if words:
        word_timestamps = [
            WordTimestamp(
                word=w.get("word", ""),
                start=w.get("start", 0.0),
                end=w.get("end", 0.0),
                speaker=w.get("speaker"),
                confidence=w.get("confidence", 1.0)
            )
            for w in words
        ]

    job_data.transcript = transcript
    job_data.word_timestamps = word_timestamps
    job_data.video_duration = video_duration
    job_data.video_path = video_path
    job_data.audio_path = audio_path

    save_job_data(job_data)


def update_job_ai_analysis(
    job_id: str,
    clips: list[dict],
    beat_timestamps: list[float] = None,
    raw_response: str = ""
) -> None:
    """
    Update AI analysis data after Gemini analysis.
    Also builds per-segment scores for the viral heatmap.
    """
    job_data = load_job_data(job_id)
    if not job_data:
        return

    from .job_data_schema import AIGramSegment, AIGramSegmentScores, EmotionalDensity

    ai_segments = []
    all_scores = []

    for clip in clips:
        for seg in clip.get("segments", []):
            start = seg.get("start_seconds", seg.get("start", 0))
            end = seg.get("end_seconds", seg.get("end", 0))

            hook = clip.get("hook_score", 5)
            emotion = _estimate_emotion_score(clip)
            curiosity = _estimate_curiosity(clip)
            shareability = hook
            clarity = 7.0
            authority = 6.0

            all_scores.append(hook)
            all_scores.append(emotion)

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
                contains_hook_phrase=_has_hook_phrase(clip),
                viral_indicators=_extract_viral_indicators(clip)
            )

            ai_segments.append(AIGramSegment(
                start=start,
                end=end,
                scores=scores,
                beat_synced=seg.get("_snapped", False)
            ))

    emotional_density = _build_emotional_density(all_scores)

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
        "beat_timestamps": beat_timestamps or [],
        "emotional_density": emotional_density
    }

    job_data.raw_ai_response = raw_response
    save_job_data(job_data)


def _estimate_emotion_score(clip: dict) -> float:
    tone = clip.get("emotional_tone", "neutral").lower()
    tone_scores = {
        "controversial": 8.5,
        "inspiring": 8.0,
        "surprising": 8.5,
        "funny": 7.5,
        "educational": 6.5,
        "motivational": 8.0,
        "neutral": 5.0
    }
    return tone_scores.get(tone, 5.0)


def _estimate_curiosity(clip: dict) -> float:
    reason = clip.get("reason", "").lower()
    curiosity_indicators = ["surprising", "secret", "mistake", "truth", "problem", "imagine", "what if"]
    base = 5.0
    for indicator in curiosity_indicators:
        if indicator in reason:
            base += 1.0
    return min(10, base)


def _has_hook_phrase(clip: dict) -> bool:
    hook_phrases = ["you know", "here's the thing", "most important", "the secret", "the problem", "imagine", "what if", "here's why", "first", "actually", "honestly"]
    text = clip.get("title", "").lower() + " " + clip.get("reason", "").lower()
    return any(phrase in text for phrase in hook_phrases)


def _extract_viral_indicators(clip: dict) -> list:
    indicators = []
    hook_phrases = ["you know", "here's the thing", "most important", "the secret", "the problem", "imagine", "what if", "here's why", "first", "actually", "honestly", "trust me", "believe me"]
    text = clip.get("title", "").lower() + " " + clip.get("reason", "").lower()
    for phrase in hook_phrases:
        if phrase in text:
            indicators.append(phrase)
    return indicators


def _build_emotional_density(scores: list[float], bucket_size: float = 5.0) -> list[dict]:
    if not scores:
        return []
    density = []
    for i, score in enumerate(scores):
        time = i * bucket_size
        label = "spike" if score >= 8 else "medium" if score >= 6 else "low"
        density.append({"time": time, "score": score / 10.0, "type": label})
    return density


def enrich_job_with_broll_suggestions(job_id: str, transcript_segments: list[dict]) -> None:
    """Extract B-roll suggestions from transcript keywords."""
    job_data = load_job_data(job_id)
    if not job_data:
        return

    from .job_data_schema import BrollSuggestion

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
    for seg in transcript_segments:
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