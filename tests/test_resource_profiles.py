"""Table-driven tests for ``resource_profiles`` (IMPROVE-TODO R01).

The plan requires coverage for: unknown values, CPU-only, low available RAM,
an occupied GPU, unequal GPUs and an invisible second card - and that every
recommendation stays advisory (a caller can always override it).
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_resource_profiles():
    spec = importlib.util.spec_from_file_location("_resource_profiles", ROOT / "resource_profiles.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


rp = load_resource_profiles()
GIB = rp.GIB


def cuda(index, total_gib, free_gib=None, name="Test GPU", physical=None):
    return rp.DeviceInfo(
        id=f"cuda:{index}",
        name=name,
        kind="cuda",
        backend="cuda",
        logical=index,
        physical=index if physical is None else physical,
        vram_total_bytes=None if total_gib is None else int(total_gib * GIB),
        vram_free_bytes=None if free_gib is None else int(free_gib * GIB),
    )


def make_snapshot(devices=(), ram_total=None, ram_available=None, **kwargs):
    return rp.ResourceSnapshot(
        cpu_count=kwargs.pop("cpu_count", 8),
        ram_total_bytes=ram_total,
        ram_available_bytes=ram_available,
        devices=list(devices) + [rp.DeviceInfo(id="cpu", name="CPU", kind="cpu", backend="cpu")],
        backends=kwargs.pop("backends", {"torch": True, "cuda": bool(devices)}),
        **kwargs,
    )


class DetectResourcesTests(unittest.TestCase):
    def test_unknown_values_are_none_and_recorded_as_notes(self):
        detected = rp.detect_resources(
            device_probe=lambda: ([], {}),
            memory_reader=lambda: (None, None),
            cpu_counter=lambda: None,
            environ={},
        )
        self.assertIsNone(detected.cpu_count)
        self.assertIsNone(detected.ram_total_bytes)
        self.assertIsNone(detected.ram_available_bytes)
        self.assertTrue(any("RAM could not be detected" in note for note in detected.notes))
        self.assertTrue(detected.is_cpu_only)
        self.assertIsNotNone(detected.captured_at)

    def test_cpu_only_machine_without_torch(self):
        detected = rp.detect_resources(
            device_probe=lambda: ([], {}),
            memory_reader=lambda: (32 * GIB, 24 * GIB),
            cpu_counter=lambda: 6,
            environ={},
        )
        self.assertTrue(detected.is_cpu_only)
        self.assertEqual(detected.backends, {})
        self.assertTrue(any("CPU-only" in note for note in detected.notes))

    def test_probe_failure_becomes_a_note_not_an_exception(self):
        def boom():
            raise RuntimeError("driver exploded")

        detected = rp.detect_resources(device_probe=boom, memory_reader=lambda: (0, 0), environ={})
        self.assertTrue(any("driver exploded" in note for note in detected.notes))
        self.assertTrue(detected.is_cpu_only)

    def test_environment_is_not_mutated(self):
        environ = {"CUDA_VISIBLE_DEVICES": "1"}
        rp.detect_resources(device_probe=lambda: ([], {}), memory_reader=lambda: (0, 0), environ=environ)
        self.assertEqual(environ, {"CUDA_VISIBLE_DEVICES": "1"})

    def test_module_has_no_top_level_torch_import(self):
        source = (ROOT / "resource_profiles.py").read_text(encoding="utf-8")
        offenders = [
            line for line in source.splitlines() if re.match(r"^(import torch|from torch)\b", line)
        ]
        self.assertEqual(offenders, [], "torch must only be imported lazily inside a function")


class DeviceBudgetTests(unittest.TestCase):
    def test_budget_is_free_minus_the_larger_reserve(self):
        device = cuda(0, 16, 12)
        snap = make_snapshot([device])
        # reserve = max(1 GiB, 10 % of 16 GiB) = 1.6 GiB
        self.assertEqual(rp.device_budget(snap, "cuda:0"), int(12 * GIB) - int(1.6 * GIB))

    def test_minimum_reserve_applies_to_small_cards(self):
        snap = make_snapshot([cuda(0, 4, 3)])
        self.assertEqual(rp.device_budget(snap, "cuda:0"), int(3 * GIB) - rp.RESERVE_MIN_BYTES)

    def test_unknown_free_vram_is_none_not_zero(self):
        snap = make_snapshot([cuda(0, 16, None)])
        self.assertIsNone(rp.device_budget(snap, "cuda:0"))

    def test_cpu_device_has_no_vram_budget(self):
        snap = make_snapshot([])
        self.assertIsNone(rp.device_budget(snap, "cpu"))
        self.assertIsNone(rp.device_budget(snap, "does-not-exist"))


class RecommendationTableTests(unittest.TestCase):
    def test_cpu_only_recommends_the_cpu_profile(self):
        snap = make_snapshot([], ram_total=32 * GIB, ram_available=20 * GIB)
        recommendations = rp.recommend_profiles(snap)
        self.assertEqual([r["id"] for r in recommendations], ["cpu_only"])
        self.assertEqual(recommendations[0]["device"], "cpu")

    def test_unknown_ram_lowers_confidence(self):
        snap = make_snapshot([])
        self.assertEqual(rp.recommend_profiles(snap)[0]["confidence"], "missing")

    def test_unknown_values_do_not_become_zero(self):
        snap = make_snapshot([cuda(0, None, None)])
        recommendation = rp.recommend_profiles(snap)[0]
        self.assertIsNone(recommendation["budget_bytes"])
        self.assertEqual(recommendation["confidence"], "missing")

    def test_low_ram_never_recommends_more_cpu_offload(self):
        snap = make_snapshot([cuda(0, 16, 12)], ram_total=16 * GIB, ram_available=3 * GIB)
        recommendation = rp.recommend_profiles(snap)[0]
        self.assertTrue(any("do not simply increase CPU offload" in note for note in recommendation["notes"]))
        self.assertNotIn("offload more", recommendation["reason"].lower())

    def test_occupied_gpu_is_reported_low_confidence(self):
        snap = make_snapshot([cuda(0, 16, 2)])
        recommendation = rp.recommend_profiles(snap)[0]
        self.assertEqual(recommendation["confidence"], "low")
        self.assertIn("largely occupied", recommendation["reason"])

    def test_gpu_without_headroom_still_reports_the_device(self):
        snap = make_snapshot([cuda(0, 16, 0.5)])
        recommendation = rp.recommend_profiles(snap)[0]
        self.assertEqual(recommendation["budget_bytes"], 0)
        self.assertEqual(recommendation["confidence"], "low")

    def test_unequal_gpus_are_separate_pools(self):
        snap = make_snapshot([cuda(0, 24, 20), cuda(1, 8, 6, name="Small GPU")])
        recommendations = rp.recommend_profiles(snap)
        self.assertEqual(len(recommendations), 2)
        self.assertEqual(
            [r["budget_bytes"] for r in recommendations],
            [rp.device_budget(snap, "cuda:0"), rp.device_budget(snap, "cuda:1")],
        )
        # never summed into one pool
        self.assertNotEqual(recommendations[0]["budget_bytes"], sum(r["budget_bytes"] for r in recommendations))
        self.assertTrue(any("separate memory pools" in note for note in recommendations[0]["notes"]))

    def test_renumbered_devices_are_reported(self):
        snap = make_snapshot(
            [replace(cuda(0, 16, 14), id="cuda:0", logical=0, physical=1)],
            visible_devices_env="1",
        )
        recommendation = rp.recommend_profiles(snap)[0]
        self.assertTrue(any("renumbered" in note for note in recommendation["notes"]))
        self.assertEqual(snap.device("cuda:0").physical, 1)

    def test_recommendations_are_plain_data_and_overridable(self):
        snap = make_snapshot([cuda(0, 16, 12)])
        recommendation = rp.recommend_profiles(snap)[0]
        self.assertEqual(
            set(recommendation),
            {"id", "label", "device", "budget_bytes", "confidence", "reason", "workload", "notes"},
        )
        # advisory only: nothing in the module mutates the snapshot or the host
        self.assertEqual(len(snap.devices), 2)
        self.assertFalse(hasattr(rp, "apply_profile"))

    def test_workload_is_carried_through(self):
        snap = make_snapshot([cuda(0, 16, 12)])
        self.assertEqual(rp.recommend_profiles(snap, workload="llm")[0]["workload"], "llm")


def load_diagnostics():
    spec = importlib.util.spec_from_file_location(
        "_toolkit_diagnostics", ROOT / "scripts" / "toolkit_diagnostics.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DiagnosticsIntegrationTests(unittest.TestCase):
    def test_diagnostics_report_carries_the_resource_section(self):
        module = load_diagnostics()
        report = module.run_diagnostics()
        self.assertIn("resources", report)
        self.assertIn("lines", report["resources"])
        self.assertIn("recommendations", report["resources"])
        text = module.format_report(report)
        self.assertIn("Resources:", text)
        self.assertIn("CPU cores:", text)
        self.assertIn("Recommendation", text)

    def test_resource_detection_failure_is_reported_not_raised(self):
        module = load_diagnostics()
        original = module._load_module

        def boom(name):
            raise RuntimeError("boom")

        module._load_module = boom
        try:
            info = module._check_resources()
        finally:
            module._load_module = original
        self.assertIsNone(info["snapshot"])
        self.assertTrue(any("Resource detection failed" in line for line in info["lines"]))


class ReportFormattingTests(unittest.TestCase):
    def test_report_mentions_unknown_ram_and_the_recommendation(self):
        snap = make_snapshot([cuda(0, 16, 12, name="RTX Test")])
        lines = "\n".join(rp.format_resource_report(snap))
        self.assertIn("RAM: unknown", lines)
        self.assertIn("Device cuda:0 (RTX Test, cuda)", lines)
        self.assertIn("Recommendation", lines)

    def test_report_renders_available_ram_when_known(self):
        snap = make_snapshot([], ram_total=64 * GIB, ram_available=48 * GIB)
        lines = "\n".join(rp.format_resource_report(snap))
        self.assertIn("64.0 GiB total, 48.0 GiB available", lines)


if __name__ == "__main__":
    unittest.main()
