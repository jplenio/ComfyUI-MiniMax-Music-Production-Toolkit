"""The style hint: the one style source the Cover Studio can read without a cycle.

The master node consumes the studio's rewritten score, so it is downstream of the
studio and cannot feed it. This node exists so the studio can still be told which
style to aim its rework at, from the same prompt file or from typed text.
"""
from __future__ import annotations

import importlib
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from _toolkit_bootstrap import load_entry_point  # noqa: E402


class StyleHintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.mod = importlib.import_module(cls.pkg.__name__ + ".style_hint")
        cls.library = importlib.import_module(cls.pkg.__name__ + ".prompt_library")

    def node(self):
        return self.pkg.NODE_CLASS_MAPPINGS["MiniMaxStyleHint"]()

    def test_typed_text_is_used_when_no_file_is_selected(self):
        text, origin = self.mod.style_hint_text("a warm analog synth-pop arrangement")
        self.assertEqual(text, "a warm analog synth-pop arrangement")
        self.assertEqual(origin, "<typed text>")

    def test_a_selected_prompt_file_wins_over_the_typed_text(self):
        text, origin = self.mod.style_hint_text(
            "typed text that should lose", "bundled_library", "", "electronic/synth-pop-vocal.txt")
        self.assertNotEqual(text, "typed text that should lose")
        self.assertEqual(origin, "electronic/synth-pop-vocal.txt")
        self.assertGreater(len(text), 100, "the file body is the hint")

    def test_the_custom_sentinel_means_typed_text_only(self):
        text, origin = self.mod.style_hint_text("only my text", "bundled_library", "", "custom")
        self.assertEqual((text, origin), ("only my text", "<typed text>"))

    def test_an_empty_configuration_sends_no_hint_and_never_raises(self):
        for args in ((), ("", "bundled_library", "", "custom"),
                     ("   ", "bundled_library", "", "<select a prompt>")):
            with self.subTest(args=args):
                text, origin = self.mod.style_hint_text(*args)
                self.assertEqual((text, origin), ("", "<empty>"))

    def test_a_missing_file_falls_back_to_the_typed_text(self):
        text, origin = self.mod.style_hint_text(
            "fallback", "bundled_library", "", "does/not/exist.txt")
        self.assertEqual((text, origin), ("fallback", "<typed text>"))

    def test_an_external_directory_file_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "style.txt"
            path.write_text("dark ambient, slow and spacious", encoding="utf-8")
            text, origin = self.mod.style_hint_text("", "external_directory", tmp, "style.txt")
        self.assertEqual(text, "dark ambient, slow and spacious")
        self.assertEqual(origin, "style.txt")

    def test_the_node_returns_one_string_output(self):
        node = self.node()
        self.assertEqual(node.RETURN_TYPES, ("STRING",))
        self.assertEqual(node.RETURN_NAMES, ("style_hint",))
        result = node.resolve("hint text")
        self.assertEqual(result, ("hint text",))

    def test_the_contract_keeps_the_new_widgets_last(self):
        spec = self.node().INPUT_TYPES()
        self.assertEqual(list(spec["required"]), ["style_text"])
        # The selection widgets carry the master's names on purpose: the shared
        # frontend helpers (readSelection, buildGroupedFileOptions) work on them
        # unchanged, so both dropdowns cannot drift apart.
        self.assertEqual(list(spec["optional"]),
                         ["user_prompt_source", "user_prompt_directory", "user_prompt_file"])

    def test_the_hint_carries_the_body_without_the_front_matter(self):
        text, _origin = self.mod.style_hint_text(
            "", "bundled_library", "", "electronic/synth-pop-vocal.txt")
        self.assertFalse(text.startswith("---"), "front matter is metadata, not prose")
        self.assertNotIn("Genre:", text.splitlines()[0] if text else "")
        self.assertTrue(text.startswith("Bright"), text[:40])

    def test_editing_the_text_or_the_selection_invalidates_the_cache(self):
        node = self.node()
        base = node.IS_CHANGED("first", "bundled_library", "", "custom")
        self.assertNotEqual(base, node.IS_CHANGED("second", "bundled_library", "", "custom"))
        self.assertNotEqual(
            base, node.IS_CHANGED("first", "bundled_library", "", "electronic/synth-pop-vocal.txt"))

    def test_the_workflow_feeds_the_studio_without_a_cycle(self):
        """The node reaches the studio's target_style, and the graph stays acyclic.

        The shipped workflow wires the hint to the plan node and nothing else. An
        earlier revision also fed the master's `description_override`; that cable is
        gone by decision, so the check requires only the studio - the consumer that
        must never be missing.
        """
        data = json.loads((ROOT / "example_workflows" / "Music_Production_Toolkit.json")
                          .read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in data["nodes"]}
        hint = next((node for node in data["nodes"] if node["type"] == "MiniMaxStyleHint"), None)
        self.assertIsNotNone(hint, "the shipped workflow must carry the style hint node")
        links = {link[0]: link for link in data["links"]}
        targets = {(links[link_id][3], links[link_id][4])
                   for link_id in hint["outputs"][0]["links"]}
        names = {(nodes[node_id]["type"], nodes[node_id]["inputs"][slot]["name"])
                 for node_id, slot in targets}
        self.assertIn(("YuE2CoverStudioPlan", "target_style"), names,
                      "the studio must receive the style hint")

        # Acyclicity: walk the real links, like ComfyUI's validator does.
        edges = {node_id: [] for node_id in nodes}
        for _lid, src, _slot, dst, _dsts, _type in data["links"]:
            if src in edges and dst in edges:
                edges[src].append(dst)
        state = {}

        def walk(node_id, trail):
            self.assertNotIn(node_id, trail, "dependency cycle: " + " -> ".join(map(str, trail + [node_id])))
            if state.get(node_id) == 2:
                return
            state[node_id] = 1
            for nxt in edges[node_id]:
                walk(nxt, trail + [node_id])
            state[node_id] = 2

        for node_id in nodes:
            walk(node_id, [])

    def test_the_cover_studio_note_uses_the_house_colours(self):
        """Heading in the frame's colour, body on the shared dark background."""
        data = json.loads((ROOT / "example_workflows" / "Music_Production_Toolkit.json")
                          .read_text(encoding="utf-8"))
        note = next(node for node in data["nodes"]
                    if node["id"] == 132 and node["type"] == "MarkdownNote")
        group = next(group for group in data["groups"]
                     if group["bounding"][0] <= note["pos"][0] <= group["bounding"][0] + group["bounding"][2]
                     and group["bounding"][1] <= note["pos"][1] - 30 <= group["bounding"][1] + group["bounding"][3])
        self.assertEqual(note.get("color"), group.get("color"))
        self.assertEqual(note.get("bgcolor"), "#252b33")
        # Every other note in the file uses the same pair, so this one is no outlier.
        for other in data["nodes"]:
            if other["type"] == "MarkdownNote":
                self.assertEqual(other.get("bgcolor"), "#252b33", other["id"])
                self.assertIsNotNone(other.get("color"), other["id"])

    def test_the_node_is_placed_inside_one_group(self):
        data = json.loads((ROOT / "example_workflows" / "Music_Production_Toolkit.json")
                          .read_text(encoding="utf-8"))
        hint = next(node for node in data["nodes"] if node["type"] == "MiniMaxStyleHint")
        x, y = hint["pos"]
        w, h = hint["size"]
        containing = [group for group in data["groups"]
                      if group["bounding"][0] <= x and group["bounding"][1] <= y - 30
                      and group["bounding"][0] + group["bounding"][2] >= x + w
                      and group["bounding"][1] + group["bounding"][3] >= y + h]
        self.assertEqual(len(containing), 1, "the hint node needs exactly one owning group")


if __name__ == "__main__":
    unittest.main()
