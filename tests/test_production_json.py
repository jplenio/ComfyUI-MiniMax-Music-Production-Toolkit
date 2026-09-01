from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module(fullname: str, path: Path):
    spec = importlib.util.spec_from_file_location(fullname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ProductionJSONTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pkg = types.ModuleType("minimax_toolkit_testpkg")
        pkg.__path__ = [str(ROOT)]
        sys.modules[pkg.__name__] = pkg
        _load_module(f"{pkg.__name__}.toolkit_logging", ROOT / "toolkit_logging.py")
        _load_module(f"{pkg.__name__}.filename_utils", ROOT / "filename_utils.py")
        _load_module(f"{pkg.__name__}.save_audio_smart_prefix", ROOT / "save_audio_smart_prefix.py")
        cls.mod = _load_module(f"{pkg.__name__}.minimax_json_output", ROOT / "minimax_json_output.py")

    def test_canonical_json_is_written_and_contains_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artwork = root / "cover.jpg"
            artwork.write_bytes(b"demo")
            prefix = root / "json" / "source"

            node = self.mod.MiniMaxSaveProductionJSON()
            saved_path, rendered = node.save(
                metadata_json=json.dumps({"schema": "test", "title": "Track"}),
                configuration_prefix=str(prefix),
                audio_tags_json=json.dumps({"album": "Album", "title": "Track", "artist": "Artist"}),
                title="Track",
                original_audio_save_json=json.dumps({"path": str(root / "original.flac"), "format": "flac"}),
                release_flac_save_json=json.dumps({"path": str(root / "release.flac"), "format": "flac"}),
                release_mp3_save_json=json.dumps({"path": str(root / "release.mp3"), "format": "mp3"}),
                artwork_path=str(artwork),
                collision_mode="auto_increment",
                filename_mode="album - title",
                create_directories=True,
            )

            saved = Path(saved_path)
            self.assertTrue(saved.exists())
            self.assertEqual(saved.name, "Album - Track.json")
            data = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual(data["standard_audio_tags"]["album"], "Album")
            self.assertEqual(data["outputs"]["release_mp3"]["format"], "mp3")
            self.assertEqual(Path(data["outputs"]["artwork"]["path"]), artwork.resolve())
            self.assertEqual(json.loads(rendered)["outputs"]["configuration"]["file"], "Album - Track.json")


if __name__ == "__main__":
    unittest.main()
