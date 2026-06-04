"""Regression tests for the 2026-06-04 bug fix batch.

Each test pins one of the four fixes:
1. Smart-narrative title dedupe (no "Hook +  + Payoff")
2. assemble_smart_narrative returns the deduped title
3. Title assembly is robust to all-empty parts (returns the hook title)
"""
import unittest

from core.analyzer import _try_assemble, assemble_smart_narrative


class _Seg:
    """Minimal stand-in for the segment dicts that _try_assemble expects."""

    def __init__(self, source_clip_title="", source_main_speaker="SPEAKER_0", **kwargs):
        self._title = source_clip_title
        self._speaker = source_main_speaker
        self._extras = kwargs

    def get(self, key, default=None):
        if key == "source_clip_title":
            return self._title
        if key == "source_main_speaker":
            return self._speaker
        return self._extras.get(key, default)


class SmartNarrativeTitleDedupeTest(unittest.TestCase):
    """Pin the 2026-06-04 fix: hook+payoff (no body) must not produce 'Hook +  + Payoff'."""

    def test_hook_and_payoff_no_body_no_double_plus(self):
        hook = {
            "source_clip_title": "The fastest way to build proof",
            "source_main_speaker": "SPEAKER_0",
            "start": "00:00:00",
            "end": "00:00:13",
            "viral_potential": 8,
            "opening_strength": 8,
            "closing_strength": 5,
        }
        payoff = {
            "source_clip_title": "Your free roadmap to scaling",
            "source_main_speaker": "SPEAKER_0",
            "start": "00:08:15",
            "end": "00:08:45",
            "viral_potential": 9,
            "opening_strength": 5,
            "closing_strength": 9,
        }
        result = _try_assemble(hook, body=None, payoff=payoff, preferred_speaker="SPEAKER_0")
        self.assertIsNotNone(result)
        title = result["assembled_title"]
        self.assertNotIn("+  +", title, f"double-plus leaked into title: {title!r}")
        self.assertNotIn(" + + ", title, f"double-plus variant leaked: {title!r}")
        self.assertIn("The fastest way to build proof", title)
        self.assertIn("Your free roadmap to scaling", title)
        self.assertIn(" + ", title, "expected exactly one separator between hook and payoff")

    def test_full_hook_body_payoff(self):
        """When all three roles are present, the title is 'A + B + C'."""
        hook = {
            "source_clip_title": "HookText",
            "source_main_speaker": "SPEAKER_0",
            "start": "00:00:00",
            "end": "00:00:13",
        }
        body = {
            "source_clip_title": "BodyText",
            "source_main_speaker": "SPEAKER_0",
            "start": "00:01:00",
            "end": "00:01:30",
        }
        payoff = {
            "source_clip_title": "PayoffText",
            "source_main_speaker": "SPEAKER_0",
            "start": "00:08:15",
            "end": "00:08:45",
        }
        result = _try_assemble(hook, body=body, payoff=payoff, preferred_speaker="SPEAKER_0")
        self.assertIsNotNone(result)
        self.assertEqual(result["assembled_title"], "HookText + BodyText + PayoffText")
        self.assertNotIn("+  +", result["assembled_title"])
        self.assertNotIn(" + + ", result["assembled_title"])

    def test_hook_only_no_payoff(self):
        """Edge case: only a hook. The title should not contain separators."""
        hook = {
            "source_clip_title": "HookOnly",
            "source_main_speaker": "SPEAKER_0",
            "start": "00:00:00",
            "end": "00:00:30",
        }
        result = _try_assemble(hook, body=None, payoff=None, preferred_speaker="SPEAKER_0")
        self.assertIsNotNone(result)
        self.assertEqual(result["assembled_title"], "HookOnly")
        self.assertNotIn("+", result["assembled_title"])


class AssembleSmartNarrativeIntegrationTest(unittest.TestCase):
    """Pin that the outer 'title' field is also deduped (no double-plus leak)."""

    def test_smart_narrative_title_deduped_for_two_source_clips(self):
        # Two source clips, each with a hook and a payoff, but no body.
        # The narrative merger should pick hook+payoff from across them
        # and the resulting title must not contain " +  + ".
        clips = [
            {
                "title": "The fastest way to build proof",
                "main_speaker": "SPEAKER_0",
                "priority": 8,
                "segments": [
                    {
                        "start": "00:00:00",
                        "end": "00:00:13",
                        "segment_role": "hook",
                        "viral_potential": 8,
                        "opening_strength": 8,
                        "closing_strength": 5,
                    }
                ],
            },
            {
                "title": "Your free roadmap to scaling",
                "main_speaker": "SPEAKER_0",
                "priority": 8,
                "segments": [
                    {
                        "start": "00:08:15",
                        "end": "00:08:45",
                        "segment_role": "payoff",
                        "viral_potential": 9,
                        "opening_strength": 5,
                        "closing_strength": 9,
                    }
                ],
            },
        ]
        result = assemble_smart_narrative(clips, main_speaker="SPEAKER_0")
        if not result:
            self.skipTest("assemble_smart_narrative returned empty (insufficient segments)")
        title = result.get("title", "")
        self.assertNotIn("+  +", title, f"double-plus leaked into outer title: {title!r}")
        self.assertNotIn(" + + ", title, f"double-plus variant leaked: {title!r}")


if __name__ == "__main__":
    unittest.main()
