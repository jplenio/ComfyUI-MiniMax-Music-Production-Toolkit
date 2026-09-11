"""Memory-shape tests for the audio stages (IMPROVE-TODO A03).

A03 reduces temporary/buffer churn without changing a single sample.  The tests
therefore compare against a reference implementation of the *old* formula and
assert exact (bit) equality where the change is provably order-preserving, plus
the ownership rule: an incoming array is never modified in place.
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_toolkit_modules():
    pkg_name = "_toolkit_audio_memory_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in (
        "toolkit_logging",
        "comfy_resources",
        "model_downloader",
        "progress_utils",
        "audio_utils",
        "audio_declip",
        "audio_hf_repair",
    ):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


MODULES = load_toolkit_modules()
flashsr = sys.modules.pop("_toolkit_audio_memory_test.flashsr_audio", None)
utils = MODULES["audio_utils"]
declip = MODULES["audio_declip"]
hf = MODULES["audio_hf_repair"]

import numpy as np  # noqa: E402


def load_flashsr():
    pkg_name = "_toolkit_audio_memory_test"
    full = f"{pkg_name}.flashsr_audio"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, ROOT / "flashsr_audio.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


flashsr = load_flashsr()


class OwnershipContractTests(unittest.TestCase):
    def test_the_ownership_contract_is_documented(self):
        doc = utils.__doc__ or ""
        self.assertIn("Ownership contract", doc)
        self.assertIn("never modified in place", doc)
        self.assertIn("scratch", doc)


class OlaFinalizeTests(unittest.TestCase):
    def reference(self, acc, weight_sum):
        weights = weight_sum.copy()
        weights[weights == 0] = 1.0
        return (acc / weights[None, :]).astype(np.float32)

    def test_the_in_place_divide_matches_the_old_formula_exactly(self):
        rng = np.random.default_rng(7)
        acc = rng.standard_normal((2, 5000)).astype(np.float32)
        weight_sum = rng.random(5000).astype(np.float32)
        weight_sum[::97] = 0.0  # the zero-weight edge case
        expected = self.reference(acc.copy(), weight_sum.copy())
        result = flashsr._finalize_ola(acc, weight_sum)
        self.assertTrue(np.array_equal(result, expected), "the in-place divide must be bit-identical")

    def test_the_result_is_the_accumulator_itself(self):
        acc = np.ones((1, 16), np.float32)
        weight_sum = np.full(16, 2.0, np.float32)
        result = flashsr._finalize_ola(acc, weight_sum)
        self.assertIs(result, acc, "no temporary output array may be allocated")

    def test_the_weight_sum_is_not_mutated(self):
        acc = np.ones((1, 8), np.float32)
        weight_sum = np.zeros(8, np.float32)
        before = weight_sum.copy()
        flashsr._finalize_ola(acc, weight_sum)
        self.assertTrue(np.array_equal(weight_sum, before), "the caller's weights must stay untouched")

    def test_all_zero_weights_keep_the_accumulator(self):
        acc = np.full((1, 4), 3.0, np.float32)
        result = flashsr._finalize_ola(acc, np.zeros(4, np.float32))
        self.assertTrue(np.allclose(result, 3.0))


# A03 removed one full-length copy here (the owned output stays, the per-channel
# copy became a reused scratch buffer).  A block-wise float64 energy accumulation
# in audio_hf_repair was measured and rejected - see that module's comment.


class DeclipScratchTests(unittest.TestCase):
    def signal(self, samples=20000):
        rng = np.random.default_rng(5)
        x = (rng.standard_normal(samples) * 0.2).astype(np.float32)
        # A clipped region so the repair path actually runs.
        x[1000:1100] = 1.0
        x[5000:5040] = -1.0
        return x

    def test_the_scratch_path_matches_the_owning_path_exactly(self):
        x = self.signal()
        from_own_copy, stats_a = declip._repair_channel(x, 48000, 98.0, 0.5, 4, 16, 30.0, 3.0, False)
        scratch = np.empty(x.shape[0], dtype=np.float32)
        from_scratch, stats_b = declip._repair_channel(x, 48000, 98.0, 0.5, 4, 16, 30.0, 3.0, False, out=scratch)
        self.assertTrue(np.array_equal(from_own_copy, from_scratch), "the scratch path must not change a sample")
        self.assertEqual(stats_a["repaired_regions"], stats_b["repaired_regions"])

    def test_the_scratch_path_does_not_modify_the_input(self):
        x = self.signal()
        before = x.copy()
        scratch = np.empty(x.shape[0], dtype=np.float32)
        declip._repair_channel(x, 48000, 98.0, 0.5, 4, 16, 30.0, 3.0, False, out=scratch)
        self.assertTrue(np.array_equal(x, before), "the channel input must stay byte-identical")

    def test_the_returned_array_aliases_the_scratch_buffer(self):
        x = self.signal()
        scratch = np.empty(x.shape[0], dtype=np.float32)
        repaired, _stats = declip._repair_channel(x, 48000, 98.0, 0.5, 4, 16, 30.0, 3.0, False, out=scratch)
        self.assertTrue(
            np.shares_memory(repaired, scratch),
            "the documented aliasing is what makes the buffer reuse possible",
        )

    def test_the_scratch_buffer_is_reused_across_channels(self):
        # Two channels of the same node run must not allocate two scratch buffers.
        first = self.signal(8000)
        second = self.signal(8000)
        scratch = np.empty(first.shape[0], dtype=np.float32)
        a, _ = declip._repair_channel(first, 48000, 98.0, 0.5, 4, 16, 30.0, 3.0, False, out=scratch)
        a_copy = a.copy()
        b, _ = declip._repair_channel(second, 48000, 98.0, 0.5, 4, 16, 30.0, 3.0, False, out=scratch)
        self.assertTrue(np.shares_memory(b, scratch))
        self.assertFalse(np.shares_memory(a_copy, scratch))
        self.assertTrue(np.array_equal(a_copy, a))


class NodeInputImmutabilityTests(unittest.TestCase):
    def make_audio(self, channels=1, samples=20000):
        import torch

        rng = np.random.default_rng(13)
        data = (rng.standard_normal((1, channels, samples)) * 0.2).astype(np.float32)
        data[0, :, 1000:1050] = 1.0
        return {"waveform": torch.from_numpy(data), "sample_rate": 48000}

    @staticmethod
    def call_with_defaults(node, function_name, audio):
        """Run a node with its own declared widget defaults (no guessed order)."""
        spec = node.INPUT_TYPES()
        kwargs = {"audio": audio}
        for section in ("required", "optional"):
            for name, entry in (spec.get(section) or {}).items():
                if name == "audio":
                    continue
                options = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else {}
                if isinstance(options, dict) and options.get("forceInput"):
                    continue
                if isinstance(options, dict) and "default" in options:
                    kwargs[name] = options["default"]
                elif isinstance(entry[0], (list, tuple)) and entry[0]:
                    kwargs[name] = entry[0][0]
                else:
                    kwargs[name] = {"INT": 0, "FLOAT": 0.0, "BOOLEAN": False, "STRING": ""}.get(str(entry[0]))
        return getattr(node, function_name)(**kwargs)

    def test_declip_leaves_the_incoming_tensor_untouched(self):
        import torch

        audio = self.make_audio(channels=2)
        before = audio["waveform"].clone()
        self.call_with_defaults(declip.AudioDeclipRepair(), "process", audio)
        self.assertTrue(torch.equal(audio["waveform"], before), "a node must not write into its input")

    def test_hf_repair_leaves_the_incoming_tensor_untouched(self):
        import torch

        audio = self.make_audio(channels=2)
        before = audio["waveform"].clone()
        self.call_with_defaults(hf.HFCymbalShimmerRepair(), "process", audio)
        self.assertTrue(torch.equal(audio["waveform"], before), "a node must not write into its input")


if __name__ == "__main__":
    unittest.main()
