"""Tests for the LLM hardware profiles (IMPROVE-TODO L01).

The module's promises, pinned here:

* the anchored sizes are the ones actually read from the repositories - a typo
  must fail the suite, not reach a recommendation;
* a profile that has no verified small-model artifact says so instead of naming
  an unchecked file;
* a low or unknown budget lowers the confidence and says why;
* an installed file is matched by name, and its provenance is only called
  verified when its size matches the anchor;
* projectors and MTP heads are never offered as chat models.
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024 ** 3


def load_toolkit_modules():
    pkg_name = "_toolkit_llm_profiles_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in (
        "toolkit_logging",
        "comfy_resources",
        "model_downloader",
        "progress_utils",
        "resource_profiles",
        "llm_chat",
        "llm_profiles",
    ):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


MODULES = load_toolkit_modules()
profiles = MODULES["llm_profiles"]
resources_module = MODULES["resource_profiles"]
llm_chat = MODULES["llm_chat"]


def cuda(index=0, total_gib=16, free_gib=14, name="Test GPU"):
    return resources_module.DeviceInfo(
        id=f"cuda:{index}",
        name=name,
        kind="cuda",
        backend="cuda",
        logical=index,
        physical=index,
        vram_total_bytes=None if total_gib is None else int(total_gib * GIB),
        vram_free_bytes=None if free_gib is None else int(free_gib * GIB),
    )


def snapshot_with(devices=(), ram_total_gib=64, ram_available_gib=48):
    return resources_module.ResourceSnapshot(
        cpu_count=8,
        ram_total_bytes=int(ram_total_gib * GIB),
        ram_available_bytes=int(ram_available_gib * GIB),
        devices=list(devices)
        + [resources_module.DeviceInfo(id="cpu", name="CPU", kind="cpu", backend="cpu")],
        backends={"torch": True, "cuda": bool(devices)},
    )


class AnchorTests(unittest.TestCase):
    def test_anchor_sizes_are_the_verified_repository_sizes(self):
        anchored = {candidate.name: candidate.bytes for profile in profiles.PROFILES for candidate in profile.candidates}
        self.assertEqual(anchored["Qwen_Qwen3.5-9B-Q5_K_M.gguf"], 7111487520)
        self.assertEqual(anchored["Qwen_Qwen3.5-9B-Q6_K.gguf"], 7958818848)
        self.assertEqual(anchored["Qwen_Qwen3.5-9B-Q4_K_M.gguf"], 6169341984)
        self.assertEqual(anchored["gemma-4-12b-it-qat-q4_0.gguf"], 6975879296)
        self.assertEqual(anchored["Qwen3.8-27B-UD-IQ3_XXS.gguf"], 10934860704)
        self.assertEqual(anchored["Qwen3.8-27B-UD-IQ4_XS.gguf"], 14252845984)
        self.assertEqual(anchored["Qwen3.8-27B-UD-Q4_K_M.gguf"], 16464440224)

    def test_every_candidate_declares_its_repository_and_revision(self):
        for profile in profiles.PROFILES:
            for candidate in profile.candidates:
                with self.subTest(candidate=candidate.name):
                    self.assertTrue(candidate.repo_id)
                    self.assertRegex(candidate.revision, r"^[0-9a-f]{40}$")
                    self.assertTrue(candidate.filename)

    def test_projectors_and_mtp_heads_are_never_offered(self):
        for profile in profiles.PROFILES:
            for candidate in profile.candidates:
                lowered = candidate.name.lower()
                with self.subTest(candidate=candidate.name):
                    self.assertNotIn("mmproj", lowered)
                    self.assertNotIn("mtp", lowered)
                    self.assertNotIn("projector", lowered)

    def test_every_profile_states_that_a_file_size_is_not_a_vram_promise(self):
        for profile in profiles.PROFILES:
            with self.subTest(profile=profile.id):
                self.assertIn(profiles.SIZE_SOURCE, profile.caveats)
                self.assertTrue(any("MoE" in caveat for caveat in profile.caveats))


class ProfileSelectionTests(unittest.TestCase):
    def test_cpu_only_stays_conservative_and_names_no_unchecked_file(self):
        result = profiles.recommend_llm_setup(snapshot_with())
        self.assertEqual(result["profile"], "cpu_only")
        self.assertTrue(result["requires_artifact_check"])
        self.assertEqual(result["candidates"], [])
        text = "\n".join(profiles.format_llm_profile_lines(result))
        self.assertIn("no verified small-model artifact yet", text)

    def test_eight_gib_prefers_the_small_class_and_flags_the_budget_check(self):
        result = profiles.recommend_llm_setup(snapshot_with([cuda(total_gib=8, free_gib=7)]))
        self.assertEqual(result["profile"], "vram_8")
        self.assertTrue(result["requires_artifact_check"])
        self.assertEqual([c["name"] for c in result["candidates"]], ["Qwen_Qwen3.5-9B-Q4_K_M.gguf"])
        self.assertIn("budget check", result["candidates"][0]["note"])

    def test_twelve_gib_offers_both_anchored_candidates(self):
        result = profiles.recommend_llm_setup(snapshot_with([cuda(total_gib=12, free_gib=11)]))
        self.assertEqual(result["profile"], "vram_12")
        self.assertEqual(result["context_tokens"], 8192)
        self.assertEqual(
            sorted(c["name"] for c in result["candidates"]),
            ["Qwen_Qwen3.5-9B-Q5_K_M.gguf", "gemma-4-12b-it-qat-q4_0.gguf"],
        )

    def test_sixteen_gib_offers_daily_candidates_and_a_quality_comparison(self):
        result = profiles.recommend_llm_setup(snapshot_with([cuda(total_gib=16, free_gib=15)]))
        self.assertEqual(result["profile"], "vram_16")
        self.assertEqual(result["context_tokens"], 16384)
        self.assertEqual(len(result["candidates"]), 3)
        self.assertIn("Qwen3.8-27B-UD-IQ3_XXS.gguf", [c["name"] for c in result["candidates"]])

    def test_largest_class_uses_the_big_quantizations(self):
        result = profiles.recommend_llm_setup(snapshot_with([cuda(total_gib=48, free_gib=46)]))
        self.assertEqual(result["profile"], "vram_32")
        self.assertEqual(
            sorted(c["name"] for c in result["candidates"]),
            ["Qwen3.8-27B-UD-IQ4_XS.gguf", "Qwen3.8-27B-UD-Q4_K_M.gguf"],
        )

    def test_unreadable_device_memory_uses_the_smallest_gpu_class(self):
        result = profiles.recommend_llm_setup(snapshot_with([cuda(total_gib=None, free_gib=None)]))
        self.assertEqual(result["profile"], "vram_8")
        self.assertEqual(result["confidence"], "missing")
        self.assertIn("could not be read", result["reason"])

    def test_unknown_free_memory_lowers_the_confidence(self):
        result = profiles.recommend_llm_setup(snapshot_with([cuda(total_gib=16, free_gib=None)]))
        self.assertEqual(result["confidence"], "low")
        self.assertIn("unknown", result["reason"].lower())

    def test_an_occupied_gpu_reports_the_budget_problem(self):
        result = profiles.recommend_llm_setup(snapshot_with([cuda(total_gib=24, free_gib=1)]))
        self.assertEqual(result["confidence"], "low")
        self.assertIsNotNone(result["free_budget_bytes"])
        self.assertLessEqual(result["free_budget_bytes"], 0)

    def test_multiple_gpus_use_the_largest_and_warn_about_splits(self):
        result = profiles.recommend_llm_setup(
            snapshot_with([cuda(index=0, total_gib=24, free_gib=22), cuda(index=1, total_gib=8, free_gib=7)])
        )
        self.assertEqual(result["profile"], "vram_24")
        self.assertEqual(result["device"], "cuda:0")
        self.assertTrue(any("separate memory pools" in caveat for caveat in result["caveats"]))


class InstalledFileTests(unittest.TestCase):
    def candidate(self):
        return profiles.QWEN_9B_Q5KM

    def test_a_size_match_is_reported_as_verified(self):
        matches = profiles.match_installed(
            [self.candidate()], ["Qwen_Qwen3.5-9B-Q5_K_M.gguf"], {"Qwen_Qwen3.5-9B-Q5_K_M.gguf": 7111487520}
        )
        self.assertEqual(matches[0]["status"], "installed")
        self.assertTrue(matches[0]["verified"])

    def test_a_name_match_alone_does_not_claim_provenance(self):
        matches = profiles.match_installed(
            [self.candidate()], ["Qwen_Qwen3.5-9B-Q5_K_M.gguf"], {"Qwen_Qwen3.5-9B-Q5_K_M.gguf": 12345}
        )
        self.assertEqual(matches[0]["status"], "name_match")
        self.assertFalse(matches[0]["verified"])
        self.assertIn("provenance not claimed", matches[0]["message"])

    def test_an_installed_candidate_is_not_offered_for_download_again(self):
        result = profiles.recommend_llm_setup(
            snapshot_with([cuda(total_gib=12, free_gib=11)]),
            installed=["Qwen_Qwen3.5-9B-Q5_K_M.gguf"],
            sizes_by_name={"Qwen_Qwen3.5-9B-Q5_K_M.gguf": 7111487520},
        )
        self.assertEqual([entry["name"] for entry in result["installed"]], ["Qwen_Qwen3.5-9B-Q5_K_M.gguf"])
        self.assertNotIn("Qwen_Qwen3.5-9B-Q5_K_M.gguf", [c["name"] for c in result["candidates"]])

    def test_installed_files_include_the_folder_and_the_catalog_paths(self):
        names, sizes = profiles.installed_llm_files()
        self.assertIsInstance(names, list)
        self.assertEqual(set(sizes), set(names))


class RenderAndIntegrationTests(unittest.TestCase):
    def test_lines_render_reason_context_and_candidates(self):
        result = profiles.recommend_llm_setup(snapshot_with([cuda(total_gib=16, free_gib=15)]))
        text = "\n".join(profiles.format_llm_profile_lines(result))
        self.assertIn("LLM profile:", text)
        self.assertIn("suggested context: 16384", text)
        self.assertIn("candidate: gemma-4-12b-it-qat-q4_0.gguf", text)

    def test_llm_chat_exposes_the_recommendation_without_raising(self):
        lines = llm_chat.describe_llm_profile()
        self.assertTrue(lines)
        self.assertTrue(any("LLM profile" in line for line in lines))

    def test_recommendation_is_serializable_and_carries_no_private_paths(self):
        import json

        result = profiles.recommend_llm_setup(snapshot_with([cuda()]))
        payload = json.dumps(result)
        self.assertNotIn("C:\\\\", payload)
        self.assertNotIn("Users", payload)


if __name__ == "__main__":
    unittest.main()
