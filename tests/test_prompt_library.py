from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_prompt_library():
    pkg_name = "_toolkit_prompt_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    for module_name in ("toolkit_logging", "prompt_library"):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return sys.modules[f"{pkg_name}.prompt_library"]


class PromptLibraryTests(unittest.TestCase):
    def test_bundled_library_contains_examples(self):
        pl = load_prompt_library()
        files = pl.list_prompt_files("user", "bundled_library")
        self.assertGreaterEqual(len(files), 30)
        self.assertIn("folk/nordic-folk-vocal.txt", files)
        self.assertIn("minimax-music3-production.txt", pl.list_prompt_files("system", "bundled_library"))

    def test_external_directory_and_utf8(self):
        pl = load_prompt_library()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "genre").mkdir()
            (root / "genre" / "one.txt").write_text("A useful prompt äöü", encoding="utf-8")
            (root / "ignore.bin").write_bytes(b"no")
            self.assertEqual(pl.list_prompt_files("user", "external_directory", str(root)), ["genre/one.txt"])
            text, rel = pl.load_prompt_file("user", "external_directory", str(root), "genre/one.txt")
            self.assertEqual(rel, "genre/one.txt")
            self.assertIn("äöü", text)

    def test_path_traversal_is_rejected(self):
        pl = load_prompt_library()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / "library"
            root.mkdir()
            (base / "outside.txt").write_text("secret", encoding="utf-8")
            with self.assertRaises(pl.PromptLibraryError):
                pl.load_prompt_file("user", "external_directory", str(root), "../outside.txt")

    def test_content_fingerprint_changes_after_edit(self):
        pl = load_prompt_library()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "prompt.txt"
            path.write_text("first", encoding="utf-8")
            a = pl.prompt_selection_fingerprint("user", "external_directory", str(root), "prompt.txt")
            path.write_text("second", encoding="utf-8")
            b = pl.prompt_selection_fingerprint("user", "external_directory", str(root), "prompt.txt")
            self.assertNotEqual(a, b)


class CustomPromptSaveTests(unittest.TestCase):
    """The structured prompt node saves its values into the library's _custom/ folder."""

    def setUp(self):
        self.pl = load_prompt_library()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _save(self, filename, fields=None, description="My description.", overwrite=False):
        return self.pl.save_custom_prompt(
            "external_directory", str(self.root), filename,
            fields or {}, description, overwrite,
        )

    def test_saves_metadata_block_and_description(self):
        relative = self._save("my-house", {"genre": "House", "length": "4-5 minutes", "lyrics": "custom"})
        self.assertEqual(relative, "_custom/my-house.txt")
        target = self.root / "_custom" / "my-house.txt"
        self.assertTrue(target.is_file())
        text = target.read_text(encoding="utf-8")
        self.assertIn("Genre: House", text)
        self.assertIn("Length: 4-5 minutes", text)
        self.assertNotIn("Lyrics", text)  # custom values are omitted
        self.assertTrue(text.endswith("My description.\n"))
        # The new file appears in the library listing.
        files = self.pl.list_prompt_files("user", "external_directory", str(self.root))
        self.assertIn("_custom/my-house.txt", files)

    def test_overwrite_is_refused_by_default(self):
        self._save("dup")
        with self.assertRaises(self.pl.PromptLibraryError):
            self._save("dup")
        # overwrite=True replaces the file.
        relative = self._save("dup", description="New text.", overwrite=True)
        self.assertEqual(relative, "_custom/dup.txt")
        self.assertIn("New text.", (self.root / "_custom" / "dup.txt").read_text(encoding="utf-8"))

    def test_invalid_names_are_rejected(self):
        for bad in ("", "../evil", "sub/dir", ".", ".."):
            with self.assertRaises((self.pl.PromptLibraryError, ValueError)):
                self._save(bad)

    def test_name_is_sanitized(self):
        relative = self._save("my house: one.txt")
        self.assertEqual(relative, "_custom/my house_ one.txt")
        # Windows-reserved device names are neutralized instead of failing.
        reserved = self._save("CON")
        self.assertEqual(reserved, "_custom/CON_.txt")


if __name__ == "__main__":
    unittest.main()
