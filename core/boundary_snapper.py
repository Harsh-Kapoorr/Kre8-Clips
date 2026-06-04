"""
Smart boundary detection for clips.

Combines four signals to land cuts on natural moments:
  1. Audio pauses (silence/quiet valleys)  — existing librosa analysis
  2. Sentence completion                    — transcript punctuation
  3. Speaker switches                      — natural conversational breaks
  4. Hook/payoff landing                    — semantic strength at candidate time

Returns a ranked list of candidate boundary points with confidence scores,
so callers can pick the best start/end near a requested timestamp.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple


SENTENCE_END_CHARS = ".!?"
SENTENCE_END_REGEX = re.compile(r"[.!?](?:\s|$|[\"'])")
CLAUSE_BREAK_REGEX = re.compile(r"[,;:](?:\s|$)")
QUESTION_REGEX = re.compile(r"\?")
EXCLAMATION_REGEX = re.compile(r"!")
SENTENCE_START_REGEX = re.compile(r"^[A-Z\[\(\"']")


@dataclass
class BoundaryCandidate:
    """A candidate cut point with multi-signal scoring."""
    time: float
    audio_pause_score: float = 0.0
    sentence_complete_score: float = 0.0
    speaker_change_score: float = 0.0
    hook_score: float = 0.0
    payoff_score: float = 0.0
    composite: float = 0.0
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.reason:
            self.reason = self._build_reason()

    def _build_reason(self) -> str:
        bits = []
        if self.sentence_complete_score >= 0.7:
            bits.append("sentence end")
        if self.audio_pause_score >= 0.6:
            bits.append("audio pause")
        if self.speaker_change_score >= 0.7:
            bits.append("speaker change")
        if self.hook_score >= 0.7:
            bits.append("strong start")
        if self.payoff_score >= 0.7:
            bits.append("strong end")
        return ", ".join(bits) or "proximity match"


@dataclass
class SnapResult:
    """Result of snapping a single segment boundary."""
    original_time: float
    snapped_time: float
    delta: float
    confidence: float
    candidate: BoundaryCandidate
    snapped: bool


def _parse_timestamp(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        parts = value.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
        except ValueError:
            return 0.0
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _audio_pause_score(time: float, beat_pauses: Sequence[float], tolerance: float) -> float:
    """1.0 if at an exact pause, falling off linearly within tolerance."""
    if not beat_pauses:
        return 0.0
    nearest = min(beat_pauses, key=lambda p: abs(p - time), default=None)
    if nearest is None:
        return 0.0
    delta = abs(nearest - time)
    if delta > tolerance:
        return 0.0
    return max(0.0, 1.0 - (delta / tolerance))


def _sentence_complete_score(
    time: float,
    segments: Sequence[dict],
    direction: str,
) -> float:
    """1.0 if a sentence ends within 0.5s of the candidate time in the search direction.

    For direction "after" (the start of a new clip), we also credit the
    beginning of a sentence near the candidate — that is the natural place
    to open a clip cleanly without mid-sentence tails.
    """
    if direction == "after":
        best = 0.0
        for seg in segments:
            seg_start = _parse_timestamp(seg.get("start", 0))
            seg_end = _parse_timestamp(seg.get("end", seg_start))
            if seg_start > time + 1.0:
                break
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            if seg_start <= time <= seg_end + 0.5:
                if SENTENCE_END_REGEX.search(text):
                    distance = max(0.0, seg_end - time)
                    best = max(best, max(0.4, 1.0 - min(1.0, distance / 0.8)))
                elif CLAUSE_BREAK_REGEX.search(text):
                    best = max(best, 0.5)
            if abs(seg_start - time) <= 0.6 and seg_start >= time - 0.1:
                if SENTENCE_START_REGEX.match(text):
                    delta = abs(seg_start - time)
                    best = max(best, max(0.6, 1.0 - min(1.0, delta / 0.6)))
        return best
    else:
        for seg in segments:
            seg_start = _parse_timestamp(seg.get("start", 0))
            seg_end = _parse_timestamp(seg.get("end", seg_start))
            if seg_end < time - 1.0:
                continue
            if seg_start - 0.5 <= time <= seg_end:
                text = (seg.get("text") or "").strip()
                if not text:
                    continue
                if SENTENCE_END_REGEX.search(text):
                    return 0.9
                if CLAUSE_BREAK_REGEX.search(text):
                    return 0.6
    return 0.0


def _speaker_change_score(time: float, segments: Sequence[dict]) -> float:
    """1.0 if a speaker change happens within 0.4s of the candidate time."""
    last_speaker: Optional[str] = None
    for seg in segments:
        seg_start = _parse_timestamp(seg.get("start", 0))
        seg_end = _parse_timestamp(seg.get("end", seg_start))
        if seg_end < time - 0.4:
            last_speaker = seg.get("speaker")
            continue
        if seg_start > time + 0.4:
            break
        speaker = seg.get("speaker")
        if speaker and last_speaker and speaker != last_speaker:
            return 1.0
        last_speaker = speaker
    return 0.0


def _hook_score(time: float, segments: Sequence[dict]) -> float:
    """Heuristic hook strength at the candidate start time (3s window)."""
    from core.virality import ViralityAnalyzer

    analyzer = ViralityAnalyzer()
    window_end = time + 3.0
    for seg in segments:
        seg_start = _parse_timestamp(seg.get("start", 0))
        seg_end = _parse_timestamp(seg.get("end", seg_start))
        if seg_end < time:
            continue
        if seg_start > window_end:
            break
        text = (seg.get("text") or "").lower()
        if not text:
            continue
        score = 5.0
        for pattern in analyzer.PATTERN_INTERRUPT_PATTERNS:
            if re.search(pattern, text):
                score = max(score, 8.5)
        for pattern in analyzer.CURIOSITY_GAP_PATTERNS:
            if re.search(pattern, text):
                score = max(score, 8.0)
        for pattern in analyzer.CONTRARIAN_PATTERNS:
            if re.search(pattern, text):
                score = max(score, 8.0)
        for word in analyzer.POWER_WORDS:
            if word in text:
                score = max(score, 7.5)
        if QUESTION_REGEX.search(text):
            score = max(score, 7.0)
        if EXCLAMATION_REGEX.search(text):
            score = max(score, 7.0)
        return min(10.0, score) / 10.0
    return 0.3


def _payoff_score(time: float, segments: Sequence[dict]) -> float:
    """Heuristic payoff strength at the candidate end time (5s window back)."""
    from core.virality import ViralityAnalyzer

    analyzer = ViralityAnalyzer()
    window_start = time - 5.0
    best = 0.0
    for seg in segments:
        seg_start = _parse_timestamp(seg.get("start", 0))
        seg_end = _parse_timestamp(seg.get("end", seg_start))
        if seg_end < window_start:
            continue
        if seg_start > time:
            break
        text = (seg.get("text") or "").lower()
        if not text:
            continue
        score = 5.0
        if EXCLAMATION_REGEX.search(text):
            score = max(score, 8.0)
        for word in analyzer.POWER_WORDS:
            if word in text:
                score = max(score, 7.5)
        word_count = len(text.split())
        if 5 <= word_count <= 18:
            score += 0.5
        if SENTENCE_END_REGEX.search(text):
            score += 0.5
        best = max(best, score)
    return min(10.0, best) / 10.0


def _build_candidate(
    time: float,
    beat_pauses: Sequence[float],
    segments: Sequence[dict],
    direction: str,
    tolerance: float,
) -> BoundaryCandidate:
    audio = _audio_pause_score(time, beat_pauses, tolerance)
    sentence = _sentence_complete_score(time, segments, direction)
    speaker = _speaker_change_score(time, segments)
    if direction == "after":
        hook = _hook_score(time, segments)
        payoff = 0.0
    else:
        hook = 0.0
        payoff = _payoff_score(time, segments)

    composite = (
        0.20 * audio
        + 0.50 * sentence
        + 0.15 * speaker
        + 0.10 * hook
        + 0.05 * payoff
    )
    if direction == "after":
        composite += 0.05 * hook - 0.05 * payoff
    else:
        composite += 0.05 * payoff - 0.05 * hook
    composite = max(0.0, min(1.0, composite))

    return BoundaryCandidate(
        time=time,
        audio_pause_score=audio,
        sentence_complete_score=sentence,
        speaker_change_score=speaker,
        hook_score=hook,
        payoff_score=payoff,
        composite=composite,
    )


def _candidate_times(
    target: float,
    beat_pauses: Sequence[float],
    sentence_anchors: Sequence[float],
    speaker_anchors: Sequence[float],
    tolerance: float,
) -> List[float]:
    seen = set()
    times: List[float] = []

    def _add(t: float) -> None:
        if t is None:
            return
        key = round(t, 2)
        if key in seen:
            return
        seen.add(key)
        times.append(t)

    for p in beat_pauses:
        if abs(p - target) <= tolerance:
            _add(p)
    for s in sentence_anchors:
        if abs(s - target) <= tolerance:
            _add(s)
    for sp in speaker_anchors:
        if abs(sp - target) <= tolerance:
            _add(sp)
    _add(target)
    return times


def _collect_sentence_anchors(segments: Sequence[dict]) -> List[float]:
    anchors: List[float] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if SENTENCE_END_REGEX.search(text):
            end_time = _parse_timestamp(seg.get("end", 0))
            anchors.append(float(end_time))
    return anchors


def _collect_speaker_anchors(segments: Sequence[dict]) -> List[float]:
    anchors: List[float] = []
    last_speaker: Optional[str] = None
    for seg in segments:
        seg_start = _parse_timestamp(seg.get("start", 0))
        speaker = seg.get("speaker")
        if speaker and last_speaker and speaker != last_speaker:
            anchors.append(float(seg_start))
        last_speaker = speaker
    return anchors


class SmartBoundarySnapper:
    """Snap requested cut times to natural boundaries using multi-signal scoring."""

    def __init__(
        self,
        beat_pauses: Optional[Sequence[float]] = None,
        transcript_segments: Optional[Sequence[dict]] = None,
        tolerance: float = 0.6,
    ) -> None:
        self.beat_pauses = list(beat_pauses or [])
        self.transcript_segments = list(transcript_segments or [])
        self.tolerance = tolerance
        self.sentence_anchors = _collect_sentence_anchors(self.transcript_segments)
        self.speaker_anchors = _collect_speaker_anchors(self.transcript_segments)

    def candidates_for_time(
        self, time: float, direction: str = "after"
    ) -> List[BoundaryCandidate]:
        candidates = _candidate_times(
            time,
            self.beat_pauses,
            self.sentence_anchors,
            self.speaker_anchors,
            self.tolerance,
        )
        out: List[BoundaryCandidate] = []
        for t in candidates:
            out.append(
                _build_candidate(
                    t,
                    self.beat_pauses,
                    self.transcript_segments,
                    direction,
                    self.tolerance,
                )
            )
        out.sort(key=lambda c: c.composite, reverse=True)
        return out

    def best_boundary(
        self, target: float, direction: str = "after"
    ) -> SnapResult:
        candidates = self.candidates_for_time(target, direction)
        best_score = candidates[0].composite if candidates else 0.0
        if not candidates or best_score < 0.3:
            fallback_tolerance = max(2.0, self.tolerance * 3.5)
            fallback = _candidate_times(
                target,
                self.beat_pauses,
                self.sentence_anchors,
                self.speaker_anchors,
                fallback_tolerance,
            )
            for t in fallback:
                candidates.append(
                    _build_candidate(
                        t,
                        self.beat_pauses,
                        self.transcript_segments,
                        direction,
                        fallback_tolerance,
                    )
                )
            candidates.sort(key=lambda c: c.composite, reverse=True)
        if not candidates:
            return SnapResult(
                original_time=target,
                snapped_time=target,
                delta=0.0,
                confidence=0.0,
                candidate=BoundaryCandidate(time=target),
                snapped=False,
            )
        best = candidates[0]
        snapped_time = best.time
        delta = abs(snapped_time - target)
        snapped = delta > 0.05
        confidence = best.composite * max(0.4, 1.0 - min(1.0, delta / self.tolerance))
        return SnapResult(
            original_time=target,
            snapped_time=snapped_time,
            delta=delta,
            confidence=confidence,
            candidate=best,
            snapped=snapped,
        )

    def snap_segment(
        self,
        start: float,
        end: float,
        min_duration: float = 1.0,
        max_duration: Optional[float] = None,
    ) -> dict:
        start_snap = self.best_boundary(start, direction="after")
        end_snap = self.best_boundary(end, direction="before")

        snapped_start = start_snap.snapped_time
        snapped_end = end_snap.snapped_time
        if snapped_end - snapped_start < min_duration:
            if start_snap.candidate.composite >= end_snap.candidate.composite:
                snapped_end = max(snapped_start + min_duration, snapped_end)
            else:
                snapped_start = min(snapped_end - min_duration, snapped_start)
        if max_duration is not None and snapped_end - snapped_start > max_duration:
            mid = (snapped_start + snapped_end) / 2
            snapped_start = mid - max_duration / 2
            snapped_end = mid + max_duration / 2

        confidence = (start_snap.confidence + end_snap.confidence) / 2
        return {
            "start": snapped_start,
            "end": snapped_end,
            "start_confidence": start_snap.confidence,
            "end_confidence": end_snap.confidence,
            "confidence": confidence,
            "start_reason": start_snap.candidate.reason,
            "end_reason": end_snap.candidate.reason,
            "start_snapped": start_snap.snapped,
            "end_snapped": end_snap.snapped,
        }
