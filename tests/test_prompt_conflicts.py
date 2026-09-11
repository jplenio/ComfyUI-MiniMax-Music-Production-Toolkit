"""Tests for the compact prompt core and the brief conflict report (P01).

P01 asks for three things that can be checked without a model: a genuinely
shorter opt-in prompt (not the same 25k-character text with an added
instruction), a brief whose explicit constraints win over free text, and a
report of known contradictions **before** generation instead of appended
contradictory sentences.
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_toolkit_modules():
    pkg_name = "_toolkit_prompt_conflicts_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in (
        "toolkit_logging",
        "prompt_library",
        "prompt_sources",
        "prompt_metadata",
        "llm_sampling",
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
sources = MODULES["prompt_sources"]
metadata = MODULES["prompt_metadata"]
sampling = MODULES["llm_sampling"]

SYSTEM_DIR = ROOT / "prompts" / "system"
COMPACT = SYSTEM_DIR / "minimax-music3-compact-core.txt"


class CompactCoreTests(unittest.TestCase):
    def read(self, name):
        return (SYSTEM_DIR / name).read_text(encoding="utf-8")

    def test_the_compact_core_exists_and_hits_the_documented_size(self):
        words = len(COMPACT.read_text(encoding="utf-8").split())
        self.assertLessEqual(words, 1200, "the core must stay inside the 800-1200 word target")
        self.assertGreaterEqual(words, 700, "a core that short would drop required rules")

    def test_it_is_really_shorter_than_the_existing_variants(self):
        core = COMPACT.read_text(encoding="utf-8")
        for name in ("minimax-music3-concise.txt", "minimax-music3-production.txt"):
            with self.subTest(template=name):
                long_text = self.read(name)
                self.assertLess(
                    len(core),
                    len(long_text) * 0.4,
                    f"the core must be less than 40% of {name}, not the same text with one extra instruction",
                )

    def test_it_promises_a_lower_llm_input_budget(self):
        core = COMPACT.read_text(encoding="utf-8")
        long_text = self.read("minimax-music3-concise.txt")
        brief = metadata.assemble_block_brief({"genre": "Ambient"}, "calm instrumental, 20 s")
        core_tokens = sampling.estimate_input_tokens(core + brief)
        long_tokens = sampling.estimate_input_tokens(long_text + brief)
        self.assertLess(core_tokens, long_tokens * 0.4)

    def test_the_output_contract_is_kept(self):
        core = COMPACT.read_text(encoding="utf-8")
        for tag in ("[Caption]", "[Lyrics]", "[Title]", "[Image_Prompt]"):
            with self.subTest(tag=tag):
                self.assertIn(tag, core)

    def test_the_conflict_rules_are_part_of_the_core(self):
        core = COMPACT.read_text(encoding="utf-8").lower()
        self.assertIn("the brief is the authority", core)
        self.assertIn("word for word", core, "supplied lyrics must be protected")
        self.assertIn("heuristic", core, "the 2:1 section rule must not be sold as a guarantee")
        self.assertIn("no text", core)

    def test_the_existing_templates_are_untouched(self):
        templates = sorted(path.name for path in SYSTEM_DIR.glob("*.txt"))
        self.assertEqual(len(templates), 12, "the 11 existing templates plus the new compact core")
        for name in templates:
            with self.subTest(template=name):
                self.assertGreater(len(self.read(name).split()), 100)

    def test_the_user_library_still_loads(self):
        # The acceptance asks for a static check of every user template.
        user_templates = sorted((ROOT / "prompts" / "user").rglob("*.txt"))
        self.assertGreaterEqual(len(user_templates), 200, "the bundled user library must stay complete")
        for path in user_templates:
            with self.subTest(template=path.name):
                self.assertTrue(path.read_text(encoding="utf-8").strip())


class BlockBriefTests(unittest.TestCase):
    def test_the_three_blocks_appear_in_order(self):
        brief = metadata.assemble_block_brief(
            {"genre": "Ambient"}, "calm and wide", provided_lyrics="[Verse]\nhello"
        )
        self.assertLess(brief.index("Constraints:"), brief.index("Creative description:"))
        self.assertLess(brief.index("Creative description:"), brief.index("Provided lyrics"))
        self.assertIn("Genre: Ambient", brief)
        self.assertIn("calm and wide", brief)
        self.assertIn("[Verse]\nhello", brief)

    def test_the_precedence_sentence_is_part_of_the_constraints(self):
        brief = metadata.assemble_block_brief({"genre": "Ambient"}, "a wild idea")
        self.assertIn(metadata.CONSTRAINTS_PRECEDENCE, brief)
        self.assertIn("the constraint wins", brief)

    def test_custom_and_empty_fields_are_omitted(self):
        brief = metadata.assemble_block_brief(
            {"genre": "Ambient", "theme": metadata.CUSTOM, "tempo": ""}, "calm"
        )
        self.assertNotIn("Lyrics theme", brief)
        self.assertNotIn("Tempo", brief)
        self.assertIn("Genre", brief)

    def test_an_empty_selection_says_so_instead_of_inventing_one(self):
        brief = metadata.assemble_block_brief({}, "")
        self.assertIn("(none given", brief)

    def test_supplied_lyrics_are_not_rewritten(self):
        lyrics = "[Verse]\nI keep your letter\n[Chorus]\nSay it slow"
        brief = metadata.assemble_block_brief({}, "pop", provided_lyrics=lyrics)
        self.assertIn(lyrics, brief)
        self.assertIn("verbatim", brief)

    def test_the_existing_assembly_is_unchanged(self):
        # The compat path must keep its historic shape (no blocks).
        legacy = metadata.assemble_structured_user_prompt({"genre": "Ambient"}, "calm and wide")
        self.assertTrue(legacy.startswith("Musical brief:"))
        self.assertIn("calm and wide", legacy)
        self.assertNotIn("Constraints:", legacy)


class ConflictReportTests(unittest.TestCase):
    def cautious_prompt(self):
        return "Avoid metallic and harsh cymbals; keep reverb tails minimal. No text in the image."

    def test_a_requested_element_beats_a_caution_rule(self):
        findings = metadata.detect_brief_conflicts(
            {"genre": "Ambient"},
            "warm bells and shimmering cymbals in the outro",
            system_prompt=self.cautious_prompt(),
        )
        codes = [finding["code"] for finding in findings]
        self.assertIn("requested_element_vs_cautious_rules", codes)
        finding = next(f for f in findings if f["code"] == "requested_element_vs_cautious_rules")
        self.assertEqual(finding["severity"], "warning")
        self.assertIn("user requirement wins", finding["resolution"])

    def test_a_clean_brief_reports_nothing(self):
        findings = metadata.detect_brief_conflicts(
            {"genre": "Techno"}, "driving kick, rolling bass", system_prompt="Be concise and specific."
        )
        self.assertEqual(findings, [])
        self.assertIn("none detected", metadata.format_brief_conflicts(findings))

    def test_cautious_wording_alone_does_not_trigger(self):
        # A style description that merely mentions an instrument, or a genre named
        # "Ambient", must not fire - only a concrete *request* does.
        findings = metadata.detect_brief_conflicts(
            {"genre": "Ambient"}, "driving kick, rolling bass, steady tempo", system_prompt=self.cautious_prompt()
        )
        self.assertEqual(findings, [])

    def test_instrumental_brief_with_supplied_lyrics_is_reported(self):
        findings = metadata.detect_brief_conflicts(
            {"genre": "Ambient"},
            "purely instrumental bed",
            provided_lyrics="[Verse]\nwords",
            system_prompt="You write music.",
        )
        codes = [finding["code"] for finding in findings]
        self.assertIn("instrumental_vs_provided_lyrics", codes)
        finding = next(f for f in findings if f["code"] == "instrumental_vs_provided_lyrics")
        self.assertIn("lyrics win", finding["resolution"])

    def test_the_positive_only_wording_is_flagged_as_informational(self):
        findings = metadata.detect_brief_conflicts(
            {},
            "cover image, no text",
            system_prompt="The image prompt is positive-only. Always add: No text, no letters.",
        )
        codes = [finding["code"] for finding in findings]
        self.assertIn("image_prompt_negative_wording", codes)
        finding = next(f for f in findings if f["code"] == "image_prompt_negative_wording")
        self.assertEqual(finding["severity"], "info")
        self.assertIn("no-text line stays", finding["resolution"])

    def test_a_duration_mismatch_shows_both_values_without_changing_them(self):
        findings = metadata.detect_brief_conflicts(
            {}, "a 360 second piece", system_prompt="x", max_duration_s=300
        )
        codes = [finding["code"] for finding in findings]
        self.assertIn("duration_mismatch", codes)
        finding = next(f for f in findings if f["code"] == "duration_mismatch")
        self.assertIn("No setting is changed automatically", finding["resolution"])

    def test_matching_durations_are_not_reported(self):
        findings = metadata.detect_brief_conflicts(
            {}, "a 300 second piece", system_prompt="x", max_duration_s=300
        )
        self.assertEqual(findings, [])

    def test_the_report_renders_every_finding(self):
        findings = metadata.detect_brief_conflicts(
            {"genre": "Ambient"},
            "bells and cymbals, 360 seconds",
            provided_lyrics="[Verse]\nwords",
            system_prompt=self.cautious_prompt() + " instrumental preferred",
            max_duration_s=300,
        )
        text = metadata.format_brief_conflicts(findings)
        self.assertGreaterEqual(len(findings), 2)
        for finding in findings:
            self.assertIn(finding["code"], text)
            self.assertIn(finding["resolution"], text)


if __name__ == "__main__":
    unittest.main()
