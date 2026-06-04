import re

def validate_youtube_url(url: str) -> bool:
    """Validate YouTube URL format."""
    patterns = [
        r'^(https?://)?(www\.)?youtube\.com/watch\?v=[\w-]+',
        r'^(https?://)?(www\.)?youtu\.be/[\w-]+',
        r'^(https?://)?(www\.)?youtube\.com/embed/[\w-]+',
        r'^(https?://)?(www\.)?youtube\.com/shorts/[\w-]+',
        r'^(https?://)?(www\.)?youtube\.com/@[\w.-]+',
        r'^(https?://)?(www\.)?youtube\.com/c/[\w.-]+',
        r'^(https?://)?(www\.)?youtube\.com/channel/[\w-]+',
        r'^(https?://)?(www\.)?youtube\.com/playlist\?list=[\w-]+',
        r'^(https?://)?(www\.)?youtube\.com/handle/[\w.-]+',
        r'^(https?://)?(www\.)?youtube\.com/\+[\w.-]+',
    ]
    return any(re.match(pattern, url) for pattern in patterns)


def parse_duration(duration_str: str) -> float:
    """Parse duration string (HH:MM:SS or MM:SS) to seconds."""
    parts = duration_str.split(':')
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0.0


def format_duration(seconds: float) -> str:
    """Format seconds to HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_time(seconds: float) -> str:
    """Format seconds to HH:MM:SS for API responses."""
    return format_duration(seconds)


def sanitize_filename(name: str) -> str:
    """Sanitize string for use as filename."""
    return re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')