"""
Face detection with MediaPipe blendshapes and lightweight track assignment.

The repo ships a MediaPipe face landmarker task file, so we use that first
for accurate face boxes plus mouth/jaw activity that helps correlate an
active speaker with the visible face in podcast layouts.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import FaceLandmarker
    from mediapipe.tasks.python.vision import FaceLandmarkerOptions
    from mediapipe.tasks.python.vision import RunningMode
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    mp = None
    BaseOptions = None
    FaceLandmarker = None
    FaceLandmarkerOptions = None
    RunningMode = None
    MEDIAPIPE_AVAILABLE = False

try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    FaceAnalysis = None
    INSIGHTFACE_AVAILABLE = False


@dataclass
class FaceDetection:
    face_id: int
    bbox: Tuple[int, int, int, int]
    landmarks: Optional[List[Tuple[float, float]]]
    confidence: float
    face_center: Tuple[float, float]
    embedding: Optional[np.ndarray] = None
    speaking_score: float = 0.0
    face_area: float = 0.0


class FaceDetector:
    """Detect faces and keep stable IDs across sampled frames."""

    def __init__(
        self,
        model_name: str = "buffalo_l",
        det_size: Tuple[int, int] = (640, 640),
        max_faces: int = 4,
        min_confidence: float = 0.65,
    ):
        self.model_name = model_name
        self.det_size = det_size
        self.max_faces = max_faces
        self.min_confidence = min_confidence
        self._face_analyzer = None
        self._landmarker = None
        self._backend = "none"
        self._next_track_id = 0

        # Track missing frames for re-identification
        self._missing_frames: Dict[int, int] = {}  # track_id -> consecutive missed frames
        self._lost_faces: Dict[int, FaceDetection] = {}  # track_id -> last known face for re-id

        if cv2 is None:
            print("FaceDetector: OpenCV not available")
            return

        self._init_mediapipe()
        if self._backend == "none":
            self._init_insightface()

        if self._backend == "none":
            print("FaceDetector: No face detection backend available")

    def _init_mediapipe(self) -> None:
        """Prefer MediaPipe because the model asset ships with this repo."""
        if not MEDIAPIPE_AVAILABLE:
            return

        task_path = Path(__file__).parent.parent / "assets" / "face_landmarker_v2_with_blendshapes.task"
        if not task_path.exists():
            return

        try:
            options = FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(task_path)),
                running_mode=RunningMode.IMAGE,
                num_faces=self.max_faces,
                min_face_detection_confidence=self.min_confidence,
                min_face_presence_confidence=self.min_confidence,
                min_tracking_confidence=self.min_confidence,
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=False,
            )
            self._landmarker = FaceLandmarker.create_from_options(options)
            self._backend = "mediapipe"
            print("FaceDetector: Using MediaPipe Face Landmarker")
        except Exception as exc:
            print(f"FaceDetector: MediaPipe init failed: {exc}")

    def _init_insightface(self) -> None:
        """Fallback for environments that already have InsightFace installed."""
        if not INSIGHTFACE_AVAILABLE:
            return

        try:
            self._face_analyzer = FaceAnalysis(name=self.model_name)
            self._face_analyzer.prepare(ctx_id=0, det_size=self.det_size)
            self._backend = "insightface"
            print(f"FaceDetector: Using InsightFace {self.model_name}")
        except Exception as exc:
            print(f"FaceDetector: InsightFace init failed: {exc}")

    def detect_faces(self, frame: np.ndarray) -> List[FaceDetection]:
        """Detect faces in a frame."""
        if self._backend == "mediapipe":
            return self._detect_faces_mediapipe(frame)
        if self._backend == "insightface":
            return self._detect_faces_insightface(frame)
        return []

    def _detect_faces_mediapipe(self, frame: np.ndarray) -> List[FaceDetection]:
        if self._landmarker is None or mp is None or cv2 is None:
            return []
        frame_h, frame_w = frame.shape[:2]
        frame_area = frame_w * frame_h
        detections: List[FaceDetection] = []

        regions = self._build_detection_regions(frame_w, frame_h)
        for region in regions:
            crop = frame[
                region["y1"]:region["y2"],
                region["x1"]:region["x2"],
            ]
            if crop.size == 0:
                continue

            if region["scale_up"] != 1.0:
                resized = cv2.resize(
                    crop,
                    (
                        int(crop.shape[1] * region["scale_up"]),
                        int(crop.shape[0] * region["scale_up"]),
                    ),
                    interpolation=cv2.INTER_LINEAR,
                )
            else:
                resized = crop

            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self._landmarker.detect(mp_image)

            face_landmarks = result.face_landmarks or []
            face_blendshapes = result.face_blendshapes or []
            resized_h, resized_w = resized.shape[:2]
            region_w = region["x2"] - region["x1"]
            region_h = region["y2"] - region["y1"]

            for idx, landmarks in enumerate(face_landmarks):
                xs = [lm.x for lm in landmarks]
                ys = [lm.y for lm in landmarks]
                if not xs or not ys:
                    continue

                x1 = max(0, int(region["x1"] + min(xs) * region_w))
                y1 = max(0, int(region["y1"] + min(ys) * region_h))
                x2 = min(frame_w, int(region["x1"] + max(xs) * region_w))
                y2 = min(frame_h, int(region["y1"] + max(ys) * region_h))
                if x2 <= x1 or y2 <= y1:
                    continue

                bbox_w = x2 - x1
                bbox_h = y2 - y1
                center_x = (x1 + x2) / 2 / frame_w

                eye_y = None
                if landmarks and len(landmarks) >= 2:
                    lm0_y = landmarks[0].y
                    lm1_y = landmarks[1].y
                    eye_y = (lm0_y + lm1_y) / 2.0
                if eye_y is not None:
                    center_y = eye_y  # already normalized (0-1)
                else:
                    center_y = (y1 + y2) / 2 / frame_h * 0.85

                speaking_score = 0.0
                categories = face_blendshapes[idx] if idx < len(face_blendshapes) else []
                if categories:
                    scores = {cat.category_name: float(cat.score) for cat in categories}
                    speaking_score = self._compute_speaking_score(scores)

                # Confidence filtering
                confidence = 0.95
                bbox_area = (bbox_w * bbox_h) / float(frame_area)

                # Reject faces where bbox_area < 0.03 * frame_area
                if bbox_area < 0.03:
                    continue

                # Reject faces touching/outside border
                if x1 < 0 or y1 < 0 or x2 > frame_w or y2 > frame_h:
                    continue

                detections.append(
                    FaceDetection(
                        face_id=idx,
                        bbox=(x1, y1, bbox_w, bbox_h),
                        landmarks=[
                            (
                                region["x1"] + lm.x * region_w,
                                region["y1"] + lm.y * region_h,
                            )
                            for lm in landmarks[:12]
                        ],
                        confidence=confidence,
                        face_center=(center_x, center_y),
                        speaking_score=speaking_score,
                        face_area=bbox_area,
                    )
                )

        return self._dedupe_detections(detections)

    def _detect_faces_insightface(self, frame: np.ndarray) -> List[FaceDetection]:
        if self._face_analyzer is None or cv2 is None:
            return []

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = self._face_analyzer.get(rgb)
        frame_h, frame_w = frame.shape[:2]
        frame_area = frame_w * frame_h
        detections: List[FaceDetection] = []

        for idx, face in enumerate(faces):
            bbox = face.bbox.astype(int)
            x1, y1, x2, y2 = bbox
            bbox_w = max(0, x2 - x1)
            bbox_h = max(0, y2 - y1)
            if bbox_w == 0 or bbox_h == 0:
                continue

            # Confidence filtering
            confidence = float(face.det_score) if hasattr(face, "det_score") else 0.9

            # Reject faces with low detection confidence
            if confidence < 0.5:
                continue

            bbox_area = (bbox_w * bbox_h) / float(frame_area)

            # Reject faces where bbox_area < 0.03 * frame_area
            if bbox_area < 0.03:
                continue

            # Reject faces touching/outside border
            if x1 < 0 or y1 < 0 or x2 > frame_w or y2 > frame_h:
                continue

            center_x = (x1 + x2) / 2 / frame_w

            eye_y = None
            if landmarks and len(landmarks) >= 2:
                lm0_y = landmarks[0][1]
                lm1_y = landmarks[1].y
                eye_y = (lm0_y + lm1_y) / 2.0
            if eye_y is not None:
                center_y = eye_y / frame_h
            else:
                center_y = (y1 + y2) / 2 / frame_h * 0.85

            landmarks = None
            if hasattr(face, "landmark") and face.landmark is not None:
                raw_landmarks = face.landmark
                landmarks = [(float(pt[0]), float(pt[1])) for pt in raw_landmarks[:12]]

            detections.append(
                FaceDetection(
                    face_id=idx,
                    bbox=(int(x1), int(y1), int(bbox_w), int(bbox_h)),
                    landmarks=landmarks,
                    confidence=confidence,
                    face_center=(center_x, center_y),
                    embedding=getattr(face, "embedding", None),
                    speaking_score=0.0,
                    face_area=bbox_area,
                )
            )

        return detections

    def _build_detection_regions(self, frame_w: int, frame_h: int) -> List[Dict[str, float]]:
        """Full frame + 2 focused regions for small podcast faces. 3 regions instead of 4."""
        mid_x = frame_w // 2
        return [
            {"x1": 0, "y1": 0, "x2": frame_w, "y2": frame_h, "scale_up": 1.0},
            {"x1": 0, "y1": 0, "x2": mid_x + frame_w // 10, "y2": frame_h, "scale_up": 1.75},
            {"x1": max(0, mid_x - frame_w // 10), "y1": 0, "x2": frame_w, "y2": frame_h, "scale_up": 1.75},
        ]

    def _dedupe_detections(self, detections: List[FaceDetection]) -> List[FaceDetection]:
        """Merge duplicate detections coming from different scan regions."""
        if not detections:
            return []

        deduped: List[FaceDetection] = []
        for detection in sorted(
            detections,
            key=lambda item: (item.face_area, item.speaking_score, item.confidence),
            reverse=True,
        ):
            duplicate = False
            for existing in deduped:
                if self._bbox_iou(existing.bbox, detection.bbox) >= 0.45:
                    duplicate = True
                    break
            if not duplicate:
                deduped.append(detection)
        return deduped

    def detect_and_track(
        self,
        frame: np.ndarray,
        prev_faces: Optional[List[FaceDetection]] = None,
    ) -> List[FaceDetection]:
        """Detect faces and reuse track IDs from the previous sampled frame."""
        current_faces = self.detect_faces(frame)
        if not current_faces:
            # Increment missing frames for all tracked faces
            for face in (prev_faces or []):
                self._missing_frames[face.face_id] = self._missing_frames.get(face.face_id, 0) + 1
                # Mark as lost after 4+ consecutive misses
                if self._missing_frames[face.face_id] >= 4:
                    self._lost_faces[face.face_id] = face
            return []

        prev_faces = prev_faces or []
        frame_h, frame_w = frame.shape[:2]
        max_displacement_threshold = 0.20 * frame_w  # 20% of frame width

        # Build dict of previous faces by track_id for quick lookup
        prev_by_id: Dict[int, FaceDetection] = {face.face_id: face for face in prev_faces}
        unmatched_prev_ids: set = set(prev_by_id.keys())
        matched_current: List[FaceDetection] = []

        for current_face in current_faces:
            best_prev_id = None
            best_score = 0.0
            best_displacement = float('inf')

            for prev_id in unmatched_prev_ids:
                prev_face = prev_by_id[prev_id]
                score = self._match_score(prev_face, current_face)

                # Compute center displacement for stability check
                center_distance = np.hypot(
                    prev_face.face_center[0] - current_face.face_center[0],
                    prev_face.face_center[1] - current_face.face_center[1],
                )
                displacement_pixels = center_distance * frame_w

                # Skip if displacement exceeds maximum threshold (new person)
                if displacement_pixels > max_displacement_threshold:
                    continue

                if score > best_score:
                    best_score = score
                    best_prev_id = prev_id
                    best_displacement = displacement_pixels
                elif score == best_score and displacement_pixels < best_displacement:
                    # Prefer the track with smallest position change (most stable match)
                    best_prev_id = prev_id
                    best_displacement = displacement_pixels

            if best_prev_id is not None and best_score >= 0.50:
                current_face.face_id = best_prev_id
                unmatched_prev_ids.remove(best_prev_id)
                # Reset missing frames for matched face
                self._missing_frames.pop(best_prev_id, None)
                matched_current.append(current_face)
            else:
                # Try to re-identify a lost face before assigning new ID
                reidentified_id = self._reidentify_face(current_face, self._lost_faces, iou_threshold=0.25)
                if reidentified_id is not None:
                    current_face.face_id = reidentified_id
                    self._lost_faces.pop(reidentified_id, None)
                    self._missing_frames.pop(reidentified_id, None)
                else:
                    current_face.face_id = self._next_track_id
                    self._next_track_id += 1
                matched_current.append(current_face)

        # Increment missing frames for unmatched previous faces
        for prev_id in unmatched_prev_ids:
            self._missing_frames[prev_id] = self._missing_frames.get(prev_id, 0) + 1
            # Mark as lost after 4+ consecutive misses
            if self._missing_frames[prev_id] >= 4:
                if prev_id in prev_by_id:
                    self._lost_faces[prev_id] = prev_by_id[prev_id]

        return matched_current

    def _reidentify_face(
        self,
        new_bbox: Tuple[int, int, int, int],
        tracked_faces: Dict[int, FaceDetection],
        iou_threshold: float = 0.40,
    ) -> Optional[int]:
        """Try to match a new detection back to a recently lost face by IOU."""
        for track_id, lost_face in tracked_faces.items():
            # Only re-identify if face was lost recently (within 4 frames)
            if self._missing_frames.get(track_id, 0) < 4:
                iou = self._bbox_iou(new_bbox, lost_face.bbox)
                if iou > iou_threshold:
                    return track_id
        return None

    def _match_score(self, previous: FaceDetection, current: FaceDetection) -> float:
        """Blend IoU, center distance, and embeddings when available."""
        iou = self._bbox_iou(previous.bbox, current.bbox)
        center_distance = np.hypot(
            previous.face_center[0] - current.face_center[0],
            previous.face_center[1] - current.face_center[1],
        )
        proximity = max(0.0, 1.0 - (center_distance / 0.35))

        score = 0.65 * iou + 0.35 * proximity

        if previous.embedding is not None and current.embedding is not None:
            denom = np.linalg.norm(previous.embedding) * np.linalg.norm(current.embedding)
            if denom > 0:
                embedding_similarity = float(np.dot(previous.embedding, current.embedding) / denom)
                score = max(score, 0.5 * score + 0.5 * embedding_similarity)

        return float(score)

    @staticmethod
    def _bbox_iou(
        bbox_a: Tuple[int, int, int, int],
        bbox_b: Tuple[int, int, int, int],
    ) -> float:
        ax1, ay1, aw, ah = bbox_a
        bx1, by1, bw, bh = bbox_b
        ax2, ay2 = ax1 + aw, ay1 + ah
        bx2, by2 = bx1 + bw, by1 + bh

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)

        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h
        if inter_area == 0:
            return 0.0

        area_a = aw * ah
        area_b = bw * bh
        union = area_a + area_b - inter_area
        if union <= 0:
            return 0.0

        return inter_area / union

    @staticmethod
    def _compute_speaking_score(blendshape_scores: Dict[str, float]) -> float:
        """Heuristic for mouth activity during speech."""
        jaw_open = blendshape_scores.get("jawOpen", 0.0)
        mouth_open = blendshape_scores.get("mouthOpen", 0.0)
        funnel = blendshape_scores.get("mouthFunnel", 0.0)
        pucker = blendshape_scores.get("mouthPucker", 0.0)
        press_left = blendshape_scores.get("mouthPressLeft", 0.0)
        press_right = blendshape_scores.get("mouthPressRight", 0.0)
        activity = jaw_open + 0.7 * mouth_open + 0.35 * funnel + 0.2 * pucker
        closed_penalty = 0.25 * (press_left + press_right)
        return max(0.0, activity - closed_penalty)

    def close(self) -> None:
        """Release detector resources."""
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None