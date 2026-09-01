from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
        artwork_inputs = {i["name"]: i.get("link") for i in artwork["inputs"]}
        self.assertIsNotNone(artwork_inputs["title"])
        self.assertIsNotNone(artwork_inputs["audio_tags_json"])
        self.assertEqual(artwork["widgets_values_named"]["filename_mode"], "album - title")

        final_json = next(n for n in self.wf["nodes"] if n["type"] == "MiniMaxSaveProductionJSON")
        linked_inputs = {i["name"]: i.get("link") for i in final_json["inputs"]}
        for required in (
            "metadata_json", "configuration_prefix", "audio_tags_json", "title",
            "original_audio_save_json", "release_flac_save_json",
            "release_mp3_save_json", "artwork_path",
        ):
            self.assertIsNotNone(linked_inputs[required], required)

    def test_public_metadata_is_generic(self):
        tags = next(n for n in self.wf["nodes"] if n["type"] == "MiniMaxStandardAudioTags")
        values = tags["widgets_values_named"]
        self.assertEqual(values["artist"], "Example Artist")
        self.assertEqual(values["album"], "Example Album")
        self.assertEqual(values["composer"], "Example Composer")

    def test_prompt_library_and_cache_buster_are_in_example(self):
        types = {n["type"] for n in self.wf["nodes"]}
        self.assertIn("MiniMaxLLMTemplateV16", types)
        self.assertIn("MiniMaxLLMSessionId", types)
        self.assertNotIn("Number to Text", types)
        self.assertNotIn("Seed", types)


if __name__ == "__main__":
    unittest.main()
