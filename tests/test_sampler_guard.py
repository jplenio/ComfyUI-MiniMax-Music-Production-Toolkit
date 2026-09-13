"""Guard behavior of the MiniMax sampler node and the runtime-safety policy.

Two failures are covered with mechanism, not prose:

* A non-finite sampler result must stop immediately. The noise follows the seed
  and the conditioning/weights are unchanged, so repeating the identical
  sampling reproduces the same latents and only doubles the longest stage of the
  prompt (observed: two identical 8m48s runs before the error). Only a
  backend/capture ``RuntimeError`` is worth one retry after clearing the
  captured state.
* ``MINIMAX_MUSIC3_RUNTIME_SAFETY=auto`` must keep its own policy value. Folding
  it into ``off`` made the risky-backend branch unreachable, so the documented
  automatic mode silently did nothing.
"""
from __future__ import annotations

import importlib.util
import itertools
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import torch

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "_sampler_guard_test"
_INSTANCES = itertools.count()


def load_package():
    """Load toolkit_logging/runtime_safety/ksampler_config as one package."""
    name = f"{PACKAGE_NAME}_{next(_INSTANCES)}"
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT)]
    sys.modules[name] = package
    modules = {}
    for module_name in ("toolkit_logging", "runtime_safety", "ksampler_config"):
        spec = importlib.util.spec_from_file_location(f"{name}.{module_name}", ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{name}.{module_name}"] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)
        setattr(package, module_name, module)
        modules[module_name] = module
    return modules


def fake_host_modules(*, capability=(12, 0), device_type="cuda", hip=False, available=True):
    """Minimal ``torch``/``comfy`` stand-ins for ``_runtime_info``/``_set_safe_flags``."""
    args = types.SimpleNamespace(disable_cuda_graphs=False, disable_comfy_compiler=False)

    class _Cuda:
        @staticmethod
        def is_available():
            return available

        @staticmethod
        def get_device_capability(device):
            return capability

    torch_stub = types.ModuleType("torch")
    torch_stub.cuda = _Cuda()
    torch_stub.version = types.SimpleNamespace(hip="7.1" if hip else None)

    model_management = types.ModuleType("comfy.model_management")
    model_management.get_torch_device = lambda: types.SimpleNamespace(type=device_type)

    cli_args = types.ModuleType("comfy.cli_args")
    cli_args.args = args

    comfy = types.ModuleType("comfy")
    comfy.model_management = model_management
    comfy.cli_args = cli_args

    return {
        "torch": torch_stub,
        "comfy": comfy,
        "comfy.model_management": model_management,
        "comfy.cli_args": cli_args,
    }, args


class RuntimeSafetyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.modules = load_package()
        self.runtime_safety = self.modules["runtime_safety"]

    def test_auto_keeps_its_own_policy(self):
        with mock.patch.dict("os.environ", {"MINIMAX_MUSIC3_RUNTIME_SAFETY": "auto"}):
            self.assertEqual(self.runtime_safety._policy(), "auto")

    def test_policy_aliases_and_default(self):
        cases = {
            "off": "off",
            "0": "off",
            "false": "off",
            "no": "off",
            " AUTO ": "auto",
            "detect": "auto",
            "on": "on",
            "1": "on",
            "true": "on",
            "yes": "on",
            "force": "on",
            "strict": "strict",
            "2": "strict",
            "nonsense": "off",
        }
        for value, expected in cases.items():
            with self.subTest(value=value), mock.patch.dict(
                "os.environ", {"MINIMAX_MUSIC3_RUNTIME_SAFETY": value}
            ):
                self.assertEqual(self.runtime_safety._policy(), expected)

    def test_default_policy_is_inert_without_touching_the_backend(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            report = self.runtime_safety.configure_runtime()
        self.assertEqual(report, {"policy": "off", "enabled": False, "reason": "disabled"})

    def test_auto_enables_only_on_a_risky_backend(self):
        for capability, expected_enabled in (((12, 0), True), ((8, 9), False)):
            with self.subTest(capability=capability):
                host, args = fake_host_modules(capability=capability)
                with mock.patch.dict("os.environ", {"MINIMAX_MUSIC3_RUNTIME_SAFETY": "auto"}), mock.patch.dict(
                    sys.modules, host
                ):
                    report = self.runtime_safety.configure_runtime()
                self.assertEqual(report["policy"], "auto")
                self.assertEqual(report["enabled"], expected_enabled)
                self.assertEqual(report["risky"], expected_enabled)
                self.assertEqual(args.disable_cuda_graphs, expected_enabled)

    def test_auto_enables_on_rocm_and_reports_the_kind(self):
        host, args = fake_host_modules(capability=None, hip=True)
        with mock.patch.dict("os.environ", {"MINIMAX_MUSIC3_RUNTIME_SAFETY": "auto"}), mock.patch.dict(
            sys.modules, host
        ):
            report = self.runtime_safety.configure_runtime()
        self.assertTrue(report["enabled"])
        self.assertEqual(report["kind"], "rocm")
        self.assertTrue(args.disable_cuda_graphs)

    def test_forced_policy_enables_on_a_safe_backend_and_strict_disables_the_compiler(self):
        for value, capacity in (("on", (8, 9)), ("strict", (8, 9))):
            with self.subTest(value=value):
                host, args = fake_host_modules(capability=capacity)
                with mock.patch.dict("os.environ", {"MINIMAX_MUSIC3_RUNTIME_SAFETY": value}), mock.patch.dict(
                    sys.modules, host
                ):
                    report = self.runtime_safety.configure_runtime()
                self.assertTrue(report["enabled"])
                self.assertTrue(args.disable_cuda_graphs)
                self.assertEqual(args.disable_comfy_compiler, value == "strict")

    def test_auto_stays_disabled_without_a_cuda_device(self):
        host, args = fake_host_modules(device_type="cpu")
        with mock.patch.dict("os.environ", {"MINIMAX_MUSIC3_RUNTIME_SAFETY": "auto"}), mock.patch.dict(
            sys.modules, host
        ):
            report = self.runtime_safety.configure_runtime()
        self.assertEqual(report["enabled"], False)
        self.assertEqual(report["reason"], "backend-not-marked-risky")
        self.assertFalse(args.disable_cuda_graphs)


class _FakeNodes:
    """Stand-in for ComfyUI's ``nodes`` module with recorded calls."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def common_ksampler(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        result = self.results[min(len(self.calls) - 1, len(self.results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result


def latent(value):
    return {"samples": torch.full((1, 128, 8), value)}


class KSamplerWithConfigTests(unittest.TestCase):
    def setUp(self):
        self.modules = load_package()
        self.ksampler = self.modules["ksampler_config"]
        self.runtime_safety = self.modules["runtime_safety"]

    def run_sample(self, nodes, **overrides):
        kwargs = dict(
            model=object(),
            positive=[("cond", {})],
            negative=[("neg", {})],
            latent_image=latent(1.0),
            seed=7,
            steps=40,
            cfg=1.7,
            sampler_name="euler",
            scheduler="simple",
            denoise=1.0,
        )
        kwargs.update(overrides)
        sampler = self.ksampler.KSamplerWithConfig()
        with mock.patch.dict(sys.modules, {"nodes": nodes}):
            return sampler.sample(**kwargs)

    def test_finite_latent_passes_through_unchanged(self):
        nodes = _FakeNodes([(latent(0.25),)])
        result = self.run_sample(nodes)
        self.assertEqual(len(nodes.calls), 1)
        self.assertEqual(result[1], "euler")
        self.assertEqual(result[2], "simple")
        self.assertTrue(torch.isfinite(result[0]["samples"]).all())

    def test_non_finite_latent_fails_immediately_without_repeating_the_sampling(self):
        nodes = _FakeNodes([(latent(float("nan")),)])
        prepare = mock.Mock()
        with mock.patch.object(self.runtime_safety, "prepare_sampler_retry", prepare):
            with self.assertRaises(ValueError) as ctx:
                self.run_sample(nodes)
        self.assertEqual(len(nodes.calls), 1, "an identical second pass cannot change a non-finite result")
        prepare.assert_not_called()
        message = str(ctx.exception)
        self.assertIn("--fp32-unet", message)
        self.assertIn("does not retry", message)
        self.assertIn("no invalid audio was passed", message)

    def test_infinity_is_detected_too(self):
        nodes = _FakeNodes([(latent(float("inf")),)])
        with self.assertRaises(ValueError):
            self.run_sample(nodes)
        self.assertEqual(len(nodes.calls), 1)

    def test_non_finite_result_after_a_capture_error_also_stops(self):
        error = RuntimeError("CUDA graph capture failed")
        nodes = _FakeNodes([error, (latent(float("nan")),)])
        with mock.patch.object(self.runtime_safety, "prepare_sampler_retry", mock.Mock(return_value={})), mock.patch.object(
            self.runtime_safety, "restore_sampler_retry_state"
        ) as restore:
            with self.assertRaises(ValueError):
                self.run_sample(nodes)
        self.assertEqual(len(nodes.calls), 2)
        restore.assert_called_once()

    def test_capture_error_is_retried_once_after_clearing_captured_state(self):
        error = RuntimeError("cudaErrorStreamCaptureInvalidated")
        nodes = _FakeNodes([error, (latent(0.5),)])
        prepare = mock.Mock(return_value={"disable_cuda_graphs": False})
        restore = mock.Mock()
        with mock.patch.object(self.runtime_safety, "prepare_sampler_retry", prepare), mock.patch.object(
            self.runtime_safety, "restore_sampler_retry_state", restore
        ):
            result = self.run_sample(nodes)
        self.assertEqual(len(nodes.calls), 2)
        prepare.assert_called_once()
        restore.assert_called_once_with({"disable_cuda_graphs": False})
        self.assertTrue(torch.isfinite(result[0]["samples"]).all())

    def test_unrelated_runtime_error_is_not_retried(self):
        nodes = _FakeNodes([RuntimeError("model has no attribute foo")])
        with self.assertRaises(RuntimeError):
            self.run_sample(nodes)
        self.assertEqual(len(nodes.calls), 1)

    def test_unknown_latent_wrapper_is_not_mistaken_for_invalid_audio(self):
        nodes = _FakeNodes([(object(),)])
        result = self.run_sample(nodes)
        self.assertEqual(len(nodes.calls), 1)
        self.assertIsInstance(result[0], object)


if __name__ == "__main__":
    unittest.main()
