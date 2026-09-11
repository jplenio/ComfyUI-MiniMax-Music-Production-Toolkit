"""ComfyUI host-cleanup tests (F10 / T19).

The move must not change *what* happens or *in which order*.  Ordering is the
contract that makes the dynamic-VRAM workarounds work: the prefetch graphs
reference the staged pages, the cast buffers must be reset while the models are
still loaded, and only ``partially_unload()`` reaches ``vbar.free_memory()``.
"""
from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path

import _toolkit_bootstrap

_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
resources = importlib.import_module(f"{_PACKAGE.__name__}.comfy_resources")
llm_chat = importlib.import_module(f"{_PACKAGE.__name__}.llm_chat")


class RecordingModelManagement:
    def __init__(self, calls, dynamic=True):
        self.calls = calls
        self.current_loaded_models = [types.SimpleNamespace(model=RecordingModel(calls, dynamic))]

    def cleanup_prefetch_queues(self):  # pragma: no cover - ComfyUI capability probe
        pass

    def reset_cast_buffers(self):
        self.calls.append("reset_cast_buffers")

    def unload_all_models(self):
        self.calls.append("unload_all_models")

    def soft_empty_cache(self, force=False):
        self.calls.append(f"soft_empty_cache(force={force})")


class RecordingModel:
    def __init__(self, calls, dynamic):
        self.calls = calls
        self.model = self
        self.offload_device = "cpu"
        self._dynamic = dynamic

    def is_dynamic(self):
        return self._dynamic

    def loaded_size(self):
        return 2**30

    def partially_unload(self, device, size):
        self.calls.append("partially_unload")
        return 2**30


def _fake_host(calls, dynamic=True):
    """Install a minimal fake ``comfy`` package and remove it again on exit."""
    modules = {}

    def install():
        comfy = types.ModuleType("comfy")
        management = RecordingModelManagement(calls, dynamic)
        management.cleanup_prefetch_queues = lambda: calls.append("cleanup_prefetch_queues")
        comfy.model_management = management
        prefetch = types.ModuleType("comfy.model_prefetch")
        prefetch.cleanup_prefetch_queues = lambda: calls.append("cleanup_prefetch_queues")
        model_management = types.ModuleType("comfy.model_management")
        model_management.current_loaded_models = management.current_loaded_models
        model_management.cleanup_prefetch_queues = prefetch.cleanup_prefetch_queues
        model_management.reset_cast_buffers = management.reset_cast_buffers
        model_management.unload_all_models = management.unload_all_models
        model_management.soft_empty_cache = management.soft_empty_cache
        modules.update({
            "comfy": comfy,
            "comfy.model_prefetch": prefetch,
            "comfy.model_management": model_management,
        })
        for name, module in modules.items():
            sys.modules[name] = module

    def remove():
        for name in modules:
            sys.modules.pop(name, None)

    return install, remove


class OrderingTests(unittest.TestCase):
    def test_cleanup_runs_in_the_contract_order(self):
        calls: list[str] = []
        install, remove = _fake_host(calls)
        install()
        self.addCleanup(remove)

        resources.free_comfyui_model_cache()

        self.assertIn("cleanup_prefetch_queues", calls)
        self.assertIn("reset_cast_buffers", calls)
        self.assertIn("unload_all_models", calls)
        self.assertIn("partially_unload", calls)
        self.assertIn("soft_empty_cache(force=True)", calls)
        self.assertLess(calls.index("cleanup_prefetch_queues"), calls.index("reset_cast_buffers"))
        self.assertLess(
            calls.index("reset_cast_buffers"), calls.index("unload_all_models"),
            "cast buffers must be reset while the dynamic models are still loaded",
        )
        self.assertLess(
            calls.index("unload_all_models"), calls.index("partially_unload"),
            "staging is released after the models are detached",
        )
        self.assertLess(calls.index("partially_unload"), calls.index("soft_empty_cache(force=True)"))

    def test_partially_unload_failure_is_guarded(self):
        calls: list[str] = []
        install, remove = _fake_host(calls)
        install()
        self.addCleanup(remove)
        sys.modules["comfy.model_management"].current_loaded_models[0].model.partially_unload = (
            lambda device, size: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        resources.free_comfyui_model_cache()  # must not raise
        self.assertIn("soft_empty_cache(force=True)", calls)

    def test_non_dynamic_models_are_not_partially_unloaded(self):
        calls: list[str] = []
        install, remove = _fake_host(calls, dynamic=False)
        install()
        self.addCleanup(remove)
        resources.free_comfyui_model_cache()
        self.assertIn("unload_all_models", calls)
        self.assertNotIn("partially_unload", calls)


class DegradedHostTests(unittest.TestCase):
    def test_no_comfy_model_management_is_a_no_op(self):
        saved = {name: sys.modules.get(name) for name in list(sys.modules) if name == "comfy" or name.startswith("comfy.")}
        for name in saved:
            sys.modules.pop(name, None)
        try:
            self.assertIsNone(resources.free_comfyui_model_cache())
        finally:
            for name, module in saved.items():
                if module is not None:
                    sys.modules[name] = module

    def test_missing_optional_capabilities_are_tolerated(self):
        calls: list[str] = []
        install, remove = _fake_host(calls)
        install()
        self.addCleanup(remove)
        # ``import comfy.model_management as m`` binds the host object; shadow the
        # optional capabilities on it so the guarded getattr path is exercised.
        host = sys.modules["comfy"].model_management
        host.reset_cast_buffers = None
        host.soft_empty_cache = None
        sys.modules.pop("comfy.model_prefetch", None)
        resources.free_comfyui_model_cache()
        self.assertIn("unload_all_models", calls)
        self.assertNotIn("reset_cast_buffers", calls)
        self.assertNotIn("soft_empty_cache(force=True)", calls)


class WrapperTests(unittest.TestCase):
    def test_llm_chat_wrapper_still_works(self):
        calls: list[str] = []
        install, remove = _fake_host(calls)
        install()
        self.addCleanup(remove)
        llm_chat._free_comfyui_model_cache()
        self.assertIn("unload_all_models", calls)

    def test_extracted_function_is_the_real_implementation(self):
        resources_source = Path(resources.__file__).read_text(encoding="utf-8")
        llm_chat_source = Path(llm_chat.__file__).read_text(encoding="utf-8")
        self.assertIn("def free_comfyui_model_cache()", resources_source)
        self.assertIn(
            'type(obj).__name__ == "ModelVBAR"', resources_source,
            "the guarded GC fallback must survive the move",
        )
        self.assertNotIn("def free_comfyui_model_cache", llm_chat_source)
        self.assertIn("def _free_comfyui_model_cache()", llm_chat_source)


if __name__ == "__main__":
    unittest.main()
