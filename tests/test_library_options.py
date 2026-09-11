"""Library option-service tests (F17 / T15).

The options cache moved from the structured node into the library service, so
these tests check the two things that mattered: aggregation uses the *safe*
enumeration and byte limit, and invalidation no longer requires importing a
node class.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

import _toolkit_bootstrap  # noqa: F401  (side-effect free import of the loader)

_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
library = importlib.import_module(f"{_PACKAGE.__name__}.prompt_library")
structured = importlib.import_module(f"{_PACKAGE.__name__}.minimax_structured_prompt")

HANDLERS = {(method, path): handler for method, path, handler in _HOST.routes}


class FakeRequest:
    def __init__(self, query=None, body=None):
        self.rel_url = types.SimpleNamespace(query=dict(query or {}))
        self._body = body

    async def json(self):
        return self._body


class LibraryOptionsTests(unittest.TestCase):
    def setUp(self):
        library.invalidate_library_options("all")

    def test_bundled_options_include_curated_and_library_values(self):
        options = library.library_options("user")
        self.assertTrue(options["genre"])
        self.assertTrue(options["lyrics"])
        self.assertIn("House", options["genre"])

    def test_options_are_cached_until_invalidated(self):
        before = library.library_option_version()
        first = library.library_options("user")
        second = library.library_options("user")
        self.assertIs(first, second, "the cached mapping is reused")
        library.invalidate_library_options("user")
        self.assertEqual(library.library_option_version(), before + 1)
        third = library.library_options("user")
        self.assertIsNot(first, third, "invalidation forces a rebuild")
        self.assertEqual(first, third)

    def test_external_directory_rebuilds_after_a_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_bytes(b"---\nGenre: Zydeco\n---\nA short description.\n")
            first = library.library_options("user", "external_directory", tmp)
            self.assertIn("Zydeco", first["genre"])
            self.assertNotIn("Skiffle", first["genre"])

            (root / "two.txt").write_bytes(b"---\nGenre: Skiffle\n---\nAnother description.\n")
            cached = library.library_options("user", "external_directory", tmp)
            self.assertNotIn("Skiffle", cached["genre"], "still cached")

            library.invalidate_library_options("user")
            refreshed = library.library_options("user", "external_directory", tmp)
            self.assertIn("Skiffle", refreshed["genre"])
            self.assertIn("Zydeco", refreshed["genre"])

    def test_aggregation_ignores_unsupported_and_hidden_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "good.txt").write_bytes(b"---\nGenre: Zydeco\n---\ntext\n")
            (root / "ignored.bin").write_bytes(b"---\nGenre: ShouldNotAppear\n---\ntext\n")
            (root / ".hidden.txt").write_bytes(b"---\nGenre: HiddenValue\n---\ntext\n")
            options = library.library_options("user", "external_directory", tmp)
            self.assertIn("Zydeco", options["genre"])
            self.assertNotIn("ShouldNotAppear", options["genre"])
            self.assertNotIn("HiddenValue", options["genre"])

    def test_aggregation_respects_the_selected_file_byte_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            oversized = b"---\nGenre: OversizedGenre\n---\n" + b"x" * (library.MAX_PROMPT_BYTES + 10)
            (root / "huge.txt").write_bytes(oversized)
            options = library.library_options("user", "external_directory", tmp)
            self.assertNotIn("OversizedGenre", options["genre"])

    def test_symlinked_file_outside_the_root_is_not_aggregated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "library"
            outside = Path(tmp) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "secret.txt").write_bytes(b"---\nGenre: Emoji-Secret\n---\ntext\n")
            try:
                os.symlink(outside / "secret.txt", root / "linked.txt")
            except (OSError, NotImplementedError, AttributeError):
                self.skipTest("symlinks are not available for this user/platform")
            options = library.library_options("user", "external_directory", str(root))
            self.assertNotIn("Emoji-Secret", options["genre"])


class InvalidationWithoutNodeImportTests(unittest.TestCase):
    def test_library_module_does_not_import_any_node(self):
        source = (Path(library.__file__)).read_text(encoding="utf-8")
        for node_module in ("minimax_structured_prompt", "minimax_prompt_source", "llm_chat"):
            with self.subTest(module=node_module):
                self.assertNotIn(node_module, source)

    def test_routes_module_does_not_import_any_node(self):
        routes = importlib.import_module(f"{_PACKAGE.__name__}.prompt_routes")
        source = Path(routes.__file__).read_text(encoding="utf-8")
        self.assertNotIn("minimax_structured_prompt", source)
        self.assertNotIn("import invalidate_library_options_cache", source)

    def test_structured_node_delegates_to_the_library_service(self):
        before = library.library_option_version()
        structured.invalidate_library_options_cache()
        self.assertEqual(library.library_option_version(), before + 1)
        self.assertEqual(structured._collect_options(), library.library_options("user"))

    def test_saving_a_custom_prompt_invalidates_the_option_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = library.library_option_version()
            handler = HANDLERS[("POST", "/minimax_music_toolkit/save_prompt")]
            response = asyncio.run(handler(FakeRequest(None, {
                "source": "external_directory",
                "directory": tmp,
                "file": "Fresh",
                "fields": {},
                "description": "text",
            })))
            self.assertEqual(response.status, 200, response.payload)
            self.assertEqual(
                library.library_option_version(), before + 1,
                "the save route must invalidate the library cache without a node import",
            )

    def test_register_routes_delegates_to_the_route_module(self):
        self.assertTrue(library.register_routes())
        self.assertIn(("GET", "/minimax_music_toolkit/prompt_files"), HANDLERS)


if __name__ == "__main__":
    unittest.main()
