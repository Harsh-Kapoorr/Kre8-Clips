"""
Caption generation with styling - SRT + ASS for burn-in.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class CaptionStyle:
    """Caption styling configuration."""
    vertical_position: float = 0.75  # 0.0 to 1.0 (1.0 = bottom)
    font_size: int = 48
    font_color: str = "&H00FFFFFF"  # White
    background_color: str = "&H00000000"  # Transparent black
    animation: str = "pop"  # "pop", "fade", "typewriter", "none"
    max_chars_per_line: int = 42
    position: str = "bottom"  # "bottom", "top", "center"
    bold: bool = True
    stroke_color: str = "&H00000000"
    stroke_width: float = 2.0


class CaptionGenerator:
    """Generates styled SRT captions for video burn-in."""

    def __init__(self, style: Optional[CaptionStyle] = None):
        self.style = style or CaptionStyle()

    def generate_srt(
        self,
        transcript_segments: List[dict],
        include_speaker: bool = True,
        max_duration: float = 60.0
    ) -> str:
        """Generate SRT content from transcript segments.

        Args:
            transcript_segments: List of {start, end, text, speaker}
            include_speaker: Whether to prefix captions with speaker name
            max_duration: Maximum caption duration

        Returns:
            SRT formatted string
        """
        srt_lines = []
        caption_index = 1

        for i, seg in enumerate(transcript_segments):
            start_time = seg.get("start", 0)
            end_time = seg.get("end", start_time)
            duration = end_time - start_time

            # Skip very short segments
            if duration < 0.3:
                continue

            # Cap duration
            if duration > max_duration:
                end_time = start_time + max_duration

            text = seg.get("text", "").strip()
            if not text:
                continue

            speaker = seg.get("speaker", "")
            if include_speaker and speaker:
                text = f"[{speaker}] {text}"

            # Word wrap
            lines = self._word_wrap(text)

            # Format timestamps
            start_srt = self._format_srt_time(start_time)
            end_srt = self._format_srt_time(end_time)

            srt_lines.append(f"{caption_index}")
            srt_lines.append(f"{start_srt} --> {end_srt}")
            srt_lines.extend(lines)
            srt_lines.append("")

            caption_index += 1

        return "\n".join(srt_lines)

    def generate_srt_from_words(
        self,
        words: List[dict],
        include_speaker: bool = True,
        max_chars: int = 42,
    ) -> str:
        """Generate SRT from word-level timestamps for precise caption sync.

        Groups consecutive words into caption lines, each with word-level timing.

        Args:
            words: List of {word, start, end, speaker, confidence}
            include_speaker: Whether to prefix captions with speaker name
            max_chars: Max characters per caption line

        Returns:
            SRT formatted string
        """
        if not words:
            return ""

        srt_lines = []
        caption_index = 1
        current_words = []
        current_start = None
        current_end = None
        current_speaker = None

        def flush_line(line_words, start, end, speaker):
            nonlocal caption_index, srt_lines
            if not line_words:
                return
            text = " ".join(w["word"] for w in line_words)
            if include_speaker and speaker:
                text = f"[{speaker}] {text}"
            lines = self._word_wrap(text)
            start_srt = self._format_srt_time(start)
            end_srt = self._format_srt_time(end)
            srt_lines.append(str(caption_index))
            srt_lines.append(f"{start_srt} --> {end_srt}")
            srt_lines.extend(lines)
            srt_lines.append("")
            caption_index += 1

        for word_entry in words:
            word_text = word_entry.get("word", "").strip()
            if not word_text:
                continue

            word_start = word_entry.get("start", 0)
            word_end = word_entry.get("end", word_start)
            word_speaker = word_entry.get("speaker", "")
            word_confidence = word_entry.get("confidence", 1.0)

            # Skip low-confidence words
            if word_confidence < 0.7:
                continue

            # Start new line if needed
            test_text = " ".join(w["word"] for w in current_words + [word_entry])
            if len(test_text) > max_chars and current_words:
                flush_line(current_words, current_start, current_end, current_speaker)
                current_words = []
                current_start = None
                current_end = None
                current_speaker = None

            if current_start is None:
                current_start = word_start
            current_end = word_end
            current_speaker = word_speaker
            current_words.append(word_entry)

        # Flush remaining
        flush_line(current_words, current_start, current_end, current_speaker)

        return "\n".join(srt_lines)

    def _format_srt_time(self, seconds: float) -> str:
        """Format seconds to SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _word_wrap(self, text: str) -> List[str]:
        """Word wrap text to fit caption width."""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = " ".join(current_line + [word])
            if len(test_line) <= self.style.max_chars_per_line:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]

        if current_line:
            lines.append(" ".join(current_line))

        return lines if lines else [text]

    def save_srt(self, srt_content: str, output_path: Path) -> Path:
        """Save SRT content to file."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        return output_path

    def generate_ass_style(self) -> str:
        """Generate ASS style section for styled burn-in.

        Returns:
            ASS format style definition
        """
        style_name = f"Kre8Clips_{self.style.animation}"

        # Calculate position
        margin_l = 20
        margin_r = 20
        margin_v = int(100 - self.style.vertical_position * 100)

        # Animation overrides
        if self.style.animation == "pop":
            animation = ",0,0,0,"
        elif self.style.animation == "typewriter":
            animation = ",0,0,0,"
        elif self.style.animation == "fade":
            animation = ",0,0,200,"
        else:
            animation = ",0,0,0,"

        # Format: StyleName, FontName, FontSize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
        style_line = (
            f"Style: {style_name},Arial,{self.style.font_size},"
            f"{self.style.font_color},{self.style.font_color},"
            f"{self.style.stroke_color},&H00000000,"
            f"{1 if self.style.bold else 0},0,0,0,100,100,0,0,"
            f"1,{self.style.stroke_width:.1f},0,"
            f"5,{margin_l},{margin_r},{margin_v},1"
        )

        return f"""[V4 Styles]
Event Type: 0, Name: Default
{style_line}
"""

    def generate_ass_events(self, srt_content: str) -> str:
        """Convert SRT content to ASS events with styling.

        Returns:
            ASS format events section
        """
        lines = []
        lines.append("[Events]")

        for i, line in enumerate(srt_content.strip().split("\n\n")):
            parts = line.strip().split("\n")
            if len(parts) < 3:
                continue

            # Skip the index number and timestamp line
            text_lines = parts[2:]

            # Format timestamp
            timestamp = parts[1].replace(",", ".")
            start_time, end_time = timestamp.split(" --> ")

            # Clean text (remove speaker labels for cleaner display)
            text = " ".join(text_lines)
            text = re.sub(r"\[SPEAKER_\d+\]\s*", "", text)

            # Format for ASS
            style_name = f"Kre8Clips_{self.style.animation}"
            lines.append(f"Dialogue: 0,{start_time},{end_time},{style_name},,0,0,0,,{text}")

        return "\n".join(lines)

    def burn_captions(
        self,
        video_path: Path,
        srt_path: Path,
        output_path: Path,
        style: Optional[CaptionStyle] = None
    ) -> Path:
        """Burn captions into video using FFmpeg with ASS styling.

        Args:
            video_path: Input video
            srt_path: SRT file path
            output_path: Output video path
            style: Optional CaptionStyle (uses self.style if None)

        Returns:
            Path to output video (returns video_path unchanged if burn-in fails)
        """
        style_obj = style if style is not None else self.style

        # Generate ASS file for styling
        ass_path = srt_path.with_suffix(".ass")

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()

        ass_content = self._generate_full_ass(srt_content, style_obj)

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        # Try multiple FFmpeg subtitle burn-in strategies
        burned = self._try_burn_with_ffmpeg(video_path, ass_path, output_path)

        if not burned:
            # Fallback: try SRT directly
            burned = self._try_burn_with_srt(video_path, srt_path, output_path)

        if not burned:
            # Last resort: copy video as-is, captions stay in SRT file
            import shutil
            try:
                shutil.copy(str(video_path), str(output_path))
            except Exception:
                pass
            # Return original path so caller still has valid file
            return video_path

        return output_path

    def _try_burn_with_ffmpeg(
        self,
        video_path: Path,
        ass_path: Path,
        output_path: Path,
    ) -> bool:
        """Try FFmpeg ASS burn-in with multiple escaping strategies."""
        strategies = [
            # Strategy 1: direct path, no special chars
            lambda: self._run_ffmpeg(["ffmpeg", "-y", "-i", str(video_path),
                "-vf", f"ass={ass_path}",
                "-c:a", "copy", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                str(output_path)]),

            # Strategy 2: filter_complex with named output
            lambda: self._run_ffmpeg(["ffmpeg", "-y", "-i", str(video_path),
                "-filter_complex", f"[0:v]ass={ass_path}[v]",
                "-map", "[v]", "-map", "0:a",
                "-c:a", "copy", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                str(output_path)]),

            # Strategy 3: absolute path without special chars
            lambda: self._run_ffmpeg(["ffmpeg", "-y", "-i", str(video_path),
                "-vf", f"ass={str(ass_path).replace(' ', '_').replace('(', '_').replace(')', '_')}",
                "-c:a", "copy", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                str(output_path)]),
        ]

        for strategy in strategies:
            try:
                retcode, _, _ = strategy()
                if retcode == 0 and output_path.exists():
                    return True
            except Exception:
                continue

        return False

    def _try_burn_with_srt(
        self,
        video_path: Path,
        srt_path: Path,
        output_path: Path,
    ) -> bool:
        """Try FFmpeg SRT burn-in."""
        strategies = [
            lambda: self._run_ffmpeg(["ffmpeg", "-y", "-i", str(video_path),
                "-vf", f"subtitles={srt_path}:force_style='FontName=Arial,FontSize={self.style.font_size},Bold=1,PrimaryColour=&H00FFFFFF,Outline=2'",
                "-c:a", "copy", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                str(output_path)]),
            lambda: self._run_ffmpeg(["ffmpeg", "-y", "-i", str(video_path),
                "-vf", f"subtitles={srt_path}",
                "-c:a", "copy", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                str(output_path)]),
        ]

        for strategy in strategies:
            try:
                retcode, _, _ = strategy()
                if retcode == 0 and output_path.exists():
                    return True
            except Exception:
                continue

        return False

    def _run_ffmpeg(self, cmd: list) -> tuple:
        """Run FFmpeg command, return (returncode, stdout, stderr)."""
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr

    def _generate_full_ass(self, srt_content: str, style: CaptionStyle) -> str:
        """Generate complete ASS file from SRT content."""
        # Build ASS header
        ass = """[Script Info]
Title: Kre8Clips Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

"""

        # Add styles
        ass += self._generate_ass_style_section()

        # Add events
        ass += self._generate_ass_events_section(srt_content)

        return ass

    def _generate_ass_style_section(self) -> str:
        """Generate ASS style section."""
        margin_v = int(100 - self.style.vertical_position * 100)

        styles = f"""[V4 Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kre8Clips_pop,Arial,{self.style.font_size},{self.style.font_color},{self.style.font_color},{self.style.stroke_color},&H00000000,{1 if self.style.bold else 0},0,0,0,100,100,0,0,1,{self.style.stroke_width:.1f},0,5,20,20,{margin_v},1
Style: Kre8Clips_fade,Arial,{self.style.font_size},{self.style.font_color},{self.style.font_color},{self.style.stroke_color},&H00000000,{1 if self.style.bold else 0},0,0,0,100,100,0,0,1,{self.style.stroke_width:.1f},0,5,20,20,{margin_v},1
Style: Kre8Clips_typewriter,Arial,{self.style.font_size},{self.style.font_color},{self.style.font_color},{self.style.stroke_color},&H00000000,{1 if self.style.bold else 0},0,0,0,100,100,0,0,1,{self.style.stroke_width:.1f},0,5,20,20,{margin_v},1
Style: Kre8Clips_none,Arial,{self.style.font_size},{self.style.font_color},{self.style.font_color},{self.style.stroke_color},&H00000000,{1 if self.style.bold else 0},0,0,0,100,100,0,0,1,{self.style.stroke_width:.1f},0,5,20,20,{margin_v},1

"""
        return styles

    def _generate_ass_events_section(self, srt_content: str) -> str:
        """Generate ASS events section from SRT."""
        events = "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"

        for block in srt_content.strip().split("\n\n"):
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue

            timestamp = lines[1].replace(",", ".")
            start_str, end_str = timestamp.split(" --> ")

            text = " ".join(lines[2:])
            text = text.replace("\n", "\\N")

            events += f"Dialogue: 0,{start_str},{end_str},Kre8Clips_{self.style.animation},,0,0,0,,{text}\n"

        return events + "\n"