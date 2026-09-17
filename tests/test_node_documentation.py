"""Every node must explain itself: a description, a doc page and real tooltips.

The tooltip tables in ``ui_help.py`` end in a generic boilerplate text, and the
installer uses it for any input nobody described. That is a safety net, not
documentation - this test fails as soon as an input would need it, so a new field
cannot ship without help text.
"""
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from _toolkit_bootstrap import load_entry_point  # noqa: E402


class NodeDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.ui_help = importlib.import_module(cls.pkg.__name__ + ".ui_help")
        cls.docs = ROOT / "web" / "docs"

    def test_no_input_falls_back_to_boilerplate_text(self):
        missing = self.ui_help.find_missing_explicit_tooltips(self.pkg.NODE_CLASS_MAPPINGS)
        self.assertEqual(
            missing, [],
            "these inputs have no tooltip of their own: "
            + "; ".join(f"{node}.{name}" for node, _section, name in missing))

    def test_every_tooltip_says_something_specific(self):
        boilerplate = self.ui_help._fallback_tooltip("x")
        for node_type, cls in self.pkg.NODE_CLASS_MAPPINGS.items():
            data = cls.INPUT_TYPES()
            for section in ("required", "optional"):
                for name, spec in (data.get(section) or {}).items():
                    tooltip = spec[1].get("tooltip") if len(spec) > 1 else None
                    self.assertTrue(tooltip and tooltip.strip(), f"{node_type}.{name}")
                    self.assertNotEqual(tooltip, boilerplate, f"{node_type}.{name} uses the fallback")
                    self.assertGreater(len(tooltip), 40,
                                       f"{node_type}.{name} tooltip is too short to help")

    def test_every_node_has_a_description_and_a_doc_page(self):
        for node_type, cls in sorted(self.pkg.NODE_CLASS_MAPPINGS.items()):
            description = (getattr(cls, "DESCRIPTION", "") or "").strip()
            self.assertTrue(description, f"{node_type} has no DESCRIPTION")
            self.assertGreater(len(description), 40, f"{node_type} description is too short")
            page = self.docs / f"{node_type}.md"
            self.assertTrue(page.is_file(), f"{node_type} has no web/docs/{node_type}.md")
            self.assertGreater(len(page.read_text(encoding="utf-8").split()), 40,
                               f"{node_type} doc page is too thin")

    def test_no_orphaned_doc_pages(self):
        pages = {path.stem for path in self.docs.glob("*.md")}
        orphans = sorted(pages - set(self.pkg.NODE_CLASS_MAPPINGS))
        self.assertEqual(orphans, [], "doc pages without a node: " + ", ".join(orphans))

    def test_tooltip_installation_keeps_the_authored_text(self):
        """A second installation must not replace an authored tooltip with a table entry."""
        cls = self.pkg.NODE_CLASS_MAPPINGS["MiniMaxAudioBranchSelect"]
        before = cls.INPUT_TYPES()["required"]["mix"][1]["tooltip"]
        self.ui_help.install_input_tooltips(self.pkg.NODE_CLASS_MAPPINGS)
        after = cls.INPUT_TYPES()["required"]["mix"][1]["tooltip"]
        self.assertEqual(before, after)

    def test_indexed_inputs_are_described_by_pattern(self):
        optional = self.pkg.NODE_CLASS_MAPPINGS["MiniMaxInstrumentalPick"].INPUT_TYPES()["optional"]
        for index in range(11):
            for prefix in ("candidate", "report"):
                tooltip = optional[f"{prefix}_{index}"][1]["tooltip"]
                self.assertIn("Lazy", tooltip, f"{prefix}_{index}")
        stage = self.pkg.NODE_CLASS_MAPPINGS["MusicOptionalStage"].INPUT_TYPES()["optional"]
        self.assertIn("Lazy", stage["report_1"][1]["tooltip"])


if __name__ == "__main__":
    unittest.main()
