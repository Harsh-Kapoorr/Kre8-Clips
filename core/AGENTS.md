# Core — Agent Guide

> `core/` is the heart of Kre8 Clips. 23 files, no `__init__` exports, each module a self-contained service.

## What you can do

- Add a new module as `core/<feature>.py`. Import settings via `from config.settings import …`.
- Add a new `GeneratedClip` field in `core/job_data_schema.py:GeneratedClip` AND `frontend/types/index.ts:GeneratedClip` (see root AGENTS.md "Schemas stay parallel").
- Add a new step label to `STEP_LABELS` in `utils/progress.py` so the Next.js progress bar (`frontend/components/pipeline-progress.tsx:getStepIndex`) recognizes it.
- Add a new env-driven flag to `config/settings.py` (one line, env + default) and document in `.env.example`.
- Use `print_step()` / `print_success()` from `utils/progress.py` for output. Never raw `print()` for pipeline progress.

## What you CANNOT do

- **NEVER** add a Flask/FastAPI/uvicorn import. This is a CLI. The Next.js backend spawns it.
- **NEVER** call `os.getenv` directly in a module. Always `from config.settings import …`.
- **NEVER** hand-edit `WEIGHTS` or `BIAS` in `viral_model.py` without running `tests/test_viral_model.py` and confirming the calibration tests pass.
- **NEVER** ship a `SpeakerTracker` change without calling `.reset()` between videos. `tests/test_speaker_tracking_regression.py` will fail and lock you out.
- **NEVER** write a clip to `output/` when `args.job_dir` is set. The web API always passes `--job-dir .jobs/<id>/`.
- **NEVER** invent a parallel source of progress truth. The JSONL sidecar (`.jobs/<id>.progress.jsonl`) is canonical.
- **NEVER** read or write `.jobs/<id>.json` outside `core/job_data_manager.py`. Use `load_job_data` / `save_job_data` / `update_job_clips` so frontend-managed fields are preserved.
- **NEVER** re-encode a clip that `_can_stream_copy()` would remux. The fast path is correct and intentional.
- **NEVER** import a module that requires `assets/face_landmarker_v2_with_blendshapes.task` at module top level. Lazy-import inside functions so `--doctor` runs without it.

## State-isolation contract (the single most violated rule)

`SpeakerTracker`, `ViralityAnalyzer`, `BoundarySnapper`, and `CaptionGenerator` are all per-video stateful. Each one must either:

1. Be a **new instance per video** (preferred), OR
2. Have an explicit `reset()` method called from `clipgen.py:run_clipgen` before processing the next video.

The current `SpeakerTracker` is a long-lived instance and uses `reset()`. If you add a field, add a `reset()` line. `tests/test_speaker_tracking_regression.py` is the canary.

## ffmpeg patterns

- **Stream-copy fast path:** `_can_stream_copy()` in `clipper.py` decides `-c copy` vs re-encode. Returns True when source/target aspect, container, and codec all line up. Don't "fix" it; the seek-is-keyframe-aligned trade-off is intentional.
- **Fade curves:** ffmpeg `fade` filter names: `tri, qua, cub, squ, cbr, par, exp, lin, sin, cos, log, ipar` (plus `in_`-prefixed inversions). The `in_` prefix is **invalid for `afade`** and silently falls back to linear; we only use `in_` for the video fade.
- **Filter escaping:** the `apply_clip_fades` helper composes the fade filter; use `_sanitize_curve` to reject unknown curve names. Test in `tests/test_clipgen_runtime_helpers.py`.
- **Two-pass for portrait crop:** `generate_clip_with_tracking` does a face-position pass then a crop+encode pass. Don't try to do it in one.

## Gemini response parsing

`core/analyzer.py:parse_clip_response` is the JSON-repair entry point. Gemini sometimes wraps JSON in ```json … ``` fences, sometimes returns trailing commas, sometimes returns nothing. The parser is forgiving on purpose.

The fallback `_mock_response` in the same file is the **offline test mode**. Don't delete it; `MOCK_GEMINI_RESPONSE=1` is how the test suite runs without a key.

## Job data lifecycle (the "two save" pattern)

1. `run_clipgen` builds `JobData` in memory, generates clips, calls `save_job_data(...)` once. This writes `.jobs/<id>.json` with the full transcript + analysis + clips (no viral predictions yet, because smart-narrative assembly runs *after* this save).
2. `assemble_smart_narrative()` may add one new clip.
3. `update_job_clips(...)` is called: it merges new clips with prior ones, preserving render-time fields (`output_path`, `reliability_score`) **and** prior viral predictions, then computes predictions for any new smart-narrative clip.

The "clip with no prior viral" branch in `update_job_clips` is the actively-tested repair path. If you change the merge logic, you break it.

## Verification

Before claiming a `core/` change is done:

1. `python -m py_compile core/<file>.py` exits 0.
2. The targeted test passes: `python -m unittest tests.test_<feature> -v`.
3. If you changed the viral predictor or speaker tracker, run their regression suites — these have historically regressed silently.
4. If you changed `job_data_schema.py`, the TS mirror is updated and `frontend/tests/` still passes.
5. `python clipgen.py --doctor` exits 0 (catches missing assets, missing keys, missing system tools).
