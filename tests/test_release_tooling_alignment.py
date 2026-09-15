"""Release-tooling alignment tests (F23 / T29)."""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))
import release_common  # noqa: E402


def load_script(filename: str, module_name: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PACKAGE = load_script("package_release.py", "_t29_package_release")
VALIDATE = load_script("validate_release.py", "_t29_validate_release")
DEMO = load_script("update_demo_catalog.py", "_t29_update_demo_catalog")


class ArchiveSelectionTests(unittest.TestCase):
    def test_dry_run_without_local_planning_documents(self):
        # A GitHub checkout has none of the maintainer's untracked handoff files.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / "workflow.json"
            workflow.write_text('{"nodes": [], "links": []}', encoding="utf-8")
            buffer = io.StringIO()
            with patch.object(PACKAGE, "ROOT", root), patch.object(PACKAGE, "WORKFLOW_SOURCE", workflow), redirect_stdout(buffer):
                PACKAGE.print_dry_run_summary("2.5.0")
            self.assertIn("local-only files: none", buffer.getvalue())

    def test_frontend_parity_uses_validator_python(self):
        # The nested Node test must not pick a different, dependency-free Python.
        from types import SimpleNamespace
        with patch("shutil.which", return_value="node"), patch("subprocess.run", return_value=SimpleNamespace(returncode=0)) as run:
            VALIDATE.check_migration_logic()
        parity = [call for call in run.call_args_list if "test_audio_eq_frontend.mjs" in str(call.args[0])]
        self.assertEqual(len(parity), 1)
        self.assertEqual(parity[0].kwargs["env"]["PYTHON"], sys.executable)

    def test_generated_release_assets_are_excluded(self):
        for relative in (
            "dist/SHA256SUMS.txt",
            "dist/MiniMax_Music3_Production_Toolkit_v2.1.1.json",
            "dist/ComfyUI-MiniMax-Music-Production-Toolkit-v2.1.1.zip",
        ):
            with self.subTest(relative=relative):
                self.assertFalse(release_common.archive_should_include(ROOT, ROOT / relative))

    def test_vcs_caches_and_local_only_files_are_excluded(self):
        for relative in (
            ".git/config",
            "__pycache__/x.pyc",
            "scripts/__pycache__/x.pyc",
            ".scratch/native_stage_base/test.json",
            ".scratch/workflow_before_26.json",
            "KONTEXT.md",
            "PROJECT_STATE.md",
            "REFACTOR-PLAN.md",
            "nested/thing.zip",
        ):
            with self.subTest(relative=relative):
                self.assertFalse(release_common.archive_should_include(ROOT, ROOT / relative))

    def test_runtime_files_are_included(self):
        for relative in (
            "__init__.py",
            "web/structured_prompt.js",
            "example_workflows/MiniMax_Music3_Production_Toolkit.json",
            "prompts/system/minimax-music3-production.txt",
        ):
            with self.subTest(relative=relative):
                self.assertTrue(release_common.archive_should_include(ROOT, ROOT / relative))

    def test_packager_uses_the_shared_rule(self):
        self.assertFalse(PACKAGE.should_include(ROOT / "dist" / "MiniMax_Music3_Production_Toolkit_v2.1.1.json"))
        self.assertTrue(PACKAGE.should_include(ROOT / "__init__.py"))
        self.assertIn("dist", PACKAGE.EXCLUDED_PARTS)

    def test_dry_run_summary_reports_no_generated_assets(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            PACKAGE.print_dry_run_summary("2.1.1")
        output = buffer.getvalue()
        self.assertIn("files in zip:", output)
        # Derived from the shared rule so adding an excluded document cannot
        # leave this guard silently stale while still asserting the intent:
        # every packaging-excluded maintainer document must be listed.
        present = sorted(name for name in release_common.PACKAGING_EXCLUDED_NAMES if (ROOT / name).exists())
        expected = ", ".join(present) or "none"
        self.assertIn(f"local-only files: {expected}", output)
        for name in present:
            with self.subTest(document=name):
                self.assertIn(name, output)


class PrivacyScanTests(unittest.TestCase):
    def test_patterns_are_shared_between_packager_and_validator(self):
        packager = (ROOT / "scripts" / "package_release.py").read_text(encoding="utf-8")
        validator = (ROOT / "scripts" / "validate_release.py").read_text(encoding="utf-8")
        for name, source in (("package_release.py", packager), ("validate_release.py", validator)):
            with self.subTest(script=name):
                self.assertIn("release_common", source)
                # No local re-declaration of the leak patterns.
                self.assertNotIn("192\\.168\\.", source)
                self.assertNotIn("COMFY_" + "PUBLISHER_ID", source)

    def test_single_backslash_user_paths_are_detected(self):
        # The validator previously required *doubled* backslashes, so this
        # real-world shape never matched.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leak = "C" + ":" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "ComfyUI"
            (root / "leak.txt").write_text(leak, encoding="utf-8")
            hits = release_common.privacy_hits(root, published_only=True)
            self.assertEqual([relative for relative, _p in hits], ["leak.txt"])

    def test_published_only_skips_local_only_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leak = "D" + ":" + chr(92) + "Users" + chr(92) + "private"
            (root / "KONTEXT.md").write_text(leak, encoding="utf-8")
            # published_only applies the archive rules, so the local-only handoff
            # file is out of scope entirely.
            self.assertEqual(release_common.privacy_hits(root, published_only=True), [])
            # Without that filter every file is scanned; the maintainer machine's
            # own files are then in scope by design.
            self.assertEqual([rel for rel, _p in release_common.privacy_hits(root)], ["KONTEXT.md"])

    def test_dist_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dist").mkdir()
            # Built programmatically: the helper's own source must not contain the
            # pattern it looks for, or the repository scan reports this file.
            leak = "C" + ":" + chr(92) + "Users" + chr(92) + "someone"
            (root / "dist" / "asset.json").write_text(leak, encoding="utf-8")
            self.assertEqual(release_common.privacy_hits(root, published_only=True), [])

    def test_repository_is_clean_under_the_stricter_pattern(self):
        self.assertEqual(release_common.privacy_hits(ROOT, published_only=True), [])


class DemoSyncDryRunTests(unittest.TestCase):
    def _fixture(self, tmp: Path) -> tuple[Path, Path]:
        docs = tmp / "docs"
        (docs / "assets").mkdir(parents=True)
        shutil.copy(ROOT / "docs" / "demo-tracks.js", docs / "demo-tracks.js")
        metadata = tmp / "track.json"
        metadata.write_text(json.dumps({
            "schema": "minimax_music3_production_metadata_v7",
            "title": "Dry Run Track",
            "caption": "A quiet test caption.",
            "lyrics": "[Verse]\nla la",
            "generation_seed": 4242,
            "standard_audio_tags": {"album": "Test Album", "title": "Dry Run Track", "artist": "Tester", "genre": "Ambient"},
            "source": {"name": "Test Album"},
        }), encoding="utf-8")
        return docs, metadata

    def _run(self, docs: Path, metadata: Path, *extra: str):
        saved = sys.argv
        sys.argv = ["update_demo_catalog.py", str(metadata), "--docs-dir", str(docs), *extra]
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                DEMO.main()
        finally:
            sys.argv = saved
        return buffer.getvalue()

    def test_dry_run_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, metadata = self._fixture(Path(tmp))
            before = (docs / "demo-tracks.js").read_text(encoding="utf-8")
            output = self._run(docs, metadata, "--dry-run")
            self.assertIn("Dry run:", output)
            self.assertFalse(
                (docs / "assets" / "demo-covers").exists(),
                "a dry run must not create the cover directory",
            )
            self.assertEqual((docs / "demo-tracks.js").read_text(encoding="utf-8"), before)

    def test_real_run_writes_the_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, metadata = self._fixture(Path(tmp))
            output = self._run(docs, metadata)
            self.assertIn("Updated", output)
            updated = (docs / "demo-tracks.js").read_text(encoding="utf-8")
            self.assertIn("Dry Run Track", updated)


class ToolingDocumentationTests(unittest.TestCase):
    def test_historical_builders_document_their_preconditions(self):
        for name in ("build_public_workflow.py", "upgrade_workflow_to_v2.py"):
            with self.subTest(script=name):
                source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
                head = source[: source.index('"""', source.index('"""') + 3)]
                self.assertIn("template", head.lower(), f"{name} must state that it fixes a template")

    def test_tooling_python_requirement_is_documented(self):
        development = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
        self.assertIn("tomllib", development, "the tomllib-based tooling requirement must be documented")
        self.assertIn("3.11", development)


if __name__ == "__main__":
    unittest.main()
