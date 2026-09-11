"""Tests for the unified model catalog (IMPROVE-TODO D01).

Pins the catalog promises:

* every configured LLM artifact is expanded, not only ``llm.example``;
* a Hugging Face artifact resolves through the documented rule while an entry
  without repository information stays URL-less instead of inventing one;
* unknown user fields survive normalization, and a config version this build
  does not know is reported rather than half-read;
* the FlashSR group target wins over a diverging per-file target (the runtime
  only opens the standard names in the group folder);
* GGUF discovery classifies projectors, MTP heads and split shards, and a split
  model is offered once with its missing parts visible.

Nothing here downloads anything - the checks resolve paths and URLs only.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_toolkit_modules():
    pkg_name = "_toolkit_model_catalog_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in ("toolkit_logging", "comfy_resources", "model_downloader", "progress_utils", "llm_chat"):
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
llm = MODULES["llm_chat"]


class NormalizeEntriesTests(unittest.TestCase):
    def config(self):
        return {
            "version": 3,
            "llm": {
                "note": "llm note",
                "directory": "models/llm",
                "example": {"name": "example.gguf", "url": "https://example.invalid/example.gguf"},
                "files": [
                    {"name": "second.gguf", "repo_id": "org/repo", "filename": "second.gguf"},
                    {"name": "example.gguf", "url": "https://example.invalid/example.gguf"},
                ],
            }
        }

    def test_every_configured_llm_file_is_expanded_not_only_the_example(self):
        entries = downloader.normalize_model_entries(self.config(), minimax=False, flux2=False, flashsr=False)
        names = [entry["name"] for entry in entries]
        self.assertIn("second.gguf", names)
        self.assertIn("example.gguf", names)
        self.assertEqual(names.count("example.gguf"), 1, "the example must not be added twice")

    def test_llm_entries_default_to_the_group_directory(self):
        entries = downloader.normalize_model_entries(self.config(), minimax=False, flux2=False, flashsr=False)
        for entry in entries:
            self.assertEqual(entry["target"], "models/llm")

    def test_unknown_user_fields_survive_normalization(self):
        config = self.config()
        config["llm"]["files"][0]["my_private_field"] = {"nested": [1, 2, 3]}
        config["llm"]["files"][0]["sha256"] = "a" * 64
        entries = downloader.normalize_model_entries(config, minimax=False, flux2=False, flashsr=False)
        second = next(entry for entry in entries if entry["name"] == "second.gguf")
        self.assertEqual(second["my_private_field"], {"nested": [1, 2, 3]})
        self.assertEqual(second["sha256"], "a" * 64)

    def test_group_note_is_attached_without_overwriting_an_entry_note(self):
        config = self.config()
        config["llm"]["files"][0]["note"] = "own note"
        entries = downloader.normalize_model_entries(config, minimax=False, flux2=False, flashsr=False)
        by_name = {entry["name"]: entry for entry in entries}
        self.assertEqual(by_name["second.gguf"]["note"], "own note")
        self.assertEqual(by_name["example.gguf"]["note"], "llm note")

    def test_flashsr_group_target_wins_over_a_diverging_file_target(self):
        config = {
            "version": 2,
            "flashsr": {
                "weights": {
                    "target": "models/audio/flashsr",
                    "files": [
                        {"name": "student_ldm.pth", "target": "models/elsewhere", "url": "https://example.invalid/a"},
                        {"name": "vae.pth", "url": "https://example.invalid/b"},
                    ],
                }
            },
        }
        entries = downloader.normalize_model_entries(config, minimax=False, flux2=False, llm=False)
        self.assertEqual([entry["target"] for entry in entries], ["models/audio/flashsr"] * 2)

    def test_malformed_entries_are_skipped_not_expanded(self):
        config = {"version": 2, "flashsr": {"weights": {"files": [42, {"name": "ok.pth"}]}}}
        entries = downloader.normalize_model_entries(config, minimax=False, flux2=False, llm=False)
        self.assertEqual([entry["name"] for entry in entries], ["ok.pth"])


class ResolveEntryUrlTests(unittest.TestCase):
    def test_explicit_url_wins(self):
        entry = {"name": "a.pth", "url": "https://example.invalid/a", "repo_id": "org/repo", "filename": "a.pth"}
        self.assertEqual(downloader.resolve_entry_url(entry), "https://example.invalid/a")

    def test_huggingface_model_artifact_is_resolved_by_the_documented_rule(self):
        entry = {"name": "dit.safetensors", "repo_id": "Comfy-Org/MiniMax-Music-3", "filename": "diffusion_models/x.safetensors"}
        self.assertEqual(
            downloader.resolve_entry_url(entry),
            "https://huggingface.co/Comfy-Org/MiniMax-Music-3/resolve/main/diffusion_models/x.safetensors",
        )

    def test_dataset_and_revision_are_honoured(self):
        entry = {
            "name": "w.pth",
            "filename": "w.pth",
            "repo_id": "jakeoneijk/FlashSR_weights",
            "repo_type": "dataset",
            "revision": "abc123",
        }
        self.assertEqual(
            downloader.resolve_entry_url(entry),
            "https://huggingface.co/datasets/jakeoneijk/FlashSR_weights/resolve/abc123/w.pth",
        )

    def test_entry_without_repository_information_stays_urlless(self):
        self.assertEqual(downloader.resolve_entry_url({"name": "a.pth"}), "")
        self.assertEqual(downloader.resolve_entry_url({"filename": "a.pth"}), "")
        # A local file name is not a remote path: without ``filename`` there is
        # no URL to derive, and guessing one would fetch the wrong artifact.
        self.assertEqual(downloader.resolve_entry_url({"name": "a.pth", "repo_id": "org/repo"}), "")

    def test_remote_filename_may_differ_from_the_local_name(self):
        entry = {
            "name": "minimax_music3_dit_fp16.safetensors",
            "filename": "diffusion_models/minimax_music3_dit_fp16.safetensors",
            "repo_id": "Comfy-Org/MiniMax-Music-3",
        }
        self.assertEqual(
            downloader.resolve_entry_url(entry),
            "https://huggingface.co/Comfy-Org/MiniMax-Music-3/resolve/main/"
            "diffusion_models/minimax_music3_dit_fp16.safetensors",
        )

    def test_check_pipeline_uses_the_resolved_url_without_downloading(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = downloader.check_file_entries(
                [
                    {
                        "name": "minimax_music3_dav.safetensors",
                        "filename": "vae/minimax_music3_dav.safetensors",
                        "target": "models/vae",
                        "repo_id": "Comfy-Org/MiniMax-Music-3",
                    }
                ],
                base_path=Path(tmp),
                auto_download=False,
            )
        entry = report[0]
        self.assertEqual(entry["status"], "missing")
        # "missing and auto_download is disabled" proves the derived URL was
        # resolved; an entry without one reports "no download URL configured".
        self.assertEqual(entry["message"], "missing and auto_download is disabled")


class ConfigVersionTests(unittest.TestCase):
    def test_supported_versions_pass(self):
        for version in downloader.SUPPORTED_CONFIG_VERSIONS:
            with self.subTest(version=version):
                self.assertIsNone(downloader.config_version_problem({"version": version}))

    def test_unversioned_config_is_still_readable(self):
        self.assertIsNone(downloader.config_version_problem({"llm": {}}))
        self.assertIsNone(downloader.config_schema_version({}))

    def test_unknown_version_is_reported_not_guessed(self):
        problem = downloader.config_version_problem({"version": 99})
        self.assertIsNotNone(problem)
        self.assertIn("99", problem)
        self.assertIn("not modified", problem)

    def test_shipped_config_is_readable_and_unmodified(self):
        # Reading the shipped catalog must not rewrite it (D01: no automatic
        # overwrite of an existing configuration).
        path = ROOT / "models_config.json"
        before = path.read_bytes()
        config = downloader.load_models_config()
        self.assertIsNone(downloader.config_version_problem(config))
        self.assertEqual(path.read_bytes(), before)


class GgufClassificationTests(unittest.TestCase):
    def test_classification(self):
        cases = {
            "Qwen3.8-27B-UD-IQ3_XXS.gguf": "model",
            "mmproj-F16.gguf": "projector",
            "Qwen-VL-projector-f16.gguf": "projector",
            "vision-encoder-f16.gguf": "projector",
            "model-00001-of-00003.gguf": "shard",
            "Qwen3.8-27B-MTP-Q4.gguf": "mtp",
            "notes.txt": "mtp",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(llm.classify_gguf(name), expected)

    def test_grouping_keeps_projectors_out_of_the_model_list(self):
        grouped = llm.group_gguf_files(
            [
                "Qwen3.8-27B-UD-IQ3_XXS.gguf",
                "mmproj-F16.gguf",
                "Model-00001-of-00002.gguf",
                "Model-00002-of-00002.gguf",
            ]
        )
        self.assertEqual(grouped["models"], ["Qwen3.8-27B-UD-IQ3_XXS.gguf"])
        self.assertEqual(grouped["projectors"], ["mmproj-F16.gguf"])
        self.assertEqual(len(grouped["split_models"]), 1)
        self.assertEqual(grouped["split_models"][0]["name"], "Model-00001-of-00002.gguf")
        self.assertEqual(grouped["split_models"][0]["parts_present"], 2)
        self.assertEqual(grouped["incomplete"], [])

    def test_split_model_with_a_missing_part_is_reported(self):
        grouped = llm.group_gguf_files(["Model-00001-of-00003.gguf", "Model-00003-of-00003.gguf"])
        self.assertEqual(len(grouped["incomplete"]), 1)
        self.assertEqual(grouped["incomplete"][0]["missing_parts"], [2])
        self.assertEqual(grouped["incomplete"][0]["parts_expected"], 3)
        self.assertEqual(grouped["incomplete"][0]["parts_present"], 2)


class ListModelsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        models_dir = Path(self._tmp.name) / "llm"
        models_dir.mkdir(parents=True)
        self.models_dir = models_dir
        for name in (
            "Qwen3.8-27B-UD-IQ3_XXS.gguf",
            "mmproj-F16.gguf",
            "Split-00001-of-00002.gguf",
            "Split-00002-of-00002.gguf",
            "MTP-head-Q4.gguf",
        ):
            (models_dir / name).write_bytes(b"x")
        self._previous = os.environ.get("COMFYUI_MODELS_DIRECTORY")
        os.environ["COMFYUI_MODELS_DIRECTORY"] = self._tmp.name
        self.addCleanup(self._restore_env)
        llm._GGUF_STAT_CACHE.clear()

    def _restore_env(self):
        if self._previous is None:
            os.environ.pop("COMFYUI_MODELS_DIRECTORY", None)
        else:
            os.environ["COMFYUI_MODELS_DIRECTORY"] = self._previous

    def test_only_chat_models_are_offered(self):
        self.assertEqual(llm.list_llm_models(), ["Qwen3.8-27B-UD-IQ3_XXS.gguf", "Split-00001-of-00002.gguf"])

    def test_metadata_cache_is_bounded_and_reports_the_size(self):
        path = self.models_dir / "Qwen3.8-27B-UD-IQ3_XXS.gguf"
        for index in range(llm.GGUF_STAT_CACHE_MAX + 5):
            llm.cached_gguf_size(self.models_dir / f"f{index}.gguf")
        self.assertLessEqual(len(llm._GGUF_STAT_CACHE), llm.GGUF_STAT_CACHE_MAX)
        self.assertEqual(llm.cached_gguf_size(path), 1)

    def test_catalog_target_is_part_of_the_llm_search_path(self):
        # The check node, the downloader and the loader must resolve the same
        # files: a catalog target outside the scanned folder is still found.
        catalog_dir = Path(self._tmp.name) / "custom-llm"
        catalog_dir.mkdir()
        (catalog_dir / "Catalog-Model.gguf").write_bytes(b"x")
        self.patch_attr(
            llm,
            "load_models_config",
            lambda: {
                "version": 3,
                "llm": {"directory": "models/custom-llm", "files": [{"name": "Catalog-Model.gguf"}]},
            },
        )
        self.assertIn("Catalog-Model.gguf", llm.list_llm_models())
        self.assertEqual(llm._find_model_path("Catalog-Model.gguf"), catalog_dir / "Catalog-Model.gguf")

    def test_unknown_config_version_is_reported_and_ignored(self):
        self.patch_attr(llm, "load_models_config", lambda: {"version": 99, "llm": {"files": []}})
        # The folder scan keeps working; the catalog is simply not consulted.
        self.assertIn("Qwen3.8-27B-UD-IQ3_XXS.gguf", llm.list_llm_models())

    def test_missing_file_reports_none_not_zero(self):
        self.assertIsNone(llm.cached_gguf_size(self.models_dir / "nope.gguf"))

    def patch_attr(self, obj, name, value):
        original = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, original)


if __name__ == "__main__":
    unittest.main()
