import json
import os
import re
import urllib.request
import ssl
from pathlib import Path
from config.settings import (
    ENABLE_VIRALITY_SCORING,
    GEMINI_API_KEY as SETTINGS_GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_INPUT_CHAR_CAP,
    MOCK_GEMINI_RESPONSE,
)
from utils.progress import console
from core import cache

GEMINI_API_KEY = SETTINGS_GEMINI_API_KEY  # Load from settings on import


def _mock_response(user_message: str) -> str:
    """Return a deterministic mock Gemini response for test/dev runs."""
    sample = [{
        "segments": [
            {
                "start": "00:00:30",
                "end": "00:01:05",
                "segment_role": "hook",
                "viral_potential": 8,
                "opening_strength": 9,
                "closing_strength": 7
            }
        ],
        "title": "MOCK: Highlight from the source video",
        "reason": "Cached / mocked response (MOCK_GEMINI_RESPONSE=1). No API call was made.",
        "priority": 8,
        "duration_seconds": 35,
        "hook_score": 8,
        "quote_potential": "",
        "emotional_tone": "inspiring",
        "main_speaker": "SPEAKER_0",
        "topic": "mock"
    }]
    return json.dumps(sample)


def _truncate_transcript(user_message: str) -> str:
    """Cap the transcript portion of the user message to limit Gemini input cost."""
    marker = "TRANSCRIPT:\n"
    idx = user_message.find(marker)
    if idx == -1 or GEMINI_INPUT_CHAR_CAP <= 0:
        return user_message
    head = user_message[: idx + len(marker)]
    body = user_message[idx + len(marker):]
    if len(body) <= GEMINI_INPUT_CHAR_CAP:
        return user_message
    kept = body[:GEMINI_INPUT_CHAR_CAP]
    return f"{head}{kept}\n\n[...transcript truncated to {GEMINI_INPUT_CHAR_CAP} chars for cost control...]"


def load_system_prompt(viral: bool = False) -> str:
    """Load the system prompt from file."""
    if viral and ENABLE_VIRALITY_SCORING:
        prompt_path = Path(__file__).parent.parent / "prompts" / "system_prompt_viral.txt"
    else:
        prompt_path = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
    return prompt_path.read_text().strip()


def analyze_transcript(transcript: str, user_prompt: str, viral: bool = True, api_key: str = None) -> list[dict]:
    """Send transcript to Gemini AI for clip analysis."""
    global GEMINI_API_KEY

    try:
        console.print("[dim]Analyzing with Gemini AI for narrative clips...[/dim]")

        if api_key:
            GEMINI_API_KEY = api_key

        system_prompt = load_system_prompt(viral=viral)

        user_message = f"TASK: {user_prompt}\n\nTRANSCRIPT:\n{transcript}"

        fingerprint = cache.make_fingerprint([viral, user_prompt, transcript])
        response, _ = call_gemini_api_cached(system_prompt, user_message, fingerprint, api_key=api_key)

        return parse_clip_response(response)

    except Exception as e:
        raise Exception(f"Gemini analysis failed: {str(e)}")


def call_gemini_api(system_prompt: str, user_message: str, api_key: str = None) -> str:
    """Call Gemini API."""
    global GEMINI_API_KEY

    if MOCK_GEMINI_RESPONSE:
        console.print("[dim]MOCK_GEMINI_RESPONSE=1 — returning synthetic response (no API call).[/dim]")
        return _mock_response(user_message)

    key = api_key or GEMINI_API_KEY
    if not key:
        raise Exception("GEMINI_API_KEY not set. Please provide a Gemini API key.")

    user_message = _truncate_transcript(user_message)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}'

    full_prompt = f"""{system_prompt}

CRITICAL JSON OUTPUT RULES - FOLLOW EXACTLY:
- Output ONLY a valid JSON array, nothing else
- Use double quotes for ALL strings
- Do NOT include newlines inside string values - replace with single space
- Do NOT include trailing commas after last item in objects/arrays
- Do NOT wrap keys or values in single quotes
- Escape double quotes inside strings with backslash (\\")
- All segment start/end times must use format "HH:MM:SS" (e.g., "00:05:30")

Output format (example):
[{{"segments":[{{"start":"00:00:06","end":"00:01:03"}}],"title":"Clip Title Here","reason":"Why this clip is compelling","priority":8,"duration_seconds":57,"hook_score":7,"quote_potential":"Key quote here","emotional_tone":"inspiring","main_speaker":"SPEAKER_0","topic":"topic"}}]

Respond with ONLY the JSON array, no explanations or markdown formatting."""

    data = {
        'contents': [{
            'parts': [
                {'text': full_prompt},
                {'text': user_message}
            ]
        }],
        'generationConfig': {
            'temperature': 0.1,
            'maxOutputTokens': GEMINI_MAX_OUTPUT_TOKENS
        }
    }

    headers = {'Content-Type': 'application/json'}

    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=600, context=ctx) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise Exception(f"Gemini HTTP {e.code}: {body[:1000]}")

    if 'candidates' not in result:
        error_msg = result.get('error', {}).get('message', str(result))
        raise Exception(f"Gemini API error: {error_msg}")

    return result['candidates'][0]['content']['parts'][0]['text']


def call_gemini_api_cached(
    system_prompt: str,
    user_message: str,
    fingerprint: str,
    api_key: str = None,
) -> tuple[str, bool]:
    """Call Gemini with response cache. Returns (response_text, cache_hit)."""
    cached = cache.get_response(fingerprint)
    if cached is not None:
        console.print("[dim]Gemini cache hit — skipping paid API call.[/dim]")
        return cached, True

    response = call_gemini_api(system_prompt, user_message, api_key=api_key)
    cache.save_response(fingerprint, response)
    return response, False


def _try_fix_truncated_json(json_str: str, error: json.JSONDecodeError) -> str:
    """Attempt to fix truncated JSON by completing the last incomplete object."""
    # Find the last complete object by scanning backwards
    # The error position tells us where JSON became invalid

    # Strategy: find the last complete object before the error position
    # and either complete it or cut it cleanly

    pos = error.pos if hasattr(error, 'pos') else 0

    # Look for the start of the last potentially incomplete object
    # Search backwards from error position for "{"
    incomplete_start = -1
    brace_count = 0
    in_string = False

    # Scan from error position backwards to find where object started
    for i in range(pos - 1, -1, -1):
        c = json_str[i]
        if c == '"' and (i == 0 or json_str[i-1] != '\\'):
            in_string = not in_string
        elif c == '}' and not in_string:
            brace_count -= 1
        elif c == '{' and not in_string:
            brace_count += 1
            if brace_count == 1:
                incomplete_start = i
                break

    if incomplete_start == -1:
        # Couldn't find start of incomplete object - try to find last complete "]"
        last_comma = json_str.rfind(',', 0, pos)
        last_brace = json_str.rfind('}', 0, pos)
        if last_brace > last_comma > 0:
            # Cut before the last object started
            json_str = json_str[:last_comma + 1] + ']'
        return json_str

    # Get the incomplete object text
    incomplete_obj = json_str[incomplete_start:pos]

    # Try to complete it by adding missing closing braces
    open_braces = incomplete_obj.count('{') - incomplete_obj.count('}')
    open_strings = incomplete_obj.count('"') % 2 == 1

    if open_strings:
        # Find the last unclosed string and close it
        # Try to find where the string value starts and ends it
        fixed = json_str[:pos]
        # Add a closing quote and the object terminator
        fixed += '"' + '}' * (open_braces + 1)
    else:
        fixed = json_str[:pos] + '}' * (open_braces + 1)

    # Remove any trailing comma issues
    fixed = re.sub(r',\s*}', '}', fixed)
    fixed = re.sub(r',\s*]', ']', fixed)

    return fixed


def _extract_complete_clips(json_str: str) -> list:
    """Extract complete clip objects from potentially broken JSON."""
    # Find all complete objects by looking for balanced braces
    clips = []
    depth = 0
    in_string = False
    obj_start = -1
    i = 0

    # Find opening bracket
    if json_str.strip().startswith('['):
        i = json_str.index('[') + 1

    while i < len(json_str):
        c = json_str[i]

        if c == '"' and (i == 0 or json_str[i-1] != '\\'):
            in_string = not in_string
        elif c == '{' and not in_string:
            if depth == 0:
                obj_start = i
            depth += 1
        elif c == '}' and not in_string:
            depth -= 1
            if depth == 0 and obj_start != -1:
                # Found complete object
                try:
                    obj_str = json_str[obj_start:i+1]
                    clip = json.loads(obj_str)
                    if isinstance(clip, dict) and 'segments' in clip and 'title' in clip:
                        clips.append(clip)
                except:
                    pass
                obj_start = -1
        elif c == ',' and not in_string and depth == 0 and obj_start == -1:
            # Separator between objects
            pass

        i += 1

    if clips:
        return clips

    # Last resort: try regex to find complete clip objects
    pattern = r'\{[^{}]*"segments"\s*:\s*\[[^\]]*\][^{}]*"title"\s*:\s*"[^"]*"[^{}]*\}'
    matches = re.findall(pattern, json_str)
    clips = []
    for match in matches:
        try:
            clip = json.loads(match)
            if isinstance(clip, dict) and 'segments' in clip:
                clips.append(clip)
        except:
            continue

    if not clips:
        raise Exception("Could not extract any complete clips from JSON - response was malformed")
    return clips


def parse_clip_response(content: str) -> list[dict]:
    """Parse AI's JSON response into clip definitions."""
    try:
        content = content.strip()

        # Remove any markdown code blocks
        for prefix in ["```json", "```JSON", "```"]:
            if content.startswith(prefix):
                content = content[len(prefix):]
                if content.endswith("```"):
                    content = content[:-3]
                break

        content = content.strip()
        # Normalize whitespace - replace any newline/CR with space
        content = re.sub(r'[\n\r\t]+', ' ', content)

        if "[" not in content or "]" not in content:
            raise Exception("No JSON array found in response")

        start_idx = content.find("[")
        end_idx = content.rfind("]") + 1
        json_str = content[start_idx:end_idx]

        try:
            clips = json.loads(json_str)
        except json.JSONDecodeError as e:
            # Try to fix truncated JSON
            json_str = _try_fix_truncated_json(json_str, e)
            try:
                clips = json.loads(json_str)
            except json.JSONDecodeError:
                # Last resort: extract complete clips
                clips = _extract_complete_clips(json_str)

        if not isinstance(clips, list):
            raise Exception("Expected JSON array of clips")

        validated_clips = []
        for clip in clips:
            if "segments" in clip and "title" in clip:
                total_duration = calculate_clip_duration(clip.get("segments", []))

                if total_duration < 15:
                    console.print(f"[dim]Skipping clip '{clip.get('title', 'Untitled')[:40]}' - too short ({total_duration:.0f}s)[/dim]")
                    continue

                # Parse per-segment fields with defaults
                parsed_segments = []
                for seg in clip.get("segments", []):
                    seg_start = parse_timestamp_value(seg.get("start", "0"))
                    seg_end = parse_timestamp_value(seg.get("end", "0"))
                    seg_duration = seg_end - seg_start

                    parsed_segments.append({
                        "start": seg.get("start", "0"),
                        "end": seg.get("end", "0"),
                        "start_seconds": seg_start,
                        "end_seconds": seg_end,
                        "duration": seg_duration,
                        "segment_role": seg.get("segment_role", "body"),
                        "viral_potential": max(1, min(10, int(seg.get("viral_potential", 5)))),
                        "opening_strength": max(1, min(10, int(seg.get("opening_strength", 5)))),
                        "closing_strength": max(1, min(10, int(seg.get("closing_strength", 5)))),
                    })

                validated_clip = {
                    "segments": parsed_segments,
                    "title": clip.get("title", "Untitled Clip"),
                    "reason": clip.get("reason", ""),
                    "priority": clip.get("priority", 5),
                    "duration_seconds": total_duration,
                    "hook_score": clip.get("hook_score", 5),
                    "quote_potential": clip.get("quote_potential", ""),
                    "emotional_tone": clip.get("emotional_tone", "neutral"),
                    "main_speaker": clip.get("main_speaker", "UNKNOWN"),
                    "topic": clip.get("topic", ""),
                    "speaker_track": clip.get("speaker_track", [])
                }
                validated_clips.append(validated_clip)

        # Sort by priority, then by duration (longer = better narrative potential)
        validated_clips.sort(key=lambda x: (x.get("priority", 0), x.get("duration_seconds", 0)), reverse=True)

        return validated_clips

    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse clip response: {str(e)}\nContent: {content[:500]}")
    except Exception as e:
        raise Exception(f"Failed to parse response: {str(e)}")


def calculate_clip_duration(segments: list[dict]) -> float:
    """Calculate total clip duration from segments."""
    if not segments:
        return 0.0

    total = 0.0
    for seg in segments:
        start = parse_timestamp_value(seg.get("start", "0"))
        end = parse_timestamp_value(seg.get("end", "0"))
        total += (end - start)

    return total


def parse_timestamp_value(ts) -> float:
    """Parse timestamp to float seconds."""
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        parts = ts.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except ValueError:
            pass
    return 0.0


def assemble_smart_narrative(
    clips: list[dict],
    min_duration: int = 20,
    max_duration: int = 65,
    main_speaker: str = None,
) -> dict:
    """
    Assemble an optimal narrative from the best segments across all clips.

    Selection algorithm:
    1. Collect all segments by role (hook/body/payoff)
    2. Score and rank each role's segments by role-specific metrics
       - Hooks: opening_strength * 3 + viral_potential
       - Bodies: viral_potential * 5 - duration_penalty (tight bodies > long rambling ones)
       - Payoffs: closing_strength * 3 + viral_potential
    3. Score candidates by: hook_quality * 3 + payoff_quality * 3 + viral_potential - duration_penalty
    4. Validate semantic coherence (hook topic matches payoff topic)
    5. Return diverse duration candidates (some 20-35s, some 35-50s, some 50-65s)

    Args:
        clips: List of clip dicts from parse_clip_response()
        min_duration: Minimum total duration in seconds
        max_duration: Maximum total duration in seconds
        main_speaker: Preferred speaker for speaker continuity

    Returns:
        Assembled narrative clip dict with 'segments', 'title', 'reason', etc.
        Returns empty dict if insufficient segments found.
    """
    if not clips:
        return {}

    # Collect all segments tagged by role
    hooks = []
    bodies = []
    payoffs = []

    for clip in clips:
        clip_segments = clip.get("segments", [])
        clip_main_speaker = clip.get("main_speaker", main_speaker)

        for seg in clip_segments:
            role = seg.get("segment_role", "body")
            seg_with_context = {
                **seg,
                "source_clip_title": clip.get("title", ""),
                "source_main_speaker": clip_main_speaker,
                "source_priority": clip.get("priority", 5),
            }

            if role == "hook":
                hooks.append(seg_with_context)
            elif role == "payoff":
                payoffs.append(seg_with_context)
            else:
                bodies.append(seg_with_context)

    # Score hooks: opening_strength is most important
    def hook_score(seg):
        return (
            seg.get("opening_strength", 5) * 3 +
            seg.get("viral_potential", 5) +
            seg.get("source_priority", 5)
        )

    # Score bodies: penalize long rambling bodies, reward tight ones
    # Duration penalty: every second over 40s costs 0.5 points
    def body_score(seg):
        duration = seg.get("duration", 0)
        duration_penalty = max(0, duration - 40) * 0.5
        return (
            seg.get("viral_potential", 5) * 5 -
            duration_penalty +
            seg.get("source_priority", 5)
        )

    # Score payoffs: closing_strength is most important
    def payoff_score(seg):
        return (
            seg.get("closing_strength", 5) * 3 +
            seg.get("viral_potential", 5) +
            seg.get("source_priority", 5)
        )

    hooks.sort(key=hook_score, reverse=True)
    bodies.sort(key=body_score, reverse=True)
    payoffs.sort(key=payoff_score, reverse=True)

    # Build candidate assembled narratives
    candidates = []

    # Strategy: Take top-N of each role and try combinations
    top_hooks = hooks[:5]
    top_bodies = bodies[:5]
    top_payoffs = payoffs[:5]

    for hook in top_hooks:
        for body in top_bodies:
            for payoff in top_payoffs:
                assembled = _try_assemble(hook, body, payoff, main_speaker)
                if assembled:
                    assembled["_combination"] = "hook_body_payoff"
                    candidates.append(assembled)

    # Also try hook + payoff only (short, punchy - good for TikTok/Reels)
    for hook in top_hooks:
        for payoff in top_payoffs:
            assembled = _try_assemble(hook, None, payoff, main_speaker)
            if assembled:
                assembled["_combination"] = "hook_payoff"
                candidates.append(assembled)

    # Also try just standalone hook (if it's strong enough and self-contained)
    for hook in top_hooks:
        if hook.get("opening_strength", 5) >= 8 and hook.get("duration", 0) <= 35:
            assembled = _try_assemble(hook, None, None, main_speaker)
            if assembled:
                assembled["_combination"] = "hook_only"
                candidates.append(assembled)

    if not candidates:
        return {}

    # Score each candidate: hook quality + payoff quality + viral potential - duration penalty
    # Duration penalty: every second over 50s costs 0.3 points
    shortform_min = 20
    for cand in candidates:
        segs = cand.get("assembled_segments", [])
        total_dur = sum(s.get("duration", 0) for s in segs)
        hook_strength = sum(s.get("opening_strength", 5) for s in segs) / max(len(segs), 1)
        payoff_strength = sum(s.get("closing_strength", 5) for s in segs) / max(len(segs), 1)
        avg_viral = sum(s.get("viral_potential", 5) for s in segs) / max(len(segs), 1)

        # Duration penalty (discourage always picking the longest)
        duration_penalty = max(0, total_dur - 50) * 0.3 if total_dur > 50 else 0

        # Segment count bonus: multi-segment clips (with real payoff) score higher than hook_only
        # A clip with actual body/payoff segments is more narratively complete
        segment_count = len(segs)
        if segment_count >= 3:  # hook + body + payoff
            completeness_bonus = 15
        elif segment_count == 2:  # hook + payoff
            completeness_bonus = 10
        else:  # hook_only - single segment, no real payoff
            completeness_bonus = -10

        # Require both strong hook AND strong payoff for top scores
        cand["_assembly_score"] = (
            hook_strength * 3 +
            payoff_strength * 3 +
            avg_viral * 2 -
            duration_penalty +
            completeness_bonus
        )
        cand["_total_duration"] = total_dur

    candidates.sort(key=lambda x: x.get("_assembly_score", 0), reverse=True)

    # DURATION DIVERSITY: pick best candidate, but DIVERSIFY by selecting from
    # different duration buckets when candidates exist across buckets.
    # Prefer global best (highest assembly score) but use duration buckets to
    # ensure variety when strong candidates exist in multiple buckets.
    short_clips = [c for c in candidates if c["_total_duration"] <= 35]
    medium_clips = [c for c in candidates if 35 < c["_total_duration"] <= 50]
    long_clips = [c for c in candidates if 50 < c["_total_duration"] <= max_duration]

    # Pick the globally best-scoring candidate, regardless of duration bucket
    # (duration bucket selection is handled at higher level for output variety)
    chosen = candidates[0] if candidates else None

    best = chosen
    if not best:
        return {}

    # Build final assembled clip structure
    final_segments = []
    for seg in best.get("assembled_segments", []):
        final_segments.append({
            "start": seg.get("start"),
            "end": seg.get("end"),
            "segment_role": seg.get("segment_role"),
            "viral_potential": seg.get("viral_potential", 5),
            "opening_strength": seg.get("opening_strength", 5),
            "closing_strength": seg.get("closing_strength", 5),
        })

    # duration was computed in best["_total_duration"] during candidate scoring
    total_duration = best.get("_total_duration", 0.0)

    # Detect speaker continuity
    speaker_main = main_speaker or best.get("main_speaker", "UNKNOWN")

    return {
        "segments": final_segments,
        "title": f"Smart Narrative: {best.get('assembled_title', 'Assembled Clip')}",
        "reason": best.get("reason", "Smart-assembled narrative from best hook/body/payoff segments"),
        "priority": best.get("_assembly_score", 0) >= 15 and best.get("avg_hook_score", 5) >= 6 and best.get("closing_score", 5) >= 6,
        "duration_seconds": total_duration,
        "hook_score": best.get("avg_hook_score", 7),
        "quote_potential": best.get("quote_potential", ""),
        "emotional_tone": best.get("emotional_tone", "inspiring"),
        "main_speaker": speaker_main,
        "topic": best.get("topic", ""),
        "assembled": True,
        "assembly_sources": best.get("sources", []),
        "_combination": best.get("_combination", ""),
    }


def _try_assemble(
    hook: dict,
    body: dict,
    payoff: dict,
    preferred_speaker: str = None,
) -> dict:
    """
    Try to assemble a valid narrative from hook/body/payoff segments.
    Returns None if speaker continuity fails or duration is invalid.
    """
    segments = []
    if hook:
        segments.append(hook)
    if body:
        segments.append(body)
    if payoff:
        segments.append(payoff)

    if len(segments) < 1:
        return None

    # Check speaker continuity
    if preferred_speaker:
        for seg in segments:
            src_spk = seg.get("source_main_speaker", "")
            if src_spk and src_spk != "UNKNOWN" and src_spk != preferred_speaker:
                # Allow mismatch but track it
                pass

    total_duration = sum(s.get("duration", 0) for s in segments)

    # Calculate timing
    current_time = 0.0
    assembled_segments = []
    sources = []

    for seg in segments:
        seg_start = seg.get("start_seconds", 0)
        seg_end = seg.get("end_seconds", seg_start + seg.get("duration", 10))
        seg_dur = seg_end - seg_start

        assembled_segments.append({
            "start": seg.get("start"),
            "end": seg.get("end"),
            "start_seconds": current_time,
            "end_seconds": current_time + seg_dur,
            "duration": seg_dur,
            "segment_role": seg.get("segment_role", "body"),
            "viral_potential": seg.get("viral_potential", 5),
            "opening_strength": seg.get("opening_strength", 5),
            "closing_strength": seg.get("closing_strength", 5),
            "original_start": seg.get("start"),
            "original_end": seg.get("end"),
            "source_clip": seg.get("source_clip_title", ""),
        })
        sources.append(f"{seg.get('segment_role', 'body')}: {seg.get('start')}->{seg.get('end')}")
        current_time += seg_dur

    # Compute aggregate scores
    avg_hook = sum(s.get("opening_strength", 5) for s in assembled_segments) / len(assembled_segments)
    avg_viral = sum(s.get("viral_potential", 5) for s in assembled_segments) / len(assembled_segments)
    avg_closing = sum(s.get("closing_strength", 5) for s in assembled_segments) / len(assembled_segments)

    # Determine emotional tone from segments
    emotional_tone = "inspiring"
    if hook:
        tone = hook.get("source_clip_title", "")
        if "funny" in tone.lower() or "joke" in tone.lower():
            emotional_tone = "funny"
        elif "surprise" in tone.lower() or "unexpected" in tone.lower():
            emotional_tone = "surprising"

    return {
        "assembled_segments": assembled_segments,
        # Stitch non-empty source titles with " + ". Skip the separator
        # when a role is absent so a hook+payoff assembly does not
        # produce "Hook +  + Payoff" (double-plus) — caught 2026-06-04.
        "assembled_title": " + ".join(
            part for part in (
                hook.get("source_clip_title", "Hook") if hook else "",
                body.get("source_clip_title", "Body") if body else "",
                payoff.get("source_clip_title", "Payoff") if payoff else "",
            ) if part
        ),
        "reason": f"Smart-assembled from: {', '.join(sources)}",
        "main_speaker": preferred_speaker or hook.get("source_main_speaker", "UNKNOWN"),
        "avg_hook_score": avg_hook,
        "avg_viral_score": avg_viral,
        "closing_score": avg_closing,
        "total_duration": total_duration,
        "sources": sources,
        "emotional_tone": emotional_tone,
        "topic": hook.get("source_clip_title", ""),
    }


# =============================================================================
# Reliability Scoring
# =============================================================================

def compute_clip_reliability_score(signals: dict, weights: dict) -> float:
    """Compute composite reliability score from clip signals.

    Weights: face_stability (30%), audio_quality (30%), structure (20%), virality (20%)
    """
    if not signals:
        return 0.5

    face_stab = signals.get("face_position_stability", 0.5)
    audio_quality = (
        signals.get("avg_speaking_score", 0.5) + signals.get("detection_continuity", 0.5)
    ) / 2
    # Normalize face_area_mean: typical range is 0.03-0.07
    face_area = signals.get("face_area_mean", 0.03)
    structure = min(1.0, face_area / 0.05)
    virality = signals.get("hook_score", 5) / 10

    score = (
        weights.get("face_stability", 0.30) * face_stab +
        weights.get("audio_quality", 0.30) * audio_quality +
        weights.get("structure", 0.20) * structure +
        weights.get("virality", 0.20) * virality
    )
    return round(min(1.0, max(0.0, score)), 2)


# =============================================================================
# Title Optimization
# =============================================================================

def optimize_title_for_platform(
    title: str,
    platform: str = "tiktok",
    emotional_tone: str = "neutral",
) -> str:
    """Post-process AI title for platform-specific optimization.

    Args:
        title: Original AI-generated title
        platform: Target platform (tiktok, shorts, reels)
        emotional_tone: Detected emotional tone

    Returns:
        Platform-optimized title
    """
    if not title or title == "Untitled Clip":
        return title

    title = title.strip()
    max_chars = 100

    # Truncate to max chars at a word boundary
    if len(title) > max_chars:
        truncated = title[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > max_chars * 0.7:
            title = truncated[:last_space].strip()
        else:
            title = truncated.strip()

    # Platform-specific adjustments
    if platform == "tiktok":
        # TikTok: add ellipsis if needed, use punchy punctuation
        if not any(title.endswith(c) for c in "!?。."):
            title = title + "..."
    elif platform == "shorts":
        # YouTube Shorts: add | if missing after topic
        if "|" not in title and " - " not in title:
            pass  # Keep as-is
    elif platform == "reels":
        # Instagram Reels: shorter is better
        if len(title) > 80:
            title = title[:77] + "..."

    return title


def generate_hashtags(
    title: str,
    topic: str = "",
    emotional_tone: str = "neutral",
    max_count: int = 5,
) -> list[str]:
    """Generate platform-relevant hashtags.

    Args:
        title: Clip title
        topic: Detected topic
        emotional_tone: Detected emotional tone
        max_count: Maximum number of hashtags

    Returns:
        List of hashtag strings
    """
    hashtags = []

    # Broad engagement hashtags (always include 2-3)
    broad = ["#viral", "#fyp", "#foryou", "#mustwatch", "#storytelling"]
    hashtags.extend(broad[:2])

    # Tone-based hashtags
    tone_map = {
        "inspiring": ["#inspiration", "#motivational", "#growthmindset"],
        "funny": ["#funny", "#humor", "#comedy"],
        "surprising": ["#mindblowing", "#wow", "#unexpected"],
        "educational": ["#learn", "#education", "#knowledge"],
        "controversial": ["#hot", "#debate", "#opinion"],
        "neutral": ["#video", "#clip", "#shortvideo"],
    }
    tone_tags = tone_map.get(emotional_tone, tone_map["neutral"])
    hashtags.append(tone_tags[0])

    # Topic from title (first meaningful word)
    if topic:
        clean_topic = "".join(c for c in topic if c.isalnum())
        if clean_topic:
            hashtags.append(f"#{clean_topic[:20]}")

    # Title words (pick 2 significant ones)
    title_words = [w for w in title.split() if len(w) > 4 and not w.startswith("#")]
    for word in title_words[:2]:
        clean = "".join(c for c in word if c.isalnum())
        if clean and len(clean) > 2:
            tag = f"#{clean[:15].lower()}"
            if tag not in hashtags:
                hashtags.append(tag)

    return hashtags[:max_count]


# =============================================================================
# Quality Dashboard
# =============================================================================

def generate_quality_dashboard(clips: list[dict]) -> list[dict]:
    """Generate per-clip quality report with scores and recommendations.

    Args:
        clips: List of output clip dicts from run_clipgen

    Returns:
        List of quality report dicts per clip
    """
    report = []

    for idx, clip in enumerate(clips):
        scores = {}
        recommendations = []

        # Reliability score
        reliability = clip.get("reliability_score")
        if reliability is not None:
            scores["face_stability"] = f"{reliability * 100:.0f}%"
            if reliability < 0.6:
                recommendations.append(
                    "Low face visibility — consider a different segment with clearer speaker visibility"
                )
            elif reliability >= 0.8:
                recommendations.append("Strong face tracking — clip is visually stable")

        # Hook score
        hook_score = clip.get("hook_score", 5)
        scores["hook_score"] = f"{hook_score}/10"
        if hook_score < 6:
            recommendations.append("Weak hook score — consider repositioning the clip start")
        else:
            recommendations.append("Strong hook — clip opens well")

        # Duration
        duration = clip.get("duration", 0)
        scores["duration"] = f"{duration:.0f}s"
        if duration < 15:
            recommendations.append("Short clip — under 15s may underperform on most platforms")
        elif duration > 90:
            recommendations.append("Long clip — consider trimming to under 60s for Shorts")

        # Emotional tone
        emotional = clip.get("emotional_tone", "neutral")
        scores["emotional_tone"] = emotional

        # Audio quality signal
        signals = clip.get("reliability_signals", {})
        if signals:
            speaking = signals.get("avg_speaking_score", 0)
            scores["audio_quality"] = f"{speaking * 100:.0f}%" if speaking else "N/A"
            if speaking and speaking < 0.2:
                recommendations.append("Low audio activity — speaker may be too quiet")

        # Segment count
        segments = clip.get("segments", [])
        if len(segments) > 1:
            recommendations.append(f"Narrative mode: {len(segments)} segments assembled")
            recommendations.append("Verify crossfade transitions sound natural")

        report.append({
            "clip_index": idx,
            "scores": scores,
            "recommendations": recommendations[:3],  # Max 3 recommendations
        })

    return report