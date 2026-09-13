"""Tests for the raw-PCM FFmpeg transport (IMPROVE-TODO A05).

The pipe path must be *equivalent* to the temporary-file path, not merely
faster: the same signal has to measure the same, no temporary file may appear,
the block writer must produce the interleaved layout FFmpeg expects, and a
failing command must still report the historic message with its stderr tail.
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_toolkit_modules():
    pkg_name = "_toolkit_ffmpeg_pipe_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in (
        "toolkit_logging",
        "ffmpeg_utils",
        "audio_utils",
        "audio_release_prep",
    ):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


MODULES = load_toolkit_modules()
ffmpeg_utils = MODULES["ffmpeg_utils"]
release_prep = MODULES["audio_release_prep"]

import numpy as np  # noqa: E402

FFMPEG_AVAILABLE = ffmpeg_utils.discover_ffmpeg() is not None


def signal(seconds=2.0, rate=48000, channels=2, peak=0.5):
    rng = np.random.default_rng(17)
    frames = int(seconds * rate)
    data = (rng.standard_normal((channels, frames)) * 0.1).astype(np.float32)
    data *= peak / max(1e-9, float(np.abs(data).max()))
    return data


class BlockLayoutTests(unittest.TestCase):
    def test_the_stream_is_time_major_interleaved(self):
        data = np.array([[1.0, 2.0, 3.0], [10.0, 20.0, 30.0]], dtype=np.float32)
        blocks = list(ffmpeg_utils.interleaved_f32le_blocks(data, block_frames=2))
        raw = b"".join(blocks)
        self.assertEqual(raw, np.ascontiguousarray(data.T).tobytes())
        decoded = np.frombuffer(raw, dtype="<f4").reshape(-1, 2)
        np.testing.assert_array_equal(decoded[0], [1.0, 10.0], "frame 0 must carry both channels")
        np.testing.assert_array_equal(decoded[2], [3.0, 30.0])

    def test_blocks_are_bounded_and_cover_everything(self):
        data = signal(seconds=0.2)
        frames = data.shape[1]
        blocks = list(ffmpeg_utils.interleaved_f32le_blocks(data, block_frames=1000))
        self.assertEqual(len(blocks), (frames + 999) // 1000)
        for block in blocks:
            self.assertLessEqual(len(block), 1000 * data.shape[0] * 4)
        self.assertEqual(b"".join(blocks), np.ascontiguousarray(data.T).tobytes())

    def test_mono_blocks_are_a_plain_stream(self):
        data = np.arange(5, dtype=np.float32)[None, :]
        raw = b"".join(ffmpeg_utils.interleaved_f32le_blocks(data, block_frames=2))
        np.testing.assert_array_equal(np.frombuffer(raw, dtype="<f4"), np.arange(5, dtype=np.float32))

    def test_a_single_block_can_hold_the_whole_track(self):
        data = signal(seconds=0.05)
        blocks = list(ffmpeg_utils.interleaved_f32le_blocks(data, block_frames=10 ** 9))
        self.assertEqual(len(blocks), 1)

    def test_the_input_array_is_not_modified(self):
        data = signal(seconds=0.05)
        before = data.copy()
        list(ffmpeg_utils.interleaved_f32le_blocks(data, block_frames=128))
        np.testing.assert_array_equal(data, before)


class PipeRunTests(unittest.TestCase):
    def setUp(self):
        if not FFMPEG_AVAILABLE:  # pragma: no cover - depends on the machine
            self.skipTest("FFmpeg is not available")
        self.ffmpeg = ffmpeg_utils.discover_ffmpeg()

    def test_a_failing_filter_reports_the_message_and_the_tail(self):
        data = signal(seconds=0.2)
        with self.assertRaises(RuntimeError) as ctx:
            ffmpeg_utils.run_ffmpeg_with_pcm(
                [self.ffmpeg, "-hide_banner", "-nostdin", "-f", "f32le", "-ar", "48000", "-ac", "2",
                 "-i", "pipe:0", "-af", "no_such_filter=1", "-f", "null", "-"],
                data,
                48000,
                failure_message="FFmpeg loudness measurement failed:",
                tail=4000,
            )
        self.assertIn("FFmpeg loudness measurement failed", str(ctx.exception))

    def test_a_timeout_is_reported_without_hanging(self):
        # Pipe backpressure lets a real encoder do most of its work before
        # run_ffmpeg_with_pcm reaches wait(timeout=...). Increasing the track
        # length therefore still races CPU speed. This child drains stdin,
        # then stays alive, exercising the real timeout/kill/reap path reliably.
        data = signal(seconds=0.01)
        child = "import sys, time; sys.stdin.buffer.read(); time.sleep(30)"
        with self.assertRaises(RuntimeError) as ctx:
            ffmpeg_utils.run_ffmpeg_with_pcm(
                [sys.executable, "-c", child],
                data,
                48000,
                timeout=0.05,
                failure_message="FFmpeg loudness measurement failed:",
            )
        self.assertIn("timed out", str(ctx.exception))


class MeasurementParityTests(unittest.TestCase):
    """The pipe path and the file path must measure the same signal the same."""

    def setUp(self):
        if not FFMPEG_AVAILABLE:  # pragma: no cover - depends on the machine
            self.skipTest("FFmpeg is not available")
        self.data = signal(seconds=1.5, channels=2)

    def measure_with_pipe(self):
        return release_prep._measure_bs1770(self.data, 48000)

    def measure_with_file_only(self):
        """Force the fallback by making the pipe helper unavailable."""
        original = release_prep.__dict__.get("_IMPORT_GUARD")
        import builtins

        real_import = builtins.__import__

        def guard(name, *args, **kwargs):
            if name.endswith("ffmpeg_utils") and kwargs.get("fromlist") and "run_ffmpeg_with_pcm" in (
                kwargs.get("fromlist") or ()
            ):
                raise ImportError("forced fallback for the test")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = guard
        try:
            return release_prep._measure_bs1770(self.data, 48000)
        finally:
            builtins.__import__ = real_import

    def test_both_transports_measure_the_same_numbers(self):
        piped = self.measure_with_pipe()
        filed = self.measure_with_file_only()
        for key in ("integrated_lufs", "true_peak_dbtp", "lra_lu", "threshold_lufs"):
            with self.subTest(metric=key):
                self.assertTrue(np.isfinite(piped[key]), f"{key} must be finite via the pipe")
                self.assertAlmostEqual(piped[key], filed[key], places=3, msg=f"{key} differs between transports")

    def test_the_pipe_path_needs_no_temporary_file(self):
        import tempfile

        original = tempfile.NamedTemporaryFile

        def refuse(*args, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("the pipe path must not create a temporary file")

        tempfile.NamedTemporaryFile = refuse
        try:
            metrics = release_prep._measure_bs1770(self.data, 48000)
        finally:
            tempfile.NamedTemporaryFile = original
        self.assertTrue(np.isfinite(metrics["integrated_lufs"]))

    def test_the_fallback_still_cleans_up_its_temporary_file(self):
        import glob
        import os
        import tempfile

        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.wav")))
        self.measure_with_file_only()
        after = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.wav")))
        self.assertEqual(after - before, set(), "the fallback must remove its temporary WAV")

    def test_a_mono_signal_is_measured_too(self):
        mono = signal(seconds=1.0, channels=1)
        metrics = release_prep._measure_bs1770(mono, 48000)
        self.assertTrue(np.isfinite(metrics["integrated_lufs"]))
        self.assertGreater(metrics["true_peak_dbtp"], -100.0)

    def test_the_input_array_is_not_modified(self):
        before = self.data.copy()
        self.measure_with_pipe()
        np.testing.assert_array_equal(self.data, before)


if __name__ == "__main__":
    unittest.main()
