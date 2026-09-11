"""Tag/cover extraction tests (F15 / T13).

The point of the extraction is that one production run decodes the cover once
instead of once per file, without changing the produced JPEG or the tag
mapping.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = "_audio_tags_test"
if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg

MODULES = {}
for _name in ("toolkit_logging", "filename_utils", "output_paths", "file_writes",
              "audio_tags", "save_audio_smart_prefix"):
    _full = f"{PKG}.{_name}"
    _spec = importlib.util.spec_from_file_location(_full, ROOT / f"{_name}.py")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_full] = _module
    assert _spec.loader is not None
    _spec.loader.exec_module(_module)
    MODULES[_name] = _module

tags_module = MODULES["audio_tags"]
saver = MODULES["save_audio_smart_prefix"]

try:
    from PIL import Image
except Exception:  # pragma: no cover - Pillow ships with the toolkit requirements
    Image = None


def _write_cover(directory: Path, size=(2048, 2048), colour=(200, 40, 90)) -> Path:
    path = directory / "cover.jpg"
    Image.new("RGB", size, colour).save(path, format="JPEG", quality=95)
    return path


@unittest.skipIf(Image is None, "Pillow is required for cover handling")
class CoverEncodingTests(unittest.TestCase):
    def test_square_cover_is_resized_to_the_requested_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            cover = _write_cover(Path(tmp), (2048, 2048))
            data = tags_module._load_cover_bytes(str(cover), target_side=512)
            with Image.open(BytesIO(data)) as embedded:
                self.assertEqual(embedded.size, (512, 512))
                self.assertEqual(embedded.format, "JPEG")

    def test_non_square_cover_is_thumbnail_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            cover = _write_cover(Path(tmp), (1600, 800))
            data = tags_module._load_cover_bytes(str(cover), target_side=400)
            with Image.open(BytesIO(data)) as embedded:
                self.assertLessEqual(max(embedded.size), 400)
                self.assertGreater(embedded.width, embedded.height)

    def test_cover_side_is_clamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            cover = _write_cover(Path(tmp), (1024, 1024))
            data = tags_module._load_cover_bytes(str(cover), target_side=8)
            with Image.open(BytesIO(data)) as embedded:
                self.assertEqual(embedded.size, (64, 64))

    def test_empty_path_returns_no_bytes(self):
        self.assertEqual(tags_module._load_cover_bytes(""), b"")

    def test_missing_cover_raises_with_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.jpg"
            with self.assertRaises(FileNotFoundError) as ctx:
                tags_module._load_cover_bytes(str(missing))
            self.assertIn("cover image not found", str(ctx.exception))


@unittest.skipIf(Image is None, "Pillow is required for cover handling")
class CoverCacheTests(unittest.TestCase):
    def test_same_cover_is_decoded_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            cover = _write_cover(Path(tmp))
            cache = tags_module.CoverCache()
            results = [cache.get(str(cover), 512) for _ in range(5)]
            self.assertEqual(cache.misses, 1, "one decode per (path, size) and invocation")
            self.assertTrue(all(r == results[0] for r in results))

    def test_different_sizes_are_separate_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            cover = _write_cover(Path(tmp))
            cache = tags_module.CoverCache()
            cache.get(str(cover), 512)
            cache.get(str(cover), 256)
            cache.get(str(cover), 512)
            self.assertEqual(cache.misses, 2)

    def test_caches_do_not_share_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            cover = _write_cover(Path(tmp))
            first = tags_module.CoverCache()
            second = tags_module.CoverCache()
            first.get(str(cover), 512)
            second.get(str(cover), 512)
            self.assertEqual((first.misses, second.misses), (1, 1))

    def test_tag_writer_reuses_a_supplied_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cover = _write_cover(Path(tmp))
            cache = tags_module.CoverCache()
            if tags_module.FLAC is None:
                self.skipTest("mutagen is not installed in this interpreter")
            import soundfile as sf
            import numpy as np

            data = np.zeros((256, 2), dtype="float32")
            for index in range(3):
                target = os.path.join(tmp, f"track{index}.flac")
                sf.write(target, data, 44100, format="FLAC", subtype="PCM_16")
                tags_module._write_standard_tags(
                    target, "flac", {"title": f"Track {index}", "album": "Album"},
                    str(cover), 512, cover_cache=cache,
                )
            self.assertEqual(cache.misses, 1, "the cover must be encoded once per save invocation")


class WrapperParityTests(unittest.TestCase):
    @unittest.skipIf(Image is None, "Pillow is required for cover handling")
    def test_saver_wrapper_matches_the_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            cover = _write_cover(Path(tmp))
            self.assertEqual(
                saver._load_cover_bytes(str(cover), 512),
                tags_module._load_cover_bytes(str(cover), 512),
            )

    def test_empty_tags_are_a_no_op_without_mutagen(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "x.flac")
            Path(target).write_bytes(b"not audio")
            # An empty tag mapping must return before touching mutagen.
            self.assertIsNone(saver._write_standard_tags(target, "flac", {}))

    def test_missing_mutagen_is_reported_clearly(self):
        if tags_module.FLAC is not None:
            self.skipTest("mutagen is installed; the guard is not exercised")
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "x.flac")
            Path(target).write_bytes(b"not audio")
            with self.assertRaises(RuntimeError) as ctx:
                tags_module._write_standard_tags(target, "flac", {"title": "T"})
            self.assertIn("requires mutagen", str(ctx.exception))

    def test_cover_cache_parameter_is_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "x.flac")
            Path(target).write_bytes(b"not audio")
            # No cache supplied: the call must still work (and simply not cache).
            self.assertIsNone(saver._write_standard_tags(target, "flac", {}, cover_cache=None))


if __name__ == "__main__":
    unittest.main()
