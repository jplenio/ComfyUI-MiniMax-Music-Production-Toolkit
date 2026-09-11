"""Regression tests for the B01 benchmark harness and its fixtures.

These tests pin the harness *contract*: deterministic workloads, warm-ups
excluded from the spread, unknown values staying ``None``, telemetry carrying no
prompt/audio content, and unmeasurable stages being reported instead of omitted.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def load_benchmark():
    spec = importlib.util.spec_from_file_location("_benchmark_toolkit", ROOT / "scripts" / "benchmark_toolkit.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bench = load_benchmark()


class MatrixAndFixtureTests(unittest.TestCase):
    def test_matrix_is_loadable_and_has_the_required_axes(self):
        matrix = bench.load_matrix()
        axes = matrix["audio"]["axes"]
        self.assertEqual(sorted(axes["seconds"]), [10, 60, 300])
        self.assertEqual(sorted(axes["channels"]), [1, 2])
        self.assertEqual(sorted(axes["sample_rate"]), [44100, 48000, 96000])
        self.assertEqual(sorted(axes["batch"]), [1, 2])

    def test_hardware_classes_are_declared_as_untested(self):
        matrix = bench.load_matrix()
        self.assertEqual(matrix["hardware"]["status"], "untested")
        self.assertEqual(sorted(str(v) for v in matrix["hardware"]["ram_gib_classes"]), ["16", "32", "64", "8"])
        self.assertIn("32+", [str(v) for v in matrix["hardware"]["vram_gib_classes"]])

    def test_default_profile_expands_to_one_workload(self):
        matrix = bench.load_matrix()
        workloads = bench.expand_audio_workloads(matrix, full=False)
        self.assertEqual(len(workloads), 1)
        self.assertEqual(workloads[0], matrix["audio"]["default_profile"])

    def test_full_matrix_expands_to_the_axis_product(self):
        workloads = bench.expand_audio_workloads(bench.load_matrix(), full=True)
        self.assertEqual(len(workloads), 3 * 2 * 3 * 2)

    def test_workload_identifier_is_stable_and_readable(self):
        self.assertEqual(
            bench.describe_workload({"seconds": 60, "channels": 1, "sample_rate": 44100, "batch": 2}),
            "60s_1ch_44100Hz_b2",
        )

    def test_briefs_fixture_covers_every_required_category(self):
        data = json.loads((FIXTURES / "benchmark_briefs.json").read_text(encoding="utf-8"))
        briefs = data["briefs"]
        self.assertGreaterEqual(len(briefs), 20)
        self.assertEqual(len({b["id"] for b in briefs}), len(briefs))
        categories = {b["category"] for b in briefs}
        self.assertEqual(
            categories,
            {"instrumental", "english_vocal", "german_vocal", "sparse_vocal", "non_latin", "custom_lyrics"},
        )
        for brief in briefs:
            with self.subTest(brief=brief["id"]):
                self.assertIsInstance(brief["seed"], int)

    def test_briefs_are_not_needed_by_the_audio_harness(self):
        # The LLM briefs are fixtures for the LLM half of the matrix; the audio
        # benchmark must never read prompt text into its telemetry.
        matrix = bench.load_matrix()
        self.assertEqual(matrix["llm"]["briefs_file"], "benchmark_briefs.json")
        self.assertTrue(matrix["llm"]["cold_and_warm"])


class MeasurementPrimitiveTests(unittest.TestCase):
    def test_summarize_times_reports_median_and_spread(self):
        summary = bench.summarize_times([10.0, 20.0, 30.0])
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["median_ms"], 20.0)
        self.assertEqual(summary["min_ms"], 10.0)
        self.assertEqual(summary["max_ms"], 30.0)
        self.assertIsNotNone(summary["stdev_ms"])

    def test_single_sample_reports_no_spread_instead_of_zero(self):
        summary = bench.summarize_times([12.5])
        self.assertEqual(summary["count"], 1)
        self.assertIsNone(summary["stdev_ms"])
        self.assertEqual(summary["median_ms"], 12.5)

    def test_empty_input_is_unknown_not_zero(self):
        summary = bench.summarize_times([])
        self.assertEqual(summary["count"], 0)
        self.assertIsNone(summary["median_ms"])
        self.assertIsNone(summary["stdev_ms"])

    def test_warmups_are_excluded_from_the_timing(self):
        calls = {"n": 0}

        def work():
            calls["n"] += 1

        result = bench.measure(work, repeats=3, warmups=2)
        self.assertEqual(calls["n"], 5)
        self.assertEqual(result["count"], 3)

    def test_process_memory_is_bytes_or_unknown_never_a_fake_zero(self):
        memory = bench.process_memory_bytes()
        self.assertEqual(set(memory), {"rss_bytes", "peak_rss_bytes"})
        for value in memory.values():
            if value is not None:
                self.assertGreater(value, 0)


class InputDefaultsTests(unittest.TestCase):
    def test_defaults_come_from_the_node_declaration(self):
        self.assertEqual(bench.default_for_input(("INT", {"default": 7, "min": 0})), 7)
        self.assertEqual(bench.default_for_input(("FLOAT", {"default": 1.5})), 1.5)
        self.assertEqual(bench.default_for_input(("BOOLEAN", {"default": True})), True)
        self.assertEqual(bench.default_for_input(("STRING", {"default": "x"})), "x")

    def test_combo_without_default_uses_the_first_entry(self):
        self.assertEqual(bench.default_for_input((["a", "b"], {})), "a")

    def test_explicit_default_beats_the_first_combo_entry(self):
        self.assertEqual(bench.default_for_input((["a", "b"], {"default": "b"})), "b")

    def test_malformed_entry_is_none(self):
        self.assertIsNone(bench.default_for_input(None))
        self.assertIsNone(bench.default_for_input(()))

    def test_stage_kwargs_inject_the_fixture_audio(self):
        class FakeNode:
            @classmethod
            def INPUT_TYPES(cls):
                return {
                    "required": {
                        "audio": ("AUDIO", {}),
                        "mode": (["gentle", "strong"], {"default": "strong"}),
                    }
                }

        kwargs = bench.stage_kwargs(FakeNode, ("audio",), {"waveform": "x"})
        self.assertEqual(kwargs["audio"], {"waveform": "x"})
        self.assertEqual(kwargs["mode"], "strong")

    def test_unfillable_required_input_is_an_error_not_a_guess(self):
        class FakeNode:
            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {"audio": ("AUDIO", {}), "caption": ("STRING", {"forceInput": True})}}

        with self.assertRaises(ValueError) as ctx:
            bench.stage_kwargs(FakeNode, ("audio",), {"waveform": "x"})
        self.assertIn("caption", str(ctx.exception))


class BenchmarkRunTests(unittest.TestCase):
    def test_real_stage_runs_and_reports_the_environment(self):
        report = bench.run_benchmark(stages=["lowpass"], repeats=1, warmups=0)
        self.assertTrue(report["results"], "the low-pass stage must be measurable on synthetic audio")
        entry = report["results"][0]
        self.assertEqual(entry["stage"], "lowpass")
        self.assertEqual(entry["node"], "FlashSRLowpassLab")
        self.assertEqual(entry["workload_id"], "10s_2ch_48000Hz_b1")
        self.assertEqual(entry["timing"]["count"], 1)
        self.assertIn("torch", report["environment"])
        self.assertEqual(report["hardware_status"], "untested")

    def test_unmeasurable_stages_are_reported_with_a_reason(self):
        report = bench.run_benchmark(stages=["lowpass"], repeats=1, warmups=0)
        for name in ("flashsr", "minimax_generation", "llm_chat", "flux_artwork"):
            with self.subTest(stage=name):
                self.assertIn(name, report["not_measured"])
                self.assertTrue(report["not_measured"][name])

    def test_unknown_stage_name_is_rejected(self):
        with self.assertRaises(ValueError):
            bench.run_benchmark(stages=["does-not-exist"], repeats=1)

    def test_telemetry_never_contains_prompt_or_audio_content(self):
        report = bench.run_benchmark(stages=["lowpass"], repeats=1, warmups=0)
        payload = json.dumps(report)
        briefs = json.loads((FIXTURES / "benchmark_briefs.json").read_text(encoding="utf-8"))["briefs"]
        for brief in briefs:
            with self.subTest(brief=brief["id"]):
                self.assertNotIn(brief["caption"], payload)
                self.assertNotIn(brief["lyrics"], payload)
        self.assertNotIn("waveform", payload)

    def test_report_renders_the_not_measured_list_and_the_untested_note(self):
        report = bench.run_benchmark(stages=["lowpass"], repeats=1, warmups=0)
        text = bench.format_report(report)
        self.assertIn("Stage timings", text)
        self.assertIn("Not measured here", text)
        self.assertIn("untested", text)

    def test_list_mode_documents_every_stage(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = bench.main(["--list"])
        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        for stage in bench.AUDIO_STAGES:
            self.assertIn(stage, output)
        for stage in bench.UNMEASURABLE_STAGES:
            self.assertIn(stage, output)


if __name__ == "__main__":
    unittest.main()
