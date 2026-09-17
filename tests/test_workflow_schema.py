from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from workflow_schema import (
    JSON_METADATA_INPUT,
    JSON_NEW_INPUT_ORDER,
    JSON_NODE_TYPE,
    PARSER_NEW_INPUT_ORDER,
    PARSER_NODE_TYPE,
    PARSER_STRUCTURED_INPUT,
    find_external_node_dependencies,
    migrate_workflow,
)

WORKFLOWS = [
    ROOT / "example_workflows" / "Music_Production_Toolkit.json",
    ROOT / "example_workflows" / "Music_Production_AudioEnhance.json",
]


def _entry(name: str, type_: str = "STRING", link=None, widget: bool = False) -> dict:
    item = {"name": name, "type": type_, "link": link}
    if widget:
        item["widget"] = {"name": name}
    return item


def make_pre_2_0_0_parser_node() -> dict:
    """Exact pre-2.0.0 serialization (verified against git tag v1.0.3)."""
    return {
        "id": 53,
        "type": PARSER_NODE_TYPE,
        "inputs": [
            _entry("structured_llm_output", link=190),
            _entry("song_count", "INT", widget=True),
            _entry("seed_mode", "COMBO", widget=True),
            _entry("base_seed", "INT", widget=True),
            _entry("user_prompt", link=178, widget=True),
            _entry("source_name_override", link=179, widget=True),
            _entry("fallback_title", widget=True),
        ],
        "outputs": [],
    }


def make_old_json_node() -> dict:
    return {
        "id": 99,
        "type": JSON_NODE_TYPE,
        "inputs": [
            _entry("metadata_json", link=145),
            _entry("configuration_prefix", link=212),
            _entry("audio_tags_json", link=211),
            _entry("title", link=213),
            _entry("artwork_path", link=217),
            _entry("collision_mode", "COMBO", widget=True),
            _entry("filename_mode", "COMBO", widget=True),
            _entry("create_directories", "BOOLEAN", widget=True),
        ],
        "outputs": [],
    }


class BundledWorkflowNoOpTests(unittest.TestCase):
    """Current workflows must survive the migration byte-for-byte."""

    def test_bundled_workflows_are_untouched(self):
        for path in WORKFLOWS:
            with self.subTest(workflow=path.name):
                workflow = json.loads(path.read_text(encoding="utf-8"))
                before = copy.deepcopy(workflow)
                diagnostics: list[str] = []
                self.assertEqual(migrate_workflow(workflow, diagnostics), [])
                self.assertEqual(workflow, before)
                self.assertEqual(diagnostics, [])

    def test_current_serialization_is_idempotent(self):
        workflow = {
            "nodes": [
                {
                    "id": 53,
                    "type": PARSER_NODE_TYPE,
                    "inputs": [
                        _entry(name, "INT" if name in ("song_count", "base_seed") else "STRING",
                               widget=name != "structured_llm_output")
                        for name in (
                            "structured_llm_output", "song_count", "seed_mode", "base_seed",
                            "user_prompt", "source_name_override", "fallback_title",
                            "manual_caption", "manual_lyrics", "manual_title",
                            "manual_image_prompt", "model_check_report", "llm_status",
                            "max_prompt_tokens", "trim_long_prompt",
                        )
                    ],
                    "outputs": [],
                }
            ],
            "links": [],
        }
        before = copy.deepcopy(workflow)
        self.assertEqual(migrate_workflow(workflow), [])
        self.assertEqual(workflow, before)


class ParserMigrationTests(unittest.TestCase):
    def test_pre_2_0_0_parser_node_needs_no_slot_change(self):
        # The pre-2.0.0 serialization is a prefix of the current grouping, so
        # the stored slots already resolve to the right inputs.
        workflow = {
            "nodes": [make_pre_2_0_0_parser_node()],
            "links": [
                [190, 85, 0, 53, 0, "STRING"],
                [178, 80, 1, 53, 4, "STRING"],
                [179, 80, 2, 53, 5, "STRING"],
            ],
        }
        before = copy.deepcopy(workflow)
        self.assertEqual(migrate_workflow(workflow), [])
        self.assertEqual(workflow, before)

    def test_unknown_inputs_are_preserved(self):
        node = make_pre_2_0_0_parser_node()
        node["inputs"].insert(2, _entry("future_field_2040", "STRING", widget=True))
        workflow = {"nodes": [node], "links": []}
        migrate_workflow(workflow)
        names = [i["name"] for i in workflow["nodes"][0]["inputs"]]
        self.assertIn("future_field_2040", names)

    def test_sparse_old_order_gets_no_slot_outside_inputs(self):
        # F04 reproduction: only structured_llm_output and song_count present.
        node = {
            "id": 53,
            "type": PARSER_NODE_TYPE,
            "inputs": [
                _entry("structured_llm_output", link=190),
                _entry("song_count", "INT", widget=True),
            ],
            "outputs": [],
        }
        workflow = {"nodes": [node], "links": [[190, 85, 0, 53, 0, "STRING"]]}
        migrate_workflow(workflow)
        count = len(workflow["nodes"][0]["inputs"])
        slot = workflow["links"][0][4]
        self.assertIsInstance(slot, int)
        self.assertTrue(0 <= slot < count, f"slot {slot} outside 0..{count - 1}")
        self.assertEqual(workflow["nodes"][0]["inputs"][slot]["name"], PARSER_STRUCTURED_INPUT)

    def test_artifact_link_on_int_slot_is_moved(self):
        # A STRING link on the INT song_count slot can only be the old LLM text.
        node = {
            "id": 53,
            "type": PARSER_NODE_TYPE,
            "inputs": [
                _entry("song_count", "INT", widget=True),
                _entry("structured_llm_output"),
                _entry("seed_mode", "COMBO", widget=True),
            ],
            "outputs": [],
        }
        workflow = {"nodes": [node], "links": [[190, 85, 0, 53, 0, "STRING"]]}
        changes = migrate_workflow(workflow)
        self.assertEqual(len(changes), 1)
        names = [i["name"] for i in workflow["nodes"][0]["inputs"]]
        slot = workflow["links"][0][4]
        self.assertEqual(names[slot], PARSER_STRUCTURED_INPUT)
        # Socket inputs are serialized first, so the rebuilt array moves it to 0.
        self.assertEqual(names, ["structured_llm_output", "song_count", "seed_mode"])

    def test_non_string_link_is_never_moved(self):
        node = {
            "id": 53,
            "type": PARSER_NODE_TYPE,
            "inputs": [
                _entry("song_count", "INT", widget=True),
                _entry("structured_llm_output"),
            ],
            "outputs": [],
        }
        workflow = {"nodes": [node], "links": [[190, 55, 0, 53, 0, "INT"]]}
        migrate_workflow(workflow)
        names = [i["name"] for i in workflow["nodes"][0]["inputs"]]
        self.assertEqual(names[workflow["links"][0][4]], "song_count")

    def test_string_link_on_string_slot_is_never_moved(self):
        node = {
            "id": 53,
            "type": PARSER_NODE_TYPE,
            "inputs": [
                _entry("user_prompt", link=178, widget=True),
                _entry("structured_llm_output"),
            ],
            "outputs": [],
        }
        workflow = {"nodes": [node], "links": [[178, 80, 1, 53, 0, "STRING"]]}
        migrate_workflow(workflow)
        names = [i["name"] for i in workflow["nodes"][0]["inputs"]]
        self.assertEqual(names[workflow["links"][0][4]], "user_prompt")

    def test_malformed_slots_are_reported_without_corruption(self):
        node = make_pre_2_0_0_parser_node()
        workflow = {
            "nodes": [node],
            "links": [
                [190, 85, 0, 53, 99, "STRING"],   # out of range
                [191, 85, 1, 53, "x", "STRING"],  # non-integer
            ],
        }
        before = copy.deepcopy(workflow)
        diagnostics: list[str] = []
        changes = migrate_workflow(workflow, diagnostics)
        self.assertEqual(changes, [])
        self.assertEqual(workflow, before)
        self.assertEqual(len(diagnostics), 2)

    def test_repeated_migration_is_idempotent(self):
        workflow = {
            "nodes": [make_pre_2_0_0_parser_node()],
            "links": [[190, 85, 0, 53, 0, "STRING"]],
        }
        migrate_workflow(workflow)
        first = copy.deepcopy(workflow)
        self.assertEqual(migrate_workflow(workflow), [])
        self.assertEqual(workflow, first)


class JsonNodeMigrationTests(unittest.TestCase):
    def test_old_order_is_repaired_by_name(self):
        workflow = {"nodes": [make_old_json_node()], "links": []}
        workflow["links"] = [
            [145, 57, 0, 99, 0, "STRING"],
            [212, 54, 3, 99, 1, "STRING"],
            [211, 63, 0, 99, 2, "STRING"],
            [213, 53, 2, 99, 3, "STRING"],
            [217, 77, 1, 99, 4, "STRING"],
        ]
        changes = migrate_workflow(workflow)
        self.assertEqual(len(changes), 1)

        names = [item["name"] for item in workflow["nodes"][0]["inputs"]]
        self.assertEqual(names, [
            "configuration_prefix", "audio_tags_json", "title", "artwork_path", "metadata_json",
            "collision_mode", "filename_mode", "create_directories",
        ])
        # Socket inputs are serialized first, so metadata_json moves up.
        by_id = {link[0]: link for link in workflow["links"]}
        for link_id, name in ((145, "metadata_json"), (212, "configuration_prefix"),
                              (211, "audio_tags_json"), (213, "title"), (217, "artwork_path")):
            self.assertEqual(names[by_id[link_id][4]], name)
        self.assertEqual(set(names), set(JSON_NEW_INPUT_ORDER).intersection(names))

    def test_metadata_link_is_only_moved_when_origin_output_proves_it(self):
        node = make_old_json_node()
        workflow = {
            "nodes": [node, {"id": 54, "type": "MiniMaxOutputPaths",
                             "outputs": [{"name": "configuration_prefix"}]},
                      {"id": 57, "type": "MiniMaxSongMetadata",
                       "outputs": [{"name": "metadata_json"}]}],
            "links": [
                [212, 54, 0, 99, 1, "STRING"],  # origin: configuration_prefix -> stays
                [145, 57, 0, 99, 0, "STRING"],  # origin: metadata_json -> may move
            ],
        }
        migrate_workflow(workflow)
        names = [i["name"] for i in workflow["nodes"][0]["inputs"]]
        by_id = {link[0]: link for link in workflow["links"]}
        self.assertEqual(names[by_id[212][4]], "configuration_prefix")
        self.assertEqual(names[by_id[145][4]], JSON_METADATA_INPUT)


class NestedGraphTests(unittest.TestCase):
    def test_subgraph_object_links_are_migrated(self):
        subgraph = {
            "id": "sub-1",
            "nodes": [
                {
                    "id": 53,
                    "type": PARSER_NODE_TYPE,
                    "inputs": [
                        _entry("song_count", "INT", widget=True),
                        _entry("structured_llm_output"),
                    ],
                    "outputs": [],
                }
            ],
            "links": [
                {"id": 190, "origin_id": 85, "origin_slot": 0, "target_id": 53,
                 "target_slot": 0, "type": "STRING"},
            ],
        }
        workflow = {"nodes": [], "links": [], "definitions": {"subgraphs": [subgraph]}}
        changes = migrate_workflow(workflow)
        self.assertEqual(len(changes), 1)
        names = [i["name"] for i in subgraph["nodes"][0]["inputs"]]
        self.assertEqual(names[subgraph["links"][0]["target_slot"]], PARSER_STRUCTURED_INPUT)

    def test_virtual_boundary_nodes_are_retained(self):
        subgraph = {
            "id": "sub-1",
            "inputNode": {"id": -10, "bounding": [0, 0, 10, 10]},
            "outputNode": {"id": -20, "bounding": [0, 0, 10, 10]},
            "inputs": [{"id": "u1", "name": "caption", "type": "STRING", "linkIds": [45]}],
            "outputs": [{"id": "u2", "name": "AUDIO", "type": "AUDIO", "linkIds": [62]}],
            "nodes": [{"id": 1, "type": "UNETLoader", "inputs": [], "outputs": []}],
            "links": [],
        }
        workflow = {"nodes": [], "links": [], "definitions": {"subgraphs": [subgraph]}}
        before = copy.deepcopy(subgraph)
        migrate_workflow(workflow)
        self.assertEqual(subgraph["inputNode"], before["inputNode"])
        self.assertEqual(subgraph["outputNode"], before["outputNode"])
        self.assertEqual(subgraph["inputs"], before["inputs"])
        self.assertEqual(subgraph["outputs"], before["outputs"])

    def test_external_dependencies_are_found_in_subgraphs(self):
        workflow = {
            "nodes": [{"id": 81, "type": "LLMSessionChatNode"}],
            "definitions": {"subgraphs": [{"nodes": [{"id": 7, "type": "EgregoraAudioUpscaler"}]}]},
        }
        found = find_external_node_dependencies(workflow)
        self.assertIn((81, "MiniMaxLLMChat (or the legacy external node if you keep it installed)"), found)
        self.assertIn((7, "MiniMaxFlashSRAudio"), found)

    def test_bundled_workflow_has_no_external_nodes(self):
        for path in WORKFLOWS:
            wf = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(find_external_node_dependencies(wf), [], path.name)


if __name__ == "__main__":
    unittest.main()
