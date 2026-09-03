"""Serialized workflow schema migration helpers.

ComfyUI validates stored input slots positionally, so changing the input order
of a node breaks older saved workflows.  In 2.0.0 the parser node
``MiniMaxParseExternalLLMOutputV16`` moved ``structured_llm_output`` from the
first required input to an optional input (so the LLM section can be bypassed
without a validation error).  This module repairs pre-2.0.0 workflows by
remapping link slots by input *name* instead of relying on positions.

The same helpers also report remaining dependencies on external custom nodes,
so release validation can enforce that the bundled workflow is self-contained.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

PARSER_NODE_TYPE = "MiniMaxParseExternalLLMOutputV16"
JSON_NODE_TYPE = "MiniMaxSaveProductionJSON"

# Canonical input order since 2.0.0 (required first, then optional).
PARSER_NEW_INPUT_ORDER = (
    "song_count",
    "seed_mode",
    "base_seed",
    "user_prompt",
    "source_name_override",
    "fallback_title",
    "structured_llm_output",
    "manual_caption",
    "manual_lyrics",
    "manual_title",
    "manual_image_prompt",
    "model_check_report",
    "llm_status",
    "max_prompt_tokens",
    "trim_long_prompt",
)

# Since 2.0.0 ``metadata_json`` moved from the first required input to the
# optional section (the song-metadata node is no longer part of the example
# workflow).
JSON_NEW_INPUT_ORDER = (
    "configuration_prefix",
    "audio_tags_json",
    "title",
    "original_audio_save_json",
    "release_flac_save_json",
    "release_mp3_save_json",
    "artwork_path",
    "collision_mode",
    "filename_mode",
    "create_directories",
    "metadata_json",
    "llm_system_prompt",
    "llm_user_prompt",
    "llm_output",
    "llm_status",
    "llm_thinking",
    "structured_summary_json",
    "caption",
    "lyrics",
    "image_prompt",
    "source_name",
    "source_path",
    "prompt_origin",
    "prompt_provenance_json",
    "generation_seed",
    "run_index",
    "variant_count",
    "max_duration",
    "text_seed",
    "text_cfg_scale",
    "text_top_k",
    "ksampler_seed",
    "ksampler_steps",
    "ksampler_cfg",
    "denoise",
    "flashsr_settings_json",
    "pre_preset",
    "pre_settings_json",
    "post_preset",
    "post_settings_json",
    "hybrid_crossover_json",
    "hf_repair_json",
    "declip_json",
    "release_prep_json",
    "workflow_name",
)

# External custom nodes the toolkit replaced with integrated implementations.
EXTERNAL_NODE_TYPES = {
    "LLMSessionChatNode": "MiniMaxLLMChat (or the legacy external node if you keep it installed)",
    "LLMSessionChatSimpleNode": "MiniMaxLLMChat",
    "LLMDialogueCycleNode": "MiniMaxLLMChat",
    "LLMDialogueCycleSimpleNode": "MiniMaxLLMChat",
    "UnloadLLMModelNode": "MiniMaxLLMUnload",
    "EgregoraAudioUpscaler": "MiniMaxFlashSRAudio",
    "EgregoraAudioEnhancer": "MiniMaxFlashSRAudio",
}


def _node_inputs_are_old_order(node: Dict[str, Any]) -> bool:
    if node.get("type") == PARSER_NODE_TYPE:
        inputs = node.get("inputs") or []
        if not inputs:
            return False
        first_name = inputs[0].get("name")
        return first_name == "structured_llm_output" and first_name != PARSER_NEW_INPUT_ORDER[0]
    if node.get("type") == JSON_NODE_TYPE:
        inputs = node.get("inputs") or []
        if not inputs:
            return False
        first_name = inputs[0].get("name")
        return first_name == "metadata_json" and first_name != JSON_NEW_INPUT_ORDER[0]
    return False


def _input_order_for(node_type: str) -> Optional[Tuple[str, ...]]:
    if node_type == PARSER_NODE_TYPE:
        return PARSER_NEW_INPUT_ORDER
    if node_type == JSON_NODE_TYPE:
        return JSON_NEW_INPUT_ORDER
    return None


def migrate_workflow(workflow: Dict[str, Any]) -> List[str]:
    """Repair pre-2.0.0 parser-node input ordering inside a workflow dict.

    Mutates the workflow in place and returns the list of applied changes.
    Link target slots are remapped by input name; the node's stored ``inputs``
    array is rebuilt in the canonical order.
    """
    changes: List[str] = []
    if not isinstance(workflow, dict):
        return changes

    links = workflow.get("links") or []
    links_by_id = {link[0]: link for link in links if isinstance(link, (list, tuple)) and len(link) >= 5}

    for node in workflow.get("nodes") or []:
        if not isinstance(node, dict) or not _node_inputs_are_old_order(node):
            continue
        node_id = node.get("id")
        node_type = node.get("type")
        order = _input_order_for(node_type)
        if order is None:  # pragma: no cover - guarded by the caller check
            continue
        old_inputs = node.get("inputs") or []
        old_by_name = {item.get("name"): item for item in old_inputs if isinstance(item, dict)}
        old_slot_by_name = {item.get("name"): slot for slot, item in enumerate(old_inputs)}

        # Rebuild the stored inputs array in the canonical order, keeping entries.
        new_inputs = []
        for name in order:
            if name in old_by_name:
                new_inputs.append(old_by_name[name])
        new_slot_by_name = {name: slot for slot, name in enumerate(order)}
        node["inputs"] = new_inputs

        # Remap links that target this node.
        for link in links:
            if len(link) >= 5 and link[3] == node_id:
                old_slot = link[4]
                if not isinstance(old_slot, int) or old_slot >= len(old_inputs):
                    continue
                input_name = old_inputs[old_slot].get("name")
                if input_name in new_slot_by_name:
                    link[4] = new_slot_by_name[input_name]

        changes.append(
            f"migrated node {node_id} ({node_type}): reordered inputs and remapped "
            f"{len([l for l in links if len(l) >= 5 and l[3] == node_id])} inbound link(s) by name"
        )
    return changes


def find_external_node_dependencies(workflow: Dict[str, Any]) -> List[Tuple[Any, str]]:
    """Return ``(node_id, replacement_hint)`` for external-node usages."""
    found: List[Tuple[Any, str]] = []
    for node in workflow.get("nodes") or []:
        node_type = node.get("type") if isinstance(node, dict) else None
        if node_type in EXTERNAL_NODE_TYPES:
            found.append((node.get("id"), EXTERNAL_NODE_TYPES[node_type]))
    return found
