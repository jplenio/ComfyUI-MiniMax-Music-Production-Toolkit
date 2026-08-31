from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RepositoryMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_versions_are_consistent(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(self.data["project"]["version"], version)
        self.assertEqual(version, "1.0.0")

    def test_publisher_and_repository_are_configured(self):
        self.assertEqual(self.data["tool"]["comfy"]["PublisherId"], "jplenio")
        self.assertEqual(self.data["project"]["urls"]["Repository"], "https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit")


if __name__ == "__main__":
    unittest.main()
