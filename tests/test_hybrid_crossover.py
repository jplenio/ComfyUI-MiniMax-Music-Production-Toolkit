"""Hybrid crossover tests (F07 / T26).

The additive mode used to compute a whole-signal low-pass it never read, and
both modes designed the same FIR kernel twice.  The output must be unchanged;
the work must not be.
"""
from __future__ import annotations

import importlib
import json
import unittest

import numpy as np
import torch

import _toolkit_bootstrap

_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
hf = importlib.import_module(f"{_PACKAGE.__name__}.audio_hf_repair")

ADDITIVE = "Original + FlashSR air"
REPLACE = "Hybrid replace above crossover"


def _audio(frames=4096, channels=2, rate=48000, seed=0):
    rng = np.random.default_rng(seed)
    return {
        "waveform": torch.from_numpy(rng.standard_normal((1, channels, frames)).astype(np.float32) * 0.2),
        "sample_rate": rate,
    }


class KernelDesignTests(unittest.TestCase):
    def test_design_is_reusable_and_matches_the_wrapper(self):
        x = np.zeros((1, 1, 1024), dtype=np.float32)
        wrapped, taps = hf._fir_lowpass(x, 48000, 13500.0, 2000.0)
        kernel, direct_taps = hf._design_lowpass(48000, 13500.0, 2000.0)
        self.assertEqual(taps, direct_taps)
        np.testing.assert_array_equal(hf._apply_fir(x, kernel), wrapped)

    def test_clipping_rules_of_the_design_are_unchanged(self):
        kernel, taps = hf._design_lowpass(48000, 1.0, 1.0)  # absurd values get clamped
        self.assertEqual(taps % 2, 1, "taps stay odd")
        self.assertGreaterEqual(taps, 257)
        self.assertEqual(kernel.ndim, 1)


class CrossoverParityTests(unittest.TestCase):
    """Both modes must produce exactly what the old code produced."""

    def _reference(self, mode, original, flashsr, crossover=13500.0, transition=2000.0, mix=0.45):
        o = original["waveform"].numpy()
        f = flashsr["waveform"].numpy()
        fsr = flashsr["sample_rate"]
        low_o, taps = hf._fir_lowpass(o, fsr, crossover, transition)
        low_f, _ = hf._fir_lowpass(f, fsr, crossover, transition)
        high_f = f - low_f
        if mode == REPLACE:
            y = low_o + np.float32(mix) * high_f
        else:
            y = o + np.float32(mix) * high_f
        return np.asarray(y, dtype=np.float32), taps

    def _run(self, mode, original, flashsr, **kwargs):
        node = hf.FlashSRHybridCrossover()
        out, report_json, info = node.process(
            original, flashsr, mode,
            kwargs.get("crossover", 13500.0), kwargs.get("transition", 2000.0), kwargs.get("mix", 0.45),
        )
        return out, json.loads(report_json), info

    def test_additive_mode_is_unchanged(self):
        original = _audio(seed=1)
        flashsr = _audio(seed=2)
        out, report, _info = self._run(ADDITIVE, original, flashsr)
        expected, taps = self._reference(ADDITIVE, original, flashsr)
        np.testing.assert_array_equal(out["waveform"].numpy(), expected)
        self.assertEqual(report["fir_taps"], taps, "the tap count must still be reported")
        self.assertEqual(report["mode"], ADDITIVE)

    def test_replace_mode_is_unchanged(self):
        original = _audio(seed=3)
        flashsr = _audio(seed=4)
        out, report, _info = self._run(REPLACE, original, flashsr)
        expected, taps = self._reference(REPLACE, original, flashsr)
        np.testing.assert_array_equal(out["waveform"].numpy(), expected)
        self.assertEqual(report["fir_taps"], taps)

    def test_both_modes_report_the_same_taps(self):
        original = _audio(seed=5)
        flashsr = _audio(seed=6)
        _out_a, report_a, _i = self._run(ADDITIVE, original, flashsr)
        _out_b, report_b, _i = self._run(REPLACE, original, flashsr)
        self.assertEqual(report_a["fir_taps"], report_b["fir_taps"])

    def test_additive_mode_designs_once_and_convolves_once(self):
        original = _audio(seed=7)
        flashsr = _audio(seed=8)
        designs = []
        convolutions = []

        real_design = hf._design_lowpass
        real_apply = hf._apply_fir

        def counting_design(*args, **kwargs):
            designs.append(args)
            return real_design(*args, **kwargs)

        def counting_apply(x, h):
            convolutions.append(x.shape)
            return real_apply(x, h)

        hf._design_lowpass = counting_design
        hf._apply_fir = counting_apply
        try:
            self._run(ADDITIVE, original, flashsr)
        finally:
            hf._design_lowpass = real_design
            hf._apply_fir = real_apply

        self.assertEqual(len(designs), 1, "the kernel must be designed once per run")
        self.assertEqual(len(convolutions), 1, "the unused low_o convolution must be gone")

    def test_replace_mode_designs_once_and_convolves_both_signals(self):
        original = _audio(seed=9)
        flashsr = _audio(seed=10)
        designs = []
        convolutions = []

        real_design = hf._design_lowpass
        real_apply = hf._apply_fir

        def counting_design(*args, **kwargs):
            designs.append(args)
            return real_design(*args, **kwargs)

        def counting_apply(x, h):
            convolutions.append(x.shape)
            return real_apply(x, h)

        hf._design_lowpass = counting_design
        hf._apply_fir = counting_apply
        try:
            self._run(REPLACE, original, flashsr)
        finally:
            hf._design_lowpass = real_design
            hf._apply_fir = real_apply

        self.assertEqual(len(designs), 1)
        self.assertEqual(len(convolutions), 2, "this mode genuinely needs both low-passed signals")

    def test_pass_through_modes_still_skip_the_filter_entirely(self):
        original = _audio(seed=11)
        flashsr = _audio(seed=12)
        node = hf.FlashSRHybridCrossover()
        original_only, report_a_json, _i = node.process(original, flashsr, "Original SRC only", 13500.0, 2000.0, 0.45)
        flashsr_only, report_b_json, _i = node.process(original, flashsr, "FlashSR only", 13500.0, 2000.0, 0.45)
        report_a = json.loads(report_a_json)
        report_b = json.loads(report_b_json)
        self.assertEqual(report_a["fir_taps"], 0)
        self.assertEqual(report_b["fir_taps"], 0)
        np.testing.assert_array_equal(original_only["waveform"].numpy().shape, original["waveform"].numpy().shape)
        np.testing.assert_array_equal(flashsr_only["waveform"].numpy(), flashsr["waveform"].numpy())


if __name__ == "__main__":
    unittest.main()
