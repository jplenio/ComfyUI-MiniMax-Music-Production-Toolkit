from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "example_workflows" / "MiniMax_Music3_Production_Toolkit.json"

# Toolkit node type -> defining module, for every toolkit node in the bundled
# workflow.  ComfyUI-core types (loaders, samplers, ...) and the embedded
# MiniMax subgraph instance are covered separately or intentionally skipped.
NODE_MODULE = {
    "SaveAudioSmartPrefix": "save_audio_smart_prefix",
    "FlashSRLowpassLab": "audio_lowpass",
    "MiniMaxSquareImageSize": "minimax_artwork",
    "MiniMaxFlashSRAudio": "flashsr_audio",
    "MiniMaxParseExternalLLMOutputV16": "minimax_prompt_source",
    "MiniMaxOutputPaths": "minimax_batch",
    "MiniMaxMusic3GenerationSettings": "minimax_settings",
    "FlashSRProcessingSettings": "minimax_settings",
    "MiniMaxSongMetadata": "minimax_metadata",
    "MiniMaxMetadataLoader": "minimax_metadata",
    "MiniMaxStandardAudioTags": "minimax_audio_tags",
    "SaveImageSmartPrefix": "minimax_artwork",
    "MiniMaxStructuredPromptV20": "minimax_structured_prompt",
    "MiniMaxLLMChat": "llm_chat",
    "MiniMaxLLMUnload": "llm_chat",
    "AudioReleasePrep": "audio_release_prep",
    "FlashSRHybridCrossover": "audio_hf_repair",
    "HFCymbalShimmerRepair": "audio_hf_repair",
    "AudioDeclipRepair": "audio_declip",
    "MiniMaxLLMSessionId": "session_utils",
    "MiniMaxSaveProductionJSON": "minimax_json_output",
    "MiniMaxModelAutodownload": "minimax_autodownload",
}

# ComfyUI core nodes legitimately used by the public workflow; their schema is
# owned by ComfyUI, not this toolkit.
CORE_NODE_TYPES = {
    "UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode", "ConditioningZeroOut",
    "CFGGuider", "RandomNoise", "KSamplerSelect", "Flux2Scheduler",
    "EmptyFlux2LatentImage", "SamplerCustomAdvanced", "VAEDecode", "MarkdownNote",
}

# Order dependencies: toolkit_logging first, then anything using it.
MODULE_NAMES = (
    "toolkit_logging",
    "filename_utils",
    "prompt_library",
    "prompt_metadata",
    "prompt_budget",
    "model_downloader",
    "minimax_prompt_source",
    "minimax_structured_prompt",
    "llm_chat",
    "flashsr_audio",
    "minimax_autodownload",
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
        cls.wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        cls.workflow_nodes = cls.wf["nodes"]
        cls.subgraph_types = {
            subgraph.get("id") for subgraph in (cls.wf.get("definitions") or {}).get("subgraphs", []) or []
        }

    def test_every_workflow_node_has_a_known_owner(self):
        for node in self.workflow_nodes:
            node_type = node.get("type")
            if node_type in NODE_MODULE or node_type in CORE_NODE_TYPES or node_type in self.subgraph_types:
                continue
            self.fail(
                f"Workflow node type '{node_type}' (id {node.get('id')}) is neither a toolkit "
                "node (add it to NODE_MODULE), a documented ComfyUI core type "
                "(add it to CORE_NODE_TYPES), nor an embedded subgraph instance."
            )

    def test_serialized_input_order_matches_input_types(self):
        # The frontend serializes inputs as two ordered groups: socket-only
        # inputs first (entries without a "widget" key), then widget inputs.
        # Within each group the definition order must be preserved, and the
        # name set must match INPUT_TYPES exactly - otherwise link slot
        # indexes in older saved workflows land on the wrong inputs.
        for node in self.workflow_nodes:
            node_type = node.get("type")
            if node_type not in NODE_MODULE:
                continue
            module = MODULES[NODE_MODULE[node_type]]
            cls = module.NODE_CLASS_MAPPINGS[node_type]
            data = cls.INPUT_TYPES()
            expected = list(data.get("required", {}).keys()) + list(data.get("optional", {}).keys())
            entries = node.get("inputs", [])
            actual = [item.get("name") for item in entries]
            self.assertEqual(
                sorted(actual), sorted(expected),
                f"{node_type} (id {node.get('id')}): serialized input names drifted from INPUT_TYPES.",
            )
            sockets_actual = [item.get("name") for item in entries if "widget" not in item]
            widgets_actual = [item.get("name") for item in entries if "widget" in item]
            expected_sockets = [name for name in expected if name in sockets_actual]
            expected_widgets = [name for name in expected if name in widgets_actual]
            self.assertEqual(
                sockets_actual, expected_sockets,
                f"{node_type} (id {node.get('id')}): socket-input order drifted from INPUT_TYPES.",
            )
            self.assertEqual(
                widgets_actual, expected_widgets,
                f"{node_type} (id {node.get('id')}): widget-input order drifted from INPUT_TYPES.",
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
