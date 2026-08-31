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
