"""FFmpeg helper tests (F15 / T12).

The important guarantee is *command parity*: moving the encode into a shared
helper must not change a single argument.  The two savers differ on purpose -
only the absolute saver strips pre-existing container metadata - so both command
lines are asserted exactly.
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PKG = "_ffmpeg_utils_test"
if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg

MODULES = {}
for _name in ("toolkit_logging", "filename_utils", "output_paths", "file_writes", "ffmpeg_utils",
              "save_audio_smart_prefix", "save_audio_absolute"):
    _full = f"{PKG}.{_name}"
    _spec = importlib.util.spec_from_file_location(_full, ROOT / f"{_name}.py")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_full] = _module
    assert _spec.loader is not None
    _spec.loader.exec_module(_module)
    MODULES[_name] = _module

ffmpeg_utils = MODULES["ffmpeg_utils"]
smart = MODULES["save_audio_smart_prefix"]
absolute = MODULES["save_audio_absolute"]


def _audio(frames=256, seed=3):
    rng = np.random.default_rng(seed)
    return np.ascontiguousarray((rng.standard_normal((frames, 2)) * 0.1).astype(np.float32))


class CommandCapture:
    """Replaces FFmpeg discovery and execution; records the argv."""

    def __init__(self, returncode=0, stderr="boom"):
        self.commands = []
        self.returncode = returncode
        self.stderr = stderr
        self.temp_files = []

    def __enter__(self):
        self._find = ffmpeg_utils.find_ffmpeg
        self._run = ffmpeg_utils.run_ffmpeg

        def fake_find(_message):
            return "ffmpeg-fake"

        def fake_run(cmd, *, failure_message, tail=None):
            self.commands.append(list(cmd))
            self.temp_files.append(cmd[cmd.index("-i") + 1])
            if self.returncode != 0:
                detail = self.stderr.strip() if tail is None else self.stderr[-tail:]
                raise RuntimeError(f"{failure_message}\n{detail}")
            return types.SimpleNamespace(returncode=0, stderr="")

        ffmpeg_utils.find_ffmpeg = fake_find
        ffmpeg_utils.run_ffmpeg = fake_run
        return self

    def __exit__(self, *exc):
        ffmpeg_utils.find_ffmpeg = self._find
        ffmpeg_utils.run_ffmpeg = self._run
        return False


class QualityMappingTests(unittest.TestCase):
    def test_known_labels(self):
        self.assertEqual(ffmpeg_utils.mp3_quality_args("V0 (~245 kbps)"), ["-q:a", "0"])
        self.assertEqual(ffmpeg_utils.mp3_quality_args("V2 (~190 kbps)"), ["-q:a", "2"])
        for kbps in ("192", "256", "320"):
            self.assertEqual(ffmpeg_utils.mp3_quality_args(f"{kbps} kbps"), ["-b:a", f"{kbps}k"])

    def test_unknown_label(self):
        self.assertEqual(ffmpeg_utils.mp3_quality_args("V9"), [])

    def test_invalid_quality_raises_the_callers_message(self):
        with self.assertRaises(ValueError) as ctx:
            smart._write_mp3("out.mp3", _audio(), 44100, "V9")
        self.assertIn("Save Audio Smart Prefix: invalid MP3 quality 'V9'.", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            absolute._write_mp3("out.mp3", _audio(), 44100, "V9")
        self.assertIn("Save Audio Absolute Path: unknown MP3 quality 'V9'.", str(ctx.exception))


class CommandParityTests(unittest.TestCase):
    def test_smart_saver_command(self):
        with CommandCapture() as capture:
            smart._write_mp3("target.mp3", _audio(), 44100, "V0 (~245 kbps)")
        self.assertEqual(len(capture.commands), 1)
        cmd = capture.commands[0]
        temp = capture.temp_files[0]
        self.assertEqual(cmd, [
            "ffmpeg-fake", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", temp, "-codec:a", "libmp3lame", "-q:a", "0",
            "-id3v2_version", "3", "target.mp3",
        ])
        self.assertNotIn("-map_metadata", cmd, "the smart saver writes its own ID3 tags")
        self.assertTrue(temp.endswith(".wav"))

    def test_absolute_saver_command_keeps_metadata_stripping(self):
        with CommandCapture() as capture:
            absolute._write_mp3("target.mp3", _audio(), 44100, "320 kbps")
        cmd = capture.commands[0]
        temp = capture.temp_files[0]
        self.assertEqual(cmd, [
            "ffmpeg-fake", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", temp, "-map_metadata", "-1", "-codec:a", "libmp3lame", "-b:a", "320k",
            "-id3v2_version", "3", "target.mp3",
        ])

    def test_temp_wav_is_removed_even_on_failure(self):
        with CommandCapture(returncode=1) as capture:
            with self.assertRaises(RuntimeError) as ctx:
                smart._write_mp3("target.mp3", _audio(), 44100, "V2 (~190 kbps)")
            self.assertIn("Save Audio Smart Prefix: FFmpeg failed:", str(ctx.exception))
            self.assertIn("boom", str(ctx.exception))
        from pathlib import Path as _Path
        self.assertFalse(_Path(capture.temp_files[0]).exists(), "the interchange WAV must be cleaned up")


class DiscoveryTests(unittest.TestCase):
    def test_prefers_path_then_imageio(self):
        module = types.ModuleType("imageio_ffmpeg")
        module.get_ffmpeg_exe = lambda: __file__  # any existing file
        saved_which = ffmpeg_utils.shutil.which
        had = sys.modules.get("imageio_ffmpeg")
        try:
            sys.modules["imageio_ffmpeg"] = module
            ffmpeg_utils.shutil.which = lambda _name: None
            self.assertEqual(ffmpeg_utils.discover_ffmpeg(), __file__)
            ffmpeg_utils.shutil.which = lambda _name: "C:/ffmpeg.exe"
            self.assertEqual(ffmpeg_utils.discover_ffmpeg(), "C:/ffmpeg.exe")
            ffmpeg_utils.shutil.which = lambda _name: None
            module.get_ffmpeg_exe = lambda: "C:/does/not/exist"
            self.assertIsNone(ffmpeg_utils.discover_ffmpeg())
        finally:
            ffmpeg_utils.shutil.which = saved_which
            if had is None:
                sys.modules.pop("imageio_ffmpeg", None)
            else:
                sys.modules["imageio_ffmpeg"] = had

    def test_find_raises_the_callers_message(self):
        saved = ffmpeg_utils.discover_ffmpeg
        try:
            ffmpeg_utils.discover_ffmpeg = lambda: None
            with self.assertRaises(RuntimeError) as ctx:
                ffmpeg_utils.find_ffmpeg("Smart: needs FFmpeg.")
            self.assertIn("Smart: needs FFmpeg.", str(ctx.exception))
        finally:
            ffmpeg_utils.discover_ffmpeg = saved


class PeakPolicyTests(unittest.TestCase):
    def test_below_full_scale_is_untouched(self):
        data = np.full((8, 2), 0.5, dtype=np.float32)
        out, peak, gain = ffmpeg_utils.prepare_samples(
            data, "normalize_only_if_clipping", unknown_peak_message="x {peak_handling}"
        )
        np.testing.assert_array_equal(out, data)
        self.assertAlmostEqual(peak, 0.5, places=6)
        self.assertEqual(gain, 1.0)

    def test_clipping_signal_is_attenuated(self):
        data = np.full((8, 2), 2.0, dtype=np.float32)
        out, peak, gain = ffmpeg_utils.prepare_samples(
            data, "normalize_only_if_clipping", unknown_peak_message="x {peak_handling}"
        )
        self.assertAlmostEqual(peak, 2.0, places=6)
        self.assertAlmostEqual(gain, 0.999 / 2.0, places=9)
        self.assertLessEqual(float(np.max(np.abs(out))), 1.0)

    def test_leave_unchanged_never_touches_samples(self):
        data = np.full((4, 1), 3.0, dtype=np.float32)
        out, _peak, gain = ffmpeg_utils.prepare_samples(
            data, "leave_unchanged", unknown_peak_message="x {peak_handling}"
        )
        self.assertEqual(gain, 1.0)
        np.testing.assert_array_equal(out, data)

    def test_unknown_policy_uses_the_callers_message(self):
        with self.assertRaises(ValueError) as ctx:
            smart._prepare(np.zeros((4, 1), dtype=np.float32), "nope")
        self.assertIn("Save Audio Smart Prefix: unknown peak_handling 'nope'.", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            absolute._prepare_samples(np.zeros((4, 1), dtype=np.float32), "nope")
        self.assertIn("Save Audio Absolute Path: unknown peak_handling 'nope'.", str(ctx.exception))

    def test_saver_wrappers_agree(self):
        data = np.full((8, 2), 1.5, dtype=np.float32)
        a = smart._prepare(data, "normalize_only_if_clipping")
        b = absolute._prepare_samples(data, "normalize_only_if_clipping")
        np.testing.assert_allclose(a[0], b[0])
        self.assertEqual(a[1], b[1])
        self.assertEqual(a[2], b[2])


class DiagnosticsDiscoveryTests(unittest.TestCase):
    def test_diagnostics_uses_runtime_discovery(self):
        spec = importlib.util.spec_from_file_location(
            "_diag_script", ROOT / "scripts" / "toolkit_diagnostics.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["_diag_script"] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        ok, message = module._check_ffmpeg()
        if ok:
            self.assertIn("ffmpeg", message.lower())
        else:
            self.assertIn("imageio-ffmpeg", message)


if __name__ == "__main__":
    unittest.main()
