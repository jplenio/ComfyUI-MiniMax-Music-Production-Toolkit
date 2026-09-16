"""Serialized workflow schema migration helpers.

ComfyUI resolves stored input slots positionally: a serialized link's
``target_slot`` indexes the target node's stored ``inputs`` array, and the
frontend re-derives that array from the node definition when a graph is
loaded.  Changing the input order of a node therefore breaks older saved
workflows.

In 2.0.0 the parser node ``MiniMaxParseExternalLLMOutputV16`` moved
``structured_llm_output`` from the first required input to an optional input
(so the LLM section can be bypassed without a validation error), and
``MiniMaxSaveProductionJSON`` moved ``metadata_json`` from the first required
input to the optional section.  This module repairs such workflows by
remapping link slots **by input name** instead of relying on positions.

Repair rules (identical to ``web/migration_utils.js``):

* The stored ``inputs`` array is rebuilt group-aware - socket inputs first,
  widget inputs second, each in canonical definition order - which is exactly
  the serialization ComfyUI's frontend produces.  Rebuilding is idempotent, so
  current workflows stay untouched.
* Unknown/future input entries are preserved in their original group; nothing
  is dropped.
* A link is only moved when the slot it currently targets cannot be the input
  it was wired to (a STRING link on a non-STRING slot for the parser; a link
  whose origin output is named ``metadata_json`` for the JSON node).  A slot
  is never written outside ``range(len(inputs))``; unresolvable links are
  reported instead of being guessed.
* Traversal covers the top-level graph *and* ``definitions.subgraphs``, whose
  links are object-form rather than array-form.

The same helpers report remaining dependencies on external custom nodes, so
release validation can enforce that the bundled workflow is self-contained.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple

PARSER_NODE_TYPE = "MiniMaxParseExternalLLMOutputV16"
JSON_NODE_TYPE = "MiniMaxSaveProductionJSON"
PARSER_STRUCTURED_INPUT = "structured_llm_output"
JSON_METADATA_INPUT = "metadata_json"

# Canonical *definition* order since 2.0.0 (required first, then optional).
# The stored serialization regroups these into socket inputs first and widget
# inputs second; both groups follow this order.
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
    # 2.6.0: the parser reads the selected song model from this wire to name the
    # expected section in errors/provenance and to enforce that model's own hard
    # prompt limit.  Appended last so every stored link slot keeps its index.
    "model_profile_json",
    "cover_source_json",
    "structured_summary_json",
)

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
    # Since 2.0.4 the canonical JSON writer also emits the MiniMax prompt
    # report as a Markdown file next to the JSON.
    "minimax_prompt_md",
    # Since V01 the writer also accepts the additive report inputs.  They are
    # appended after every existing entry on purpose: the stored workflow keeps
    # its link slots, and the public workflow carries them unlinked because the
    # production graph has no EQ/mastering stage yet (the new audio-only
    # workflows wire them).
    "eq_report_json",
    "auto_eq_analysis_json",
    "mastering_json",
    "resource_profile_json",
    "llm_runtime_json",
    "model_identity_json",
    "template_version",
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


class Link:
    """Read-only view over one serialized link (array or object form)."""

    __slots__ = ("raw", "object_form", "id", "origin_id", "origin_slot", "target_id", "target_slot", "type")

    def __init__(self, raw: Any):
        self.raw = raw
        self.object_form = isinstance(raw, dict)
        if self.object_form:
            self.id = raw.get("id")
            self.origin_id = raw.get("origin_id")
            self.origin_slot = raw.get("origin_slot")
            self.target_id = raw.get("target_id")
            self.target_slot = raw.get("target_slot")
            self.type = raw.get("type")
        elif isinstance(raw, (list, tuple)) and len(raw) >= 5:
            self.id = raw[0]
            self.origin_id = raw[1]
            self.origin_slot = raw[2]
            self.target_id = raw[3]
            self.target_slot = raw[4]
            self.type = raw[5] if len(raw) > 5 else None
        else:
            raise ValueError("unsupported link shape")

    def set_target_slot(self, slot: int) -> None:
        if self.object_form:
            self.raw["target_slot"] = slot
        else:  # list/tuple: the caller supplies a list
            self.raw[4] = slot

    @property
    def target_slot_index(self) -> Optional[int]:
        if isinstance(self.target_slot, bool):
            return None
        return self.target_slot if isinstance(self.target_slot, int) else None


def _iter_graphs(workflow: Any) -> Iterator[Dict[str, Any]]:
    """Yield the graph itself and every nested subgraph definition."""
    if not isinstance(workflow, dict):
        return
    yield workflow
    definitions = workflow.get("definitions")
    if not isinstance(definitions, dict):
        return
    for subgraph in definitions.get("subgraphs") or []:
        if isinstance(subgraph, dict):
            yield from _iter_graphs(subgraph)


def _iter_links(graph: Dict[str, Any]) -> Iterator[Link]:
    for raw in graph.get("links") or []:
        try:
            yield Link(raw)
        except ValueError:
            continue


def _node_by_id(graph: Dict[str, Any]) -> Dict[Any, Dict[str, Any]]:
    return {
        node.get("id"): node
        for node in graph.get("nodes") or []
        if isinstance(node, dict) and node.get("id") is not None
    }


def _origin_output_name(graph: Dict[str, Any], link: Link, nodes: Dict[Any, Dict[str, Any]]) -> Optional[str]:
    origin = nodes.get(link.origin_id)
    if not isinstance(origin, dict):
        return None
    outputs = origin.get("outputs") or []
    slot = link.origin_slot
    if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot < len(outputs):
        return None
    entry = outputs[slot]
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    return name if isinstance(name, str) else None


def _rebuild_inputs(entries: List[Dict[str, Any]], canonical: Tuple[str, ...]) -> List[Dict[str, Any]]:
    """Group-aware canonical rebuild that preserves unknown inputs.

    Serialized inputs are grouped socket-first, then widgets, matching the
    ComfyUI frontend.  Known names follow the canonical definition order inside
    their group; unknown/future names keep their original relative order and
    stay in the group they were serialized in.
    """
    known = [entry for entry in entries if entry.get("name") in canonical]
    unknown = [entry for entry in entries if entry.get("name") not in canonical]
    rank = {name: index for index, name in enumerate(canonical)}

    def sort_key(entry: Dict[str, Any]) -> int:
        return rank.get(entry.get("name"), len(canonical))

    def group(entries_in_group: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(entries_in_group, key=sort_key)

    sockets_known = [e for e in known if "widget" not in e]
    widgets_known = [e for e in known if "widget" in e]
    sockets_unknown = [e for e in unknown if "widget" not in e]
    widgets_unknown = [e for e in unknown if "widget" in e]
    return group(sockets_known) + sockets_unknown + group(widgets_known) + widgets_unknown


def _repair_node(
    node: Dict[str, Any],
    graph: Dict[str, Any],
    links: List[Link],
    nodes: Dict[Any, Dict[str, Any]],
    changes: List[str],
    diagnostics: Optional[List[str]] = None,
) -> None:
    node_type = node.get("type")
    if node_type == PARSER_NODE_TYPE:
        canonical = PARSER_NEW_INPUT_ORDER
        wanted_name = PARSER_STRUCTURED_INPUT
    elif node_type == JSON_NODE_TYPE:
        canonical = JSON_NEW_INPUT_ORDER
        wanted_name = JSON_METADATA_INPUT
    else:
        return

    old_inputs = [entry for entry in (node.get("inputs") or []) if isinstance(entry, dict)]
    if not old_inputs:
        return

    # The stored array is the only witness for which input a link was wired to,
    # so capture the slot->name mapping *before* rebuilding.
    old_name_by_slot = [entry.get("name") for entry in old_inputs]
    rebuilt = _rebuild_inputs(old_inputs, canonical)
    slot_by_name: Dict[Any, int] = {}
    for index, entry in enumerate(rebuilt):
        slot_by_name.setdefault(entry.get("name"), index)

    node_id = node.get("id")
    inbound = [link for link in links if link.target_id == node_id]
    wanted_slots = {index for index, name in enumerate(old_name_by_slot) if name == wanted_name}
    already_linked = any(link.target_slot_index in wanted_slots for link in inbound) or any(
        old_inputs[index].get("link") not in (None, 0) for index in wanted_slots
    )

    moved = 0
    skipped: List[str] = []
    for link in inbound:
        slot = link.target_slot_index
        if slot is None:
            skipped.append(f"link {link.id}: non-integer target_slot {link.target_slot!r}")
            continue
        if not 0 <= slot < len(old_inputs):
            skipped.append(f"link {link.id}: target_slot {slot} outside 0..{len(old_inputs) - 1}")
            continue

        intended = old_name_by_slot[slot]
        if node_type == PARSER_NODE_TYPE:
            artifact = (
                link.type == "STRING"
                and intended != wanted_name
                and old_inputs[slot].get("type") != "STRING"
                and not already_linked
            )
        else:
            artifact = (
                _origin_output_name(graph, link, nodes) == JSON_METADATA_INPUT
                and intended != wanted_name
                and not already_linked
            )
        if artifact:
            intended = wanted_name
            already_linked = True

        new_slot = slot_by_name.get(intended)
        if new_slot is None:  # pragma: no cover - unknown names are preserved
            skipped.append(f"link {link.id}: input '{intended}' not present")
            continue
        if new_slot == slot:
            continue
        link.set_target_slot(new_slot)
        if artifact:
            old_inputs[slot]["link"] = None
            rebuilt[new_slot]["link"] = link.id
        moved += 1

    if rebuilt != old_inputs:
        node["inputs"] = rebuilt
    if moved or rebuilt != old_inputs:
        changes.append(
            f"migrated node {node_id} ({node_type}): rebuilt input groups and "
            f"remapped {moved} inbound link slot(s)"
        )
    if skipped and diagnostics is not None:
        diagnostics.extend(
            f"node {node_id} ({node_type}): {note}" for note in skipped
        )


def _remove_llm_session_input(node, graph, changes):
    """Remove only the obsolete session wire, preserving all other slot targets."""
    if node.get("type") != "MiniMaxLLMChat":
        return
    inputs = node.get("inputs") or []
    removed_slots = {i for i, entry in enumerate(inputs) if entry.get("name") == "session_id"}
    if not removed_slots:
        return
    removed_links = set()
    removed_raw = set()
    for link in _iter_links(graph):
        if link.target_id != node.get("id") or link.target_slot_index is None:
            continue
        slot = link.target_slot_index
        if not 0 <= slot < len(inputs):
            continue
        if slot in removed_slots:
            removed_links.add(link.id)
            removed_raw.add(id(link.raw))
        else:
            link.set_target_slot(slot - sum(index < slot for index in removed_slots))
    node["inputs"] = [entry for i, entry in enumerate(inputs) if i not in removed_slots]
    graph["links"] = [raw for raw in graph.get("links", []) if id(raw) not in removed_raw]
    for source in graph.get("nodes", []):
        for output in source.get("outputs", []):
            if output.get("links"):
                output["links"] = [lid for lid in output["links"] if lid not in removed_links]
    for boundary in (graph.get("inputs") or []) + (graph.get("outputs") or []):
        if boundary.get("linkIds"):
            boundary["linkIds"] = [lid for lid in boundary["linkIds"] if lid not in removed_links]
    changes.append(f"migrated node {node.get('id')} (MiniMaxLLMChat): removed obsolete session input; LLM now runs fresh automatically")


def migrate_workflow(workflow: Dict[str, Any], diagnostics: Optional[List[str]] = None) -> List[str]:
    """Repair serialized link slots for the 2.0.0 parser/JSON input reorders.

    Mutates the workflow in place and returns the list of applied changes.
    Valid graphs - including both bundled workflows - produce no changes and
    are left byte-for-byte identical.  Links whose slot cannot be resolved are
    never guessed at; pass a list as *diagnostics* to collect those notes.
    """
    changes: List[str] = []
    for graph in _iter_graphs(workflow):
        for node in graph.get("nodes") or []:
            if isinstance(node, dict):
                _remove_llm_session_input(node, graph, changes)
        nodes = _node_by_id(graph)
        links = list(_iter_links(graph))
        for node in graph.get("nodes") or []:
            if isinstance(node, dict):
                _repair_node(node, graph, links, nodes, changes, diagnostics)
    return changes


def find_external_node_dependencies(workflow: Dict[str, Any]) -> List[Tuple[Any, str]]:
    """Return ``(node_id, replacement_hint)`` for external-node usages."""
    found: List[Tuple[Any, str]] = []
    for graph in _iter_graphs(workflow):
        for node in graph.get("nodes") or []:
            node_type = node.get("type") if isinstance(node, dict) else None
            if node_type in EXTERNAL_NODE_TYPES:
                found.append((node.get("id"), EXTERNAL_NODE_TYPES[node_type]))
    return found
