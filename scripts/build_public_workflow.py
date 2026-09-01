#!/usr/bin/env python3
"""Build a sanitized public example workflow from a local production workflow.

The script deliberately removes personal notes/metadata and replaces utility
nodes that are not required by this toolkit.  It does not alter the production
settings of the audio, MiniMax, FlashSR, artwork, or mastering nodes.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

DEFAULT_USER_PROMPT = (
    "Nordic Folk — haunting, sparse and deeply atmospheric, with an intimate female vocal, "
    "acoustic guitar, bowed strings, wooden flute and subtle frame drum. Cold, mystical landscape "
    "atmosphere with ancient-sounding melodies and restrained production. Lyrics about waiting for "
    "someone who never returned from a journey through the northern wilderness. Poetic, mysterious "
    "and bittersweet. 4–5 minutes."
)

REMOVE_NODE_IDS = {61, 62, 78, 87, 89, 90, 92, 97, 98}
REMOVE_LINK_IDS = {191, 192, 193}


def node_by_id(workflow: dict, node_id: int) -> dict:
    return next(n for n in workflow["nodes"] if n["id"] == node_id)


def widget_named(node: dict, values: dict) -> None:
    node["widgets_values_named"] = values




def normalize_artwork_saver_inputs(workflow: dict) -> None:
    """Keep SaveImageSmartPrefix serialized input slots aligned with INPUT_TYPES.

    ComfyUI validates saved workflow input slots positionally.  The title and
    audio_tags_json sockets were added in v1.0.5, and an incorrectly reordered
    serialized node can make the subsequent widget values appear under the
    wrong inputs (for example collision_mode=True and jpeg_quality='album - title').
    Reorder by stable input name and repair every destination slot accordingly.
    """
    artwork = next((n for n in workflow.get("nodes", []) if n.get("type") == "SaveImageSmartPrefix"), None)
    if artwork is None:
        return

    expected = [
        "image", "filename_prefix", "collision_mode", "create_directories",
        "jpeg_quality", "title", "audio_tags_json", "filename_mode",
    ]
    by_name = {item.get("name"): item for item in artwork.get("inputs", [])}
    if any(name not in by_name for name in expected):
        return

    artwork["inputs"] = [by_name[name] for name in expected]
    links = {link[0]: link for link in workflow.get("links", []) if isinstance(link, list) and len(link) >= 5}
    for slot, item in enumerate(artwork["inputs"]):
        link_id = item.get("link")
        if link_id is not None and link_id in links:
            links[link_id][3] = artwork["id"]
            links[link_id][4] = slot


def build(source: Path, destination: Path, system_prompt_file: Path) -> dict:
    wf = json.loads(source.read_text(encoding="utf-8"))
    system_prompt = system_prompt_file.read_text(encoding="utf-8-sig").strip()
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    release_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "dev"

    wf["nodes"] = [n for n in wf["nodes"] if n["id"] not in REMOVE_NODE_IDS]
    wf["links"] = [l for l in wf["links"] if l[0] not in REMOVE_LINK_IDS]
    normalize_artwork_saver_inputs(wf)

    # Generic output directory. Subdirectory defaults and all processing values stay unchanged.
    n54 = node_by_id(wf, 54)
    n54["widgets_values"][0] = "audio/minimax3/%date:yyyy-MM-dd%/Example Album/"
    n54.setdefault("widgets_values_named", {})["base_output"] = n54["widgets_values"][0]

    # Generic interoperable tags: no private artist/composer/comment data in the public template.
    n63 = node_by_id(wf, 63)
    tags = [
        "Example Artist",
        "Example Album",
        "2026",
        "01",
        "Example Genre",
        "Generated with MiniMax Music Production Toolkit",
        "Example Artist",
        "Example Composer",
    ]
    n63["widgets_values"] = tags
    widget_named(n63, dict(zip(["artist", "album", "year", "track", "genre", "comment", "album_artist", "composer"], tags)))

    # Public toolkit name in reproducibility metadata.
    n57 = node_by_id(wf, 57)
    workflow_name = f"MiniMax Music Production Toolkit {release_version} – Example Workflow"
    if n57.get("widgets_values"):
        n57["widgets_values"][-1] = workflow_name
    n57.setdefault("widgets_values_named", {})["workflow_name"] = workflow_name

    # Turn legacy node 80 into the public file-backed prompt-library configuration while
    # retaining manual fallbacks for backward compatibility.
    n80 = node_by_id(wf, 80)
    n80["title"] = "1a. LLM Prompt Library / Template"
    n80["size"] = [993.25, 1120]
    # Existing required inputs remain first. Add optional file-library controls.
    existing_names = {i["name"] for i in n80.get("inputs", [])}
    optional_inputs = [
        {"localized_name": "user_prompt_source", "name": "user_prompt_source", "type": "COMBO", "widget": {"name": "user_prompt_source"}, "link": None},
        {"localized_name": "user_prompt_directory", "name": "user_prompt_directory", "type": "STRING", "widget": {"name": "user_prompt_directory"}, "link": None},
        {"localized_name": "user_prompt_file", "name": "user_prompt_file", "type": "COMBO", "widget": {"name": "user_prompt_file"}, "link": None},
        {"localized_name": "system_prompt_source", "name": "system_prompt_source", "type": "COMBO", "widget": {"name": "system_prompt_source"}, "link": None},
        {"localized_name": "system_prompt_directory", "name": "system_prompt_directory", "type": "STRING", "widget": {"name": "system_prompt_directory"}, "link": None},
        {"localized_name": "system_prompt_file", "name": "system_prompt_file", "type": "COMBO", "widget": {"name": "system_prompt_file"}, "link": None},
    ]
    n80["inputs"].extend(i for i in optional_inputs if i["name"] not in existing_names)
    n80["widgets_values"] = [
        DEFAULT_USER_PROMPT,
        system_prompt,
        "",
        "bundled_library",
        "",
        "folk/nordic-folk-vocal.txt",
        "bundled_library",
        "",
        "minimax-music3-production.txt",
    ]
    widget_named(n80, {
        "user_prompt": DEFAULT_USER_PROMPT,
        "system_prompt": system_prompt,
        "source_name_override": "",
        "user_prompt_source": "bundled_library",
        "user_prompt_directory": "",
        "user_prompt_file": "folk/nordic-folk-vocal.txt",
        "system_prompt_source": "bundled_library",
        "system_prompt_directory": "",
        "system_prompt_file": "minimax-music3-production.txt",
    })

    # Replace WAS Number-to-Text + Seed and core concatenate with one dependency-free toolkit node.
    new_node_id = max(n["id"] for n in wf["nodes"]) + 1
    new_link_id = max(l[0] for l in wf["links"]) + 1
    session_node = {
        "id": new_node_id,
        "type": "MiniMaxLLMSessionId",
        "pos": [-100, 1080],
        "size": [330, 110],
        "flags": {},
        "order": 21,
        "mode": 0,
        "inputs": [
            {"localized_name": "seed", "name": "seed", "type": "INT", "widget": {"name": "seed"}, "link": None},
            {"localized_name": "prefix", "name": "prefix", "type": "STRING", "widget": {"name": "prefix"}, "link": None},
        ],
        "outputs": [
            {"localized_name": "session_id", "name": "session_id", "type": "STRING", "links": [new_link_id]},
            {"localized_name": "seed", "name": "seed", "type": "INT", "links": []},
        ],
        "title": "LLM Session ID / Cache Buster",
        "properties": {"Node name for S&R": "MiniMaxLLMSessionId"},
        "widgets_values": [1, "randomize", "song_"],
        "widgets_values_named": {"seed": 1, "control_after_generate": "randomize", "prefix": "song_"},
        "color": "#233",
        "bgcolor": "#355",
    }
    wf["nodes"].append(session_node)
    llm = node_by_id(wf, 81)
    session_input = next(i for i in llm["inputs"] if i["name"] == "session_id")
    session_input["link"] = new_link_id
    session_slot = next(i for i, inp in enumerate(llm["inputs"]) if inp["name"] == "session_id")
    wf["links"].append([new_link_id, new_node_id, 0, 81, session_slot, "STRING"])

    # Public notes explain the library rather than embedding a private prompt collection.
    n39 = node_by_id(wf, 39)
    n39["title"] = "Prompt library + external LLM"
    n39["widgets_values"] = [
        "## Prompt library + external LLM\n\n"
        "`LLM Prompt Library / Template` can use manual text, bundled prompt files, or an external directory. "
        "Bundled examples live in `prompts/user/` and the production system prompt in `prompts/system/`.\n\n"
        "The required LLM output order is `[Caption]` → `[Lyrics]` → `[Title]` → `[Image_Prompt]`. "
        "The parser is deliberately order-tolerant for robustness.\n\n"
        "Connect Template `system_prompt` and `user_prompt` to a compatible external LLM node, then connect its final text to `Parse Structured Music LLM Output`."
    ]
    widget_named(n39, {"text": n39["widgets_values"][0]})

    n40 = node_by_id(wf, 40)
    n40["widgets_values"] = [
        "## Reproducible output + metadata\n\n"
        "The workflow writes the source FLAC plus 44.1 kHz release FLAC/MP3, standard tags, cover art and JSON sidecars. "
        "Audio filenames default to `[Album] - [Title]`, while the embedded Title tag remains the generated song title.\n\n"
        "The public template contains generic metadata. Replace it with your own release metadata before publishing music."
    ]
    widget_named(n40, {"text": n40["widgets_values"][0]})

    # Update release-prep title only; processing/default values are not touched.
    n91 = node_by_id(wf, 91)
    n91["title"] = "Release Prep – 44.1 kHz / STATIC LUFS / True Peak"

    # Remove private/interactive explanatory notes from embedded MiniMax subgraph
    # definitions while leaving all processing/model settings untouched.
    definitions = wf.get("definitions", {})
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []) or []:
            if isinstance(subgraph, dict):
                subgraph["nodes"] = [
                    n for n in subgraph.get("nodes", [])
                    if n.get("type") not in {"Note", "MarkdownNote"}
                ]
                sub_ids = {n.get("id") for n in subgraph.get("nodes", [])}
                # Subgraphs use virtual boundary nodes for their public inputs/outputs.
                # Those boundary IDs are NOT present in subgraph["nodes"], so they must
                # be treated as valid endpoints when sanitizing links. Dropping them
                # produces ComfyUI errors such as:
                #   No link found in parent graph for id [37:6] slot [0] unet_name
                input_boundary_id = (subgraph.get("inputNode") or {}).get("id")
                output_boundary_id = (subgraph.get("outputNode") or {}).get("id")
                valid_endpoints = set(sub_ids)
                if input_boundary_id is not None:
                    valid_endpoints.add(input_boundary_id)
                if output_boundary_id is not None:
                    valid_endpoints.add(output_boundary_id)

                # Definitions may use object-style links rather than the top-level array form.
                cleaned_links = []
                for link in subgraph.get("links", []) or []:
                    if isinstance(link, dict):
                        if link.get("origin_id") not in valid_endpoints or link.get("target_id") not in valid_endpoints:
                            continue
                    cleaned_links.append(link)
                subgraph["links"] = cleaned_links

    wf.setdefault("extra", {})["workflow_name"] = "MiniMax Music Production Toolkit – Example Workflow"
    wf["extra"]["workflow_version"] = release_version

    wf["last_node_id"] = max(n["id"] for n in wf["nodes"])
    wf["last_link_id"] = max(l[0] for l in wf["links"])
    wf["revision"] = int(wf.get("revision", 0)) + 1

    # Remove stale UE link metadata referencing links that no longer exist.
    valid_links = {l[0] for l in wf["links"]}
    extra = wf.get("extra")
    if isinstance(extra, dict):
        for key in ("ue_links", "links_added_by_ue"):
            if isinstance(extra.get(key), list):
                cleaned = []
                for item in extra[key]:
                    if isinstance(item, int) and item not in valid_links:
                        continue
                    cleaned.append(item)
                extra[key] = cleaned

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(wf, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return wf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--system-prompt", type=Path, required=True)
    args = parser.parse_args()
    wf = build(args.source, args.destination, args.system_prompt)
    print(f"Wrote {args.destination}: {len(wf['nodes'])} nodes, {len(wf['links'])} links")


if __name__ == "__main__":
    main()
