"""Route offload tests (IMPROVE-TODO U02).

The prompt routes serve a library with a few hundred (potentially thousands of)
files.  Reading and aggregating them synchronously inside an async handler blocks
ComfyUI's event loop, so the blocking calls now run through
``asyncio.to_thread``.  These tests prove the offload happens, that the payload
is unchanged, and that the library size limit also applies to
``/prompt_metadata``.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _toolkit_bootstrap as bootstrap  # noqa: E402

PACKAGE_NAME = "_toolkit_route_offload_test"


class FakeRequest:
    def __init__(self, query=None, body=None):
        self.rel_url = types.SimpleNamespace(query=query or {})
        self._body = body

    async def json(self):
        if self._body is None:
            raise ValueError("no JSON body")
        return self._body


class RouteOffloadTests(unittest.TestCase):
    def setUp(self):
        self.package, self.host = bootstrap.load_entry_point(PACKAGE_NAME)
        self.routes = {(method, path): handler for method, path, handler in self.host.routes}
        self.routes_module = sys.modules[f"{self.package.__name__}.prompt_routes"]
        self.loop_thread = threading.current_thread().name
        self.observed = []

    def call(self, method, path, request):
        handler = self.routes[(method, path)]
        return asyncio.run(handler(request))

    def record_thread(self, original, label):
        def wrapper(*args, **kwargs):
            self.observed.append((label, threading.current_thread().name))
            return original(*args, **kwargs)

        return wrapper

    def test_the_file_listing_runs_off_the_event_loop_thread(self):
        original = self.routes_module.list_prompt_files
        self.routes_module.list_prompt_files = self.record_thread(original, "list")
        try:
            response = self.call("GET", "/minimax_music_toolkit/prompt_files", FakeRequest({"kind": "user"}))
        finally:
            self.routes_module.list_prompt_files = original
        self.assertTrue(response.payload["ok"])
        self.assertTrue(response.payload["files"])
        label, thread_name = self.observed[-1]
        self.assertEqual(label, "list")
        self.assertNotEqual(thread_name, self.loop_thread, "the scan must not run on the event-loop thread")

    def test_the_option_aggregation_runs_off_the_event_loop_thread(self):
        # The handler imports this inside the function, so it must be patched on
        # the metadata module rather than on the routes module.
        metadata_module = sys.modules[f"{self.package.__name__}.prompt_metadata"]
        original = metadata_module.collect_file_field_values
        calls = []

        def wrapper(paths):
            calls.append(threading.current_thread().name)
            return original(paths)

        metadata_module.collect_file_field_values = wrapper
        try:
            response = self.call("GET", "/minimax_music_toolkit/prompt_metadata", FakeRequest())
        finally:
            metadata_module.collect_file_field_values = original
        self.assertTrue(response.payload["ok"])
        self.assertIn("unique_values", response.payload)
        self.assertTrue(calls, "the aggregation must have run")
        self.assertNotEqual(calls[-1], self.loop_thread)

    def test_the_single_file_read_runs_off_the_event_loop_thread(self):
        original = self.routes_module.load_prompt_file
        self.routes_module.load_prompt_file = self.record_thread(original, "load")
        try:
            listed = self.call("GET", "/minimax_music_toolkit/prompt_files", FakeRequest({"kind": "user"}))
            selected = listed.payload["files"][0]
            response = self.call(
                "GET",
                "/minimax_music_toolkit/prompt_text",
                FakeRequest({"kind": "user", "file": selected}),
            )
        finally:
            self.routes_module.load_prompt_file = original
        self.assertTrue(response.payload["ok"])
        label, thread_name = self.observed[-1]
        self.assertEqual(label, "load")
        self.assertNotEqual(thread_name, self.loop_thread)

    def test_the_metadata_payload_is_unchanged_by_the_offload(self):
        listed = self.call("GET", "/minimax_music_toolkit/prompt_files", FakeRequest({"kind": "user"}))
        selected = listed.payload["files"][0]
        response = self.call(
            "GET",
            "/minimax_music_toolkit/prompt_metadata",
            FakeRequest({"source": "bundled_library", "file": selected}),
        )
        payload = response.payload
        self.assertTrue(payload["ok"])
        self.assertIn("fields", payload)
        self.assertIn("description", payload)
        self.assertIn("unique_values", payload)

    def test_a_placeholder_selection_returns_options_only(self):
        response = self.call(
            "GET", "/minimax_music_toolkit/prompt_metadata", FakeRequest({"file": "<select a prompt>"})
        )
        self.assertTrue(response.payload["ok"])
        self.assertEqual(response.payload["fields"], {})
        self.assertIn("unique_values", response.payload)


class SizeLimitTests(unittest.TestCase):
    def setUp(self):
        self.package, self.host = bootstrap.load_entry_point(PACKAGE_NAME)
        self.routes = {(method, path): handler for method, path, handler in self.host.routes}
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.library = Path(self._tmp.name)

    def call(self, method, path, request):
        return asyncio.run(self.routes[(method, path)](request))

    def test_an_oversized_prompt_is_rejected_by_the_metadata_route(self):
        library = sys.modules[f"{self.package.__name__}.prompt_library"]
        big = self.library / "huge.txt"
        big.write_text("x" * (library.MAX_PROMPT_BYTES + 1), encoding="utf-8")
        response = self.call(
            "GET",
            "/minimax_music_toolkit/prompt_metadata",
            FakeRequest({"source": "external_directory", "directory": str(self.library), "file": "huge.txt"}),
        )
        self.assertEqual(response.status, 400, "the size limit must apply to /prompt_metadata too")
        self.assertIn("too large", response.payload["error"])

    def test_a_normal_sized_prompt_passes(self):
        (self.library / "small.txt").write_text("---\ngenre: Ambient\n---\n\ncalm and wide", encoding="utf-8")
        response = self.call(
            "GET",
            "/minimax_music_toolkit/prompt_metadata",
            FakeRequest({"source": "external_directory", "directory": str(self.library), "file": "small.txt"}),
        )
        self.assertTrue(response.payload["ok"], response.payload)
        self.assertEqual(response.payload["fields"].get("genre"), "Ambient")


if __name__ == "__main__":
    unittest.main()
