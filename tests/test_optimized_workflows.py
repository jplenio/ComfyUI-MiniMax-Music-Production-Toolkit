"""Behavior preservation, graph integrity and usable layout of the new examples."""
import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / "example_workflows" / (name+".json")).read_text(encoding="utf-8"))


class OptimizedWorkflowTests(unittest.TestCase):
    def test_only_canonical_examples_are_shipped(self):
        files = {p.name for p in (ROOT / "example_workflows").glob("*.json")}
        self.assertEqual(files, {"MiniMax_Music3_Production_Toolkit.json",
                                 "MiniMax_Music3_Production_Toolkit_AudioEnhance.json"})

    def test_enhancement_has_no_processing_after_final_mastering(self):
        result = read("MiniMax_Music3_Production_Toolkit_AudioEnhance")
        nodes = {n["id"]: n for n in result["nodes"]}
        audio = {(s,d) for _,s,_,d,_,typ in result["links"] if typ == "AUDIO"}
        self.assertTrue({(13,15),(14,26),(26,16)} <= audio)
        self.assertEqual(nodes[14]["widgets_values_named"]["processing"], "Resample only")
        self.assertEqual(nodes[14]["widgets_values"][1], "Resample only")
        self.assertEqual({d for s,d in audio if s == 26}, {16})

    def test_independent_eq_controls_and_final_rates(self):
        for name in ("MiniMax_Music3_Production_Toolkit", "MiniMax_Music3_Production_Toolkit_AudioEnhance"):
            wf = read(name)
            eqs = [n for n in wf["nodes"] if n["type"] == "MiniMaxParametricEQ"]
            self.assertEqual(len(eqs),2)
            linked = [n for n in eqs if next(i for i in n["inputs"] if i["name"] == "eq_settings_json")["link"] is not None]
            self.assertEqual(len(linked),1)
            auto = next(n for n in wf["nodes"] if n["type"] == "MiniMaxAutoEQAnalyze")
            self.assertTrue(auto["widgets_values_named"]["enabled"])
            names = [i["name"] for i in auto["inputs"] if "widget" in i]
            self.assertIs(auto["widgets_values"][names.index("enabled")], True)
            rate = next(n for n in wf["nodes"] if n["type"] == "AudioReleasePrep")
            self.assertEqual(rate["widgets_values_named"]["target_sample_rate"],"44100")
            self.assertEqual(rate["widgets_values_named"]["processing"],"Resample only")
            master = next(n for n in wf["nodes"] if n["type"] == "MiniMaxMasteringCompressor")
            self.assertEqual(master["widgets_values_named"]["target_sample_rate"],"keep")

    def test_generated_files_links_groups_and_no_overlap(self):
        for suffix in ("", "_AudioEnhance"):
            name = "MiniMax_Music3_Production_Toolkit"+suffix
            source = read(name)
            wf = source
            nodes = {n["id"]: n for n in wf["nodes"]}
            links = {l[0]:l for l in wf["links"]}
            self.assertEqual(len(links), len(wf["links"]))
            edges = {nid: [] for nid in nodes}
            for lid, src, slot, dst, target, typ in wf["links"]:
                self.assertEqual(nodes[dst]["inputs"][target]["link"],lid)
                self.assertIn(lid,nodes[src]["outputs"][slot]["links"])
                self.assertIn(nodes[src]["outputs"][slot]["type"],(typ,"*"))
                edges[src].append(dst)
            seen, active = set(), set()
            def visit(nid):
                self.assertNotIn(nid, active, "Graph cycle")
                if nid in seen:
                    return
                active.add(nid)
                for dst in edges[nid]:
                    visit(dst)
                active.remove(nid)
                seen.add(nid)
            for nid in nodes:
                visit(nid)
            for n in nodes.values():
                for slot, inp in enumerate(n.get("inputs", [])):
                    if inp.get("link") is not None:
                        self.assertEqual(links[inp["link"]][3:5],[n["id"],slot])
                for slot, out in enumerate(n.get("outputs", [])):
                    for lid in out.get("links") or []:
                        self.assertEqual(links[lid][1:3],[n["id"],slot])
                x,y = n["pos"]; w,h = n["size"]
                containing = [g for g in wf["groups"] if
                              g["bounding"][0] <= x and g["bounding"][1] <= y-30 and
                              g["bounding"][0]+g["bounding"][2] >= x+w and
                              g["bounding"][1]+g["bounding"][3] >= y+h]
                self.assertEqual(len(containing),1,n["id"])
                if n["type"] == "MarkdownNote":
                    self.assertEqual(n["widgets_values"][0],n["widgets_values_named"]["text"])
                for other in nodes.values():
                    if other["id"] <= n["id"]:
                        continue
                    ox,oy = other["pos"]; ow,oh = other["size"]
                    self.assertFalse(x < ox+ow and x+w > ox and y-30 < oy+oh and y+h > oy-30,
                                     (n["id"],other["id"]))


if __name__ == "__main__":
    unittest.main()
