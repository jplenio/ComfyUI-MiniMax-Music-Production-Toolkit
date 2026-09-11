"""Streaming overlap-add tests (F09 / T25).

The refactor must not change a single sample.  The strongest available check is
a differential one: the streaming accumulator and the retained-list stitch are
driven with the *same* deterministic predictions and compared bit-exactly.
"""
from __future__ import annotations

import importlib
import unittest

import numpy as np

import _toolkit_bootstrap

_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
flashsr = importlib.import_module(f"{_PACKAGE.__name__}.flashsr_audio")


def _predictions(spans, channels=2, seed=0):
    rng = np.random.default_rng(seed)
    window = flashsr.CHUNK_SAMPLES
    out = []
    for index, (start, length) in enumerate(spans):
        padded = max(length, window)
        out.append((rng.standard_normal((channels, padded)).astype(np.float32), start, length))
    return out


class AccumulatorParityTests(unittest.TestCase):
    def test_streaming_matches_the_list_stitch_bit_exactly(self):
        for hop in (flashsr.CHUNK_SAMPLES // 2, flashsr.CHUNK_SAMPLES - 1, flashsr.CHUNK_SAMPLES):
            for total in (1, flashsr.CHUNK_SAMPLES, flashsr.CHUNK_SAMPLES + 1, flashsr.CHUNK_SAMPLES * 3 + 37):
                with self.subTest(hop=hop, total=total):
                    spans = flashsr._iter_chunks(total, flashsr.CHUNK_SAMPLES, hop)
                    predictions = _predictions(spans, seed=total + hop)

                    expected = flashsr._wola_stitch(predictions, total, flashsr.CHUNK_SAMPLES)

                    window_full = np.hanning(flashsr.CHUNK_SAMPLES).astype(np.float32)
                    acc = np.zeros((predictions[0][0].shape[0], total), np.float32)
                    weight_sum = np.zeros(total, np.float32)
                    for pred, start, valid_len in predictions:
                        flashsr._ola_accumulate(
                            acc, weight_sum, pred, start, valid_len, flashsr.CHUNK_SAMPLES, window_full
                        )
                    actual = flashsr._finalize_ola(acc, weight_sum)

                    np.testing.assert_array_equal(actual, expected)

    def test_empty_prediction_list(self):
        result = flashsr._wola_stitch([], total_len=0, window=flashsr.CHUNK_SAMPLES)
        self.assertEqual(result.shape, (1, 1))
        self.assertEqual(result.dtype, np.float32)

    def test_single_chunk_is_its_own_prediction(self):
        spans = flashsr._iter_chunks(flashsr.CHUNK_SAMPLES // 2, flashsr.CHUNK_SAMPLES, flashsr.CHUNK_SAMPLES // 2)
        predictions = _predictions(spans, seed=5)
        stitched = flashsr._wola_stitch(predictions, flashsr.CHUNK_SAMPLES // 2, flashsr.CHUNK_SAMPLES)
        self.assertEqual(stitched.shape, (2, flashsr.CHUNK_SAMPLES // 2))

    def test_spans_are_the_single_source_of_chunking(self):
        spans = flashsr._iter_chunks(flashsr.CHUNK_SAMPLES * 2, flashsr.CHUNK_SAMPLES, flashsr.CHUNK_SAMPLES // 2)
        # Contiguous, non-overlapping start order, last span clamped to the end.
        self.assertEqual(spans[0][0], 0)
        for (start, length), (next_start, _next_length) in zip(spans, spans[1:]):
            self.assertLess(start, next_start)
        self.assertEqual(spans[-1][0] + spans[-1][1], flashsr.CHUNK_SAMPLES * 2)


class UpscaleStreamingTests(unittest.TestCase):
    """End-to-end: the node must produce the samples the old path produced."""

    class FakeRunner:
        def __init__(self, channels=2):
            self.channels = channels
            self.calls = 0

        def __call__(self, x, lowpass_input=False):
            import torch
            self.calls += 1
            # Deterministic, order-independent transform of the input.
            return x * 0.5 + 1.0

    def _run(self, total_samples, hop_factor=0.5):
        import torch

        runner = self.FakeRunner()
        saved_runner = flashsr._get_runner
        saved_weights = flashsr._ensure_flashsr_weights
        flashsr._get_runner = lambda _dir: {"model": runner, "device": "cpu"}
        flashsr._ensure_flashsr_weights = lambda _auto: flashsr.VENDOR_ROOT
        try:
            audio = {
                "waveform": torch.zeros((1, 2, total_samples), dtype=torch.float32),
                "sample_rate": flashsr.REQ_SR,
            }
            # Deterministic content so both paths see identical input.
            rng = np.random.default_rng(total_samples)
            audio["waveform"][0] = torch.from_numpy(rng.standard_normal((2, total_samples)).astype(np.float32))
            out, settings = flashsr.MiniMaxFlashSRAudio().upscale(
                audio=audio, lowpass_input=False, output_sr=str(flashsr.REQ_SR), auto_download=False
            )
        finally:
            flashsr._get_runner = saved_runner
            flashsr._ensure_flashsr_weights = saved_weights
        return out, settings, runner, audio["waveform"]

    def test_streamed_output_matches_the_reference_stitch(self):
        import torch

        total = flashsr.CHUNK_SAMPLES + 1234
        out, _settings, runner, source = self._run(total)
        self.assertEqual(runner.calls, len(flashsr._iter_chunks(total, flashsr.CHUNK_SAMPLES, int((flashsr.CHUNK_S - flashsr.OVERLAP_S) * flashsr.REQ_SR))))

        waveform = out["waveform"]
        self.assertEqual(out["sample_rate"], flashsr.REQ_SR)
        self.assertEqual(tuple(waveform.shape), (1, 2, total))

        # Rebuild the expected result with the historical list-then-stitch path,
        # feeding the model exactly the same padded chunks the node fed it.
        hop = int((flashsr.CHUNK_S - flashsr.OVERLAP_S) * flashsr.REQ_SR)
        spans = flashsr._iter_chunks(total, flashsr.CHUNK_SAMPLES, hop)
        source_np = source.numpy()[0]
        predictions = []
        for start, length in spans:
            chunk = source_np[:, start:start + length]
            if length < flashsr.CHUNK_SAMPLES:
                chunk = np.concatenate(
                    [chunk, np.zeros((2, flashsr.CHUNK_SAMPLES - length), np.float32)], axis=1
                )
            predicted = (torch.from_numpy(np.ascontiguousarray(chunk)) * 0.5 + 1.0).numpy()
            predictions.append((predicted, start, length))
        expected = flashsr._wola_stitch(predictions, total, flashsr.CHUNK_SAMPLES)
        np.testing.assert_array_equal(waveform.numpy()[0], expected)

    def test_settings_report_unchanged_contract(self):
        import json

        out, settings, _runner, _source = self._run(flashsr.CHUNK_SAMPLES)
        payload = json.loads(settings)
        self.assertEqual(payload["schema"], "flashsr_settings_v1")
        self.assertEqual(payload["inference_sr"], flashsr.REQ_SR)
        self.assertEqual(payload["chunk_s"], flashsr.CHUNK_S)
        self.assertEqual(payload["overlap_s"], flashsr.OVERLAP_S)
        self.assertFalse(payload["lowpass_input"])
        self.assertEqual(payload["device"], "cpu")

    def test_inference_failure_includes_the_captured_tail(self):
        class Boom:
            def __call__(self, x, lowpass_input=False):
                print("vendor noise", file=__import__("sys").stderr)
                raise RuntimeError("kernel exploded")

        saved_runner = flashsr._get_runner
        saved_weights = flashsr._ensure_flashsr_weights
        flashsr._get_runner = lambda _dir: {"model": Boom(), "device": "cpu"}
        flashsr._ensure_flashsr_weights = lambda _auto: flashsr.VENDOR_ROOT
        try:
            import torch

            audio = {
                "waveform": torch.zeros((1, 1, flashsr.CHUNK_SAMPLES), dtype=torch.float32),
                "sample_rate": flashsr.REQ_SR,
            }
            with self.assertRaises(RuntimeError) as ctx:
                flashsr.MiniMaxFlashSRAudio().upscale(
                    audio=audio, lowpass_input=False, output_sr=str(flashsr.REQ_SR), auto_download=False
                )
        finally:
            flashsr._get_runner = saved_runner
            flashsr._ensure_flashsr_weights = saved_weights
        self.assertIn("chunk 1/1", str(ctx.exception))
        self.assertIn("kernel exploded", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
