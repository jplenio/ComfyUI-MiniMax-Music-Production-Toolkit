"""Frozen public contract of every registered toolkit node (F01 / T01).

The serialized example workflow is a compatibility surface: ComfyUI resolves
stored input slots positionally, so renaming, reordering or retyping an input
silently breaks older saved workflows.  This test freezes the complete public
contract of legacy and additive audio identifiers against a checked-in snapshot
(``tests/fixtures/node_contracts.json``).

The snapshot deliberately contains the *undecorated* schemas (tooltips are
stripped); tooltip installation is asserted separately, including its
idempotency.  Regenerate the fixture only with a reviewed, intentional
contract change:

    python scripts/dump_node_contracts.py --write
"""
from __future__ import annotations

import json
import unittest

from _toolkit_bootstrap import (
    CONTRACT_FIXTURE,
    EXPECTED_ROUTES,
    NODE_OWNER,
    collect,
    load_entry_point,
)

ENTRY_POINT = None
HOST = None


def setUpModule():
    global ENTRY_POINT, HOST
    ENTRY_POINT, HOST = load_entry_point()


class EntryPointTests(unittest.TestCase):
    """The real ``__init__.py`` must run outside ComfyUI and register cleanly."""

    def test_all_identifiers_are_registered(self):
        self.assertEqual(len(ENTRY_POINT.NODE_CLASS_MAPPINGS), 34)
        self.assertEqual(set(ENTRY_POINT.NODE_CLASS_MAPPINGS), set(NODE_OWNER))

    def test_display_name_for_every_identifier(self):
        for node_type in NODE_OWNER:
            display = ENTRY_POINT.NODE_DISPLAY_NAME_MAPPINGS.get(node_type)
            self.assertTrue(display, f"{node_type} has no display name")
            self.assertNotEqual(display, node_type, f"{node_type} display name is the raw identifier")

    def test_no_duplicate_identifiers_across_modules(self):
        # Merging module mappings silently hides a collision; rebuild the count
        # from the owning modules and compare it with the merged mapping.
        total = 0
        for owner in set(NODE_OWNER.values()):
            module = __import__(f"{ENTRY_POINT.__name__}.{owner}", fromlist=["NODE_CLASS_MAPPINGS"])
            total += len(module.NODE_CLASS_MAPPINGS)
        self.assertEqual(total, len(ENTRY_POINT.NODE_CLASS_MAPPINGS))

    def test_node_owner_module_is_stable(self):
        for node_type, owner in NODE_OWNER.items():
            cls = ENTRY_POINT.NODE_CLASS_MAPPINGS[node_type]
            self.assertEqual(cls.__module__.rsplit(".", 1)[-1], owner, node_type)

    def test_web_directory_constant(self):
        self.assertEqual(ENTRY_POINT.WEB_DIRECTORY, "./web")

    def test_legacy_nodes_keep_registering(self):
        # These are absent from the bundled example workflows but are public API.
        for node_type in (
            "MiniMaxPromptBatchLoader",
            "MiniMaxPromptSourceArtworkV16",
            "MiniMaxLLMTemplateV16",
            "MiniMaxSongMetadata",
            "MiniMaxMetadataLoader",
            "FlashSRProcessingSettings",
            "SaveAudioAbsolutePath",
            "KSamplerWithConfig",
        ):
            self.assertIn(node_type, ENTRY_POINT.NODE_CLASS_MAPPINGS)

    def test_routes_registered_with_fake_server(self):
        registered = [(method, path) for method, path, _ in HOST.routes]
        for expected in EXPECTED_ROUTES:
            self.assertIn(expected, registered)


class TooltipTests(unittest.TestCase):
    """Tooltips must decorate every input and installation must be idempotent."""

    def test_every_input_has_a_tooltip(self):
        for node_type, cls in ENTRY_POINT.NODE_CLASS_MAPPINGS.items():
            data = cls.INPUT_TYPES()
            for section in ("required", "optional"):
                for name, spec in data.get(section, {}).items():
                    options = spec[1] if isinstance(spec, tuple) and len(spec) > 1 else None
                    self.assertIsInstance(options, dict, f"{node_type}.{name} lost its options dict")
                    tooltip = options.get("tooltip")
                    self.assertTrue(tooltip and tooltip.strip(), f"{node_type}.{name} has no tooltip")

    def test_installation_is_idempotent(self):
        before = collect(ENTRY_POINT)
        package = __import__(ENTRY_POINT.__name__, fromlist=["NODE_CLASS_MAPPINGS"])
        module = __import__(f"{package.__name__}.ui_help", fromlist=["install_input_tooltips"])
        module.install_input_tooltips(package.NODE_CLASS_MAPPINGS)
        module.install_input_tooltips(package.NODE_CLASS_MAPPINGS)
        self.assertEqual(collect(ENTRY_POINT), before)


class ContractSnapshotTests(unittest.TestCase):
    """The live schemas must match the frozen fixture exactly."""

    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))

    def test_snapshot_covers_every_node(self):
        self.assertEqual(set(self.expected), set(ENTRY_POINT.NODE_CLASS_MAPPINGS))

    def test_contracts_match_snapshot(self):
        actual = collect(ENTRY_POINT)
        for node_type in sorted(self.expected):
            with self.subTest(node=node_type):
                self.assertEqual(
                    actual[node_type],
                    self.expected[node_type],
                    f"{node_type}: public contract drifted from the frozen snapshot. "
                    "If this is intentional, regenerate tests/fixtures/node_contracts.json "
                    "with `python scripts/dump_node_contracts.py --write`.",
                )

    def test_input_order_is_preserved(self):
        # Redundant with the full comparison but fails with a precise message.
        for node_type, expected in self.expected.items():
            cls = ENTRY_POINT.NODE_CLASS_MAPPINGS[node_type]
            data = cls.INPUT_TYPES()
            for section in ("required", "optional"):
                self.assertEqual(
                    list(data.get(section, {}).keys()),
                    list(expected[section].keys()),
                    f"{node_type}: {section} input order drifted",
                )


if __name__ == "__main__":
    unittest.main()
