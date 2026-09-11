"""Metadata migration + loader policy tests (F19 / T17)."""
from __future__ import annotations

import copy
import importlib
import json
import tempfile
import unittest
from pathlib import Path

import _toolkit_bootstrap

_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
schema = importlib.import_module(f"{_PACKAGE.__name__}.metadata_schema")
metadata = importlib.import_module(f"{_PACKAGE.__name__}.minimax_metadata")

CURRENT = schema.CURRENT_PRODUCTION_METADATA_SCHEMA
V6 = "minimax_music3_production_metadata_v6"


class V6ToV7Tests(unittest.TestCase):
    def test_migration_does_not_mutate_the_caller_payload(self):
        payload = {"schema": V6, "flashsr": {"pre_lowpass": {"preset": "PRE 10 kHz"}}}
        before = copy.deepcopy(payload)

        migrated, applied = schema.migrate_metadata_payload(payload)

        self.assertEqual(payload, before, "the caller's payload must stay untouched")
        self.assertNotIn("settings", payload["flashsr"], "no nested key may appear on the input")
        self.assertEqual(migrated["schema"], CURRENT)
        self.assertIn("settings", migrated["flashsr"])
        self.assertEqual(migrated["flashsr"]["pre_lowpass"], {"preset": "PRE 10 kHz"})
        self.assertEqual(applied, [CURRENT], "applied lists the schema versions reached")

    def test_migration_adds_v7_defaults(self):
        migrated, _applied = schema.migrate_metadata_payload({"schema": V6})
        self.assertEqual(migrated["llm"], {})
        self.assertEqual(migrated["structured_prompt"], {})
        self.assertEqual(migrated["flashsr"], {"settings": {}})

    def test_current_payload_is_returned_unchanged(self):
        payload = {"schema": CURRENT, "title": "Song"}
        migrated, applied = schema.migrate_metadata_payload(payload)
        self.assertEqual(applied, [])
        self.assertEqual(migrated["title"], "Song")

    def test_unknown_schema_still_raises_for_the_writer_path(self):
        with self.assertRaises(ValueError) as ctx:
            schema.migrate_metadata_payload({"schema": "minimax_music3_production_metadata_v99"})
        self.assertIn("Unknown production metadata schema", str(ctx.exception))


class LoaderPolicyTests(unittest.TestCase):
    def test_known_older_schema_is_migrated(self):
        payload, applied, note = schema.migrate_metadata_payload_if_known({"schema": V6, "title": "Old"})
        self.assertEqual(payload["schema"], CURRENT)
        self.assertEqual(payload["title"], "Old")
        self.assertEqual(note, "")
        self.assertTrue(applied)

    def test_current_schema_is_a_no_op(self):
        payload, applied, note = schema.migrate_metadata_payload_if_known({"schema": CURRENT, "title": "New"})
        self.assertEqual(payload["schema"], CURRENT)
        self.assertEqual((applied, note), ([], ""))

    def test_unversioned_payload_stays_readable(self):
        original = {"title": "Unversioned", "caption": "c"}
        payload, applied, note = schema.migrate_metadata_payload_if_known(original)
        self.assertIs(payload, original, "no migration is attempted")
        self.assertEqual(applied, [])
        self.assertIn("no 'schema' field", note)

    def test_unknown_schema_stays_readable_with_a_note(self):
        original = {"schema": "minimax_music3_production_metadata_v99", "title": "Future"}
        payload, applied, note = schema.migrate_metadata_payload_if_known(original)
        self.assertIs(payload, original)
        self.assertEqual(applied, [])
        self.assertIn("unknown schema", note)


class LoaderNodeTests(unittest.TestCase):
    def _write(self, directory: Path, payload: dict) -> str:
        path = directory / "song.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_loads_a_v6_file_and_returns_the_migrated_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {
                "schema": V6,
                "title": "Old Song",
                "caption": "A caption",
                "lyrics": "la",
                "minimax_music3": {"max_duration": 123.0, "ksampler": {"steps": 17}},
            })
            out = metadata.MiniMaxMetadataLoader().load(path)
            self.assertEqual(out[0], "Old Song")
            self.assertEqual(out[4], 123.0)
            self.assertEqual(out[10], 17)
            returned = json.loads(out[17])
            self.assertEqual(returned["schema"], CURRENT)
            self.assertEqual(returned["flashsr"]["settings"], {})

    def test_loads_an_unversioned_file_without_rejecting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"title": "Plain", "caption": "c", "lyrics": "l"})
            out = metadata.MiniMaxMetadataLoader().load(path)
            self.assertEqual(out[0], "Plain")
            returned = json.loads(out[17])
            self.assertNotIn("schema", returned, "an unversioned file must not gain a schema")

    def test_loads_an_unknown_schema_file_without_rejecting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"schema": "future_v99", "title": "Future"})
            out = metadata.MiniMaxMetadataLoader().load(path)
            self.assertEqual(out[0], "Future")
            self.assertEqual(json.loads(out[17])["schema"], "future_v99")

    def test_empty_path_is_rejected(self):
        with self.assertRaises(ValueError):
            metadata.MiniMaxMetadataLoader().load("   ")


class LoaderFingerprintTests(unittest.TestCase):
    def test_fingerprint_tracks_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "song.json"
            path.write_text('{"title": "A"}', encoding="utf-8")
            first = metadata.MiniMaxMetadataLoader.IS_CHANGED(str(path))
            same = metadata.MiniMaxMetadataLoader.IS_CHANGED(str(path))
            self.assertEqual(first, same)
            path.write_text('{"title": "B"}', encoding="utf-8")
            self.assertNotEqual(first, metadata.MiniMaxMetadataLoader.IS_CHANGED(str(path)))

    def test_fingerprint_is_deterministic_for_a_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "nope.json")
            first = metadata.MiniMaxMetadataLoader.IS_CHANGED(missing)
            self.assertEqual(first, metadata.MiniMaxMetadataLoader.IS_CHANGED(missing))
            self.assertTrue(first.startswith("unreadable:"))

    def test_empty_path_fingerprint(self):
        self.assertEqual(metadata.MiniMaxMetadataLoader.IS_CHANGED("  "), "empty")


if __name__ == "__main__":
    unittest.main()
