# Kre8 Clips

Kre8 Clips turns long-form YouTube videos into short-form clips with AI-assisted clip selection, Deepgram transcription, and optional speaker-aware vertical reframing for podcasts and interviews.

## What It Does

- Downloads a YouTube video with `yt-dlp`
- Extracts 16k mono audio with `ffmpeg`
- Transcribes speech with Deepgram diarization
- Sends the transcript to Gemini for clip selection
- Renders clips in `9:16`, `4:5`, `1:1`, or `16:9`
- Tracks visible speakers for portrait crops when multiple people are on screen
- Exports tracking debug snapshots for tuning difficult podcast layouts

## Setup

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Install system tools:

```bash
# macOS
brew install yt-dlp ffmpeg

# Ubuntu / Debian
sudo apt install yt-dlp ffmpeg
```

3. Configure environment variables:

```bash
cp .env.example .env
```

Required keys:
- `DEEPGRAM_API_KEY`
- `GEMINI_API_KEY`

Recommended flags:
- `ENABLE_SPEAKER_TRACKING=true`
- `ENABLE_TRACKING_DEBUG=true`

## Usage

Basic:

```bash
python clipgen.py "https://youtube.com/watch?v=..."
```

Podcast-friendly portrait clipping:

```bash
python clipgen.py "https://youtube.com/watch?v=..." \
  --aspect-ratio 9:16 \
  --min-duration 30 \
  --max-duration 90 \
  --captions
```

Interactive mode:

```bash
python clipgen.py
```

Health check:

```bash
python clipgen.py --doctor
```

## Smart Speaker Tracking

For multi-speaker portrait output, Kre8 Clips now:

- Detects faces with the bundled MediaPipe face landmarker asset
- Classifies the video layout (`split_two`, `single`, `single_dominant`, `dynamic_multi`)
- Maps diarized speakers to visible face tracks
- Follows the active speaker when confidence is high
- Falls back to stable speaker lanes when confidence is weak

When tracking is enabled, Kre8 Clips writes a debug snapshot like:

```text
output/<video_name>_tracking_debug.json
```

That file includes:
- layout classification
- speaker-to-track assignments
- confidence scores
- face sample snapshots
- timeline preview

## Regression Tests

The repo includes synthetic speaker-tracking regressions for podcast layouts:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Notes

- `--doctor` checks dependencies, API keys, speaker-tracking requirements, and regression tests.
- Portrait multi-speaker runs auto-enable speaker tracking.
- If tracking dependencies are missing, the run now fails early with actionable setup guidance instead of failing deep in the pipeline.
