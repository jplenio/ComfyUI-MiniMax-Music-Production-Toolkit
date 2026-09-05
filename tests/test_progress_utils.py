"""Unit tests for the log progress-bar helper."""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_progress_utils():
    pkg_name = "_progress_utils_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    spec = importlib.util.spec_from_file_location(f"{pkg_name}.progress_utils", ROOT / "progress_utils.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{pkg_name}.progress_utils"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FormatProgressBarTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_progress_utils()

    def test_bar_spans_zero_to_total(self):
        text = self.mod.format_progress_bar(0, 100, width=10)
        self.assertEqual(text, "[----------]  0/100")

    def test_half_done_bar(self):
        text = self.mod.format_progress_bar(50, 100, width=10)
        self.assertEqual(text, "[#####-----]  50/100")

    def test_done_bar_fills_completely(self):
        text = self.mod.format_progress_bar(100, 100, width=10)
        self.assertEqual(text, "[##########]  100/100")

    def test_done_is_clamped_to_total(self):
        text = self.mod.format_progress_bar(150, 100, width=10)
        self.assertEqual(text, "[##########]  100/100")

    def test_zero_total_does_not_divide(self):
        text = self.mod.format_progress_bar(0, 0, width=10)
        self.assertEqual(text, "[----------]  0/1")


if __name__ == "__main__":
    unittest.main()
