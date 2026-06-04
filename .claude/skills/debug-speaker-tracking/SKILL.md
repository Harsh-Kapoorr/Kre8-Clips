---
name: debug-speaker-tracking
description: Debug a speaker-tracking regression (face crop jitters, wrong speaker followed, state leak between videos, face detection fails). Use when the user reports bad portrait crops, jitter, or the regression test fails.
---

# Debug speaker tracking

The tracking pipeline is 5 phases: face detection → embedding → multi-hypothesis → Kalman → audio-visual fusion. Most bugs are state leaks, not algorithm bugs.

### Part 1: Run the regression test first

```bash
python -m unittest tests.test_speaker_tracking_regression.py -v
```

If this fails, the regression suite has caught a real bug. Read the failure message — it usually points at the missing `reset()` line.

### Part 2: Check the state-isolation contract

Open `core/speaker_tracker.py` and find `SpeakerTracker.reset()`. Every instance attribute that accumulates across clips MUST be reset here. The current reset covers:

- Frame counter
- Embedding cache
- Hypothesis probabilities
- Kalman state
- Last known positions

If you added a new field to `SpeakerTracker.__init__`, you MUST add a corresponding line to `reset()`. The regression test `test_multi_clip_state_isolation` is the canary.

### Part 3: Check the asset is present

```bash
ls assets/face_landmarker_v2_with_blendshapes.task
```

If this file is missing, speaker tracking silently no-ops (it lazy-imports the asset so `--doctor` doesn't crash). The doctor check is:

```bash
python clipgen.py --doctor
```

— it should report "speaker tracking: ready". If it doesn't, the asset is missing or the model version mismatched.

### Part 4: Check the debug snapshot

When `ENABLE_TRACKING_DEBUG=true` (the default), `SpeakerTracker.export_debug_snapshot()` writes `.jobs/<id>.tracking.json` per clip. Open it. It contains:

- Detected face positions per frame
- Hypothesis probabilities over time
- Active-speaker decision log
- Audio-visual fusion scores

If the active speaker is "switching too often", look at the hypothesis probabilities — if the top-2 are within 0.1 of each other for many frames, the smoother should hold the previous choice. If the smoother is switching anyway, check the `SPEAKER_TRACKING_SMOOTHING` env var (default 0.3).

### Part 5: Check the ffmpeg crop command

`core/clipper.py:generate_clip_with_tracking` runs a 2-pass render: pass 1 detects face positions; pass 2 crops + encodes. If the output video is jittery, the crop coordinates are changing between frames. Look at the smoothing curve in the debug snapshot — if it's spiky, the OneEuroFilter cutoff frequency is too high. Try `SPEAKER_TRACKING_SMOOTHING=0.6` and re-run.

### Part 6: If all else fails, run with `ENABLE_SPEAKER_TRACKING=false`

```bash
ENABLE_SPEAKER_TRACKING=false python clipgen.py "..."
```

This skips the tracking pipeline and renders the source video at the target aspect ratio without cropping. If the output is now correct, the bug is in the tracking pipeline. If it's still wrong, the bug is elsewhere (clip boundaries, ffmpeg args, etc.).

### What you MUST NOT do

- Do NOT change `EMBEDDING_MATCH_WEIGHT` (default 0.65) without re-running the regression suite. It is calibrated.
- Do NOT bypass `reset()` "temporarily" to make a test pass. The test exists to catch the bug pattern; if the test fails, fix the code.
- Do NOT delete the `.task` asset from the repo. The MediaPipe model is required.

### Verification

1. `python -m unittest tests.test_speaker_tracking_regression.py -v` — passes
2. `python -m py_compile core/speaker_tracker.py` — no syntax errors
3. Run a 2-video batch. Inspect both `.jobs/<id>.tracking.json` files. The second one MUST show frame counter = 0 in its first frame.
