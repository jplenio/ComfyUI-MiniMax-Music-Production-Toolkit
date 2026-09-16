"""Production-metadata builder tests (F19 / T16).

The payload shape must not change; the caller's dictionaries must.
"""
from __future__ import annotations

import copy
import importlib
import json
import unittest

import _toolkit_bootstrap

_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
builder = importlib.import_module(f"{_PACKAGE.__name__}.production_metadata")
node_module = importlib.import_module(f"{_PACKAGE.__name__}.minimax_json_output")
schema = importlib.import_module(f"{_PACKAGE.__name__}.metadata_schema")


class ParsePolicyTests(unittest.TestCase):
    def test_strict_policy_rejects_malformed_json(self):
        with self.assertRaises(ValueError) as ctx:
            builder.parse_object("{not json", "declip_json")
        self.assertIn("declip_json", str(ctx.exception))
        self.assertEqual(builder.parse_object("", "declip_json"), {})
        with self.assertRaises(ValueError):
            builder.parse_object("[1, 2]", "declip_json")

    def test_tolerant_policy_preserves_unparsable_content(self):
        self.assertEqual(builder.parse_legacy_object(""), {})
        self.assertEqual(builder.parse_legacy_object('{"a": 1}'), {"a": 1})
        self.assertEqual(builder.parse_legacy_object("{not json"), {"raw": "{not json"})
        self.assertEqual(builder.parse_legacy_object("[1, 2]"), {"raw": "[1, 2]"})

    def test_node_wrappers_use_the_shared_policy(self):
        self.assertEqual(node_module._parse_object('{"a": 1}', "x"), {"a": 1})
        with self.assertRaises(ValueError):
            node_module._parse_object("{oops", "x")


class NonMutationTests(unittest.TestCase):
    def test_caller_metadata_is_not_modified(self):
        legacy = {
            "schema": schema.CURRENT_PRODUCTION_METADATA_SCHEMA,
            "llm": {"status": "old"},
            "source": {"name": "old"},
            "minimax_music3": {"ksampler": {"steps": 1}},
            "flashsr": {"settings": {"old": True}},
            "restoration": {"declip": {"old": True}},
            "custom_unknown_field": {"keep": "me"},
        }
        before = copy.deepcopy(legacy)

        payload = builder.build_generation_metadata(
            legacy,
            llm_status="new",
            source_name="fresh",
            ksampler_steps=9,
            flashsr_settings_json=json.dumps({"streaming_safe": True}),
            declip_json=json.dumps({"repaired": 3}),
        )

        self.assertEqual(legacy, before, "the caller's metadata object must stay untouched")
        self.assertEqual(payload["llm"]["status"], "new")
        self.assertEqual(payload["source"]["name"], "fresh")
        self.assertEqual(payload["minimax_music3"]["ksampler"]["steps"], 9)
        self.assertEqual(payload["flashsr"]["settings"], {"streaming_safe": True})
        self.assertEqual(payload["restoration"]["declip"], {"repaired": 3})
        self.assertEqual(payload["custom_unknown_field"], {"keep": "me"})

    def test_nested_legacy_sections_are_copied_not_shared(self):
        legacy = {"restoration": {}}
        payload = builder.build_generation_metadata(legacy, declip_json=json.dumps({"repaired": 1}))
        self.assertEqual(legacy["restoration"], {}, "the nested legacy dict must not gain keys")
        self.assertIsNot(payload["restoration"], legacy["restoration"])

    def test_repeated_calls_are_independent(self):
        legacy = {"restoration": {"declip": {"old": True}}}
        first = builder.build_generation_metadata(legacy, declip_json=json.dumps({"run": 1}))
        second = builder.build_generation_metadata(legacy, declip_json=json.dumps({"run": 2}))
        self.assertEqual(first["restoration"]["declip"], {"run": 1})
        self.assertEqual(second["restoration"]["declip"], {"run": 2})
        self.assertEqual(legacy["restoration"]["declip"], {"old": True})


class PayloadShapeTests(unittest.TestCase):
    def test_schema_is_stamped_and_workflow_defaults(self):
        payload = builder.build_generation_metadata({})
        self.assertEqual(payload["schema"], schema.CURRENT_PRODUCTION_METADATA_SCHEMA)
        self.assertEqual(payload["workflow"], builder.DEFAULT_WORKFLOW_NAME)
        self.assertEqual(node_module.DEFAULT_WORKFLOW_NAME, builder.DEFAULT_WORKFLOW_NAME)

    def test_empty_sections_are_omitted(self):
        payload = builder.build_generation_metadata({})
        for absent in ("llm", "source", "flashsr", "restoration", "release_prep",
                       "structured_prompt", "caption", "generation_seed"):
            self.assertNotIn(absent, payload, f"{absent} must be omitted when empty")

    def test_overlay_skips_blank_values_and_strips_whitespace(self):
        base = {}
        builder.overlay(base, "a", "   ")
        builder.overlay(base, "b", "")
        builder.overlay(base, "c", None)
        builder.overlay(base, "d", " value ")
        self.assertEqual(base, {"d": "value"}, "string values are stripped before storing")

    def test_zero_and_false_values_survive(self):
        payload = builder.build_generation_metadata(
            {}, generation_seed=0, run_index=0, variant_count=0, max_duration=0.0, text_top_k=0, denoise=0.0,
        )
        self.assertEqual(payload["generation_seed"], 0)
        self.assertEqual(payload["source"]["run_index"], 0)
        self.assertEqual(payload["source"]["variant_count"], 0)
        self.assertEqual(payload["minimax_music3"]["max_duration"], 0.0)
        self.assertEqual(payload["minimax_music3"]["text_encode"]["top_k"], 0)
        self.assertEqual(payload["minimax_music3"]["ksampler"]["denoise"], 0.0)

    def test_unknown_legacy_keys_are_preserved(self):
        legacy = {"future_section": {"x": 1}, "schema": "production_metadata_v6"}
        payload = builder.build_generation_metadata(legacy)
        self.assertEqual(payload["future_section"], {"x": 1})
        self.assertEqual(payload["schema"], schema.CURRENT_PRODUCTION_METADATA_SCHEMA)


class AdditiveReportTests(unittest.TestCase):
    """V01: EQ / auto-EQ / mastering / runtime / model sections are additions.

    They must appear only when their input carries content, they must survive the
    schema migrator untouched, and a payload written without them must stay
    exactly as it was.
    """

    EQ_REPORT = json.dumps({"schema": "minimax_eq_report_v1", "bypass": False, "input_peak": 0.9})
    AUTO_EQ_REPORT = json.dumps({"schema": "minimax_auto_eq_report_v1", "applied": False})
    MASTERING_REPORT = json.dumps({"schema": "minimax_mastering_v1", "bypass": False})
    RESOURCE_PROFILE = json.dumps({"recommended": {"profile": "balanced"}, "effective": {"device": "cpu"}})
    LLM_RUNTIME = json.dumps({"model": "local-gguf", "device": "cuda:0", "context": 8192})
    MODEL_IDENTITY = json.dumps({"llm": {"revision": "0" * 40}})

    def _full_payload(self):
        return builder.build_generation_metadata(
            {},
            eq_report_json=self.EQ_REPORT,
            auto_eq_analysis_json=self.AUTO_EQ_REPORT,
            mastering_json=self.MASTERING_REPORT,
            resource_profile_json=self.RESOURCE_PROFILE,
            llm_runtime_json=self.LLM_RUNTIME,
            model_identity_json=self.MODEL_IDENTITY,
            template_version=" minimax-music3-concise v1 ",
        )

    def test_reports_are_stored_verbatim(self):
        payload = self._full_payload()
        self.assertEqual(payload["mastering"]["eq"]["schema"], "minimax_eq_report_v1")
        self.assertIs(payload["mastering"]["auto_eq"]["applied"], False)
        self.assertEqual(payload["mastering"]["chain"]["schema"], "minimax_mastering_v1")
        self.assertEqual(payload["runtime"]["resource_profile"]["effective"]["device"], "cpu")
        self.assertEqual(payload["runtime"]["resource_profile"]["recommended"]["profile"], "balanced")
        self.assertEqual(payload["runtime"]["llm"]["context"], 8192)
        self.assertEqual(payload["models"]["llm"]["revision"], "0" * 40)
        self.assertEqual(payload["llm"]["template_version"], "minimax-music3-concise v1")

    def test_effective_and_recommended_stay_separable(self):
        """The record must not blur what was used with what was suggested."""
        runtime = self._full_payload()["runtime"]["resource_profile"]
        self.assertIn("recommended", runtime)
        self.assertIn("effective", runtime)
        self.assertNotEqual(runtime["recommended"], runtime["effective"])

    def test_sections_are_omitted_when_empty(self):
        payload = builder.build_generation_metadata({})
        for absent in ("mastering", "runtime", "models"):
            self.assertNotIn(absent, payload, f"{absent} must be omitted when empty")
        self.assertNotIn("llm", payload)

    def test_payload_without_new_inputs_gains_no_keys(self):
        legacy = {
            "schema": "minimax_music3_production_metadata_v6",
            "title": "Legacy",
            "flashsr": {"settings": {"mode": "hybrid"}},
        }
        before = copy.deepcopy(legacy)
        payload = builder.build_generation_metadata(legacy)
        self.assertEqual(set(payload), set(before) | {"schema", "workflow"})
        self.assertEqual(legacy, before, "the caller's payload is not modified")

    def test_migration_keeps_the_new_sections(self):
        # The third return value is a *note*, empty when nothing needed doing.
        payload = self._full_payload()
        migrated, steps, note = schema.migrate_metadata_payload_if_known(payload)
        self.assertEqual(steps, [], "a current-schema payload needs no migration step")
        self.assertEqual(note, "")
        self.assertEqual(migrated["mastering"]["eq"]["schema"], "minimax_eq_report_v1")
        self.assertEqual(migrated["runtime"]["llm"]["context"], 8192)
        self.assertEqual(migrated["models"]["llm"]["revision"], "0" * 40)

    def test_old_schema_is_migrated_and_keeps_the_new_sections(self):
        legacy = dict(self._full_payload())
        legacy["schema"] = "minimax_music3_production_metadata_v6"
        migrated, steps, note = schema.migrate_metadata_payload_if_known(legacy)
        self.assertEqual(note, "")
        self.assertEqual(migrated["schema"], schema.CURRENT_PRODUCTION_METADATA_SCHEMA)
        self.assertIn("minimax_music3_production_metadata_v7", steps)
        self.assertEqual(migrated["mastering"]["chain"]["schema"], "minimax_mastering_v1")
        self.assertEqual(migrated["runtime"]["resource_profile"]["effective"]["device"], "cpu")

    def test_node_exposes_the_new_inputs_as_optional_sockets(self):
        inputs = node_module.MiniMaxSaveProductionJSON.INPUT_TYPES()
        optional = inputs["optional"]
        for name in ("eq_report_json", "auto_eq_analysis_json", "mastering_json",
                     "resource_profile_json", "llm_runtime_json", "model_identity_json",
                     "template_version", "artifact_reduction_json"):
            self.assertIn(name, optional, f"{name} missing from the node")
            self.assertTrue(optional[name][1].get("forceInput"), f"{name} must stay a socket")
        names = list(optional)
        # Appended, never inserted: a stored workflow keeps its input slots.
        self.assertEqual(names[-8:], [
            "eq_report_json", "auto_eq_analysis_json", "mastering_json",
            "resource_profile_json", "llm_runtime_json", "model_identity_json",
            "template_version", "artifact_reduction_json",
        ])

class PublicSafePayloadTests(unittest.TestCase):
    """V01: a payload embedded in a public example carries no secrets or paths."""

    # Built from parts so this test file itself stays free of the literal
    # patterns the release privacy scan rejects.
    WINDOWS_FILE = "C:" + "\\" + "Users" + "\\" + "someone" + "\\" + "Music" + "\\" + "Album - Title.flac"
    POSIX_FILE = "/" + "home" + "/someone/out/Album - Title.flac"
    UNC_FILE = "\\\\" + "share" + "\\" + "render" + "\\" + "Album - Title.flac"

    def test_absolute_paths_keep_only_the_tail(self):
        payload = {
            "source": {"path": self.WINDOWS_FILE},
            "outputs": {"original_audio": {"path": self.POSIX_FILE}},
            "artwork": {"path": self.UNC_FILE},
            "note": "saved under " + self.WINDOWS_FILE,
        }
        safe = builder.public_safe_payload(payload)
        rendered = json.dumps(safe)
        self.assertIn("Album - Title.flac", rendered)
        for leaked in ("someone", "C:", "share", "/home"):
            self.assertNotIn(leaked, rendered, f"{leaked!r} leaked into the public payload")

    def test_secret_named_keys_are_dropped(self):
        payload = {
            "source": {"hf_token": "hf_secret", "path": "in.flac"},
            "runtime": {"api_key": "k", "access_token": "t", "authorization": "Bearer x",
                        "device": "cpu"},
            "models": {"llm": {"revision": "r"}},
        }
        safe = builder.public_safe_payload(payload)
        self.assertEqual(safe["source"], {"path": "in.flac"})
        self.assertEqual(safe["runtime"], {"device": "cpu"})
        self.assertEqual(safe["models"], {"llm": {"revision": "r"}})

    def test_input_is_not_modified(self):
        payload = {"source": {"path": self.WINDOWS_FILE}, "hf_token": "x"}
        before = copy.deepcopy(payload)
        builder.public_safe_payload(payload)
        self.assertEqual(payload, before)

    def test_plain_content_survives_unchanged(self):
        payload = {
            "schema": schema.CURRENT_PRODUCTION_METADATA_SCHEMA,
            "caption": "Neon-lit synthwave, 42 tokens",
            "minimax_music3": {"ksampler": {"steps": 32, "cfg": 6.5, "denoise": 1.0}},
            "flags": [True, False, None],
            "counts": {"flac": 3},
        }
        self.assertEqual(builder.public_safe_payload(payload), payload)
        self.assertTrue(builder.contains_private_path(self.POSIX_FILE))
        self.assertFalse(builder.contains_private_path("Album - Title.flac"))


if __name__ == "__main__":
    unittest.main()
