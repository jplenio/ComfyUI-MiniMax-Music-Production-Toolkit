"""Behavior preservation, graph integrity and usable layout of the new examples."""
import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / "example_workflows" / (name+".json")).read_text(encoding="utf-8"))


class OptimizedWorkflowTests(unittest.TestCase):
    def test_cover_switch_sits_in_the_cover_area(self):
        """The FLUX.2 switch belongs with the artwork stage it controls.

        The maintainer's layout decision places it in
        05 · ILLUSTRATE / Cover artwork (not at the top of the start group).
        This pins that placement, the ON default and the two connections that
        make the switch effective.
        """
        wf = read("Music_Production_Toolkit")
        # Since the consolidation one production control owns the cover choice and
        # feeds the artwork, the preview and the FLUX.2 download group.
        control = next(n for n in wf["nodes"] if n["type"] == "MusicProductionControl")
        choose = next(g for g in wf["groups"] if g["title"].startswith("00"))
        x, y = control["pos"]
        w, h = control["size"]
        bx, by, bw, bh = choose["bounding"]
        self.assertTrue(bx <= x and by <= y - 30 and bx + bw >= x + w and by + bh >= y + h,
                        "the production control must sit inside its own group")
        nodes = {n["id"]: n for n in wf["nodes"]}
        connected = {(nodes[l[3]]["type"], nodes[l[3]]["inputs"][l[4]]["name"])
                     for l in wf["links"] if l[1] == control["id"]}
        self.assertIn(("SaveImageSmartPrefix", "enabled"), connected)
        self.assertIn(("MusicOptionalCoverPreview", "enabled"), connected)
        self.assertIn(("MiniMaxModelAutodownload", "flux2_models"), connected)

    def test_only_canonical_examples_are_shipped(self):
        files = {p.name for p in (ROOT / "example_workflows").glob("*.json")}
        # Consolidated in 3.1.0: one main workflow and one enhancement workflow.
        self.assertEqual(files, {"Music_Production_Toolkit.json",
                                 "Music_Production_AudioEnhance.json"})

    def test_enhancement_has_no_processing_after_final_mastering(self):
        result = read("Music_Production_AudioEnhance")
        nodes = {n["id"]: n for n in result["nodes"]}
        audio = {(s,d) for _,s,_,d,_,typ in result["links"] if typ == "AUDIO"}
        # The restoration chain, the artifact reduction and both bypass gates sit
        # inside the path: POST low-pass -> refinement gate -> artifact reduction,
        # then manual EQ -> mastering gate -> release prep -> dynamics -> savers.
        self.assertTrue({(13, 15), (15, 30), (30, 31), (31, 27), (31, 25),
                         (28, 14), (28, 33), (14, 26), (26, 33)} <= audio)
        self.assertEqual({d for s, d in audio if s == 33}, {16, 34})
        self.assertEqual(nodes[14]["widgets_values_named"]["processing"], "Resample only")
        self.assertEqual(nodes[14]["widgets_values"][1], "Resample only")

    def test_independent_eq_controls_and_final_rates(self):
        for name in ("Music_Production_Toolkit", "Music_Production_AudioEnhance"):
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

    def test_no_shipped_budget_can_truncate_a_prompt_or_a_response(self):
        """Pin the token budgets against the measured real demand.

        On 2026-09-17, 35 production JSONs of a YuE2 Cover album measured: parser
        prompt (caption+lyrics) up to 1707 tokens, LLM prompt up to ~11.6k tokens,
        LLM response up to ~2k tokens. A parser budget of 1200 with trimming off
        would therefore fail 24 of those 35 runs with a ValueError instead of
        producing a song, and trim_long_prompt=True would silently drop lyrics.
        """
        wf = read("Music_Production_Toolkit")
        measured_parser_max = 1707
        measured_prompt_max = 11590
        parser = [n for n in wf["nodes"] if n["type"] == "MiniMaxParseExternalLLMOutputV16"]
        self.assertTrue(parser, "the main workflow must keep its parser node")
        for node in parser:
            named = node["widgets_values_named"]
            self.assertGreater(named["max_prompt_tokens"], measured_parser_max,
                               "parser budget below the measured prompt size fails every cover")
            self.assertFalse(named["trim_long_prompt"],
                             "trimming would drop cover lyrics or ABC sections silently")
            widget_inputs = [i["name"] for i in node["inputs"] if "widget" in i]
            self.assertEqual(node["widgets_values"][widget_inputs.index("max_prompt_tokens")],
                             named["max_prompt_tokens"],
                             "positional and named budgets must agree")

        for node in [n for n in wf["nodes"] if n["type"] == "MiniMaxLLMChat"]:
            named = node.get("widgets_values_named")
            self.assertIsInstance(named, dict,
                                  f"LLM node {node['id']} must carry named widget values")
            self.assertGreaterEqual(named["max_tokens"], 24576, node["id"])
            self.assertGreaterEqual(named["remote_max_tokens"], 65536, node["id"])
            self.assertGreaterEqual(named["n_ctx"], 37376, node["id"])
            # The whole point of the 2026-09-17 budget: even a maximum-length
            # answer must fit into the context next to the largest measured
            # prompt, so the runtime never ends an answer instead of the node.
            self.assertLessEqual(measured_prompt_max + named["max_tokens"], named["n_ctx"],
                                 f"LLM node {node['id']} could truncate a maximum-length answer")

    def test_generated_files_links_groups_and_no_overlap(self):
        for name in ("Music_Production_Toolkit", "Music_Production_AudioEnhance"):
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
