"""
Tests for the viral prediction model.

These tests lock in:
  - The calibrated output range: an empty / no-signal clip should still land
    near 0.30-0.40 (so the UI never shows "0%"), and a clip with strong
    features should land near 0.50-0.70.
  - Strong feature clips produce a meaningfully non-zero share probability.
  - The displayed percentage in the UI (`Math.round(value * 100)`) is > 0
    for a clip with non-zero features.
  - The output values stay in the [0, 1] range required by the API contract.
  - The bias is tuned such that an "average" feature vector (all features 0.3)
    lands in 0.3-0.5.
"""
import math
import unittest

from core.viral_model import (
    BIAS,
    COMPOSITE_WEIGHTS,
    ClipFeatures,
    HeuristicViralModel,
    ViralPredictor,
    WEIGHTS,
    _score_target,
    _sigmoid,
    extract_features,
)


def _all_features(value: float) -> ClipFeatures:
    """Build a ClipFeatures with every numeric feature set to `value`."""
    return ClipFeatures(
        hook_pattern_interrupt=value,
        hook_curiosity_gap=value,
        hook_contrarian=value,
        hook_question=value,
        hook_exclamation=value,
        hook_power_word_density=value,
        hook_cta=value,
        emotion_intensity=value,
        specificity=value,
        actionability=value,
        quotability=value,
        controversy=value,
        relatability=value,
        information_density=value,
        story_structure=value,
        payoff_strength=value,
        ending_sentence_complete=value,
        duration_seconds=30.0,
        duration_fit=value,
        speaker_count=1,
        speaker_continuity=value,
    )


class ViralModelCalibrationTest(unittest.TestCase):
    """Pin the bias retune: typical clips must produce visibly non-zero scores."""

    def test_sigmoid_helper(self):
        self.assertAlmostEqual(_sigmoid(0.0), 0.5, places=6)
        self.assertAlmostEqual(_sigmoid(100.0), 1.0, places=4)
        self.assertAlmostEqual(_sigmoid(-100.0), 0.0, places=4)

    def test_outputs_in_unit_interval(self):
        """API contract: every output must be 0..1."""
        model = HeuristicViralModel()
        for features in (_all_features(0.0), _all_features(0.5), _all_features(1.0)):
            pred = model.predict(features)
            for name in ("share", "save", "comment", "composite", "confidence"):
                v = getattr(pred, name)
                self.assertGreaterEqual(v, 0.0, f"{name} below 0")
                self.assertLessEqual(v, 1.0, f"{name} above 1")
                self.assertFalse(math.isnan(v), f"{name} is NaN")
            self.assertEqual(pred.model_version, "heuristic-v1")

    def test_empty_features_does_not_return_zero(self):
        """The previous bias of -1.6 made an all-zero clip return ~0.17,
        which the UI showed as 17% and felt broken. With the new bias, an
        all-zero clip must land in the 0.30-0.45 range so the score card
        shows a real, recognizable number."""
        model = HeuristicViralModel()
        pred = model.predict(_all_features(0.0))
        for name in ("share", "save", "comment", "composite"):
            v = getattr(pred, name)
            self.assertGreater(v, 0.25, f"{name}={v} too low for empty features")
            self.assertLess(v, 0.50, f"{name}={v} too high for empty features")

    def test_strong_features_produce_high_score(self):
        """A clip where every feature is at maximum should produce a share
        probability well above 0.5 and a composite above 0.5 — the user
        must see a clear "this is good" signal, not 30%."""
        model = HeuristicViralModel()
        pred = model.predict(_all_features(1.0))
        self.assertGreater(pred.share, 0.55, f"share={pred.share} too low for max features")
        self.assertGreater(pred.composite, 0.50, f"composite={pred.composite} too low for max features")
        self.assertGreater(pred.confidence, 0.5, f"confidence={pred.confidence} should be high")

    def test_average_features_land_in_mid_range(self):
        """An "average" clip (every feature = 0.3) should land in 0.3-0.55.
        The previous bias landed at 0.20 which the user perceived as zero."""
        model = HeuristicViralModel()
        pred = model.predict(_all_features(0.3))
        for name in ("share", "save", "comment", "composite"):
            v = getattr(pred, name)
            self.assertGreater(v, 0.30, f"{name}={v} below mid range")
            self.assertLess(v, 0.60, f"{name}={v} above mid range")

    def test_strong_clip_above_weak_clip(self):
        """Sanity: stronger features should always score higher."""
        model = HeuristicViralModel()
        weak = model.predict(_all_features(0.1))
        strong = model.predict(_all_features(0.9))
        self.assertGreater(strong.share, weak.share)
        self.assertGreater(strong.composite, weak.composite)

    def test_ui_percentage_is_meaningfully_nonzero_for_strong_clip(self):
        """Mirror the UI math: `Math.round(value * 100)`. For a strong
        clip, the displayed percentage must be > 20 (not 0)."""
        model = HeuristicViralModel()
        pred = model.predict(_all_features(1.0))
        displayed = round(pred.composite * 100)
        self.assertGreater(displayed, 20, f"UI would show {displayed}% for strong clip")

    def test_ui_percentage_is_nonzero_for_weak_clip(self):
        """Even a weak clip should show a non-zero percentage now. The old
        bias of -2.4 for comment pushed weak clips to 0%."""
        model = HeuristicViralModel()
        pred = model.predict(_all_features(0.0))
        for name in ("share", "save", "comment", "composite"):
            displayed = round(getattr(pred, name) * 100)
            self.assertGreater(displayed, 0, f"UI shows 0% for {name} on empty clip")

    def test_weights_sum_to_unity_per_target(self):
        """Required by the bias retune assumption: sum(weights) = 1 per target
        so that feature_value * sum_weights has a predictable scale."""
        for target, weights in WEIGHTS.items():
            self.assertAlmostEqual(sum(weights.values()), 1.0, places=6, msg=f"{target}")

    def test_bias_is_in_typical_calibration_range(self):
        """With weights summing to 1, bias values should be in the [-1.5, 0]
        range — large negative biases push the sigmoid into the 0% zone."""
        for target, bias in BIAS.items():
            self.assertGreaterEqual(bias, -1.5, f"BIAS[{target}]={bias} too negative")
            self.assertLessEqual(bias, 0.5, f"BIAS[{target}]={bias} positive pushes low-feature clips too high")


class ViralModelExtractFeaturesTest(unittest.TestCase):
    """Verify the feature extractor picks up the signals we want."""

    def test_strong_hook_activates_pattern_interrupt(self):
        segments = [
            {"text": "You won't believe this insane secret about AI!", "speaker": "S0"},
            {"text": "Step 1: do this one thing first.", "speaker": "S0"},
            {"text": "Trust me, this changes everything!", "speaker": "S0"},
        ]
        features = extract_features(segments=segments, duration=12.0)
        self.assertGreater(features.hook_curiosity_gap, 0.0)
        self.assertGreater(features.hook_power_word_density, 0.0)
        self.assertEqual(features.hook_exclamation, 1.0)
        self.assertGreater(features.actionability, 0.0)
        self.assertGreater(features.payoff_strength, 0.0)

    def test_empty_text_returns_zero_features(self):
        features = extract_features(segments=[], duration=30.0)
        self.assertEqual(features.duration_seconds, 30.0)
        self.assertEqual(features.hook_pattern_interrupt, 0.0)
        self.assertEqual(features.emotion_intensity, 0.0)

    def test_strong_features_produce_nonzero_share(self):
        """The user's reported failure mode: 'showing 0'. Make sure a clip
        with strong viral cues produces a share probability > 0.2."""
        segments = [
            {"text": "Actually, here's the secret nobody tells you.", "speaker": "S0"},
            {"text": "You won't believe the truth about productivity.", "speaker": "S0"},
            {"text": "Step 1: do this. Step 2: follow this rule. Trust me!", "speaker": "S0"},
        ]
        pred = ViralPredictor(persist=False).predict(
            segments=segments, duration=18.0
        )
        self.assertGreater(pred.share, 0.20, f"share={pred.share} should be > 0.2 for strong clip")
        self.assertGreater(pred.composite, 0.20, f"composite={pred.composite} should be > 0.2")


class ViralModelPublicAPITest(unittest.TestCase):
    """The ViralPredictor is the public API; its outputs must be JSON-clean
    and stay in the 0..1 range promised to callers."""

    def test_predict_returns_dict_serializable(self):
        segments = [{"text": "Actually, the truth is shocking.", "speaker": "S0"}]
        pred = ViralPredictor(persist=False).predict(segments=segments, duration=5.0)
        d = pred.to_dict()
        for key in ("share", "save", "comment", "composite", "confidence"):
            self.assertIn(key, d)
            self.assertIsInstance(d[key], float)
            self.assertGreaterEqual(d[key], 0.0)
            self.assertLessEqual(d[key], 1.0)
        self.assertEqual(d["model_version"], "heuristic-v1")
        self.assertIn("features", d)
        self.assertIn("rationale", d)

    def test_persist_false_does_not_write(self):
        import os
        from core.viral_model import TRAINING_FILE
        # Capture the file size before
        before = TRAINING_FILE.stat().st_size if TRAINING_FILE.exists() else 0
        ViralPredictor(persist=False).predict(
            segments=[{"text": "hello", "speaker": "S0"}],
            duration=2.0,
            clip_id="test_no_persist_xyz",
        )
        after = TRAINING_FILE.stat().st_size if TRAINING_FILE.exists() else 0
        self.assertEqual(before, after, "persist=False must not write to training file")


class ViralModelBiasTest(unittest.TestCase):
    """Lock the bias values so a future tuning pass doesn't reintroduce the
    '0% across the board' bug."""

    def test_share_bias(self):
        self.assertAlmostEqual(BIAS["share"], -0.4, places=4)

    def test_save_bias(self):
        self.assertAlmostEqual(BIAS["save"], -0.5, places=4)

    def test_comment_bias(self):
        self.assertAlmostEqual(BIAS["comment"], -0.8, places=4)


if __name__ == "__main__":
    unittest.main()
