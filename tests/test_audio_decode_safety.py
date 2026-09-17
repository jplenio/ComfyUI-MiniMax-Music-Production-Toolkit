"""Numerical failures must stop before publication, without altering good audio."""
from __future__ import annotations

import importlib
import json
import tempfile
import unittest
import weakref
from pathlib import Path
from unittest import mock

import numpy as np
import torch

import _toolkit_bootstrap

PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
decode = importlib.import_module(f"{PACKAGE.__name__}.audio_decode")
audio_utils = importlib.import_module(f"{PACKAGE.__name__}.audio_utils")
smart = importlib.import_module(f"{PACKAGE.__name__}.save_audio_smart_prefix")
absolute = importlib.import_module(f"{PACKAGE.__name__}.save_audio_absolute")


def latent_input():
    return {"samples": torch.ones(1, 128, 8)}


def raw_audio():
    # BTC, with a meaningful std*5 divisor and a second, quiet batch element.
    loud = torch.linspace(-1.2, 1.3, 514).reshape(1, 257, 2)
    return torch.cat([loud, loud * 0.01])


def fake_vae(raw=None):
    return mock.Mock(audio_sample_rate=32000, audio_sample_rate_output=48000,
                     decode=mock.Mock(return_value=raw),
                     decode_tiled=mock.Mock(return_value=raw))


class CheckedDecodeTests(unittest.TestCase):
    def test_valid_decode_matches_host_gain_shape_and_rate_without_mutation(self):
        for tiled in (False, True):
            with self.subTest(tiled=tiled):
                raw = raw_audio()
                before = raw.clone()
                samples = latent_input()
                original_latents = samples["samples"].clone()
                vae = fake_vae(raw)
                result, = decode.MiniMaxSafeAudioDecode().decode(samples, vae, 1536, 64, tiled)
                expected = before.movedim(-1, 1)
                scale = torch.std(expected, dim=[1, 2], keepdim=True) * 5
                scale[scale < 1] = 1
                expected = expected / scale
                torch.testing.assert_close(result["waveform"], expected, rtol=0, atol=0)
                torch.testing.assert_close(raw, before, rtol=0, atol=0)
                torch.testing.assert_close(samples["samples"], original_latents, rtol=0, atol=0)
                self.assertEqual(result["sample_rate"], 48000)
                if tiled:
                    vae.decode_tiled.assert_called_once_with(samples["samples"], tile_x=1536, tile_y=1536, overlap=64)
                    vae.decode.assert_not_called()
                else:
                    vae.decode.assert_called_once_with(samples["samples"])
                    vae.decode_tiled.assert_not_called()

    def test_explicit_and_legacy_sample_rates(self):
        for vae_rate, explicit, expected in ((32000, 44100, 44100), (32000, None, 32000), (None, None, 44100)):
            with self.subTest(vae_rate=vae_rate, explicit=explicit):
                vae = type("VAE", (), {"decode": lambda self, samples: raw_audio()})()
                if vae_rate is not None:
                    vae.audio_sample_rate = vae_rate
                samples = latent_input()
                if explicit is not None:
                    samples["sample_rate"] = explicit
                result, = decode.MiniMaxSafeAudioDecode().decode(samples, vae, tiled=False)
                self.assertEqual(result["sample_rate"], expected)

    def test_nan_or_infinity_latents_never_reach_vae(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            samples = latent_input()
            samples["samples"][0, -1, -1] = value
            vae = fake_vae(raw_audio())
            with self.subTest(value=value), self.assertRaisesRegex(audio_utils.NonFiniteAudioError, "Music sampler latents.*Rerun music sampling"):
                decode.MiniMaxSafeAudioDecode().decode(samples, vae)
            vae.decode.assert_not_called()
            vae.decode_tiled.assert_not_called()

    def test_invalid_decode_gets_one_tiled_retry_with_same_latents(self):
        for tiled in (True, False):
            for value in (float("nan"), float("inf")):
                with self.subTest(tiled=tiled, value=value):
                    samples = latent_input()
                    vae = fake_vae()
                    bad = torch.full((1, 257, 2), value)
                    if tiled:
                        vae.decode_tiled.side_effect = [bad, raw_audio()]
                    else:
                        vae.decode.return_value = bad
                        vae.decode_tiled.return_value = raw_audio()
                    with self.assertLogs(decode.LOGGER, level="WARNING") as logs:
                        result, = decode.MiniMaxSafeAudioDecode().decode(samples, vae, 1536, 64, tiled)
                    self.assertTrue(torch.isfinite(result["waveform"]).all())
                    self.assertGreater(result["waveform"].abs().max().item(), 0.1)
                    self.assertIn("sampling is not repeated", logs.output[0])
                    self.assertEqual(vae.decode.call_count + vae.decode_tiled.call_count, 2)
                    vae.decode_tiled.assert_called_with(samples["samples"], tile_x=512, tile_y=512, overlap=32)
                    for call in vae.decode_tiled.call_args_list:
                        self.assertIs(call.args[0], samples["samples"])

    def test_failed_audio_buffer_is_released_before_retry(self):
        references = []

        def attempt(*args, **kwargs):
            if not references:
                failed = torch.full((1, 257, 2), float("nan"))
                references.append(weakref.ref(failed))
                return failed
            self.assertIsNone(references[0](), "failed audio retained across retry")
            return raw_audio()

        vae = fake_vae()
        vae.decode_tiled.side_effect = attempt
        with self.assertLogs(decode.LOGGER, level="WARNING"):
            decode.MiniMaxSafeAudioDecode().decode(latent_input(), vae)

    def test_retry_is_bounded_and_never_replaces_bad_output_with_silence(self):
        vae = fake_vae(torch.full((1, 257, 2), float("nan")))
        with self.assertLogs(decode.LOGGER, level="WARNING"), self.assertRaisesRegex(
                audio_utils.NonFiniteAudioError, "retry also failed.*incoming latents were finite"):
            decode.MiniMaxSafeAudioDecode().decode(latent_input(), vae, 256, 32)
        self.assertEqual(vae.decode_tiled.call_count, 2)
        self.assertEqual(vae.decode_tiled.call_args.kwargs, {"tile_x": 128, "tile_y": 128, "overlap": 32})

    def test_non_finite_normalization_is_detected(self):
        huge = torch.tensor([-3e38, 3e38]).reshape(1, 2, 1)
        vae = fake_vae()
        vae.decode_tiled.side_effect = [huge, raw_audio()]
        with self.assertLogs(decode.LOGGER, level="WARNING") as logs:
            output, = decode.MiniMaxSafeAudioDecode().decode(latent_input(), vae)
        self.assertIn("normalization", logs.output[0])
        self.assertTrue(torch.isfinite(output["waveform"]).all())

    def test_other_exceptions_and_cancellation_propagate_without_retry(self):
        for failure in (RuntimeError("decoder backend failed"), KeyboardInterrupt()):
            vae = fake_vae()
            vae.decode.side_effect = failure
            with self.subTest(error=type(failure).__name__), self.assertRaises(type(failure)):
                decode.MiniMaxSafeAudioDecode().decode(latent_input(), vae, tiled=False)
            vae.decode.assert_called_once()
            vae.decode_tiled.assert_not_called()

    def test_invalid_inputs_stop_before_decode(self):
        cases = [({}, {}), ({"samples": torch.zeros(1, 2)}, {}),
                 ({"samples": torch.zeros(1, 128, 0)}, {}),
                 (latent_input(), {"tile_size": 16}),
                 (latent_input(), {"tile_size": 64, "overlap": 64}),
                 ({**latent_input(), "sample_rate": 0}, {})]
        for samples, options in cases:
            vae = fake_vae()
            with self.subTest(options=options), self.assertRaises(ValueError):
                decode.MiniMaxSafeAudioDecode().decode(samples, vae, **options)
            vae.decode.assert_not_called()
            vae.decode_tiled.assert_not_called()

    def test_both_decoder_alternatives_are_checked(self):
        """Both models decode through the safe tiled node, with the right tile size.

        The decoders are created by the generation expansion rather than stored in
        the workflow file, so the contract is checked on the expanded graph.
        """
        package, _host = _toolkit_bootstrap.load_entry_point()
        for model, tile_size, tiled in (("MiniMax Music 3", 1536, True), ("YuE2", 1920, True)):
            profile = package.NODE_CLASS_MAPPINGS["MusicProductionControl"]().build(model)[0]
            settings_node = package.NODE_CLASS_MAPPINGS["MiniMaxMusicModelSettings"]()
            spec = settings_node.INPUT_TYPES()["required"]
            args = {name: options[1]["default"] for name, options in spec.items()
                    if "default" in options[1]}
            settings = settings_node.build(**args, generation_seed=7, profile_json=profile)[-1]
            import sys
            import types
            from test_yue2 import Graph
            module = types.ModuleType("comfy_execution.graph_utils")
            module.GraphBuilder = Graph
            from unittest.mock import patch as _patch
            with _patch.dict(sys.modules, {"comfy_execution.graph_utils": module}):
                expanded = package.NODE_CLASS_MAPPINGS["MusicGeneration"]().generate(
                    profile, settings, "style", "lyrics", "yue2.safetensors",
                    "dit", "clip", "vae")["expand"]
            decoders = [node for node in expanded.values() if node["class_type"] == "MiniMaxSafeAudioDecode"]
            self.assertEqual(len(decoders), 1, model)
            self.assertEqual(decoders[0]["inputs"]["tile_size"], tile_size, model)
            self.assertEqual(decoders[0]["inputs"]["tiled"], tiled, model)


class AudioExportSafetyTests(unittest.TestCase):
    def save(self, kind, folder, audio, fmt="flac", depth="24-bit", peak="leave_unchanged"):
        common = dict(audio=audio, format=fmt, collision_mode="overwrite", create_directories=True,
                      mp3_quality="V0 (~245 kbps)", flac_bit_depth=depth, wav_bit_depth=depth, peak_handling=peak)
        if kind == "smart":
            return smart.SaveAudioSmartPrefix().save(
                filename_prefix=str(Path(folder) / "track"), filename_mode="prefix as provided",
                write_json_sidecar=True, metadata_json='{"title":"test"}', embed_basic_metadata=False, **common)
        return absolute.SaveAudioAbsolutePath().save(absolute_directory=folder, filename="track", **common)

    def test_all_samples_and_batches_checked_before_any_encode_or_sidecar(self):
        for kind, module in (("smart", smart), ("absolute", absolute)):
            for fmt in ("flac", "wav", "mp3"):
                for value in (float("nan"), float("inf"), -float("inf")):
                    with self.subTest(kind=kind, fmt=fmt, value=value), tempfile.TemporaryDirectory() as tmp:
                        waveform = torch.zeros(2, 2, 270000)
                        waveform[-1, -1, -1] = value  # after the first batch and validation block
                        before = waveform.clone()
                        with mock.patch.object(module.sf, "write") as encoder, mock.patch.object(module, "_write_mp3") as mp3:
                            with self.assertRaisesRegex(audio_utils.NonFiniteAudioError, "NaN or Infinity.*No audio file was written"):
                                self.save(kind, tmp, {"waveform": waveform, "sample_rate": 32000}, fmt, peak="normalize_only_if_clipping")
                            encoder.assert_not_called()
                            mp3.assert_not_called()
                        self.assertEqual(list(Path(tmp).iterdir()), [])
                        torch.testing.assert_close(waveform, before, rtol=0, atol=0, equal_nan=True)

    def test_empty_batches_channels_or_frames_are_rejected(self):
        for kind in ("smart", "absolute"):
            for shape in ((0, 2, 100), (1, 0, 100), (1, 2, 0)):
                with self.subTest(kind=kind, shape=shape), tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaisesRegex(ValueError, "empty"):
                        self.save(kind, tmp, {"waveform": torch.zeros(shape), "sample_rate": 32000})
                    self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_real_flac_and_wav_roundtrips_preserve_signal_and_metadata(self):
        for kind in ("smart", "absolute"):
            for fmt, depth, tolerance in (("flac", "16-bit", 2**-15), ("flac", "24-bit", 2**-23),
                                          ("wav", "16-bit", 2**-15), ("wav", "24-bit", 2**-23),
                                          ("wav", "32-bit float", 0)):
                with self.subTest(kind=kind, fmt=fmt, depth=depth), tempfile.TemporaryDirectory() as tmp:
                    waveform = torch.linspace(-0.8, 0.7, 2000).reshape(1, 2, 1000)
                    audio = {"waveform": waveform, "sample_rate": 32000}
                    result = self.save(kind, tmp, audio, fmt, depth)
                    saved = result[1] if kind == "smart" else result[0]
                    data, rate = smart.sf.read(saved, dtype="float32", always_2d=True)
                    self.assertEqual(rate, 32000)
                    self.assertEqual(data.shape, (1000, 2))
                    np.testing.assert_allclose(data, waveform[0].numpy().T, atol=tolerance, rtol=0)
                    if kind == "smart":
                        self.assertIs(result[0], audio)
                        self.assertEqual(json.loads(result[3])["applied_gain"], 1.0)
                        self.assertEqual(json.loads(Path(result[2]).read_text(encoding="utf-8"))["title"], "test")

    def test_peak_policy_still_normalizes_only_when_requested(self):
        for kind in ("smart", "absolute"):
            for peak in ("leave_unchanged", "normalize_only_if_clipping"):
                with self.subTest(kind=kind, peak=peak), tempfile.TemporaryDirectory() as tmp:
                    waveform = torch.tensor([[[-1.5, 0.0, 1.5]]])
                    before = waveform.clone()
                    result = self.save(kind, tmp, {"waveform": waveform, "sample_rate": 44100},
                                       "wav", "32-bit float", peak)
                    data, _ = smart.sf.read(result[1] if kind == "smart" else result[0], dtype="float32", always_2d=True)
                    expected, _, _ = smart._prepare(before[0].numpy(), peak)
                    np.testing.assert_array_equal(data, expected.T)
                    torch.testing.assert_close(waveform, before, rtol=0, atol=0)

    def test_short_codec_write_is_explained_and_never_overwrites_existing_file(self):
        def short_write(path, *args, **kwargs):
            Path(path).write_bytes(b"incomplete encode")
            raise AssertionError()

        for kind, module in (("smart", smart), ("absolute", absolute)):
            for existing in (False, True):
                with self.subTest(kind=kind, existing=existing), tempfile.TemporaryDirectory() as tmp:
                    target = Path(tmp) / "track.flac"
                    if existing:
                        target.write_bytes(b"previous release")
                    with mock.patch.object(module.sf, "write", side_effect=short_write):
                        with self.assertRaisesRegex(RuntimeError, "FLAC/PCM_24 encoder wrote fewer samples.*libsndfile="):
                            self.save(kind, tmp, {"waveform": torch.zeros(1, 2, 500), "sample_rate": 32000})
                    self.assertEqual(list(Path(tmp).iterdir()), [target] if existing else [])
                    if existing:
                        self.assertEqual(target.read_bytes(), b"previous release")


if __name__ == "__main__":
    unittest.main()
