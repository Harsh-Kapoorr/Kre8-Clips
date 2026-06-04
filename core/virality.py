"""
Virality optimization - hook detection, beat pauses, virality scoring.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np

# Check if librosa is available for audio analysis
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False


@dataclass
class HookDetection:
    """Detected hook in a segment."""
    start_time: float
    end_time: float
    hook_type: str  # "pattern_interrupt", "curiosity_gap", "contrarian", "energy_spike"
    confidence: float
    text_evidence: str


@dataclass
class ViralityScore:
    """Virality scoring for a clip."""
    hook_score: int  # 1-10
    quote_potential: str  # Quotable line if any
    emotional_tone: str  # "excited", "controversial", "inspiring", etc.
    suggested_cta: str  # Optional CTA text
    beat_pauses: List[float]  # Timestamps of natural cut points


class ViralityAnalyzer:
    """Analyzes content for virality potential."""

    # Hook patterns
    PATTERN_INTERRUPT_PATTERNS = [
        r"\b(what if|tell me|you know what|here's the thing|let me tell you)\b",
        r"\b(actually|honestly|truth is|real talk)\b",
        r"\b(the secret|the truth|no one tells you|they don't want you)\b",
    ]

    CURIOSITY_GAP_PATTERNS = [
        r"\b(but what if|here's why|this is why|the reason|because)\b",
        r"\b(you won't believe|trust me|wait till you see|imagine)\b",
        r"\b(the interesting part|the scary part|the best part)\b",
    ]

    CONTRARIAN_PATTERNS = [
        r"\b(everyone thinks|most people|the myth|contrary to|opposite of)\b",
        r"\b(wrong about|not actually|in reality|but actually|here's the thing)\b",
        r"\b(unpopular opinion|hot take|controversial|take it or leave it)\b",
    ]

    POWER_WORDS = [
        "secret", "proven", "instant", "exclusive", "guaranteed",
        "shocking", "mind-blowing", "game-changing", "life-changing",
        "never told", "hidden", "famous", "revolutionary"
    ]

    CTA_PATTERNS = [
        r"\b(follow|subscribe|like|comment|share|check out)\b",
        r"\b(if you want|learn more|get started|take action)\b",
    ]

    def __init__(self):
        self._hooks: List[HookDetection] = []
        self._beat_pauses: List[float] = []

    def detect_hooks(self, transcript_segments: List[dict]) -> List[HookDetection]:
        """Detect hook patterns in transcript.

        Args:
            transcript_segments: List of {start, end, text, speaker}

        Returns:
            List of HookDetection objects
        """
        hooks = []

        for seg in transcript_segments:
            text = seg.get("text", "").lower()
            start = seg.get("start", 0)

            # Check for pattern interrupt
            for pattern in self.PATTERN_INTERRUPT_PATTERNS:
                if re.search(pattern, text):
                    hooks.append(HookDetection(
                        start_time=start,
                        end_time=start + 3.0,
                        hook_type="pattern_interrupt",
                        confidence=0.8,
                        text_evidence=text[:100]
                    ))
                    break

            # Check for curiosity gaps
            for pattern in self.CURIOSITY_GAP_PATTERNS:
                if re.search(pattern, text):
                    hooks.append(HookDetection(
                        start_time=start,
                        end_time=start + 3.0,
                        hook_type="curiosity_gap",
                        confidence=0.75,
                        text_evidence=text[:100]
                    ))
                    break

            # Check for contrarian statements
            for pattern in self.CONTRARIAN_PATTERNS:
                if re.search(pattern, text):
                    hooks.append(HookDetection(
                        start_time=start,
                        end_time=start + 3.0,
                        hook_type="contrarian",
                        confidence=0.7,
                        text_evidence=text[:100]
                    ))
                    break

        # Sort by confidence
        hooks.sort(key=lambda h: h.confidence, reverse=True)
        self._hooks = hooks
        return hooks

    def find_beat_pauses(
        self,
        audio_path: str,
        min_pause_duration: float = 0.3
    ) -> List[float]:
        """Find natural pause points in audio for smart cutting.

        Args:
            audio_path: Path to audio file
            min_pause_duration: Minimum pause duration in seconds

        Returns:
            List of pause timestamps
        """
        if not LIBROSA_AVAILABLE:
            # Return empty if librosa not available
            return []

        try:
            # Load audio
            y, sr = librosa.load(audio_path, sr=16000)

            # Compute RMS energy
            frame_length = int(sr * 0.05)  # 50ms frames
            hop_length = int(sr * 0.01)  # 10ms hop

            rms = librosa.feature.rms(
                y=y,
                frame_length=frame_length,
                hop_length=hop_length
            )[0]

            # Find valleys (pauses) below threshold
            threshold = np.percentile(rms, 20)  # Bottom 20%

            # Find continuous regions below threshold
            pauses = []
            in_pause = False
            pause_start = 0

            for i, energy in enumerate(rms):
                time = i * hop_length / sr

                if energy < threshold:
                    if not in_pause:
                        in_pause = True
                        pause_start = time
                else:
                    if in_pause:
                        pause_duration = time - pause_start
                        if pause_duration >= min_pause_duration:
                            # Add the center of the pause
                            pauses.append(pause_start + pause_duration / 2)
                        in_pause = False

            self._beat_pauses = pauses
            return pauses

        except Exception as e:
            print(f"Warning: Could not analyze audio for beat pauses: {e}")
            return []

    def snap_to_nearest_pause(
        self,
        beat_pauses: List[float],
        timestamp: float,
        tolerance: float = 0.4,
    ) -> float:
        """Snap a timestamp to the nearest beat pause within tolerance.

        Args:
            beat_pauses: List of pause center timestamps from find_beat_pauses()
            timestamp: The original timestamp to snap
            tolerance: Max distance (seconds) to snap — if nearest pause is beyond this, return original

        Returns:
            Snapped timestamp if within tolerance, otherwise original timestamp
        """
        if not beat_pauses:
            return timestamp
        nearest = min(beat_pauses, key=lambda p: abs(p - timestamp), default=timestamp)
        if abs(nearest - timestamp) <= tolerance:
            return nearest
        return timestamp

    def snap_boundaries_to_pauses(
        self,
        segments: List[dict],
        beat_pauses: List[float],
        tolerance: float = 0.4,
    ) -> List[dict]:
        """Snap all segment start/end boundaries to nearest beat pauses.

        Args:
            segments: List of dicts with 'start_seconds' and 'end_seconds' keys
            beat_pauses: List of pause center timestamps
            tolerance: Max snap distance in seconds

        Returns:
            Segments with snapped boundaries
        """
        snapped = []
        for seg in segments:
            new_seg = dict(seg)
            start = seg.get("start_seconds", seg.get("start", 0))
            end = seg.get("end_seconds", seg.get("end", 0))
            snapped_start = self.snap_to_nearest_pause(beat_pauses, start, tolerance)
            snapped_end = self.snap_to_nearest_pause(beat_pauses, end, tolerance)
            new_seg["start_seconds"] = snapped_start
            new_seg["end_seconds"] = snapped_end
            # Track if snapped for logging
            new_seg["_snapped"] = (
                abs(snapped_start - start) > 0.01 or abs(snapped_end - end) > 0.01
            )
            snapped.append(new_seg)
        return snapped

    def score_virality(
        self,
        transcript_segments: List[dict],
        start_time: float,
        end_time: float
    ) -> ViralityScore:
        """Score virality potential of a segment.

        Args:
            transcript_segments: Full transcript
            start_time, end_time: Segment time range

        Returns:
            ViralityScore object
        """
        # Get segment text
        segment_text = ""
        for seg in transcript_segments:
            if seg.get("start", 0) >= start_time - 1 and seg.get("end", 0) <= end_time + 1:
                segment_text += seg.get("text", "") + " "

        segment_text = segment_text.lower()

        # Calculate hook score
        hook_score = self._calculate_hook_score(segment_text, start_time, transcript_segments)

        # Find quote potential
        quote_potential = self._find_quote_potential(segment_text)

        # Determine emotional tone
        emotional_tone = self._analyze_emotional_tone(segment_text)

        # Find suggested CTA
        suggested_cta = self._find_cta_suggestion(segment_text)

        return ViralityScore(
            hook_score=hook_score,
            quote_potential=quote_potential,
            emotional_tone=emotional_tone,
            suggested_cta=suggested_cta,
            beat_pauses=self._beat_pauses
        )

    def _calculate_hook_score(
        self,
        segment_text: str,
        start_time: float,
        full_segments: list
    ) -> int:
        """Calculate hook score 1-10 based on opening strength."""
        score = 5  # Base score

        # Check if first segment has strong hook patterns
        first_segment_text = ""
        for seg in full_segments:
            if seg.get("start", 0) >= start_time - 0.5:
                first_segment_text = seg.get("text", "").lower()
                break

        if first_segment_text:
            # Pattern interrupt bonus
            for pattern in self.PATTERN_INTERRUPT_PATTERNS:
                if re.search(pattern, first_segment_text):
                    score += 2
                    break

            # Power word bonus
            power_word_count = sum(1 for word in self.POWER_WORDS if word in first_segment_text)
            score += min(power_word_count, 2)

            # Question bonus (engages viewer)
            if "?" in first_segment_text:
                score += 1

            # Long word bonus (sounds more authoritative)
            if len(first_segment_text.split()) > 8:
                score += 1

        return min(score, 10)

    def _find_quote_potential(self, segment_text: str) -> str:
        """Find quotable line in segment."""
        # Look for short, punchy statements
        sentences = re.split(r"[.!?]", segment_text)
        for sent in sentences:
            sent = sent.strip()
            # Quote-worthy: short, declarative, no hedging
            if 5 < len(sent.split()) < 15 and not any(
                w in sent for w in ["maybe", "perhaps", "might", "could", "probably"]
            ):
                if any(w in sent for w in ["is", "are", "will", "can", "did", "do"]):
                    return sent.strip()
        return ""

    def _analyze_emotional_tone(self, segment_text: str) -> str:
        """Analyze emotional tone of segment."""
        # Check for excitement markers
        excitement_words = ["amazing", "incredible", "unbelievable", "wow", "awesome", "fantastic"]
        if any(w in segment_text for w in excitement_words):
            return "excited"

        # Check for controversial markers
        controversial_words = ["wrong", "myth", "lie", "false", "actually", "contrary"]
        if any(w in segment_text for w in controversial_words):
            return "controversial"

        # Check for inspiring markers
        inspiring_words = ["can do it", "believe", "success", "achieve", "goal", "dream"]
        if any(w in segment_text for w in inspiring_words):
            return "inspiring"

        # Check for surprising markers
        surprising_words = ["surprising", "unexpected", "shocking", "wouldn't expect"]
        if any(w in segment_text for w in surprising_words):
            return "surprising"

        return "neutral"

    def _find_cta_suggestion(self, segment_text: str) -> str:
        """Find or suggest a CTA based on segment content."""
        # Look for existing CTAs
        for pattern in self.CTA_PATTERNS:
            match = re.search(pattern, segment_text)
            if match:
                # Return surrounding context
                start = max(0, match.start() - 20)
                end = min(len(segment_text), match.end() + 20)
                return segment_text[start:end].strip()

        # Suggest generic CTA based on content type
        if "how to" in segment_text or "tutorial" in segment_text:
            return "Follow for more tips like this"
        elif any(w in segment_text for w in ["secret", "reveal", "truth"]):
            return "Save this for later"
        else:
            return "Follow for more"

    def get_best_hook(self, transcript_segments: List[dict]) -> Optional[HookDetection]:
        """Get the best hook from transcript."""
        hooks = self.detect_hooks(transcript_segments)
        if hooks:
            return hooks[0]
        return None

    def recommend_clip_duration(
        self,
        segment_duration: float,
        content_type: str = "general"
    ) -> Tuple[float, float]:
        """Recommend optimal clip duration based on content type.

        Returns:
            (recommended_start, recommended_end)
        """
        # For TikTok/Reels: target 21-34 seconds
        target_duration = {
            "comedy": 25,
            "educational": 45,
            "story": 60,
            "general": 30
        }.get(content_type, 30)

        # If segment is within range, no adjustment needed
        if 15 <= segment_duration <= target_duration:
            return (0, segment_duration)

        # If too long, recommend trimming to target
        if segment_duration > target_duration:
            return (0, float(target_duration))

        # If too short, return as is
        return (0, segment_duration)