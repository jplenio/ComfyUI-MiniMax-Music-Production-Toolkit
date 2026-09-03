from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_demo_catalog.py"

spec = importlib.util.spec_from_file_location("update_demo_catalog", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class DemoCatalogTests(unittest.TestCase):
    def test_public_catalog_is_valid_and_covers_exist(self):
        text = (ROOT / "docs" / "demo-tracks.js").read_text(encoding="utf-8")
        config, tracks = module._read_demo_js(ROOT / "docs" / "demo-tracks.js")
        self.assertGreaterEqual(len(tracks), 25)
        self.assertEqual(len({t["id"] for t in tracks}), len(tracks))
        self.assertEqual(len({t["showcaseOrder"] for t in tracks}), len(tracks))
        for track in tracks:
            self.assertTrue((ROOT / "docs" / track["cover"]).is_file(), track["cover"])
            url = track.get("soundcloudUrl", "")
            if url:
                self.assertRegex(url, r"^https://(?:www\.)?soundcloud\.com/")
        playlist = config.get("soundcloudPlaylistUrl", "")
        if playlist:
            self.assertRegex(playlist, r"^https://(?:www\.)?soundcloud\.com/")

    def test_track_type_distinguishes_instrumental_and_vocal(self):
        self.assertEqual(module._track_type("[Intro]\n[Instrumental]\n[Outro]"), "Instrumental")
        self.assertEqual(module._track_type("[Intro]\ncarry me through\n[Outro]"), "Vocal")

    def test_humanize_common_prompt_slugs(self):
        self.assertEqual(module._humanize_slug("future-rave-sparse-vocals"), "Future Rave Sparse Vocals")
        self.assertEqual(module._genre_for_public("future-rave-sparse-vocals", "Future Rave / Festival Electronic"), "Future Rave")

    def test_writer_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "demo-tracks.js"
            config = {"soundcloudPlaylistUrl": "https://soundcloud.com/pelenio/sets/example"}
            tracks = [{"id": "a", "showcaseOrder": 1, "title": "A", "album": "X", "seed": 1}]
            module._write_demo_js(path, config, tracks)
            new_config, new_tracks = module._read_demo_js(path)
            self.assertEqual(new_config, config)
            self.assertEqual(new_tracks, tracks)


if __name__ == "__main__":
    unittest.main()
