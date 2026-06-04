"""
Kre8 Clips v2 — Comprehensive Job Data Schema

This module defines the complete data structure for storing all
pipeline outputs (transcript, AI analysis, segments, etc.) so that
subsequent operations (web editor, clip variations, multi-platform
exports) can work without re-running AI analysis.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    words: list = field(default_factory=list)


@dataclass
class WordTimestamp:
    word: str
    start: float
    end: float
    speaker: Optional[str] = None
    confidence: float = 1.0


@dataclass
class AIGramSegmentScores:
    hook_score: float = 5.0
    emotion_score: float = 5.0
    curiosity_score: float = 5.0
    authority_score: float = 5.0
    story_score: float = 5.0
    shareability_score: float = 5.0
    clarity_score: float = 5.0
    platform_match: dict = field(default_factory=lambda: {
        "tiktok": 5.0,
        "linkedin": 5.0,
        "youtube_shorts": 5.0
    })
    emotional_tone: str = "neutral"
    topic: str = ""
    main_speaker: str = "UNKNOWN"
    contains_cta: bool = False
    contains_hook_phrase: bool = False
    viral_indicators: list = field(default_factory=list)


@dataclass
class AIGramSegment:
    start: float
    end: float
    scores: AIGramSegmentScores = field(default_factory=AIGramSegmentScores)
    beat_synced: bool = False


@dataclass
class BeatTimestamp:
    time: float
    strength: float = 1.0


@dataclass
class EmotionalDensity:
    time: float
    density: float
    label: str = "normal"


@dataclass
class ClipSegment:
    start: str
    end: str
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    duration: float = 0.0
    segment_role: str = "body"
    viral_potential: int = 5
    opening_strength: int = 5
    closing_strength: int = 5


@dataclass
class ContextReference:
    start: str
    end: str
    reason: str = ""


@dataclass
class GeneratedClip:
    id: str
    title: str
    original_title: str = ""
    priority: int = 5
    hook_score: float = 5.0
    emotional_tone: str = "neutral"
    main_speaker: str = "UNKNOWN"
    topic: str = ""
    reason: str = ""
    quote_potential: str = ""
    hashtags: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    reliability_score: Optional[float] = None
    context_needed: Optional[ContextReference] = None
    output_path: str = ""
    duration_seconds: float = 0.0
    # New viral prediction fields
    viral_share_prob: float = 0.0
    viral_save_prob: float = 0.0
    viral_comment_prob: float = 0.0
    viral_composite: float = 0.0
    viral_model_version: str = ""
    viral_features: dict = field(default_factory=dict)
    boundary_confidence: float = 0.0
    boundary_start_reason: str = ""
    boundary_end_reason: str = ""
    render_error: str = ""
    render_traceback: str = ""


@dataclass
class CreatorProfile:
    caption_style: str = "pop"
    transition_style: str = "fade"
    pacing_preference: str = "medium"
    preferred_hook_types: list = field(default_factory=list)
    aspect_ratio_priority: list = field(default_factory=lambda: ["9:16"])
    meme_usage: bool = False
    broll_style: str = "minimal"
    custom_templates: list = field(default_factory=list)


@dataclass
class BrollSuggestion:
    time: float
    keyword: str
    suggestions: list = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class ClipVariation:
    variant_id: str
    style: str
    hook_start_override: Optional[str] = None
    context_included: bool = False
    emotional_climax_highlighted: bool = False
    removed_silence: bool = False


@dataclass
class PlatformExportConfig:
    aspect_ratio: str = "9:16"
    caption_style: str = "pop"
    cta_enabled: bool = True
    title_modifier: str = ""
    hashtag_count: int = 5


@dataclass
class ClipMultiPlatformExports:
    tiktok: PlatformExportConfig = field(default_factory=PlatformExportConfig)
    linkedin: PlatformExportConfig = field(default_factory=lambda: PlatformExportConfig(
        aspect_ratio="9:16", caption_style="minimal", cta_enabled=False
    ))
    youtube_shorts: PlatformExportConfig = field(default_factory=lambda: PlatformExportConfig(
        aspect_ratio="9:16", caption_style="fade", cta_enabled=True
    ))


@dataclass
class JobData:
    job_id: str
    url: str
    video_title: str
    video_duration: float = 0.0
    video_path: str = ""
    audio_path: str = ""
    created_at: str = ""
    completed_at: str = ""

    transcript: list = field(default_factory=list)
    word_timestamps: list = field(default_factory=list)

    ai_analysis: dict = field(default_factory=lambda: {
        "segments": [],
        "beat_timestamps": [],
        "emotional_density": []
    })

    generated_clips: list = field(default_factory=list)

    creator_profile: CreatorProfile = field(default_factory=CreatorProfile)

    broll_suggestions: list = field(default_factory=list)

    clip_variations: dict = field(default_factory=dict)
    clip_multi_platform_exports: dict = field(default_factory=dict)

    raw_ai_response: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "JobData":
        if "creator_profile" in d and isinstance(d["creator_profile"], dict):
            d["creator_profile"] = CreatorProfile(**d["creator_profile"])
        expected = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in d.items() if k in expected}
        return cls(**filtered)


def create_job_data(job_id: str, url: str, video_title: str) -> JobData:
    """Create a new JobData instance with metadata."""
    from datetime import datetime
    return JobData(
        job_id=job_id,
        url=url,
        video_title=video_title,
        created_at=datetime.utcnow().isoformat() + "Z"
    )