"""Tests for the FlashSR batch/device/determinism fixes (IMPROVE-TODO A01).

The task calls the batch handling a bugfix: ``[B, C, T]`` was silently reduced to
item 0, so a batch of two returned one result.  These tests pin the whole
guarantee set - every item is processed, length/channels/rate survive, a cancel
between chunks stops cleanly, an RNG seed is honoured without leaking into other
nodes, and a failed device transfer never leaves a half-moved model in the cache.
No weights are needed: the runner and the model are faked.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_flashsr():
    pkg_name = "_toolkit_flashsr_batch_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in (
        "toolkit_logging",
        "comfy_resources",
        "model_downloader",
        "progress_utils",
        "flashsr_audio",
    ):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded["flashsr_audio"]


flashsr = load_flashsr()
PROGRESS = sys.modules["_toolkit_flashsr_batch_test.progress_utils"]


class FakeBar:
    def update_absolute(self, value):
        pass


class FakeModel:
    """Returns its input scaled by ``gain`` (optionally with noise)."""

    def __init__(self, gain=1.0, noise=0.0):
        self.gain = gain
        self.noise = noise
        self.calls = []

    def __call__(self, x, lowpass_input=False):
        import torch

        self.calls.append(tuple(x.shape))
        y = x * self.gain
        if self.noise:
            y = y + torch.randn_like(x) * self.noise
        return y


class FlashSRBatchTestCase(unittest.TestCase):
    def setUp(self):
        import torch

        self.torch = torch
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.weights = Path(self._tmp.name)
        for name in ("student_ldm.pth", "sr_vocoder.pth", "vae.pth"):
            (self.weights / name).write_bytes(b"x")

        self.model = FakeModel()
        self.runner = {"model": self.model, "device": "cpu", "requested_device": "cpu", "fallback": False}
        self.original_get_runner = flashsr._get_runner
        self.patch(flashsr, "_ensure_flashsr_weights", lambda auto_download: self.weights)
        self.patch(flashsr, "_get_runner", lambda weights_dir: self.runner)
        self.patch(PROGRESS, "make_progress_bar", lambda total: FakeBar())
        flashsr._runner_cache.clear()

    def patch(self, obj, name, value):
        original = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, original)

    def make_audio(self, items, sr=48000):
        """items: list of [C, S] numpy arrays -> one batched AUDIO tensor."""
        import numpy as np

        stacked = np.stack(items).astype("float32")
        return {"waveform": self.torch.from_numpy(stacked), "sample_rate": sr}

    def node(self):
        return flashsr.MiniMaxFlashSRAudio()


class BatchPreservationTests(FlashSRBatchTestCase):
    def test_a_batch_of_two_returns_two_results(self):
        import numpy as np

        item_a = np.full((1, 288000), 0.10, np.float32)
        item_b = np.full((1, 288000), 0.20, np.float32)
        audio, _settings = self.node().upscale(self.make_audio([item_a, item_b]), auto_download=False)
        waveform = audio["waveform"]
        self.assertEqual(tuple(waveform.shape)[0], 2, "both batch items must survive")
        self.assertEqual(tuple(waveform.shape)[1], 1)
        means = [float(waveform[0].mean()), float(waveform[1].mean())]
        self.assertLess(means[0], means[1], "item 2 must be item 2, not a copy of item 1")

    def test_channels_and_rate_are_preserved(self):
        import numpy as np

        item = np.zeros((2, 288000), np.float32)
        audio, _settings = self.node().upscale(
            self.make_audio([item, item]), output_sr="44100", auto_download=False
        )
        self.assertEqual(tuple(audio["waveform"].shape)[:2], (2, 2))
        self.assertEqual(audio["sample_rate"], 44100)

    def test_every_item_is_actually_inferred(self):
        import json

        import numpy as np

        item = np.zeros((1, 288000), np.float32)
        _audio, settings = self.node().upscale(self.make_audio([item, item, item]), auto_download=False)
        parsed = json.loads(settings)
        self.assertEqual(parsed["batch_items"], 3)
        self.assertGreaterEqual(
            len(self.model.calls), 6, "each of the three items needs its own chunks (>=2 per item)"
        )

    def test_unequal_items_are_padded_by_the_batch_helper(self):
        import numpy as np

        # A tensor batch is uniform by construction, so unequal items can only
        # reach the helper from a future caller or a list input; the padding is
        # defensive and unit-tested where it lives.
        audio, padded = flashsr._make_audio_batch(
            48000, [np.zeros((1, 100), np.float32), np.zeros((1, 150), np.float32)]
        )
        self.assertTrue(padded)
        self.assertEqual(tuple(audio["waveform"].shape), (2, 1, 150))

    def test_a_uniform_batch_is_not_flagged_as_padded(self):
        import json

        import numpy as np

        item = np.zeros((1, 288000), np.float32)
        _audio, settings = self.node().upscale(self.make_audio([item, item]), auto_download=False)
        self.assertFalse(json.loads(settings)["padded"])

    def test_input_audio_is_not_modified_in_place(self):
        import numpy as np

        item = np.full((1, 288000), 0.25, np.float32)
        audio = self.make_audio([item, item])
        before = audio["waveform"].clone()
        self.node().upscale(audio, auto_download=False)
        self.assertTrue(self.torch.equal(audio["waveform"], before), "the incoming tensor must stay untouched")


class DeterminismTests(FlashSRBatchTestCase):
    def setUp(self):
        super().setUp()
        self.model = FakeModel(noise=0.01)
        self.runner["model"] = self.model

    def test_a_seed_makes_the_run_reproducible(self):
        import numpy as np

        item = np.zeros((1, 288000), np.float32)
        first, _ = self.node().upscale(self.make_audio([item]), auto_download=False, seed=1234)
        second, _ = self.node().upscale(self.make_audio([item]), auto_download=False, seed=1234)
        self.assertTrue(
            self.torch.allclose(first["waveform"], second["waveform"]),
            "the same seed must reproduce the stochastic steps",
        )

    def test_without_a_seed_the_historical_random_semantics_stay(self):
        import numpy as np

        item = np.zeros((1, 288000), np.float32)
        first, settings = self.node().upscale(self.make_audio([item]), auto_download=False)
        second, _ = self.node().upscale(self.make_audio([item]), auto_download=False)
        import json

        self.assertIn("unseeded", json.loads(settings)["determinism"])
        self.assertFalse(self.torch.allclose(first["waveform"], second["waveform"]))

    def test_the_seed_does_not_leak_into_the_global_rng(self):
        import numpy as np

        self.torch.manual_seed(7)
        before = self.torch.get_rng_state().clone()
        item = np.zeros((1, 288000), np.float32)
        self.node().upscale(self.make_audio([item]), auto_download=False, seed=99)
        self.assertTrue(
            self.torch.equal(before, self.torch.get_rng_state()),
            "the RNG state must be restored after a seeded run",
        )


class CancellationTests(FlashSRBatchTestCase):
    def test_cancel_between_chunks_stops_the_run(self):
        import numpy as np

        self.patch(flashsr, "_processing_interrupted", lambda: True)
        item = np.zeros((1, 288000), np.float32)
        with self.assertRaises(Exception):
            self.node().upscale(self.make_audio([item]), auto_download=False)
        self.assertEqual(len(self.model.calls), 0, "no chunk may run after a cancel was detected")


class DeviceResolutionTests(unittest.TestCase):
    class FakeCuda:
        def __init__(self, available=True, count=2, current=0):
            self._available = available
            self._count = count
            self._current = current

        def is_available(self):
            return self._available

        def device_count(self):
            return self._count

        def current_device(self):
            return self._current

    def resolve(self, cuda, env=None):
        original = os.environ.pop("MINIMAX_FLASHSR_DEVICE", None)
        try:
            if env is not None:
                os.environ["MINIMAX_FLASHSR_DEVICE"] = env
            return flashsr._resolve_execution_device(types.SimpleNamespace(cuda=cuda))
        finally:
            if env is not None:
                os.environ.pop("MINIMAX_FLASHSR_DEVICE", None)
            if original is not None:
                os.environ["MINIMAX_FLASHSR_DEVICE"] = original

    def test_default_rule_prefers_cuda_then_cpu(self):
        self.assertEqual(self.resolve(self.FakeCuda()), "cuda:0")
        self.assertEqual(self.resolve(self.FakeCuda(available=False)), "cpu")

    def test_explicit_cpu_is_honoured_even_with_cuda_available(self):
        self.assertEqual(self.resolve(self.FakeCuda(), env="cpu"), "cpu")

    def test_explicit_device_index_is_used(self):
        self.assertEqual(self.resolve(self.FakeCuda(count=2), env="cuda:1"), "cuda:1")

    def test_unavailable_explicit_device_warns_and_falls_back(self):
        self.assertEqual(self.resolve(self.FakeCuda(available=False), env="cuda:0"), "cpu")
        self.assertEqual(self.resolve(self.FakeCuda(count=1), env="cuda:5"), "cuda:0")

    def test_unknown_value_ignored(self):
        self.assertEqual(self.resolve(self.FakeCuda(), env="banana"), "cuda:0")


class RunnerFallbackTests(FlashSRBatchTestCase):
    class FakeFlashSR:
        """Counts constructions and can refuse any ``.to()`` for one instance."""

        instances = []
        refuse_cpu_for = set()

        def __init__(self, student, vocoder, vae):
            self.moves = []
            self.index = len(self.instances)
            type(self).instances.append(self)

        def eval(self):
            return self

        def to(self, device):
            self.moves.append(device)
            if str(device).startswith("cuda"):
                raise RuntimeError("CUDA out of memory")
            if str(device) == "cpu" and self.index in type(self).refuse_cpu_for:
                raise RuntimeError("cpu move failed too")
            return self

    def setUp(self):
        super().setUp()
        # These tests exercise the real _get_runner, so the fake installed by the
        # base class is undone here.
        flashsr._get_runner = self.original_get_runner
        self.FakeFlashSR.instances = []
        self.FakeFlashSR.refuse_cpu_for = set()
        self.patch(flashsr, "_resolve_execution_device", lambda torch_module: "cuda:0")
        self.patch(flashsr, "_import_flashsr_model", lambda: self.FakeFlashSR)

    def test_a_failed_transfer_publishes_a_cpu_runner(self):
        runner = flashsr._get_runner(self.weights)
        self.assertEqual(runner["device"], "cpu")
        self.assertEqual(runner["requested_device"], "cuda:0")
        self.assertTrue(runner["fallback"])
        self.assertEqual(len(self.FakeFlashSR.instances), 1, "an undone transfer needs no rebuild")

    def test_an_unrecoverable_transfer_rebuilds_a_clean_cpu_model(self):
        self.FakeFlashSR.refuse_cpu_for = {0}
        runner = flashsr._get_runner(self.weights)
        self.assertEqual(len(self.FakeFlashSR.instances), 2, "the half-moved instance must be discarded")
        self.assertTrue(runner["fallback"])
        self.assertTrue(runner["rebuilt_on_cpu"])
        self.assertEqual(runner["device"], "cpu")

    def test_the_cpu_runner_is_cached_under_the_requested_key(self):
        first = flashsr._get_runner(self.weights)
        second = flashsr._get_runner(self.weights)
        self.assertIs(first, second)
        self.assertEqual(len(self.FakeFlashSR.instances), 1)


if __name__ == "__main__":
    unittest.main()
