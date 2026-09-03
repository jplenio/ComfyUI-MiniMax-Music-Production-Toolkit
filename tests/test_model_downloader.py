from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_model_downloader():
    pkg_name = "_toolkit_downloader_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    for module_name in ("toolkit_logging", "model_downloader"):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return sys.modules[f"{pkg_name}.model_downloader"]


DOWNLOADER = load_model_downloader()


class ModelsConfigTests(unittest.TestCase):
    def test_config_is_valid_and_complete(self):
        config = DOWNLOADER.load_models_config()
        self.assertEqual(config["version"], 2)
        flashsr = config["flashsr"]
        self.assertEqual(len(flashsr["weights"]["files"]), 3)
        for entry in flashsr["weights"]["files"]:
            self.assertTrue(entry["url"].startswith("https://"))
            self.assertTrue(entry["name"].endswith(".pth"))
        # The inference code is bundled with the toolkit, not downloaded.
        self.assertNotIn("inference_repo", flashsr)
        self.assertNotIn("torchjaekwon_repo", flashsr)
        self.assertEqual(len(config["minimax"]["files"]), 3)
        self.assertEqual(len(config["flux2"]["files"]), 3)
        # Entries without a verified URL must remain empty so nothing unverified is downloaded.
        for group in ("minimax", "flux2"):
            for entry in config[group]["files"]:
                self.assertEqual(entry["url"], "")

    def test_resolve_target_with_explicit_base(self):
        base = Path(tempfile.gettempdir())
        target = DOWNLOADER.resolve_target("models/audio/flashsr", base_path=base)
        self.assertEqual(target, base / "models" / "audio" / "flashsr")

    def test_resolve_target_keeps_absolute(self):
        absolute = Path(tempfile.gettempdir()) / "abs"
        self.assertEqual(DOWNLOADER.resolve_target(str(absolute), base_path=Path("x")), absolute)

    def test_resolve_target_honors_models_directory_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            models_root = Path(tmp) / "F-ComfyUI" / "models"
            previous = os.environ.get("COMFYUI_MODELS_DIRECTORY")
            os.environ["COMFYUI_MODELS_DIRECTORY"] = str(models_root)
            try:
                # ComfyUI convention: config targets start with "models/".
                target = DOWNLOADER.resolve_target("models/audio/flashsr")
                self.assertEqual(target, models_root / "audio" / "flashsr")
                # Targets without the prefix resolve directly below models_dir.
                self.assertEqual(DOWNLOADER.resolve_target("audio/flashsr"), models_root / "audio" / "flashsr")
                self.assertEqual(DOWNLOADER.comfy_models_dir(), models_root)
            finally:
                if previous is None:
                    os.environ.pop("COMFYUI_MODELS_DIRECTORY", None)
                else:
                    os.environ["COMFYUI_MODELS_DIRECTORY"] = previous


class FileDownloadTests(unittest.TestCase):
    def test_download_file_from_local_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.pth"
            payload = b"weight-bytes" * 100
            source.write_bytes(payload)
            destination = root / "models" / "audio" / "flashsr" / "source.pth"
            result = DOWNLOADER.download_file(source.as_uri(), destination)
            self.assertEqual(result.read_bytes(), payload)

    def test_download_file_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "a.bin"
            source.write_bytes(b"data")
            destination = root / "out" / "a.bin"
            DOWNLOADER.download_file(source.as_uri(), destination)
            first_stat = destination.stat().st_mtime_ns
            DOWNLOADER.download_file(source.as_uri(), destination)
            self.assertEqual(destination.stat().st_mtime_ns, first_stat)

    def test_download_file_verifies_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "a.bin"
            payload = b"checksum-data"
            source.write_bytes(payload)
            good = hashlib.sha256(payload).hexdigest()
            destination = root / "out" / "a.bin"
            DOWNLOADER.download_file(source.as_uri(), destination, sha256=good)
            with self.assertRaises(RuntimeError):
                DOWNLOADER.download_file(
                    source.as_uri(), root / "out" / "b.bin", sha256="0" * 64
                )

    def test_download_and_extract_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "repo.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("FlashSR_Inference-main/FlashSR/FlashSR.py", "MODEL_CODE")
                zf.writestr("FlashSR_Inference-main/Readme.md", "doc")
            target = root / "models" / "audio" / "flashsr" / "FlashSR_Inference"
            DOWNLOADER.download_and_extract_zip(zip_path.as_uri(), target, strip_top_dir=True)
            self.assertEqual((target / "FlashSR" / "FlashSR.py").read_text(), "MODEL_CODE")
            self.assertTrue((target / ".minimax_download_ok").is_file())


class CheckFileEntriesTests(unittest.TestCase):
    def test_present_missing_and_failed_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            present = base / "models" / "audio" / "x.pth"
            present.parent.mkdir(parents=True)
            present.write_bytes(b"present")

            entries = [
                {"name": "x.pth", "target": "models/audio", "url": ""},
                {"name": "missing.pth", "target": "models/audio", "url": ""},
                {
                    "name": "dl.pth",
                    "target": "models/audio",
                    "url": (base / "source.pth").as_uri(),
                },
            ]
            (base / "source.pth").write_bytes(b"downloaded-content")

            report = DOWNLOADER.check_file_entries(entries, base_path=base, auto_download=True)
            by_name = {item["name"]: item for item in report}
            self.assertEqual(by_name["x.pth"]["status"], "present")
            self.assertEqual(by_name["missing.pth"]["status"], "missing")
            self.assertIn("no download URL", by_name["missing.pth"]["message"])
            self.assertEqual(by_name["dl.pth"]["status"], "downloaded")

    def test_auto_download_disabled_keeps_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.pth"
            source.write_bytes(b"data")
            entries = [{"name": "a.pth", "target": "models/audio", "url": source.as_uri()}]
            report = DOWNLOADER.check_file_entries(entries, base_path=base, auto_download=False)
            self.assertEqual(report[0]["status"], "missing")
            self.assertIn("disabled", report[0]["message"])

    def test_format_report_mentions_all_statuses(self):
        report = [
            {"name": "a.pth", "target": "x", "status": "present", "message": ""},
            {"name": "b.pth", "target": "x", "status": "missing", "message": "note"},
            {"name": "c.pth", "target": "x", "status": "downloaded", "message": ""},
            {"name": "d.pth", "target": "x", "status": "failed", "message": "boom"},
        ]
        text = DOWNLOADER.format_check_report(report)
        for fragment in ("OK ", "-- ", "DL ", "ERR", "b.pth", "boom"):
            self.assertIn(fragment, text)


if __name__ == "__main__":
    unittest.main()
