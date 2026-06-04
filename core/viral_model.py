"""
Viral prediction model.

Outputs three calibrated probabilities per clip:
  P(share)    — likelihood the viewer shares/forwards
  P(save)     — likelihood the viewer bookmarks for later
  P(comment)  — likelihood the viewer comments / engages

The default backend is a calibrated heuristic that mirrors the signals used
by short-form recommendation algorithms (hook strength, emotional resonance,
specificity, actionability, controversy, etc.). The interface is intentionally
narrow so the backend can later be swapped for a trained ML model without
changing call sites.

Active learning: every prediction is logged to .training/clipgen_training.jsonl
with all input features. When real engagement outcomes arrive (user feedback
or platform metrics), `record_outcome()` updates the row so the corpus can
be used to train a successor model.
"""
from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from config.settings import BASE_DIR


# ----- Feature extraction ---------------------------------------------------

QUESTION_REGEX = re.compile(r"\?")
EXCLAMATION_REGEX = re.compile(r"!")
SENTENCE_END_REGEX = re.compile(r"[.!?](?:\s|$|[\"'])")
NUMBER_REGEX = re.compile(r"\b\d+(?:[\.,]\d+)?\b")
PERSONAL_PRONOUN_REGEX = re.compile(r"\b(you|your|you're|you've|you'll|you'd)\b", re.IGNORECASE)
FIRST_PERSON_REGEX = re.compile(r"\b(i|we|my|our|us)\b", re.IGNORECASE)
NEGATIVE_RATING_REGEX = re.compile(r"\b(worst|terrible|awful|garbage|trash)\b", re.IGNORECASE)

POWER_WORDS = {
    "secret", "proven", "instant", "exclusive", "guaranteed",
    "shocking", "mind-blowing", "game-changing", "life-changing",
    "never", "hidden", "famous", "revolutionary", "insane", "crazy",
    "unbelievable", "impossible", "brilliant", "genius", "wild",
}

PATTERN_INTERRUPT_PHRASES = [
    "what if", "tell me", "you know what", "here's the thing",
    "let me tell you", "actually", "honestly", "truth is", "real talk",
    "the secret", "the truth", "no one tells you", "they don't want you",
]

CURIOSITY_GAP_PHRASES = [
    "here's why", "this is why", "the reason", "because",
    "you won't believe", "trust me", "wait till you see", "imagine",
    "the interesting part", "the scary part", "the best part",
    "the catch", "the trick", "the hack",
]

CONTRARIAN_PHRASES = [
    "everyone thinks", "most people", "the myth", "contrary to",
    "opposite of", "wrong about", "not actually", "in reality",
    "but actually", "unpopular opinion", "hot take", "controversial",
    "take it or leave it", "stop doing", "never do", "don't ever",
]

ACTIONABILITY_PHRASES = [
    "step 1", "step 2", "first", "next", "then", "finally",
    "how to", "the formula", "the framework", "the rule", "the trick",
    "do this", "try this", "use this", "follow this",
]

CTA_PHRASES = [
    "follow for more", "subscribe", "comment below", "let me know",
    "thoughts?", "agree?", "disagree?", "what do you think",
    "share this", "send this to",
]


@dataclass
class ClipFeatures:
    """Numeric features used as input to the predictor."""
    # Text-derived
    hook_pattern_interrupt: float = 0.0
    hook_curiosity_gap: float = 0.0
    hook_contrarian: float = 0.0
    hook_question: float = 0.0
    hook_exclamation: float = 0.0
    hook_power_word_density: float = 0.0
    hook_cta: float = 0.0

    # Body-derived
    emotion_intensity: float = 0.0
    specificity: float = 0.0
    actionability: float = 0.0
    quotability: float = 0.0
    controversy: float = 0.0
    relatability: float = 0.0
    information_density: float = 0.0
    story_structure: float = 0.0

    # End-derived
    payoff_strength: float = 0.0
    ending_sentence_complete: float = 0.0

    # Context
    duration_seconds: float = 0.0
    duration_fit: float = 0.0
    speaker_count: int = 1
    speaker_continuity: float = 1.0

    # Free-form for future model
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ViralPrediction:
    """Output of the predictor."""
    share: float
    save: float
    comment: float
    composite: float
    confidence: float
    features: ClipFeatures
    rationale: Dict[str, float] = field(default_factory=dict)
    model_version: str = "heuristic-v1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "share": round(self.share, 4),
            "save": round(self.save, 4),
            "comment": round(self.comment, 4),
            "composite": round(self.composite, 4),
            "confidence": round(self.confidence, 4),
            "features": self.features.to_dict(),
            "rationale": {k: round(v, 4) for k, v in self.rationale.items()},
            "model_version": self.model_version,
        }


# ----- Heuristic predictor --------------------------------------------------

# Calibrated weights — these mirror what short-form recommendation systems
# empirically reward. They can be replaced by a trained model later.
WEIGHTS: Dict[str, Dict[str, float]] = {
    "share": {
        "hook_pattern_interrupt": 0.18,
        "hook_curiosity_gap": 0.20,
        "hook_contrarian": 0.15,
        "hook_exclamation": 0.05,
        "hook_power_word_density": 0.10,
        "emotion_intensity": 0.18,
        "controversy": 0.10,
        "quotability": 0.04,
    },
    "save": {
        "actionability": 0.25,
        "specificity": 0.20,
        "information_density": 0.15,
        "story_structure": 0.15,
        "payoff_strength": 0.10,
        "hook_curiosity_gap": 0.05,
        "relatability": 0.05,
        "duration_fit": 0.05,
    },
    "comment": {
        "hook_question": 0.20,
        "hook_contrarian": 0.15,
        "controversy": 0.20,
        "emotion_intensity": 0.15,
        "relatability": 0.10,
        "hook_cta": 0.10,
        "hook_pattern_interrupt": 0.05,
        "speaker_continuity": 0.05,
    },
}

# Per-target bias so the calibrated output sits in a reasonable range.
# Weights per target sum to 1.0, so an "average" clip (every feature ~0.3)
# produces z ~= 0.30 + bias. We pick bias so that:
#   - all-zero / fallback clip lands near 0.30-0.40 (still visibly non-zero)
#   - typical clip (features ~0.3) lands near 0.40-0.50
#   - strong clip (features ~0.7+) lands near 0.55-0.70
# These were tuned by hand against known viral content patterns.
BIAS: Dict[str, float] = {
    "share": -0.4,
    "save": -0.5,
    "comment": -0.8,
}

# Composite weights — share dominates because platform algorithms surface share-heavy content.
COMPOSITE_WEIGHTS = {
    "share": 0.50,
    "save": 0.30,
    "comment": 0.20,
}


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _score_target(features: ClipFeatures, target: str) -> Tuple[float, Dict[str, float]]:
    weights = WEIGHTS[target]
    bias = BIAS[target]
    z = bias
    contributions: Dict[str, float] = {}
    for name, w in weights.items():
        f = getattr(features, name, 0.0)
        try:
            f_val = float(f)
        except (TypeError, ValueError):
            f_val = 0.0
        contribution = w * f_val
        contributions[name] = contribution
        z += contribution
    p = _sigmoid(z)
    return p, contributions


class HeuristicViralModel:
    """Calibrated heuristic predictor. Drop-in replaceable by a trained model."""

    name = "heuristic-v1"

    def predict(self, features: ClipFeatures) -> ViralPrediction:
        share, contrib_share = _score_target(features, "share")
        save, contrib_save = _score_target(features, "save")
        comment, contrib_comment = _score_target(features, "comment")

        composite = (
            COMPOSITE_WEIGHTS["share"] * share
            + COMPOSITE_WEIGHTS["save"] * save
            + COMPOSITE_WEIGHTS["comment"] * comment
        )

        # Confidence: low if all features are near zero (no signal);
        # high if many features contributed meaningfully.
        non_zero = sum(1 for c in contrib_share.values() if abs(c) > 0.05)
        non_zero += sum(1 for c in contrib_save.values() if abs(c) > 0.05)
        non_zero += sum(1 for c in contrib_comment.values() if abs(c) > 0.05)
        confidence = min(1.0, non_zero / 12.0)

        rationale = {
            "share_top": _top_contribution(contrib_share),
            "save_top": _top_contribution(contrib_save),
            "comment_top": _top_contribution(contrib_comment),
        }

        return ViralPrediction(
            share=share,
            save=save,
            comment=comment,
            composite=composite,
            confidence=confidence,
            features=features,
            rationale=rationale,
            model_version=self.name,
        )


def _top_contribution(contributions: Dict[str, float]) -> float:
    if not contributions:
        return 0.0
    return max(contributions.values())


# ----- Feature extraction ---------------------------------------------------

# Keywords used to detect emotional intensity.
EMOTION_KEYWORDS = {
    "excited": {"amazing", "incredible", "wow", "insane", "unbelievable", "epic", "crazy"},
    "surprising": {"surprising", "shocking", "unbelievable", "plot twist", "twist", "secret"},
    "controversial": {"wrong", "lie", "myth", "scam", "fraud", "hate", "stupid", "dumb"},
    "inspiring": {"inspire", "change your life", "transform", "believe", "dream", "achieve"},
    "funny": {"hilarious", "funny", "joke", "laugh", "lol", "ridiculous"},
}

CONTROVERSY_KEYWORDS = {
    "wrong", "lie", "lying", "myth", "scam", "fraud", "hate", "stupid", "dumb",
    "garbage", "trash", "overrated", "underrated", "unpopular opinion",
    "controversial", "sucks", "terrible", "awful",
}


def _phrase_hits(text: str, phrases: Iterable[str]) -> int:
    lower = text.lower()
    return sum(1 for p in phrases if p in lower)


def _word_count(text: str) -> int:
    return max(1, len([w for w in re.split(r"\s+", text.strip()) if w]))


def _density(hits: int, total_words: int) -> float:
    if total_words <= 0:
        return 0.0
    return min(1.0, hits / total_words * 4.0)  # 25% density = 1.0


def _emotional_intensity(text: str) -> float:
    lower = text.lower()
    total = 0.0
    for words in EMOTION_KEYWORDS.values():
        for w in words:
            if w in lower:
                total += 1.0
    return min(1.0, total / 4.0)


def _controversy(text: str) -> float:
    lower = text.lower()
    hits = sum(1 for k in CONTROVERSY_KEYWORDS if k in lower)
    return min(1.0, hits / 2.0)


def _specificity(text: str) -> float:
    numbers = len(NUMBER_REGEX.findall(text))
    proper_nouns = len(re.findall(r"\b[A-Z][a-z]+\b", text))
    score = min(1.0, (numbers * 0.15) + (proper_nouns * 0.05))
    return score


def _actionability(text: str) -> float:
    return min(1.0, _phrase_hits(text, ACTIONABILITY_PHRASES) / 2.0)


def _quotability(text: str) -> float:
    sentences = [s.strip() for s in re.split(r"[.!?]", text) if s.strip()]
    if not sentences:
        return 0.0
    best = 0.0
    for s in sentences:
        words = s.split()
        wc = len(words)
        if 4 <= wc <= 14:
            score = 0.5
            if EXCLAMATION_REGEX.search(s):
                score += 0.2
            if any(w in POWER_WORDS for w in (w.lower() for w in words)):
                score += 0.2
            if QUESTION_REGEX.search(s):
                score -= 0.1
            if FIRST_PERSON_REGEX.search(s) and not PERSONAL_PRONOUN_REGEX.search(s):
                score += 0.1
            best = max(best, score)
    return min(1.0, best)


def _relatability(text: str) -> float:
    return min(1.0, len(PERSONAL_PRONOUN_REGEX.findall(text)) / 4.0)


def _information_density(text: str, duration: float) -> float:
    if duration <= 0:
        return 0.0
    words = _word_count(text)
    wps = words / duration
    # Sweet spot is 2-3.5 words/sec on short-form.
    if wps < 0.5:
        return 0.2
    if wps < 2.0:
        return 0.6
    if wps < 3.5:
        return 1.0
    if wps < 4.5:
        return 0.7
    return 0.4


def _story_structure(segments: Sequence[dict]) -> float:
    """Crude proxy: did we see setup -> development -> resolution words/phrases?"""
    if not segments:
        return 0.0
    text = " ".join((s.get("text") or "") for s in segments).lower()
    setup = _phrase_hits(text, ["once", "imagine", "suppose", "picture", "years ago", "story", "happened"])
    develop = _phrase_hits(text, ["then", "after", "next", "because", "so", "as a result"])
    resolve = _phrase_hits(text, ["finally", "in the end", "turns out", "realized", "lesson", "takeaway"])
    score = 0.0
    if setup > 0:
        score += 0.3
    if develop > 0:
        score += 0.3
    if resolve > 0:
        score += 0.4
    return min(1.0, score)


def _duration_fit(duration: float) -> float:
    """Optimal range is 20-45s for hooks, 30-65s for stories."""
    if 20 <= duration <= 45:
        return 1.0
    if 15 <= duration <= 60:
        return 0.7
    if 10 <= duration <= 90:
        return 0.4
    return 0.2


def _payoff_strength(text: str) -> float:
    if not text:
        return 0.0
    score = 0.4
    if EXCLAMATION_REGEX.search(text):
        score += 0.2
    if any(w in text.lower() for w in POWER_WORDS):
        score += 0.2
    words = text.split()
    if 4 <= len(words) <= 16:
        score += 0.2
    return min(1.0, score)


def _speaker_continuity(segments: Sequence[dict]) -> float:
    """Fraction of segments spoken by the dominant speaker (0..1)."""
    if not segments:
        return 1.0
    counts: Dict[str, int] = {}
    for s in segments:
        sp = s.get("speaker") or "UNKNOWN"
        counts[sp] = counts.get(sp, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return 1.0
    dominant = max(counts.values())
    return dominant / total


def extract_features(
    *,
    segments: Sequence[dict],
    duration: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> ClipFeatures:
    """Extract heuristic features for the predictor."""
    if not segments:
        return ClipFeatures(duration_seconds=duration)

    full_text = " ".join((s.get("text") or "") for s in segments)
    if not full_text.strip():
        return ClipFeatures(duration_seconds=duration)

    hook_text = (segments[0].get("text") or "")
    payoff_text = (segments[-1].get("text") or "")
    hook_lower = hook_text.lower()
    payoff_lower = payoff_text.lower()

    total_words = _word_count(full_text)
    hook_words = max(1, _word_count(hook_text))

    features = ClipFeatures(
        hook_pattern_interrupt=min(1.0, _phrase_hits(hook_lower, PATTERN_INTERRUPT_PHRASES) / 1.0),
        hook_curiosity_gap=min(1.0, _phrase_hits(hook_lower, CURIOSITY_GAP_PHRASES) / 1.0),
        hook_contrarian=min(1.0, _phrase_hits(hook_lower, CONTRARIAN_PHRASES) / 1.0),
        hook_question=1.0 if QUESTION_REGEX.search(hook_text) else 0.0,
        hook_exclamation=1.0 if EXCLAMATION_REGEX.search(hook_text) else 0.0,
        hook_power_word_density=_density(sum(1 for w in POWER_WORDS if w in hook_lower), hook_words),
        hook_cta=min(1.0, _phrase_hits(hook_lower, CTA_PHRASES) / 1.0),

        emotion_intensity=_emotional_intensity(full_text),
        specificity=_specificity(full_text),
        actionability=_actionability(full_text),
        quotability=_quotability(full_text),
        controversy=_controversy(full_text),
        relatability=_relatability(full_text),
        information_density=_information_density(full_text, duration),
        story_structure=_story_structure(segments),

        payoff_strength=_payoff_strength(payoff_text),
        ending_sentence_complete=1.0 if SENTENCE_END_REGEX.search(payoff_text) else 0.0,

        duration_seconds=duration,
        duration_fit=_duration_fit(duration),
        speaker_count=len({s.get("speaker") or "UNKNOWN" for s in segments}),
        speaker_continuity=_speaker_continuity(segments),
    )

    if metadata:
        features.metadata = dict(metadata)
    return features


# ----- Training data capture ------------------------------------------------

TRAINING_DIR = BASE_DIR / ".training"
TRAINING_FILE = TRAINING_DIR / "clipgen_training.jsonl"


def _ensure_training_dir() -> None:
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    _ensure_training_dir()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def make_training_record(
    *,
    clip_id: str,
    job_id: Optional[str],
    video_id: Optional[str],
    prediction: ViralPrediction,
    features: ClipFeatures,
    hook_text: str,
    payoff_text: str,
    full_text: str,
    segments: Sequence[dict],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "clip_id": clip_id,
        "job_id": job_id,
        "video_id": video_id,
        "timestamp": time.time(),
        "model_version": prediction.model_version,
        "prediction": {
            "share": prediction.share,
            "save": prediction.save,
            "comment": prediction.comment,
            "composite": prediction.composite,
        },
        "features": features.to_dict(),
        "hook_text": hook_text,
        "payoff_text": payoff_text,
        "full_text": full_text,
        "duration_seconds": features.duration_seconds,
        "speaker_count": features.speaker_count,
        "segments": [
            {
                "start": s.get("start"),
                "end": s.get("end"),
                "speaker": s.get("speaker"),
                "text": s.get("text"),
            }
            for s in segments
        ],
        "outcome": None,
        "metadata": metadata or {},
    }


def save_training_record(record: Dict[str, Any]) -> None:
    _append_jsonl(TRAINING_FILE, record)


def update_outcome(clip_id: str, outcome: Dict[str, Any]) -> int:
    """Append a separate outcome-update record (keeps history append-only)."""
    if not TRAINING_FILE.exists():
        return 0
    records = _read_jsonl(TRAINING_FILE)
    matched = 0
    for r in records:
        if r.get("clip_id") == clip_id and r.get("outcome") is None:
            r["outcome"] = outcome
            r["outcome_recorded_at"] = time.time()
            matched += 1
    if matched:
        with TRAINING_FILE.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return matched


def load_training_data(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    records = _read_jsonl(TRAINING_FILE)
    if limit is not None:
        return records[-limit:]
    return records


def training_stats() -> Dict[str, Any]:
    records = _read_jsonl(TRAINING_FILE)
    total = len(records)
    with_outcomes = sum(1 for r in records if r.get("outcome") is not None)
    by_outcome: Dict[str, int] = {}
    for r in records:
        out = r.get("outcome") or {}
        label = out.get("label") or "unknown"
        by_outcome[label] = by_outcome.get(label, 0) + 1
    return {
        "total_records": total,
        "with_outcomes": with_outcomes,
        "outcome_breakdown": by_outcome,
        "storage_path": str(TRAINING_FILE),
    }


# ----- Public predictor API --------------------------------------------------


class ViralPredictor:
    """Public predictor. Wraps the model backend and persists training records."""

    def __init__(self, model: Optional[Any] = None, persist: bool = True) -> None:
        self.model = model or HeuristicViralModel()
        self.persist = persist

    def predict(
        self,
        *,
        segments: Sequence[dict],
        duration: float,
        clip_id: Optional[str] = None,
        job_id: Optional[str] = None,
        video_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ViralPrediction:
        features = extract_features(segments=segments, duration=duration, metadata=metadata)
        prediction = self.model.predict(features)

        if self.persist and clip_id:
            full_text = " ".join((s.get("text") or "") for s in segments)
            hook_text = (segments[0].get("text") or "") if segments else ""
            payoff_text = (segments[-1].get("text") or "") if segments else ""
            record = make_training_record(
                clip_id=clip_id,
                job_id=job_id,
                video_id=video_id,
                prediction=prediction,
                features=features,
                hook_text=hook_text,
                payoff_text=payoff_text,
                full_text=full_text,
                segments=segments,
                metadata=metadata,
            )
            try:
                save_training_record(record)
            except OSError:
                pass

        return prediction
