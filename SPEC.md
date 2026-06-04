# Kre8 Clips — AI-Powered YouTube Video Clipper

## Concept & Vision

Kre8 Clips is an intelligent video clipping tool that transforms long-form YouTube content into engaging short-form clips. Unlike basic clipper tools that simply cut sequential segments, Kre8 Clips uses AI to understand narrative flow, detect viral-worthy hooks, and can intelligently rearrange non-contiguous clips to build compelling narratives. It feels like having a smart video editor that understands *storytelling*.

---

## Design Language

**Aesthetic Direction**: Terminal-first CLI tool with rich visual feedback. Dark mode by default, inspired by professional video editing tools (DaVinci Resolve, Premiere).

**Color Palette**:
- Primary: `#7C3AED` (Violet — action, creativity)
- Secondary: `#10B981` (Emerald — success, completion)
- Accent: `#F59E0B` (Amber — warnings, highlights)
- Background: `#0F172A` (Slate 900)
- Surface: `#1E293B` (Slate 800)
- Text Primary: `#F1F5F9` (Slate 100)
- Text Secondary: `#94A3B8` (Slate 400)
- Error: `#EF4444` (Red)

**Typography**:
- Headings: SF Mono Bold
- Body: SF Mono Regular
- Output/Status: SF Mono Light

**Spatial System**: 8px base grid. Generous padding in status outputs for readability.

**Motion Philosophy**:
- Progress indicators animate smoothly (no jarring jumps)
- Status messages fade in
- Final clip paths displayed with a subtle pulse animation

---

## Architecture

```
clipgen/
├── clipgen.py              # Main CLI entry point
├── core/
│   ├── __init__.py
│   ├── downloader.py        # YT-dlp video downloader
│   ├── extractor.py        # FFmpeg audio extractor
│   ├── transcriber.py       # DeepGram transcription
│   ├── analyzer.py         # MiniMax API integration
│   ├── clipper.py          # FFmpeg clip extraction
│   └── narrative.py         # Clip rearrangement engine
├── config/
│   ├── __init__.py
│   └── settings.py         # API keys, paths, defaults
├── utils/
│   ├── __init__.py
│   ├── progress.py          # Rich progress bars
│   └── validators.py        # URL/format validation
├── prompts/
│   └── system_prompt.txt   # MiniMax analysis prompt template
├── output/                  # Generated clips directory
└── temp/                    # Temporary files (audio, video chunks)
```

---

## Workflow States

### 1. INPUT PHASE
- User provides YouTube URL and optional prompt
- Validates URL format
- Checks for required dependencies (yt-dlp, ffmpeg)
- Checks for API keys (DeepGram, MiniMax)

### 2. DOWNLOAD PHASE
- `yt-dlp` downloads video to temp directory
- Shows real-time download progress (percentage, speed, ETA)
- Validates video has audio track
- Progress: `Downloading... ████████░░ 78% 12.4MB/s ETA 0:23`

### 3. EXTRACTION PHASE
- FFmpeg extracts audio track as 16kHz mono WAV (DeepGram optimized)
- Progress: `Extracting audio... ████████████████░░░░░░░░░░░░`

### 4. TRANSCRIPTION PHASE
- DeepGram CLI processes the WAV file
- Shows speaker diarization if available
- Returns timestamped transcript segments
- Progress: `Transcribing... ████████████████████████░░░░ 95%`

### 5. ANALYSIS PHASE
- Sends full transcript + user prompt to MiniMax API
- MiniMax returns structured clip definitions with:
  - `start_time`, `end_time`
  - `title` (suggested title)
  - `reason` (why this clip is compelling)
  - `priority` (1-10 viral potential score)
- Optional: clip arrangement for narrative flow

### 6. CLIPPING PHASE
- FFmpeg extracts each clip segment
- Outputs to `.mp4` (H.264) or `.mov` (ProRes) based on settings
- Naming: `{original_title}_clip_{index}_{timestamp}.{ext}`
- Shows individual clip progress, then overall progress

### 7. OUTPUT PHASE
- Displays all generated clips with:
  - File path
  - Duration
  - Suggested title
  - Priority score
- Option to open output folder

---

## MiniMax API Integration

### Request Format
```json
{
  "model": "minimax/video-01",
  "messages": [
    {
      "role": "system",
      "content": "[SYSTEM_PROMPT]"
    },
    {
      "role": "user",
      "content": "TASK: {user_prompt}\n\nTRANSCRIPT:\n{transcript_with_timestamps}"
    }
  ]
}
```

### System Prompt Template
```
You are an expert video clip analyst. Your job is to identify compelling segments from a transcript.

ANALYSIS RULES:
1. Look for hook-worthy openings: surprising statements, questions, bold claims
2. Identify self-contained moments: clips that make sense without full context
3. Detect emotional peaks: laughter, excitement, tension, revelation
4. Find quotable moments: lines people would share
5. Note: clips can be NON-CONTIGUOUS — you can suggest combining segments from different parts of the video if they together form a better narrative

CLIP OUTPUT FORMAT (JSON array):
[
  {
    "segments": [
      {"start": "00:02:15", "end": "00:02:45"},
      {"start": "00:05:30", "end": "00:05:55"}
    ],
    "title": "Suggested viral title",
    "reason": "Why this works as a clip",
    "priority": 9
  },
  ...
]

PRIORITY SCORING:
- 9-10: Absolute gold, instant viral potential
- 7-8: Very strong, worth posting
- 5-6: Good, could work with good thumbnail/title
- 1-4: Decent but probably skip

Return EXACTLY this JSON array, no additional text.
```

### User Prompt (from CLI)
Default: "Find the most engaging, viral-worthy moments that work as standalone clips."

Users can customize to find:
- "Clips about [topic]"
- "Funniest moments"
- "Most controversial takes"
- "Educational insights"
- "Q&A segments"

---

## Clipper Tool Behavior

### FFmpeg Extraction
```bash
# Single clip extraction
ffmpeg -i input.mp4 -ss {start} -to {end} \
  -c:v libx264 -c:a aac -b:a 192k \
  -movflags +faststart \
  output.mp4

# For reordered clips ( Narrative Mode):
# First extract each segment, then concatenate
```

### Narrative Mode
When MiniMax returns multiple segments for a single clip:
1. Extract each segment as individual clip
2. Concatenate in specified order using FFmpeg concat demuxer
3. Add smooth transition hint (crossfade 0.1s) if enabled

---

## CLI Interface

```bash
# Basic usage
python clipgen.py "https://youtube.com/watch?v=..."

# With custom prompt
python clipgen.py "https://youtube.com/watch?v=..." \
  --prompt "Find the funniest moments"

# Specify output format
python clipgen.py "..." --format mov

# Enable narrative mode (reorder clips)
python clipgen.py "..." --narrative

# Verbose mode
python clipgen.py "..." --verbose

# Show help
python clipgen.py --help
```

### Progress Output Example
```
╔══════════════════════════════════════════════════════════╗
║                    CLIPGEN v1.0.0                       ║
╚══════════════════════════════════════════════════════════╝

🎬 Input: https://youtube.com/watch?v=dQw4w9WgXcQ
📝 Prompt: Find the most engaging viral-worthy moments

[1/6] 📥 Downloading video...
         ████████████████████░░░░░░░░░░░░░ 67% 8.2MB/s

[2/6] 🔊 Extracting audio...
         ████████████████████████░░░░░░░░░ 83%

[3/6] 🎤 Transcribing with DeepGram...
         ████████████████████████████████ 100%

[4/6] 🤖 Analyzing with MiniMax...
         Sending 47 transcript segments...

[5/6] ✂️ Generating clips...
         Clip 1/4: "The moment everything changed" [00:02:15 - 00:02:45]
         ████████████████████░░░░░░░░░░░░░ 52%
         Clip 2/4: "This is genius" [00:05:30 - 00:06:10]
         ██████████████████████████████████ 100%
         ...

[6/6] ✅ Complete!

📁 Output: ./output/
├── Rick_Astley_Never_Gonna_Give_You_Up_clip_1_0215.mov
├── Rick_Astley_Never_Gonna_Give_You_Up_clip_2_0530.mov
└── ...

🎉 Generated 4 clips in 12.3 seconds
```

---

## Configuration (config/settings.py)

```python
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")

# Paths
TEMP_DIR = "./temp"
OUTPUT_DIR = "./output"

# FFmpeg settings
AUDIO_FORMAT = "wav"
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1

# Clip settings
DEFAULT_FORMAT = "mp4"  # or "mov"
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"
VIDEO_BITRATE = "8M"
AUDIO_BITRATE = "192k"

# MiniMax settings
MINIMAX_MODEL = "minimax/video-01"
MINIMAX_MAX_TOKENS = 4096

# Clipper behavior
NARRATIVE_MODE = False
CROSSFADE_DURATION = 0.1  # seconds
MAX_CLIP_DURATION = 60  # seconds (hard limit for shorts)
MIN_CLIP_DURATION = 3   # seconds
```

---

## Error Handling

| Error | User Message | Recovery |
|-------|--------------|----------|
| Invalid YouTube URL | "❌ Invalid YouTube URL format" | Show correct format hint |
| Video unavailable | "❌ Video is unavailable or age-restricted" | Exit |
| No audio track | "❌ This video has no audio track" | Exit |
| DeepGram failure | "❌ Transcription failed: {error}" | Retry option |
| MiniMax failure | "❌ AI analysis failed: {error}" | Retry with transcript export |
| FFmpeg error | "❌ Clip extraction failed: {error}" | Skip failed clip, continue others |
| Missing API key | "❌ {Service} API key not found" | Show setup instructions |

---

## Dependencies

- **yt-dlp**: Video downloading
- **ffmpeg**: Audio extraction, clip generation
- **deepgram-sdk** (Python): Transcription
- **anthropic** or **requests**: MiniMax API calls
- **rich**: Beautiful terminal output with progress bars
- **python-dotenv**: Environment variable management

---

## File Structure

```
/Users/harshkapoor/Downloads/Harsh Kapoor/Development/Clipping Agent/
├── clipgen.py                 # Main CLI
├── core/
│   ├── __init__.py
│   ├── downloader.py
│   ├── extractor.py
│   ├── transcriber.py
│   ├── analyzer.py
│   ├── clipper.py
│   └── narrative.py
├── config/
│   ├── __init__.py
│   └── settings.py
├── utils/
│   ├── __init__.py
│   ├── progress.py
│   └── validators.py
├── prompts/
│   └── system_prompt.txt
├── output/                    # Generated clips
├── temp/                      # Temporary files
├── .env.example
├── requirements.txt
├── SPEC.md
└── README.md
```
