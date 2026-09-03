from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name: str, pkg_name: str = "_minimax_windows_paths_test"):
    pkg = sys.modules.get(pkg_name) or types.ModuleType(pkg_name)
    if pkg_name not in sys.modules:
        pkg.__path__ = [str(ROOT)]
        sys.modules[pkg_name] = pkg
    full = f"{pkg_name}.{module_name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SafeComponentWindowsEdgeTests(unittest.TestCase):
    """Portable filename components must survive Windows filesystem rules."""

    @classmethod
    def setUpClass(cls):
        cls.utils = load_module("filename_utils")

    def test_reserved_device_names_are_neutralized(self):
        for name in ("CON", "con", "NUL", "nul", "PRN", "AUX", "COM1", "COM9", "LPT1", "LPT9"):
            out = self.utils.safe_filename_component(name)
            self.assertNotEqual(out.lower().split(".")[0], name.lower())
            self.assertTrue(out.endswith("_"), name)

    def test_reserved_device_names_with_extension(self):
        for name, expected_base in (
            ("CON.txt", "CON_"),
            ("COM3.backup", "COM3_"),
            ("LPT1", "LPT1_"),
        ):
            out = self.utils.safe_filename_component(name)
            base = out.split(".")[0]
            self.assertEqual(base, expected_base)
            self.assertNotIn(base, {"CON", "COM3", "LPT1"})

    def test_non_reserved_names_are_unchanged(self):
        for name in ("Console", "Comet", "Nylon", "Composer", "CON2 music"):
            self.assertEqual(self.utils.safe_filename_component(name), name)

    def test_trailing_dots_and_spaces_are_stripped(self):
        self.assertEqual(self.utils.safe_filename_component("title."), "title")
        self.assertEqual(self.utils.safe_filename_component("title   "), "title")
        self.assertEqual(self.utils.safe_filename_component("title. ."), "title")
        self.assertEqual(self.utils.safe_filename_component("..."), "song")

    def test_unicode_titles_stay_usable(self):
        for name in ("Café", "Übermorgen", "日本語の歌", "🎵 Nachtlied", "Cafe\u0301"):
            out = self.utils.safe_filename_component(name)
            self.assertTrue(out)
            self.assertNotIn("\x00", out)
            # No control characters or Windows-invalid characters may remain.
            self.assertFalse(any(ch in out for ch in '<>:"/\\|?*'))
            self.assertEqual(out.encode("utf-8").decode("utf-8"), out)

    def test_over_long_titles_are_truncated_on_character_boundary(self):
        long_title = "x" * 5000
        out = self.utils.safe_filename_component(long_title)
        self.assertLessEqual(len(out), self.utils.MAX_COMPONENT_LENGTH)
        self.assertFalse(out.endswith((" ", ".")))
        out.encode("utf-8")  # must not raise (no lone surrogate)

    def test_empty_values_fall_back_to_song(self):
        self.assertEqual(self.utils.safe_filename_component(""), "song")
        self.assertEqual(self.utils.safe_filename_component("   "), "song")
        self.assertEqual(self.utils.safe_filename_component('<>:"/\\|?*'), "song")


class DuplicateTitleCollisionTests(unittest.TestCase):
    """Duplicate Album+Title pairs must stay deterministic; auto_increment disambiguates."""

    @classmethod
    def setUpClass(cls):
        cls.utils = load_module("filename_utils")
        cls.saver = load_module("save_audio_smart_prefix")

    def test_duplicate_titles_yield_identical_base(self):
        tags = {"album": "Example Album", "title": "Same Song"}
        first = self.utils.apply_filename_mode("out/src", tags, tags["title"], "album - title")
        second = self.utils.apply_filename_mode("out/src", tags, tags["title"], "album - title")
        self.assertEqual(first, second)

    def test_pick_path_auto_increments_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "Example Album - Same Song")
            with open(f"{prefix}.flac", "w", encoding="utf-8") as fh:
                fh.write("x")
            chosen = self.saver._pick_path(prefix, "flac", "auto_increment")
            self.assertEqual(os.path.basename(chosen), "Example Album - Same Song_001.flac")

    def test_pick_path_error_if_exists_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "Example Album - Same Song")
            with open(f"{prefix}.flac", "w", encoding="utf-8") as fh:
                fh.write("x")
            with self.assertRaises(FileExistsError):
                self.saver._pick_path(prefix, "flac", "error_if_exists")

    def test_preview_output_files_reports_collisions_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "audio")
            entry = self.saver.preview_output_files(
                f"{base}/32flac/", "flac", collision_mode="auto_increment",
                filename_mode="album - title", tags_meta={"album": "Al", "title": "Ti"}, title="Ti",
            )
            self.assertEqual(entry["kind"], "flac")
            self.assertFalse(entry["exists"])
            self.assertTrue(entry["path"].endswith("Al - Ti.flac"))
            # Create the file; the next preview must pick the auto-increment path.
            os.makedirs(os.path.dirname(entry["path"]), exist_ok=True)
            with open(entry["path"], "w", encoding="utf-8") as fh:
                fh.write("x")
            second = self.saver.preview_output_files(
                f"{base}/32flac/", "flac", collision_mode="auto_increment",
                filename_mode="album - title", tags_meta={"album": "Al", "title": "Ti"}, title="Ti",
            )
            self.assertTrue(second["path"].endswith("Al - Ti_001.flac"))
            self.assertFalse(second["exists"])


if __name__ == "__main__":
    unittest.main()
