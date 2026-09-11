"""Shared AUDIO helper tests (F06/F07 / T24).

Two guarantees matter here: the validators keep their behaviour *and* their
messages per caller, and the single Kaiser SRC kernel is numerically identical
to a direct SciPy call - the whole point of de-duplicating it.
"""
from __future__ import annotations

import importlib
import unittest

import numpy as np
import torch

import _toolkit_bootstrap

_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
audio_utils = importlib.import_module(f"{_PACKAGE.__name__}.audio_utils")
declip = importlib.import_module(f"{_PACKAGE.__name__}.audio_declip")
lowpass = importlib.import_module(f"{_PACKAGE.__name__}.audio_lowpass")
hf_repair = importlib.import_module(f"{_PACKAGE.__name__}.audio_hf_repair")
release = importlib.import_module(f"{_PACKAGE.__name__}.audio_release_prep")
smart = importlib.import_module(f"{_PACKAGE.__name__}.save_audio_smart_prefix")
absolute = importlib.import_module(f"{_PACKAGE.__name__}.save_audio_absolute")
flashsr = importlib.import_module(f"{_PACKAGE.__name__}.flashsr_audio")


def good_audio(frames=256, channels=2, rate=44100):
    return {
        "waveform": torch.zeros((1, channels, frames), dtype=torch.float32),
        "sample_rate": rate,
    }


class ProblemMatrixTests(unittest.TestCase):
    def test_valid_audio_returns_waveform_and_rate(self):
        waveform, rate = audio_utils.validate_audio(good_audio(rate=48000), error_label="T")
        self.assertEqual(rate, 48000)
        self.assertEqual(tuple(waveform.shape), (1, 2, 256))

    def test_problem_codes(self):
        cases = [
            ("not a dict", "not_mapping"),
            ({}, "missing_fields"),
            ({"waveform": torch.zeros(3)}, "missing_fields"),
            ({"waveform": "x", "sample_rate": 1}, "not_tensor"),
            ({"waveform": torch.zeros(2, 3), "sample_rate": 1}, "wrong_ndim"),
        ]
        for value, expected in cases:
            with self.subTest(value=type(value).__name__):
                self.assertEqual(audio_utils.audio_problem(value), expected)

    def test_rate_check_is_opt_in(self):
        bad_rate = {"waveform": torch.zeros((1, 1, 4)), "sample_rate": 0}
        self.assertIsNone(audio_utils.audio_problem(bad_rate))
        self.assertEqual(audio_utils.audio_problem(bad_rate, require_positive_rate=True), "invalid_rate")
        non_numeric = {"waveform": torch.zeros((1, 1, 4)), "sample_rate": "abc"}
        self.assertEqual(audio_utils.audio_problem(non_numeric, require_positive_rate=True), "invalid_rate")

    def test_compact_template_messages(self):
        with self.assertRaises(ValueError) as ctx:
            audio_utils.validate_audio("nope", error_label="Node")
        self.assertEqual(str(ctx.exception), "Node: expected ComfyUI AUDIO with waveform and sample_rate.")
        with self.assertRaises(ValueError) as ctx:
            audio_utils.validate_audio({"waveform": torch.zeros(2, 2), "sample_rate": 1}, error_label="Node")
        self.assertEqual(str(ctx.exception), "Node: waveform must be torch.Tensor [B,C,T].")

    def test_separate_template_messages(self):
        with self.assertRaises(ValueError) as ctx:
            audio_utils.validate_audio(
                {"waveform": torch.zeros(2, 2), "sample_rate": 1}, error_label="Node", template="separate"
            )
        self.assertEqual(str(ctx.exception), "Node: expected waveform [B,C,T], got (2, 2).")
        with self.assertRaises(ValueError) as ctx:
            audio_utils.validate_audio(
                {"waveform": torch.zeros((1, 1, 4)), "sample_rate": 0},
                error_label="Node", template="separate", require_positive_rate=True,
            )
        self.assertEqual(str(ctx.exception), "Node: invalid sample rate 0.")


class PerCallerBehaviourTests(unittest.TestCase):
    """Each caller keeps its own label, policy and message shape."""

    def test_restoration_and_mastering_labels(self):
        for module, expected in (
            (declip, "audio: expected ComfyUI AUDIO with waveform and sample_rate."),
            (hf_repair, "audio: expected ComfyUI AUDIO with waveform and sample_rate."),
            (release, "Audio Release Prep: expected ComfyUI AUDIO with waveform and sample_rate."),
            (smart, "Save Audio Smart Prefix: expected ComfyUI AUDIO with waveform and sample_rate."),
        ):
            with self.subTest(module=module.__name__):
                with self.assertRaises(ValueError) as ctx:
                    module._validate_audio("nope")
                self.assertEqual(str(ctx.exception), expected)

    def test_separate_message_callers(self):
        with self.assertRaises(ValueError) as ctx:
            lowpass._validate_audio("nope")
        self.assertEqual(str(ctx.exception), "FlashSR Lowpass Lab: AUDIO input must be a ComfyUI AUDIO dictionary.")
        with self.assertRaises(ValueError) as ctx:
            absolute._validate_audio({"waveform": torch.zeros(2, 2), "sample_rate": 1})
        self.assertEqual(
            str(ctx.exception), "Save Audio Absolute Path: expected waveform [B,C,T], got (2, 2)."
        )

    def test_rate_policy_differs_per_caller(self):
        bad_rate = {"waveform": torch.zeros((1, 1, 8)), "sample_rate": 0}
        # No explicit rate check historically:
        for module in (declip, hf_repair, release):
            with self.subTest(module=module.__name__):
                self.assertEqual(module._validate_audio(bad_rate)[1], 0)
        # Explicit rejection historically:
        for module in (smart, lowpass, absolute):
            with self.subTest(module=module.__name__):
                with self.assertRaises(ValueError) as ctx:
                    module._validate_audio(bad_rate)
                self.assertIn("invalid sample rate", str(ctx.exception))

    def test_custom_label_is_forwarded(self):
        with self.assertRaises(ValueError) as ctx:
            declip._validate_audio("nope", label="Declip Repair")
        self.assertTrue(str(ctx.exception).startswith("Declip Repair:"))


class ResamplerParityTests(unittest.TestCase):
    def test_same_rate_returns_a_float32_view_for_float32_input(self):
        data = np.zeros((1, 2, 64), dtype=np.float32)
        out = audio_utils.resample_kaiser_polyphase(data, 44100, 44100)
        self.assertEqual(out.dtype, np.float32)
        self.assertTrue(np.shares_memory(out, data), "the historic shortcut returns a view, not a copy")
        # A higher-precision input is converted (and therefore copied), as before.
        as64 = audio_utils.resample_kaiser_polyphase(np.zeros((1, 1, 8), dtype=np.float64), 44100, 44100)
        self.assertEqual(as64.dtype, np.float32)

    def test_different_rate_scales_the_length(self):
        data = np.zeros((1, 1, 1000), dtype=np.float32)
        out = audio_utils.resample_kaiser_polyphase(data, 44100, 48000)
        self.assertEqual(out.shape, (1, 1, int(np.ceil(1000 * 48000 / 44100))))
        self.assertFalse(np.shares_memory(out, data))

    def test_kernel_matches_a_direct_scipy_call(self):
        from scipy.signal import resample_poly

        rng = np.random.default_rng(0)
        data = rng.standard_normal((1, 2, 512)).astype(np.float32)
        expected = resample_poly(
            data, 160, 147, axis=-1, window=("kaiser", audio_utils.KAISER_BETA)
        ).astype(np.float32)
        actual = audio_utils.resample_kaiser_polyphase(data, 44100, 48000)
        np.testing.assert_array_equal(actual, expected)

    def test_all_three_src_entry_points_agree(self):
        rng = np.random.default_rng(1)
        data = rng.standard_normal((1, 1, 300)).astype(np.float32)
        results = [
            audio_utils.resample_kaiser_polyphase(data, 32000, 44100),
            hf_repair._resample_hq(data, 32000, 44100),
            release._resample_hq(data, 32000, 44100),
        ]
        for other in results[1:]:
            np.testing.assert_array_equal(results[0], other)

    def test_missing_scipy_uses_the_callers_message(self):
        saved_helper = audio_utils._scipy_resample_poly
        audio_utils._scipy_resample_poly = None
        try:
            with self.assertRaises(RuntimeError) as ctx:
                audio_utils.resample_kaiser_polyphase(
                    np.zeros((1, 1, 4), dtype=np.float32), 44100, 48000,
                    missing_message="Node: scipy required.",
                )
            self.assertEqual(str(ctx.exception), "Node: scipy required.")
        finally:
            audio_utils._scipy_resample_poly = saved_helper

        # The release-prep wrapper keeps its own historic wording.
        saved_release = release.resample_poly
        release.resample_poly = None
        audio_utils._scipy_resample_poly = None
        try:
            with self.assertRaises(RuntimeError) as ctx:
                release._resample_hq(np.zeros((1, 1, 4), dtype=np.float32), 44100, 48000)
            self.assertIn("Audio Release Prep: scipy required for HQ resampling.", str(ctx.exception))
        finally:
            release.resample_poly = saved_release
            audio_utils._scipy_resample_poly = saved_helper

    def test_flashsr_ct_adapter_stays_separate_from_bct_validation(self):
        stereo = np.zeros((2, 100), dtype=np.float32)
        channels, rate = flashsr._to_channel_samples((stereo, 44100))
        self.assertEqual((channels.shape, rate), ((2, 100), 44100))
        # A 2-D waveform is exactly what the FlashSR adapter accepts and what the
        # BCT validator must keep rejecting - the adapters are not merged.
        self.assertEqual(
            audio_utils.audio_problem({"waveform": torch.zeros(2, 100), "sample_rate": 44100}),
            "wrong_ndim",
        )


if __name__ == "__main__":
    unittest.main()
