import subprocess
import json
from pathlib import Path
from config.settings import TEMP_DIR
from utils.progress import console, print_info, print_success


def get_video_info(url: str) -> dict:
    """Get video information without downloading."""
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-download",
        "--remote-components", "ejs:npm",
        url
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get video info: {e.stderr}")
    except json.JSONDecodeError:
        raise Exception("Failed to parse video info")


def download_video(url: str, progress_callback=None, output_dir=None) -> Path:
    """Download video using yt-dlp, skipping if already downloaded."""
    download_dir = Path(output_dir) if output_dir else TEMP_DIR
    download_dir.mkdir(parents=True, exist_ok=True)
    output_path = download_dir / "%(title)s.%(ext)s"

    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-download",
        "--no-progress",
        url
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        video_info = json.loads(result.stdout)
        video_title = video_info.get("title", "video")
    except:
        video_title = None

    if video_title:
        existing = list(download_dir.glob(f"{video_title}.mp4"))
        if existing:
            console.print(f"[dim]Video already exists, using cached version[/dim]")
            return existing[0]

    cmd = [
        "yt-dlp",
        "-f", "best[ext=mp4]/best",
        "-o", str(output_path),
        "--no-progress",
        url
    ]

    console.print("[dim]Downloading video...[/dim]")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Monitor progress
        for line in process.stdout:
            if progress_callback:
                progress_callback(line)

        process.wait()

        if process.returncode != 0:
            stderr = process.stderr.read()
            raise Exception(f"Download failed: {stderr}")

    except FileNotFoundError:
        raise Exception("yt-dlp not found. Install with: pip install yt-dlp")
    except Exception as e:
        raise Exception(f"Download error: {str(e)}")

    # Find the downloaded file
    downloaded_files = list(download_dir.glob("*.[mm][po][4t]"))
    if not downloaded_files:
        raise Exception("Video file not found after download")

    # Return the most recent file
    return max(downloaded_files, key=lambda p: p.stat().st_mtime)


def check_dependencies():
    """Check if required dependencies are installed."""
    deps = {
        "yt-dlp": ["yt-dlp", "--version"],
        "ffmpeg": ["ffmpeg", "-version"],
    }

    missing = []
    for name, cmd in deps.items():
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append(name)

    if missing:
        raise Exception(f"Missing dependencies: {', '.join(missing)}. Install with: pip install -r requirements.txt")