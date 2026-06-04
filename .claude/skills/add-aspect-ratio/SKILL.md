---
name: add-aspect-ratio
description: Add a new output aspect ratio (e.g. 4:5, 1:1, 21:9) to Kre8 Clips. Use when the user asks for a new aspect ratio or when the user asks to add Instagram portrait, square, or ultra-wide support.
---

# Add a new aspect ratio

Adding a new aspect ratio touches 4 files. Do all 4 in one commit.

### Part 1: Register in `config/settings.py`

The default is set in `DEFAULT_ASPECT_RATIO`. Add the new value to the inline comment that lists the supported values:

```python
DEFAULT_ASPECT_RATIO = os.getenv("DEFAULT_ASPECT_RATIO", "9:16")  # 9:16, 16:9, 1:1, 4:5
```

### Part 2: Implement dimensions in `core/clipper.py`

`get_target_dimensions(aspect_ratio: str) -> tuple[int, int]` is the canonical place. The currently supported set (verified):

- `9:16` (1080×1920) — TikTok, Reels, Shorts
- `16:9` (1920×1080) — YouTube
- `1:1` (1080×1080) — Instagram square
- `4:5` (1080×1350) — Instagram portrait

Add a branch for the new ratio. The aspect-ratio choices list in `clipgen.py`'s argparse (`--aspect-ratio {9:16,16:9,1:1,4:5}`) must be updated to include the new value, otherwise the CLI will reject the input. Reject unknown values with a clear `ValueError` listing the supported set.

### Part 3: Update `frontend/components/options-panel.tsx`

Find the aspect-ratio selector and add the new option. Keep the order: 9:16, 1:1, 4:5, 16:9, 21:9.

### Part 4: Update `_can_stream_copy` if needed

The fast-path check uses target dimensions. If the new aspect is supported by the source-resolution matrix the check already considers, no change. Otherwise add a branch.

### Verification

1. `python -m py_compile config/settings.py core/clipper.py`
2. `cd frontend && npm run build` — typecheck the new selector
3. `python clipgen.py --doctor` — no regressions
4. `python -m unittest tests.test_clipgen_runtime_helpers.py -v` — `_can_stream_copy` tests still pass
5. If new dimensions, add a test case for `get_target_dimensions("<new ratio>")` returning the expected tuple.
