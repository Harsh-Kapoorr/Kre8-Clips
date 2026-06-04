"""
Advanced face tracking for vertical video cropping.

Implements:
- Phase 1: High-frequency face detection (every frame or adaptive interval)
- Phase 2: Embedding-based continuous face identity tracking
- Phase 3: Multi-hypothesis crop tracking (3 parallel smoothers, voting)
- Phase 4: Kalman filter for predictive motion tracking
- Phase 5: Audio-visual fusion for active speaker detection
"""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import math

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

from core.face_detector import FaceDetection, FaceDetector
from core.smoothing import CropSmoother


@dataclass
class KalmanState:
    """Kalman filter state for face position tracking."""
    x: float = 0.5
    y: float = 0.4
    vx: float = 0.0
    vy: float = 0.0
    P: np.ndarray = field(default_factory=lambda: np.eye(4) * 1e-4)

    def predict(self, dt: float) -> "KalmanState":
        """Predict next state using constant velocity model."""
        F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        Q = np.array([
            [dt**4/4, 0, dt**3/2, 0],
            [0, dt**4/4, 0, dt**3/2],
            [dt**3/2, 0, dt**2, 0],
            [0, dt**3/2, 0, dt**2]
        ]) * 1e-6

        state = np.array([self.x, self.y, self.vx, self.vy])
        new_state = F @ state
        new_P = F @ self.P @ F.T + Q

        return KalmanState(
            x=new_state[0], y=new_state[1],
            vx=new_state[2], vy=new_state[3],
            P=new_P
        )

    def update(self, zx: float, zy: float) -> "KalmanState":
        """Update state with observation."""
        H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ])
        R = np.eye(2) * 5e-5

        z = np.array([zx, zy])
        state = np.array([self.x, self.y, self.vx, self.vy])

        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)

        y_res = z - H @ state
        new_state = state + K @ y_res
        I = np.eye(4)
        new_P = (I - K @ H) @ self.P

        return KalmanState(
            x=new_state[0], y=new_state[1],
            vx=new_state[2], vy=new_state[3],
            P=new_P
        )


@dataclass
class MultiHypothesisSmoother:
    """Three parallel smoothers with voting for robust crop position."""
    smoother_a: CropSmoother = field(default_factory=lambda: CropSmoother(min_cutoff=0.8, beta=0.2))
    smoother_b: CropSmoother = field(default_factory=lambda: CropSmoother(min_cutoff=1.5, beta=0.5))
    smoother_c: CropSmoother = field(default_factory=lambda: CropSmoother(min_cutoff=2.5, beta=0.8))
    weights: Tuple[float, float, float] = (0.4, 0.35, 0.25)

    def update(self, x: float, y: float, t: float) -> Tuple[float, float]:
        """Update all smoothers and return weighted vote."""
        ax, ay = self.smoother_a.update(x, y, t)
        bx, by = self.smoother_b.update(x, y, t)
        cx, cy = self.smoother_c.update(x, y, t)

        result_x = self.weights[0] * ax + self.weights[1] * bx + self.weights[2] * cx
        result_y = self.weights[0] * ay + self.weights[1] * by + self.weights[2] * cy

        return result_x, result_y

    def reset(self):
        """Reset all smoothers."""
        self.smoother_a.reset()
        self.smoother_b.reset()
        self.smoother_c.reset()


@dataclass
class ContinuousFaceTrack:
    """Maintains continuous face position between sparse detections."""
    track_id: int
    last_x: float = 0.5
    last_y: float = 0.4
    last_t: float = 0.0
    embedding: Optional[np.ndarray] = None
    confidence: float = 1.0
    kalman: KalmanState = field(default_factory=KalmanState)
    missing_frames: int = 0

    def predict(self, dt: float) -> Tuple[float, float]:
        """Predict position using Kalman filter."""
        self.kalman = self.kalman.predict(dt)
        self.last_x = self.kalman.x
        self.last_y = self.kalman.y
        return self.kalman.x, self.kalman.y

    def update(self, x: float, y: float, t: float,
              embedding: Optional[np.ndarray] = None):
        """Update with observed position."""
        if t > self.last_t:
            dt = t - self.last_t
            self.kalman = self.kalman.update(x, y)
            self.last_x = self.kalman.x
            self.last_y = self.kalman.y
            self.last_t = t
            self.missing_frames = 0
        else:
            self.missing_frames += 1

        if embedding is not None:
            self.embedding = embedding


class SpeakerTracker:
    """High-precision speaker-aware face tracking for vertical video cropping."""

    def __init__(
        self,
        smoothing_window: float = 0.5,
        face_detection_interval: float = 0.25,
        adaptive_interval: bool = True,
    ):
        self.smoothing_window = smoothing_window
        self.face_detection_interval = face_detection_interval
        self.adaptive_interval = adaptive_interval
        self._detector: Optional[FaceDetector] = None
        self._multi_smoother = MultiHypothesisSmoother()
        self._last_layout_info: Dict[str, object] = {}
        self._speaker_confidences: Dict[str, float] = {}
        self._last_track_stats: Dict[int, Dict[str, object]] = {}
        self._last_speaker_track_map: Dict[str, int] = {}
        self._last_timeline: List[Tuple[float, str, float, float, Optional[int]]] = []
        self._last_face_detections: List[Tuple[float, List[FaceDetection]]] = []

        self._continuous_tracks: Dict[int, ContinuousFaceTrack] = {}
        self._frame_timestamps: Dict[int, float] = {}
        # Multi-face detection stats for two-person layout validation
        self._frames_with_multi_face: int = 0
        self._frames_with_any_face: int = 0

    def reset(self) -> None:
        """Reset all internal state so the tracker can process a new video or clip.

        Call this before each independent generate_position_track() call to prevent
        state (Kalman filters, face track IDs, smoothers, etc.) from drifting
        when processing multiple clips or re-processing the same video.
        """
        self._continuous_tracks.clear()
        self._frame_timestamps.clear()
        self._frames_with_multi_face = 0
        self._frames_with_any_face = 0
        self._multi_smoother.reset()
        self._last_layout_info = {}
        self._speaker_confidences = {}
        self._last_track_stats = {}
        self._last_speaker_track_map = {}
        self._last_timeline = []
        self._last_face_detections = []
        if self._detector is not None:
            self._detector.close()
            self._detector = None

    def detect_faces(
        self,
        video_path: Path,
        interval: Optional[float] = None,
        clip_segments: Optional[List[dict]] = None,
        portrait_mode: bool = False,
    ) -> List[Tuple[float, List[FaceDetection]]]:
        """Detect faces at adaptive high-frequency intervals."""
        interval = interval or self.face_detection_interval

        # Use shorter interval for portrait mode when adaptive_interval is enabled
        if self.adaptive_interval and portrait_mode:
            interval = 0.1

        print(f"SpeakerTracker: High-frequency face detection (interval={interval:.3f}s)...")

        if cv2 is None:
            print("SpeakerTracker: OpenCV not available")
            return []

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print("SpeakerTracker: Could not open video")
            return []

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        print(f"SpeakerTracker: Video duration {duration:.1f}s, fps {fps:.2f}")

        timestamps = self._build_sample_timestamps(duration, interval, clip_segments, portrait_mode)
        self._detector = FaceDetector()
        detections_by_time: List[Tuple[float, List[FaceDetection]]] = []
        prev_faces: List[FaceDetection] = []

        self._continuous_tracks.clear()
        self._frame_timestamps.clear()
        self._frames_with_multi_face = 0
        self._frames_with_any_face = 0
        detected_frames = 0

        for idx, ts in enumerate(timestamps):
            frame_number = int(ts * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ok, frame = cap.read()
            if not ok:
                detections_by_time.append((ts, []))
                continue

            faces = self._detector.detect_and_track(frame, prev_faces)

            for face in faces:
                track_id = face.face_id
                if track_id not in self._continuous_tracks:
                    self._continuous_tracks[track_id] = ContinuousFaceTrack(
                        track_id=track_id,
                        last_x=face.face_center[0],
                        last_y=face.face_center[1],
                        last_t=ts,
                        embedding=face.embedding,
                        kalman=KalmanState(x=face.face_center[0], y=face.face_center[1])
                    )
                else:
                    track = self._continuous_tracks[track_id]
                    track.update(face.face_center[0], face.face_center[1], ts,
                               embedding=face.embedding)

            if faces:
                prev_faces = faces
                detected_frames += 1
                self._frames_with_any_face += 1
                if len(faces) >= 2:
                    self._frames_with_multi_face += 1
            else:
                prev_faces = []

            detections_by_time.append((ts, faces))

            if idx and idx % 40 == 0:
                print(f"SpeakerTracker: Processed {idx}/{len(timestamps)} samples")

        cap.release()
        if self._detector:
            self._detector.close()

        print(f"SpeakerTracker: Face detections on {detected_frames}/{len(timestamps)} samples")
        return detections_by_time

    def get_multi_face_stats(self) -> Tuple[int, int, float]:
        """Return (frames_with_multi_face, frames_with_any_face, multi_face_ratio)."""
        ratio = (
            self._frames_with_multi_face / self._frames_with_any_face
            if self._frames_with_any_face > 0 else 0.0
        )
        return (self._frames_with_multi_face, self._frames_with_any_face, ratio)

    def _build_sample_timestamps(
        self,
        duration: float,
        interval: float,
        clip_segments: Optional[List[dict]],
        portrait_mode: bool = False,
    ) -> List[float]:
        if clip_segments:
            timestamps: List[float] = []
            # Use half interval in clip segments for higher detection resolution
            effective_interval = interval * 0.5 if portrait_mode else interval
            for seg in clip_segments:
                start = max(0.0, float(seg.get("start", 0)))
                end = min(duration, float(seg.get("end", start)))
                t = start
                while t <= end + 0.01:
                    timestamps.append(round(t, 3))
                    t += effective_interval
            return sorted(set(timestamps))

        capped_duration = min(duration, 300)
        timestamps = []
        t = 0.0
        while t < capped_duration:
            timestamps.append(round(t, 3))
            t += interval
        return timestamps

    def generate_position_track(
        self,
        video_path: Path,
        diarization_segments: List[dict],
        face_detections: Optional[List[Tuple[float, List[FaceDetection]]]] = None,
        clip_segments: Optional[List[dict]] = None,
        fps: float = 1.0,
        portrait_mode: bool = False,
    ) -> List[Tuple[float, str, float, float, Optional[int]]]:
        """Generate high-precision speaker-aware position timeline."""
        self.reset()
        if face_detections is None:
            face_detections = self.detect_faces(
                video_path,
                clip_segments=clip_segments,
                portrait_mode=portrait_mode,
            )
        self._last_face_detections = face_detections

        if not face_detections:
            return self._build_default_timeline(diarization_segments)

        track_stats = self._build_track_stats(face_detections)
        self._last_track_stats = track_stats
        if not track_stats:
            return self._build_default_timeline(diarization_segments)

        layout_info = self._classify_layout(track_stats)
        self._last_layout_info = layout_info
        print(
            f"SpeakerTracker: Layout={layout_info['type']} "
            f"(confidence={layout_info['confidence']:.2f})"
        )

        speaker_track_map, speaker_confidences = self._assign_speakers_to_tracks(
            diarization_segments,
            face_detections,
            track_stats,
            layout_info,
            clip_segments=clip_segments,
        )
        self._speaker_confidences = speaker_confidences
        self._last_speaker_track_map = speaker_track_map

        timeline = self._build_position_timeline(
            diarization_segments,
            track_stats,
            speaker_track_map,
            speaker_confidences,
            layout_info,
            clip_segments=clip_segments,
            portrait_mode=portrait_mode,
        )
        self._last_timeline = timeline

        if not timeline:
            return self._build_default_timeline(diarization_segments)

        print(f"SpeakerTracker: Generated {len(timeline)} timeline entries")
        return timeline

    def get_debug_snapshot(
        self,
        diarization_segments: Optional[List[dict]] = None,
        sample_limit: int = 80,
    ) -> Dict[str, object]:
        """Return a serializable debug snapshot for inspection."""
        face_samples = []
        for timestamp, detections in self._last_face_detections[:sample_limit]:
            face_samples.append({
                "time": timestamp,
                "faces": [{
                    "track_id": detection.face_id,
                    "x": round(detection.face_center[0], 4),
                    "y": round(detection.face_center[1], 4),
                    "area": round(detection.face_area, 6),
                    "speaking_score": round(detection.speaking_score, 4),
                    "confidence": round(detection.confidence, 4),
                } for detection in detections]
            })

        timeline_preview = [{
            "time": timestamp,
            "speaker": speaker,
            "x": round(x_pos, 4),
            "y": round(y_pos, 4),
            "track_id": track_id,
        } for timestamp, speaker, x_pos, y_pos, track_id in self._last_timeline[:sample_limit]]

        track_stats = {}
        for track_id, stats in self._last_track_stats.items():
            track_stats[str(track_id)] = {
                "avg_x": round(float(stats["avg_x"]), 4),
                "avg_y": round(float(stats["avg_y"]), 4),
                "avg_area": round(float(stats["avg_area"]), 6),
                "sample_count": int(stats["sample_count"]),
            }

        return {
            "layout": self._last_layout_info,
            "speaker_confidences": self._speaker_confidences,
            "speaker_track_map": self._last_speaker_track_map,
            "track_stats": track_stats,
            "face_sample_coverage": {
                "samples_with_faces": sum(1 for _, detections in self._last_face_detections if detections),
                "total_samples": len(self._last_face_detections),
                "frames_with_multi_face": self._frames_with_multi_face,
                "frames_with_any_face": self._frames_with_any_face,
                "multi_face_ratio": (
                    self._frames_with_multi_face / self._frames_with_any_face
                    if self._frames_with_any_face > 0 else 0.0
                ),
            },
            "face_samples": face_samples,
            "timeline_preview": timeline_preview,
            "timeline_total": len(self._last_timeline),
            "diarization_segments": diarization_segments or [],
        }

    def export_debug_snapshot(
        self,
        output_path: Path,
        diarization_segments: Optional[List[dict]] = None,
        sample_limit: int = 80,
    ) -> Path:
        """Persist the latest debug snapshot to JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = self.get_debug_snapshot(
            diarization_segments=diarization_segments,
            sample_limit=sample_limit,
        )
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2)
        print(f"SpeakerTracker: Wrote debug snapshot to {output_path}")
        return output_path

    def get_clip_reliability_signals(
        self,
        clip_start: float,
        clip_end: float,
    ) -> dict:
        """Aggregate face detection signals for a specific clip time range.

        Args:
            clip_start: Clip start time in seconds
            clip_end: Clip end time in seconds

        Returns:
            Dict with face_position_stability, detection_continuity,
            avg_face_confidence, avg_speaking_score, face_area_mean, multi_face_ratio
        """
        import statistics

        # Filter face detections to clip time range
        clip_detections = []
        for timestamp, detections in self._last_face_detections:
            if clip_start <= timestamp <= clip_end:
                clip_detections.extend(detections)

        if not clip_detections:
            return {
                "face_position_stability": 0.5,
                "detection_continuity": 0.5,
                "avg_face_confidence": 0.5,
                "avg_speaking_score": 0.5,
                "face_area_mean": 0.03,
                "multi_face_ratio": 0.0,
            }

        # Position stability (1 - normalized std dev)
        x_vals = [d.face_center[0] for d in clip_detections]
        y_vals = [d.face_center[1] for d in clip_detections]
        std_x = statistics.stdev(x_vals) if len(x_vals) > 1 else 0.0
        std_y = statistics.stdev(y_vals) if len(y_vals) > 1 else 0.0
        # Normalize: std of 0.1 (10% of frame) = 0 stability, std of 0 = 1.0 stability
        position_stability = max(0.0, 1.0 - (std_x + std_y) / 0.2)

        # Detection continuity (fraction of samples with any face)
        total_samples = len(self._last_face_detections)
        samples_in_range = sum(
            1 for t, dets in self._last_face_detections
            if clip_start <= t <= clip_end
        )
        samples_with_faces = sum(
            1 for t, dets in self._last_face_detections
            if clip_start <= t <= clip_end and dets
        )
        detection_continuity = (
            samples_with_faces / samples_in_range if samples_in_range > 0 else 0.5
        )

        # Averages
        avg_confidence = sum(d.confidence for d in clip_detections) / len(clip_detections)
        avg_speaking = sum(d.speaking_score for d in clip_detections) / len(clip_detections)
        avg_area = sum(d.face_area for d in clip_detections) / len(clip_detections)

        # Multi-face ratio from coverage stats
        multi_face_ratio = (
            self._frames_with_multi_face / self._frames_with_any_face
            if self._frames_with_any_face > 0 else 0.0
        )

        return {
            "face_position_stability": round(position_stability, 3),
            "detection_continuity": round(detection_continuity, 3),
            "avg_face_confidence": round(avg_confidence, 3),
            "avg_speaking_score": round(avg_speaking, 3),
            "face_area_mean": round(avg_area, 4),
            "multi_face_ratio": round(multi_face_ratio, 3),
        }

    def _build_track_stats(
        self,
        face_detections: List[Tuple[float, List[FaceDetection]]],
    ) -> Dict[int, Dict[str, object]]:
        """Aggregate detection history per face track."""
        track_stats: Dict[int, Dict[str, object]] = {}

        for ts, detections in face_detections:
            for detection in detections:
                track_id = detection.face_id
                entry = track_stats.setdefault(
                    track_id,
                    {"samples": [], "avg_x": 0.5, "avg_y": 0.4, "avg_area": 0.0},
                )
                entry["samples"].append({
                    "time": ts,
                    "x": detection.face_center[0],
                    "y": detection.face_center[1],
                    "area": detection.face_area,
                    "speaking_score": detection.speaking_score,
                })

        for track_id, entry in track_stats.items():
            samples = entry["samples"]
            entry["samples"] = sorted(samples, key=lambda sample: sample["time"])
            entry["avg_x"] = float(np.mean([sample["x"] for sample in samples]))
            entry["avg_y"] = float(np.mean([sample["y"] for sample in samples]))
            entry["avg_area"] = float(np.mean([sample["area"] for sample in samples]))
            entry["sample_count"] = len(samples)

        return track_stats

    def _classify_layout(self, track_stats: Dict[int, Dict[str, object]]) -> Dict[str, object]:
        """Infer whether the clip is single speaker, split-screen, or dynamic."""
        sorted_tracks = sorted(
            track_stats.items(),
            key=lambda item: (item[1]["sample_count"], item[1]["avg_area"]),
            reverse=True,
        )
        if not sorted_tracks:
            return {"type": "unknown", "confidence": 0.0, "primary_tracks": []}

        primary_tracks = [track_id for track_id, _ in sorted_tracks[:3]]
        if len(sorted_tracks) == 1:
            return {"type": "single", "confidence": 0.95, "primary_tracks": primary_tracks}

        first_track = sorted_tracks[0][1]
        second_track = sorted_tracks[1][1]
        x_separation = abs(first_track["avg_x"] - second_track["avg_x"])
        area_similarity = 1.0 - min(
            1.0,
            abs(first_track["avg_area"] - second_track["avg_area"]) / max(first_track["avg_area"], 1e-6),
        )
        coverage_similarity = min(
            first_track["sample_count"],
            second_track["sample_count"],
        ) / max(first_track["sample_count"], second_track["sample_count"])

        if x_separation >= 0.18 and area_similarity >= 0.45 and coverage_similarity >= 0.4:
            confidence = min(0.98, 0.45 + x_separation + 0.25 * area_similarity)
            return {
                "type": "split_two",
                "confidence": float(confidence),
                "primary_tracks": [sorted_tracks[0][0], sorted_tracks[1][0]],
            }

        dominant_track = sorted_tracks[0][1]
        if dominant_track["sample_count"] >= second_track["sample_count"] * 1.8:
            return {
                "type": "single_dominant",
                "confidence": 0.75,
                "primary_tracks": [sorted_tracks[0][0]],
            }

        return {
            "type": "dynamic_multi",
            "confidence": 0.55,
            "primary_tracks": primary_tracks,
        }

    def _assign_speakers_to_tracks(
        self,
        diarization_segments: List[dict],
        face_detections: List[Tuple[float, List[FaceDetection]]],
        track_stats: Dict[int, Dict[str, object]],
        layout_info: Dict[str, object],
        clip_segments: Optional[List[dict]] = None,
    ) -> Tuple[Dict[str, int], Dict[str, float]]:
        """Choose the most likely face track for each diarized speaker."""
        track_scores: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
        known_speakers = sorted({
            seg.get("speaker", "UNKNOWN")
            for seg in diarization_segments
            if seg.get("speaker")
        })

        if clip_segments:
            clip_start = min(float(s.get("start", 0)) for s in clip_segments)
            clip_end = max(float(s.get("end", 0)) for s in clip_segments)
        else:
            clip_start, clip_end = None, None

        for ts, detections in face_detections:
            if clip_start is not None and clip_end is not None:
                if ts < clip_start or ts > clip_end:
                    continue

            speaker = self._speaker_at_time(diarization_segments, ts)
            if not speaker or not detections:
                continue

            for detection in detections:
                size_bonus = detection.face_area * 2.5
                activity_bonus = detection.speaking_score * 4.0
                centered_bonus = max(0.0, 0.15 - abs(detection.face_center[0] - 0.5))
                track_scores[speaker][detection.face_id] += (
                    0.2 + size_bonus + activity_bonus + centered_bonus
                )

            if len(detections) == 1:
                only_face = detections[0]
                track_scores[speaker][only_face.face_id] += 3.0

        assigned_tracks: Dict[str, int] = {}
        used_tracks = set()
        speaker_confidences: Dict[str, float] = {}

        candidates = []
        for speaker, scores in track_scores.items():
            for track_id, score in scores.items():
                candidates.append((score, speaker, track_id))
        candidates.sort(reverse=True)

        for score, speaker, track_id in candidates:
            if speaker in assigned_tracks or track_id in used_tracks:
                continue
            assigned_tracks[speaker] = track_id
            used_tracks.add(track_id)
            sorted_scores = sorted(track_scores[speaker].values(), reverse=True)
            next_best = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
            confidence = score / max(score + next_best, 1e-6)
            speaker_confidences[speaker] = float(confidence)

        if layout_info.get("type") == "split_two" and len(known_speakers) == 2:
            left_right_tracks = sorted(
                layout_info.get("primary_tracks", []),
                key=lambda tid: track_stats[tid]["avg_x"],
            )
            unresolved = [sp for sp in known_speakers if sp not in assigned_tracks]
            for speaker, track_id in zip(unresolved, left_right_tracks):
                if track_id in used_tracks:
                    continue
                assigned_tracks[speaker] = track_id
                used_tracks.add(track_id)
                speaker_confidences[speaker] = 0.55

        remaining_tracks = sorted([
            (track_id, stats["avg_x"])
            for track_id, stats in track_stats.items()
            if track_id not in used_tracks
        ], key=lambda item: item[1])
        remaining_speakers = [sp for sp in known_speakers if sp not in assigned_tracks]
        for speaker, (track_id, _) in zip(remaining_speakers, remaining_tracks):
            assigned_tracks[speaker] = track_id
            speaker_confidences[speaker] = max(speaker_confidences.get(speaker, 0.0), 0.35)

        for speaker, track_id in sorted(assigned_tracks.items()):
            stats = track_stats[track_id]
            print(
                f"SpeakerTracker: {speaker} -> track {track_id} "
                f"(x={stats['avg_x']:.3f}, y={stats['avg_y']:.3f}, "
                f"conf={speaker_confidences.get(speaker, 0.0):.2f})"
            )

        return assigned_tracks, speaker_confidences

    def _get_interpolated_face_position(
        self,
        t: float,
        face_detections_in_range: List[Tuple[float, List[FaceDetection]]],
    ) -> Tuple[float, float, int]:
        """Return interpolated (x, y, track_id) at time t using surrounding detection samples."""
        if not face_detections_in_range:
            return (0.5, 0.4, -1)

        # Find surrounding detections
        before = [(ts, dets) for ts, dets in face_detections_in_range if ts <= t]
        after = [(ts, dets) for ts, dets in face_detections_in_range if ts >= t]

        if not before and not after:
            return (0.5, 0.4, -1)
        if not before:
            # All detections are after t - use earliest
            ts, dets = after[0]
            if dets:
                return (dets[0].face_center[0], dets[0].face_center[1], dets[0].face_id)
            return (0.5, 0.4, -1)
        if not after:
            # All detections are before t - use latest
            ts, dets = before[-1]
            if dets:
                return (dets[0].face_center[0], dets[0].face_center[1], dets[0].face_id)
            return (0.5, 0.4, -1)

        # Linear interpolation between surrounding detections
        ts_before, dets_before = before[-1]
        ts_after, dets_after = after[0]

        if ts_before == ts_after or not dets_before or not dets_after:
            return (dets_before[0].face_center[0], dets_before[0].face_center[1], dets_before[0].face_id)

        alpha = (t - ts_before) / (ts_after - ts_before)

        # Interpolate position
        x = dets_before[0].face_center[0] + alpha * (dets_after[0].face_center[0] - dets_before[0].face_center[0])
        y = dets_before[0].face_center[1] + alpha * (dets_after[0].face_center[1] - dets_before[0].face_center[1])
        track_id = dets_before[0].face_id

        return (x, y, track_id)

    def _build_position_timeline(
        self,
        diarization_segments: List[dict],
        track_stats: Dict[int, Dict[str, object]],
        speaker_track_map: Dict[str, int],
        speaker_confidences: Dict[str, float],
        layout_info: Dict[str, object],
        clip_segments: Optional[List[dict]] = None,
        portrait_mode: bool = False,
    ) -> List[Tuple[float, str, float, float, Optional[int]]]:
        """Build high-precision timeline at 0.1s resolution with interpolated positions.

        Integrates MultiHypothesisSmoother for robust crop position tracking.
        When speaker changes, reset smoother to new position.
        Between speaker changes, all positions pass through smoother.
        If smoother output differs from raw input by less than 2% of frame, use smoother output.
        """
        if not diarization_segments:
            return []

        sorted_segments = sorted(diarization_segments, key=lambda seg: seg.get("start", 0))

        if clip_segments:
            clip_start = min(float(seg.get("start", 0)) for seg in clip_segments)
            clip_end = max(float(seg.get("end", 0)) for seg in clip_segments)
            sorted_segments = [
                seg for seg in sorted_segments
                if float(seg.get("start", 0)) < clip_end and float(seg.get("end", 0)) > clip_start
            ]
        else:
            clip_start = min(float(seg.get("start", 0)) for seg in sorted_segments)
            clip_end = max(float(seg.get("end", 0)) for seg in sorted_segments)

        # Reset multi-smoother at start
        self._multi_smoother.reset()

        timeline = []
        last_x = None
        last_y = None
        last_track_id = None
        last_speaker = None

        face_detections_in_range = []
        if clip_start is not None and clip_end is not None:
            for ts, detections in self._last_face_detections:
                if clip_start <= ts <= clip_end and detections:
                    face_detections_in_range.append((ts, detections))

        t = clip_start
        while t <= clip_end + 0.001:
            speaker = self._speaker_at_time(sorted_segments, t) or last_speaker or "UNKNOWN"
            track_id = speaker_track_map.get(speaker, last_track_id)
            confidence = speaker_confidences.get(speaker, 0.0)

            raw_x, raw_y = None, None

            # Interpolate face position at time t
            raw_x_interp, raw_y_interp, raw_track_id = self._get_interpolated_face_position(
                t, face_detections_in_range
            )
            if raw_track_id != -1:
                # Use interpolated position, preferring the speaker's assigned track
                if layout_info.get("type") == "split_two" and track_id is not None:
                    # Find the detection that matches the speaker's track
                    matching_detection = None
                    for ts, detections in face_detections_in_range:
                        for det in detections:
                            if det.face_id == track_id:
                                matching_detection = det
                                break
                        if matching_detection:
                            break
                    if matching_detection:
                        raw_x = matching_detection.face_center[0]
                        raw_y = matching_detection.face_center[1]
                    else:
                        raw_x = raw_x_interp
                        raw_y = raw_y_interp
                else:
                    raw_x = raw_x_interp
                    raw_y = raw_y_interp

            if raw_x is None:
                if track_id in track_stats and confidence >= 0.45:
                    raw_x, raw_y = self._interpolate_track_position(
                        track_stats[track_id]["samples"], t
                    )
                elif track_id in track_stats and layout_info.get("type") == "split_two" and confidence < 0.45:
                    raw_x = float(track_stats[track_id]["avg_x"])
                    raw_y = float(track_stats[track_id]["avg_y"])
                elif last_track_id in track_stats:
                    raw_x, raw_y = self._interpolate_track_position(
                        track_stats[last_track_id]["samples"], t
                    )
                    track_id = last_track_id
                else:
                    raw_x, raw_y = self._fallback_position_for_speaker(
                        speaker, speaker_track_map, track_stats, layout_info
                    )

            if raw_x is None:
                raw_x, raw_y = 0.5, 0.4

            # Check for speaker change - reset smoother on new speaker
            if last_speaker is not None and speaker != last_speaker:
                self._multi_smoother.reset()
                self._multi_smoother.update(raw_x, raw_y, t)
                smoothed_x, smoothed_y = raw_x, raw_y
            else:
                # Pass through multi-hypothesis smoother
                smoothed_x, smoothed_y = self._multi_smoother.update(raw_x, raw_y, t)
                # If smoother output differs from raw by less than 2% of frame, use smoother
                diff_x = abs(smoothed_x - raw_x)
                diff_y = abs(smoothed_y - raw_y)
                if diff_x < 0.02 and diff_y < 0.02:
                    # Use smoother output (reduces shake)
                    pass
                else:
                    # Raw differs too much from smoother - use weighted blend
                    smoothed_x = 0.7 * smoothed_x + 0.3 * raw_x
                    smoothed_y = 0.7 * smoothed_y + 0.3 * raw_y

            last_x = smoothed_x
            last_y = smoothed_y
            last_speaker = speaker
            last_track_id = track_id

            timeline.append((round(t, 3), speaker, smoothed_x, smoothed_y, track_id))
            t += 0.1

        return timeline

    def _fallback_position_for_speaker(
        self,
        speaker: str,
        speaker_track_map: Dict[str, int],
        track_stats: Dict[int, Dict[str, object]],
        layout_info: Dict[str, object],
    ) -> Tuple[float, float]:
        """Stable fallback when direct tracking confidence is weak."""
        track_id = speaker_track_map.get(speaker)
        if track_id in track_stats:
            return (float(track_stats[track_id]["avg_x"]), float(track_stats[track_id]["avg_y"]))

        if layout_info.get("type") == "split_two":
            speakers = sorted(speaker_track_map.keys())
            if speaker in speakers and len(speakers) > 1:
                lane_positions = np.linspace(0.32, 0.68, len(speakers))
                return (float(lane_positions[speakers.index(speaker)]), 0.4)

        if layout_info.get("type") in {"single", "single_dominant"}:
            return (0.5, 0.38)

        return (0.5, 0.4)

    def _interpolate_track_position(
        self,
        samples: List[dict],
        timestamp: float,
    ) -> Tuple[float, float]:
        """Linear interpolation between samples for smooth tracking."""
        if not samples:
            return (0.5, 0.4)

        before = [s for s in samples if s["time"] <= timestamp]
        after = [s for s in samples if s["time"] >= timestamp]

        if not before:
            return (after[0]["x"], after[0]["y"])
        if not after:
            return (before[-1]["x"], before[-1]["y"])

        a, b = before[-1], after[0]
        if a["time"] == b["time"]:
            return (a["x"], a["y"])

        alpha = (timestamp - a["time"]) / (b["time"] - a["time"])
        x = a["x"] + alpha * (b["x"] - a["x"])
        y = a["y"] + alpha * (b["y"] - a["y"])
        return (float(x), float(y))

    def _build_default_timeline(
        self,
        diarization_segments: List[dict],
    ) -> List[Tuple[float, str, float, float, Optional[int]]]:
        """Fallback when no real face detections are available."""
        if not diarization_segments:
            return []

        speakers = sorted({
            seg.get("speaker", "UNKNOWN")
            for seg in diarization_segments if seg.get("speaker")
        })
        speaker_positions: Dict[str, Tuple[float, float]] = {}
        if not speakers:
            speaker_positions["UNKNOWN"] = (0.5, 0.4)
        elif len(speakers) == 1:
            speaker_positions[speakers[0]] = (0.5, 0.4)
        else:
            lane_positions = np.linspace(0.32, 0.68, len(speakers))
            for speaker, x_pos in zip(speakers, lane_positions):
                speaker_positions[speaker] = (float(x_pos), 0.4)

        timeline = []
        t = min(float(seg.get("start", 0)) for seg in diarization_segments)
        end = max(float(seg.get("end", 0)) for seg in diarization_segments)
        while t <= end + 0.001:
            speaker = self._speaker_at_time(diarization_segments, t) or "UNKNOWN"
            x_pos, y_pos = speaker_positions.get(speaker, (0.5, 0.4))
            timeline.append((round(t, 3), speaker, x_pos, y_pos, None))
            t += 0.25

        print("SpeakerTracker: Using fallback speaker lanes because no faces were detected")
        return timeline

    @staticmethod
    def _speaker_at_time(diarization_segments: List[dict], timestamp: float) -> Optional[str]:
        for segment in diarization_segments:
            start = float(segment.get("start", 0))
            end = float(segment.get("end", start))
            if start <= timestamp <= end:
                return segment.get("speaker", "UNKNOWN")
        return None