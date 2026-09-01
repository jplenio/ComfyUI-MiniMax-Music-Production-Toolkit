from __future__ import annotations

import importlib.util
import json
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "example_workflows" / "MiniMax_Music3_Production_Toolkit.json"
BUILDER = ROOT / "scripts" / "build_public_workflow.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("minimax_workflow_builder", BUILDER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WorkflowBuilderTests(unittest.TestCase):
    def test_artwork_input_normalizer_repairs_slots(self):
        module = load_builder()
        wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        artwork = next(n for n in wf["nodes"] if n.get("type") == "SaveImageSmartPrefix")

        # Recreate the v1.0.5 serialization regression deliberately: linked title/tag
        # sockets precede the widget-backed inputs in the saved node.
        bad_order = [
            "image", "filename_prefix", "title", "audio_tags_json",
            "collision_mode", "create_directories", "jpeg_quality", "filename_mode",
        ]
        by_name = {item["name"]: item for item in artwork["inputs"]}
        artwork["inputs"] = [deepcopy(by_name[name]) for name in bad_order]
        links = {link[0]: link for link in wf["links"]}
        for slot, item in enumerate(artwork["inputs"]):
            if item.get("link") is not None:
                links[item["link"]][4] = slot

        module.normalize_artwork_saver_inputs(wf)

        expected = [
            "image", "filename_prefix", "collision_mode", "create_directories",
            "jpeg_quality", "title", "audio_tags_json", "filename_mode",
        ]
        self.assertEqual([item["name"] for item in artwork["inputs"]], expected)
        self.assertEqual(links[218][4], 5)
        self.assertEqual(links[219][4], 6)


if __name__ == "__main__":
    unittest.main()
