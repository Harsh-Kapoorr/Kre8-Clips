"""
API response cache for Deepgram transcripts and Gemini clip analysis.

Caches are keyed by a SHA-256 hash of the input fingerprint (URL + prompt
+ relevant generation options). On cache hit, the stored response is
returned instead of calling the paid API. Bypassed entirely if
CLIPGEN_DISABLE_CACHE=1.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional


CACHE_DIR = Path(__file__).parent.parent / ".cache"
TRANSCRIPT_DIR = CACHE_DIR / "transcripts"
RESPONSE_DIR = CACHE_DIR / "responses"

DEFAULT_TTL_SECONDS = 30 * 24 * 3600


def _ensure_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    RESPONSE_DIR.mkdir(parents=True, exist_ok=True)


def _is_disabled() -> bool:
    return os.getenv("CLIPGEN_DISABLE_CACHE", "0").lower() in ("1", "true", "yes")


def make_fingerprint(parts: list) -> str:
    """Build a stable SHA-256 fingerprint from input parts."""
    payload = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_fresh(path: Path, ttl: int) -> bool:
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl


def get_transcript(fingerprint: str) -> Optional[dict]:
    """Return cached transcript payload or None."""
    if _is_disabled():
        return None
    _ensure_dirs()
    path = TRANSCRIPT_DIR / f"{fingerprint}.json"
    if not _is_fresh(path, DEFAULT_TTL_SECONDS):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def save_transcript(fingerprint: str, payload: dict) -> None:
    """Persist transcript payload to cache."""
    if _is_disabled():
        return
    _ensure_dirs()
    path = TRANSCRIPT_DIR / f"{fingerprint}.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    tmp.replace(path)


def get_response(fingerprint: str) -> Optional[str]:
    """Return cached Gemini response text or None."""
    if _is_disabled():
        return None
    _ensure_dirs()
    path = RESPONSE_DIR / f"{fingerprint}.txt"
    if not _is_fresh(path, DEFAULT_TTL_SECONDS):
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def save_response(fingerprint: str, text: str) -> None:
    """Persist Gemini response text to cache."""
    if _is_disabled():
        return
    _ensure_dirs()
    path = RESPONSE_DIR / f"{fingerprint}.txt"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
    tmp.replace(path)


def cache_stats() -> dict:
    """Return counts and total size of the cache (for diagnostics)."""
    _ensure_dirs()
    t_count = sum(1 for _ in TRANSCRIPT_DIR.glob("*.json"))
    r_count = sum(1 for _ in RESPONSE_DIR.glob("*.txt"))
    t_size = sum(p.stat().st_size for p in TRANSCRIPT_DIR.glob("*.json"))
    r_size = sum(p.stat().st_size for p in RESPONSE_DIR.glob("*.txt"))
    return {
        "transcripts": t_count,
        "responses": r_count,
        "transcript_bytes": t_size,
        "response_bytes": r_size,
        "total_bytes": t_size + r_size,
    }


def clear_cache() -> int:
    """Delete all cached entries. Returns count of files removed."""
    _ensure_dirs()
    removed = 0
    for path in list(TRANSCRIPT_DIR.glob("*.json")) + list(RESPONSE_DIR.glob("*.txt")):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
