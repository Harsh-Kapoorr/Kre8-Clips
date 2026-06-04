from pathlib import Path
from deepgram import DeepgramClient
from config.settings import DEEPGRAM_API_KEY, DEEPGRAM_MODEL, DEEPGRAM_SMART_FORMAT
from utils.progress import console, print_success
from core import cache
import json
import requests
import hashlib


def _fingerprint_for_audio(audio_path: Path, words: bool) -> str:
    """Fingerprint an audio file by path + size + mtime + transcription mode."""
    stat = audio_path.stat()
    payload = {
        "path": str(audio_path.resolve()),
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "model": DEEPGRAM_MODEL,
        "words": words,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def transcribe_audio(audio_path: Path, progress_callback=None) -> list[dict]:
    """Transcribe audio file using DeepGram with speaker diarization."""
    if not DEEPGRAM_API_KEY:
        raise Exception("DEEPGRAM_API_KEY not set in environment")

    fingerprint = _fingerprint_for_audio(audio_path, words=False)
    cached = cache.get_transcript(fingerprint)
    if cached is not None:
        console.print("[dim]Deepgram cache hit — skipping paid transcription.[/dim]")
        return cached.get("segments", [])

    try:
        console.print("[dim]Transcribing with DeepGram (speaker diarization enabled)...[/dim]")

        console.print(f"[dim]Audio file: {audio_path}[/dim]")
        file_size = audio_path.stat().st_size / (1024 * 1024)
        console.print(f"[dim]Audio size: {file_size:.1f} MB[/dim]")

        with open(audio_path, "rb") as audio_file:
            audio_data = audio_file.read()

        console.print(f"[dim]Read {len(audio_data)} bytes[/dim]")

        url = "https://api.deepgram.com/v1/listen"
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "audio/wav"
        }
        params = {
            "model": DEEPGRAM_MODEL,
            "smart_format": "true" if DEEPGRAM_SMART_FORMAT else "false",
            "utterances": "true",
            "diarize": "true",
            "detect_language": "true",
            "punctuate": "true"
        }

        console.print("[dim]Sending request to DeepGram API...[/dim]")
        response = requests.post(
            url,
            headers=headers,
            params=params,
            data=audio_data,
            timeout=(120, 900)
        )

        console.print(f"[dim]Response status: {response.status_code}[/dim]")

        if response.status_code != 200:
            raise Exception(f"DeepGram API error: {response.status_code} - {response.text}")

        result = response.json()

        segments = []

        if "results" in result:
            results = result["results"]

            if "utterances" in results and results["utterances"]:
                for utterance in results["utterances"]:
                    speaker_label = None
                    if utterance.get("speaker") is not None:
                        speaker_label = f"SPEAKER_{utterance['speaker']}"

                    segments.append({
                        "start": float(utterance.get("start", 0)),
                        "end": float(utterance.get("end", 0)),
                        "text": utterance.get("transcript", ""),
                        "speaker": speaker_label
                    })

                speakers = set(s.get("speaker") for s in segments if s.get("speaker"))
                console.print(f"[dim]Diarization: found {len(speakers)} speakers[/dim]")

        segments.sort(key=lambda x: x["start"])
        cache.save_transcript(fingerprint, {"segments": segments, "words": []})
        return segments

    except requests.exceptions.Timeout:
        raise Exception("Transcription timed out - audio file may be too large")
    except Exception as e:
        raise Exception(f"Transcription failed: {str(e)}")


def transcribe_audio_with_words(audio_path: Path) -> tuple[list[dict], list[dict]]:
    """Transcribe and also return word-level timestamps."""
    if not DEEPGRAM_API_KEY:
        raise Exception("DEEPGRAM_API_KEY not set in environment")

    fingerprint = _fingerprint_for_audio(audio_path, words=True)
    cached = cache.get_transcript(fingerprint)
    if cached is not None:
        console.print("[dim]Deepgram cache hit — skipping paid transcription.[/dim]")
        return cached.get("segments", []), cached.get("words", [])

    try:
        with open(audio_path, "rb") as audio_file:
            audio_data = audio_file.read()

        url = "https://api.deepgram.com/v1/listen"
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "audio/wav"
        }
        params = {
            "model": DEEPGRAM_MODEL,
            "smart_format": "true" if DEEPGRAM_SMART_FORMAT else "false",
            "utterances": "true",
            "diarize": "true",
            "punctuate": "true",
            "words": "true"
        }

        response = requests.post(
            url,
            headers=headers,
            params=params,
            data=audio_data,
            timeout=(60, 600)
        )

        if response.status_code != 200:
            raise Exception(f"DeepGram API error: {response.status_code}")

        result = response.json()
        segments = []
        words = []

        if "results" in result and "utterances" in result["results"]:
            for utterance in result["results"]["utterances"]:
                speaker_label = f"SPEAKER_{utterance['speaker']}" if utterance.get("speaker") is not None else None

                segments.append({
                    "start": float(utterance.get("start", 0)),
                    "end": float(utterance.get("end", 0)),
                    "text": utterance.get("transcript", ""),
                    "speaker": speaker_label
                })

                if "words" in utterance:
                    for word in utterance["words"]:
                        word_speaker = speaker_label
                        if word.get("speaker") is not None:
                            word_speaker = f"SPEAKER_{word['speaker']}"

                        words.append({
                            "word": word.get("word", ""),
                            "start": float(word.get("start", 0)),
                            "end": float(word.get("end", 0)),
                            "speaker": word_speaker,
                            "confidence": float(word.get("confidence", 1.0))
                        })

        segments.sort(key=lambda x: x["start"])
        words.sort(key=lambda x: x["start"])

        cache.save_transcript(fingerprint, {"segments": segments, "words": words})
        return segments, words

    except Exception as e:
        raise Exception(f"Transcription failed: {str(e)}")


def format_transcript_for_analysis(segments: list[dict], max_chars: int = 50000) -> str:
    """Format transcript segments for AI analysis with speaker context."""
    formatted = []

    current_speaker = None
    current_block = []

    for seg in segments:
        speaker = seg.get("speaker") or "UNKNOWN"
        start = format_timestamp(seg["start"])
        text = seg["text"].strip()

        if not text:
            continue

        if speaker != current_speaker:
            if current_block:
                formatted.append("")
            formatted.append(f"[{start}] [{speaker}]:")
            current_speaker = speaker

        formatted.append(f"  {text}")

        if len("\n".join(formatted)) > max_chars:
            break

    return "\n".join(formatted)


def format_timestamp(seconds: float) -> str:
    """Format seconds to HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"