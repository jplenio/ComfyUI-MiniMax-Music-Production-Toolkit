from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_toolkit_modules():
    pkg_name = "_toolkit_budget_test"
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
parser_node = MODULES["minimax_prompt_source"].MiniMaxParseExternalLLMOutputV16


def make_long_lyrics(lines=80) -> str:
    sections = []
    for index in range(1, lines // 4 + 1):
        sections.append(f"[Verse {index}]")
        sections.extend(
            f"line {index} wordy lyric content with rhythm and rhyme " for _ in range(3)
        )
    return "\n".join(sections)


class PromptTokenEstimateTests(unittest.TestCase):
    def test_empty_prompt_is_zero(self):
        self.assertEqual(budget.estimate_prompt_tokens("", ""), 0)

    def test_estimate_grows_with_text(self):
        small = budget.estimate_prompt_tokens("short caption", "[Intro]")
        large = budget.estimate_prompt_tokens("short caption", make_long_lyrics(60))
        self.assertGreater(large, small)

    def test_estimate_is_conservative_against_calibration(self):
        # Calibration: the real MiniMax tokenizer consumed 91 tokens for a
        # 458-character build_prompt (German worst case ~3.68 chars/token).
        # The estimator must stay above the real count.
        sample = "x" * 352
        estimate = budget.estimate_prompt_tokens("", sample)
        self.assertEqual(estimate, 125)  # ceil(352/3.5)+24
        self.assertGreaterEqual(estimate, 91)

    def test_constants(self):
        self.assertEqual(budget.MINIMAX_MAX_PROMPT_TOKENS, 5000)
        self.assertLess(budget.DEFAULT_PROMPT_TOKEN_BUDGET, budget.MINIMAX_MAX_PROMPT_TOKENS)


class SoftTrimTests(unittest.TestCase):
    def test_under_budget_is_untouched(self):
        result = budget.trim_prompt_to_budget("caption", "[Intro]\ncontent", 4500)
        self.assertFalse(result["trimmed"])
        self.assertEqual(result["caption"], "caption")
        self.assertEqual(result["lyrics"], "[Intro]\ncontent")

    def test_over_budget_trims_whole_lines_from_the_end(self):
        caption = "A concise caption."
        lyrics = make_long_lyrics(80)
        result = budget.trim_prompt_to_budget(caption, lyrics, 600)
        self.assertTrue(result["trimmed"])
        self.assertEqual(result["caption"], caption)
        self.assertLessEqual(result["estimated_tokens"], 600)
        self.assertGreater(result["original_estimated_tokens"], 600)
        # The beginning of the lyrics survives; the end is dropped.
        trimmed_lyrics = result["lyrics"]
        self.assertTrue(trimmed_lyrics.startswith("[Verse 1]"))
        self.assertLess(len(trimmed_lyrics.splitlines()), len(lyrics.splitlines()))

    def test_orphan_section_tags_are_removed(self):
        caption = "A concise caption."
        lyrics = "[Intro]\ncontent line\n[Outro]"
        result = budget.trim_prompt_to_budget(caption, lyrics, 35)
        self.assertTrue(result["trimmed"])
        self.assertFalse(result["lyrics"].endswith("[Outro]"))
        self.assertTrue(result["lyrics"].startswith("[Intro]"))

    def test_hard_cut_only_for_single_oversized_line(self):
        caption = "A concise caption."
        lyrics = "word" * 4000  # one giant line, no newlines
        result = budget.trim_prompt_to_budget(caption, lyrics, 600)
        self.assertTrue(result["trimmed"])
        self.assertLessEqual(result["estimated_tokens"], 600)
        self.assertTrue(result["hard_cut_used"])

    def test_oversized_caption_is_trimmed_linewise(self):
        caption = "\n".join(f"caption line {i} " * 10 for i in range(60))
        lyrics = "[Intro]"
        result = budget.trim_prompt_to_budget(caption, lyrics, 600)
        self.assertLessEqual(result["estimated_tokens"], 600)
        # The beginning survives intact and whole lines are kept (no mid-word
        # cuts except possibly the final kept line when a hard cut is needed).
        trimmed_lines = result["caption"].splitlines()
        self.assertEqual(trimmed_lines[0], caption.splitlines()[0])
        for line in trimmed_lines[:-1]:
            self.assertTrue(line.rstrip().endswith(tuple(str(i) for i in range(10))))


class ParserBudgetIntegrationTests(unittest.TestCase):
    def _parse(self, caption, lyrics, **overrides):
        kwargs = dict(
            song_count=1,
            seed_mode="random_each_song",
            base_seed=1,
            user_prompt="a user prompt",
            source_name_override="",
            fallback_title="llm-song",
            structured_llm_output=None,
            manual_caption=caption,
            manual_lyrics=lyrics,
            manual_title="",
            manual_image_prompt="",
            model_check_report="",
            max_prompt_tokens=600,
            trim_long_prompt=True,
        )
        kwargs.update(overrides)
        return parser_node().parse(**kwargs)

    def test_parser_softly_trims_long_llm_prompt(self):
        caption = "A concise caption with arrangement details."
        lyrics = make_long_lyrics(80)
        result = self._parse(caption, lyrics)
        self.assertEqual(result[0], [caption])
        self.assertLess(len(result[1][0]), len(lyrics))
        provenance = json.loads(result[10][0])
        self.assertTrue(provenance["prompt_trimmed"])
        self.assertLessEqual(provenance["prompt_tokens_estimated"], 600)
        self.assertGreater(provenance["original_prompt_tokens_estimated"], 600)

    def test_parser_keeps_short_prompt_untouched(self):
        caption = "A concise caption."
        lyrics = "[Intro]\nshort"
        result = self._parse(caption, lyrics)
        self.assertEqual(result[1], ["[Intro]\nshort"])
        provenance = json.loads(result[10][0])
        self.assertFalse(provenance["prompt_trimmed"])
        self.assertIn("prompt_tokens_estimated", provenance)

    def test_parser_raises_clearly_when_trim_disabled(self):
        caption = "A concise caption."
        lyrics = make_long_lyrics(80)
        with self.assertRaises(ValueError) as ctx:
            self._parse(caption, lyrics, trim_long_prompt=False)
        self.assertIn("exceeds the MiniMax token budget", str(ctx.exception))

    def test_input_types_expose_budget_controls(self):
        optional = parser_node.INPUT_TYPES()["optional"]
        self.assertEqual(optional["max_prompt_tokens"][1]["default"], 4500)
        self.assertEqual(optional["trim_long_prompt"][1]["default"], True)


if __name__ == "__main__":
    unittest.main()
