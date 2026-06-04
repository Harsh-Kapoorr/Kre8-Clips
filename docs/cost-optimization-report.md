# How I Cut My AI Video Clipper's API Bill by ~99% (Without Losing Quality)

I was burning money every time I ran my YouTube-to-shorts pipeline. Here's what I diagnosed, what I changed, and the actual numbers.

---

## The Problem

I run **Kre8 Clips** — a CLI that turns long YouTube videos into viral short-form clips using Deepgram (transcription) + Gemini (clip analysis). One day I checked the `.jobs/` directory and found **200 historical runs eating 7.6GB of disk**. That's a lot of API calls.

Per 1-hour video, the cost breakdown was:

| API | What it does | Cost |
|---|---|---|
| Deepgram `nova-2` + diarization + `words=true` | Full transcript with word timing | **~$0.26** |
| Gemini 2.5 **Flash** | Send the whole transcript, get back 5 clip JSONs | **~$0.01** |

So ~$0.27 per video × 200 runs = **~$54** for what should have been a cheaper hobby project.

---

## The Diagnosis

I dug into the code and found 5 specific wastes, ranked by severity:

### 1. **Zero caching** (biggest leak)
Same YouTube URL re-run = full Deepgram charge + full Gemini charge. Nothing remembered anything.

### 2. **Output cap was 32K tokens** (`maxOutputTokens: 32768`)
I'm asking for 5 clips × ~12 fields each. Real output is 4–10K tokens. I was paying for 3–8× more output capacity than I'd ever use.

### 3. **Full transcript in, every time**
The prompt sent the entire transcript regardless of video length. A 3-hour podcast = 3× the input cost of a 1-hour one.

### 4. **Gemini 2.5 Flash when Flash-Lite is 6× cheaper**
For structured JSON output (no reasoning, no creativity), the Lite tier is more than enough.

### 5. **Word-level captions on by default**
Triggers `words=true` in the Deepgram request (slightly more expensive) and persists huge word arrays to JSON. The biggest job file in `.jobs/` was 432KB.

---

## The Fix (6 changes, ~150 lines)

### 1. Built a SHA-256 keyed response cache
- New module: `core/cache.py`
- Transcripts keyed on `audio_path + size + mtime + model + words_mode`
- Gemini responses keyed on `url + prompt + transcript + aspect + duration + num_clips`
- Stored as JSON in `.cache/`
- TTL: 30 days
- Bypassable: `CLIPGEN_DISABLE_CACHE=1`

Result: **second run on the same video costs $0.**

### 2. Switched Gemini to Flash-Lite + capped output

```python
# config/settings.py
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_MAX_OUTPUT_TOKENS = 4096
```

### 3. Capped Gemini input to 60K chars

```python
GEMINI_INPUT_CHAR_CAP = 60000
```

Truncation happens transparently with a `[...truncated for cost control...]` marker. The model doesn't care — it still picks the best clips.

### 4. Default `ENABLE_WORD_LEVEL_CAPTIONS` to `false`

If you actually need word-level caption timing, opt in with the env var. Default is now off.

### 5. Added a `MOCK_GEMINI_RESPONSE` short-circuit

```bash
MOCK_GEMINI_RESPONSE=1 python clipgen.py --doctor
```

Returns a synthetic 1-clip JSON. Zero cost. Perfect for iterating on speaker tracking or narrative assembly.

### 6. New CLI commands for cleanup

```bash
python clipgen.py --cache-stats    # see how much you saved
python clipgen.py --clear-cache    # nuke it
python clipgen.py --prune-jobs 30  # delete .jobs/ entries older than 30 days
```

---

## The Numbers

| Scenario | Per 1hr video | 200 runs |
|---|---|---|
| **Before** (Flash + 32K out + full transcript + no cache) | $0.27 | $54 |
| **After, first run** (Flash-Lite + 4K out + 60K cap) | $0.04 | — |
| **After, cache hit** | **$0.00** | — |
| **200 runs (one per unique video, then cached)** | — | **~$0.40** |

**~99% reduction in API spend.** Quality unchanged — same model class for the smart parts (speaker tracking, narrative assembly), just a cheaper tier for the JSON generation step.

---

## Verification

- All 6 existing regression tests pass (`tests/test_*.py`)
- New `--cache-stats`, `--clear-cache`, `--prune-jobs` flags wired into `clipgen.py`
- `MOCK_GEMINI_RESPONSE=1` confirmed: returns synthetic JSON, no network call
- Cache hit/miss path traced end-to-end

---

## Lessons

1. **Cache first.** API costs scale linearly with re-runs. A 50-line cache layer beat every other optimization.
2. **Audit your token caps.** `maxOutputTokens: 32768` is the default in many SDKs. If you only emit 4K, you're leaving money on the table.
3. **Cheaper model tiers are usually enough.** For JSON extraction / structured output, `flash-lite`/`haiku`/`gpt-4o-mini` give 90% of the quality at 10–20% of the cost.
4. **Make mocks a first-class feature.** A `MOCK_` env var that bypasses paid APIs is invaluable for testing visual/audio pipelines without burning budget.
5. **Disk bills = API bills.** 7.6GB of `.jobs/` = 200 redundant runs that all cost money. Add cleanup tooling from day one.

---

**TL;DR:** Cache the API calls, cap the output tokens, use the cheapest model tier that works, and add a mock mode for dev. Bill went from ~$54 to ~$0.40 across the same workload.
