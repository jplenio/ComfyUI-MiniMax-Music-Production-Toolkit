from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module(fullname: str, path: Path):
    spec = importlib.util.spec_from_file_location(fullname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ProductionJSONTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pkg = types.ModuleType("minimax_toolkit_testpkg")
        pkg.__path__ = [str(ROOT)]
        sys.modules[pkg.__name__] = pkg
        _load_module(f"{pkg.__name__}.toolkit_logging", ROOT / "toolkit_logging.py")
        _load_module(f"{pkg.__name__}.filename_utils", ROOT / "filename_utils.py")
        _load_module(f"{pkg.__name__}.save_audio_smart_prefix", ROOT / "save_audio_smart_prefix.py")
        cls.mod = _load_module(f"{pkg.__name__}.minimax_json_output", ROOT / "minimax_json_output.py")
        cls.schema_mod = _load_module(f"{pkg.__name__}.metadata_schema", ROOT / "metadata_schema.py")

    def test_canonical_json_is_written_and_contains_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artwork = root / "cover.jpg"
            artwork.write_bytes(b"demo")
            prefix = root / "json" / "source"

            node = self.mod.MiniMaxSaveProductionJSON()
            saved_path, rendered = node.save(
                metadata_json=json.dumps({"schema": "test", "title": "Track"}),
                configuration_prefix=str(prefix),
                audio_tags_json=json.dumps({"album": "Album", "title": "Track", "artist": "Artist"}),
                title="Track",
                original_audio_save_json=json.dumps({"path": str(root / "original.flac"), "format": "flac"}),
                release_flac_save_json=json.dumps({"path": str(root / "release.flac"), "format": "flac"}),
                release_mp3_save_json=json.dumps({"path": str(root / "release.mp3"), "format": "mp3"}),
                artwork_path=str(artwork),
                collision_mode="auto_increment",
                filename_mode="album - title",
                create_directories=True,
            )

            saved = Path(saved_path)
            self.assertTrue(saved.exists())
            self.assertEqual(saved.name, "Album - Track.json")
            data = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual(data["standard_audio_tags"]["album"], "Album")
            self.assertEqual(data["outputs"]["release_mp3"]["format"], "mp3")
            self.assertEqual(Path(data["outputs"]["artwork"]["path"]), artwork.resolve())
            self.assertEqual(json.loads(rendered)["outputs"]["configuration"]["file"], "Album - Track.json")

    def test_minimax_prompt_report_is_written_next_to_the_json(self):
        # The MiniMax prompt report is written as "Album - Title.md" with the
        # same basename as the canonical JSON, and recorded in the payload.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            node = self.mod.MiniMaxSaveProductionJSON()
            report = "# MiniMax Music 3 - Prompt Report\n\n```\nfinal prompt\n```\n"
            saved_path, rendered = node.save(
                configuration_prefix=str(root / "json" / "source"),
                audio_tags_json=json.dumps({"album": "Album", "title": "Track"}),
                title="Track",
                original_audio_save_json=json.dumps({"path": str(root / "original.flac")}),
                release_flac_save_json=json.dumps({"path": str(root / "release.flac")}),
                release_mp3_save_json=json.dumps({"path": str(root / "release.mp3")}),
                artwork_path=str(root / "cover.jpg"),
                collision_mode="auto_increment",
                filename_mode="album - title",
                create_directories=True,
                minimax_prompt_md=report,
            )
            saved = Path(saved_path)
            report_path = saved.with_suffix(".md")
            self.assertTrue(report_path.exists())
            self.assertEqual(report_path.name, "Album - Track.md")
            self.assertIn("final prompt", report_path.read_text(encoding="utf-8"))
            data = json.loads(rendered)
            self.assertEqual(data["outputs"]["prompt_report"]["file"], "Album - Track.md")
            self.assertEqual(Path(data["outputs"]["prompt_report"]["path"]), report_path.resolve())

    def test_no_markdown_file_is_written_without_prompt_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            node = self.mod.MiniMaxSaveProductionJSON()
            saved_path, rendered = node.save(
                configuration_prefix=str(root / "json" / "source"),
                audio_tags_json=json.dumps({"album": "Album", "title": "Track"}),
                title="Track",
                original_audio_save_json=json.dumps({"path": str(root / "original.flac")}),
                release_flac_save_json=json.dumps({"path": str(root / "release.flac")}),
                release_mp3_save_json=json.dumps({"path": str(root / "release.mp3")}),
                artwork_path=str(root / "cover.jpg"),
                collision_mode="auto_increment",
                filename_mode="album - title",
                create_directories=True,
            )
            self.assertFalse(Path(saved_path).with_suffix(".md").exists())
            self.assertNotIn("prompt_report", json.loads(rendered)["outputs"])

    def test_canonical_json_works_without_metadata_payload(self):
        # metadata_json is optional since 2.0.0; the canonical JSON still
        # records the tags, title and artifacts.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            node = self.mod.MiniMaxSaveProductionJSON()
            saved_path, rendered = node.save(
                configuration_prefix=str(root / "json" / "source"),
                audio_tags_json=json.dumps({"album": "Album", "title": "Track", "artist": "Artist"}),
                title="Track",
                original_audio_save_json=json.dumps({"path": str(root / "original.flac"), "format": "flac"}),
                release_flac_save_json=json.dumps({"path": str(root / "release.flac"), "format": "flac"}),
                release_mp3_save_json=json.dumps({"path": str(root / "release.mp3"), "format": "mp3"}),
                artwork_path=str(root / "cover.jpg"),
                collision_mode="auto_increment",
                filename_mode="album - title",
                create_directories=True,
            )
            self.assertTrue(Path(saved_path).exists())
            data = json.loads(rendered)
            self.assertEqual(data["title"], "Track")
            self.assertEqual(data["standard_audio_tags"]["album"], "Album")
            self.assertIn("outputs", data)
            self.assertEqual(data["outputs"]["release_flac"]["format"], "flac")

    def test_complete_generation_record_is_assembled(self):
        # The JSON must contain everything needed to recreate the song: LLM
        # stage, parsed sections, seeds, MiniMax settings and audio reports.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            node = self.mod.MiniMaxSaveProductionJSON()
            _saved, rendered = node.save(
                configuration_prefix=str(root / "json" / "source"),
                audio_tags_json=json.dumps({"album": "Album", "title": "Track"}),
                title="Track",
                original_audio_save_json=json.dumps({"path": str(root / "original.flac")}),
                release_flac_save_json=json.dumps({"path": str(root / "release.flac")}),
                release_mp3_save_json=json.dumps({"path": str(root / "release.mp3")}),
                artwork_path=str(root / "cover.jpg"),
                llm_system_prompt="SYSTEM",
                llm_user_prompt="USER PROMPT",
                llm_output="[Caption]\nLLM caption\n[Lyrics]\n[Intro]\n[Title]\nLLM Song\n[Image_Prompt]\ncover",
                llm_status="LLM ok: chars=42",
                llm_thinking="<think>\nPlan: caption first, then lyrics.\n</think>",
                structured_summary_json=json.dumps({"user_prompt_origin": "house/deep-house.txt"}),
                caption="LLM caption",
                lyrics="[Intro]",
                image_prompt="cover",
                source_name="llm-song",
                source_path="<external_comfyui_llm>",
                prompt_origin="external_comfyui_llm",
                prompt_provenance_json=json.dumps({"source_mode": "external_comfyui_llm"}),
                generation_seed=42,
                run_index=1,
                variant_count=1,
                max_duration=300.0,
                text_seed=42,
                text_cfg_scale=1.7,
                text_top_k=50,
                ksampler_seed=42,
                ksampler_steps=40,
                ksampler_cfg=1.7,
                denoise=1.0,
                flashsr_settings_json=json.dumps({"schema": "flashsr_settings_v1", "inference_sr": 48000}),
                pre_preset="PRE 12 kHz - recommended",
                pre_settings_json=json.dumps({"schema": "x", "cutoff_hz": 12000.0}),
                post_preset="POST 19 kHz - slightly stronger",
                post_settings_json=json.dumps({"schema": "x", "cutoff_hz": 19000.0}),
                hybrid_crossover_json=json.dumps({"schema": "x", "mix": 0.45}),
                hf_repair_json=json.dumps({"schema": "x", "mode": "Gentle"}),
                declip_json=json.dumps({"schema": "x", "repaired": 0}),
                release_prep_json=json.dumps({"schema": "x", "lufs": -14.0}),
            )
            data = json.loads(rendered)
            self.assertEqual(data["schema"], self.mod.CURRENT_PRODUCTION_METADATA_SCHEMA)
            self.assertEqual(data["llm"]["system_prompt"], "SYSTEM")
            self.assertEqual(data["llm"]["user_prompt"], "USER PROMPT")
            self.assertIn("LLM caption", data["llm"]["output"])
            self.assertEqual(data["llm"]["status"], "LLM ok: chars=42")
            # Thinking is recorded separately from the real output.
            self.assertIn("Plan: caption first", data["llm"]["thinking"])
            self.assertNotIn("Plan: caption first", data["llm"]["output"])
            self.assertEqual(data["structured_prompt"]["user_prompt_origin"], "house/deep-house.txt")
            self.assertEqual(data["caption"], "LLM caption")
            self.assertEqual(data["lyrics"], "[Intro]")
            self.assertEqual(data["image_prompt"], "cover")
            self.assertEqual(data["source"]["name"], "llm-song")
            self.assertEqual(data["source"]["origin"], "external_comfyui_llm")
            self.assertEqual(data["generation_seed"], 42)
            self.assertEqual(data["minimax_music3"]["max_duration"], 300.0)
            self.assertEqual(data["minimax_music3"]["text_encode"]["seed"], 42)
            self.assertEqual(data["minimax_music3"]["ksampler"]["steps"], 40)
            self.assertEqual(data["flashsr"]["settings"]["inference_sr"], 48000)
            self.assertEqual(data["flashsr"]["pre_lowpass"]["preset"], "PRE 12 kHz - recommended")
            self.assertEqual(data["flashsr"]["post_lowpass"]["preset"], "POST 19 kHz - slightly stronger")
            self.assertEqual(data["flashsr"]["hybrid_crossover"]["mix"], 0.45)
            self.assertEqual(data["flashsr"]["hf_cymbal_shimmer_repair"]["mode"], "Gentle")
            self.assertEqual(data["restoration"]["declip"]["repaired"], 0)
            self.assertEqual(data["release_prep"]["lufs"], -14.0)
            self.assertIn("outputs", data)


class MetadataSchemaPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pkg = types.ModuleType("minimax_toolkit_testpkg_schema")
        pkg.__path__ = [str(ROOT)]
        sys.modules[pkg.__name__] = pkg
        cls.schema_mod = _load_module(f"{pkg.__name__}.metadata_schema", ROOT / "metadata_schema.py")

    def test_current_schema_payload_passes_through(self):
        current = self.schema_mod.CURRENT_PRODUCTION_METADATA_SCHEMA
        payload, applied = self.schema_mod.migrate_metadata_payload({"schema": current, "title": "x"})
        self.assertEqual(applied, [])
        self.assertEqual(payload["schema"], current)

    def test_registered_migration_runs_and_sets_next_schema(self):
        mod = self.schema_mod
        saved = dict(mod.PRODUCTION_METADATA_MIGRATIONS)
        try:
            def _v5_to_v6(payload):
                payload = dict(payload)
                payload["renamed"] = payload.pop("old_name", "")
                payload["schema"] = mod.CURRENT_PRODUCTION_METADATA_SCHEMA
                return payload

            mod.register_metadata_migration("minimax_music3_production_metadata_v5", _v5_to_v6)
            payload, applied = mod.migrate_metadata_payload({
                "schema": "minimax_music3_production_metadata_v5", "old_name": "track",
            })
            self.assertEqual(applied, [mod.CURRENT_PRODUCTION_METADATA_SCHEMA])
            self.assertEqual(payload["renamed"], "track")
            self.assertEqual(payload["schema"], mod.CURRENT_PRODUCTION_METADATA_SCHEMA)
        finally:
            mod.PRODUCTION_METADATA_MIGRATIONS.clear()
            mod.PRODUCTION_METADATA_MIGRATIONS.update(saved)

    def test_unknown_schema_raises_instead_of_silent_reinterpretation(self):
        with self.assertRaises(ValueError):
            self.schema_mod.migrate_metadata_payload({"schema": "made_up_schema_v9"})

    def test_missing_schema_raises(self):
        with self.assertRaises(ValueError):
            self.schema_mod.migrate_metadata_payload({"title": "no schema"})

    def test_non_dict_payload_raises(self):
        with self.assertRaises(ValueError):
            self.schema_mod.migrate_metadata_payload([1, 2, 3])


if __name__ == "__main__":
    unittest.main()
