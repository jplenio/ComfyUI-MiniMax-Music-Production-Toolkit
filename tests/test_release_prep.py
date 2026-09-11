"""Audio Release Prep behaviour tests (F05 / T06).

The loudness meter shells out to FFmpeg, so these tests stub
``audio_release_prep._measure_bs1770`` and verify the numerical contract of the
static-gain stage: the intended output changes, the *input* tensor never does.
"""
from __future__ import annotations

import importlib
import json
import unittest

import numpy as np
import torch

from _toolkit_bootstrap import load_entry_point

_PACKAGE, _HOST = load_entry_point()
release = importlib.import_module(f"{_PACKAGE.__name__}.audio_release_prep")


def make_audio(frames=2048, channels=2, sample_rate=44100, seed=7, dtype=torch.float32):
    rng = np.random.default_rng(seed)
    data = (rng.standard_normal((1, channels, frames)) * 0.25).astype(np.float32)
    return {"waveform": torch.tensor(data, dtype=dtype), "sample_rate": sample_rate}


class StubMeter(unittest.TestCase):
    """Replaces the FFmpeg loudness meter with fixed measurements."""

    def setUp(self):
        self.calls = []
        self.saved = release._measure_bs1770

        def fake(data_tc, sr):
            self.calls.append((data_tc.copy(), sr))
            peak = float(np.max(np.abs(data_tc))) if data_tc.size else 0.0
            return {
                "integrated_lufs": -20.0,
                "true_peak_dbtp": -3.0,
                "lra_lu": 5.0,
                "threshold_lufs": -30.0,
            }

        release._measure_bs1770 = fake
        self.addCleanup(lambda: setattr(release, "_measure_bs1770", self.saved))


class ReleaseBufferOwnershipTests(StubMeter):
    def test_same_rate_static_gain_does_not_mutate_the_input(self):
        audio = make_audio()
        original = audio["waveform"].clone()

        out, report_json, _info = release.AudioReleasePrep().process(
            audio, "keep", "Streaming Safe -14 LUFS / -1 dBTP", -14.0, -1.0
        )

        self.assertTrue(torch.equal(audio["waveform"], original), "input AUDIO tensor was mutated")
        # requested gain 6 dB (from -20 to -14), true-peak headroom 2 dB -> 2 dB applied
        gain = np.float32(10.0 ** (2.0 / 20.0))
        expected = np.asarray(original[0].numpy(), dtype=np.float32) * gain
        np.testing.assert_allclose(out["waveform"][0].numpy(), expected, rtol=0, atol=1e-6)
        report = json.loads(report_json)
        self.assertEqual(report["batch_reports"][0]["applied_constant_gain_db"], 2.0)
        self.assertTrue(report["batch_reports"][0]["gain_limited_by_true_peak"])

    def test_same_rate_input_and_output_do_not_share_storage(self):
        audio = make_audio()
        out, _report, _info = release.AudioReleasePrep().process(
            audio, "keep", "Custom", -14.0, -1.0
        )
        self.assertFalse(np.shares_memory(audio["waveform"].numpy(), out["waveform"].numpy()))

    def test_branched_consumer_sees_unmodified_audio(self):
        # A second graph branch keeps a reference to the original AUDIO object.
        audio = make_audio()
        branch_reference = audio["waveform"]
        branch_snapshot = branch_reference.clone()
        release.AudioReleasePrep().process(audio, "keep", "Custom", -10.0, -2.0)
        self.assertTrue(torch.equal(branch_reference, branch_snapshot))

    def test_resampled_path_leaves_input_untouched(self):
        audio = make_audio(sample_rate=44100)
        original = audio["waveform"].clone()
        out, _report, _info = release.AudioReleasePrep().process(
            audio, "48000", "Streaming Safe -14 LUFS / -1 dBTP", -14.0, -1.0
        )
        self.assertTrue(torch.equal(audio["waveform"], original))
        self.assertEqual(out["sample_rate"], 48000)

    def test_resample_only_never_scales_and_never_mutates(self):
        audio = make_audio()
        original = audio["waveform"].clone()
        out, report_json, _info = release.AudioReleasePrep().process(
            audio, "keep", "Resample only", -14.0, -1.0
        )
        self.assertTrue(torch.equal(audio["waveform"], original))
        report = json.loads(report_json)
        self.assertEqual(report["gain_strategy"], "none")
        self.assertEqual(self.calls, [], "the meter must not run in resample-only mode")
        np.testing.assert_allclose(out["waveform"].numpy(), original.numpy(), rtol=0, atol=0)

    def test_bypass_returns_the_original_object(self):
        audio = make_audio()
        out, report_json, _info = release.AudioReleasePrep().process(
            audio, "44100", "Bypass", -14.0, -1.0
        )
        self.assertIs(out, audio)
        self.assertFalse(json.loads(report_json)["enabled"])

    def test_float64_input_is_owned_by_the_node(self):
        audio = make_audio(dtype=torch.float64)
        original = audio["waveform"].clone()
        out, _report, _info = release.AudioReleasePrep().process(
            audio, "keep", "Custom", -14.0, -1.0
        )
        self.assertTrue(torch.equal(audio["waveform"], original))
        self.assertEqual(out["waveform"].dtype, torch.float32)


if __name__ == "__main__":
    unittest.main()
