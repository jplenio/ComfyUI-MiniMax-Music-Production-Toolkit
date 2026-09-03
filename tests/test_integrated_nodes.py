from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_toolkit_modules():
    pkg_name = "_toolkit_integrated_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in ("toolkit_logging", "model_downloader", "flashsr_audio", "llm_chat"):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


MODULES = load_toolkit_modules()
flashsr = MODULES["flashsr_audio"]
llm_chat = MODULES["llm_chat"]


class FlashSRHelpersTests(unittest.TestCase):
    def test_channel_samples_normalization_from_tuple(self):
        stereo = np.random.default_rng(0).standard_normal((2, 1000)).astype(np.float32)
        cs, sr = flashsr._to_channel_samples((stereo, 44100))
        self.assertEqual(cs.shape, (2, 1000))
        self.assertEqual(sr, 44100)

    def test_channel_samples_frames_first_transposed(self):
        frames_first = np.random.default_rng(0).standard_normal((1000, 2)).astype(np.float32)
        cs, _sr = flashsr._to_channel_samples((frames_first, 44100))
        self.assertEqual(cs.shape, (2, 1000))

    def test_invalid_audio_raises(self):
        with self.assertRaises(RuntimeError):
            flashsr._to_channel_samples(None)

    def test_chunk_iteration_covers_everything_with_overlap(self):
        spans = flashsr._iter_chunks(1000, window=300, hop=200)
        self.assertEqual(spans[0], (0, 300))
        self.assertEqual(spans[-1][1], 1000 - spans[-1][0])
        covered = [start + length for start, length in spans]
        self.assertEqual(max(covered), 1000)

    def test_wola_stitch_identity(self):
        # Overlap-add of identical content reconstructs the input exactly, except
        # for the very first sample where the Hann window starts at zero (the same
        # boundary behavior as the external FlashSR node this replaces).
        rng = np.random.default_rng(1)
        x = rng.standard_normal((2, 1000)).astype(np.float32)
        window = 300
        hop = window // 2  # 50% overlap: Hann OLA sums to exactly 1
        predictions = []
        for start, length in flashsr._iter_chunks(1000, window, hop):
            chunk = x[:, start:start + length]
            if length < window:
                chunk = np.concatenate([chunk, np.zeros((2, window - length), np.float32)], axis=1)
            predictions.append((chunk, start, length))
        out = flashsr._wola_stitch(predictions, total_len=1000, window=window)
        np.testing.assert_allclose(out[:, 1:], x[:, 1:], atol=1e-6)

    def test_resample_same_rate_is_identity(self):
        x = np.random.default_rng(2).standard_normal((1, 500)).astype(np.float32)
        out = flashsr._resample_hq(x, 48000, 48000)
        np.testing.assert_array_equal(out, x)

    def test_resample_length_scales(self):
        x = np.random.default_rng(3).standard_normal((1, 4800)).astype(np.float32)
        out = flashsr._resample_hq(x, 48000, 24000)
        self.assertAlmostEqual(out.shape[1], 2400, delta=2)

    def test_input_types_contract(self):
        data = flashsr.MiniMaxFlashSRAudio.INPUT_TYPES()
        self.assertEqual(data["required"]["output_sr"][0], ["48000", "44100", "96000"])
        self.assertEqual(data["required"]["lowpass_input"][1]["default"], False)


class LLMChatTests(unittest.TestCase):
    def test_model_listing_and_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.gguf").write_bytes(b"x")
            (root / "notes.txt").write_text("ignored")
            original = llm_chat._llm_directories
            llm_chat._llm_directories = lambda: [root]
            try:
                self.assertEqual(llm_chat.list_llm_models(), ["a.gguf"])
                self.assertEqual(llm_chat._find_model_path("a.gguf"), root / "a.gguf")
                self.assertIsNone(llm_chat._find_model_path("missing.gguf"))
            finally:
                llm_chat._llm_directories = original

    def test_llm_directories_follow_models_directory_env(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            models_root = Path(tmp) / "G-ComfyUI" / "models"
            previous = os.environ.get("COMFYUI_MODELS_DIRECTORY")
            previous_base = os.environ.get("COMFYUI_BASE_PATH")
            os.environ["COMFYUI_MODELS_DIRECTORY"] = str(models_root)
            os.environ.pop("COMFYUI_BASE_PATH", None)
            try:
                directories = llm_chat._llm_directories()
                self.assertIn(models_root / "llm", directories)
            finally:
                if previous is None:
                    os.environ.pop("COMFYUI_MODELS_DIRECTORY", None)
                else:
                    os.environ["COMFYUI_MODELS_DIRECTORY"] = previous
                if previous_base is not None:
                    os.environ["COMFYUI_BASE_PATH"] = previous_base

    def test_llm_directories_fallback_chain(self):
        import os
        previous = os.environ.get("COMFYUI_MODELS_DIRECTORY")
        previous_base = os.environ.get("COMFYUI_BASE_PATH")
        os.environ.pop("COMFYUI_MODELS_DIRECTORY", None)
        os.environ.pop("COMFYUI_BASE_PATH", None)
        try:
            directories = llm_chat._llm_directories()
            self.assertTrue(directories)
            self.assertTrue(all(d.name == "llm" for d in directories))
        finally:
            if previous is not None:
                os.environ["COMFYUI_MODELS_DIRECTORY"] = previous
            if previous_base is not None:
                os.environ["COMFYUI_BASE_PATH"] = previous_base

    def test_chat_rejects_empty_user_text(self):
        node = llm_chat.MiniMaxLLMChat()
        with self.assertRaises(ValueError):
            node.chat(True, "", "system", "session", "any.gguf", 16, 0.7, 0.8, -1, 512, True, False)

    def test_chat_disabled_returns_empty_text_without_backend(self):
        node = llm_chat.MiniMaxLLMChat()
        text, status, thinking = node.chat(False, "", "system", "session", "any.gguf", 16, 0.7, 0.8, -1, 512, True, False)
        self.assertEqual(text, "")
        self.assertEqual(thinking, "")
        self.assertIn("disabled", status)

    def test_chat_explains_missing_llama_cpp(self):
        node = llm_chat.MiniMaxLLMChat()
        saved = llm_chat._loaded_llama_cpp
        llm_chat._loaded_llama_cpp = None
        try:
            with self.assertRaises(RuntimeError) as ctx:
                node.chat(True, "user", "system", "session", "missing.gguf", 16, 0.7, 0.8, -1, 512, True, False)
            self.assertIn("llama-cpp-python", str(ctx.exception))
        finally:
            llm_chat._loaded_llama_cpp = saved

    def test_chat_with_fake_llama_backend(self):
        # Exercise the full chat path (load, completion, status) without real weights.
        class FakeLlama:
            closed = False
            state = None

            def __init__(self, model_path, **kwargs):
                self.model_path = model_path
                self.kwargs = kwargs

            def create_chat_completion(self, messages, **kwargs):
                content = "|".join(m["role"] + ":" + m["content"] for m in messages)
                return {"choices": [{"message": {"content": content + " REPLY"}}]}

            def save_state(self):
                return b"state-bytes"

            def set_state(self, state):
                FakeLlama.state = state

            def close(self):
                FakeLlama.closed = True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tiny.gguf").write_bytes(b"fake")

            saved_modules = (llm_chat._loaded_llama_cpp, llm_chat._loaded_models, llm_chat._llm_directories)
            llm_chat._loaded_llama_cpp = types.SimpleNamespace(Llama=FakeLlama)
            llm_chat._loaded_models = {}
            llm_chat._llm_directories = lambda: [root]
            try:
                node = llm_chat.MiniMaxLLMChat()
                text, status, thinking = node.chat(
                    True, "user text", "system text", "sess-1", "tiny.gguf",
                    16, 0.7, 0.8, -1, 512, False, False,
                )
                self.assertIn("system text", text)
                self.assertIn("user:user text", text)
                self.assertIn("REPLY", text)
                self.assertIn("sess-1", status)
                self.assertEqual(thinking, "")
                # Second turn with session state kept: set_state receives saved bytes.
                _text2, _status2, _thinking2 = node.chat(
                    True, "second", "system text", "sess-1", "tiny.gguf",
                    16, 0.7, 0.8, -1, 512, False, False,
                )
                self.assertEqual(FakeLlama.state, b"state-bytes")
            finally:
                llm_chat._loaded_llama_cpp, llm_chat._loaded_models, llm_chat._llm_directories = saved_modules

    def test_run_chat_omits_cache_prompt_when_unsupported(self):
        # llama-cpp-python 0.3.48 (and others) has no cache_prompt kwarg; the
        # call must succeed without it.  The explicit signature below rejects
        # unknown kwargs, so a regression would raise TypeError.
        class StrictFakeLlama:
            def __init__(self):
                self.received = None

            def create_chat_completion(self, messages, max_tokens, temperature, top_p):
                self.received = (messages, max_tokens, temperature, top_p)
                return {"choices": [{"message": {"content": "strict reply"}}]}

        model = StrictFakeLlama()
        text, thinking = llm_chat._run_chat(model, "sys", "user", 16, 0.7, 0.8)
        self.assertEqual(text, "strict reply")
        self.assertEqual(thinking, "")
        messages, max_tokens, temperature, top_p = model.received
        self.assertEqual(messages[0]["content"], "sys")
        self.assertEqual(max_tokens, 16)

    def test_run_chat_passes_cache_prompt_when_supported(self):
        class CacheFakeLlama:
            def __init__(self):
                self.received = None

            def create_chat_completion(self, messages, max_tokens, temperature, top_p, cache_prompt=True):
                self.received = cache_prompt
                return {"choices": [{"message": {"content": "cached reply"}}]}

        model = CacheFakeLlama()
        text, thinking = llm_chat._run_chat(model, "sys", "user", 16, 0.7, 0.8)
        self.assertEqual(text, "cached reply")
        self.assertEqual(thinking, "")
        self.assertIs(model.received, True)

    def test_split_thinking_tags(self):
        clean, thinking = llm_chat._split_thinking_tags(
            "<think>\nThe user wants one word.\n</think>\n\nOK"
        )
        self.assertEqual(clean, "OK")
        self.assertIn("one word", thinking)

        # Missing opening tag: everything before </think> is thinking.
        clean2, thinking2 = llm_chat._split_thinking_tags(
            "Just answer with OK.\n</think>\n\nOK"
        )
        self.assertEqual(clean2, "OK")
        self.assertIn("Just answer", thinking2)

        # No tags: content unchanged, no thinking.
        clean3, thinking3 = llm_chat._split_thinking_tags("plain reply")
        self.assertEqual(clean3, "plain reply")
        self.assertEqual(thinking3, "")

        # Malformed opener that never closes: everything up to the first
        # section header is thinking.
        clean4, thinking4 = llm_chat._split_thinking_tags(
            "<think>/\nLet me plan this track carefully.\n\n[Caption]\ncap"
        )
        self.assertEqual(clean4, "[Caption]\ncap")
        self.assertIn("Let me plan", thinking4)

        # Gemma channel markers before the first section are stripped too.
        clean5, thinking5 = llm_chat._split_thinking_tags(
            "<|channel>thought\n<|channel|>[Caption]\ncap"
        )
        self.assertEqual(clean5, "[Caption]\ncap")
        self.assertIn("channel", thinking5)

    def test_run_chat_separates_reasoning_from_answer(self):
        class ThinkingFakeLlama:
            def create_chat_completion(self, messages, max_tokens, temperature, top_p, **kwargs):
                return {"choices": [{"message": {
                    "reasoning_content": "internal reasoning",
                    "content": "<think>\nmore thinking\n</think>\n\n[Caption]\ncap",
                }}]}

        model = ThinkingFakeLlama()
        text, thinking = llm_chat._run_chat(model, "sys", "user", 16, 0.7, 0.8)
        self.assertEqual(text, "[Caption]\ncap")
        self.assertIn("internal reasoning", thinking)
        self.assertIn("more thinking", thinking)
        self.assertNotIn("<think>", text)

    def test_accepts_cache_prompt_detection(self):
        class NoCache:
            def create_chat_completion(self, messages, max_tokens):
                pass

        class WithCache:
            def create_chat_completion(self, messages, max_tokens, cache_prompt=True):
                pass

        class NoMethod:
            pass

        self.assertFalse(llm_chat._accepts_cache_prompt(NoCache()))
        self.assertTrue(llm_chat._accepts_cache_prompt(WithCache()))
        self.assertFalse(llm_chat._accepts_cache_prompt(NoMethod()))

    def test_tensor_split_never_fails_the_run(self):
        # Regression: a "0" or other non-positive split hint must fall back
        # to auto distribution instead of raising.
        self.assertIsNone(llm_chat._parse_tensor_split("", 2))
        self.assertIsNone(llm_chat._parse_tensor_split("0", 2))
        self.assertIsNone(llm_chat._parse_tensor_split("0,0", 2))
        self.assertIsNone(llm_chat._parse_tensor_split("abc", 2))
        self.assertEqual(llm_chat._parse_tensor_split("1,0", 2), [1.0])
        self.assertEqual(llm_chat._parse_tensor_split("2,3", 2), [0.4, 0.6])
        self.assertEqual(llm_chat._parse_tensor_split("0.5", 2), [1.0])
        self.assertEqual(llm_chat._parse_tensor_split("even", 2), [0.5, 0.5])
        self.assertIsNone(llm_chat._parse_tensor_split("even", 1))

    def test_unload_releases_cached_models(self):
        class FakeModel:
            def close(self):
                pass

        saved = llm_chat._loaded_models
        llm_chat._loaded_models = {"a": FakeModel(), "b": FakeModel()}
        try:
            count = llm_chat.unload_llm_models()
            self.assertEqual(count, 2)
            self.assertEqual(llm_chat._loaded_models, {})
        finally:
            llm_chat._loaded_models = saved

    def test_free_comfyui_cache_is_safe_outside_comfyui(self):
        # Outside ComfyUI the helper must be a silent no-op (import of
        # comfy.model_management fails and is caught).
        try:
            llm_chat._free_comfyui_model_cache()
        except Exception as exc:  # pragma: no cover
            self.fail(f"_free_comfyui_model_cache raised outside ComfyUI: {exc}")

    def test_free_comfyui_cache_releases_dynamic_staging(self):
        # On dynamic-VRAM builds the staged weight pages must be released via
        # partially_unload() because unload_all_models() alone keeps them
        # resident in the VBAR.
        import sys

        class FakeModule:
            pass

        class FakeDynamicModel:
            def __init__(self):
                self.model = FakeModule()
                self.offload_device = "cpu"
                self.released = []

            def is_dynamic(self):
                return True

            def partially_unload(self, device_to, memory_to_free):
                self.released.append((device_to, memory_to_free))
                return 3 * (2**30)

        class FakeLoadedEntry:
            def __init__(self, model):
                self.model = model

        dynamic = FakeDynamicModel()
        state = {"unloaded": False, "soft_emptied": False, "cast_reset": False, "prefetch_cleaned": False}
        model_management = types.SimpleNamespace(
            current_loaded_models=[FakeLoadedEntry(dynamic)],
            reset_cast_buffers=lambda: state.__setitem__("cast_reset", True),
            unload_all_models=lambda: state.__setitem__("unloaded", True),
            soft_empty_cache=lambda force=False: state.__setitem__("soft_emptied", True),
        )
        model_prefetch = types.SimpleNamespace(
            cleanup_prefetch_queues=lambda: state.__setitem__("prefetch_cleaned", True)
        )
        fake_comfy = types.ModuleType("comfy")
        fake_comfy.__path__ = []
        fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(empty_cache=lambda: None))

        saved = {name: sys.modules.get(name) for name in ("comfy", "comfy.model_management", "comfy.model_prefetch", "torch")}
        sys.modules["comfy"] = fake_comfy
        sys.modules["comfy.model_management"] = model_management
        sys.modules["comfy.model_prefetch"] = model_prefetch
        if "torch" not in sys.modules:
            sys.modules["torch"] = fake_torch
        try:
            llm_chat._free_comfyui_model_cache()
            self.assertTrue(state["prefetch_cleaned"])
            self.assertTrue(state["cast_reset"])
            self.assertTrue(state["unloaded"])
            self.assertEqual(dynamic.released, [("cpu", 1e32)])
        finally:
            for name, value in saved.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value

    def test_pick_llm_main_gpu_routing(self):
        import sys

        class FakeCuda:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def current_device():
                return 0

            @staticmethod
            def mem_get_info(index):
                # GPU 0 busy (2 GiB free), GPU 1 free (12 GiB free).
                return {0: (2 << 30, 16 << 30), 1: (12 << 30, 16 << 30)}[index]

        fake_torch = types.SimpleNamespace(cuda=FakeCuda)
        saved_torch = sys.modules.get("torch")
        sys.modules["torch"] = fake_torch
        try:
            model_path = Path("missing.gguf")  # stat() fails -> size unknown
            # Default config with 2 GPUs -> the freest non-default GPU (1).
            self.assertEqual(llm_chat._pick_llm_main_gpu(0, model_path, 32768, 2, 0, None), 1)
            # Single GPU -> 0.
            self.assertEqual(llm_chat._pick_llm_main_gpu(0, model_path, 32768, 1, 0, None), 0)
            # Explicit user choice wins.
            self.assertEqual(llm_chat._pick_llm_main_gpu(0, model_path, 32768, 2, 1, [0.5, 0.5]), 0)
            self.assertEqual(llm_chat._pick_llm_main_gpu(1, model_path, 32768, 2, 0, None), 1)
        finally:
            if saved_torch is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = saved_torch

    def test_unload_node_passthrough(self):
        node = llm_chat.MiniMaxLLMUnload()
        trigger, released = node.unload("marker", True, False)
        self.assertEqual(trigger, "marker")
        self.assertIsInstance(released, int)


if __name__ == "__main__":
    unittest.main()
