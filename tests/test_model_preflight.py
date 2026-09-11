"""Preflight tests (IMPROVE-TODO D04).

The preflight is the deliberately triggered setup action: inventory, size and
space report plus an *explicitly requested* download.  These tests pin the
promises that make it usable as one:

* nothing networks at import time or inside ``INPUT_TYPES()``;
* the report says what is missing, how big it is and whether the volume holds it;
* a previously successful check never hides a file that was deleted afterwards;
* only the selected branches (and never an optional artifact) are considered;
* the node keeps its single STRING output and offers the structured result in
  its UI payload.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _toolkit_bootstrap as bootstrap  # noqa: E402  (lives next to the tests)


def load_toolkit_modules():
    pkg_name = "_toolkit_preflight_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in ("toolkit_logging", "comfy_resources", "model_downloader", "minimax_autodownload"):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


MODULES = load_toolkit_modules()
downloader = MODULES["model_downloader"]
autodownload = MODULES["minimax_autodownload"]


def entry(name, target="models/audio/flashsr", **extra):
    payload = {"name": name, "target": target}
    payload.update(extra)
    return payload


class PreflightTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        downloader.VERIFIED_CACHE.clear()

    def place(self, target, name, data=b"x" * 16):
        directory = self.base / target
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_bytes(data)
        return directory / name

    def patch(self, obj, name, value):
        original = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, original)


class PreflightReportTests(PreflightTestCase):
    def test_fresh_install_reports_every_required_file_missing(self):
        result = downloader.preflight_models(
            [entry("a.pth", bytes=100), entry("b.pth", target="models/vae", bytes=250)],
            base_path=self.base,
            auto_download=False,
        )
        summary = result["summary"]
        self.assertEqual(summary["missing"], 2)
        self.assertEqual(summary["present"], 0)
        self.assertEqual(summary["missing_bytes"], 350)
        self.assertEqual(sorted(summary["required_missing"]), ["a.pth", "b.pth"])
        self.assertFalse(summary["ok"])
        self.assertFalse(summary["auto_download"])
        self.assertTrue(result["checked_at"])

    def test_present_files_are_reported_with_their_size(self):
        self.place("models/audio/flashsr", "a.pth", b"y" * 4096)
        result = downloader.preflight_models(
            [entry("a.pth", bytes=4096), entry("b.pth", bytes=10)],
            base_path=self.base,
            auto_download=False,
        )
        by_name = {item["name"]: item for item in result["entries"]}
        self.assertEqual(by_name["a.pth"]["status"], "present")
        self.assertEqual(by_name["a.pth"]["bytes_present"], 4096)
        self.assertIsNone(by_name["b.pth"]["bytes_present"])
        self.assertEqual(result["summary"]["missing_bytes"], 10)

    def test_a_deleted_file_is_missing_again_on_the_next_check(self):
        self.place("models/audio/flashsr", "a.pth")
        first = downloader.preflight_models([entry("a.pth")], base_path=self.base, auto_download=False)
        self.assertEqual(first["summary"]["present"], 1)
        (self.base / "models/audio/flashsr/a.pth").unlink()
        second = downloader.preflight_models([entry("a.pth")], base_path=self.base, auto_download=False)
        self.assertEqual(second["summary"]["present"], 0)
        self.assertEqual(second["summary"]["required_missing"], ["a.pth"])

    def test_optional_artifacts_are_reported_but_not_required(self):
        result = downloader.preflight_models(
            [entry("int8.safetensors", optional=True, bytes=100)],
            base_path=self.base,
            auto_download=False,
        )
        summary = result["summary"]
        self.assertEqual(summary["required_missing"], [])
        self.assertEqual(summary["optional_missing"], ["int8.safetensors"])
        self.assertTrue(summary["ok"], "an optional artifact must not fail the preflight")

    def test_space_shortfall_is_reported(self):
        original = shutil.disk_usage
        usage = shutil.disk_usage(self.base)

        def tiny(_path):
            return type(usage)(usage.total, usage.used, 1024)

        self.patch(shutil, "disk_usage", tiny)
        try:
            result = downloader.preflight_models(
                [entry("big.safetensors", target="models/vae", bytes=10 * 1024 ** 3)],
                base_path=self.base,
                auto_download=False,
            )
        finally:
            shutil.disk_usage = original
        self.assertFalse(result["summary"]["space_ok"])
        self.assertIn("WARNING", "\n".join(downloader.format_preflight_report(result)))

    def test_report_lines_name_the_required_and_optional_gaps(self):
        result = downloader.preflight_models(
            [entry("req.pth"), entry("opt.pth", optional=True)],
            base_path=self.base,
            auto_download=False,
        )
        text = "\n".join(downloader.format_preflight_report(result))
        self.assertIn("required and missing: req.pth", text)
        self.assertIn("optional and missing", text)
        self.assertIn("missing bytes", text)


class PreflightDownloadPolicyTests(PreflightTestCase):
    def test_disabled_auto_download_never_opens_a_connection(self):
        def explode(*args, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("the preflight must not transfer when auto_download is off")

        self.patch(downloader, "urlopen", explode)
        result = downloader.preflight_models(
            [entry("a.pth", url="https://example.invalid/a.pth")],
            base_path=self.base,
            auto_download=False,
        )
        self.assertEqual(result["entries"][0]["status"], "missing")
        self.assertFalse(result["summary"]["auto_download"])

    def test_the_explicit_flag_reaches_the_transfer_layer(self):
        captured = {}

        def fake_check(entries, base_path=None, auto_download=True):
            captured["auto_download"] = auto_download
            return [
                {"name": item["name"], "target": item.get("target", ""), "status": "downloaded", "message": ""}
                for item in entries
            ]

        self.patch(downloader, "check_file_entries", fake_check)
        result = downloader.preflight_models([entry("a.pth")], base_path=self.base, auto_download=True)
        self.assertTrue(captured["auto_download"])
        self.assertEqual(result["entries"][0]["status"], "downloaded")

    def test_only_the_selected_branches_are_preflighted(self):
        config = downloader.load_models_config()
        entries = downloader.normalize_model_entries(config, minimax=False, flux2=False, llm=False)
        result = downloader.preflight_models(entries, base_path=self.base, auto_download=False)
        self.assertEqual(result["summary"]["total"], 3, "only the FlashSR weights")
        self.assertTrue(all(item["name"].endswith(".pth") for item in result["entries"]))

    def test_the_optional_quantization_is_not_preflighted_by_default(self):
        config = downloader.load_models_config()
        default = downloader.normalize_model_entries(config, flux2=False, flashsr=False, llm=False)
        names = {item["name"] for item in default}
        self.assertNotIn("minimax_music3_dit_int8_convrot.safetensors", names)
        with_optional = downloader.normalize_model_entries(
            config, flux2=False, flashsr=False, llm=False, include_optional=True
        )
        self.assertIn("minimax_music3_dit_int8_convrot.safetensors", {item["name"] for item in with_optional})


class AutodownloadNodeTests(PreflightTestCase):
    def sample_preflight(self, status="present", ok=True):
        return {
            "entries": [
                {"name": "a.pth", "target": str(self.base / "a.pth"), "status": status, "message": "note"}
            ],
            "summary": {"total": 1, "present": 1 if ok else 0, "downloaded": 0, "missing": 0 if ok else 1,
                        "failed": 0 if ok else 1, "required_missing": [], "optional_missing": [],
                        "missing_bytes": 0, "free_bytes": 1, "space_ok": True, "auto_download": False, "ok": ok},
            "checked_at": "2026-09-11T00:00:00Z",
        }

    def test_node_keeps_the_string_output_and_adds_a_structured_payload(self):
        self.patch(autodownload, "preflight_models", lambda *a, **k: self.sample_preflight())
        payload = autodownload.MiniMaxModelAutodownload().check(auto_download=False)
        self.assertIsInstance(payload["result"], tuple)
        self.assertEqual(len(payload["result"]), 1)
        self.assertIn("model check", payload["result"][0])
        structured = json.loads(payload["ui"]["preflight_json"][0])
        self.assertTrue(structured["summary"]["ok"])
        self.assertEqual(payload["ui"]["text"][0], payload["result"][0])

    def test_node_raises_on_a_failed_download_when_auto_download_is_on(self):
        report = self.sample_preflight(status="failed", ok=False)
        report["entries"][0]["message"] = "HTTP 403"
        self.patch(autodownload, "preflight_models", lambda *a, **k: report)
        with self.assertRaises(RuntimeError) as ctx:
            autodownload.MiniMaxModelAutodownload().check(auto_download=True)
        self.assertIn("a.pth", str(ctx.exception))
        self.assertIn("403", str(ctx.exception))

    def test_node_reports_failures_without_raising_when_auto_download_is_off(self):
        report = self.sample_preflight(status="failed", ok=False)
        self.patch(autodownload, "preflight_models", lambda *a, **k: report)
        payload = autodownload.MiniMaxModelAutodownload().check(auto_download=False)
        self.assertIn("failed", payload["result"][0])


class ModelManagerRouteTests(unittest.TestCase):
    """The preflight as an HTTP surface: report on GET, download on POST."""

    class FakeRequest:
        def __init__(self, query=None, body=None):
            self.rel_url = types.SimpleNamespace(query=query or {})
            self._body = body

        async def json(self):
            if self._body is None:
                raise ValueError("no JSON body")
            return self._body

    def setUp(self):
        self.package, self.host = bootstrap.load_entry_point()
        self.routes = {(method, path): handler for method, path, handler in self.host.routes}
        self.module = sys.modules[f"{self.package.__name__}.model_manager_routes"]
        self.calls = []
        self.report = {
            "entries": [],
            "summary": {"ok": True, "total": 5, "present": 5, "missing": 0, "failed": 0},
            "checked_at": "2026-09-11T00:00:00Z",
        }
        self.module.build_preflight = lambda flags, download: (
            self.calls.append((flags, download)),
            self.report,
        )[1]

    def call(self, method, request):
        import asyncio

        handler = self.routes[(method, "/minimax_music_toolkit/model_preflight")]
        return asyncio.run(handler(request))

    def test_both_routes_are_registered(self):
        self.assertIn(("GET", "/minimax_music_toolkit/model_preflight"), self.routes)
        self.assertIn(("POST", "/minimax_music_toolkit/model_preflight"), self.routes)

    def test_get_reports_without_downloading(self):
        response = self.call("GET", self.FakeRequest())
        self.assertFalse(response.payload["downloaded"])
        self.assertEqual(self.calls[-1][1], False)
        self.assertTrue(response.payload["ok"])
        self.assertIsInstance(response.payload["lines"], list)

    def test_get_query_selects_the_groups(self):
        self.call("GET", self.FakeRequest(query={"flux2": "0", "llm": "false", "minimax": "1"}))
        flags = self.calls[-1][0]
        self.assertFalse(flags["flux2"])
        self.assertFalse(flags["llm"])
        self.assertTrue(flags["minimax"])

    def test_post_downloads_when_asked(self):
        response = self.call("POST", self.FakeRequest(body={"download": True, "minimax": False}))
        self.assertTrue(response.payload["downloaded"])
        flags, download = self.calls[-1]
        self.assertTrue(download)
        self.assertFalse(flags["minimax"])
        self.assertTrue(response.payload["ok"])

    def test_post_without_a_body_is_still_an_explicit_request(self):
        # A POST to this path is the "do it" action; the query flags are absent
        # here, so every group is selected and the download runs.
        response = self.call("POST", self.FakeRequest())
        flags, download = self.calls[-1]
        self.assertTrue(download)
        self.assertTrue(all(flags.values()))
        self.assertIn("ok", response.payload)


class NoNetworkAtLoadTests(unittest.TestCase):
    class NoNetwork:
        def __enter__(self):
            import socket

            self._saved = socket.socket.connect

            def deny(*args, **kwargs):  # pragma: no cover - only on a violation
                raise AssertionError("a network connection was attempted during load or INPUT_TYPES()")

            socket.socket.connect = deny
            return self

        def __exit__(self, *exc):
            import socket

            socket.socket.connect = self._saved
            return False

    def test_importing_and_querying_input_types_never_opens_a_socket(self):
        with self.NoNetwork():
            package, host = bootstrap.load_entry_point()
            self.assertGreaterEqual(len(package.NODE_CLASS_MAPPINGS), 31)
            for node_type, node_class in package.NODE_CLASS_MAPPINGS.items():
                with self.subTest(node=node_type):
                    node_class.INPUT_TYPES()
        self.assertTrue(host.routes, "the routes are still registered")


if __name__ == "__main__":
    unittest.main()
