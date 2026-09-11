"""Transfer tests for the model downloader (IMPROVE-TODO D03).

Everything runs against a local scripted HTTP server: no real download, no
network.  The suite covers the acceptance list of the task - interruption and
resume, a server that ignores ``Range``, a changed validator, wrong/short/absent
lengths, a wrong hash, retryable and fatal statuses, two concurrent callers, low
disk space, and an intact local file needing no request at all.
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_downloader():
    pkg_name = "_toolkit_download_test"
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


downloader = load_downloader()
BODY = bytes(range(256)) * 800  # 204 800 bytes, deterministic


class Payload:
    """Server behaviour for one test."""

    def __init__(self, body=BODY, **options):
        self.body = body
        self.etag = options.pop("etag", '"v1"')
        self.statuses = list(options.pop("statuses", []))
        self.fatal = options.pop("fatal", None)
        self.ignore_range = options.pop("ignore_range", False)
        self.truncate_plan = list(options.pop("truncate_plan", []))
        self.omit_length = options.pop("omit_length", False)
        self.length_offset = options.pop("length_offset", 0)
        assert not options, f"unknown options: {options}"

    def truncate_for_this_request(self):
        if self.truncate_plan:
            return self.truncate_plan.pop(0)
        return None


class ScriptedHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the test output clean
        pass

    def do_GET(self):
        payload = self.server.payload
        self.server.requests.append(self.headers.get("Range"))
        self.server.if_ranges.append(self.headers.get("If-Range"))
        if payload.fatal:
            self.send_response(payload.fatal)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if payload.statuses:
            self.send_response(payload.statuses.pop(0))
            self.send_header("Retry-After", "0")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = payload.body
        range_header = self.headers.get("Range")
        if_range = self.headers.get("If-Range")
        if range_header and not payload.ignore_range and (if_range is None or if_range == payload.etag):
            start = int(range_header.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
            self.send_header("Content-Length", str(len(body) - start))
            self.send_header("ETag", payload.etag)
            self.end_headers()
            self.wfile.write(body[start:])
            return
        truncate = payload.truncate_for_this_request()
        self.send_response(200)
        self.send_header("ETag", payload.etag)
        if not payload.omit_length:
            self.send_header("Content-Length", str(len(body) + payload.length_offset))
        self.end_headers()
        self.wfile.write(body[:truncate] if truncate else body)
        if truncate:
            self.close_connection = True


class TransferTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        downloader.VERIFIED_CACHE.clear()

    def serve(self, payload: Payload):
        server = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedHandler)
        server.payload = payload
        server.requests = []
        server.if_ranges = []
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{server.server_address[1]}/model.bin", server

    def dest(self, name="model.bin"):
        return self.dir / name


class DownloadTests(TransferTestCase):
    def test_complete_download_publishes_a_verified_file(self):
        url, server = self.serve(Payload())
        path = downloader.download_file(url, self.dest(), sha256=hashlib.sha256(BODY).hexdigest())
        self.assertEqual(path.read_bytes(), BODY)
        self.assertFalse((self.dir / "model.bin.part").exists())
        self.assertFalse((self.dir / "model.bin.part.json").exists())
        self.assertEqual(len(server.requests), 1)

    def test_existing_valid_file_needs_no_request(self):
        url, server = self.serve(Payload())
        self.dest().write_bytes(BODY)
        path = downloader.download_file(url, self.dest(), sha256=hashlib.sha256(BODY).hexdigest(), expected_bytes=len(BODY))
        self.assertEqual(path.read_bytes(), BODY)
        self.assertEqual(server.requests, [])

    def test_interrupted_transfer_keeps_a_partial_and_resumes_it(self):
        payload = Payload(truncate_plan=[100_000])
        url, server = self.serve(payload)
        with self.assertRaises(downloader.IncompleteTransfer):
            downloader.download_file(url, self.dest(), expected_bytes=len(BODY))
        partial = self.dir / "model.bin.part"
        self.assertTrue(partial.exists(), "a resumable partial must survive the interruption")
        self.assertEqual(partial.stat().st_size, 100_000)
        self.assertTrue((self.dir / "model.bin.part.json").exists())
        self.assertFalse(self.dest().exists(), "no half file may look installed")

        path = downloader.download_file(url, self.dest(), sha256=hashlib.sha256(BODY).hexdigest(), expected_bytes=len(BODY))
        self.assertEqual(path.read_bytes(), BODY)
        self.assertEqual(server.requests[1], "bytes=100000-", "the second attempt must resume")
        self.assertFalse((self.dir / "model.bin.part").exists())

    def test_server_ignoring_range_restarts_instead_of_concatenating(self):
        payload = Payload(truncate_plan=[80_000], ignore_range=True)
        url, server = self.serve(payload)
        with self.assertRaises(downloader.IncompleteTransfer):
            downloader.download_file(url, self.dest(), expected_bytes=len(BODY))
        path = downloader.download_file(url, self.dest(), expected_bytes=len(BODY))
        self.assertEqual(path.read_bytes(), BODY, "a 200 answer must replace the partial, not append to it")

    def test_changed_validator_restarts_the_transfer(self):
        payload = Payload(truncate_plan=[80_000])
        url, server = self.serve(payload)
        with self.assertRaises(downloader.IncompleteTransfer):
            downloader.download_file(url, self.dest(), expected_bytes=len(BODY))
        payload.etag = '"v2"'  # the resource changed between the two attempts
        path = downloader.download_file(url, self.dest(), expected_bytes=len(BODY))
        self.assertEqual(path.read_bytes(), BODY)
        self.assertEqual(server.if_ranges[1], '"v1"', "the resume must pin the validator it started from")

    def test_retryable_statuses_are_retried_with_retry_after(self):
        url, server = self.serve(Payload(statuses=[429, 503]))
        path = downloader.download_file(url, self.dest())
        self.assertEqual(path.read_bytes(), BODY)
        self.assertEqual(len(server.requests), 3)

    def test_fatal_status_fails_immediately_without_retrying(self):
        url, server = self.serve(Payload(fatal=403))
        with self.assertRaises(downloader.DownloadError) as ctx:
            downloader.download_file(url, self.dest())
        self.assertIn("403", str(ctx.exception))
        self.assertEqual(len(server.requests), 1, "a permission problem must not be retried")
        self.assertFalse(self.dest().exists())

    def test_wrong_hash_is_a_failure_and_leaves_nothing_behind(self):
        url, _ = self.serve(Payload())
        with self.assertRaises(downloader.DownloadError) as ctx:
            downloader.download_file(url, self.dest(), sha256="0" * 64)
        self.assertIn("SHA256", str(ctx.exception))
        self.assertFalse(self.dest().exists())
        self.assertFalse((self.dir / "model.bin.part").exists(), "wrong bytes must not stay for a resume")

    def test_declared_length_longer_than_the_body_is_detected(self):
        url, _ = self.serve(Payload(length_offset=5))
        with self.assertRaises(downloader.IncompleteTransfer):
            downloader.download_file(url, self.dest())
        self.assertFalse(self.dest().exists())

    def test_missing_content_length_still_completes(self):
        url, _ = self.serve(Payload(omit_length=True))
        path = downloader.download_file(url, self.dest(), sha256=hashlib.sha256(BODY).hexdigest())
        self.assertEqual(path.read_bytes(), BODY)

    def test_wrong_expected_size_is_rejected(self):
        url, _ = self.serve(Payload())
        with self.assertRaises(downloader.DownloadError) as ctx:
            downloader.download_file(url, self.dest(), expected_bytes=len(BODY) + 1)
        self.assertIn("wrong size", str(ctx.exception))
        self.assertFalse(self.dest().exists())

    def test_two_callers_download_once(self):
        url, server = self.serve(Payload())
        results = []
        errors = []

        def call():
            try:
                results.append(downloader.download_file(url, self.dest()))
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=call) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(self.dest().read_bytes(), BODY)
        self.assertEqual(len(server.requests), 1, "the second caller must wait, not transfer again")

    def test_low_disk_space_refuses_before_any_request(self):
        url, server = self.serve(Payload())
        usage = shutil.disk_usage(self.dir)
        original = shutil.disk_usage

        def fake_usage(_path):
            return type(usage)(usage.total, usage.used, 1024)

        shutil.disk_usage = fake_usage
        try:
            with self.assertRaises(downloader.DownloadError) as ctx:
                downloader.download_file(url, self.dest(), expected_bytes=len(BODY))
        finally:
            shutil.disk_usage = original
        self.assertIn("disk space", str(ctx.exception))
        self.assertEqual(server.requests, [])


class RedactionAndCacheTests(TransferTestCase):
    def test_signed_urls_are_redacted_in_logs_and_errors(self):
        self.assertEqual(
            downloader.redact_url("https://example.invalid/a.bin?token=secret&x=1#frag"),
            "https://example.invalid/a.bin",
        )
        self.assertEqual(downloader.redact_url("https://example.invalid/a.bin"), "https://example.invalid/a.bin")

    def test_fatal_error_message_does_not_leak_the_token(self):
        url, _ = self.serve(Payload(fatal=403))
        url_with_token = f"{url}?token=supersecret"
        with self.assertRaises(downloader.DownloadError) as ctx:
            downloader.download_file(url_with_token, self.dest())
        self.assertNotIn("supersecret", str(ctx.exception))

    def test_verification_is_cached_by_signature(self):
        path = self.dest()
        path.write_bytes(BODY)
        digest = hashlib.sha256(BODY).hexdigest()
        calls = []
        original = downloader._verify_sha256

        def counting(p, expected):
            calls.append(p)
            return original(p, expected)

        downloader._verify_sha256 = counting
        try:
            self.assertTrue(downloader._file_is_ready(path, digest))
            self.assertTrue(downloader._file_is_ready(path, digest))
            self.assertEqual(len(calls), 1, "the second check must use the signature cache")
            path.write_bytes(BODY + b"x")
            self.assertFalse(downloader._file_is_ready(path, digest))
            self.assertEqual(len(calls), 2, "a changed file must be re-verified")
        finally:
            downloader._verify_sha256 = original

    def test_check_file_entries_uses_the_resolved_url_and_size(self):
        url, server = self.serve(Payload())
        report = downloader.check_file_entries(
            [{"name": "model.bin", "target": "models/llm", "url": url, "bytes": len(BODY)}],
            base_path=self.dir,
            auto_download=True,
        )
        self.assertEqual(report[0]["status"], "downloaded")
        self.assertEqual(Path(report[0]["target"]).read_bytes(), BODY)
        self.assertEqual(len(server.requests), 1)


if __name__ == "__main__":
    unittest.main()
