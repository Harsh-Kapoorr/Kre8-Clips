---
name: add-clip-field
description: Add a new field to the GeneratedClip dataclass and mirror it in the TypeScript schema. Use when the user asks to surface new metadata on a clip (e.g. a new virality dimension, a new quality signal, a new platform export flag).
---

# Add a `GeneratedClip` field

The Python dataclass and the TS interface must change in the same commit. Three files, plus tests.

### Part 1: Python dataclass

`core/job_data_schema.py:GeneratedClip` — add the field with a default value:

```python
@dataclass
class GeneratedClip:
    # … existing fields …
    new_field: Optional[float] = None
```

Use `Optional[T]` and a `None` default for backward-compat with old `.jobs/*.json` files.

### Part 2: Python assignment

Find where `GeneratedClip` is constructed in `core/analyzer.py`, `core/clipper.py`, and `clipgen.py`. Populate the new field with a meaningful value at each construction site. The dataclass's `asdict` will then serialize it.

### Part 3: TypeScript mirror

`frontend/types/index.ts:GeneratedClip` — add the matching field. Pick the right type:

- `number` for floats/ints
- `string` for strings
- `string | null` for optional strings (the Python side emits `None` → JSON `null`)
- `boolean` for booleans
- nested interface for objects (mirror the Python sub-dataclass)

### Part 4: UI surface

If the new field should render in the UI:

- Add it to `frontend/components/clip-card.tsx` (or wherever the clip is shown).
- Add a small bar/component rather than just dumping the value.
- If it's a probability ∈ [0,1], use the `<ViralScore />` pattern (see `components/viral-score.tsx`).

### Part 5: Tests

- Add a `tests/test_<feature>.py` case that constructs a `GeneratedClip` with the new field and asserts it round-trips through `save_job_data` / `load_job_data`.
- If the field is a derived signal (like a virality score), the test must cover the empty-input case so calibration regressions are caught.

### Verification

1. `python -m py_compile core/job_data_schema.py core/<changed>.py clipgen.py`
2. `cd frontend && npm run build` — TS typecheck
3. `python -m unittest tests.test_<new_feature> -v`
4. Run a real job end-to-end with `MOCK_GEMINI_RESPONSE=1` and confirm the new field appears in `.jobs/<id>.json`.

### What you MUST NOT do

- Do NOT add a field only in Python. The UI will silently drop it.
- Do NOT add a field only in TS. The Python side will not populate it and the TS type will lie.
- Do NOT use `Any` in the TS type. Use the precise type or `unknown` + a narrowing helper.
