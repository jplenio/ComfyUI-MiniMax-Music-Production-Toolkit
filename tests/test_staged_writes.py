"""Staged publication tests (F14 / T10).

Verifies the single invariant that matters for the savers: a failed operation
must not leave a file at the final path, must not leave staging leftovers, and
must not overwrite an artifact another producer created in the meantime.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PKG = "_staged_writes_test"
if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg

MODULES = {}
for _name in ("toolkit_logging", "filename_utils", "output_paths", "file_writes"):
    _full = f"{PKG}.{_name}"
    _spec = importlib.util.spec_from_file_location(_full, ROOT / f"{_name}.py")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_full] = _module
    assert _spec.loader is not None
    _spec.loader.exec_module(_module)
    MODULES[_name] = _module

writes = MODULES["file_writes"]


def _staging_leftovers(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if ".part-" in p.name)


class StagedWriteTests(unittest.TestCase):
    def test_successful_write_publishes_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "Album - Title.flac")
            with writes.staged_write(target) as staged:
                self.assertNotEqual(staged.staging, target)
                self.assertTrue(staged.staging.endswith(".flac"), "staging keeps the extension")
                Path(staged.staging).write_bytes(b"audio")
            self.assertEqual(staged.target, target)
            self.assertEqual(Path(target).read_bytes(), b"audio")
            self.assertEqual(_staging_leftovers(Path(tmp)), [])

    def test_failure_leaves_no_final_file_and_no_leftovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "Album - Title.flac")
            with self.assertRaises(RuntimeError):
                with writes.staged_write(target) as staged:
                    Path(staged.staging).write_bytes(b"partial")
                    raise RuntimeError("encoder failed")
            self.assertFalse(os.path.exists(target), "a failed write must not publish")
            self.assertEqual(_staging_leftovers(Path(tmp)), [], "staging must be cleaned up")

    def test_failure_does_not_touch_an_existing_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "Album - Title.flac")
            Path(target).write_bytes(b"previous release")
            with self.assertRaises(ValueError):
                with writes.staged_write(target) as staged:
                    Path(staged.staging).write_bytes(b"broken")
                    raise ValueError("tagging failed")
            self.assertEqual(Path(target).read_bytes(), b"previous release")
            self.assertEqual(_staging_leftovers(Path(tmp)), [])

    def test_publish_failure_is_cleaned_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            # The target directory is replaced by a file, so os.replace fails.
            blocked = os.path.join(tmp, "blocked")
            Path(blocked).write_bytes(b"x")
            target = os.path.join(blocked, "Album - Title.flac")
            with self.assertRaises(OSError):
                with writes.staged_write(target):
                    pass
            self.assertEqual(Path(blocked).read_bytes(), b"x")

    def test_reserve_moves_to_the_next_free_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "Album - Title")
            target = f"{prefix}.flac"
            with writes.staged_write(
                target,
                reserve=lambda: writes.reserve_target(prefix, "flac", "auto_increment"),
            ) as staged:
                Path(staged.staging).write_bytes(b"first")
                # Another producer takes the name while we are "encoding".
                Path(target).write_bytes(b"someone else")
            self.assertEqual(Path(target).read_bytes(), b"someone else", "must not overwrite")
            self.assertEqual(Path(staged.target).name, "Album - Title_001.flac")
            self.assertEqual(Path(staged.target).read_bytes(), b"first")

    def test_reserve_raises_for_error_if_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "Album - Title")
            target = f"{prefix}.flac"
            Path(target).write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                with writes.staged_write(
                    target,
                    reserve=lambda: writes.reserve_target(prefix, "flac", "error_if_exists"),
                ) as staged:
                    Path(staged.staging).write_bytes(b"x")
            self.assertEqual(_staging_leftovers(Path(tmp)), [])

    def test_overwrite_keeps_the_requested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "Album - Title")
            target = f"{prefix}.flac"
            Path(target).write_bytes(b"old")
            with writes.staged_write(
                target, reserve=lambda: writes.reserve_target(prefix, "flac", "overwrite")
            ) as staged:
                Path(staged.staging).write_bytes(b"new")
            self.assertEqual(Path(target).read_bytes(), b"new")

    def test_write_text_staged_is_utf8_with_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "Album - Title.md")
            published = writes.write_text_staged(target, "Zeile 1\nZeile 2\n")
            self.assertEqual(published, target)
            self.assertEqual(Path(target).read_text(encoding="utf-8"), "Zeile 1\nZeile 2\n")
            self.assertEqual(_staging_leftovers(Path(tmp)), [])

    def test_staging_names_are_unique_within_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "x.flac")
            seen = set()
            for _ in range(5):
                with writes.staged_write(target) as staged:
                    seen.add(staged.staging)
                    Path(staged.staging).write_bytes(b"a")
            self.assertEqual(len(seen), 5)


if __name__ == "__main__":
    unittest.main()
