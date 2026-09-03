from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow_schema import (
    JSON_NEW_INPUT_ORDER,
    JSON_NODE_TYPE,
    PARSER_NEW_INPUT_ORDER,
    PARSER_NODE_TYPE,
    find_external_node_dependencies,
    migrate_workflow,
)


def make_old_parser_node() -> dict:
    return {
        "id": 53,
        "type": PARSER_NODE_TYPE,
        "inputs": [
            {"name": "structured_llm_output", "type": "STRING", "link": 190},
            {"name": "song_count", "type": "INT", "widget": {"name": "song_count"}},
            {"name": "seed_mode", "type": "COMBO", "widget": {"name": "seed_mode"}},
            {"name": "base_seed", "type": "INT", "widget": {"name": "base_seed"}},
            {"name": "user_prompt", "type": "STRING", "widget": {"name": "user_prompt"}, "link": 178},
            {"name": "source_name_override", "type": "STRING", "widget": {"name": "source_name_override"}, "link": 179},
            {"name": "fallback_title", "type": "STRING", "widget": {"name": "fallback_title"}},
        ],
        "outputs": [],
    }


class WorkflowSchemaMigrationTests(unittest.TestCase):
    def test_old_parser_node_is_detected(self):
        workflow = {
            "nodes": [make_old_parser_node(), {"id": 1, "type": "MiniMaxLLMChat"}],
            "links": [
                [190, 85, 0, 53, 0, "STRING"],
                [178, 80, 1, 53, 4, "STRING"],
                [179, 80, 2, 53, 5, "STRING"],
            ],
        }
        changes = migrate_workflow(workflow)
        self.assertEqual(len(changes), 1)
        self.assertIn("node 53", changes[0])

        parser = workflow["nodes"][0]
        names = [i["name"] for i in parser["inputs"]]
        # Entries that existed in the old order are rebuilt in canonical order.
        expected = [n for n in PARSER_NEW_INPUT_ORDER if n in names]
        self.assertEqual(names[:7], expected[:7])

        # Link slots remapped by name: structured_llm_output 0->6, user_prompt 4->3,
        # source_name_override 5->4.
        by_id = {link[0]: link for link in workflow["links"]}
        self.assertEqual(by_id[190][4], PARSER_NEW_INPUT_ORDER.index("structured_llm_output"))
        self.assertEqual(by_id[178][4], PARSER_NEW_INPUT_ORDER.index("user_prompt"))
        self.assertEqual(by_id[179][4], PARSER_NEW_INPUT_ORDER.index("source_name_override"))

    def test_new_order_workflow_is_untouched(self):
        node = {"id": 53, "type": PARSER_NODE_TYPE, "inputs": [
            {"name": name, "type": "STRING", "link": None} for name in PARSER_NEW_INPUT_ORDER
        ]}
        workflow = {"nodes": [node], "links": []}
        changes = migrate_workflow(workflow)
        self.assertEqual(changes, [])
        self.assertEqual(workflow["nodes"][0]["inputs"], node["inputs"])

    def test_migration_is_idempotent(self):
        workflow = {
            "nodes": [make_old_parser_node()],
            "links": [[190, 85, 0, 53, 0, "STRING"]],
        }
        migrate_workflow(workflow)
        first = copy.deepcopy(workflow)
        self.assertEqual(migrate_workflow(workflow), [])
        self.assertEqual(workflow, first)

    def test_external_node_dependencies_are_reported(self):
        workflow = {
            "nodes": [
                {"id": 81, "type": "LLMSessionChatNode"},
                {"id": 45, "type": "EgregoraAudioUpscaler"},
                {"id": 20, "type": "MiniMaxLLMChat"},
            ]
        }
        found = find_external_node_dependencies(workflow)
        self.assertEqual(found, [(81, "MiniMaxLLMChat (or the legacy external node if you keep it installed)"), (45, "MiniMaxFlashSRAudio")])

    def test_old_json_node_order_is_repaired_by_name(self):
        node = {
            "id": 99,
            "type": JSON_NODE_TYPE,
            "inputs": [
                {"name": "metadata_json", "type": "STRING", "link": 145},
                {"name": "configuration_prefix", "type": "STRING", "link": 212},
                {"name": "audio_tags_json", "type": "STRING", "link": 211},
                {"name": "title", "type": "STRING", "link": 213},
                {"name": "artwork_path", "type": "STRING", "link": 217},
                {"name": "collision_mode", "type": "COMBO", "widget": {"name": "collision_mode"}},
                {"name": "filename_mode", "type": "COMBO", "widget": {"name": "filename_mode"}},
                {"name": "create_directories", "type": "BOOLEAN", "widget": {"name": "create_directories"}},
            ],
            "outputs": [],
        }
        workflow = {
            "nodes": [node],
            "links": [
                [145, 57, 0, 99, 0, "STRING"],
                [212, 54, 3, 99, 1, "STRING"],
                [211, 63, 0, 99, 2, "STRING"],
                [213, 53, 2, 99, 3, "STRING"],
                [217, 77, 1, 99, 4, "STRING"],
            ],
        }
        changes = migrate_workflow(workflow)
        self.assertEqual(len(changes), 1)
        self.assertIn("node 99", changes[0])

        names = [item["name"] for item in workflow["nodes"][0]["inputs"]]
        self.assertEqual(names[0], JSON_NEW_INPUT_ORDER[0])
        self.assertEqual(names[-1], "metadata_json")

        by_id = {link[0]: link for link in workflow["links"]}
        self.assertEqual(by_id[145][4], JSON_NEW_INPUT_ORDER.index("metadata_json"))
        self.assertEqual(by_id[212][4], JSON_NEW_INPUT_ORDER.index("configuration_prefix"))
        self.assertEqual(by_id[211][4], JSON_NEW_INPUT_ORDER.index("audio_tags_json"))

    def test_new_json_node_order_is_untouched(self):
        node = {"id": 99, "type": JSON_NODE_TYPE, "inputs": [
            {"name": name, "type": "STRING", "link": None} for name in JSON_NEW_INPUT_ORDER
        ]}
        workflow = {"nodes": [node], "links": []}
        self.assertEqual(migrate_workflow(workflow), [])
        self.assertEqual(workflow["nodes"][0]["inputs"], node["inputs"])

    def test_bundled_workflow_has_no_external_nodes(self):
        wf = json.loads(
            (ROOT / "example_workflows" / "MiniMax_Music3_Production_Toolkit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(find_external_node_dependencies(wf), [])


if __name__ == "__main__":
    unittest.main()
