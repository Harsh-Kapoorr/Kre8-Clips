# Kre8 Clips — Agent Constitution

## What this is

Kre8 Clips turns a YouTube URL into N short-form clips. One Python pipeline (`clipgen.py`), three clients: the CLI, a Streamlit dashboard, and a Next.js 16 web app. The Next.js API `spawn()`s the CLI as a subprocess — there is no Python HTTP server.

Pipeline: URL → Download → Extract Audio → Transcribe (Deepgram) → Analyze (Gemini) → Render (ffmpeg) → Clips.

## What you can do

- Add modules to `core/<feature>.py`. Import settings via `from config.settings import …` (never `os.getenv` directly).
- Add env-driven flags to `config/settings.py` (one line, env + default) and document in `.env.example`.
- Add `GeneratedClip` fields to BOTH `core/job_data_schema.py` AND `frontend/types/index.ts:GeneratedClip` — they must stay parallel.
- Add tests as `tests/test_<feature>.py` using `unittest.TestCase` (the project uses `unittest`; one pytest file is a deliberate exception).
- Emit progress via `print_step()` / `print_success()` from `utils/progress.py`. The JSONL sidecar (`.jobs/<id>.progress.jsonl`) is the source of truth for progress.
- Add new step labels via `STEP_LABELS` in `utils/progress.py` so the Next.js progress bar (`frontend/components/pipeline-progress.tsx`) recognizes them.

## What you CANNOT do

- **NEVER** refactor toward a Python HTTP server (Flask, FastAPI, uvicorn). The Next.js backend spawns the CLI; that is the architecture.
- **NEVER** add a linter, formatter, or CI workflow without asking. The project runs `python -m py_compile` only.
- **NEVER** change `prompts/system_prompt_viral.txt` casually. Single-word edits have changed global clip quality. If AI clips are bad, suspect the prompt first. Use the `.claude/skills/edit-prompt-template/SKILL.md` skill.
- **NEVER** hand-edit `BIAS` or `WEIGHTS` in `core/viral_model.py`. They are hand-tuned; `tests/test_viral_model.py` locks the calibration in.
- **NEVER** skip `SpeakerTracker.reset()` between videos. `tests/test_speaker_tracking_regression.py:test_multi_clip_state_isolation` is the canary.
- **NEVER** write to `output/` when `--job-dir` is set. The Next.js API passes `--job-dir .jobs/<id>/`; the static-file route serves from there.
- **NEVER** invent a new "source of truth" for progress. The JSONL sidecar is canonical. The regex parser in the API route is a fallback for legacy jobs.
- **NEVER** use destructive git operations (`reset --hard`, `clean -fd`, `push --force` to shared branches) without explicit user approval.
- **NEVER** run `git push` without the user typing the exact command in chat. Local commits are fine.
- **NEVER** commit `.env`, API keys, or any value matching `sk-` / `AIza` / `AIzaSy` / `ghp_`.

## Architecture invariants

- **Settings live in one place.** `config/settings.py` is the only source. Never `os.getenv` in a module.
- **Schemas stay parallel.** `core/job_data_schema.py` (Python dataclasses) ↔ `frontend/types/index.ts` (TS interfaces). Every new `GeneratedClip` field appears in both, in the same commit, or the UI silently drops it.
- **The pipeline is sequential per video.** Within a video the steps depend on each other. Across videos is fine.
- **`_can_stream_copy()` is the fast path.** When source/target aspect, container, and codec line up, the clipper uses `-c copy`. Source videos with sparse keyframes → output may extend a few hundred ms; this is intentional. Do not "fix" by re-encoding.
- **The sidecar-first progress pattern.** `utils/progress.py` writes structured events to `.jobs/<id>.progress.jsonl`. The SSE endpoint polls the last line every 500 ms.
- **`update_job_clips()` preserves prior viral fields** and recomputes for new smart-narrative clips. The "clip with no prior viral" branch in `core/job_data_manager.py` is the actively-tested repair path.
- **No project-wide linter.** `py_compile` is the closest thing. Don't add one silently.

## Verification (the goal as a verifiable signal)

Before claiming a change is done, confirm:

1. The targeted test passes: `python -m unittest tests.test_<feature> -v`
2. `python -m py_compile <every_file_you_touched>` exits 0
3. `python clipgen.py --doctor` reports 4/4 checks pass
4. If a CLI flag changed: `python clipgen.py --help` shows it
5. If a frontend field changed: `cd frontend && npm run build` succeeds; the TS mirror is updated

For the viral predictor or speaker tracker, also run the regression suite — these have historically regressed silently:

```bash
python -m unittest tests.test_viral_model tests.test_viral_prediction_pipeline -v
python -m unittest tests.test_speaker_tracking_regression -v
```

## Conventions

- Python: `snake_case` functions, `PascalCase` classes, dataclasses for plain data
- Filenames: `snake_case.py`
- Frontend components: `kebab-case.tsx`, types `PascalCase` (no `I`-prefix)
- Time format: `HH:MM:SS` (Gemini) · `HH:MM:SS.mmm` (ffmpeg) · `MM:SS` (UI display)
- Job IDs: 8-char UUID prefix
- Severity vocabulary: `ALWAYS` / `NEVER` / `PREFER` / `AVOID` — pick one and use consistently
- Progress output: `print_step()` from `utils/progress.py`, not raw `print()`
