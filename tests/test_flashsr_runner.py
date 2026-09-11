"""FlashSR runner construction tests (F08 / T21).

Fake model + fake torch, so the construction contract is verifiable without
weights: resolve a concrete device, fail early on missing files, undo a failed
transfer, and never publish a broken runner into the cache.
"""
from __future__ import annotations

import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path

import _toolkit_bootstrap

_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
flashsr = importlib.import_module(f"{_PACKAGE.__name__}.flashsr_audio")


class FakeCuda:
    def __init__(self, available=True, index=0, current_raises=False):
        self._available = available
        self._index = index
        self._raises = current_raises

    def is_available(self):
        return self._available

    def current_device(self):
        if self._raises:
            raise RuntimeError("no current device")
        return self._index


class FakeTorch:
    def __init__(self, **kwargs):
        self.cuda = FakeCuda(**kwargs)


class FakeModel:
    """Records ``.to()`` calls; can fail the first transfer on demand."""

    def __init__(self, fail_to=None):
        self.moves = []
        self._fail_to = fail_to

    def eval(self):
        self.evaluated = True
        return self

    def to(self, device):
        self.moves.append(device)
        if self._fail_to is not None and device == self._fail_to:
            self._fail_to = None
            raise RuntimeError(f"out of memory moving to {device}")
        return self


class RunnerHarness:
    def __init__(self, model=None, torch_module=None):
        self.model = model or FakeModel()
        self.torch = torch_module or FakeTorch()

    def __enter__(self):
        self._saved = {
            "_import_flashsr_model": flashsr._import_flashsr_model,
            "_runner_cache": dict(flashsr._runner_cache),
        }
        self.model_class = lambda *_args: self.model
        flashsr._import_flashsr_model = lambda: self.model_class
        flashsr._runner_cache.clear()
        self._real_torch = sys.modules.get("torch")
        sys.modules["torch"] = self.torch
        return self

    def __exit__(self, *exc):
        flashsr._import_flashsr_model = self._saved["_import_flashsr_model"]
        flashsr._runner_cache.clear()
        flashsr._runner_cache.update(self._saved["_runner_cache"])
        if self._real_torch is not None:
            sys.modules["torch"] = self._real_torch
        else:
            sys.modules.pop("torch", None)
        return False


def weights_dir(root: Path, create=True) -> Path:
    directory = root / "flashsr"
    directory.mkdir(parents=True, exist_ok=True)
    if create:
        for name in ("student_ldm.pth", "sr_vocoder.pth", "vae.pth"):
            (directory / name).write_bytes(b"x")
    return directory


class DeviceResolutionTests(unittest.TestCase):
    def test_cpu_when_cuda_is_unavailable(self):
        self.assertEqual(flashsr._resolve_execution_device(FakeTorch(available=False)), "cpu")

    def test_concrete_cuda_index(self):
        self.assertEqual(flashsr._resolve_execution_device(FakeTorch(index=2)), "cuda:2")

    def test_index_failure_defaults_to_zero(self):
        self.assertEqual(flashsr._resolve_execution_device(FakeTorch(current_raises=True)), "cuda:0")

    def test_broken_torch_reports_cpu(self):
        class Broken:
            @property
            def cuda(self):
                raise RuntimeError("no cuda attribute")

        self.assertEqual(flashsr._resolve_execution_device(Broken()), "cpu")


class RunnerConstructionTests(unittest.TestCase):
    def test_missing_weights_fail_before_the_model_is_built(self):
        built = []

        with RunnerHarness() as harness:
            harness.model_class = lambda *args: built.append(args) or harness.model
            flashsr._import_flashsr_model = lambda: harness.model_class
            with tempfile.TemporaryDirectory() as tmp:
                directory = weights_dir(Path(tmp), create=False)
                with self.assertRaises(RuntimeError) as ctx:
                    flashsr._get_runner(directory)
        self.assertIn("FlashSR weight missing", str(ctx.exception))
        self.assertEqual(built, [], "the model must not be constructed without its weights")

    def test_successful_runner_records_the_concrete_device(self):
        with RunnerHarness(torch_module=FakeTorch(index=1)) as harness:
            with tempfile.TemporaryDirectory() as tmp:
                directory = weights_dir(Path(tmp))
                runner = flashsr._get_runner(directory)
                self.assertIn(f"{directory}|cuda:1", flashsr._runner_cache)
        self.assertEqual(runner["device"], "cuda:1")
        self.assertEqual(harness.model.moves, ["cuda:1"])

    def test_failed_transfer_falls_back_to_cpu_and_reports_it(self):
        model = FakeModel(fail_to="cuda:0")
        with RunnerHarness(model=model) as harness:
            with tempfile.TemporaryDirectory() as tmp:
                directory = weights_dir(Path(tmp))
                runner = flashsr._get_runner(directory)
        self.assertEqual(runner["device"], "cpu", "the reported device must match reality")
        self.assertEqual(model.moves, ["cuda:0", "cpu"], "a partial move must be undone")

    def test_cache_is_reused_for_the_same_key(self):
        with RunnerHarness() as harness:
            with tempfile.TemporaryDirectory() as tmp:
                directory = weights_dir(Path(tmp))
                first = flashsr._get_runner(directory)
                second = flashsr._get_runner(directory)
                self.assertIs(first, second)
                self.assertEqual(len(flashsr._runner_cache), 1)

    def test_different_devices_get_separate_cache_entries(self):
        with RunnerHarness(torch_module=FakeTorch(index=0)) as harness:
            with tempfile.TemporaryDirectory() as tmp:
                directory = weights_dir(Path(tmp))
                first = flashsr._get_runner(directory)
                harness.torch.cuda._index = 1
                second = flashsr._get_runner(directory)
        self.assertIsNot(first, second)
        self.assertEqual({first["device"], second["device"]}, {"cuda:0", "cuda:1"})

    def test_clear_cache_releases_and_rebuilds(self):
        with RunnerHarness() as harness:
            with tempfile.TemporaryDirectory() as tmp:
                directory = weights_dir(Path(tmp))
                first = flashsr._get_runner(directory)
                released = flashsr.clear_flashsr_cache()
                second = flashsr._get_runner(directory)
                self.assertEqual(released, 1)
                self.assertIsNot(first, second)


class WeightPreparationTests(unittest.TestCase):
    def _stub_check(self, report):
        return lambda entries, base_path=None, auto_download=False: report

    def test_missing_weights_fail_with_downloads_disabled(self):
        saved = flashsr.check_file_entries
        flashsr.check_file_entries = self._stub_check([
            {"name": "student_ldm.pth", "status": "missing", "target": "x", "message": ""},
        ])
        try:
            with self.assertRaises(RuntimeError) as ctx:
                flashsr._ensure_flashsr_weights(auto_download=False)
            self.assertIn("auto-download disabled", str(ctx.exception))
            self.assertIn("student_ldm.pth", str(ctx.exception))
        finally:
            flashsr.check_file_entries = saved

    def test_ready_weights_return_the_target_directory(self):
        saved = flashsr.check_file_entries
        flashsr.check_file_entries = self._stub_check([
            {"name": "student_ldm.pth", "status": "present", "target": "x", "message": ""},
        ])
        try:
            result = flashsr._ensure_flashsr_weights(auto_download=True)
            self.assertTrue(str(result))
        finally:
            flashsr.check_file_entries = saved

    def test_failed_downloads_are_reported(self):
        saved = flashsr.check_file_entries
        flashsr.check_file_entries = self._stub_check([
            {"name": "vae.pth", "status": "failed", "target": "x", "message": "HTTP 404"},
        ])
        try:
            with self.assertRaises(RuntimeError) as ctx:
                flashsr._ensure_flashsr_weights(auto_download=True)
            self.assertIn("HTTP 404", str(ctx.exception))
        finally:
            flashsr.check_file_entries = saved


if __name__ == "__main__":
    unittest.main()
