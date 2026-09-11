"""Traceable declip findings: confidence, regions and honest caveats (Q01).

Q01 asks that limiter-processed or intentionally distorted material is not
presented as safely repairable clipping, that the reconstruction makes no
promise of restoring the original, and that the repaired regions are marked so
they can be auditioned against the source.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_toolkit_modules():
    pkg_name = "_toolkit_declip_confidence_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    for module_name in ("toolkit_logging", "audio_utils", "audio_declip"):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return sys.modules[f"{pkg_name}.audio_declip"]


declip = load_toolkit_modules()

import numpy as np  # noqa: E402
import torch  # noqa: E402

RATE = 48000
DEFAULTS = dict(sr=RATE, threshold_pct=98.0, plateau_tol_pct=0.5, min_flat_samples=4,
                context_samples=16, max_repair_ms=30.0, max_extension_db=3.0, analyze_only=False)


def run(signal, **overrides):
    kwargs = dict(DEFAULTS)
    kwargs.update(overrides)
    return declip._repair_channel(signal, **kwargs)


def clean_signal(seconds=1.0):
    rng = np.random.default_rng(3)
    return (rng.standard_normal(int(seconds * RATE)) * 0.2).astype(np.float32)


def clipped_signal(seconds=1.0):
    """Short, flat-topped crests with context - the case declip exists for."""
    signal = clean_signal(seconds)
    for start in (4000, 20000, 30000):
        signal[start:start + 6] = 0.95
    return signal


def limited_signal(seconds=1.0):
    """A long, flat plateau: limiter processing rather than clipped crests."""
    signal = clean_signal(seconds)
    signal[5000:20000] = 0.99
    return signal


class ConfidenceTests(unittest.TestCase):
    def test_a_clean_signal_reports_no_candidates(self):
        _out, stats = run(clean_signal())
        self.assertEqual(stats["candidate_regions"], 0)
        self.assertEqual(stats["confidence"], "none")
        self.assertIn("no clipping candidates", stats["confidence_reason"])

    def test_short_flat_crests_are_high_confidence(self):
        _out, stats = run(clipped_signal())
        self.assertGreater(stats["candidate_regions"], 0)
        self.assertEqual(stats["confidence"], "high")
        self.assertIn("flat-topped crests", stats["confidence_reason"])

    def test_a_long_plateau_is_not_sold_as_repairable_clipping(self):
        _out, stats = run(limited_signal())
        self.assertEqual(stats["confidence"], "low")
        self.assertIn("limiter processing", stats["confidence_reason"])
        self.assertTrue(
            any("not safely repairable clipping" in caveat for caveat in stats["caveats"]),
            "the report must say what the material probably is",
        )

    def test_analyze_only_reports_the_same_findings(self):
        _out, stats = run(limited_signal(), analyze_only=True)
        self.assertEqual(stats["confidence"], "low")
        self.assertGreater(stats["candidate_regions"], 0)


class RegionReportTests(unittest.TestCase):
    def test_regions_are_listed_with_position_and_shape(self):
        _out, stats = run(clipped_signal())
        regions = stats["regions_for_review"]
        self.assertGreater(len(regions), 0)
        for region in regions:
            with self.subTest(region=region):
                self.assertLess(region["start_sample"], region["end_sample"])
                self.assertGreaterEqual(region["samples"], 1)
                self.assertIn(region["classification"], ("flat_top", "long_plateau", "edge_of_signal"))
        self.assertIn("flat_top", {region["classification"] for region in regions})
        self.assertFalse(stats["regions_truncated"])

    def test_a_long_plateau_is_classified_as_such(self):
        _out, stats = run(limited_signal())
        self.assertIn("long_plateau", {region["classification"] for region in stats["regions_for_review"]})

    def test_the_region_list_is_bounded(self):
        signal = clean_signal(seconds=2.0)
        for start in range(0, 90000, 300):  # many candidates
            signal[start:start + 5] = 0.97
        _out, stats = run(signal)
        self.assertLessEqual(len(stats["regions_for_review"]), 64)
        self.assertTrue(stats["regions_truncated"], "a truncated list must say so")

    def test_positions_convert_to_milliseconds(self):
        _out, stats = run(clipped_signal())
        region = stats["regions_for_review"][0]
        self.assertAlmostEqual(region["start_ms"], region["start_sample"] / RATE * 1000.0, places=2)


class CaveatTests(unittest.TestCase):
    def test_the_reconstruction_never_promises_the_original(self):
        for signal in (clean_signal(), clipped_signal(), limited_signal()):
            with self.subTest(signal=len(signal)):
                _out, stats = run(signal)
                self.assertTrue(
                    any("does not restore the original samples" in caveat for caveat in stats["caveats"]),
                    "the caveat must be present in every report",
                )

    def test_the_node_report_carries_the_findings(self):
        audio = {"waveform": torch.from_numpy(clipped_signal()[None, None, :]), "sample_rate": RATE}
        node = declip.AudioDeclipRepair()
        spec = node.INPUT_TYPES()["required"]
        kwargs = {"audio": audio}
        for name, entry in spec.items():
            if name == "audio":
                continue
            options = entry[1] if isinstance(entry, tuple) and len(entry) > 1 else {}
            kwargs[name] = options.get("default", entry[0][0] if isinstance(entry[0], list) else 0)
        result = node.process(**kwargs)
        report = json.loads(result[1])
        self.assertIn("channel_reports", report)
        channel = report["channel_reports"][0]
        self.assertIn("confidence", channel)
        self.assertIn("regions_for_review", channel)
        self.assertTrue(channel["caveats"])

    def test_the_audio_result_is_unchanged_by_the_reporting(self):
        signal = clipped_signal()
        repaired, _stats = run(signal)
        reference = clipped_signal()
        repaired_again, _stats2 = run(reference)
        self.assertTrue(np.array_equal(repaired, repaired_again))


if __name__ == "__main__":
    unittest.main()
