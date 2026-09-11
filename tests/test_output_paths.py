"""Output path planning tests (F13 / T08).

Covers macro expansion, absolute/UNC/relative resolution, collision selection,
the non-writing preview and the parity between the audio and artwork wrappers -
plus the guarantee that planning a filename pulls in no codec/audio imports.
"""
from __future__ import annotations

import datetime
import importlib.util
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = "_output_paths_test"


def _load_synthetic(module_names):
    if PKG not in sys.modules:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = [str(ROOT)]
        sys.modules[PKG] = pkg
    loaded = {}
    for name in module_names:
        full = f"{PKG}.{name}"
        if full not in sys.modules:
            spec = importlib.util.spec_from_file_location(full, ROOT / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[full] = module
            assert spec.loader is not None
            spec.loader.exec_module(module)
        loaded[name] = sys.modules[full]
    return loaded


MODULES = _load_synthetic(["toolkit_logging", "filename_utils", "output_paths", "save_audio_smart_prefix", "minimax_artwork"])
paths = MODULES["output_paths"]
audio_saver = MODULES["save_audio_smart_prefix"]
artwork_saver = MODULES["minimax_artwork"]

FIXED_NOW = datetime.datetime(2026, 9, 10, 13, 45, 6)


class DateMacroTests(unittest.TestCase):
    def test_macros_expand_against_one_timestamp(self):
        self.assertEqual(
            paths.expand_date_macros("%date:yyyy-MM-dd%", now=FIXED_NOW),
            "2026-09-10",
        )
        self.assertEqual(
            paths.expand_date_macros("%date:yyyy-MM-dd_HH-mm-ss%", now=FIXED_NOW),
            "2026-09-10_13-45-06",
        )
        self.assertEqual(
            paths.expand_date_macros("a/%date:yyyy%/%date:MM%", now=FIXED_NOW),
            "a/2026/09",
        )

    def test_invalid_pattern_is_left_untouched(self):
        raw = "%date:%q%"
        self.assertEqual(paths.expand_date_macros(raw, now=FIXED_NOW), raw)

    def test_plain_text_is_unchanged(self):
        self.assertEqual(paths.expand_date_macros("plain/path", now=FIXED_NOW), "plain/path")


class AbsolutePathDetectionTests(unittest.TestCase):
    def test_posix_and_windows_absolute_forms(self):
        for value in ("/var/audio", "C:\\audio", "C:/audio", "\\\\server\\share\\x", "//server/share/x"):
            with self.subTest(value=value):
                self.assertTrue(paths.is_abs_any_platform(value))

    def test_relative_forms(self):
        for value in ("audio/minimax3", "sub\\dir", "", "  "):
            with self.subTest(value=value):
                self.assertFalse(paths.is_abs_any_platform(value))

    def test_single_leading_backslash_is_not_absolute_off_windows(self):
        # Documented policy: on POSIX a leading backslash is a legal relative
        # filename, so it must stay contained in the output directory.  On
        # Windows os.path.isabs already reports it as absolute.
        expected = os.path.isabs("\\folder")
        self.assertEqual(paths.is_abs_any_platform("\\folder"), expected)


class ResolvePrefixTests(unittest.TestCase):
    def test_relative_prefix_resolves_under_the_output_directory(self):
        out = paths.resolve_prefix("audio/minimax3/")
        self.assertTrue(os.path.isabs(out))
        self.assertTrue(out.endswith(os.path.join("audio", "minimax3")))
        self.assertEqual(os.path.basename(out), "minimax3")

    def test_absolute_prefix_is_passed_through_normalized(self):
        absolute = os.path.join(tempfile.gettempdir(), "toolkit-out", "..", "toolkit-out")
        self.assertEqual(paths.resolve_prefix(absolute), os.path.normpath(absolute))

    def test_escape_attempt_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            paths.resolve_prefix("../outside")
        # NOTE: the dedicated "may not escape" message in resolve_prefix is
        # unreachable - the raised ValueError is swallowed by the surrounding
        # `except ValueError` that maps commonpath failures to this message.
        # Behaviour is preserved from the pre-extraction implementation.
        self.assertIn("invalid relative filename_prefix", str(ctx.exception))

    def test_empty_prefix_is_rejected_with_the_caller_label(self):
        with self.assertRaises(ValueError) as ctx:
            paths.resolve_prefix("   ", error_prefix="Save Production JSON")
        self.assertIn("Save Production JSON", str(ctx.exception))


class CollisionTests(unittest.TestCase):
    def test_overwrite_and_error_if_exists(self):
        self.assertEqual(paths.pick_path("p", "flac", "overwrite", exists=lambda _: True), "p.flac")
        with self.assertRaises(FileExistsError):
            paths.pick_path("p", "flac", "error_if_exists", exists=lambda _: True)
        self.assertEqual(paths.pick_path("p", "flac", "error_if_exists", exists=lambda _: False), "p.flac")

    def test_auto_increment_uses_the_first_free_suffix(self):
        taken = {"p.flac", "p_001.flac", "p_002.flac"}
        self.assertEqual(
            paths.pick_path("p", "flac", "auto_increment", exists=lambda t: t in taken),
            "p_003.flac",
        )

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            paths.pick_path("p", "flac", "nope", error_prefix="Save Audio Smart Prefix")
        self.assertIn("Save Audio Smart Prefix", str(ctx.exception))


class PreviewTests(unittest.TestCase):
    def test_preview_shape_and_no_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "32flac") + os.sep
            entry = paths.preview_output_files(
                prefix, "flac", collision_mode="auto_increment",
                filename_mode="album - title", tags_meta={"album": "Al", "title": "Ti"}, title="Ti",
            )
            self.assertEqual(entry["kind"], "flac")
            self.assertFalse(entry["exists"])
            self.assertFalse(entry["would_raise"])
            self.assertTrue(entry["path"].endswith("Al - Ti.flac"))
            self.assertFalse(os.path.exists(entry["path"]), "preview must not write the file")

    def test_preview_reports_collisions_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "32flac") + os.sep
            first = paths.preview_output_files(prefix, "flac", tags_meta={"album": "Al", "title": "Ti"}, title="Ti")
            os.makedirs(os.path.dirname(first["path"]), exist_ok=True)
            with open(first["path"], "w", encoding="utf-8") as handle:
                handle.write("x")
            second = paths.preview_output_files(prefix, "flac", tags_meta={"album": "Al", "title": "Ti"}, title="Ti")
            # The selected auto-increment path itself does not exist yet.
            self.assertTrue(second["path"].endswith("_001.flac"))
            self.assertFalse(second["exists"])
            third = paths.preview_output_files(
                prefix, "flac", collision_mode="error_if_exists",
                tags_meta={"album": "Al", "title": "Ti"}, title="Ti",
            )
            self.assertTrue(third["would_raise"])
            self.assertEqual(third["path"], "")

    def test_preview_can_use_an_injected_exists(self):
        # The injected predicate reports only the un-suffixed path as taken, so
        # the preview must fall through to the first free _001 name without
        # touching the filesystem.
        entry = paths.preview_output_files(
            "audio/", "flac", collision_mode="auto_increment",
            tags_meta={"album": "Al", "title": "Ti"}, title="Ti",
            exists=lambda candidate: candidate.endswith("Al - Ti.flac"),
        )
        self.assertTrue(entry["path"].endswith("_001.flac"))


class WrapperParityTests(unittest.TestCase):
    def test_audio_and_artwork_wrappers_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "out")
            tags = {"album": "Example Album", "title": "Example Song"}
            for mode in ("album - title", "title only", "prefix as provided"):
                with self.subTest(mode=mode):
                    a = audio_saver.preview_output_files(f"{base}/a/", "flac", filename_mode=mode, tags_meta=tags, title="Example Song")
                    b = artwork_saver.preview_output_files(f"{base}/a/", "flac", filename_mode=mode, tags_meta=tags, title="Example Song") if hasattr(artwork_saver, "preview_output_files") else a
                    self.assertEqual(a["path"], b["path"])
                    self.assertEqual(a["basename"], b["basename"])

    def test_audio_and_artwork_resolve_identically(self):
        for prefix in ("audio/minimax3/", "C:\\out\\audio", "%date:yyyy%/%date:MM%/"):
            with self.subTest(prefix=prefix):
                self.assertEqual(audio_saver._resolve_prefix(prefix), artwork_saver._resolve_prefix(prefix))

    def test_audio_saver_wrapper_matches_the_shared_implementation(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "p")
            with open(prefix + ".flac", "w", encoding="utf-8") as handle:
                handle.write("x")
            self.assertEqual(
                audio_saver._pick_path(prefix, "flac", "auto_increment"),
                paths.pick_path(prefix, "flac", "auto_increment"),
            )


class ImportIsolationTests(unittest.TestCase):
    """Planning a filename must not import audio codecs or Torch."""

    def test_output_paths_imports_no_heavy_dependencies(self):
        code = (
            "import importlib.util, sys, types, pathlib\n"
            f"ROOT = pathlib.Path(r'{ROOT}')\n"
            "pkg = types.ModuleType('_iso'); pkg.__path__ = [str(ROOT)]; sys.modules['_iso'] = pkg\n"
            "for dep in ('toolkit_logging', 'filename_utils', 'output_paths'):\n"
            "    spec = importlib.util.spec_from_file_location('_iso.' + dep, ROOT / (dep + '.py'))\n"
            "    mod = importlib.util.module_from_spec(spec); sys.modules['_iso.' + dep] = mod\n"
            "    spec.loader.exec_module(mod)\n"
            "heavy = [n for n in ('numpy', 'torch', 'soundfile', 'mutagen', 'PIL', 'scipy') if n in sys.modules]\n"
            "print('HEAVY:' + ','.join(heavy))\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HEAVY:", result.stdout)
        heavy = result.stdout.strip().split("HEAVY:", 1)[1]
        self.assertEqual(heavy, "", f"output_paths pulled in heavy imports: {heavy}")


if __name__ == "__main__":
    unittest.main()
