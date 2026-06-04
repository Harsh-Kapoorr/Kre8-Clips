import subprocess
from pathlib import Path
from config.settings import TEMP_DIR, AUDIO_FORMAT, AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, TEST_MODE
from utils.progress import console


def extract_audio(video_path: Path, progress_callback=None, max_duration: float = None, output_dir=None) -> Path:
    """Extract audio from video file as WAV.

    Args:
        video_path: Path to video file
        progress_callback: Optional callback
        max_duration: Maximum duration in seconds (for TEST_MODE, limits to first N seconds)
    """
    audio_dir = Path(output_dir) if output_dir else TEMP_DIR
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{video_path.stem}_audio.{AUDIO_FORMAT}"

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel", "quiet",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
    ]
    if max_duration:
        cmd.extend(["-t", str(max_duration)])
    cmd.append(str(audio_path))

    try:
        console.print("[dim]Extracting audio...[/dim]")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        if not audio_path.exists():
            raise Exception("Audio file was not created")

        return audio_path

    except FileNotFoundError:
        raise Exception("ffmpeg not found. Install with: brew install ffmpeg")
    except Exception as e:
        raise Exception(f"Audio extraction failed: {str(e)}")