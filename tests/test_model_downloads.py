"""Model-entry normalization and download hardening tests (F12 / T22, T23)."""
from __future__ import annotations

import importlib
import io
import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

import _toolkit_bootstrap

_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
downloader = importlib.import_module(f"{_PACKAGE.__name__}.model_downloader")
autodownload = importlib.import_module(f"{_PACKAGE.__name__}.minimax_autodownload")
flashsr = importlib.import_module(f"{_PACKAGE.__name__}.flashsr_audio")


class FakeResponse:
    def __init__(self, payload: bytes, content_length=None):
        self._stream = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload) if content_length is None else content_length)}

    def read(self, size=-1):
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class UrlOpenPatch:
    def __init__(self, payload: bytes, content_length=None, error=None):
        self.payload = payload
        self.content_length = content_length
        self.error = error

    def __enter__(self):
        self._saved = downloader.urlopen

        def fake_urlopen(request, timeout=None):
            if self.error is not None:
                raise self.error
            return FakeResponse(self.payload, self.content_length)

        downloader.urlopen = fake_urlopen
        return self

    def __exit__(self, *exc):
        downloader.urlopen = self._saved
        return False


class NormalizationTests(unittest.TestCase):
    def test_bundled_config_expands_every_group(self):
        entries = downloader.normalize_model_entries(downloader.load_models_config())
        names = {entry["name"] for entry in entries}
        self.assertIn("student_ldm.pth", names)
        self.assertTrue(any(entry.get("note") for entry in entries))
        for entry in entries:
            self.assertEqual(downloader.validate_model_entry(entry), None)
            self.assertTrue(entry.get("target"), f"{entry['name']} lost its target")

    def test_group_note_and_default_target_are_applied(self):
        config = {
            "minimax": {"note": "group note", "files": [{"name": "a", "target": "t"}]},
            "flashsr": {"weights": {"target": "models/audio/flashsr", "files": [{"name": "b"}]}},
        }
        entries = downloader.normalize_model_entries(config, flux2=False, llm=False)
        self.assertEqual(entries[0]["note"], "group note")
        self.assertEqual(entries[1]["target"], "models/audio/flashsr")

    def test_explicit_values_win_over_group_defaults(self):
        config = {
            "minimax": {"note": "group", "files": [{"name": "a", "target": "t", "note": "own"}]},
            "flashsr": {"weights": {"target": "models/audio/flashsr", "files": [{"name": "b"}]}},
        }
        entries = downloader.normalize_model_entries(config, flux2=False, llm=False)
        # An entry keeps its own note and (outside the FlashSR group) its target.
        self.assertEqual(entries[0]["note"], "own")
        self.assertEqual(entries[1]["target"], "models/audio/flashsr")

    def test_flashsr_target_follows_the_group_not_the_entry(self):
        # D01: the FlashSR runtime only opens the standard file names in the
        # group folder, so a diverging per-file target would download a file
        # that is then never found.  The group target wins deliberately; the
        # divergence is logged instead of being honoured silently.
        config = {
            "flashsr": {"weights": {"target": "models/audio/flashsr", "files": [{"name": "b", "target": "custom"}]}},
        }
        entries = downloader.normalize_model_entries(config, minimax=False, flux2=False, llm=False)
        self.assertEqual(entries[0]["target"], "models/audio/flashsr")

    def test_malformed_entries_are_skipped_not_fatal(self):
        config = {"minimax": {"files": [42, {"name": 5, "target": "t"}, {"name": "ok", "target": "t"}]}}
        entries = downloader.normalize_model_entries(config, flux2=False, flashsr=False, llm=False)
        self.assertEqual([entry["name"] for entry in entries], ["ok"])

    def test_non_dict_config_is_tolerated(self):
        self.assertEqual(downloader.normalize_model_entries(None), [])

    def test_group_toggles(self):
        config = downloader.load_models_config()
        only_flashsr = downloader.normalize_model_entries(
            config, minimax=False, flux2=False, llm=False
        )
        self.assertTrue(only_flashsr)
        self.assertTrue(all(entry["name"].endswith(".pth") for entry in only_flashsr))


class ConsumerParityTests(unittest.TestCase):
    def test_check_node_and_normalizer_agree(self):
        captured = {}
        # D04: the node now goes through the preflight (inventory/space report)
        # instead of calling check_file_entries directly, so this is the seam that
        # has to agree with the normalizer.
        saved_preflight = autodownload.preflight_models

        def fake_preflight(entries, base_path=None, auto_download=False):
            captured["entries"] = entries
            enriched = [
                {
                    "name": e["name"],
                    "target": e.get("target", ""),
                    "status": "present",
                    "message": "",
                    "bytes_expected": e.get("bytes"),
                    "bytes_present": None,
                    "optional": bool(e.get("optional")),
                }
                for e in entries
            ]
            return {
                "entries": enriched,
                "summary": {
                    "total": len(enriched),
                    "present": len(enriched),
                    "downloaded": 0,
                    "missing": 0,
                    "failed": 0,
                    "required_missing": [],
                    "optional_missing": [],
                    "missing_bytes": 0,
                    "free_bytes": None,
                    "space_ok": None,
                    "auto_download": False,
                    "ok": True,
                },
                "checked_at": "2026-09-11T00:00:00Z",
            }

        autodownload.preflight_models = fake_preflight
        try:
            autodownload.MiniMaxModelAutodownload().check(auto_download=False)
        finally:
            autodownload.preflight_models = saved_preflight

        expected = downloader.normalize_model_entries(downloader.load_models_config())
        self.assertEqual(
            [(e["name"], e.get("target", "")) for e in captured["entries"]],
            [(e["name"], e.get("target", "")) for e in expected],
        )

    def test_flashsr_runtime_uses_the_same_expansion(self):
        config = downloader.load_models_config()
        expected = downloader.normalize_model_entries(config, minimax=False, flux2=False, llm=False)
        captured = {}
        saved = flashsr.check_file_entries

        def fake_check(entries, base_path=None, auto_download=False):
            captured["entries"] = entries
            return [{"name": e["name"], "target": e.get("target", ""), "status": "present", "message": ""} for e in entries]

        flashsr.check_file_entries = fake_check
        try:
            flashsr._ensure_flashsr_weights(auto_download=False)
        finally:
            flashsr.check_file_entries = saved
        self.assertEqual(
            [e.get("target", "") for e in captured["entries"]],
            [e.get("target", "") for e in expected],
        )

    def test_diagnostics_uses_the_same_expansion(self):
        spec = importlib.util.spec_from_file_location(
            "_diag_models", Path(__file__).resolve().parents[1] / "scripts" / "toolkit_diagnostics.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["_diag_models"] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        report = module._check_models(auto_download=False)
        named = {item["name"] for item in report}
        self.assertIn("student_ldm.pth", named)
        for item in report:
            self.assertTrue(item["target"], f"{item['name']} has no resolved target")


class DownloadHardeningTests(unittest.TestCase):
    def _target(self, tmp: str) -> Path:
        return Path(tmp) / "models" / "audio" / "song.bin"

    def test_successful_download_publishes_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = self._target(tmp)
            with UrlOpenPatch(b"x" * 4096):
                result = downloader.download_file("http://example.invalid/x", destination)
            self.assertEqual(result, destination)
            self.assertEqual(destination.read_bytes(), b"x" * 4096)
            self.assertEqual([p.name for p in destination.parent.iterdir()], ["song.bin"])

    def test_empty_response_is_a_failure_with_no_leftovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = self._target(tmp)
            with UrlOpenPatch(b""):
                with self.assertRaises(RuntimeError) as ctx:
                    downloader.download_file("http://example.invalid/x", destination)
            self.assertIn("empty download", str(ctx.exception))
            self.assertFalse(destination.exists())
            self.assertEqual([p.name for p in destination.parent.iterdir()], [])

    def test_short_body_against_declared_length_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = self._target(tmp)
            with UrlOpenPatch(b"x" * 100, content_length=1000):
                with self.assertRaises(RuntimeError) as ctx:
                    downloader.download_file("http://example.invalid/x", destination)
            self.assertIn("incomplete download", str(ctx.exception))
            self.assertFalse(destination.exists(), "no half file may look installed")
            # D03: an interrupted transfer keeps a *resumable* partial plus the
            # sidecar that names its URL and validator - that is the point of the
            # resume, and it is not a leftover the user could mistake for a model.
            self.assertEqual(sorted(p.name for p in destination.parent.iterdir()),
                             [destination.name + ".part", destination.name + ".part.json"])
            self.assertLess((destination.parent / (destination.name + ".part")).stat().st_size, 1000)

    def test_checksum_mismatch_is_a_failure_with_no_leftovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = self._target(tmp)
            with UrlOpenPatch(b"x" * 64):
                with self.assertRaises(RuntimeError) as ctx:
                    downloader.download_file("http://example.invalid/x", destination, sha256="0" * 64)
            self.assertIn("SHA256 mismatch", str(ctx.exception))
            self.assertFalse(destination.exists())
            # Wrong bytes must never be kept for a resume.
            self.assertEqual(list(destination.parent.iterdir()), [])

    def test_network_error_leaves_no_staging_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = self._target(tmp)
            # attempts=1 keeps this test fast; the retry path is covered by
            # tests/test_download_resume.py with a scripted server.
            with UrlOpenPatch(b"", error=OSError("connection reset")):
                with self.assertRaises(downloader.DownloadError) as ctx:
                    downloader.download_file("http://example.invalid/x", destination, attempts=1)
            self.assertIn("gave up after 1 attempt", str(ctx.exception))
            self.assertEqual(list(destination.parent.iterdir()), [])

    def test_existing_file_is_not_downloaded_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = self._target(tmp)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"already")

            def explode(*args, **kwargs):  # pragma: no cover - must never run
                raise AssertionError("urlopen must not be called for a present file")

            saved = downloader.urlopen
            downloader.urlopen = explode
            try:
                self.assertEqual(downloader.download_file("http://example.invalid/x", destination), destination)
            finally:
                downloader.urlopen = saved

    def test_staging_name_is_stable_so_a_resume_can_find_it(self):
        # D03 deliberately replaced the per-call unique staging name with a
        # stable one: a resume needs to find its partial again.  Safety comes
        # from the per-destination lock and the sidecar's URL/validator check,
        # not from the file name.
        first = downloader._staging_path(Path("models/song.bin"))
        second = downloader._staging_path(Path("models/song.bin"))
        self.assertEqual(first, second)
        self.assertTrue(first.name.endswith(".part"))
        other = downloader._staging_path(Path("models/other.bin"))
        self.assertNotEqual(first, other)

    def test_destination_lock_is_per_file(self):
        a = downloader.destination_lock(Path("models/song.bin"))
        b = downloader.destination_lock(Path("models/song.bin"))
        c = downloader.destination_lock(Path("models/other.bin"))
        self.assertIs(a, b)
        self.assertIsNot(a, c)


class ZipContainmentTests(unittest.TestCase):
    def _archive(self, members: dict) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)
        return buffer.getvalue()

    def test_extraction_skips_escaping_and_absolute_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "vendor"
            archive = self._archive({
                "Repo-main/inner.txt": "ok",
                "../escaped.txt": "nope",
                "/absolute.txt": "nope",
            })
            with UrlOpenPatch(archive):
                downloader.download_and_extract_zip("http://example.invalid/z.zip", destination)
            self.assertTrue((destination / "inner.txt").is_file())
            self.assertTrue((destination / ".minimax_download_ok").is_file())
            self.assertFalse((Path(tmp) / "escaped.txt").exists())
            self.assertFalse(Path("/absolute.txt").exists())
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name.endswith(".part")]
            self.assertEqual(leftovers, [])

    def test_empty_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "vendor"
            with UrlOpenPatch(b""):
                with self.assertRaises(RuntimeError):
                    downloader.download_and_extract_zip("http://example.invalid/z.zip", destination)
            self.assertFalse((destination / ".minimax_download_ok").exists())

    def test_marker_makes_repeated_calls_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "vendor"
            archive = self._archive({"Repo-main/inner.txt": "ok"})
            with UrlOpenPatch(archive):
                downloader.download_and_extract_zip("http://example.invalid/z.zip", destination)

            def explode(*args, **kwargs):  # pragma: no cover - must never run
                raise AssertionError("a completed extraction must not download again")

            saved = downloader.urlopen
            downloader.urlopen = explode
            try:
                self.assertEqual(
                    downloader.download_and_extract_zip("http://example.invalid/z.zip", destination),
                    destination,
                )
            finally:
                downloader.urlopen = saved


if __name__ == "__main__":
    unittest.main()
