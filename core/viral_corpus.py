"""
Viral corpus — ingest known-viral reels and reverse-engineer what makes them work.

This is the active-learning arm of the system: instead of waiting for thumbs-up
feedback on our generated clips, we proactively harvest high-performing reference
content, analyze it across every dimension that matters (cuts, music, text
placement, script structure, hook, animation, relatability, shareability, save-
worthiness), and use the aggregated patterns to refine the predictor.

Each reel is stored under .training/viral_corpus/<reel_id>/ with:
  - video.mp4           (the source file)
  - audio.wav           (16k mono extract)
  - transcript.json     (Deepgram output)
  - analysis.json       (full per-reel analysis)
  - metadata.json       (engagement metrics, source, "why viral" notes)

Aggregate insights live in .training/viral_corpus/patterns.json.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from config.settings import BASE_DIR


CORPUS_ROOT = BASE_DIR / ".training" / "viral_corpus"


# ----- Engagement data ------------------------------------------------------

@dataclass
class EngagementMetrics:
    """Real-world performance data for a reel."""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    avg_watch_pct: float = 0.0
    platform: str = "tiktok"  # tiktok, reels, shorts

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def engagement_rate(self) -> float:
        if self.views <= 0:
            return 0.0
        interactions = self.likes + self.comments + self.shares + self.saves
        return interactions / self.views

    @property
    def share_rate(self) -> float:
        return self.shares / self.views if self.views > 0 else 0.0

    @property
    def save_rate(self) -> float:
        return self.saves / self.views if self.views > 0 else 0.0

    @property
    def comment_rate(self) -> float:
        return self.comments / self.views if self.views > 0 else 0.0


# ----- Per-reel analysis ----------------------------------------------------

@dataclass
class ReelAnalysis:
    """Structured analysis of one viral reel."""
    reel_id: str
    duration_seconds: float = 0.0
    word_count: int = 0
    words_per_second: float = 0.0
    sentences: int = 0
    sentence_lengths: List[int] = field(default_factory=list)
    question_count: int = 0
    exclamation_count: int = 0
    cut_count: int = 0
    average_shot_length: float = 0.0
    cut_density_per_min: float = 0.0
    music_bpm: float = 0.0
    music_energy: float = 0.0
    hook_text: str = ""
    hook_type: str = ""  # pattern_interrupt, curiosity_gap, contrarian, question, bold_claim
    hook_score: float = 0.0
    payoff_text: str = ""
    payoff_score: float = 0.0
    has_you_statements: bool = False
    you_count: int = 0
    controversy_score: float = 0.0
    specificity_score: float = 0.0
    actionability_score: float = 0.0
    quotability_score: float = 0.0
    emotion_intensity: float = 0.0
    story_structure_score: float = 0.0
    full_text: str = ""
    segments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----- Storage helpers ------------------------------------------------------

def _ensure_corpus_dir() -> Path:
    CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
    return CORPUS_ROOT


def _reel_dir(reel_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", reel_id)[:64] or f"reel_{int(time.time())}"
    path = CORPUS_ROOT / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_reels() -> List[str]:
    _ensure_corpus_dir()
    return sorted([p.name for p in CORPUS_ROOT.iterdir() if p.is_dir()])


# ----- Per-reel analysis pipeline ------------------------------------------

QUESTION_REGEX = re.compile(r"\?")
EXCLAMATION_REGEX = re.compile(r"!")
SENTENCE_END_REGEX = re.compile(r"[.!?](?:\s|$|[\"'])")
PERSONAL_PRONOUN_REGEX = re.compile(r"\b(you|your|you're|you've|you'll|you'd)\b", re.IGNORECASE)


def _try_librosa():
    try:
        import librosa
        return librosa
    except ImportError:
        return None


def _transcribe(audio_path: Path) -> List[Dict[str, Any]]:
    """Lightweight wrapper around Deepgram if available, else empty list."""
    from core.transcriber import transcribe_audio
    try:
        return transcribe_audio(audio_path)
    except Exception:
        return []


def _extract_audio(video_path: Path, dest: Path) -> Path:
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


def _count_cuts(video_path: Path) -> int:
    """Detect scene changes via ffmpeg scene-change detector. Cheap and good enough."""
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(video_path),
        "-filter:v", "select='gt(scene,0.25)',showinfo",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return sum(1 for line in result.stderr.splitlines() if "Parsed_showinfo" in line or "showinfo" in line)
    except Exception:
        return 0


def _detect_hook(hook_text: str) -> str:
    from core.viral_model import (
        PATTERN_INTERRUPT_PHRASES,
        CURIOSITY_GAP_PHRASES,
        CONTRARIAN_PHRASES,
    )
    lower = hook_text.lower()
    for p in PATTERN_INTERRUPT_PHRASES:
        if p in lower:
            return "pattern_interrupt"
    for p in CURIOSITY_GAP_PHRASES:
        if p in lower:
            return "curiosity_gap"
    for p in CONTRARIAN_PHRASES:
        if p in lower:
            return "contrarian"
    if QUESTION_REGEX.search(hook_text):
        return "question"
    if EXCLAMATION_REGEX.search(hook_text):
        return "exclamation"
    return "statement"


def _analyze_script(text: str) -> Dict[str, float]:
    """Run the same feature extraction we use for our clips."""
    from core.viral_model import (
        _emotional_intensity, _controversy, _specificity,
        _actionability, _quotability, _relatability, _story_structure,
    )
    lower = text.lower()
    return {
        "controversy": _controversy(text),
        "specificity": _specificity(text),
        "actionability": _actionability(text),
        "quotability": _quotability(text),
        "relatability": _relatability(text),
        "emotion": _emotional_intensity(text),
        "story": _story_structure([{"text": text}]),
    }


def analyze_reel(
    video_path: Path,
    *,
    transcript: Optional[Sequence[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ReelAnalysis:
    """Deep analysis of one viral reel across all dimensions."""
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    reel_id = f"{video_path.stem}_{int(time.time())}"
    tmp_audio = video_path.with_suffix(".wav")

    if not tmp_audio.exists():
        try:
            _extract_audio(video_path, tmp_audio)
        except Exception as e:
            raise RuntimeError(f"ffmpeg audio extract failed: {e}")

    if transcript is None:
        transcript = _transcribe(tmp_audio)

    full_text = " ".join((s.get("text") or "").strip() for s in transcript)
    word_count = len(full_text.split())
    duration = 0.0
    if transcript:
        try:
            duration = max(
                (float(s.get("end", 0)) for s in transcript),
                default=0.0,
            )
        except Exception:
            duration = 0.0
    if duration <= 0:
        try:
            cmd_probe = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ]
            r = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=30)
            duration = float(r.stdout.strip() or 0.0)
        except Exception:
            duration = 0.0

    sentences = [s for s in re.split(r"[.!?]+", full_text) if s.strip()]
    sentence_lengths = [len(s.split()) for s in sentences]
    you_count = len(PERSONAL_PRONOUN_REGEX.findall(full_text))
    cut_count = _count_cuts(video_path)
    bpm = 0.0
    energy = 0.0
    librosa_mod = _try_librosa()
    if librosa_mod is not None and tmp_audio.exists():
        try:
            y, sr = librosa_mod.load(str(tmp_audio), sr=None, mono=True)
            tempo, _ = librosa_mod.beat.beat_track(y=y, sr=sr)
            bpm = float(tempo) if tempo is not None else 0.0
            rms = librosa_mod.feature.rms(y=y).mean()
            energy = float(rms)
        except Exception:
            pass

    hook_text = (transcript[0].get("text") or "") if transcript else full_text[:120]
    payoff_text = (transcript[-1].get("text") or "") if transcript else full_text[-120:]
    script_features = _analyze_script(full_text)

    analysis = ReelAnalysis(
        reel_id=reel_id,
        duration_seconds=float(duration),
        word_count=word_count,
        words_per_second=word_count / duration if duration > 0 else 0.0,
        sentences=len(sentences),
        sentence_lengths=sentence_lengths,
        question_count=len(QUESTION_REGEX.findall(full_text)),
        exclamation_count=len(EXCLAMATION_REGEX.findall(full_text)),
        cut_count=cut_count,
        average_shot_length=duration / max(1, cut_count + 1),
        cut_density_per_min=(cut_count / duration * 60) if duration > 0 else 0.0,
        music_bpm=bpm,
        music_energy=energy,
        hook_text=hook_text.strip(),
        hook_type=_detect_hook(hook_text),
        hook_score=min(1.0, len(hook_text.split()) / 12.0),
        payoff_text=payoff_text.strip(),
        payoff_score=min(1.0, len(payoff_text.split()) / 16.0),
        has_you_statements=you_count > 0,
        you_count=you_count,
        controversy_score=script_features["controversy"],
        specificity_score=script_features["specificity"],
        actionability_score=script_features["actionability"],
        quotability_score=script_features["quotability"],
        emotion_intensity=script_features["emotion"],
        story_structure_score=script_features["story"],
        full_text=full_text,
        segments=[{
            "start": s.get("start"),
            "end": s.get("end"),
            "speaker": s.get("speaker"),
            "text": s.get("text"),
        } for s in transcript],
        metadata=metadata or {},
    )
    return analysis


# ----- Ingestion ------------------------------------------------------------

def add_reel(
    video_path: Path,
    *,
    engagement: Optional[EngagementMetrics] = None,
    why_viral: str = "",
    source: str = "",
    category: str = "",
    transcript: Optional[Sequence[Dict[str, Any]]] = None,
) -> str:
    """Add a reel to the corpus. Returns the reel_id."""
    video_path = Path(video_path).expanduser()
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    reel_id = f"{video_path.stem}_{int(time.time())}"
    rdir = _reel_dir(reel_id)

    dest_video = rdir / "video.mp4"
    if dest_video.exists() or rdir.joinpath("video").exists():
        # Reel already exists; re-ingest under new id
        reel_id = f"{video_path.stem}_{int(time.time())}_v2"
        rdir = _reel_dir(reel_id)
        dest_video = rdir / "video.mp4"

    shutil.copy2(video_path, dest_video)

    try:
        analysis = analyze_reel(video_path, transcript=transcript, metadata={
            "source": source, "category": category, "why_viral": why_viral,
        })
    except Exception as e:
        analysis = ReelAnalysis(reel_id=reel_id, metadata={"error": str(e)})

    audio_wav = rdir / "audio.wav"
    if video_path.with_suffix(".wav").exists():
        shutil.move(str(video_path.with_suffix(".wav")), audio_wav)
    elif not audio_wav.exists():
        try:
            _extract_audio(dest_video, audio_wav)
        except Exception:
            pass

    transcript_payload = transcript if transcript is not None else analysis.segments
    (rdir / "transcript.json").write_text(
        json.dumps(transcript_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (rdir / "analysis.json").write_text(
        json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (rdir / "metadata.json").write_text(
        json.dumps({
            "reel_id": reel_id,
            "source_video": str(video_path),
            "stored_video": str(dest_video),
            "engagement": engagement.to_dict() if engagement else None,
            "why_viral": why_viral,
            "source": source,
            "category": category,
            "added_at": time.time(),
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    _refresh_patterns()
    return reel_id


# ----- Aggregate patterns ---------------------------------------------------

PATTERNS_FILE = CORPUS_ROOT / "patterns.json"


def _refresh_patterns() -> Dict[str, Any]:
    """Recompute aggregate patterns across the entire corpus."""
    _ensure_corpus_dir()
    reels = list_reels()
    if not reels:
        if PATTERNS_FILE.exists():
            PATTERNS_FILE.unlink()
        return {"corpus_size": 0}

    rows: List[Dict[str, Any]] = []
    for rid in reels:
        a = CORPUS_ROOT / rid / "analysis.json"
        m = CORPUS_ROOT / rid / "metadata.json"
        if not a.exists():
            continue
        try:
            row = json.loads(a.read_text(encoding="utf-8"))
            if m.exists():
                mdata = json.loads(m.read_text(encoding="utf-8"))
                row["engagement"] = mdata.get("engagement") or {}
                row["why_viral"] = mdata.get("why_viral") or ""
                row["category"] = mdata.get("category") or ""
        except Exception:
            continue
        rows.append(row)

    if not rows:
        return {"corpus_size": 0}

    def _stat(key: str) -> Dict[str, float]:
        vals = [float(r.get(key, 0)) for r in rows if isinstance(r.get(key), (int, float))]
        if not vals:
            return {"avg": 0.0, "min": 0.0, "max": 0.0, "count": 0}
        return {
            "avg": round(sum(vals) / len(vals), 3),
            "min": round(min(vals), 3),
            "max": round(max(vals), 3),
            "count": len(vals),
        }

    hook_types: Dict[str, int] = {}
    for r in rows:
        ht = r.get("hook_type") or "statement"
        hook_types[ht] = hook_types.get(ht, 0) + 1

    cuts = [r.get("cut_count", 0) for r in rows]
    avg_cuts = sum(cuts) / len(cuts) if cuts else 0
    shot_lengths = [r.get("average_shot_length", 0) for r in rows if r.get("average_shot_length")]
    avg_shot = sum(shot_lengths) / len(shot_lengths) if shot_lengths else 0

    # Engagement vs feature correlations (Pearson on matched pairs)
    def _corr(key: str, engagement_key: str) -> Optional[float]:
        xs = []
        ys = []
        for r in rows:
            eng = r.get("engagement") or {}
            v = eng.get(engagement_key)
            f = r.get(key)
            if isinstance(v, (int, float)) and isinstance(f, (int, float)) and v > 0:
                xs.append(float(f))
                ys.append(float(v))
        if len(xs) < 3:
            return None
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den_x = (sum((x - mx) ** 2 for x in xs)) ** 0.5
        den_y = (sum((y - my) ** 2 for y in ys)) ** 0.5
        if den_x == 0 or den_y == 0:
            return None
        return round(num / (den_x * den_y), 3)

    correlations = {
        "vs_share_rate": {
            k: _corr(k, "share_rate") for k in [
                "hook_score", "emotion_intensity", "controversy_score",
                "specificity_score", "actionability_score", "quotability_score",
                "words_per_second", "cut_density_per_min", "music_bpm", "music_energy",
            ]
        },
        "vs_save_rate": {
            k: _corr(k, "save_rate") for k in [
                "hook_score", "actionability_score", "specificity_score",
                "story_structure_score", "words_per_second",
            ]
        },
        "vs_comment_rate": {
            k: _corr(k, "comment_rate") for k in [
                "controversy_score", "question_count", "emotion_intensity",
                "you_count", "hook_score",
            ]
        },
    }

    patterns = {
        "corpus_size": len(rows),
        "last_refreshed": time.time(),
        "feature_stats": {
            "duration_seconds": _stat("duration_seconds"),
            "word_count": _stat("word_count"),
            "words_per_second": _stat("words_per_second"),
            "cut_count": _stat("cut_count"),
            "average_shot_length": _stat("average_shot_length"),
            "cut_density_per_min": _stat("cut_density_per_min"),
            "music_bpm": _stat("music_bpm"),
            "music_energy": _stat("music_energy"),
            "hook_score": _stat("hook_score"),
            "payoff_score": _stat("payoff_score"),
            "controversy_score": _stat("controversy_score"),
            "specificity_score": _stat("specificity_score"),
            "actionability_score": _stat("actionability_score"),
            "quotability_score": _stat("quotability_score"),
            "emotion_intensity": _stat("emotion_intensity"),
            "story_structure_score": _stat("story_structure_score"),
        },
        "hook_type_distribution": hook_types,
        "correlations": correlations,
        "top_reels_by_engagement": _top_reels(rows, k=5),
        "insights": _insights_from_patterns(rows),
    }
    PATTERNS_FILE.write_text(
        json.dumps(patterns, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return patterns


def _top_reels(rows: List[Dict[str, Any]], k: int = 5) -> List[Dict[str, Any]]:
    def _eng(r: Dict[str, Any]) -> float:
        e = r.get("engagement") or {}
        return float(e.get("likes", 0)) + float(e.get("comments", 0)) * 2
    ranked = sorted(rows, key=_eng, reverse=True)[:k]
    out = []
    for r in ranked:
        out.append({
            "reel_id": r.get("reel_id"),
            "engagement": r.get("engagement"),
            "hook_type": r.get("hook_type"),
            "words_per_second": r.get("words_per_second"),
            "cut_density_per_min": r.get("cut_density_per_min"),
            "music_bpm": r.get("music_bpm"),
            "why_viral": r.get("why_viral"),
        })
    return out


def _insights_from_patterns(rows: List[Dict[str, Any]]) -> List[str]:
    """Surface human-readable insights a creator can act on."""
    if not rows:
        return []
    out: List[str] = []

    avg_wps = sum(r.get("words_per_second", 0) for r in rows) / len(rows)
    out.append(
        f"Top-performing reels average {avg_wps:.2f} words/sec — match this pacing in your scripts."
    )

    avg_cuts = sum(r.get("cut_density_per_min", 0) for r in rows) / len(rows)
    out.append(
        f"Reference reels cut ~{avg_cuts:.1f} times/min — your clips should match this density for short-form."
    )

    avg_shot = sum(r.get("average_shot_length", 0) for r in rows) / max(1, len(rows))
    if avg_shot > 0:
        out.append(f"Average shot length in viral reels: {avg_shot:.1f}s.")

    bpm = sum(r.get("music_bpm", 0) for r in rows) / max(1, len(rows))
    if bpm > 0:
        out.append(f"Background music tempo: {bpm:.0f} BPM — pick a track in this range.")

    hook_dist: Dict[str, int] = {}
    for r in rows:
        ht = r.get("hook_type") or "statement"
        hook_dist[ht] = hook_dist.get(ht, 0) + 1
    if hook_dist:
        top = max(hook_dist.items(), key=lambda x: x[1])
        out.append(
            f"Most common hook type in your corpus: {top[0]} ({top[1]}/{len(rows)} reels)."
        )

    you_share = sum(1 for r in rows if r.get("has_you_statements")) / len(rows)
    out.append(
        f"{you_share * 100:.0f}% of viral reels address the viewer directly with 'you' statements."
    )

    contr_avg = sum(r.get("controversy_score", 0) for r in rows) / len(rows)
    if contr_avg > 0.3:
        out.append("Controversy/contrarian language is common in this corpus — strong lever for comments.")

    act_avg = sum(r.get("actionability_score", 0) for r in rows) / len(rows)
    if act_avg > 0.3:
        out.append("Actionable content (steps, frameworks, 'how to') is a strong save-signal in this corpus.")

    return out


def get_patterns() -> Dict[str, Any]:
    if not PATTERNS_FILE.exists():
        return _refresh_patterns()
    try:
        return json.loads(PATTERNS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _refresh_patterns()


def corpus_stats() -> Dict[str, Any]:
    patterns = get_patterns()
    return {
        "corpus_size": patterns.get("corpus_size", 0),
        "patterns_path": str(PATTERNS_FILE),
        "insights": patterns.get("insights", []),
        "hook_distribution": patterns.get("hook_type_distribution", {}),
    }


# ----- Refined predictor weights -------------------------------------------

def suggest_weights() -> Dict[str, Dict[str, float]]:
    """Use corpus correlations to suggest updated predictor weights.

    Returns a dict in the same shape as core.viral_model.WEIGHTS so the caller
    can swap it in. Falls back to current weights when the corpus is too small.
    """
    from core.viral_model import WEIGHTS

    patterns = get_patterns()
    if patterns.get("corpus_size", 0) < 5:
        return {"share": dict(WEIGHTS["share"]), "save": dict(WEIGHTS["save"]), "comment": dict(WEIGHTS["comment"])}

    cor_share = (patterns.get("correlations") or {}).get("vs_share_rate") or {}
    cor_save = (patterns.get("correlations") or {}).get("vs_save_rate") or {}
    cor_comment = (patterns.get("correlations") or {}).get("vs_comment_rate") or {}

    def _renormalize(d: Dict[str, float], target_sum: float) -> Dict[str, float]:
        if not d:
            return d
        s = sum(d.values())
        if s <= 0:
            return d
        return {k: round(v * target_sum / s, 4) for k, v in d.items()}

    def _abs_corr(d: Dict[str, Optional[float]]) -> Dict[str, float]:
        return {k: max(0.0, abs(v or 0.0)) for k, v in d.items()}

    share_w = _renormalize(_abs_corr(cor_share), sum(WEIGHTS["share"].values()))
    save_w = _renormalize(_abs_corr(cor_save), sum(WEIGHTS["save"].values()))
    comment_w = _renormalize(_abs_corr(cor_comment), sum(WEIGHTS["comment"].values()))

    return {"share": share_w, "save": save_w, "comment": comment_w}
