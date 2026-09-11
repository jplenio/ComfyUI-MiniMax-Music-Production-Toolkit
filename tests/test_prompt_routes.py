"""End-to-end tests for the prompt-library HTTP routes (F03 / T05).

The handlers are exercised through the real entry point (fake ``PromptServer``
from ``tests/_toolkit_bootstrap.py``) with fake ``aiohttp`` request objects, so
the response envelope, status codes and error boundary are the real ones.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

from _toolkit_bootstrap import EXPECTED_ROUTES, load_entry_point

ENTRY_POINT = None
HANDLERS = {}


def setUpModule():
    global ENTRY_POINT, HANDLERS
    ENTRY_POINT, host = load_entry_point()
    HANDLERS = {(method, path): handler for method, path, handler in host.routes}


class FakeRequest:
    def __init__(self, query=None, body=None, bad_json=False):
        self.rel_url = types.SimpleNamespace(query=dict(query or {}))
        self._body = body
        self._bad_json = bad_json

    async def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._body


def call(method, path, *args, **kwargs):
    handler = HANDLERS[(method, path)]
    return asyncio.run(handler(FakeRequest(*args, **kwargs)))


PROMPT_METADATA = ("GET", "/minimax_music_toolkit/prompt_metadata")
SAVE_PROMPT = ("POST", "/minimax_music_toolkit/save_prompt")
SAVE_SYSTEM_PROMPT = ("POST", "/minimax_music_toolkit/save_system_prompt")
PROMPT_TEXT = ("GET", "/minimax_music_toolkit/prompt_text")
PROMPT_FILES = ("GET", "/minimax_music_toolkit/prompt_files")


class RouteRegistrationTests(unittest.TestCase):
    def test_all_routes_are_registered(self):
        self.assertEqual(set(HANDLERS), set(EXPECTED_ROUTES))


class PromptMetadataRouteTests(unittest.TestCase):
    def test_option_only_refresh_without_selection(self):
        # F03: option refresh used to fail because the empty selection was
        # loaded before aggregation.  An absent/empty file must return options.
        for query in ({"file": ""}, {}):
            with self.subTest(query=query):
                response = call("GET", PROMPT_METADATA[1], query)
                self.assertEqual(response.status, 200)
                self.assertTrue(response.payload["ok"], response.payload)
                self.assertEqual(response.payload["fields"], {})
                self.assertEqual(response.payload["description"], "")
                self.assertIn("genre", response.payload["unique_values"])
                self.assertTrue(response.payload["unique_values"]["genre"])

    def test_selected_file_returns_its_metadata(self):
        response = call("GET", PROMPT_METADATA[1], {"file": "electronic/synth-pop-vocal.txt"})
        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["ok"], response.payload)
        self.assertTrue(response.payload["unique_values"]["genre"])
        # The selected file uses a metadata block, so at least the description
        # or a structured field is populated.
        self.assertTrue(response.payload["description"] or response.payload["fields"])

    def test_missing_selected_file_is_a_controlled_error(self):
        response = call("GET", PROMPT_METADATA[1], {"file": "does/not/exist.txt"})
        self.assertEqual(response.status, 400)
        self.assertFalse(response.payload["ok"])
        self.assertIn("does not exist", response.payload["error"])


class SavePromptRouteTests(unittest.TestCase):
    def _tmpdir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return tmp.name

    def test_saves_a_custom_user_prompt(self):
        directory = self._tmpdir()
        response = call("POST", SAVE_PROMPT[1], None, {
            "source": "external_directory",
            "directory": directory,
            "file": "My Song",
            "fields": {"genre": "House", "tempo": "custom"},
            "description": "A description.",
            "overwrite": False,
        })
        self.assertEqual(response.status, 200, response.payload)
        self.assertTrue(response.payload["ok"])
        self.assertEqual(response.payload["file"], "_custom/My Song.txt")
        written = Path(directory) / "_custom" / "My Song.txt"
        self.assertTrue(written.exists())
        text = written.read_text(encoding="utf-8")
        self.assertIn("Genre: House", text)
        self.assertNotIn("Tempo:", text)  # "custom" fields are omitted
        self.assertIn("A description.", text)

    def test_malformed_bodies_are_controlled_errors(self):
        directory = self._tmpdir()
        base = {"source": "external_directory", "directory": directory, "file": "x"}
        cases = [
            ("not a dict", "plain text"),
            ("fields not an object", {**base, "fields": "nope"}),
            ("non-string field value", {**base, "fields": {"genre": 3}}),
            ("non-string name", {**base, "file": 5}),
            ("non-boolean overwrite", {**base, "overwrite": "yes"}),
        ]
        for label, body in cases:
            with self.subTest(case=label):
                response = call("POST", SAVE_PROMPT[1], None, body)
                self.assertEqual(response.status, 400, (label, response.payload))
                self.assertFalse(response.payload["ok"])

    def test_invalid_json_is_a_controlled_error(self):
        response = call("POST", SAVE_PROMPT[1], None, None, bad_json=True)
        self.assertEqual(response.status, 400)
        self.assertFalse(response.payload["ok"])

    def test_duplicate_name_without_overwrite_is_rejected(self):
        directory = self._tmpdir()
        body = {
            "source": "external_directory", "directory": directory, "file": "Dupe",
            "fields": {}, "description": "x",
        }
        self.assertEqual(call("POST", SAVE_PROMPT[1], None, body).status, 200)
        second = call("POST", SAVE_PROMPT[1], None, body)
        self.assertEqual(second.status, 400)
        self.assertIn("already exists", second.payload["error"])


class SaveSystemPromptRouteTests(unittest.TestCase):
    def test_saves_and_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            response = call("POST", SAVE_SYSTEM_PROMPT[1], None, {
                "source": "external_directory",
                "directory": directory,
                "file": "My System",
                "text": "You are a helpful producer.",
                "overwrite": False,
            })
            self.assertEqual(response.status, 200, response.payload)
            self.assertEqual(response.payload["file"], "_custom/My System.txt")
            text = (Path(directory) / "_custom" / "My System.txt").read_text(encoding="utf-8")
            self.assertEqual(text, "You are a helpful producer.\n")

            bad = call("POST", SAVE_SYSTEM_PROMPT[1], None, {
                "source": "external_directory", "directory": directory,
                "file": "x", "text": 42,
            })
            self.assertEqual(bad.status, 400)


class PromptFilesAndTextRouteTests(unittest.TestCase):
    def test_prompt_files_lists_bundled_library(self):
        response = call("GET", PROMPT_FILES[1], {"kind": "user"})
        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["ok"])
        self.assertIn("electronic/synth-pop-vocal.txt", response.payload["files"])
        self.assertEqual(response.payload["files"], sorted(response.payload["files"], key=str.casefold))

    def test_prompt_text_requires_a_selection(self):
        response = call("GET", PROMPT_TEXT[1], {"kind": "user", "file": ""})
        self.assertEqual(response.status, 400)

    def test_prompt_text_returns_file_text(self):
        response = call("GET", PROMPT_TEXT[1], {
            "kind": "system", "file": "minimax-music3-production.txt",
        })
        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["ok"])
        self.assertIn("MiniMax", response.payload["text"])


if __name__ == "__main__":
    unittest.main()

class CustomPromptContainmentTests(unittest.TestCase):
    """Writes must have the same root protection as reads (F14 / T11)."""

    def _tmpdir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def _body(self, directory, **overrides):
        body = {
            "source": "external_directory",
            "directory": str(directory),
            "file": "Contained",
            "fields": {"genre": "House"},
            "description": "text",
            "overwrite": False,
        }
        body.update(overrides)
        return body

    def test_custom_directory_symlink_escape_is_rejected(self):
        outside = self._tmpdir()
        library = self._tmpdir()
        try:
            os.symlink(outside, library / "_custom", target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("symlinks are not available for this user/platform")
        response = call("POST", SAVE_PROMPT[1], None, self._body(library))
        self.assertEqual(response.status, 400, response.payload)
        self.assertIn("outside the selected library root", response.payload["error"])
        self.assertEqual(list(outside.iterdir()), [], "nothing may be written outside the library")

    def test_existing_target_symlink_is_rejected(self):
        outside_file = self._tmpdir() / "target.txt"
        outside_file.write_text("keep me", encoding="utf-8")
        library = self._tmpdir()
        custom = library / "_custom"
        custom.mkdir()
        try:
            os.symlink(outside_file, custom / "Contained.txt")
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("symlinks are not available for this user/platform")
        response = call("POST", SAVE_PROMPT[1], None, self._body(library, overwrite=True))
        self.assertEqual(response.status, 400, response.payload)
        self.assertIn("symlink", response.payload["error"])
        self.assertEqual(outside_file.read_text(encoding="utf-8"), "keep me")

    def test_overwrite_is_atomic_and_leaves_no_staging_file(self):
        library = self._tmpdir()
        body = self._body(library, overwrite=False)
        self.assertEqual(call("POST", SAVE_PROMPT[1], None, body).status, 200)
        again = call("POST", SAVE_PROMPT[1], None, dict(body, overwrite=True, description="updated"))
        self.assertEqual(again.status, 200, again.payload)
        custom = library / "_custom"
        self.assertEqual(sorted(p.name for p in custom.iterdir()), ["Contained.txt"])
        self.assertIn("updated", (custom / "Contained.txt").read_text(encoding="utf-8"))

    def test_exclusive_creation_rejects_a_racing_file(self):
        library = self._tmpdir()
        custom = library / "_custom"
        custom.mkdir()
        (custom / "Race.txt").write_text("someone else", encoding="utf-8")
        response = call("POST", SAVE_PROMPT[1], None, self._body(library, file="Race"))
        self.assertEqual(response.status, 400, response.payload)
        self.assertIn("already exists", response.payload["error"])
        self.assertEqual((custom / "Race.txt").read_text(encoding="utf-8"), "someone else")

    def test_system_prompt_writes_are_contained_too(self):
        outside = self._tmpdir()
        library = self._tmpdir()
        try:
            os.symlink(outside, library / "_custom", target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("symlinks are not available for this user/platform")
        response = call("POST", SAVE_SYSTEM_PROMPT[1], None, {
            "source": "external_directory", "directory": str(library),
            "file": "Sys", "text": "hi", "overwrite": False,
        })
        self.assertEqual(response.status, 400, response.payload)
        self.assertEqual(list(outside.iterdir()), [])
