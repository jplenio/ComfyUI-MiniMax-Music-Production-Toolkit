"""Tests for the exact MiniMax token counting path (IMPROVE-TODO P02).

Covers three promises of the task:

* the real tokenizer is used when its checkpoint is readable, and the value is
  reported as *measured* rather than estimated;
* the fallback is visibly an estimate, including the case where the heuristic
  is below the measured count (dense scripts such as CJK or Urdu);
* the tokenizer is cached by checkpoint identity with a bounded cache, and only
  the ``tokenizer_json`` metadata tensor is read.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_toolkit_modules():
    pkg_name = "_toolkit_token_count_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in (
        "toolkit_logging",
        "prompt_library",
        "prompt_metadata",
        "prompt_budget",
        "minimax_prompt_source",
        "minimax_prompt_report",
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
budget = MODULES["prompt_budget"]
source = MODULES["minimax_prompt_source"]
report = MODULES["minimax_prompt_report"]
PARSER_NODE = source.MiniMaxParseExternalLLMOutputV16

FAKE_COMFY_MODULES = (
    "comfy",
    "comfy.ldm",
    "comfy.ldm.minimax_music",
    "comfy.ldm.minimax_music.prompt",
)


class FakeTokenizer:
    """Duck-typed stand-in for ``tokenizers.Tokenizer``."""

    def __init__(self, chars_per_token=4.0):
        self.chars_per_token = chars_per_token
        self.encoded = []

    def encode(self, text, add_special_tokens=False):
        self.encoded.append((text, add_special_tokens))
        count = max(1, int(len(text) / self.chars_per_token))
        return types.SimpleNamespace(ids=list(range(count)))


def install_fake_runtime(tokenizer=None, payload=b'{"version":"1.0"}', fail_on_tensor=False):
    """Install fake ``tokenizers``/``safetensors`` modules and return the calls."""
    tokenizer = tokenizer if tokenizer is not None else FakeTokenizer()
    calls = []

    class _Handle:
        def __init__(self, path, framework=None):
            calls.append(("open", str(path), framework))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_tensor(self, key):
            calls.append(("tensor", key))
            if fail_on_tensor:
                raise KeyError(key)
            return types.SimpleNamespace(tobytes=lambda: payload)

    safetensors = types.ModuleType("safetensors")
    safetensors.safe_open = _Handle
    tokenizers = types.ModuleType("tokenizers")

    class _Tokenizer:
        @staticmethod
        def from_str(text):
            calls.append(("from_str", text))
            return tokenizer

    tokenizers.Tokenizer = _Tokenizer
    sys.modules["safetensors"] = safetensors
    sys.modules["tokenizers"] = tokenizers
    return calls


def install_fake_build_prompt(text_template="{caption}|{lyrics}"):
    """Install a fake ``comfy.ldm.minimax_music.prompt`` module."""
    captured = []

    comfy = types.ModuleType("comfy")
    comfy.__path__ = []
    ldm = types.ModuleType("comfy.ldm")
    ldm.__path__ = []
    minimax = types.ModuleType("comfy.ldm.minimax_music")
    minimax.__path__ = []
    prompt = types.ModuleType("comfy.ldm.minimax_music.prompt")

    def build_prompt(caption, lyrics):
        captured.append((caption, lyrics))
        return text_template.format(caption=caption, lyrics=lyrics)

    prompt.build_prompt = build_prompt
    prompt.clean_caption = lambda text: text
    prompt.normalize_lyrics = lambda text: text
    minimax.prompt = prompt
    for name, module in (
        ("comfy", comfy),
        ("comfy.ldm", ldm),
        ("comfy.ldm.minimax_music", minimax),
        ("comfy.ldm.minimax_music.prompt", prompt),
    ):
        sys.modules[name] = module
    return captured


class TokenCountTestCase(unittest.TestCase):
    def setUp(self):
        budget._TOKENIZER_CACHE.clear()
        self._saved = {name: sys.modules.get(name) for name in FAKE_COMFY_MODULES}
        self._saved["safetensors"] = sys.modules.get("safetensors")
        self._saved["tokenizers"] = sys.modules.get("tokenizers")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._restore)

    def _restore(self):
        for name in FAKE_COMFY_MODULES + ("safetensors", "tokenizers"):
            saved = self._saved.get(name)
            if saved is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved
        budget._TOKENIZER_CACHE.clear()

    def _checkpoint(self, name="minimax_music3_text_encoder_pruned_int8_convrot.safetensors", data=b"x"):
        path = Path(self._tmp.name) / name
        path.write_bytes(data)
        return path

    def patch_attr(self, obj, name, value):
        original = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, original)


class EstimateFallbackTests(TokenCountTestCase):
    def test_without_runtime_the_value_is_marked_as_an_estimate(self):
        self.patch_attr(budget, "_safe_import_tokenizer_runtime", lambda: None)
        info = budget.count_prompt_tokens("caption", "[Intro]\nline")
        self.assertEqual(info["method"], "estimate")
        self.assertFalse(info["exact"])
        self.assertEqual(info["tokens"], budget.estimate_prompt_tokens("caption", "[Intro]\nline"))
        self.assertIsNone(info["estimate_covers_real"])

    def test_missing_checkpoint_falls_back_to_the_estimate(self):
        install_fake_runtime()
        info = budget.count_prompt_tokens("caption", "lyrics", checkpoint=Path(self._tmp.name) / "nope.safetensors")
        self.assertEqual(info["method"], "estimate")
        self.assertFalse(info["exact"])

    def test_unreadable_metadata_falls_back_to_the_estimate(self):
        install_fake_runtime(fail_on_tensor=True)
        info = budget.count_prompt_tokens("caption", "lyrics", checkpoint=self._checkpoint())
        self.assertEqual(info["method"], "estimate")
        self.assertFalse(info["exact"])

    def test_dense_script_reports_that_the_estimate_undershoots(self):
        # 1.2 chars/token: far denser than the 3.5 heuristic assumes (CJK/Urdu).
        install_fake_runtime(FakeTokenizer(chars_per_token=1.2))
        info = budget.count_prompt_tokens("词" * 40, "字" * 40, checkpoint=self._checkpoint())
        self.assertTrue(str(info["method"]).startswith("tokenizer"))
        self.assertEqual(info["estimate_covers_real"], False)
        self.assertGreater(info["tokens"], info["estimate"])


class TokenizerLoadingTests(TokenCountTestCase):
    def test_only_the_tokenizer_json_tensor_is_read(self):
        calls = install_fake_runtime()
        tokenizer, identity = budget.load_minimax_tokenizer(self._checkpoint())
        self.assertIsNotNone(tokenizer)
        self.assertIn(identity, budget._TOKENIZER_CACHE)
        self.assertEqual([c[1] for c in calls if c[0] == "tensor"], ["tokenizer_json"])
        self.assertTrue(all(c[2] == "np" for c in calls if c[0] == "open"))

    def test_identity_is_reused_for_the_same_signature(self):
        calls = install_fake_runtime()
        path = self._checkpoint()
        first, first_id = budget.load_minimax_tokenizer(path)
        second, second_id = budget.load_minimax_tokenizer(path)
        self.assertIs(first, second)
        self.assertEqual(first_id, second_id)
        self.assertEqual(len([c for c in calls if c[0] == "from_str"]), 1)

    def test_changed_signature_loads_a_new_tokenizer(self):
        calls = install_fake_runtime()
        path = self._checkpoint()
        budget.load_minimax_tokenizer(path)
        path.write_bytes(b"y" * 64)
        budget.load_minimax_tokenizer(path)
        self.assertEqual(len([c for c in calls if c[0] == "from_str"]), 2)

    def test_cache_is_bounded(self):
        install_fake_runtime()
        for index in range(4):
            budget.load_minimax_tokenizer(self._checkpoint(name=f"minimax_music3_text_encoder_{index}.safetensors"))
        self.assertLessEqual(len(budget._TOKENIZER_CACHE), budget._TOKENIZER_CACHE_MAX)


class CountedPromptTests(TokenCountTestCase):
    def test_count_uses_comfyui_build_prompt_text_when_available(self):
        tokenizer = FakeTokenizer(chars_per_token=4.0)
        install_fake_runtime(tokenizer)
        captured = install_fake_build_prompt("<s>{caption}#{lyrics}</s>")
        info = budget.count_prompt_tokens("cap", "lyr", checkpoint=self._checkpoint())
        self.assertEqual(captured, [("cap", "lyr")])
        self.assertEqual(info["method"], "tokenizer")
        self.assertTrue(info["exact"])
        self.assertEqual([text for text, _ in tokenizer.encoded], ["<s>cap#lyr</s>"])
        self.assertEqual(info["tokens"], len("<s>cap#lyr</s>") // 4)

    def test_count_is_text_only_when_build_prompt_is_unavailable(self):
        install_fake_runtime(FakeTokenizer(chars_per_token=4.0))
        info = budget.count_prompt_tokens("cap", "lyr", checkpoint=self._checkpoint())
        self.assertEqual(info["method"], "tokenizer_text_only")
        self.assertFalse(info["exact"])


class MeasuredTrimmingTests(TokenCountTestCase):
    @staticmethod
    def line_counter():
        return lambda caption, lyrics: len(f"{caption}\n{lyrics}".strip().splitlines())

    def test_trimming_uses_the_measured_count_and_reports_removals(self):
        lyrics = "\n".join(f"line {index}" for index in range(40))
        result = budget.trim_prompt_to_budget("caption", lyrics, 10, counter=self.line_counter())
        self.assertTrue(result["trimmed"])
        self.assertEqual(result["count_method"], "tokenizer")
        self.assertLessEqual(result["estimated_tokens"], 10)
        self.assertGreater(result["removed_lines"], 0)

    def test_section_tags_removed_with_their_content_are_counted(self):
        lyrics = "[Verse]\nkeep\n[Chorus]\ndrop me\n[Outro]\nand me"
        result = budget.trim_prompt_to_budget("caption", lyrics, 6, counter=self.line_counter())
        self.assertTrue(result["trimmed"])
        self.assertGreaterEqual(result["removed_sections"], 1)

    def test_boundary_just_below_and_above_the_hard_limit(self):
        counter = lambda caption, lyrics: len(caption) + len(lyrics)
        fits = budget.trim_prompt_to_budget("a" * 100, "b" * 100, 200, counter=counter)
        self.assertFalse(fits["trimmed"])
        over = budget.trim_prompt_to_budget("a" * 100, "b" * 101, 200, counter=counter)
        self.assertTrue(over["trimmed"])
        self.assertLessEqual(over["estimated_tokens"], 200)

    def test_empty_counter_value_never_loops_forever(self):
        call_count = {"n": 0}

        def never_fits(caption, lyrics):
            call_count["n"] += 1
            return 10 ** 6

        result = budget.trim_prompt_to_budget("caption", "line one\nline two", 50, counter=never_fits)
        self.assertTrue(result["trimmed"])
        self.assertLess(call_count["n"], 200)


class ParserNodeReportingTests(TokenCountTestCase):
    def setUp(self):
        super().setUp()
        self._original = source.token_counter

    def tearDown(self):
        source.token_counter = self._original
        super().tearDown()

    def test_measured_counter_is_used_and_labelled(self):
        source.token_counter = lambda *a, **k: (lambda caption, lyrics: 12, "fake::1")
        caption, lyrics, info = PARSER_NODE._apply_prompt_budget("cap", "lyr", 4500, True)
        self.assertEqual((caption, lyrics), ("cap", "lyr"))
        self.assertEqual(info["prompt_tokens"], 12)
        self.assertEqual(info["prompt_token_count_method"], "tokenizer")
        self.assertEqual(info["prompt_tokenizer"], "fake::1")
        self.assertFalse(info["prompt_trimmed"])
        self.assertEqual(info["prompt_tokens_estimated"], budget.estimate_prompt_tokens("cap", "lyr"))

    def test_estimate_path_is_labelled_as_an_estimate(self):
        source.token_counter = lambda *a, **k: (None, None)
        caption, lyrics, info = PARSER_NODE._apply_prompt_budget("cap", "lyr", 4500, True)
        self.assertEqual(info["prompt_token_count_method"], "estimate")
        self.assertIsNone(info["prompt_tokenizer"])
        self.assertEqual(info["prompt_tokens"], budget.estimate_prompt_tokens("cap", "lyr"))

    def test_measured_overflow_trims_and_reports_removals(self):
        source.token_counter = lambda *a, **k: (
            lambda caption, lyrics: len(f"{caption}\n{lyrics}".strip().splitlines()),
            "fake::1",
        )
        lyrics = "\n".join(f"line {index}" for index in range(30))
        caption, trimmed_lyrics, info = PARSER_NODE._apply_prompt_budget("cap", lyrics, 8, True)
        self.assertTrue(info["prompt_trimmed"])
        self.assertLessEqual(info["prompt_tokens"], 8)
        self.assertGreater(info["removed_lines"], 0)
        self.assertLessEqual(len(trimmed_lyrics.splitlines()), len(lyrics.splitlines()))

    def test_measured_overflow_without_trimming_raises(self):
        source.token_counter = lambda *a, **k: (lambda caption, lyrics: 10 ** 6, "fake::1")
        with self.assertRaises(ValueError) as ctx:
            PARSER_NODE._apply_prompt_budget("cap", "lyr", 4500, False)
        self.assertIn("measured", str(ctx.exception))


class PromptReportTests(TokenCountTestCase):
    def test_report_marks_the_estimate_as_an_estimate(self):
        self.patch_attr(budget, "_safe_import_tokenizer_runtime", lambda: None)
        markdown = report.build_prompt_report("caption", "[Intro]\nline", "Title", "cover art")
        self.assertIn("## Token budget (MiniMax text encoder)", markdown)
        self.assertIn("estimate", markdown)
        self.assertIn(str(budget.MINIMAX_MAX_PROMPT_TOKENS), markdown)

    def test_report_marks_a_measured_count_as_measured(self):
        install_fake_runtime(FakeTokenizer(chars_per_token=4.0))
        install_fake_build_prompt()
        self.patch_attr(budget, "resolve_minimax_tokenizer_checkpoint", self._checkpoint)
        markdown = report.build_prompt_report("caption", "lyrics", "Title", "cover art")
        self.assertIn("measured with the MiniMax tokenizer", markdown)
        self.assertNotIn("*estimate*", markdown)

    def test_report_warns_when_the_estimate_undershoots(self):
        install_fake_runtime(FakeTokenizer(chars_per_token=1.2))
        install_fake_build_prompt()
        self.patch_attr(budget, "resolve_minimax_tokenizer_checkpoint", self._checkpoint)
        markdown = report.build_prompt_report("字" * 40, "词" * 40, "Title", "cover art")
        self.assertIn("below* the measured count", markdown)


if __name__ == "__main__":
    unittest.main()
