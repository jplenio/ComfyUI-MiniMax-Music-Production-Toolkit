"""Tests for ``scripts/calibrate_prompt_tokens.py`` (IMPROVE-TODO P02).

The regression this pins: the calibrator used to report the *maximum*
chars/token as the "worst case".  For a conservative chars-per-token ceiling,
the binding sample is the one with the **minimum** ratio (the densest script),
so the maximum would have accepted a constant that undershoots.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_calibrator():
    spec = importlib.util.spec_from_file_location(
        "_calibrate_prompt_tokens", ROOT / "scripts" / "calibrate_prompt_tokens.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


cal = load_calibrator()


class CalibrationStatisticsTests(unittest.TestCase):
    def rows(self):
        # 6.0 chars/token (sparse, e.g. English) vs 2.0 chars/token (dense).
        return [
            {"label": "sparse", "prompt_chars": 600, "tokens": 100, "chars_per_token": 6.0},
            {"label": "dense", "prompt_chars": 200, "tokens": 100, "chars_per_token": 2.0},
            {"label": "middle", "prompt_chars": 400, "tokens": 100, "chars_per_token": 4.0},
        ]

    def test_binding_statistic_is_the_minimum_not_the_maximum(self):
        summary = cal.summarize_rows(self.rows())
        self.assertEqual(summary["binding_min"], 2.0)
        self.assertEqual(summary["binding_label"], "dense")
        self.assertEqual(summary["max"], 6.0)
        self.assertEqual(summary["median"], 4.0)

    def test_verdict_rejects_a_constant_above_the_minimum(self):
        summary = cal.summarize_rows(self.rows())
        self.assertFalse(cal.verdict(summary, 3.5)["ok"])
        self.assertTrue(cal.verdict(summary, 2.0)["ok"])
        self.assertTrue(cal.verdict(summary, 1.5)["ok"])

    def test_verdict_reports_the_binding_sample(self):
        result = cal.verdict(cal.summarize_rows(self.rows()), 3.5)
        self.assertEqual(result["binding_label"], "dense")
        self.assertIn("undershoot", result["reason"])

    def test_unusable_rows_do_not_crash(self):
        summary = cal.summarize_rows([{"label": "empty", "prompt_chars": 0, "tokens": 0, "chars_per_token": None}])
        self.assertIsNone(summary["binding_min"])
        self.assertIsNone(cal.verdict(summary, 3.5)["ok"])

    def test_build_rows_measures_the_estimator_input_text(self):
        rows = cal.build_rows([("sample", "capt", "lyr")], lambda caption, lyrics: 5)
        self.assertEqual(rows[0]["prompt_chars"], len("capt") + 1 + len("lyr"))
        self.assertEqual(rows[0]["tokens"], 5)
        self.assertEqual(rows[0]["chars_per_token"], (len("capt") + 1 + len("lyr")) / 5)


class CalibrationSampleTests(unittest.TestCase):
    def test_samples_cover_several_scripts(self):
        labels = [label for label, _, _ in cal.SAMPLES]
        self.assertGreaterEqual(len(labels), 6)
        self.assertEqual(len(labels), len(set(labels)), "sample labels must be unique")

    def test_samples_are_multilingual(self):
        # Dense scripts are the reason the minimum matters; at least four
        # samples must be non-Latin so the coverage cannot silently regress.
        non_latin = 0
        for _, caption, lyrics in cal.SAMPLES:
            text = caption + lyrics
            if any(ord(char) > 0x0370 for char in text):
                non_latin += 1
        self.assertGreaterEqual(non_latin, 4)

    def test_documented_constant_is_the_prompt_budget_value(self):
        source = (ROOT / "prompt_budget.py").read_text(encoding="utf-8")
        self.assertIn(f"_CHARS_PER_TOKEN = {cal.DOCUMENTED_CHARS_PER_TOKEN}", source)


if __name__ == "__main__":
    unittest.main()
