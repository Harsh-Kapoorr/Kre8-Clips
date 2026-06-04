---
name: edit-prompt-template
description: Edit `prompts/system_prompt_viral.txt` (the production Gemini prompt). Use ONLY when AI clip quality is bad and the user has asked to change the prompt. Editing the prompt is the highest-leverage change in the codebase — it changes global clip quality. Do not edit casually.
---

# Edit the Gemini prompt

The production prompt is `prompts/system_prompt_viral.txt`. There is also a legacy `prompts/system_prompt.txt` (simpler) which is used when `ENABLE_VIRALITY_SCORING=false`.

### Part 1: Identify the failure mode first

Before editing, gather signal:

1. Look at recent jobs in `.jobs/*.json` and read the `ai_analysis.segments[]` — are the timestamps wrong? Are `segment_role` labels wrong? Are `opening_strength`/`closing_strength` scores flat? Are the suggested durations wrong for the platform?
2. Look at `.training/clipgen_feedback.jsonl` — what did users thumb-down on?
3. Run `python -m unittest tests.test_clipgen_runtime_helpers.py -v` to make sure the JSON parsing tests still pass before changing the prompt.

### Part 2: Make the smallest possible edit

The prompt is tuned. Single-word changes have changed global clip quality. PREFER:

- Adding a single rule ("… MUST end on a sentence boundary")
- Tightening an existing rule ("… `opening_strength` 1-10, calibrated such that 8+ means the first 3 seconds would stop a mid-scroll viewer")
- Removing a rule that's confusing Gemini

AVOID:

- Rewriting more than 10% of the prompt in one change
- Removing the JSON shape section — `parse_clip_response` depends on it
- Adding examples that are too long (>200 words of example)

### Part 3: Verify the JSON shape is preserved

The prompt ends with a `Output JSON shape:` block. The Python parser in `core/analyzer.py:parse_clip_response` depends on the exact field names. Run:

```bash
python -m unittest tests.test_clipgen_runtime_helpers.py -v
```

If the parser tests fail, the prompt and the parser are out of sync — fix the prompt, not the parser, unless the field is genuinely deprecated.

### Part 4: A/B test by running the same video twice

Before/after a prompt change, run the same YouTube URL twice (with cache cleared for that fingerprint). Compare:

- Number of clips returned
- Distribution of `opening_strength` / `closing_strength` / `viral_potential`
- Distribution of `segment_role` (hook / body / payoff)
- Average suggested duration vs. `SMART_NARRATIVE_MIN_DURATION` … `MAX_DURATION`

### What you MUST NOT do

- Do NOT edit the prompt to "see what happens" without a measurable hypothesis first.
- Do NOT delete the JSON shape section.
- Do NOT introduce platform-specific copy that contradicts `DEFAULT_PLATFORM` (the user can override per-clip).
- Do NOT use the legacy `system_prompt.txt` for production. Switch `ENABLE_VIRALITY_SCORING=true`.

### Verification

1. `python -m unittest tests.test_clipgen_runtime_helpers.py -v` — JSON parsing still works
2. `python -m unittest tests.test_viral_prediction_pipeline.py -v` — pipeline still wires up
3. Run a real job with a known-good video. Inspect the output clips. If the `opening_strength` distribution skews <5 across the board, the prompt is now too lenient.
