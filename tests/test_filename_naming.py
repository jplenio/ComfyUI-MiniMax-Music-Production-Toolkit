from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_filename_utils():
    spec = importlib.util.spec_from_file_location("_minimax_filename_utils_test", ROOT / "filename_utils.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FilenameNamingTests(unittest.TestCase):
    def test_album_title_replaces_prompt_source_basename(self):
        mod = load_filename_utils()
        out = mod.apply_filename_mode(
            "artwork/nordic-folk-vocal",
            {"album": "Example Album", "title": "Last Wick"},
            "Last Wick",
            "album - title",
        )
        self.assertEqual(out.replace("\\", "/"), "artwork/Example Album - Last Wick")

    def test_audio_artwork_json_share_portable_sanitization(self):
        mod = load_filename_utils()
        prefix = "out/source"
        tags = {"album": "Album: One", "title": "Song / Two?"}
        names = [mod.apply_filename_mode(prefix, tags, tags["title"], "album - title") for _ in range(3)]
        self.assertEqual(names[0], names[1])
        self.assertEqual(names[1], names[2])
        self.assertTrue(names[0].endswith("Album_ One - Song _ Two_"))


if __name__ == "__main__":
    unittest.main()
