"""Catalog recipes through the actual EQ renderer, not just UI snapshots."""
import importlib
import json
from pathlib import Path
import unittest

import numpy as np
import torch
from _toolkit_bootstrap import load_entry_point

PACKAGE, _ = load_entry_point()
eq = importlib.import_module(f"{PACKAGE.__name__}.eq_config")
renderer = importlib.import_module(f"{PACKAGE.__name__}.audio_eq")
auto = importlib.import_module(f"{PACKAGE.__name__}.audio_auto_eq")
CATALOG = json.loads((Path(__file__).resolve().parents[1] / "web/eq_presets.json").read_text(encoding="utf-8"))


class EQPresetTests(unittest.TestCase):
    def test_all_curves_render_finite_without_changing_audio_dimensions(self):
        for sr in (32000, 44100, 48000):
            source = {"sample_rate": sr, "waveform": torch.from_numpy(
                np.random.default_rng(5).normal(0, .05, (2, 2, 4096)).astype(np.float32))}
            for preset in CATALOG["manual"]:
                with self.subTest(rate=sr, preset=preset["name"]):
                    result = renderer.MiniMaxParametricEQ().process(source, json.dumps(preset["settings"]))["result"]
                    output, report = result[0], json.loads(result[1])
                    self.assertEqual(output["waveform"].shape, source["waveform"].shape)
                    self.assertEqual(output["sample_rate"], sr)
                    self.assertTrue(torch.isfinite(output["waveform"]).all())
                    self.assertFalse(report["hidden_normalization"])
                    if preset["name"] == "Flat":
                        self.assertIs(output, source)

    def test_yue2_curves_reduce_harshness_with_little_bass_change(self):
        for sr in (32000, 44100, 48000):
            curves = [eq.response_db(p["settings"], sr, np.array([100, 3500, 7500, 14000]))
                      for p in CATALOG["manual"] if p["name"].startswith("YuE2")]
            self.assertEqual(len(curves), 2)
            for curve in curves:
                self.assertLess(abs(curve[0]), .1)
                # A shelf reaches half its asymptotic gain at its corner.
                self.assertTrue(np.all(curve[1:] < -1.0))
            self.assertTrue(np.all(curves[1][1:] < curves[0][1:]))

    def test_catalog_limits_and_unchanged_node_defaults(self):
        self.assertEqual(len(CATALOG["auto"]), 10)
        self.assertEqual(len(CATALOG["manual"]), 24)
        for group in CATALOG.values():
            self.assertEqual(len({p["name"] for p in group}), len(group))
        inputs = auto.MiniMaxAutoEQAnalyze.INPUT_TYPES()["required"]
        for preset in CATALOG["auto"]:
            for key, value in preset["values"].items():
                kind, limits = inputs[key]
                if isinstance(kind, list):
                    self.assertIn(value, kind)
                else:
                    self.assertLessEqual(limits["min"], value)
                    self.assertLessEqual(value, limits["max"])
        balanced = next(p for p in CATALOG["auto"] if p["name"] == "Reference - balanced")
        self.assertEqual(balanced["values"], {k:inputs[k][1]["default"] for k in balanced["values"]})
        self.assertEqual(CATALOG["manual"][0]["name"], "Flat")
        self.assertEqual(CATALOG["manual"][0]["settings"], json.loads(eq.DEFAULT_SETTINGS))


if __name__ == "__main__":
    unittest.main()
