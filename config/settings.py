import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"

# Ensure directories exist
TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# API Keys
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# FFmpeg settings
AUDIO_FORMAT = "wav"
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1

# Clip settings
DEFAULT_FORMAT = "mp4"
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"
VIDEO_BITRATE = "8M"
AUDIO_BITRATE = "192k"

# Clipper behavior
NARRATIVE_MODE = False
CROSSFADE_DURATION = float(os.getenv("CROSSFADE_DURATION", "0.3"))
MAX_CLIP_DURATION = 60
MIN_CLIP_DURATION = 3

# === NEW: Smart Narrative Assembly ===
SMART_NARRATIVE_MODE = os.getenv("SMART_NARRATIVE_MODE", "false").lower() == "true"
SMART_NARRATIVE_MIN_DURATION = 30
SMART_NARRATIVE_MAX_DURATION = 90

# DeepGram settings
DEEPGRAM_MODEL = "nova-2"
DEEPGRAM_SMART_FORMAT = True

# === NEW: Speaker Tracking Settings ===
ENABLE_SPEAKER_TRACKING = os.getenv("ENABLE_SPEAKER_TRACKING", "false").lower() == "true"
SPEAKER_TRACKING_SMOOTHING = float(os.getenv("SPEAKER_TRACKING_SMOOTHING", "0.3"))
ENABLE_TRACKING_DEBUG = os.getenv("ENABLE_TRACKING_DEBUG", "true").lower() == "true"

# === NEW: Aspect Ratio Settings ===
DEFAULT_ASPECT_RATIO = os.getenv("DEFAULT_ASPECT_RATIO", "9:16")  # 9:16, 16:9, 1:1

# === NEW: Virality Settings ===
ENABLE_VIRALITY_SCORING = os.getenv("ENABLE_VIRALITY_SCORING", "true").lower() == "true"
HOOK_DETECTION_THRESHOLD = float(os.getenv("HOOK_DETECTION_THRESHOLD", "0.7"))

# === NEW: Caption Settings ===
ENABLE_CAPTIONS = os.getenv("ENABLE_CAPTIONS", "false").lower() == "true"
CAPTION_STYLE = os.getenv("CAPTION_STYLE", "pop")  # pop, fade, typewriter, none

# === NEW: pyannote Diarization (optional, higher accuracy) ===
PYANNOTE_HF_TOKEN = os.getenv("PYANNOTE_HF_TOKEN")
USE_PYANNOTE_DIARIZATION = os.getenv("USE_PYANNOTE_DIARIZATION", "false").lower() == "true"

# === NEW: Test Mode ===
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

# === NEW: Beat-Synchronized Cutting ===
ENABLE_BEAT_SYNC = os.getenv("ENABLE_BEAT_SYNC", "true").lower() == "true"
BEAT_SNAP_TOLERANCE = float(os.getenv("BEAT_SNAP_TOLERANCE", "0.4"))

# === NEW: Word-Level Captions ===
ENABLE_WORD_LEVEL_CAPTIONS = os.getenv("ENABLE_WORD_LEVEL_CAPTIONS", "false").lower() == "true"

# === NEW: Reliability Scoring ===
ENABLE_RELIABILITY_SCORING = os.getenv("ENABLE_RELIABILITY_SCORING", "true").lower() == "true"
RELIABILITY_WEIGHTS = {
    "face_stability": 0.30,
    "audio_quality": 0.30,
    "structure": 0.20,
    "virality": 0.20,
}

# === NEW: Title Optimization ===
DEFAULT_PLATFORM = os.getenv("DEFAULT_PLATFORM", "tiktok")  # tiktok, shorts, reels
TITLE_MAX_CHARS = int(os.getenv("TITLE_MAX_CHARS", "100"))
MAX_HASHTAGS = int(os.getenv("MAX_HASHTAGS", "5"))

# === NEW: Speaker Embedding Identity ===
EMBEDDING_MATCH_WEIGHT = float(os.getenv("EMBEDDING_MATCH_WEIGHT", "0.65"))

# === NEW: Adaptive Crossfade ===
ADAPTIVE_CROSSFADE = os.getenv("ADAPTIVE_CROSSFADE", "true").lower() == "true"

# === NEW: B-Roll Detection ===
ENABLE_B_ROLL_SUGGESTION = os.getenv("ENABLE_B_ROLL_SUGGESTION", "false").lower() == "true"
MOTION_THRESHOLD = float(os.getenv("MOTION_THRESHOLD", "0.3"))

# === NEW: Batch Processing ===
BATCH_CONCURRENT_LIMIT = int(os.getenv("BATCH_CONCURRENT_LIMIT", "3"))

# === NEW: Thumbnail Generation ===
THUMBNAIL_COUNT = int(os.getenv("THUMBNAIL_COUNT", "3"))

# === NEW: Quality Dashboard ===
ENABLE_QUALITY_DASHBOARD = os.getenv("ENABLE_QUALITY_DASHBOARD", "true").lower() == "true"

# === Clip Fade In/Out (post-render, applied to every generated clip) ===
ENABLE_CLIP_FADES = os.getenv("ENABLE_CLIP_FADES", "true").lower() == "true"
CLIP_FADE_IN_DURATION = float(os.getenv("CLIP_FADE_IN_DURATION", "0.3"))
CLIP_FADE_OUT_DURATION = float(os.getenv("CLIP_FADE_OUT_DURATION", "0.5"))
# ffmpeg `fade` filter curve. Empty = linear. "qua" = quadratic ease-out (cinematic).
# See ffmpeg fade docs for the full list: tri, qsin, hsin, esin, log, par, qua,
# cub, squ, cbr, plus their "in_" prefixed invert variants.
CLIP_FADE_IN_CURVE = os.getenv("CLIP_FADE_IN_CURVE", "")
CLIP_FADE_OUT_CURVE = os.getenv("CLIP_FADE_OUT_CURVE", "qua")

# === Cost Optimization ===
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "4096"))
GEMINI_INPUT_CHAR_CAP = int(os.getenv("GEMINI_INPUT_CHAR_CAP", "60000"))
MOCK_GEMINI_RESPONSE = os.getenv("MOCK_GEMINI_RESPONSE", "false").lower() in ("1", "true", "yes")
