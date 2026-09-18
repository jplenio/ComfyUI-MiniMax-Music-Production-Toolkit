"""The cover-song demo section: catalog, artwork and the wiring in the page.

The generated-song catalog has its own test file (``test_demo_catalog.py``). This one
covers the second category on the same page: an original track with the covers made
from it underneath, fed by ``docs/demo-covers.js``.

The checks are deliberately static. They cannot prove how the page looks in a browser —
that needs Playwright, which is optional here — but they do catch the two mistakes this
section is actually prone to: a catalog that points at an image nobody prepared, and a
script that asks for an element id the page does not have.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "demo-covers.js"
PAGE = ROOT / "docs" / "index.html"
SCRIPT = ROOT / "scripts" / "update_cover_demo_catalog.py"

spec = importlib.util.spec_from_file_location("update_cover_demo_catalog", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def read_groups() -> list[dict]:
    text = CATALOG.read_text(encoding="utf-8")
    match = re.search(r"window\.DEMO_COVER_GROUPS\s*=\s*(\[.*\]);\s*$", text, re.S)
    if not match:
        raise AssertionError("docs/demo-covers.js does not assign window.DEMO_COVER_GROUPS")
    return json.loads(match.group(1))


class CoverCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.groups = read_groups()
        cls.covers = [cover for group in cls.groups for cover in group.get("covers", [])]

    def test_every_group_has_covers_and_identifies_its_original(self):
        self.assertTrue(self.groups, "the cover catalog is empty")
        for group in self.groups:
            with self.subTest(group=group.get("id")):
                self.assertTrue(group.get("title"), "an original needs a title")
                self.assertTrue(group.get("sourceFile"), "an original needs its source file name")
                self.assertTrue(group.get("covers"), "an original without covers should not be listed")

    def test_ids_are_unique(self):
        group_ids = [group["id"] for group in self.groups]
        cover_ids = [cover["id"] for cover in self.covers]
        self.assertEqual(len(group_ids), len(set(group_ids)), "duplicate original id")
        self.assertEqual(len(cover_ids), len(set(cover_ids)), "duplicate cover id")

    def test_every_cover_has_the_fields_the_page_renders(self):
        for cover in self.covers:
            with self.subTest(cover=cover.get("id")):
                for key in ("id", "title", "variant", "model", "soundcloudUrl", "freedom"):
                    self.assertIn(key, cover, f"{cover.get('id')} lacks {key}")
                # Both of these are filled in by hand: the URL after uploading, the
                # freedom level because the production JSON does not record it. Either
                # may still be empty - but a value that is present has to be usable.
                url = cover["soundcloudUrl"]
                if url:
                    self.assertRegex(url, r"^https://(?:www\.)?soundcloud\.com/")
                freedom = cover["freedom"]
                if freedom != "":
                    self.assertTrue(str(freedom).isdigit() and 0 <= int(freedom) <= 100,
                                    f"{cover.get('id')}: freedom must be 0-100, got {freedom!r}")

    def test_every_cover_art_file_exists(self):
        for cover in self.covers:
            art = cover.get("coverArt")
            with self.subTest(cover=cover.get("id")):
                self.assertTrue(art, "cover art is missing from the catalog")
                self.assertTrue((ROOT / "docs" / art).is_file(), art)
                self.assertEqual(Path(art).parent.as_posix(), "assets/demo-covers")

    def test_soundcloud_urls_are_either_empty_or_normal_urls(self):
        urls = [group.get("soundcloudUrl", "") for group in self.groups]
        urls += [cover.get("soundcloudUrl", "") for cover in self.covers]
        for url in urls:
            if url:
                self.assertRegex(url, r"^https://(?:www\.)?soundcloud\.com/")

    def test_a_rebuild_keeps_hand_written_values(self):
        """Re-running the generator must not wipe URLs or comments typed in by hand."""
        previous = [{
            "id": self.groups[0]["id"],
            "soundcloudUrl": "https://soundcloud.com/pelenio/original",
            "comment": "my own words",
            "covers": [{"id": self.covers[0]["id"],
                        "soundcloudUrl": "https://soundcloud.com/pelenio/cover",
                        "freedom": 75}],
        }]
        merged = module.merge_hand_edits(json.loads(json.dumps(self.groups)), previous)
        self.assertEqual(merged[0]["soundcloudUrl"], "https://soundcloud.com/pelenio/original")
        self.assertEqual(merged[0]["comment"], "my own words")
        kept = next(c for c in merged[0]["covers"] if c["id"] == self.covers[0]["id"])
        self.assertEqual(kept["soundcloudUrl"], "https://soundcloud.com/pelenio/cover")
        self.assertEqual(kept["freedom"], 75)


class DemoPageWiringTests(unittest.TestCase):
    """The page's script asks for element ids; the markup must actually have them."""

    @classmethod
    def setUpClass(cls):
        cls.page = PAGE.read_text(encoding="utf-8")

    def test_every_requested_element_id_exists(self):
        requested = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", self.page))
        self.assertTrue(requested, "the page script requests no element ids at all?")
        present = set(re.findall(r"id=\"([^\"]+)\"", self.page))
        self.assertEqual(sorted(requested - present), [],
                         "the script asks for ids the page does not define")

    def test_the_second_catalog_is_loaded(self):
        self.assertIn('<script src="demo-tracks.js"></script>', self.page)
        self.assertIn('<script src="demo-covers.js"></script>', self.page)
        for name in ("demo-tracks.js", "demo-covers.js"):
            self.assertTrue((ROOT / "docs" / name).is_file(), name)

    def test_the_category_switch_can_show_both_sections(self):
        for element_id in ("section-songs", "section-covers", "categories"):
            self.assertIn(f'id="{element_id}"', self.page)
        self.assertIn("data-cat=\"songs\"", self.page)
        self.assertIn("data-cat=\"covers\"", self.page)
        self.assertRegex(self.page, r'id="section-covers"\s+hidden')

    def test_the_generator_is_the_documented_way_in(self):
        for name in ("docs/demo-covers.js", "docs/demo-tracks.js"):
            self.assertIn(name, module.__doc__ or "", f"{name} should be named in the docs")


class DemoPageScriptTests(unittest.TestCase):
    """The page's JavaScript must at least parse.

    A syntax error in the inline script or in one of the catalogs leaves a blank page
    with a console message, which no static check of the data would notice. Node is
    asked to parse the exact text that ships; on a machine without node the check
    reports a skip instead of guessing.
    """

    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")

    def _node_check(self, label, source):
        if not self.node:
            self.skipTest("node is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snippet.js"
            path.write_text(source, encoding="utf-8")
            proc = subprocess.run([self.node, "--check", str(path)],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace")
            self.assertEqual(proc.returncode, 0, f"{label} does not parse:\n{proc.stderr}")

    def test_the_inline_page_script_parses(self):
        page = PAGE.read_text(encoding="utf-8")
        blocks = re.findall(r"<script>(.*?)</script>", page, re.S)
        self.assertTrue(blocks, "index.html carries no inline script")
        for index, block in enumerate(blocks):
            with self.subTest(block=index):
                self._node_check(f"index.html inline script {index}", block)

    def test_both_catalogs_parse(self):
        for name in ("demo-tracks.js", "demo-covers.js"):
            with self.subTest(name=name):
                self._node_check(name, (ROOT / "docs" / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
