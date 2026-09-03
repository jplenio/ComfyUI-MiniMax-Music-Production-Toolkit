from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow_schema import JSON_NEW_INPUT_ORDER

WORKFLOW = ROOT / "example_workflows" / "MiniMax_Music3_Production_Toolkit.json"


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))

    def test_all_links_resolve(self):
        nodes = {n["id"]: n for n in self.wf["nodes"]}
        links = {l[0]: l for l in self.wf["links"]}
        for lid, src, src_slot, dst, dst_slot, _typ in self.wf["links"]:
            self.assertIn(src, nodes, lid)
            self.assertIn(dst, nodes, lid)
            self.assertLess(src_slot, len(nodes[src].get("outputs", [])), lid)
            self.assertLess(dst_slot, len(nodes[dst].get("inputs", [])), lid)
        for node in self.wf["nodes"]:
            for inp in node.get("inputs", []):
                if inp.get("link") is not None:
                    self.assertIn(inp["link"], links)
            for out in node.get("outputs", []):
                for lid in out.get("links") or []:
                    self.assertIn(lid, links)


    def test_subgraph_links_resolve_including_boundary_nodes(self):
        definitions = self.wf.get("definitions") or {}
        for subgraph in definitions.get("subgraphs", []) or []:
            nodes = {n["id"]: n for n in subgraph.get("nodes", [])}
            links = {l["id"]: l for l in subgraph.get("links", [])}
            input_id = (subgraph.get("inputNode") or {}).get("id")
            output_id = (subgraph.get("outputNode") or {}).get("id")
            valid_endpoints = set(nodes) | {x for x in (input_id, output_id) if x is not None}

            for item in (subgraph.get("inputs", []) or []) + (subgraph.get("outputs", []) or []):
                for lid in item.get("linkIds") or []:
                    self.assertIn(lid, links, (subgraph.get("name"), item.get("name"), lid))

            for node in nodes.values():
                for inp in node.get("inputs", []) or []:
                    if inp.get("link") is not None:
                        self.assertIn(inp["link"], links, (subgraph.get("name"), node["id"], inp.get("name")))
                for out in node.get("outputs", []) or []:
                    for lid in out.get("links") or []:
                        self.assertIn(lid, links, (subgraph.get("name"), node["id"], out.get("name")))

            for lid, link in links.items():
                self.assertIn(link["origin_id"], valid_endpoints, lid)
                self.assertIn(link["target_id"], valid_endpoints, lid)

    def test_subgraph_instance_inputs_match_definition(self):
        definitions = self.wf.get("definitions") or {}
        defs = {d.get("id"): d for d in definitions.get("subgraphs", []) or []}
        for node in self.wf.get("nodes", []):
            if node.get("type") in defs:
                expected = [i.get("name") for i in defs[node["type"]].get("inputs", [])]
                actual = [i.get("name") for i in node.get("inputs", [])]
                self.assertEqual(actual, expected, node.get("id"))


    def test_current_output_contract_and_llm_settings(self):
        nodes = {n["id"]: n for n in self.wf["nodes"]}
        types = {n["type"] for n in self.wf["nodes"]}
        self.assertIn("MiniMaxSaveProductionJSON", types)

        llm = nodes[81]
        self.assertEqual(llm["widgets_values_named"]["max_tokens"], 16384)
        self.assertEqual(llm["widgets_values_named"]["n_ctx"], 32768)

        paths = nodes[54]
        self.assertEqual(paths["widgets_values_named"]["configuration_subdir"], "json")
        self.assertIn("configuration_prefix", [o["name"] for o in paths["outputs"]])

        for nid in (35, 46, 52):
            saver = nodes[nid]
            self.assertFalse(saver["widgets_values_named"]["write_json_sidecar"])
            metadata_input = next(i for i in saver["inputs"] if i["name"] == "metadata_json")
            self.assertIsNone(metadata_input["link"])
            self.assertIn("save_info_json", [o["name"] for o in saver["outputs"]])


        artwork = nodes[77]
        self._assert_input_order(
            artwork,
            [
                "image", "filename_prefix", "collision_mode", "create_directories",
                "jpeg_quality", "title", "audio_tags_json", "filename_mode",
            ],
            "artwork saver",
        )
        self.assertEqual(artwork["widgets_values_named"]["collision_mode"], "auto_increment")
        self.assertIsInstance(artwork["widgets_values_named"]["jpeg_quality"], int)
        self.assertNotIsInstance(artwork["widgets_values_named"]["jpeg_quality"], bool)
        artwork_inputs = {i["name"]: i.get("link") for i in artwork["inputs"]}
        self.assertIsNotNone(artwork_inputs["title"])
        self.assertIsNotNone(artwork_inputs["audio_tags_json"])
        self.assertEqual(artwork["widgets_values_named"]["filename_mode"], "album - title")

        final_json = next(n for n in self.wf["nodes"] if n["type"] == "MiniMaxSaveProductionJSON")
        linked_inputs = {i["name"]: i.get("link") for i in final_json["inputs"]}
        for required in (
            "configuration_prefix", "audio_tags_json", "title",
            "original_audio_save_json", "release_flac_save_json",
            "release_mp3_save_json", "artwork_path",
        ):
            self.assertIsNotNone(linked_inputs[required], required)
        # metadata_json is optional since 2.0.0 (song-metadata node removed);
        # the node assembles the complete generation record from direct inputs.
        self.assertIsNone(linked_inputs["metadata_json"])
        self._assert_input_order(final_json, list(JSON_NEW_INPUT_ORDER), "production JSON")
        self.assertIsNotNone(linked_inputs["llm_system_prompt"])
        self.assertIsNotNone(linked_inputs["llm_output"])
        self.assertIsNotNone(linked_inputs["caption"])
        self.assertIsNotNone(linked_inputs["release_prep_json"])

    def test_legacy_settings_and_metadata_nodes_are_removed(self):
        types = {n["type"] for n in self.wf["nodes"]}
        self.assertNotIn("FlashSRProcessingSettings", types)
        self.assertNotIn("MiniMaxSongMetadata", types)
        # Low-pass values live directly on the PRE/POST low-pass nodes.
        lowpasses = [n for n in self.wf["nodes"] if n["type"] == "FlashSRLowpassLab"]
        self.assertEqual(len(lowpasses), 2)
        for node in lowpasses:
            for entry in node["inputs"]:
                if entry["name"].endswith("_override"):
                    self.assertIsNone(entry["link"])
        self.assertEqual(lowpasses[0]["widgets_values"][0], "PRE 12 kHz - recommended")
        self.assertEqual(lowpasses[1]["widgets_values"][0], "POST 19 kHz - slightly stronger")
        # FlashSR lowpass_input is a plain widget.
        flashsr = next(n for n in self.wf["nodes"] if n["type"] == "MiniMaxFlashSRAudio")
        lowpass_input = next(i for i in flashsr["inputs"] if i["name"] == "lowpass_input")
        self.assertIsNone(lowpass_input["link"])
        self.assertIs(flashsr["widgets_values"][0], False)

    def test_artwork_size_uses_large_preset(self):
        artwork_size = [n for n in self.wf["nodes"] if n["type"] == "MiniMaxSquareImageSize"]
        self.assertGreaterEqual(len(artwork_size), 1)
        presets = {n["widgets_values"][0] for n in artwork_size}
        self.assertIn("1536x1536", presets)

    def test_public_metadata_is_generic(self):
        tags = next(n for n in self.wf["nodes"] if n["type"] == "MiniMaxStandardAudioTags")
        values = tags["widgets_values_named"]
        self.assertEqual(values["artist"], "Example Artist")
        self.assertEqual(values["album"], "Example Album")
        self.assertEqual(values["composer"], "Example Composer")

    def test_prompt_library_and_cache_buster_are_in_example(self):
        types = {n["type"] for n in self.wf["nodes"]}
        self.assertIn("MiniMaxStructuredPromptV20", types)
        self.assertIn("MiniMaxLLMChat", types)
        self.assertIn("MiniMaxLLMUnload", types)
        self.assertIn("MiniMaxFlashSRAudio", types)
        self.assertIn("MiniMaxModelAutodownload", types)
        self.assertIn("MiniMaxLLMSessionId", types)
        self.assertNotIn("Number to Text", types)
        self.assertNotIn("Seed", types)
        self.assertNotIn("LLMSessionChatNode", types)
        self.assertNotIn("UnloadLLMModelNode", types)
        self.assertNotIn("EgregoraAudioUpscaler", types)
        # The optional song-restore loader belongs in a separate workflow.
        self.assertNotIn("MiniMaxMetadataLoader", types)

    def test_section_notes_document_the_workflow(self):
        notes = [n for n in self.wf["nodes"] if n["type"] == "MarkdownNote"]
        titles = {n.get("title") for n in notes}
        for expected in ("Models & Folders", "Save & Release (06)", "Audio Enhancement (05)"):
            self.assertIn(expected, titles)
        # Note 39 ("Prompt library + integrated LLM") is intentionally
        # removed by the user; only the six section notes are required.
        # The frontend renders the note text from the positional
        # widgets_values entry; a note with only widgets_values_named appears
        # empty in ComfyUI (regression guard).
        for note in notes:
            values = note.get("widgets_values") or []
            self.assertTrue(values, f"note {note.get('id')} has no widgets_values text")
            self.assertTrue(str(values[0]).strip(), f"note {note.get('id')} text is empty")
            named = (note.get("widgets_values_named") or {}).get("text")
            self.assertEqual(values[0], named, f"note {note.get('id')} widgets_values/named out of sync")
        models_note = next(n for n in notes if n.get("title") == "Models & Folders")
        text = models_note["widgets_values"][0]
        self.assertIn("minimax_music3_dit_fp16.safetensors", text)
        self.assertIn("audio", text)
        self.assertIn("flashsr", text)

    def _assert_input_order(self, node, expected, label):
        # ComfyUI serializes inputs in two valid orders: the definition order
        # (required then optional) and the frontend's socket-first order
        # (linked socket inputs before the widget inputs).  Within each group
        # the definition order must be preserved and the name set must match.
        entries = node.get("inputs", [])
        actual = [item.get("name") for item in entries]
        sockets = [item.get("name") for item in entries if "widget" not in item]
        widgets = [item.get("name") for item in entries if "widget" in item]
        self.assertEqual(sorted(actual), sorted(expected), label + " names")
        self.assertEqual(sockets, [name for name in expected if name in sockets], label + " socket order")
        self.assertEqual(widgets, [name for name in expected if name in widgets], label + " widget order")

    def test_parser_input_order_is_canonical_2_0(self):
        from workflow_schema import PARSER_NEW_INPUT_ORDER
        parser = next(n for n in self.wf["nodes"] if n["type"] == "MiniMaxParseExternalLLMOutputV16")
        self._assert_input_order(parser, list(PARSER_NEW_INPUT_ORDER), "parser")

    def test_llm_part_is_switchable(self):
        chat = next(n for n in self.wf["nodes"] if n["type"] == "MiniMaxLLMChat")
        parser = next(n for n in self.wf["nodes"] if n["type"] == "MiniMaxParseExternalLLMOutputV16")
        chat_values = chat["widgets_values_named"]
        self.assertIs(chat_values["enabled"], True)
        parser_links = {i["name"]: i.get("link") for i in parser["inputs"]}
        self.assertIsNotNone(parser_links["structured_llm_output"])
        self.assertIsNotNone(parser_links["model_check_report"])
        # The unload node passes the chat text through to the parser, mirroring the v1 chain.
        unload = next(n for n in self.wf["nodes"] if n["type"] == "MiniMaxLLMUnload")
        trigger = {i["name"]: i.get("link") for i in unload["inputs"]}["trigger"]
        links = {link[0]: link for link in self.wf["links"]}
        # chat text -> unload trigger -> parser structured_llm_output
        self.assertEqual(links[trigger][1], next(n["id"] for n in self.wf["nodes"] if n["type"] == "MiniMaxLLMChat"))
        self.assertEqual(links[parser_links["structured_llm_output"]][1], unload["id"])
        # chat status -> parser llm_status (upstream failure diagnostics)
        self.assertIsNotNone(parser_links["llm_status"])
        self.assertEqual(links[parser_links["llm_status"]][1], chat["id"])


if __name__ == "__main__":
    unittest.main()
