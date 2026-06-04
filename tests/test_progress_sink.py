import json
import tempfile
import unittest
from pathlib import Path

from utils import progress as progress_mod
from utils.progress import (
    MAX_ETA_SECONDS,
    _write_progress,
    print_step,
    set_progress_sink,
)


class ProgressSinkTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.sink_path = self.tmp_path / "test.progress.jsonl"
        set_progress_sink(str(self.sink_path))

    def tearDown(self):
        set_progress_sink(None)
        self._tmp.cleanup()

    def test_print_step_writes_structured_event(self):
        print_step(2, 7, "Downloading video")
        self.assertTrue(self.sink_path.exists())
        lines = self.sink_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(payload["step"], "Downloading")
        self.assertAlmostEqual(payload["progress"], 1.5 / 7, places=5)
        self.assertEqual(payload["step_detail"], "Downloading video")

    def test_print_step_appends_multiple_lines(self):
        print_step(1, 7, "Validating URL and dependencies")
        print_step(2, 7, "Downloading video")
        print_step(3, 7, "Extracting audio")
        lines = self.sink_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        first = json.loads(lines[0])
        last = json.loads(lines[-1])
        self.assertEqual(first["step"], "Validating")
        self.assertEqual(first["step_detail"], "Validating URL and dependencies")
        self.assertEqual(last["step"], "Extracting Audio")
        self.assertEqual(last["step_detail"], "Extracting audio")

    def test_write_progress_helper_writes_event(self):
        _write_progress("Custom", 0.42, "detail here")
        lines = self.sink_path.read_text(encoding="utf-8").splitlines()
        payload = json.loads(lines[-1])
        self.assertEqual(payload["step"], "Custom")
        self.assertEqual(payload["progress"], 0.42)
        self.assertEqual(payload["step_detail"], "detail here")

    def test_cleared_sink_does_not_write(self):
        set_progress_sink(None)
        print_step(1, 7, "Validating")
        self.assertFalse(self.sink_path.exists())

    def test_unwritable_sink_does_not_raise(self):
        """An OSError on the sink path must be swallowed (regex fallback)."""
        # Point the sink at a path inside a non-existent directory; the open()
        # will fail with FileNotFoundError (a subclass of OSError).
        bad_path = self.tmp_path / "does" / "not" / "exist" / "sink.jsonl"
        set_progress_sink(str(bad_path))
        # Must not raise. Calling print_step exercises the full write path.
        print_step(1, 7, "Validating")
        # And the helper directly:
        _write_progress("Custom", 0.5, "detail")

    def test_unwritable_sink_does_not_corrupt_next_sink(self):
        """A failed sink must not poison a subsequent valid sink."""
        bad_path = self.tmp_path / "missing" / "sink.jsonl"
        set_progress_sink(str(bad_path))
        print_step(1, 7, "this should be swallowed")

        # Switch to a valid sink. The first failure must not block subsequent
        # writes (the warning latch resets when a new sink is set).
        good_path = self.tmp_path / "good_sink.jsonl"
        set_progress_sink(str(good_path))
        print_step(2, 7, "this should land")

        self.assertTrue(good_path.exists())
        lines = good_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(payload["step"], "Downloading")


class ProgressSinkTimingTest(unittest.TestCase):
    """Verify the timing fields that drive the frontend remaining-time UI."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.sink_path = self.tmp_path / "timing.progress.jsonl"

        # Deterministic clock so we don't need real sleeps. Each tick() call
        # advances the simulated time by the given number of seconds.
        self._now = 1000.0
        progress_mod._time_fn = lambda: self._now
        # set_progress_sink uses the patched clock to initialise its baseline,
        # so call it after the patch is in place.
        set_progress_sink(str(self.sink_path))

    def tearDown(self):
        set_progress_sink(None)
        progress_mod._time_fn = progress_mod.time.monotonic
        self._tmp.cleanup()

    def tick(self, seconds: float) -> None:
        self._now += seconds

    def _events(self):
        return [
            json.loads(line)
            for line in self.sink_path.read_text(encoding="utf-8").splitlines()
        ]

    def test_first_event_has_no_eta_because_elapsed_is_zero(self):
        # At t=0 we have no useful sample to extrapolate from, so eta_s must
        # be absent rather than a misleading 0 or huge extrapolation.
        print_step(1, 7, "Validating URL and dependencies")
        ev = self._events()[0]
        self.assertEqual(ev["elapsed_s"], 0.0)
        self.assertIsNone(ev["eta_s"])
        self.assertFalse(ev["eta_capped"])
        self.assertIsNone(ev["last_step_duration_s"])

    def test_eta_is_reasonable_after_real_progress(self):
        # Mimic a normal run: step 1 finishes after ~5s, step 2 starts. With
        # progress=1.5/7=0.214 and elapsed=5s the formula predicts ~18.3s
        # remaining. Confirm the value lands in a sensible window and is not
        # clamped to the cap.
        print_step(1, 7, "Validating")
        self.tick(5.0)
        print_step(2, 7, "Downloading video")

        ev = self._events()[-1]
        self.assertAlmostEqual(ev["elapsed_s"], 5.0, places=3)
        self.assertAlmostEqual(ev["last_step_duration_s"], 5.0, places=3)
        self.assertIsNotNone(ev["eta_s"])
        # 5 * (7/1.5 - 1) ≈ 18.33
        self.assertGreater(ev["eta_s"], 10.0)
        self.assertLess(ev["eta_s"], 30.0)
        self.assertFalse(ev["eta_capped"])

    def test_eta_decreases_as_more_steps_complete(self):
        # As the job progresses (each step takes a uniform 5s), the predicted
        # remaining time must shrink monotonically — the whole point of the
        # self-correcting formula.
        print_step(1, 7, "Validating")
        self.tick(5.0)
        print_step(2, 7, "Downloading")
        self.tick(5.0)
        print_step(3, 7, "Extracting Audio")
        self.tick(5.0)
        print_step(4, 7, "Transcribing")

        etas = [e["eta_s"] for e in self._events()]
        # The first event has no ETA (elapsed=0); skip it.
        usable = [e for e in etas if e is not None]
        self.assertGreaterEqual(len(usable), 3)
        for earlier, later in zip(usable, usable[1:]):
            self.assertGreater(earlier, later)

    def test_eta_capped_when_a_single_step_takes_far_too_long(self):
        # 100s on step 1 alone would naively project hundreds of seconds of
        # remaining work. The cap must trigger so the UI never shows that.
        print_step(1, 7, "Validating")
        self.tick(100.0)
        print_step(2, 7, "Downloading video")

        ev = self._events()[-1]
        # 100 * (7/1.5 - 1) ≈ 366.67, which exceeds MAX_ETA_SECONDS.
        self.assertEqual(ev["eta_s"], MAX_ETA_SECONDS)
        self.assertTrue(ev["eta_capped"])
        # The reported elapsed_s remains truthful even when the ETA is capped.
        self.assertAlmostEqual(ev["elapsed_s"], 100.0, places=3)

    def test_eta_zero_at_completion(self):
        print_step(1, 7, "Validating")
        self.tick(10.0)
        print_step(7, 7, "Complete")
        # progress for step 7 is (7 - 0.5)/7 = 0.928, not 1.0, so eta is a
        # small positive number rather than 0. Verify by injecting an explicit
        # 1.0 progress event via _write_progress so we exercise the
        # ``progress >= 1`` branch.
        _write_progress("Complete", 1.0, "all done")
        ev = self._events()[-1]
        self.assertEqual(ev["eta_s"], 0.0)
        self.assertFalse(ev["eta_capped"])

    def test_set_progress_sink_resets_timing_baseline(self):
        # Advance time and emit one event so _job_started_at is established.
        print_step(1, 7, "Validating")
        self.tick(30.0)
        print_step(2, 7, "Downloading")

        # Now point at a fresh sink — this must reset the timing baseline so
        # the next job's first event reports elapsed_s == 0 instead of 30s.
        new_sink = self.tmp_path / "second.progress.jsonl"
        set_progress_sink(str(new_sink))
        print_step(1, 7, "Validating again")

        payload = json.loads(new_sink.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(payload["elapsed_s"], 0.0)
        self.assertIsNone(payload["eta_s"])


if __name__ == "__main__":
    unittest.main()
