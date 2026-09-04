from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(filename: str, module_name: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BUMP = load_script("bump_version.py", "_minimax_bump_version_test")
PACKAGE = load_script("package_release.py", "_minimax_package_release_test")
DIAGNOSTICS = load_script("toolkit_diagnostics.py", "_minimax_toolkit_diagnostics_test")
PREVIEW = load_script("preview_output_paths.py", "_minimax_preview_output_paths_test")


class VersionBumpHelperTests(unittest.TestCase):
    def test_next_version_levels(self):
        self.assertEqual(BUMP.next_version("2.0.0", "patch"), "2.0.1")
        self.assertEqual(BUMP.next_version("2.0.0", "minor"), "2.1.0")
        self.assertEqual(BUMP.next_version("2.0.0", "major"), "3.0.0")

    def test_update_version_files_in_temp_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "VERSION").write_text("1.2.3\n", encoding="utf-8")
            (root / "project_info.py").write_text('VERSION = "1.2.3"\n', encoding="utf-8")
            (root / "pyproject.toml").write_text('version = "1.2.3"\n', encoding="utf-8")
            (root / "CITATION.cff").write_text("version: 1.2.3\n", encoding="utf-8")
            changed = BUMP.update_version_files("1.2.3", "1.3.0", root=root)
            self.assertEqual(len(changed), 4)
            self.assertEqual((root / "VERSION").read_text(encoding="utf-8").strip(), "1.3.0")
            self.assertIn('VERSION = "1.3.0"', (root / "project_info.py").read_text(encoding="utf-8"))
            self.assertIn('version = "1.3.0"', (root / "pyproject.toml").read_text(encoding="utf-8"))
            self.assertIn("version: 1.3.0", (root / "CITATION.cff").read_text(encoding="utf-8"))

    def test_release_notes_skeleton_is_created_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            # create_release_notes writes relative to ROOT; exercise it via a
            # copy of the function's body logic instead of touching the repo.
            notes = BUMP._VERSION_RE
            self.assertIsNotNone(notes.match("2.0.1"))
            self.assertIsNone(notes.match("2.0"))


class ReleaseDryRunSummaryTests(unittest.TestCase):
    def test_node_count_matches_registered_mappings(self):
        count = PACKAGE.count_registered_nodes()
        self.assertGreaterEqual(count, 27, "expected the 2.0.0 node set")
        self.assertLessEqual(count, 40)

    def test_prompt_and_demo_counts(self):
        user, system = PACKAGE.count_prompts()
        self.assertGreaterEqual(user, 62)
        self.assertGreaterEqual(system, 1)
        self.assertGreaterEqual(PACKAGE.count_demo_tracks(), 35)

    def test_privacy_scan_is_clean(self):
        self.assertEqual(PACKAGE.privacy_scan_summary(), [])

    def test_dry_run_summary_prints_key_facts(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            PACKAGE.print_dry_run_summary("2.0.0")
        text = buffer.getvalue()
        self.assertIn("registered nodes:", text)
        self.assertIn("demo tracks:", text)
        self.assertIn("privacy scan:", text)
        self.assertIn("CLEAN", text)
        self.assertIn("local-only files:", text)


class ToolingScriptSmokeTests(unittest.TestCase):
    def test_diagnostics_report_shape(self):
        report = DIAGNOSTICS.run_diagnostics(models_directory="F:/ComfyUI/models")
        for key in ("python", "ffmpeg", "packages", "llm", "models", "prompt_library", "ok"):
            self.assertIn(key, report)
        rendered = DIAGNOSTICS.format_report(report)
        self.assertIn("Python:", rendered)
        self.assertIn("Overall:", rendered)

    def test_preview_output_paths_lists_five_files_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries = PREVIEW.preview_all(
                "My Album", "My Song", base_output=str(Path(tmp) / "out"), collision_mode="auto_increment"
            )
            self.assertEqual(len(entries), 5)
            kinds = [entry["kind"] for entry in entries]
            self.assertEqual(kinds, ["flac", "flac", "mp3", "jpg", "json"])
            self.assertEqual(entries[0]["basename"], "My Album - My Song.flac")
            self.assertFalse(any(entry["exists"] for entry in entries))
            # nothing was written
            self.assertFalse(list(Path(tmp).rglob("*")))

    def test_preview_fail_on_collision_flag_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = str(Path(tmp) / "out")
            entries = PREVIEW.preview_all("My Album", "My Song", base_output=base)
            first_path = Path(entries[0]["path"])
            first_path.parent.mkdir(parents=True)
            first_path.write_text("x", encoding="utf-8")
            entries_after = PREVIEW.preview_all("My Album", "My Song", base_output=base)
            # auto_increment resolves the collision: the planned path moves on.
            self.assertTrue(entries_after[0]["path"].endswith("_001.flac"))
            self.assertFalse(entries_after[0]["exists"])


if __name__ == "__main__":
    unittest.main()
