import json
import unittest
from pathlib import Path

from core.face_detector import FaceDetection
from core.speaker_tracker import SpeakerTracker


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


def build_face_detections(raw_entries: list[dict]):
    face_detections = []
    for entry in raw_entries:
        faces = []
        for face in entry["faces"]:
            faces.append(
                FaceDetection(
                    face_id=face["track_id"],
                    bbox=(0, 0, 100, 100),
                    landmarks=None,
                    confidence=0.95,
                    face_center=(face["x"], face["y"]),
                    speaking_score=face.get("speaking_score", 0.0),
                    face_area=face.get("area", 0.05),
                )
            )
        face_detections.append((entry["time"], faces))
    return face_detections


class SpeakerTrackingRegressionTest(unittest.TestCase):
    def run_fixture(self, fixture_name: str):
        fixture = load_fixture(fixture_name)
        tracker = SpeakerTracker(face_detection_interval=0.5)
        diarization_segments = fixture["diarization_segments"]
        face_detections = build_face_detections(fixture["face_detections"])
        timeline = tracker.generate_position_track(
            video_path=Path("synthetic.mp4"),
            diarization_segments=diarization_segments,
            face_detections=face_detections,
        )
        self.assertTrue(timeline)
        return fixture, tracker, timeline

    def test_multi_clip_state_isolation(self):
        """Regression test: processing multiple clips with the same SpeakerTracker
        instance should NOT cause face tracking drift on subsequent clips.

        Bug: when the same SpeakerTracker instance was reused for multiple
        generate_position_track() calls (e.g., processing multiple clips from
        the same video), internal state (_continuous_tracks, smoothers,
        track_stats, etc.) persisted between calls, causing face bounding
        boxes to drift on later clips.
        """
        tracker = SpeakerTracker(face_detection_interval=0.5)

        clip_a_diarization = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_0"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_1"},
        ]
        clip_a_faces = build_face_detections([
            {"time": 0.0, "faces": [{"track_id": 0, "x": 0.30, "y": 0.40, "area": 0.07, "speaking_score": 0.8}]},
            {"time": 2.0, "faces": [{"track_id": 0, "x": 0.31, "y": 0.41, "area": 0.07, "speaking_score": 0.7}]},
            {"time": 5.0, "faces": [{"track_id": 1, "x": 0.70, "y": 0.40, "area": 0.07, "speaking_score": 0.8}]},
            {"time": 7.0, "faces": [{"track_id": 1, "x": 0.69, "y": 0.41, "area": 0.07, "speaking_score": 0.7}]},
        ])

        clip_b_diarization = [
            {"start": 15.0, "end": 20.0, "speaker": "SPEAKER_0"},
            {"start": 20.0, "end": 25.0, "speaker": "SPEAKER_1"},
        ]
        clip_b_faces = build_face_detections([
            {"time": 15.0, "faces": [{"track_id": 0, "x": 0.50, "y": 0.38, "area": 0.07, "speaking_score": 0.8}]},
            {"time": 17.0, "faces": [{"track_id": 0, "x": 0.51, "y": 0.39, "area": 0.07, "speaking_score": 0.7}]},
            {"time": 20.0, "faces": [{"track_id": 1, "x": 0.60, "y": 0.40, "area": 0.07, "speaking_score": 0.8}]},
            {"time": 22.0, "faces": [{"track_id": 1, "x": 0.59, "y": 0.41, "area": 0.07, "speaking_score": 0.7}]},
        ])

        clip_a_segments = [{"start": 0.0, "end": 10.0}]
        clip_b_segments = [{"start": 15.0, "end": 25.0}]

        timeline_a = tracker.generate_position_track(
            video_path=Path("synthetic.mp4"),
            diarization_segments=clip_a_diarization,
            face_detections=clip_a_faces,
            clip_segments=clip_a_segments,
        )
        self.assertTrue(timeline_a)

        timeline_b = tracker.generate_position_track(
            video_path=Path("synthetic.mp4"),
            diarization_segments=clip_b_diarization,
            face_detections=clip_b_faces,
            clip_segments=clip_b_segments,
        )
        self.assertTrue(timeline_b)

        for entry in timeline_b:
            t, speaker, x, y, track_id = entry
            self.assertGreaterEqual(
            x, 0.0, f"Face x position should be valid, got {x} at t={t}"
            )
            self.assertLessEqual(
                x, 1.0, f"Face x position should be valid, got {x} at t={t}"
            )
            self.assertGreaterEqual(
                y, 0.0, f"Face y position should be valid, got {y} at t={t}"
            )
            self.assertLessEqual(
                y, 1.0, f"Face y position should be valid, got {y} at t={t}"
            )

        xs_speaker_0 = [x for t, sp, x, y, tid in timeline_b if sp == "SPEAKER_0"]
        self.assertTrue(xs_speaker_0, "SPEAKER_0 should have entries in clip B")
        mean_x_speaker_0 = sum(xs_speaker_0) / len(xs_speaker_0)
        self.assertAlmostEqual(
            mean_x_speaker_0,
            0.505,
            delta=0.15,
            msg=f"SPEAKER_0 face center x should be ~0.50 in clip B, got {mean_x_speaker_0:.3f}",
        )

        xs_speaker_1 = [x for t, sp, x, y, tid in timeline_b if sp == "SPEAKER_1"]
        self.assertTrue(xs_speaker_1, "SPEAKER_1 should have entries in clip B")
        mean_x_speaker_1 = sum(xs_speaker_1) / len(xs_speaker_1)
        self.assertAlmostEqual(
            mean_x_speaker_1,
            0.595,
            delta=0.15,
            msg=f"SPEAKER_1 face center x should be ~0.60 in clip B, got {mean_x_speaker_1:.3f}",
        )

    def test_reset_clears_internal_state(self):
        """Verify that SpeakerTracker.reset() properly clears all internal state."""
        tracker = SpeakerTracker(face_detection_interval=0.5)

        self.assertIsNotNone(tracker._multi_smoother)
        self.assertEqual(tracker._continuous_tracks, {})
        self.assertEqual(tracker._frame_timestamps, {})
        self.assertEqual(tracker._frames_with_multi_face, 0)
        self.assertEqual(tracker._frames_with_any_face, 0)

        tracker._continuous_tracks[0] = None
        tracker._frame_timestamps[0] = 0.0
        tracker._frames_with_multi_face = 5
        tracker._frames_with_any_face = 10

        tracker.reset()

        self.assertEqual(tracker._continuous_tracks, {})
        self.assertEqual(tracker._frame_timestamps, {})
        self.assertEqual(tracker._frames_with_multi_face, 0)
        self.assertEqual(tracker._frames_with_any_face, 0)
        self.assertEqual(tracker._last_face_detections, [])
        self.assertEqual(tracker._last_timeline, [])
        self.assertEqual(tracker._last_layout_info, {})
        self.assertEqual(tracker._speaker_confidences, {})

    def test_split_two_podcast_layout(self):
        fixture, tracker, timeline = self.run_fixture("podcast_split_two_regression.json")
        expected = fixture["expected"]

        self.assertEqual(tracker._last_layout_info["type"], expected["layout_type"])
        self.assertEqual(tracker._last_speaker_track_map["SPEAKER_0"], expected["speaker_tracks"]["SPEAKER_0"])
        self.assertEqual(tracker._last_speaker_track_map["SPEAKER_1"], expected["speaker_tracks"]["SPEAKER_1"])

        for speaker, bounds in expected["speaker_ranges"].items():
            xs = [x for _, sp, x, _, _ in timeline if sp == speaker]
            self.assertTrue(xs, f"Expected timeline entries for {speaker}")
            self.assertGreaterEqual(min(xs), bounds["min_x"])
            self.assertLessEqual(max(xs), bounds["max_x"])

    def test_single_dominant_layout(self):
        fixture, tracker, timeline = self.run_fixture("podcast_single_dominant_regression.json")
        expected = fixture["expected"]

        self.assertEqual(tracker._last_layout_info["type"], expected["layout_type"])
        self.assertEqual(tracker._last_layout_info["primary_tracks"][0], expected["primary_track"])

        bounds = expected["speaker_ranges"]["SPEAKER_0"]
        xs = [x for _, speaker, x, _, _ in timeline if speaker == "SPEAKER_0"]
        self.assertTrue(xs)
        self.assertGreaterEqual(min(xs), bounds["min_x"])
        self.assertLessEqual(max(xs), bounds["max_x"])


if __name__ == "__main__":
    unittest.main()
