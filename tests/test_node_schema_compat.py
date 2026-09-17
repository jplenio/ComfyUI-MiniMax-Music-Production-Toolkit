from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = [
    ROOT / "example_workflows" / "Music_Production_Toolkit.json",
    ROOT / "example_workflows" / "Music_Production_AudioEnhance.json",
    ROOT / "example_workflows" / "Music_Production_Toolkit.json",
]

# Toolkit node type -> defining module, for every toolkit node in the bundled
# workflow.  ComfyUI-core types (loaders, samplers, ...) and the embedded
# MiniMax subgraph instance are covered separately or intentionally skipped.
NODE_MODULE = {
    "AudioArtifactReduction": "audio_artifact_reduction",
    "MusicCoverSource": "music_cover",
    "MusicCoverTranscription": "music_cover",
    "MusicCoverScore": "music_cover",
    "MusicCoverLyrics": "whisper_lyrics",
    "MusicOptionalCoverPreview": "music_production_control",
    "MusicProductionControl": "music_production_control",
    "MusicOptionalStage": "music_production_control",
    "MusicGeneration": "music_generation",
    "MusicGenerationReceipt": "music_generation",
    "SaveAudioSmartPrefix": "save_audio_smart_prefix",
    "FlashSRLowpassLab": "audio_lowpass",
    "MiniMaxSquareImageSize": "minimax_artwork",
    "MiniMaxFlashSRAudio": "flashsr_audio",
    "MiniMaxParseExternalLLMOutputV16": "minimax_prompt_source",
    "YuE2CoverStudioPlan": "cover_studio",
    "YuE2CoverStudioTransform": "cover_studio",
    "YuE2CoverStudioApply": "cover_studio",
    "MiniMaxInstrumentalVocalCheck": "instrumental_check",
    "MiniMaxInstrumentalPick": "instrumental_check",
    "MiniMaxStyleHint": "style_hint",
    "MiniMaxAudioTagReader": "audio_tag_copy",
    "MiniMaxOutputPaths": "minimax_batch",
    "MiniMaxMusic3GenerationSettings": "minimax_settings",
    "MiniMaxMusicModelSettings": "minimax_settings",
    "MiniMaxMusicModelProfile": "minimax_model_profile",
    "FlashSRProcessingSettings": "minimax_settings",
    "MiniMaxSongMetadata": "minimax_metadata",
    "MiniMaxMetadataLoader": "minimax_metadata",
    "MiniMaxStandardAudioTags": "minimax_audio_tags",
    "SaveImageSmartPrefix": "minimax_artwork",
    "MiniMaxCoverControl": "minimax_artwork",
    "MiniMaxStructuredPromptV20": "minimax_structured_prompt",
    "MiniMaxLLMChat": "llm_chat",
    "MiniMaxSafeAudioDecode": "audio_decode",
    "MiniMaxLLMUnload": "llm_chat",
    "AudioReleasePrep": "audio_release_prep",
    "FlashSRHybridCrossover": "audio_hf_repair",
    "HFCymbalShimmerRepair": "audio_hf_repair",
    "AudioDeclipRepair": "audio_declip",
    "MiniMaxLLMSessionId": "session_utils",
    "MiniMaxSaveProductionJSON": "minimax_json_output",
    "MiniMaxModelAutodownload": "minimax_autodownload",
    "MiniMaxPromptReport": "minimax_prompt_report",
    # Since V01 the Audio Enhancement Lab workflow carries the EQ and mastering
    # stages, so their node types need an owner here too.
    "MiniMaxParametricEQ": "audio_eq",
    "MiniMaxAutoEQAnalyze": "audio_auto_eq",
    "MiniMaxMasteringCompressor": "audio_mastering",
}

# ComfyUI core nodes legitimately used by the public workflows; their schema is
# owned by ComfyUI, not this toolkit.
CORE_NODE_TYPES = {
    "UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode", "ConditioningZeroOut",
    "CFGGuider", "RandomNoise", "KSamplerSelect", "Flux2Scheduler",
    "EmptyFlux2LatentImage", "SamplerCustomAdvanced", "VAEDecode", "MarkdownNote",
    "LoadAudio", "PrimitiveString", "PrimitiveInt", "PreviewImage", "PreviewAudio",
    "ComfySwitchNode",
    # YuE2 support (2.6.0): the YuE2_Production_Toolkit example drives the
    # ComfyUI-core YuE2 nodes plus a checkpoint loader.
    "CheckpointLoaderSimple", "YuE2GenerateMusic", "EmptyYuE2LatentAudio",
    "PrimitiveBoolean",
}

# Order dependencies: toolkit_logging first, then anything using it.
MODULE_NAMES = (
    "audio_artifact_reduction",
    "cover_score",
    "music_cover",
    "whisper_lyrics",
    "music_production_control",
    "music_generation",
    "toolkit_logging",
    "model_profiles",
    "filename_utils",
    "prompt_library",
    "prompt_metadata",
    "prompt_budget",
    "model_downloader",
    "minimax_prompt_source",
    "minimax_structured_prompt",
    "minimax_model_profile",
    "comfy_resources",
    "llm_chat",
    "flashsr_audio",
    "minimax_autodownload",
    "minimax_prompt_report",
    "save_audio_smart_prefix",
    "minimax_json_output",
    "minimax_artwork",
    "minimax_settings",
    "minimax_metadata",
    "minimax_audio_tags",
    "minimax_batch",
    "session_utils",
    "audio_lowpass",
    "audio_hf_repair",
    "audio_declip",
    "audio_release_prep",
    "audio_decode",
    # V01: the Audio Enhancement Lab workflow now carries these stages.
    "audio_eq",
    "audio_auto_eq",
    "audio_mastering",
    # 3.1.0: the Cover Studio, the instrumental vocal check and the tag reader.
    "cover_studio",
    "instrumental_check",
    "audio_tag_copy",
    # 3.1.0: the one style source the studio can read without a dependency cycle.
    "style_hint",
)


def load_toolkit_modules():
    pkg_name = "_toolkit_schema_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in MODULE_NAMES:
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


MODULES = load_toolkit_modules()


class NodeSchemaCompatibilityTests(unittest.TestCase):
    """Snapshot of INPUT_TYPES name/order for every toolkit node in the workflow.

    ComfyUI validates stored input slots positionally, so a reordered or
    renamed input in Python silently breaks older saved workflows.  This test
    pins the serialized workflow input order to the live INPUT_TYPES of each
    node definition.
    """

    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            path.name: json.loads(path.read_text(encoding="utf-8")) for path in WORKFLOWS
        }

    def test_every_workflow_node_has_a_known_owner(self):
        for name, wf in self.workflows.items():
            subgraph_types = {
                subgraph.get("id") for subgraph in (wf.get("definitions") or {}).get("subgraphs", []) or []
            }
            for node in wf["nodes"]:
                node_type = node.get("type")
                if node_type in NODE_MODULE or node_type in CORE_NODE_TYPES or node_type in subgraph_types:
                    continue
                self.fail(
                    f"Workflow '{name}' node type '{node_type}' (id {node.get('id')}) is neither a toolkit "
                    "node (add it to NODE_MODULE), a documented ComfyUI core type "
                    "(add it to CORE_NODE_TYPES), nor an embedded subgraph instance."
                )

    def test_serialized_input_order_matches_input_types(self):
        # The frontend serializes inputs as two ordered groups: socket-only
        # inputs first (entries without a "widget" key), then widget inputs.
        # Within each group the definition order must be preserved, and every
        # contract input must be present - otherwise link slot indexes in older
        # saved workflows land on the wrong inputs.
        for name, wf in self.workflows.items():
            inner_nodes = [node for subgraph in wf.get("definitions", {}).get("subgraphs", [])
                           for node in subgraph.get("nodes", [])]
            for node in wf["nodes"] + inner_nodes:
                node_type = node.get("type")
                if node_type not in NODE_MODULE:
                    continue
                module = MODULES[NODE_MODULE[node_type]]
                cls = module.NODE_CLASS_MAPPINGS[node_type]
                data = cls.INPUT_TYPES()
                expected = list(data.get("required", {}).keys()) + list(data.get("optional", {}).keys())
                entries = node.get("inputs", [])
                actual = [item.get("name") for item in entries]
                # Additive optional switch: legacy analyzer instances omit it
                # and retain enabled=True; optimized instances serialize it.
                if node_type == "MiniMaxAutoEQAnalyze" and "enabled" not in actual:
                    self.assertIs(data["optional"]["enabled"][1]["default"], True)
                    expected.remove("enabled")
                # ComfyUI's audio widget serialises two helper entries next to the
                # value itself (audioUI + upload) as soon as the node declares
                # audio_upload. They are frontend scaffolding, not contract inputs:
                # allowed in a saved workflow, never required by it.
                allowed_extras = set()
                if any(isinstance(spec[1], dict) and spec[1].get("audio_upload")
                       for spec in data.get("required", {}).values() if len(spec) > 1):
                    allowed_extras = {"audioUI", "upload"}
                missing = [n for n in expected if n not in actual]
                unexpected = [n for n in actual if n not in expected and n not in allowed_extras]
                self.assertEqual(
                    missing + unexpected, [],
                    f"{name}: {node_type} (id {node.get('id')}): serialized inputs drifted from "
                    f"INPUT_TYPES (missing={missing}, unexpected={unexpected}).",
                )
                contract = [n for n in expected]
                sockets_actual = [item.get("name") for item in entries if "widget" not in item]
                widgets_actual = [item.get("name") for item in entries
                                  if "widget" in item and item.get("name") not in allowed_extras]
                expected_sockets = [n for n in contract if n in sockets_actual]
                expected_widgets = [n for n in contract if n in widgets_actual]
                self.assertEqual(
                    sockets_actual, expected_sockets,
                    f"{name}: {node_type} (id {node.get('id')}): socket-input order drifted from INPUT_TYPES.",
                )
                self.assertEqual(
                    widgets_actual, expected_widgets,
                    f"{name}: {node_type} (id {node.get('id')}): widget-input order drifted from INPUT_TYPES.",
                )

    def test_required_inputs_are_present_and_optional_inputs_may_be_missing(self):
        # A serialized node may omit optional inputs (ComfyUI fills their
        # defaults), but every required input must be present - otherwise the
        # node cannot be configured.
        for name, wf in self.workflows.items():
            for node in wf["nodes"]:
                node_type = node.get("type")
                if node_type not in NODE_MODULE:
                    continue
                module = MODULES[NODE_MODULE[node_type]]
                cls = module.NODE_CLASS_MAPPINGS[node_type]
                data = cls.INPUT_TYPES()
                required = set(data.get("required", {}))
                serialized = {item.get("name") for item in node.get("inputs", [])}
                missing = required - serialized
                self.assertEqual(
                    missing, set(),
                    f"{name}: {node_type} (id {node.get('id')}) is missing required inputs: {sorted(missing)}",
                )

    def test_optional_inputs_tolerate_omission(self):
        # Required and optional names are disjoint, and a serialization that
        # carries only the required inputs is still a valid subset of the
        # definition's names (optional inputs may be omitted entirely).
        for module_name, module in MODULES.items():
            for node_type, cls in getattr(module, "NODE_CLASS_MAPPINGS", {}).items():
                data = cls.INPUT_TYPES()
                required = list(data.get("required", {}))
                optional = list(data.get("optional", {}))
                self.assertFalse(
                    set(required) & set(optional),
                    f"{node_type}: required and optional input names overlap",
                )
                serialized = set(required)
                self.assertTrue(
                    serialized <= set(required) | set(optional),
                    f"{node_type}: required inputs must be known input names",
                )

    def test_return_names_count_matches_return_types(self):
        for module in set(NODE_MODULE.values()):
            mappings = MODULES[module].NODE_CLASS_MAPPINGS
            for node_type in NODE_MODULE:
                if NODE_MODULE[node_type] != module or node_type not in mappings:
                    continue
                cls = mappings[node_type]
                types_count = len(cls.RETURN_TYPES)
                names_count = len(cls.RETURN_NAMES)
                self.assertEqual(names_count, types_count, node_type)


if __name__ == "__main__":
    unittest.main()
