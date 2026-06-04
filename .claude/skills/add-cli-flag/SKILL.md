---
name: add-cli-flag
description: Add a new command-line flag to `clipgen.py` and wire it through the pipeline. Use when the user asks to expose a new setting as a CLI argument, or when plumbing a `config/settings.py` flag into the run.
---

# Add a CLI flag

`clipgen.py` uses `argparse`. The flags fall into 3 categories.

### Part 1: Pick the right category

- **One-off runtime flag** (e.g. `--max-clips 5`): top-level argparse, parsed in `main()`.
- **Pipeline step flag** (e.g. `--captions`, `--narrative`): top-level argparse, threaded through `run_clipgen(url, *, new_flag, ...)`.
- **Config override flag** (e.g. `--doctor`, `--clear-cache`): top-level argparse, handles its own sub-routine.

### Part 2: Register the flag

In `clipgen.py:main()`, find the argparse block (search for `parser = argparse.ArgumentParser`). Add the flag with `help=` text and `default=` matching the corresponding `config/settings.py` value.

```python
parser.add_argument(
    "--new-flag",
    type=str,
    default=None,  # or bool for store_true
    help="One-line description. (default: from NEW_FLAG env var)",
)
```

### Part 3: Thread it through

If the flag controls pipeline behavior, pass it as a keyword argument to `run_clipgen(...)`. Then propagate to the relevant `core/` module.

If the flag maps directly to a `config/settings.py` value, prefer:

```python
arg = args.new_flag or NEW_FLAG
```

— so the CLI wins, the env var is the fallback.

### Part 4: Update the help text and `run_clipgen` signature

- `python clipgen.py --help` must show the new flag.
- The function signature in `clipgen.py:run_clipgen(...)` gains a keyword argument.

### Part 5: Update the Next.js spawn call

`frontend/app/api/jobs/route.ts:createJob` builds the args array passed to `spawn`. If the flag should be settable from the web UI, also add it to `frontend/types/index.ts:GenerationOptions` and thread it through `createJob`.

### Verification

1. `python -m py_compile clipgen.py`
2. `python clipgen.py --help | grep new-flag` — flag appears
3. `python clipgen.py --new-flag <value> "https://..." --dry-run` — runs without error (or wire up a `--dry-run` if missing)
4. `cd frontend && npm run build` — typecheck if the TS surface changed
