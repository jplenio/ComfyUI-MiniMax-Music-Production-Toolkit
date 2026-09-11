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

class PortableLengthAndSeparatorTests(unittest.TestCase):
    """Windows separators/UNC and UTF-16 component budgets (T09 / F13)."""

    @classmethod
    def setUpClass(cls):
        cls.utils = load_module("filename_utils")
        cls.saver = load_module("save_audio_smart_prefix")
        cls.artwork = load_module("minimax_artwork")
        cls.absolute = load_module("save_audio_absolute")
        cls.paths = load_module("output_paths")

    # -- length is counted in UTF-16 units, not Python characters -----------

    def test_astral_titles_stay_within_the_utf16_budget(self):
        # 500 emoji = 1000 UTF-16 units; a character-counted budget would keep
        # 180 of them (360 units) and still fit, but a mix of wide/narrow text
        # must never exceed the budget either way.
        out = self.utils.safe_filename_component("\U0001F3B5" * 500)
        self.assertLessEqual(self.utils.utf16_length(out), self.utils.MAX_COMPONENT_LENGTH)
        out.encode("utf-8")  # no lone surrogate

    def test_mixed_bmp_and_astral_names_fit(self):
        out = self.utils.safe_filename_component("Song \U0001F3B5" * 200)
        self.assertLessEqual(self.utils.utf16_length(out), self.utils.MAX_COMPONENT_LENGTH)
        self.assertFalse(out.endswith((" ", ".")))

    def test_truncate_never_splits_a_surrogate_pair(self):
        text = "\U0001F3B5" * 10
        truncated = self.utils.truncate_to_utf16(text, 5)
        self.assertEqual(truncated, "\U0001F3B5" * 2)
        self.assertEqual(self.utils.utf16_length(truncated), 4)
        self.assertEqual(self.utils.truncate_to_utf16("abc", 10), "abc")

    def test_ordinary_names_are_not_renamed(self):
        for name in ("Café", "Übermorgen", "日本語の歌", "Example Album - Example Song"):
            with self.subTest(name=name):
                self.assertEqual(self.utils.safe_filename_component(name), name)

    # -- combined album + title budget --------------------------------------

    def test_combined_album_title_stays_within_budget(self):
        album = "A" * 170
        title = "B" * 170
        base = self.utils.apply_filename_mode(
            "out/placeholder", {"album": album, "title": title}, title, "album - title"
        )
        basename = os.path.basename(base)
        self.assertLessEqual(self.utils.utf16_length(basename), self.utils.MAX_COMPONENT_LENGTH)
        self.assertTrue(basename.startswith("A" * 10), "the album prefix must stay readable")
        self.assertTrue(basename.endswith("B"), "truncation shortens the title tail")

    def test_normal_album_title_is_unchanged(self):
        base = self.utils.apply_filename_mode(
            "out/placeholder", {"album": "Example Album", "title": "Example Song"},
            "Example Song", "album - title",
        )
        self.assertEqual(base, os.path.join("out", "Example Album - Example Song"))

    def test_title_only_and_prefix_modes_are_unaffected(self):
        base = self.utils.apply_filename_mode(
            "out/placeholder", {"album": "Example Album", "title": "Example Song"},
            "Example Song", "title only",
        )
        self.assertEqual(base, os.path.join("out", "Example Song"))
        as_is = self.utils.apply_filename_mode(
            "out/placeholder", {"album": "Example Album", "title": "Example Song"},
            "Example Song", "prefix as provided",
        )
        self.assertEqual(as_is, os.path.join("out", "placeholder"))

    def test_invalid_mode_still_raises_with_the_caller_label(self):
        with self.assertRaises(ValueError) as ctx:
            self.utils.apply_filename_mode("out/x", {}, "t", "nope", error_prefix="Save Image Smart Prefix")
        self.assertIn("Save Image Smart Prefix", str(ctx.exception))

    # -- absolute saver filename cleanup ------------------------------------

    def test_absolute_saver_bounds_long_names_and_keeps_policy(self):
        self.assertEqual(self.absolute._clean_filename("Song.flac"), "Song")
        self.assertEqual(self.absolute._clean_filename("  "), "audio")
        self.assertEqual(self.absolute._clean_filename("CON"), "_CON")
        long_name = self.absolute._clean_filename("Q" * 5000)
        self.assertLessEqual(self.utils.utf16_length(long_name), self.utils.MAX_COMPONENT_LENGTH)
        # Ordinary names keep their exact previous spelling.
        self.assertEqual(self.absolute._clean_filename("Example Song"), "Example Song")

    # -- smart prefix resolution with Windows separators --------------------

    def test_windows_separators_resolve_like_forward_slashes(self):
        forward = self.saver._resolve_prefix("audio/minimax3")
        backward = self.saver._resolve_prefix("audio\\minimax3")
        self.assertTrue(os.path.isabs(forward) and os.path.isabs(backward))
        self.assertEqual(os.path.normpath(forward), os.path.normpath(backward))

    def test_drive_and_unc_prefixes_are_absolute_for_both_savers(self):
        for value in ("C:\\Music\\MiniMax", "C:/Music/MiniMax", "\\\\server\\share\\x", "//server/share/x"):
            with self.subTest(value=value):
                self.assertTrue(self.paths.is_abs_any_platform(value))
                if os.name == "nt":
                    self.assertEqual(
                        os.path.normpath(self.saver._resolve_prefix(value)),
                        os.path.normpath(self.artwork._resolve_prefix(value)),
                    )

    def test_relative_prefixes_stay_contained(self):
        for value in ("../escape", "audio/../../escape"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.saver._resolve_prefix(value)


if __name__ == "__main__":
    unittest.main()
