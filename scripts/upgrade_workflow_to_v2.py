#!/usr/bin/env python3
"""Upgrade the public example workflow from v1.x to v2.0.0.

Replaces the external custom-node dependencies with the integrated toolkit
nodes and rewires the parser for the optional/manual-fallback schema:

- ``MiniMaxLLMTemplateV16`` (id 80) -> ``MiniMaxStructuredPromptV20``
- ``LLMSessionChatNode`` (id 81)      -> ``MiniMaxLLMChat``
- ``UnloadLLMModelNode`` (id 85)      -> ``MiniMaxLLMUnload``
- ``EgregoraAudioUpscaler`` (id 45)   -> ``MiniMaxFlashSRAudio``
- new node 101: ``MiniMaxModelAutodownload`` (report -> parser)

Run this script from the repository root after the Python nodes exist.  It is
idempotent in the sense that it re-derives the node entries every time; make a
backup before experimenting.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "example_workflows" / "MiniMax_Music3_Production_Toolkit.json"
SYSTEM_PROMPT_FILE = ROOT / "prompts" / "system" / "minimax-music3-production.txt"

PLACEHOLDER = "<select a prompt>"
CUSTOM = "custom"
STRUCTURED_FIELDS = ("genre", "tempo", "key", "lyrics", "language", "voice", "theme", "length")


def widget_input(name: str, input_type: str, link=None):
    entry = {
        "localized_name": name,
        "name": name,
        "type": input_type,
        "widget": {"name": name},
        "link": link,
    }
    return entry


def linked_input(name: str, input_type: str, link):
    return {"localized_name": name, "name": name, "type": input_type, "link": link}


def output(name: str, output_type: str, links=None):
    return {"name": name, "type": output_type, "links": links if links is not None else []}


def set_node(workflow, node_id, **updates):
    nodes = {n["id"]: n for n in workflow["nodes"]}
    node = nodes[node_id]
    node.update(updates)
    return node


def find_link(workflow, link_id):
    for link in workflow["links"]:
        if link[0] == link_id:
            return link
    raise SystemExit(f"link {link_id} not found")


def main() -> None:
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8-sig").strip()

    # ---------------------------------------------------------------- node 80
    # MiniMaxLLMTemplateV16 -> MiniMaxStructuredPromptV20 (same id/outputs)
    set_node(
        wf, 80,
        type="MiniMaxStructuredPromptV20",
        title="Structured Song Prompt + System Prompt",
        pos=[380.0, 120.0],
        size=[430, 880],
        inputs=[
            widget_input("user_prompt_source", "COMBO"),
            widget_input("user_prompt_directory", "STRING"),
            widget_input("user_prompt_file", "COMBO"),
            *[widget_input(field, "COMBO") for field in STRUCTURED_FIELDS],
            widget_input("description_override", "STRING"),
            widget_input("system_prompt", "STRING"),
            widget_input("system_prompt_source", "COMBO"),
            widget_input("system_prompt_directory", "STRING"),
            widget_input("system_prompt_file", "COMBO"),
            widget_input("source_name_override", "STRING"),
        ],
        widgets_values=[
            "bundled_library", "", PLACEHOLDER,
            *([CUSTOM] * len(STRUCTURED_FIELDS)),
            "", system_prompt, "manual", "", PLACEHOLDER, "",
        ],
        outputs=[
            output("system_prompt", "STRING", [180, 195]),
            output("user_prompt", "STRING", [188, 178]),
            output("source_name", "STRING", [179]),
            output("structured_summary_json", "STRING"),
        ],
        widgets_values_named={
            "user_prompt_source": "bundled_library", "user_prompt_directory": "",
            "user_prompt_file": PLACEHOLDER,
            **{field: CUSTOM for field in STRUCTURED_FIELDS},
            "description_override": "", "system_prompt": system_prompt,
            "system_prompt_source": "manual", "system_prompt_directory": "",
            "system_prompt_file": PLACEHOLDER, "source_name_override": "",
        },
    )

    # ---------------------------------------------------------------- node 81
    # LLMSessionChatNode -> MiniMaxLLMChat
    set_node(
        wf, 81,
        type="MiniMaxLLMChat",
        title="Integrated LLM Chat (llama.cpp)",
        size=[460, 1500],
        inputs=[
            widget_input("enabled", "BOOLEAN"),
            linked_input("user_text", "STRING", 188),
            linked_input("system_prompt", "STRING", 180),
            linked_input("session_id", "STRING", 210),
            widget_input("model", "COMBO"),
            widget_input("max_tokens", "INT"),
            widget_input("temperature", "FLOAT"),
            widget_input("top_p", "FLOAT"),
            widget_input("n_gpu_layers", "INT"),
            widget_input("n_ctx", "INT"),
            widget_input("reset_session", "BOOLEAN"),
            widget_input("auto_download", "BOOLEAN"),
            widget_input("chat_format", "COMBO"),
            widget_input("thinking", "COMBO"),
            widget_input("top_k", "INT"),
            widget_input("min_p", "FLOAT"),
            widget_input("repeat_penalty", "FLOAT"),
            widget_input("presence_penalty", "FLOAT"),
            widget_input("frequency_penalty", "FLOAT"),
            widget_input("seed", "INT"),
            widget_input("split_mode", "COMBO"),
            widget_input("tensor_split", "STRING"),
            widget_input("main_gpu", "INT"),
            widget_input("tensor_parallel", "BOOLEAN"),
        ],
        widgets_values=[
            True, "Qwen3.8-27B-UD-IQ3_XXS.gguf", 16384, 0.7, 0.8, -1, 32768, True, True,
            "auto", "off", 40, 0.0, 1.1, 0.0, 0.0, -1, "none", "", 0, False,
        ],
        widgets_values_named={
            "enabled": True, "model": "Qwen3.8-27B-UD-IQ3_XXS.gguf", "max_tokens": 16384,
            "temperature": 0.7, "top_p": 0.8, "n_gpu_layers": -1, "n_ctx": 32768,
            "reset_session": True, "auto_download": True,
            "chat_format": "auto", "thinking": "off", "top_k": 40, "min_p": 0.0,
            "repeat_penalty": 1.1, "presence_penalty": 0.0, "frequency_penalty": 0.0,
            "seed": -1, "split_mode": "none", "tensor_split": "", "main_gpu": 0,
            "tensor_parallel": False,
        },
        outputs=[output("text", "STRING", [189]), output("status", "STRING", [221, 226]), output("thinking", "STRING", [254])],
    )

    # ---------------------------------------------------------------- node 85
    # UnloadLLMModelNode -> MiniMaxLLMUnload
    set_node(
        wf, 85,
        type="MiniMaxLLMUnload",
        title="Unload LLM (integrated)",
        size=[300, 110],
        inputs=[
            linked_input("trigger", "*", 189),
            widget_input("unload_now", "BOOLEAN"),
            widget_input("unload_flashsr", "BOOLEAN"),
        ],
        widgets_values=[True, False],
        widgets_values_named={"unload_now": True, "unload_flashsr": False},
        outputs=[output("trigger", "*", [190]), output("released_count", "INT")],
    )

    # ---------------------------------------------------------------- node 45
    # EgregoraAudioUpscaler -> MiniMaxFlashSRAudio
    set_node(
        wf, 45,
        type="MiniMaxFlashSRAudio",
        title="Audio Super Resolution (FlashSR, integrated)",
        inputs=[
            linked_input("audio", "AUDIO", 105),
            widget_input("lowpass_input", "BOOLEAN", link=119),
            widget_input("output_sr", "COMBO"),
            widget_input("auto_download", "BOOLEAN"),
        ],
        widgets_values=[False, "48000", True],
        widgets_values_named={"lowpass_input": False, "output_sr": "48000", "auto_download": True},
        outputs=[output("audio", "AUDIO", [106]), output("settings_json", "STRING", [245])],
    )

    # ---------------------------------------------------------------- node 53
    # Parser: canonical 2.0.0 input order (structured_llm_output is optional).
    set_node(
        wf, 53,
        title="Parse Structured LLM Output (LLM or manual fallback)",
        inputs=[
            widget_input("song_count", "INT"),
            widget_input("seed_mode", "COMBO"),
            widget_input("base_seed", "INT"),
            widget_input("user_prompt", "STRING", link=178),
            widget_input("source_name_override", "STRING", link=179),
            widget_input("fallback_title", "STRING"),
            linked_input("structured_llm_output", "STRING", 190),
            widget_input("manual_caption", "STRING"),
            widget_input("manual_lyrics", "STRING"),
            widget_input("manual_title", "STRING"),
            widget_input("manual_image_prompt", "STRING"),
            widget_input("model_check_report", "STRING", link=220),
            widget_input("llm_status", "STRING", link=221),
            widget_input("max_prompt_tokens", "INT"),
            widget_input("trim_long_prompt", "BOOLEAN"),
        ],
        widgets_values=[
            1, "random_each_song", 1, "llm-song", "", "llm-song", "", "", "", "", "",
            "", 4500, True,
        ],
        widgets_values_named={
            "song_count": 1, "seed_mode": "random_each_song", "base_seed": 1,
            "user_prompt": "llm-song", "source_name_override": "", "fallback_title": "llm-song",
            "manual_caption": "", "manual_lyrics": "", "manual_title": "",
            "manual_image_prompt": "", "model_check_report": "", "llm_status": "",
            "max_prompt_tokens": 4500, "trim_long_prompt": True,
        },
    )

    # ---------------------------------------------------------- new node 101
    node_101 = {
        "id": 101,
        "type": "MiniMaxModelAutodownload",
        "pos": [1019.0, 60.0],
        "size": [320, 200],
        "flags": {},
        "order": 52,
        "mode": 0,
        "title": "Model Auto-Download / Check",
        "inputs": [
            widget_input("minimax_models", "BOOLEAN"),
            widget_input("flux2_models", "BOOLEAN"),
            widget_input("flashsr_models", "BOOLEAN"),
            widget_input("llm_model", "BOOLEAN"),
            widget_input("auto_download", "BOOLEAN"),
        ],
        "outputs": [output("report", "STRING", [220])],
        "properties": {"Node name for S&R": "MiniMaxModelAutodownload"},
        "widgets_values": [True, True, True, True, True],
        "widgets_values_named": {
            "minimax_models": True, "flux2_models": True, "flashsr_models": True,
            "llm_model": True, "auto_download": True,
        },
        "color": "#232",
        "bgcolor": "#353",
    }
    if not any(n.get("id") == 101 for n in wf["nodes"]):
        wf["nodes"].append(node_101)

    # ------------------------------------------------------------ fix links
    # 180: 80.system_prompt -> 81.system_prompt  (slot 5 -> 2)
    find_link(wf, 180)[4] = 2
    # 188: 80.user_prompt -> 81.user_text (slot 1 stays)
    # 210: 97.session_id -> 81.session_id (slot 2 -> 3)
    find_link(wf, 210)[4] = 3
    # 190: 85.trigger -> 53.structured_llm_output (slot 0 -> 6)
    find_link(wf, 190)[4] = 6
    # 178: 80.user_prompt -> 53.user_prompt (slot 4 -> 3)
    find_link(wf, 178)[4] = 3
    # 179: 80.source_name -> 53.source_name_override (slot 5 -> 4)
    find_link(wf, 179)[4] = 4
    # new: 101.report -> 53.model_check_report
    if not any(link[0] == 220 for link in wf["links"]):
        wf["links"].append([220, 101, 0, 53, 11, "STRING"])
    # new: 81.status -> 53.llm_status (upstream LLM diagnostics for the parser)
    if not any(link[0] == 221 for link in wf["links"]):
        wf["links"].append([221, 81, 1, 53, 12, "STRING"])

    # ------------------------------------------ remove legacy setting nodes
    # 56 (FlashSRProcessingSettings) and 57 (MiniMaxSongMetadata) are no longer
    # part of the example workflow: the PRE/POST low-pass values live directly
    # on the low-pass nodes, and the canonical production JSON assembles the
    # complete generation record itself (metadata_json is optional since 2.0.0).
    removed_links = set(range(109, 146)) | {149, 195, 196, 200, 201, 203}
    wf["links"] = [link for link in wf["links"] if link[0] not in removed_links]
    wf["nodes"] = [node for node in wf["nodes"] if node.get("id") not in (56, 57)]
    # Remove stale references to the deleted links on the remaining nodes.
    valid_links = {link[0] for link in wf["links"]}
    for node in wf["nodes"]:
        for output_entry in node.get("outputs", []) or []:
            output_entry["links"] = [
                lid for lid in (output_entry.get("links") or []) if lid in valid_links
            ]
        for input_entry in node.get("inputs", []) or []:
            if input_entry.get("link") is not None and input_entry["link"] not in valid_links:
                input_entry["link"] = None

    # Low-pass values come from the PRE/POST low-pass widgets directly.
    for nid in (49, 50):
        lowpass = next(node for node in wf["nodes"] if node["id"] == nid)
        for entry in lowpass["inputs"]:
            if str(entry.get("name", "")).endswith("_override"):
                entry["link"] = None

    # FlashSR lowpass_input is a plain widget now (default False).
    flashsr_node = next(node for node in wf["nodes"] if node["id"] == 45)
    for entry in flashsr_node["inputs"]:
        if entry.get("name") == "lowpass_input":
            entry["link"] = None

    # Artwork size: use the new 1536 preset (larger presets selectable).
    set_node(wf, 64, widgets_values=["1536x1536", 1536], widgets_values_named={"size_preset": "1536x1536", "custom_size": 1536})

    # Production JSON: metadata_json is optional since 2.0.0 and the node
    # assembles the COMPLETE generation record from direct inputs (LLM stage,
    # parsed sections, MiniMax settings, every audio report).
    set_node(
        wf, 99,
        inputs=[
            linked_input("configuration_prefix", "STRING", 212),
            linked_input("audio_tags_json", "STRING", 211),
            linked_input("title", "STRING", 213),
            linked_input("original_audio_save_json", "STRING", 214),
            linked_input("release_flac_save_json", "STRING", 215),
            linked_input("release_mp3_save_json", "STRING", 216),
            linked_input("artwork_path", "STRING", 217),
            widget_input("collision_mode", "COMBO"),
            widget_input("filename_mode", "COMBO"),
            widget_input("create_directories", "BOOLEAN"),
            linked_input("metadata_json", "STRING", None),
            linked_input("llm_system_prompt", "STRING", 222),
            linked_input("llm_user_prompt", "STRING", 223),
            linked_input("llm_output", "STRING", 225),
            linked_input("llm_status", "STRING", 226),
            linked_input("llm_thinking", "STRING", 254),
            linked_input("structured_summary_json", "STRING", 224),
            linked_input("caption", "STRING", 227),
            linked_input("lyrics", "STRING", 228),
            linked_input("image_prompt", "STRING", 229),
            linked_input("source_name", "STRING", 230),
            linked_input("source_path", "STRING", 234),
            linked_input("prompt_origin", "STRING", 235),
            linked_input("prompt_provenance_json", "STRING", 236),
            linked_input("generation_seed", "INT", 231),
            linked_input("run_index", "INT", 232),
            linked_input("variant_count", "INT", 233),
            linked_input("max_duration", "FLOAT", 237),
            linked_input("text_seed", "INT", 238),
            linked_input("text_cfg_scale", "FLOAT", 239),
            linked_input("text_top_k", "INT", 240),
            linked_input("ksampler_seed", "INT", 241),
            linked_input("ksampler_steps", "INT", 242),
            linked_input("ksampler_cfg", "FLOAT", 243),
            linked_input("denoise", "FLOAT", 244),
            linked_input("flashsr_settings_json", "STRING", 245),
            linked_input("pre_preset", "STRING", 246),
            linked_input("pre_settings_json", "STRING", 247),
            linked_input("post_preset", "STRING", 248),
            linked_input("post_settings_json", "STRING", 249),
            linked_input("hybrid_crossover_json", "STRING", 250),
            linked_input("hf_repair_json", "STRING", 251),
            linked_input("declip_json", "STRING", 252),
            linked_input("release_prep_json", "STRING", 253),
            widget_input("workflow_name", "STRING"),
        ],
        widgets_values=["auto_increment", "album - title", True, "MiniMax Music Production Toolkit 2.0.0"],
        widgets_values_named={
            "collision_mode": "auto_increment", "filename_mode": "album - title",
            "create_directories": True, "workflow_name": "MiniMax Music Production Toolkit 2.0.0",
        },
        title="Save Production JSON (complete generation record)",
    )

    # --------------------------------------------------------- new links
    # The production JSON receives the complete generation record.
    new_links = [
        [222, 80, 0, 99, 11, "STRING"],   # system_prompt -> llm_system_prompt
        [223, 80, 1, 99, 12, "STRING"],   # user_prompt -> llm_user_prompt
        [224, 80, 3, 99, 16, "STRING"],   # structured_summary_json
        [225, 85, 0, 99, 13, "STRING"],   # LLM text (through unload) -> llm_output
        [226, 81, 1, 99, 14, "STRING"],   # LLM status -> llm_status
        [254, 81, 2, 99, 15, "STRING"],   # LLM thinking -> llm_thinking
        [227, 53, 0, 99, 17, "STRING"],   # caption
        [228, 53, 1, 99, 18, "STRING"],   # lyrics
        [229, 53, 3, 99, 19, "STRING"],   # image_prompt
        [230, 53, 4, 99, 20, "STRING"],   # source_name
        [231, 53, 5, 99, 24, "INT"],      # generation_seed
        [232, 53, 6, 99, 25, "INT"],      # run_index
        [233, 53, 7, 99, 26, "INT"],      # variant_count
        [234, 53, 8, 99, 21, "STRING"],   # source_path
        [235, 53, 9, 99, 22, "STRING"],   # prompt_origin
        [236, 53, 10, 99, 23, "STRING"],  # prompt_provenance_json
        [237, 55, 0, 99, 27, "FLOAT"],    # max_duration
        [238, 55, 1, 99, 28, "INT"],      # text_seed
        [239, 55, 2, 99, 29, "FLOAT"],    # text_cfg_scale
        [240, 55, 3, 99, 30, "INT"],      # text_top_k
        [241, 55, 4, 99, 31, "INT"],      # ksampler_seed
        [242, 55, 5, 99, 32, "INT"],      # ksampler_steps
        [243, 55, 6, 99, 33, "FLOAT"],    # ksampler_cfg
        [244, 55, 7, 99, 34, "FLOAT"],    # denoise
        [245, 45, 1, 99, 35, "STRING"],   # flashsr settings_json
        [246, 49, 2, 99, 36, "STRING"],   # pre_preset
        [247, 49, 3, 99, 37, "STRING"],   # pre_settings_json
        [248, 50, 2, 99, 38, "STRING"],   # post_preset
        [249, 50, 3, 99, 39, "STRING"],   # post_settings_json
        [250, 93, 1, 99, 40, "STRING"],   # hybrid_crossover_json
        [251, 94, 1, 99, 41, "STRING"],   # hf_repair_json
        [252, 95, 1, 99, 42, "STRING"],   # declip_json
        [253, 91, 1, 99, 43, "STRING"],   # release_prep_json
    ]
    for link in new_links:
        if not any(existing[0] == link[0] for existing in wf["links"]):
            wf["links"].append(link)

    def append_output_links(node_id: int, output_name: str, link_ids: list) -> None:
        node = next(n for n in wf["nodes"] if n["id"] == node_id)
        for out in node.get("outputs", []):
            if out.get("name") == output_name:
                current = set(out.get("links") or [])
                out["links"] = list(current) + [lid for lid in link_ids if lid not in current]
                return
        raise SystemExit(f"output {output_name} not found on node {node_id}")

    append_output_links(80, "system_prompt", [222])
    append_output_links(80, "user_prompt", [223])
    append_output_links(80, "structured_summary_json", [224])
    append_output_links(85, "trigger", [225])
    append_output_links(81, "status", [226])
    append_output_links(81, "thinking", [254])
    append_output_links(53, "caption", [227])
    append_output_links(53, "lyrics", [228])
    append_output_links(53, "image_prompt", [229])
    append_output_links(53, "source_name", [230])
    append_output_links(53, "generation_seed", [231])
    append_output_links(53, "run_index", [232])
    append_output_links(53, "variant_count", [233])
    append_output_links(53, "source_path", [234])
    append_output_links(53, "prompt_origin", [235])
    append_output_links(53, "prompt_provenance_json", [236])
    append_output_links(55, "max_duration", [237])
    append_output_links(55, "text_seed", [238])
    append_output_links(55, "text_cfg_scale", [239])
    append_output_links(55, "text_top_k", [240])
    append_output_links(55, "ksampler_seed", [241])
    append_output_links(55, "ksampler_steps", [242])
    append_output_links(55, "ksampler_cfg", [243])
    append_output_links(55, "denoise", [244])
    append_output_links(45, "settings_json", [245])
    append_output_links(49, "preset", [246])
    append_output_links(49, "settings_json", [247])
    append_output_links(50, "preset", [248])
    append_output_links(50, "settings_json", [249])
    append_output_links(93, "hybrid_crossover_json", [250])
    append_output_links(94, "hf_repair_json", [251])
    append_output_links(95, "declip_json", [252])
    append_output_links(91, "release_prep_json", [253])

    # 58 MiniMaxMetadataLoader left the example workflow; it belongs in a
    # separate song-restore workflow.  The node class stays registered.
    wf["nodes"] = [node for node in wf["nodes"] if node.get("id") != 58]

    # ------------------------------------------------- artwork saver order
    # Frontend re-saves put linked sockets before the widget inputs; the
    # canonical serialization follows the INPUT_TYPES definition order.
    artwork = next((node for node in wf["nodes"] if node.get("type") == "SaveImageSmartPrefix"), None)
    if artwork is not None:
        expected_artwork = [
            "image", "filename_prefix", "collision_mode", "create_directories",
            "jpeg_quality", "title", "audio_tags_json", "filename_mode",
        ]
        by_name = {item.get("name"): item for item in artwork.get("inputs", [])}
        if all(name in by_name for name in expected_artwork):
            artwork["inputs"] = [by_name[name] for name in expected_artwork]
            links_by_id = {link[0]: link for link in wf["links"]}
            for slot, item in enumerate(artwork["inputs"]):
                link_id = item.get("link")
                if link_id is not None and link_id in links_by_id:
                    links_by_id[link_id][3] = artwork["id"]
                    links_by_id[link_id][4] = slot

    wf["last_node_id"] = max(int(wf.get("last_node_id", 99)), 101)
    wf["last_link_id"] = max(int(wf.get("last_link_id", 220)), 254)

    # ------------------------------------------------------- section notes
    def add_note(nid: int, title: str, text: str, pos: list, size: list, order: int) -> None:
        note = {
            "id": nid,
            "type": "MarkdownNote",
            "pos": pos,
            "size": size,
            "flags": {},
            "order": order,
            "mode": 0,
            "inputs": [],
            "outputs": [],
            "title": title,
            "properties": {"Node name for S&R": "MarkdownNote"},
            # The frontend renders the note text from the positional
            # widgets_values entry; widgets_values_named alone leaves it empty.
            "widgets_values": [text],
            "widgets_values_named": {"text": text},
            "color": "#432",
            "bgcolor": "#653",
        }
        wf["nodes"] = [n for n in wf["nodes"] if n["id"] != nid] + [note]

    add_note(
        102, "Prompt & LLM (01 + 02)",
        "## 01 + 02 - Prompt & LLM\n\n"
        "- `Structured Song Prompt`: choose a prompt file (`bundled_library`), then pick Genre / Tempo / Key / "
        "Lyrics / Language / Voice / Theme / Length (or `custom`). Selecting a file prefills the fields and copies "
        "its description into the description field - edit freely. `custom` always means no specification for that "
        "field. The `Save as custom prompt` button stores the current values into the library's `_custom/` folder.\n"
        "- `LLM Chat`: needs `llama-cpp-python` and a GGUF in `models/llm` (see the Models note). All LM Studio-style "
        "sampling parameters are available; `chat_format=auto` is verified for Qwen3.8 and Gemma 4. `thinking=off` "
        "splits any reasoning off the answer - thinking is logged and recorded in the JSON separately. With several "
        "GPUs, `split_mode` (layer/row), `tensor_split` (`even`) and `main_gpu` distribute the model.\n"
        "- `Parse Structured LLM Output`: with `LLM Chat -> enabled = false` the manual fallback fields take over, "
        "so the LLM section can be switched off without errors.\n"
        "- Song length is capped at 5 minutes (hard limit).",
        [-460, 650], [430, 400], 40,
    )
    add_note(
        103, "FLUX.2 Cover (03)",
        "## 03 - FLUX.2 Cover\n\n"
        "- `Artwork Size` controls the square cover: presets 256 up to 3096 (FLUX.2 quantizes to multiples of 16, "
        "so 3096 renders as 3088 - prefer 3072).\n"
        "- `CLIP Text Encode` receives the generated `Image_Prompt`.\n"
        "- Models: `flux-2-klein-4b.safetensors`, `qwen_3_4b.safetensors`, `flux2-vae.safetensors` "
        "(see the Models note for folders).",
        [-460, 900], [430, 260], 41,
    )
    add_note(
        104, "MiniMax Music 3 (04)",
        "## 04 - MiniMax Music 3\n\n"
        "- `MiniMax Music 3 Generation Settings`: max_duration (300 s = 5 min), text CFG / top_k and sampler "
        "steps / CFG / denoise.\n"
        "- The subgraph generates the music from Caption + Lyrics plus these settings; normally nothing to change.\n"
        "- Models: dit, text encoder and VAE (see the Models note).",
        [-460, 1150], [430, 240], 42,
    )
    add_note(
        105, "Audio Enhancement (05)",
        "## 05 - Audio Enhancement\n\n"
        "- `Audio Declip / Overload Repair`: conservative flat-top reconstruction (keep Auto/conservative for batches).\n"
        "- `PRE Lowpass`: 12 kHz recommended before FlashSR; `Audio Super Resolution (FlashSR)`: 48 kHz reconstruction, "
        "weights auto-download once into `models/audio/flashsr/`.\n"
        "- `FlashSR Hybrid Crossover`: blends original + FlashSR air (mix 0.45 default).\n"
        "- `HF Cymbal / Shimmer Repair`: gentle default.\n"
        "- `POST Lowpass`: 19 kHz default.\n"
        "- `Release Prep`: 44.1 kHz + static LUFS / true peak.",
        [-460, 1400], [430, 330], 43,
    )
    add_note(
        106, "Save & Release (06)",
        "## 06 - Save & Release\n\n"
        "- `Output Paths` defines the base folder and subfolders; every saver uses the same `Album - Title` basename.\n"
        "- `Standard MP3/FLAC Metadata` sets artist / album / title tags.\n"
        "- `Save Production JSON` writes ONE canonical JSON with the COMPLETE generation record: LLM prompt + answer, "
        "parsed sections, seeds, MiniMax settings, all audio-enhancement reports and the written files. "
        "This file can later be used to recreate the song with modified settings in a separate workflow.",
        [-460, 1650], [430, 300], 44,
    )
    add_note(
        107, "Models & Folders",
        "## Models & Folders\n\n"
        "All paths follow ComfyUI's `--models-directory` (here `F:\\ComfyUI\\models`):\n\n"
        "```text\n"
        "diffusion_models\\minimax_music3_dit_fp16.safetensors\n"
        "text_encoders\\minimax_music3_text_encoder_pruned_int8_convrot.safetensors\n"
        "vae\\minimax_music3_dav.safetensors\n"
        "diffusion_models\\flux-2-klein-4b.safetensors\n"
        "text_encoders\\qwen_3_4b.safetensors\n"
        "vae\\flux2-vae.safetensors\n"
        "llm\\Qwen3.8-27B-UD-IQ3_XXS.gguf   (any GGUF works)\n"
        "audio\\flashsr\\student_ldm.pth + sr_vocoder.pth + vae.pth   (auto-download)\n"
        "```\n\n"
        "`Model Auto-Download / Check` reports missing files at the start of every run. The FlashSR inference code is "
        "bundled with the toolkit (`flashsr_inference/`) - never put FlashSR code into the models folder.",
        [-460, 1900], [520, 400], 45,
    )

    # ------------------------------------------------------------ note 39
    note_text = (
        "## Prompt control + integrated LLM\n\n"
        "`Structured Song Prompt` loads a prompt file (bundled `prompts/user/` or an external "
        "directory) and prefills Genre / Tempo / Key / Lyrics / Language / Voice / Theme / Length "
        "from the file's optional metadata block. Every field can be overridden; `custom` leaves "
        "the part out of the LLM prompt. The rest of the prompt file is the description.\n\n"
        "`LLM Chat (llama.cpp)` is part of this toolkit — no external LLM custom node is needed. "
        "It needs llama-cpp-python plus a GGUF in `models/llm` (auto-download when a URL is "
        "configured in `models_config.json`).\n\n"
        "The required LLM output order is `[Caption]` → `[Lyrics]` → `[Title]` → `[Image_Prompt]`. "
        "The parser is deliberately order-tolerant for robustness. The LLM chat node's status output "
        "is wired into the parser, so a failed or empty LLM generation is reported as such instead "
        "of looking like a prompt-format error.\n\n"
        "## Switching the LLM section off\n\n"
        "Set `LLM Chat → enabled` to false and fill `manual_caption` / `manual_lyrics` "
        "(and optionally `manual_title`, `manual_image_prompt`) on the parser. The rest of the "
        "workflow keeps running without the LLM.\n\n"
        "## LLM Recommendation\n\n"
        "I tried Qwen3.8-27B-IQ3_XXS.gguf from Unsloth and it worked perfect. "
        "The Gemma 4 models should also work decently."
    )
    # Note 39 is rebuilt defensively: a ComfyUI-side re-save of the example
    # workflow can drop note nodes, so regenerate it every time instead of
    # requiring it to exist.
    wf["nodes"] = [node for node in wf["nodes"] if node.get("id") != 39]
    note_39 = {
        "id": 39,
        "type": "MarkdownNote",
        "pos": [163.42553426177085, 385.4645749090889],
        "size": [332.5, 523.875],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "title": "Prompt library + integrated LLM",
        "properties": {"Node name for S&R": "MarkdownNote"},
        "widgets_values": [note_text],
        "widgets_values_named": {"text": note_text},
        "color": "#432",
        "bgcolor": "#653",
    }
    wf["nodes"].append(note_39)

    # ------------------------------------------------------------ metadata
    if "workflow_version" in (wf.get("extra") or {}):
        wf["extra"]["workflow_version"] = "2.0.0"
    wf["revision"] = int(wf.get("revision", 11)) + 1

    WORKFLOW.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Upgraded {WORKFLOW.name} to 2.0.0 schema ({len(wf['nodes'])} nodes, {len(wf['links'])} links)")


if __name__ == "__main__":
    main()
