"""Tests for the lazy audio-branch selector (IMPROVE-TODO A04).

Pins the two promises that make the node useful:

* **lazy evaluation actually skips branches** - ``check_lazy_status()`` requests
  only the inputs the chosen profile needs, so an unneeded branch never runs;
* **the output contract belongs to the selector** - rate and length always come
  from the original input, so a replacement branch can never silently change
  them (the trap of the old ``Original SRC only`` mode).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _toolkit_bootstrap as bootstrap  # noqa: E402


def load_toolkit_modules():
    pkg_name = "_toolkit_audio_branch_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in ("toolkit_logging", "audio_utils", "minimax_audio_branch"):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


MODULES = load_toolkit_modules()
branch = MODULES["minimax_audio_branch"]

import numpy as np  # noqa: E402
import torch  # noqa: E402


def audio(seconds=2.0, rate=48000, channels=1, value=0.5):
    frames = int(seconds * rate)
    data = np.full((1, channels, frames), value, np.float32)
    return {"waveform": torch.from_numpy(data), "sample_rate": rate}


class LazyStatusTests(unittest.TestCase):
    def node(self):
        return branch.MiniMaxAudioBranchSelect()

    def test_keep_original_requests_no_branch(self):
        self.assertEqual(
            self.node().check_lazy_status(branch.PROFILE_ORIGINAL, original_audio=audio()),
            [],
        )

    def test_careful_restore_requests_only_the_restored_branch(self):
        pending = self.node().check_lazy_status(branch.PROFILE_CAREFUL, original_audio=audio())
        self.assertEqual(pending, ["restored_audio"])

    def test_a_present_branch_is_not_requested_again(self):
        pending = self.node().check_lazy_status(
            branch.PROFILE_CAREFUL, original_audio=audio(), restored_audio=audio()
        )
        self.assertEqual(pending, [])

    def test_reconstruction_requests_only_the_bandwidth_branch(self):
        pending = self.node().check_lazy_status(
            branch.PROFILE_RECONSTRUCT, original_audio=audio(), restored_audio=audio()
        )
        self.assertEqual(pending, ["bandwidth_audio"])

    def test_a_missing_original_is_requested(self):
        self.assertEqual(
            self.node().check_lazy_status(branch.PROFILE_ORIGINAL),
            ["original_audio"],
        )

    def test_an_unknown_profile_falls_back_to_the_original(self):
        self.assertEqual(
            self.node().check_lazy_status("something else", original_audio=audio()),
            [],
        )


class SelectionTests(unittest.TestCase):
    def node(self):
        return branch.MiniMaxAudioBranchSelect()

    def test_keep_original_passes_the_input_through_untouched(self):
        source = audio(seconds=1.0, channels=2, value=0.25)
        before = source["waveform"].clone()
        out, report, info = self.node().select(branch.PROFILE_ORIGINAL, original_audio=source)
        self.assertTrue(torch.equal(out["waveform"], source["waveform"]))
        self.assertTrue(torch.equal(source["waveform"], before), "the input must stay untouched")
        self.assertEqual(out["sample_rate"], 48000)
        parsed = json.loads(report)
        self.assertIsNone(parsed["replacement_source"])
        self.assertIn("Keep original", info)

    def test_the_output_rate_and_length_come_from_the_original(self):
        source = audio(seconds=2.0, rate=48000)
        replacement = audio(seconds=1.0, rate=44100, value=0.9)  # shorter and at another rate
        out, report, _info = self.node().select(
            branch.PROFILE_CAREFUL, mix=0.5, original_audio=source, restored_audio=replacement
        )
        self.assertEqual(out["sample_rate"], 48000, "the replacement rate must not win")
        self.assertEqual(out["waveform"].shape, source["waveform"].shape, "the original length wins")
        notes = " ".join(json.loads(report)["notes"])
        self.assertIn("resampled", notes)
        self.assertIn("padded", notes)

    def test_a_longer_replacement_is_trimmed_not_length_extended(self):
        source = audio(seconds=1.0)
        replacement = audio(seconds=3.0, value=1.0)
        out, report, _info = self.node().select(
            branch.PROFILE_RECONSTRUCT, mix=1.0, original_audio=source, bandwidth_audio=replacement
        )
        self.assertEqual(out["waveform"].shape[2], source["waveform"].shape[2])
        self.assertIn("trimmed", " ".join(json.loads(report)["notes"]))

    def test_mix_is_applied_to_the_replacement(self):
        source = audio(seconds=0.5, value=0.0)
        replacement = audio(seconds=0.5, value=1.0)
        out, _report, _info = self.node().select(
            branch.PROFILE_CAREFUL, mix=0.25, original_audio=source, restored_audio=replacement
        )
        self.assertAlmostEqual(float(out["waveform"].mean()), 0.25, places=5)

    def test_mix_zero_keeps_the_original_and_says_so(self):
        source = audio(seconds=0.5, value=0.3)
        replacement = audio(seconds=0.5, value=1.0)
        out, report, _info = self.node().select(
            branch.PROFILE_CAREFUL, mix=0.0, original_audio=source, restored_audio=replacement
        )
        self.assertTrue(torch.allclose(out["waveform"], source["waveform"], atol=1e-6))
        self.assertIn("mix=0", " ".join(json.loads(report)["notes"]))

    def test_a_missing_branch_is_a_clear_error_naming_the_profile(self):
        with self.assertRaises(ValueError) as ctx:
            self.node().select(branch.PROFILE_CAREFUL, original_audio=audio())
        self.assertIn("Careful restore", str(ctx.exception))
        self.assertIn("restored_audio", str(ctx.exception))

    def test_an_unknown_profile_is_rejected_with_the_choices(self):
        with self.assertRaises(ValueError) as ctx:
            self.node().select("nope", original_audio=audio())
        self.assertIn("unknown profile", str(ctx.exception))
        self.assertIn(branch.PROFILE_ORIGINAL, str(ctx.exception))

    def test_a_channel_mismatch_is_conformed_and_reported(self):
        source = audio(seconds=0.5, channels=2)
        replacement = audio(seconds=0.5, channels=1, value=0.8)
        out, report, _info = self.node().select(
            branch.PROFILE_RECONSTRUCT, mix=1.0, original_audio=source, bandwidth_audio=replacement
        )
        self.assertEqual(out["waveform"].shape[1], 2)
        self.assertIn("channels conformed", " ".join(json.loads(report)["notes"]))


class PreviewTests(unittest.TestCase):
    def node(self):
        return branch.MiniMaxAudioBranchSelect()

    def test_a_preview_trims_the_result_and_states_the_limit(self):
        source = audio(seconds=60.0)
        out, report, _info = self.node().select(
            branch.PROFILE_ORIGINAL, preview_seconds=20.0, original_audio=source
        )
        self.assertAlmostEqual(out["waveform"].shape[2] / 48000.0, 20.0, places=3)
        parsed = json.loads(report)
        self.assertEqual(parsed["preview"]["applied_seconds"], 20.0)
        self.assertIn("already ran in full upstream", " ".join(parsed["notes"]))

    def test_a_short_request_is_clamped_into_the_documented_window(self):
        source = audio(seconds=60.0)
        _out, report, _info = self.node().select(
            branch.PROFILE_ORIGINAL, preview_seconds=5.0, original_audio=source
        )
        self.assertEqual(json.loads(report)["preview"]["applied_seconds"], branch.PREVIEW_MIN_SECONDS)

    def test_zero_means_full_render(self):
        source = audio(seconds=2.0)
        out, report, _info = self.node().select(
            branch.PROFILE_ORIGINAL, preview_seconds=0.0, original_audio=source
        )
        self.assertEqual(out["waveform"].shape, source["waveform"].shape)
        self.assertEqual(json.loads(report)["preview"]["applied_seconds"], 0.0)

    def test_a_preview_longer_than_the_selection_does_not_pad_it(self):
        source = audio(seconds=5.0)
        out, report, _info = self.node().select(
            branch.PROFILE_ORIGINAL, preview_seconds=25.0, original_audio=source
        )
        self.assertAlmostEqual(out["waveform"].shape[2] / 48000.0, 5.0, places=3)
        self.assertIn("nothing was trimmed", " ".join(json.loads(report)["notes"]))


class RegistrationTests(unittest.TestCase):
    def test_the_node_is_registered_and_documented(self):
        package, _host = bootstrap.load_entry_point()
        self.assertIn("MiniMaxAudioBranchSelect", package.NODE_CLASS_MAPPINGS)
        self.assertTrue((ROOT / "web" / "docs" / "MiniMaxAudioBranchSelect.md").is_file())
        self.assertEqual(bootstrap.NODE_OWNER["MiniMaxAudioBranchSelect"], "minimax_audio_branch")

    def test_the_profiles_are_offered_in_the_node_interface(self):
        spec = branch.MiniMaxAudioBranchSelect.INPUT_TYPES()
        self.assertEqual(list(spec["required"]["profile"][0]), list(branch.PROFILES))
        self.assertIn("restored_audio", spec["optional"])
        self.assertIn("bandwidth_audio", spec["optional"])


if __name__ == "__main__":
    unittest.main()
