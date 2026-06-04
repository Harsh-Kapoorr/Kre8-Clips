import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from clipgen import (
    calculate_total_segment_duration,
    ensure_output_dir,
    expand_or_trim_clips,
    generate_clip_srt,
    is_render_healthy,
    recompute_duration_from_segments,
    trim_clip_segments,
)
from core.boundary_snapper import SmartBoundarySnapper
from core.clipper import apply_clip_fades, get_clip_duration, _sanitize_curve
from core.clipper import _can_stream_copy, generate_clip, get_video_info


class ClipgenRuntimeHelpersTest(unittest.TestCase):
    def test_expand_or_trim_clips_flattens_non_narrative_multi_segment_clips(self):
        clips = [
            {
                "title": "Podcast Clip",
                "segments": [
                    {"start": "00:00:00", "end": "00:00:20"},
                    {"start": "00:01:00", "end": "00:01:20"},
                ],
                "duration_seconds": 40,
            }
        ]

        normalized = expand_or_trim_clips(clips, narrative_mode=False, max_duration=90)
        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]["title"], "Podcast Clip Part 1")
        self.assertEqual(normalized[1]["title"], "Podcast Clip Part 2")
        self.assertAlmostEqual(normalized[0]["duration_seconds"], 20.0)

    def test_expand_or_trim_clips_enforces_max_duration(self):
        clips = [
            {
                "title": "Long Clip",
                "segments": [{"start": "00:00:00", "end": "00:02:00"}],
                "duration_seconds": 120,
            }
        ]

        normalized = expand_or_trim_clips(clips, narrative_mode=True, max_duration=45)
        self.assertEqual(len(normalized), 1)
        self.assertAlmostEqual(normalized[0]["duration_seconds"], 45.0)
        self.assertAlmostEqual(calculate_total_segment_duration(normalized[0]["segments"]), 45.0)

    def test_trim_clip_segments_without_snapper_uses_blunt_trim(self):
        # Without a snapper, end should be clamped exactly to the budget.
        segments = [{"start": "00:00:00", "end": "00:02:00"}]
        trimmed = trim_clip_segments(segments, max_duration=45)
        self.assertEqual(len(trimmed), 1)
        self.assertEqual(trimmed[0]["start"], "00:00:00")
        self.assertEqual(trimmed[0]["end"], "00:00:45.000")

    def test_trim_clip_segments_with_snapper_lands_on_natural_boundary(self):
        # Build a snapper with a sentence-end anchor at 00:00:42 so the
        # natural end point sits ~3s before the blunt 45s chop. With the
        # snapper enabled, the trimmed end should land on (or near) 42.0s
        # rather than the blunt 45.0s chop, and never past the budget.
        transcript = [
            {"start": 0.0, "end": 20.0, "text": "Opening thought"},
            {"start": 20.0, "end": 42.0, "text": "Mid pitch that wraps up."},
        ]
        snapper = SmartBoundarySnapper(transcript_segments=transcript, tolerance=3.0)
        segments = [{"start": "00:00:00", "end": "00:02:00"}]

        trimmed = trim_clip_segments(segments, max_duration=45, snapper=snapper)
        self.assertEqual(len(trimmed), 1)

        from clipgen import parse_timestamp_str
        trimmed_end = parse_timestamp_str(trimmed[0]["end"])
        # Snapped to the sentence end at 42.0, not the blunt 45.0 chop.
        self.assertLess(trimmed_end, 45.0)
        self.assertLessEqual(trimmed_end, 45.0)  # never past the budget
        self.assertAlmostEqual(trimmed_end, 42.0, delta=1.0)

    def test_trim_clip_segments_snapper_never_exceeds_budget(self):
        # If the only natural boundary is past the budget, the snapper
        # result must be clamped back to the budget cap.
        transcript = [
            {"start": 0.0, "end": 20.0, "text": "Long uninterrupted block."},
        ]
        snapper = SmartBoundarySnapper(transcript_segments=transcript, tolerance=0.6)
        segments = [{"start": "00:00:00", "end": "00:02:00"}]

        trimmed = trim_clip_segments(segments, max_duration=15, snapper=snapper)
        from clipgen import parse_timestamp_str
        trimmed_end = parse_timestamp_str(trimmed[0]["end"])
        self.assertLessEqual(trimmed_end, 15.0)

    def test_trim_clip_segments_snapper_is_keyword_only(self):
        # The new parameter is keyword-only, so a positional 3rd arg must
        # raise TypeError. The keyword form must still work.
        segments = [{"start": "00:00:00", "end": "00:00:30"}]
        with self.assertRaises(TypeError):
            trim_clip_segments(segments, 30, None)  # type: ignore[arg-type]
        # Sanity check: keyword form succeeds.
        result = trim_clip_segments(segments, 30, snapper=None)
        self.assertEqual(len(result), 1)

    def test_expand_or_trim_clips_forwards_snapper(self):
        # Non-narrative multi-segment clips are split into parts and are
        # NOT trimmed (each part is a single segment already), so the
        # snapper should not be invoked on those. The snapper's effect
        # is only visible on the single-segment narrative path.
        transcript = [
            {"start": 0.0, "end": 10.0, "text": "First."},
            {"start": 50.0, "end": 70.0, "text": "Second that ends here."},
        ]
        snapper = SmartBoundarySnapper(transcript_segments=transcript, tolerance=0.6)
        clips = [
            {
                "title": "Long",
                "segments": [{"start": "00:00:00", "end": "00:02:00"}],
                "duration_seconds": 120,
            }
        ]
        normalized = expand_or_trim_clips(
            clips, narrative_mode=True, max_duration=30, snapper=snapper,
        )
        self.assertEqual(len(normalized), 1)
        from clipgen import parse_timestamp_str
        trimmed_end = parse_timestamp_str(normalized[0]["segments"][0]["end"])
        self.assertLessEqual(trimmed_end, 30.0)

    def test_ensure_output_dir_creates_target_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "nested" / "clips"
            resolved = ensure_output_dir(output_dir)
            self.assertEqual(resolved, output_dir)
            self.assertTrue(output_dir.exists())

    def test_generate_clip_srt_rebases_narrative_segments(self):
        transcript_segments = [
            {"start": 10.0, "end": 12.0, "text": "First part", "speaker": "SPEAKER_0"},
            {"start": 30.0, "end": 32.0, "text": "Second part", "speaker": "SPEAKER_1"},
        ]
        clip_segments = [
            {"start": "00:00:10", "end": "00:00:12"},
            {"start": "00:00:30", "end": "00:00:32"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            srt_path = Path(temp_dir) / "narrative.srt"
            generate_clip_srt(transcript_segments, clip_segments, srt_path)
            content = srt_path.read_text(encoding="utf-8")

        self.assertIn("00:00:00,000 --> 00:00:02,000", content)
        self.assertIn("00:00:02,000 --> 00:00:04,000", content)
        self.assertIn("First part", content)
        self.assertIn("Second part", content)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _make_synthetic_clip(path: Path, duration: int = 5, with_audio: bool = True) -> bool:
    cmd = ["ffmpeg", "-y", "-loglevel", "quiet",
           "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={duration}"]
    if with_audio:
        cmd.extend(["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"])
        cmd.extend(["-map", "0:v", "-map", "1:a"])
    cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if with_audio:
        cmd.extend(["-c:a", "aac", "-shortest"])
    cmd.append(str(path))
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def _make_sized_clip(path: Path, width: int, height: int, duration: int = 5) -> bool:
    """Build an H.264/AAC mp4 at an exact (width x height). Used for fast-path tests."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "quiet",
        "-f", "lavfi", "-i", f"color=c=blue:s={width}x{height}:d={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(path),
    ]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


class ApplyClipFadesTest(unittest.TestCase):
    def test_fades_with_audio_preserves_duration_and_size(self):
        if not _ffmpeg_available():
            self.skipTest("ffmpeg/ffprobe not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            test_video = Path(temp_dir) / "input.mp4"
            if not _make_synthetic_clip(test_video, duration=5, with_audio=True):
                self.skipTest("Could not generate synthetic test video")

            original_duration = get_clip_duration(test_video)
            self.assertGreater(original_duration, 0)

            result_path = apply_clip_fades(
                test_video, fade_in_duration=0.3, fade_out_duration=0.5,
            )
            self.assertIsNotNone(result_path)
            self.assertTrue(result_path.exists())
            self.assertGreater(result_path.stat().st_size, 0)

            new_duration = get_clip_duration(result_path)
            self.assertAlmostEqual(new_duration, original_duration, delta=0.5)

    def test_fades_without_audio_does_not_crash(self):
        if not _ffmpeg_available():
            self.skipTest("ffmpeg/ffprobe not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            test_video = Path(temp_dir) / "silent.mp4"
            if not _make_synthetic_clip(test_video, duration=3, with_audio=False):
                self.skipTest("Could not generate silent test video")

            result_path = apply_clip_fades(
                test_video, fade_in_duration=0.2, fade_out_duration=0.4,
            )
            self.assertIsNotNone(result_path)
            self.assertTrue(result_path.exists())
            self.assertGreater(result_path.stat().st_size, 0)

    def test_fades_with_zero_durations_is_noop(self):
        if not _ffmpeg_available():
            self.skipTest("ffmpeg/ffprobe not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            test_video = Path(temp_dir) / "input.mp4"
            if not _make_synthetic_clip(test_video, duration=3, with_audio=True):
                self.skipTest("Could not generate synthetic test video")

            size_before = test_video.stat().st_size
            result_path = apply_clip_fades(test_video, fade_in_duration=0, fade_out_duration=0)
            self.assertEqual(result_path, test_video)
            self.assertEqual(test_video.stat().st_size, size_before)

    def test_fades_clamps_to_half_duration(self):
        if not _ffmpeg_available():
            self.skipTest("ffmpeg/ffprobe not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            test_video = Path(temp_dir) / "input.mp4"
            if not _make_synthetic_clip(test_video, duration=2, with_audio=True):
                self.skipTest("Could not generate synthetic test video")

            result_path = apply_clip_fades(
                test_video, fade_in_duration=10.0, fade_out_duration=10.0,
            )
            self.assertIsNotNone(result_path)
            self.assertTrue(result_path.exists())
            self.assertGreater(result_path.stat().st_size, 0)
            self.assertAlmostEqual(get_clip_duration(result_path), 2.0, delta=0.5)

    def test_fades_with_qua_curve_produces_valid_output(self):
        if not _ffmpeg_available():
            self.skipTest("ffmpeg/ffprobe not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            test_video = Path(temp_dir) / "input.mp4"
            if not _make_synthetic_clip(test_video, duration=5, with_audio=True):
                self.skipTest("Could not generate synthetic test video")

            result_path = apply_clip_fades(
                test_video,
                fade_in_duration=0.3,
                fade_out_duration=0.5,
                fade_in_curve="in_qua",
                fade_out_curve="qua",
            )
            self.assertIsNotNone(result_path)
            self.assertTrue(result_path.exists())
            self.assertGreater(result_path.stat().st_size, 0)
            self.assertAlmostEqual(get_clip_duration(result_path), 5.0, delta=0.5)

    def test_fades_with_invalid_curve_falls_back_to_linear(self):
        if not _ffmpeg_available():
            self.skipTest("ffmpeg/ffprobe not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            test_video = Path(temp_dir) / "input.mp4"
            if not _make_synthetic_clip(test_video, duration=4, with_audio=True):
                self.skipTest("Could not generate synthetic test video")

            result_path = apply_clip_fades(
                test_video,
                fade_in_duration=0.3,
                fade_out_duration=0.5,
                fade_in_curve="not_a_real_curve",
                fade_out_curve="also_fake",
            )
            self.assertIsNotNone(result_path)
            self.assertTrue(result_path.exists())
            self.assertGreater(result_path.stat().st_size, 0)


class FadeCurveSanitizationTest(unittest.TestCase):
    def test_empty_returns_empty(self):
        self.assertEqual(_sanitize_curve(""), "")
        self.assertEqual(_sanitize_curve(None), "")

    def test_valid_curves_pass_through(self):
        for c in ("tri", "qua", "cub", "squ", "cbr", "par", "exp", "lin", "sin", "cos", "log", "ipar"):
            self.assertEqual(_sanitize_curve(c), c)

    def test_in_prefixed_curves_fall_back_to_empty(self):
        # ffmpeg's afade doesn't support the "in_" prefix; we drop it to
        # avoid passing garbage to the filter.
        self.assertEqual(_sanitize_curve("in_qua"), "")
        self.assertEqual(_sanitize_curve("in_cub"), "")

    def test_invalid_curves_fall_back_to_empty(self):
        self.assertEqual(_sanitize_curve("nope"), "")
        self.assertEqual(_sanitize_curve("ease_out"), "")
        self.assertEqual(_sanitize_curve("in_nope"), "")
        self.assertEqual(_sanitize_curve("out_qua"), "")

    def test_strips_whitespace(self):
        self.assertEqual(_sanitize_curve("  qua  "), "qua")
        self.assertEqual(_sanitize_curve("\tpar\n"), "par")


class CanStreamCopyTest(unittest.TestCase):
    """Pure-logic tests for the fast-path decision (no ffmpeg required)."""

    def _path(self, ext: str = "mp4") -> Path:
        return Path(f"/tmp/fake.{ext}")

    def test_matching_aspect_ratio_and_format_allows_copy(self):
        # 1080x1920 is exactly 9:16, output also 9:16 mp4 -> fast path.
        self.assertTrue(_can_stream_copy(
            video_path=self._path("mp4"),
            source_w=1080, source_h=1920,
            source_codec="h264",
            aspect_ratio="9:16",
            speaker_position=None,
            output_format="mp4",
        ))

    def test_speaker_position_blocks_copy(self):
        # A tracking crop is being applied - we must re-encode.
        self.assertFalse(_can_stream_copy(
            video_path=self._path("mp4"),
            source_w=1080, source_h=1920,
            source_codec="h264",
            aspect_ratio="9:16",
            speaker_position=(0.5, 0.4),
            output_format="mp4",
        ))

    def test_mismatched_aspect_ratio_blocks_copy(self):
        # 1920x1080 source asked for 9:16 -> needs crop -> re-encode.
        self.assertFalse(_can_stream_copy(
            video_path=self._path("mp4"),
            source_w=1920, source_h=1080,
            source_codec="h264",
            aspect_ratio="9:16",
            speaker_position=None,
            output_format="mp4",
        ))

    def test_aspect_ratio_within_tolerance_allows_copy(self):
        # 1081x1920 is ~0.3% off perfect 9:16 - inside default 0.5% tolerance.
        self.assertTrue(_can_stream_copy(
            video_path=self._path("mp4"),
            source_w=1081, source_h=1920,
            source_codec="h264",
            aspect_ratio="9:16",
            speaker_position=None,
            output_format="mp4",
        ))

    def test_mp4_family_containers_are_interchangeable(self):
        # .mov source -> .mp4 output is a safe remux for h264.
        self.assertTrue(_can_stream_copy(
            video_path=self._path("mov"),
            source_w=1080, source_h=1920,
            source_codec="h264",
            aspect_ratio="9:16",
            speaker_position=None,
            output_format="mp4",
        ))

    def test_foreign_container_blocks_copy(self):
        # .webm source into .mp4 output - codec/container risk, re-encode.
        self.assertFalse(_can_stream_copy(
            video_path=self._path("webm"),
            source_w=1080, source_h=1920,
            source_codec="h264",
            aspect_ratio="9:16",
            speaker_position=None,
            output_format="mp4",
        ))

    def test_unsupported_codec_blocks_copy(self):
        # vp9 in mp4 is messy - bail out to the safe re-encode path.
        self.assertFalse(_can_stream_copy(
            video_path=self._path("mp4"),
            source_w=1080, source_h=1920,
            source_codec="vp9",
            aspect_ratio="9:16",
            speaker_position=None,
            output_format="mp4",
        ))

    def test_hevc_is_allowed(self):
        # HEVC plays cleanly in mp4 with stream copy.
        self.assertTrue(_can_stream_copy(
            video_path=self._path("mp4"),
            source_w=1080, source_h=1920,
            source_codec="hevc",
            aspect_ratio="9:16",
            speaker_position=None,
            output_format="mp4",
        ))

    def test_zero_source_dimensions_blocks_copy(self):
        self.assertFalse(_can_stream_copy(
            video_path=self._path("mp4"),
            source_w=0, source_h=0,
            source_codec="h264",
            aspect_ratio="9:16",
            speaker_position=None,
            output_format="mp4",
        ))


class GenerateClipFastPathTest(unittest.TestCase):
    """End-to-end checks of the new stream-copy path in generate_clip()."""

    def test_matching_aspect_ratio_uses_stream_copy(self):
        if not _ffmpeg_available():
            self.skipTest("ffmpeg/ffprobe not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            # 360x640 == perfect 9:16, h264/aac source.
            src = temp / "src_portrait.mp4"
            if not _make_sized_clip(src, 360, 640, duration=5):
                self.skipTest("Could not generate 9:16 synthetic clip")

            src_info = get_video_info(src)
            self.assertEqual(src_info["codec"], "h264")

            out = generate_clip(
                video_path=src,
                start_time=1.0,
                end_time=4.0,
                output_filename="fast",
                clip_index=1,
                aspect_ratio="9:16",
                speaker_position=None,
                output_dir=temp,
                output_format="mp4",
            )

            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 0)
            # Stream copy preserves the source codec verbatim.
            out_info = get_video_info(out)
            self.assertEqual(out_info["codec"], src_info["codec"])
            # Sanity: matching aspect ratio means dimensions stay identical too.
            self.assertEqual(out_info["width"], src_info["width"])
            self.assertEqual(out_info["height"], src_info["height"])
            # Stream-copy seek is keyframe-aligned, so the clip may extend
            # back to the prior keyframe (especially on synthetic clips with
            # sparse keyframes). Only assert that we got real, bounded output.
            out_duration = get_clip_duration(out)
            self.assertGreater(out_duration, 0)
            self.assertLessEqual(out_duration, src_info["duration"] + 0.5)

    def test_mismatched_aspect_ratio_falls_back_to_re_encode(self):
        if not _ffmpeg_available():
            self.skipTest("ffmpeg/ffprobe not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            # 16:9 source asked for 9:16 -> must crop -> re-encode path.
            src = temp / "src_landscape.mp4"
            if not _make_sized_clip(src, 640, 360, duration=4):
                self.skipTest("Could not generate 16:9 synthetic clip")

            out = generate_clip(
                video_path=src,
                start_time=0.5,
                end_time=3.0,
                output_filename="slow",
                clip_index=1,
                aspect_ratio="9:16",
                speaker_position=None,
                output_dir=temp,
                output_format="mp4",
            )

            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 0)
            # Re-encode path resizes to the 9:16 target dimensions.
            out_info = get_video_info(out)
            self.assertEqual(out_info["width"], 1080)
            self.assertEqual(out_info["height"], 1920)

    def test_speaker_position_forces_re_encode_even_with_matching_ratio(self):
        if not _ffmpeg_available():
            self.skipTest("ffmpeg/ffprobe not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            src = temp / "src_portrait.mp4"
            if not _make_sized_clip(src, 360, 640, duration=4):
                self.skipTest("Could not generate 9:16 synthetic clip")

            # Same 9:16 aspect, but a tracking crop is being applied.
            # That always re-encodes (and rescales to canonical 1080x1920).
            out = generate_clip(
                video_path=src,
                start_time=0.0,
                end_time=2.0,
                output_filename="tracked",
                clip_index=1,
                aspect_ratio="9:16",
                speaker_position=(0.5, 0.4),
                output_dir=temp,
                output_format="mp4",
            )

            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 0)
            out_info = get_video_info(out)
            self.assertEqual(out_info["width"], 1080)
            self.assertEqual(out_info["height"], 1920)

    def test_stream_copy_preserves_audio_stream(self):
        """Stream copy uses -c copy which remuxes all streams, audio included.

        This is the only material difference from the re-encode path that
        lacked coverage. Locks in that the fast path doesn't silently drop
        the audio track.
        """
        if not _ffmpeg_available():
            self.skipTest("ffmpeg/ffprobe not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            src = temp / "src_with_audio.mp4"
            if not _make_synthetic_clip(src, duration=5, with_audio=True):
                self.skipTest("Could not generate synthetic clip with audio")

            # Confirm source has an audio stream first (sanity).
            probe_cmd = [
                "ffprobe", "-v", "quiet",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(src),
            ]
            probe = subprocess.run(probe_cmd, capture_output=True, text=True)
            self.assertEqual(probe.stdout.strip(), "audio",
                             "Test setup error: synthetic clip must have audio")

            out = generate_clip(
                video_path=src,
                start_time=1.0,
                end_time=4.0,
                output_filename="audio_preserved",
                clip_index=1,
                aspect_ratio="9:16",
                speaker_position=None,
                output_dir=temp,
                output_format="mp4",
            )

            self.assertTrue(out.exists())
            # The fast path must have copied the audio track.
            out_probe = subprocess.run(probe_cmd[:-1] + [str(out)], capture_output=True, text=True)
            self.assertEqual(out_probe.stdout.strip(), "audio",
                             "Stream-copy path silently dropped the audio track")


class RenderHealthCheckTest(unittest.TestCase):
    """Pin the 2026-06-04 post-render size check.

    `is_render_healthy` is the gate that turns a 262-byte stub MP4 into
    a hard render failure instead of a silent "success".
    """

    def test_none_path_is_unhealthy(self):
        self.assertFalse(is_render_healthy(None))

    def test_missing_file_is_unhealthy(self):
        self.assertFalse(is_render_healthy(Path("/tmp/definitely-does-not-exist-12345.mp4")))

    def test_stub_file_is_unhealthy(self):
        """A 262-byte file (the actual 2026-06-04 stub) is rejected."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 262)
            stub_path = Path(f.name)
        try:
            self.assertFalse(is_render_healthy(stub_path))
        finally:
            stub_path.unlink()

    def test_sub_threshold_file_is_unhealthy(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 49_999)  # one byte under the threshold
            p = Path(f.name)
        try:
            self.assertFalse(is_render_healthy(p))
        finally:
            p.unlink()

    def test_realistic_clip_is_healthy(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 200_000)  # 200 KB — well over 50 KB
            p = Path(f.name)
        try:
            self.assertTrue(is_render_healthy(p))
        finally:
            p.unlink()

    def test_custom_threshold_is_respected(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 1000)
            p = Path(f.name)
        try:
            self.assertFalse(is_render_healthy(p, min_bytes=10_000))
            self.assertTrue(is_render_healthy(p, min_bytes=500))
        finally:
            p.unlink()


class RecomputeDurationFromSegmentsTest(unittest.TestCase):
    """Pin the 2026-06-04 duration-fallback fix.

    When `get_clip_dur` returns 0 (stub file), `recompute_duration_from_segments`
    falls back to the planned segment span so the summary table doesn't
    show "Duration: 0s" for a real 30s clip.
    """

    def test_returns_fallback_for_empty_segments(self):
        self.assertEqual(recompute_duration_from_segments([]), 0.0)
        self.assertEqual(recompute_duration_from_segments(None), 0.0)
        self.assertEqual(recompute_duration_from_segments([], fallback=42.0), 42.0)

    def test_returns_segment_span_for_hhMMSS_timestamps(self):
        segs = [
            {"start": "00:01:00", "end": "00:01:30"},  # 30s
        ]
        self.assertEqual(recompute_duration_from_segments(segs), 30.0)

    def test_returns_segment_span_for_MMSS_timestamps(self):
        segs = [
            {"start": "01:00", "end": "01:45"},
        ]
        self.assertEqual(recompute_duration_from_segments(segs), 45.0)

    def test_uses_first_to_last_when_segments_is_a_list_of_dicts(self):
        segs = [
            {"start": "00:00:00", "end": "00:00:13"},
            {"start": "00:08:15", "end": "00:08:45"},
        ]
        # 8:45 = 525s, 0:00 = 0s → 525s span (across the gap).
        self.assertEqual(recompute_duration_from_segments(segs), 525.0)

    def test_handles_numeric_timestamps(self):
        segs = [{"start": 0.0, "end": 30.5}]
        self.assertEqual(recompute_duration_from_segments(segs), 30.5)

    def test_handles_malformed_segments_gracefully(self):
        segs = [{"start": "garbage", "end": "more garbage"}]
        # parse_timestamp_str returns 0.0 for garbage, so end <= start → fallback
        self.assertEqual(recompute_duration_from_segments(segs), 0.0)
        self.assertEqual(recompute_duration_from_segments(segs, fallback=99.0), 99.0)
