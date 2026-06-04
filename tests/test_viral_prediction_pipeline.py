"""
Tests for `clipgen.clip_text_segments` and the `update_job_clips` repair
of missing viral fields. The original bug:

  * The viral predictor call site at `clipgen.py:646` was passing the FULL
    transcript to `viral_predictor.predict(...)`, which meant the model's
    hook/payoff features were computed from the transcript's first/last
    segment — not the clip's. A clip with a strong in-the-middle hook got
    scored as if its hook were "Hey everyone, welcome back".
  * `update_job_clips` re-merged new clip dicts with prior and fell back
    to 0.0 for any clip that was added AFTER the first save (e.g., a
    smart-narrative-assembled clip). That made the UI show 0% for
    otherwise good clips.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import clipgen
from clipgen import clip_text_segments


class ClipTextSegmentsTest(unittest.TestCase):
    def test_filters_to_clip_window(self):
        transcript = [
            {"start": 0.0, "end": 5.0, "text": "Intro fluff.", "speaker": "S0"},
            {"start": 50.0, "end": 55.0, "text": "Boring middle.", "speaker": "S0"},
            {"start": 60.0, "end": 75.0, "text": "The actual hook.", "speaker": "S0"},
            {"start": 100.0, "end": 110.0, "text": "Wrap up.", "speaker": "S0"},
        ]
        clip = {"segments": [{"start": "00:01:00", "end": "00:01:15"}]}
        out = clip_text_segments(clip, transcript)
        texts = [s["text"] for s in out]
        self.assertIn("The actual hook.", texts)
        self.assertNotIn("Intro fluff.", texts)
        self.assertNotIn("Boring middle.", texts)
        self.assertNotIn("Wrap up.", texts)

    def test_returns_empty_for_no_segments(self):
        out = clip_text_segments({"segments": []}, [{"text": "x", "start": 0}])
        self.assertEqual(out, [])

    def test_returns_empty_for_no_transcript(self):
        out = clip_text_segments({"segments": [{"start": "0", "end": "5"}]}, [])
        self.assertEqual(out, [])

    def test_handles_string_timestamps(self):
        transcript = [
            {"start": 0.0, "end": 5.0, "text": "A", "speaker": "S0"},
            {"start": 50.0, "end": 60.0, "text": "B", "speaker": "S0"},
        ]
        clip = {"segments": [{"start": "00:00:00", "end": "00:00:05"}]}
        out = clip_text_segments(clip, transcript)
        self.assertEqual([s["text"] for s in out], ["A"])

    def test_padding_includes_boundary_segments(self):
        """0.5s padding should pick up a segment that ends just before the
        clip's start, so the boundary-snapper's slight shifts don't
        blackhole the hook text."""
        transcript = [
            {"start": 9.6, "end": 10.4, "text": "Right at the edge.", "speaker": "S0"},
            {"start": 10.5, "end": 20.0, "text": "Inside the clip.", "speaker": "S0"},
        ]
        clip = {"segments": [{"start": "00:00:10", "end": "00:00:20"}]}
        out_default = clip_text_segments(clip, transcript)
        out_no_pad = clip_text_segments(clip, transcript, padding=0.0)
        self.assertGreaterEqual(len(out_default), len(out_no_pad))

    def test_speaker_preserved(self):
        transcript = [
            {"start": 0.0, "end": 5.0, "text": "Hello", "speaker": "GUEST_1"},
        ]
        clip = {"segments": [{"start": "00:00:00", "end": "00:00:05"}]}
        out = clip_text_segments(clip, transcript)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["speaker"], "GUEST_1")


class UpdateJobClipsFillsMissingViralTest(unittest.TestCase):
    """Lock in: a clip that was added to the job AFTER the first save
    (e.g., a smart-narrative-assembled clip) should still get a real viral
    prediction, not all-zeros."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Redirect JOBS_DIR into the temp dir
        import core.job_data_manager as jdm
        self._original_jobs_dir = jdm.JOBS_DIR
        jdm.JOBS_DIR = Path(self._tmp.name)
        self.addCleanup(lambda: setattr(jdm, "JOBS_DIR", self._original_jobs_dir))

    def _write_job(self, job_id, transcript, existing_clips):
        path = Path(self._tmp.name) / f"{job_id}.json"
        payload = {
            "job_id": job_id,
            "url": "https://example.com/test",
            "video_title": "Test Video",
            "transcript": transcript,
            "generated_clips": existing_clips,
            "ai_analysis": {"segments": [], "beat_timestamps": [], "emotional_density": []},
            "broll_suggestions": [],
        }
        path.write_text(json.dumps(payload))

    def test_clip_with_no_prior_viral_gets_prediction(self):
        """Reproduce the user-reported 'all zeros' case: a smart-narrative
        clip existed in the new render list but had no prior viral entry."""
        from core.job_data_manager import update_job_clips

        job_id = "test_job_001"
        transcript = [
            {"start": 0.0, "end": 5.0, "text": "Welcome to the show.", "speaker": "S0"},
            {"start": 5.0, "end": 15.0, "text": "Today is going to be incredible.", "speaker": "S0"},
            {"start": 15.0, "end": 25.0, "text": "Here's the secret that changes everything.", "speaker": "S0"},
            {"start": 25.0, "end": 35.0, "text": "You won't believe what happens next.", "speaker": "S0"},
            {"start": 35.0, "end": 45.0, "text": "Step 1: do this. Step 2: follow this rule!", "speaker": "S0"},
            {"start": 45.0, "end": 55.0, "text": "Trust me, this is the trick.", "speaker": "S0"},
        ]
        # No prior clips
        self._write_job(job_id, transcript, existing_clips=[])

        # New render produced a clip dict
        new_clip = {
            "title": "The secret that changes everything",
            "segments": [
                {"start": "00:00:15", "end": "00:00:25", "segment_role": "hook"},
                {"start": "00:00:25", "end": "00:00:55", "segment_role": "body"},
            ],
            "duration_seconds": 40.0,
            "path": "/tmp/output.mp4",
        }

        update_job_clips(job_id, [new_clip])

        # Reload and assert
        with (Path(self._tmp.name) / f"{job_id}.json").open() as f:
            d = json.load(f)
        clip = d["generated_clips"][0]
        # The key assertion: the clip is NOT all zeros anymore
        self.assertNotEqual(clip["viral_share_prob"], 0.0)
        self.assertNotEqual(clip["viral_composite"], 0.0)
        self.assertEqual(clip["viral_model_version"], "heuristic-v1")
        self.assertGreater(clip["viral_share_prob"], 0.2)
        self.assertGreater(clip["viral_composite"], 0.2)
        # output_path preserved
        self.assertEqual(clip["output_path"], "/tmp/output.mp4")

    def test_clip_with_prior_viral_keeps_its_values(self):
        """We must not clobber an existing prior prediction. A clip that
        was scored during the first save should keep those exact values
        after the render update."""
        from core.job_data_manager import update_job_clips

        job_id = "test_job_002"
        transcript = [
            {"start": 0.0, "end": 5.0, "text": "Hello world.", "speaker": "S0"},
        ]
        prior_clip = {
            "id": "clip_1",
            "title": "Already scored",
            "viral_share_prob": 0.42,
            "viral_save_prob": 0.55,
            "viral_comment_prob": 0.30,
            "viral_composite": 0.44,
            "viral_model_version": "heuristic-v1",
            "viral_features": {"hook_pattern_interrupt": 0.5},
            "boundary_confidence": 0.8,
            "output_path": "/tmp/old.mp4",
        }
        self._write_job(job_id, transcript, existing_clips=[prior_clip])

        new_clip = {
            "title": "Already scored",
            "segments": [{"start": "0", "end": "5"}],
            "duration_seconds": 5.0,
            "path": "/tmp/new.mp4",
        }
        update_job_clips(job_id, [new_clip])

        with (Path(self._tmp.name) / f"{job_id}.json").open() as f:
            d = json.load(f)
        clip = d["generated_clips"][0]
        self.assertAlmostEqual(clip["viral_share_prob"], 0.42, places=4)
        self.assertAlmostEqual(clip["viral_composite"], 0.44, places=4)
        self.assertEqual(clip["viral_model_version"], "heuristic-v1")
        self.assertEqual(clip["output_path"], "/tmp/new.mp4")


if __name__ == "__main__":
    unittest.main()
