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


if __name__ == "__main__":
    unittest.main()
