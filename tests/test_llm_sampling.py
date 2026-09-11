"""Tests for family adapters, context planning and runtime options (L02).

What is pinned here:

* the family table (template + thinking capability) and its version;
* the context planner picks the smallest candidate that holds input + output +
  reserve, and reports an overflow instead of planning below the input;
* a runtime option is only accepted when the installed build declares it, and it
  changes the model cache identity - two runtime configurations are two models;
* token statistics come from the backend when it reports them, and a chunk count
  is never presented as an exact token count;
* the thinking toggle is reported as unsupported where the build cannot control
  it, instead of implying a speedup.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024 ** 3


def load_toolkit_modules():
    pkg_name = "_toolkit_llm_sampling_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in (
        "toolkit_logging",
        "comfy_resources",
        "model_downloader",
        "progress_utils",
        "resource_profiles",
        "llm_sampling",
        "llm_profiles",
        "llm_chat",
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
sampling = MODULES["llm_sampling"]
llm_chat = MODULES["llm_chat"]


class FamilyAdapterTests(unittest.TestCase):
    def test_detection_order_is_specific_first(self):
        cases = {
            "Qwen3.8-27B-UD-IQ3_XXS.gguf": "qwen3.8",
            "Qwen_Qwen3.5-9B-Q5_K_M.gguf": "qwen3.5",
            "some-qwen2-7b.gguf": "qwen",
            "gemma-4-12b-it-qat-q4_0.gguf": "gemma4",
            "Meta-Llama-3-8B-Instruct.gguf": "llama3",
            "mystery-model.gguf": "generic",
        }
        for name, expected in cases.items():
            with self.subTest(model=name):
                self.assertEqual(sampling.detect_family(name).id, expected)

    def test_gemma_uses_its_own_template_not_chatml(self):
        adapter = sampling.detect_family("gemma-4-12b-it-qat-q4_0.gguf")
        self.assertEqual(adapter.chat_format, "none")
        self.assertEqual(adapter.thinking, "unsupported")

    def test_qwen_families_use_chatml(self):
        for name in ("Qwen3.8-27B-UD-IQ3_XXS.gguf", "Qwen_Qwen3.5-9B-Q6_K.gguf"):
            with self.subTest(model=name):
                self.assertEqual(sampling.detect_family(name).chat_format, "chatml")

    def test_generic_adapter_always_matches(self):
        self.assertEqual(sampling.detect_family("").id, "generic")

    def test_adapter_report_is_versioned_and_complete(self):
        report = sampling.adapter_report("Qwen3.8-27B-UD-IQ3_XXS.gguf", lambda name: True)
        self.assertEqual(report["adapter_version"], sampling.ADAPTER_VERSION)
        self.assertEqual(report["family"], "qwen3.8")
        self.assertTrue(report["thinking"]["supported"])
        self.assertEqual(report["chat_format"], "chatml")


class ThinkingSupportTests(unittest.TestCase):
    def test_reasoning_budget_is_preferred_when_the_build_has_it(self):
        adapter = sampling.detect_family("Qwen3.8-27B-UD-IQ3_XXS.gguf")
        support = sampling.thinking_support(adapter, lambda name: name == "reasoning_budget")
        self.assertTrue(support["supported"])
        self.assertIn("reasoning_budget", support["mechanism"])

    def test_template_kwargs_are_accepted_as_the_other_mechanism(self):
        adapter = sampling.detect_family("some-qwen2-7b.gguf")
        support = sampling.thinking_support(adapter, lambda name: name == "chat_template_kwargs")
        self.assertTrue(support["supported"])
        self.assertEqual(support["mechanism"], "chat_template_kwargs")

    def test_unsupported_is_reported_and_not_sold_as_a_speedup(self):
        adapter = sampling.detect_family("gemma-4-12b-it-qat-q4_0.gguf")
        support = sampling.thinking_support(adapter, lambda name: False)
        self.assertFalse(support["supported"])
        self.assertIn("not a speedup", support["message"])
        text = "\n".join(sampling.format_adapter_lines(sampling.adapter_report("gemma-4-12b-it-qat-q4_0.gguf", lambda n: False)))
        self.assertIn("NOT supported", text)

    def test_non_thinking_sampling_only_for_the_family_that_documents_it(self):
        self.assertEqual(
            sampling.sampling_for("Qwen3.8-27B-UD-IQ3_XXS.gguf", "off"),
            {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "repeat_penalty": 1.0},
        )
        self.assertEqual(sampling.sampling_for("Qwen3.8-27B-UD-IQ3_XXS.gguf", "auto"), {})
        self.assertEqual(sampling.sampling_for("gemma-4-12b-it-qat-q4_0.gguf", "off"), {})


class ContextPlanningTests(unittest.TestCase):
    def test_small_prompt_uses_the_smallest_candidate(self):
        plan = sampling.plan_context(input_chars=2000, output_tokens=2048, reserve_tokens=512)
        self.assertTrue(plan["fits"])
        self.assertEqual(plan["context"], 4096)
        self.assertEqual(plan["method"], "estimate")

    def test_medium_prompt_grows_to_the_next_candidate(self):
        # 12000/3.5 = 3429 estimated input + 4096 output + 512 reserve = 8037 -> 8192
        plan = sampling.plan_context(input_chars=12000, output_tokens=4096, reserve_tokens=512)
        self.assertEqual(plan["context"], 8192)
        self.assertTrue(plan["fits"])

    def test_larger_prompt_grows_further(self):
        plan = sampling.plan_context(input_chars=20000, output_tokens=4096, reserve_tokens=512)
        self.assertEqual(plan["context"], 16384)
        self.assertTrue(plan["fits"])

    def test_boundary_exactly_on_a_candidate(self):
        needed = 8192
        chars = int((needed - 512 - 1024) * sampling.ESTIMATE_CHARS_PER_TOKEN)
        plan = sampling.plan_context(input_chars=chars, output_tokens=1024, reserve_tokens=512)
        self.assertEqual(plan["context"], 8192)

    def test_overflow_is_reported_and_never_truncates_the_input(self):
        plan = sampling.plan_context(input_chars=10_000_000, output_tokens=16384, reserve_tokens=512)
        self.assertFalse(plan["fits"])
        self.assertEqual(plan["context"], max(sampling.CONTEXT_CANDIDATES))
        self.assertGreater(plan["needed_tokens"], plan["context"])
        self.assertIn("never truncated silently", plan["reason"])

    def test_planned_context_always_holds_the_plan(self):
        for chars in (0, 500, 5000, 50000, 200000):
            with self.subTest(chars=chars):
                plan = sampling.plan_context(input_chars=chars, output_tokens=4096, reserve_tokens=512)
                if plan["fits"]:
                    self.assertGreaterEqual(plan["context"], plan["needed_tokens"])
                else:
                    # An overflow is reported with the largest candidate instead
                    # of planning a context that cannot hold the input.
                    self.assertEqual(plan["context"], max(sampling.CONTEXT_CANDIDATES))
                    self.assertIn("Shorten the prompt", plan["reason"])

    def test_empty_candidates_are_rejected(self):
        with self.assertRaises(ValueError):
            sampling.plan_context(1000, candidates=())


class RuntimeOptionTests(unittest.TestCase):
    def test_accepted_options_are_passed_through(self):
        result = sampling.build_runtime_options(
            {"n_ubatch": 256, "flash_attn": True, "type_k": "q8_0"},
            lambda name: True,
        )
        self.assertEqual(result["options"], {"n_ubatch": 256, "flash_attn": True, "type_k": "q8_0"})
        self.assertEqual(result["unsupported"], {})

    def test_a_build_without_the_parameter_reports_it_as_unsupported(self):
        result = sampling.build_runtime_options({"n_ubatch": 256}, lambda name: False)
        self.assertEqual(result["options"], {})
        self.assertIn("not supported", result["unsupported"]["n_ubatch"])

    def test_invalid_values_are_rejected_with_a_reason(self):
        cases = {
            "n_ubatch": 0,
            "n_batch": "512",
            "flash_attn": "yes",
            "type_k": "nope",
        }
        for name, value in cases.items():
            with self.subTest(option=name):
                result = sampling.build_runtime_options({name: value}, lambda _name: True)
                self.assertEqual(result["options"], {})
                self.assertIn(name, result["unsupported"])

    def test_unknown_option_names_are_rejected(self):
        result = sampling.build_runtime_options({"nonsense": 1}, lambda _name: True)
        self.assertIn("nonsense", result["unsupported"])

    def test_no_request_means_no_options(self):
        self.assertEqual(sampling.build_runtime_options(None, lambda name: True), {"options": {}, "unsupported": {}})
        self.assertEqual(sampling.build_runtime_options({}, lambda name: True), {"options": {}, "unsupported": {}})


class RuntimeOptionIntegrationTests(unittest.TestCase):
    """The runtime options must change the cache identity, and only there."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "model-a.gguf"
        self.path.write_bytes(b"A" * 1024)
        llm_chat._loaded_models.clear()
        self.instances = []

        recorder = self.instances

        class FakeLlama:
            def __init__(self, model_path=None, verbose=False, n_batch=512, n_ubatch=512, **options):
                self.model_path = model_path
                self.options = options
                self.n_batch = n_batch
                self.n_ubatch = n_ubatch
                self.closed = False
                recorder.append(self)

            def close(self):
                self.closed = True

        llm_chat._loaded_llama_cpp = types.SimpleNamespace(Llama=FakeLlama, __version__="test")
        original = llm_chat._find_model_path
        llm_chat._find_model_path = lambda name: self.path
        self.addCleanup(setattr, llm_chat, "_find_model_path", original)
        self.addCleanup(llm_chat._loaded_models.clear)

    def test_supported_runtime_option_reaches_the_model(self):
        llm_chat._get_model("model-a.gguf", False, runtime_options={"n_ubatch": 256})
        self.assertEqual(self.instances[-1].n_ubatch, 256)

    def test_unsupported_runtime_option_is_ignored_not_fatal(self):
        llm_chat._get_model("model-a.gguf", False, runtime_options={"type_k": "q8_0"})
        # FakeLlama does not declare type_k, so it must not be passed.
        self.assertNotIn("type_k", self.instances[-1].options)

    def test_two_runtime_configurations_are_two_cache_entries(self):
        llm_chat._get_model("model-a.gguf", False, runtime_options={"n_ubatch": 128})
        first = self.instances[-1]
        llm_chat._get_model("model-a.gguf", False, runtime_options={"n_ubatch": 256})
        self.assertEqual(len(self.instances), 2, "a different runtime configuration is a different model instance")
        self.assertTrue(first.closed)
        llm_chat._get_model("model-a.gguf", False, runtime_options={"n_ubatch": 256})
        self.assertEqual(len(self.instances), 2, "the same configuration is served from the cache")

    def test_catalog_runtime_options_are_read_without_a_widget(self):
        original = llm_chat.load_models_config
        llm_chat.load_models_config = lambda: {"llm": {"runtime_options": {"n_ubatch": 128}}}
        try:
            configured = llm_chat._configured_runtime_options()
        finally:
            llm_chat.load_models_config = original
        self.assertEqual(configured, {"n_ubatch": 128})

    def test_catalog_without_runtime_options_yields_nothing(self):
        original = llm_chat.load_models_config
        llm_chat.load_models_config = lambda: {"llm": {}}
        try:
            self.assertEqual(llm_chat._configured_runtime_options(), {})
        finally:
            llm_chat.load_models_config = original


class TokenStatisticsTests(unittest.TestCase):
    def test_backend_usage_is_used_when_present(self):
        usage = llm_chat._usage_from_response(
            {"usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}, chunks=5
        )
        self.assertEqual(usage["completion_tokens"], 20)
        self.assertEqual(usage["source"], "backend")
        self.assertEqual(usage["chunks"], 5)

    def test_a_chunk_count_is_never_sold_as_tokens(self):
        usage = llm_chat._usage_from_response({}, chunks=42)
        self.assertIsNone(usage["completion_tokens"])
        self.assertEqual(usage["source"], "chunks")
        self.assertEqual(usage["chunks"], 42)

    def test_unknown_stays_unknown(self):
        usage = llm_chat._usage_from_response(None)
        self.assertEqual(usage["source"], "unknown")
        self.assertIsNone(usage["completion_tokens"])

    def test_empty_answer_mentions_reasoning_when_there_was_only_reasoning(self):
        plain = llm_chat._empty_answer_message("")
        self.assertNotIn("reasoning", plain)
        explained = llm_chat._empty_answer_message("some private chain of thought")
        self.assertIn("reasoning", explained)
        self.assertIn("switch thinking off", explained)


class StreamingIntegrationTests(unittest.TestCase):
    class FakeBar:
        def update_absolute(self, value):
            pass

    class FakeStream:
        def __init__(self, chunks):
            self.chunks = chunks
            self.closed = False

        def __iter__(self):
            return iter(self.chunks)

        def close(self):
            self.closed = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        progress = MODULES["progress_utils"]
        original = progress.make_progress_bar
        progress.make_progress_bar = lambda total: self.FakeBar()
        self.addCleanup(setattr, progress, "make_progress_bar", original)

    def test_streaming_reports_a_usage_that_the_backend_provided(self):
        chunks = [
            {"choices": [{"delta": {"content": "hello "}}]},
            {"choices": [{"delta": {"content": "world"}}], "usage": {"completion_tokens": 2, "total_tokens": 7}},
        ]
        model = types.SimpleNamespace(
            create_chat_completion=lambda **kwargs: self.FakeStream(chunks),
        )
        text, thinking, usage = llm_chat._run_chat_streamed(model, {"messages": []}, 10)
        self.assertEqual(text, "hello world")
        self.assertEqual(usage["source"], "backend")
        self.assertEqual(usage["completion_tokens"], 2)

    def test_streaming_without_usage_reports_the_chunk_count(self):
        chunks = [{"choices": [{"delta": {"content": "x"}}]} for _ in range(3)]
        model = types.SimpleNamespace(create_chat_completion=lambda **kwargs: self.FakeStream(chunks))
        text, thinking, usage = llm_chat._run_chat_streamed(model, {"messages": []}, 10)
        self.assertEqual(usage["source"], "chunks")
        self.assertEqual(usage["chunks"], 3)
        self.assertIsNone(usage["completion_tokens"])


if __name__ == "__main__":
    unittest.main()
