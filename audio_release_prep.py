from __future__ import annotations

from .toolkit_logging import get_logger

LOGGER = get_logger("audio_release_prep")

import json
import math
import os
import shutil
import subprocess
import tempfile
from fractions import Fraction
from typing import Any, Dict, Tuple

import numpy as np
try:
    import torch  # type: ignore
except ImportError:  # torch ships with ComfyUI; absent only in bare CI/test environments
    torch = None  # type: ignore[assignment]

try:
    import soundfile as sf
except Exception as exc:
    sf = None
    _SF_ERR = exc
else:
    _SF_ERR = None

try:
    from scipy.signal import resample_poly
except Exception as exc:
    resample_poly = None
    _SCIPY_ERR = exc
else:
    _SCIPY_ERR = None


def _validate_audio(audio: Any) -> Tuple[torch.Tensor, int]:
    if not isinstance(audio, dict) or "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError("Audio Release Prep: expected ComfyUI AUDIO with waveform and sample_rate.")
    waveform = audio["waveform"]
    sr = int(audio["sample_rate"])
    if not isinstance(waveform, torch.Tensor) or waveform.ndim != 3:
        raise ValueError("Audio Release Prep: waveform must be torch.Tensor [B,C,T].")
    return waveform, sr


def _find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    raise RuntimeError("Audio Release Prep: FFmpeg not found. Run install_requirements.bat.")


def _run(cmd):
    kwargs = {}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)
    if p.returncode != 0:
        raise RuntimeError("Audio Release Prep: FFmpeg failed:\n" + p.stderr[-5000:])
    return p


def _resample_hq(x_bct: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return np.asarray(x_bct, dtype=np.float32)
    if resample_poly is None:
        raise RuntimeError(f"Audio Release Prep: scipy required for HQ resampling. Import error: {_SCIPY_ERR}")
    frac = Fraction(sr_out, sr_in).limit_denominator(10000)
    y = resample_poly(x_bct, frac.numerator, frac.denominator, axis=-1, window=("kaiser", 14.769656459379492))
    return np.asarray(y, dtype=np.float32)


def _extract_loudnorm_json(stderr: str) -> Dict[str, str]:
    start = stderr.rfind('{\n\t"input_i"')
    if start < 0:
        start = stderr.rfind('{\r\n\t"input_i"')
    if start < 0:
        key = stderr.rfind('"input_i"')
        if key >= 0:
            start = stderr.rfind('{', 0, key)
    if start < 0:
        raise RuntimeError("Audio Release Prep: could not parse FFmpeg loudnorm analysis output.")
    end = stderr.find('}', start)
    if end < 0:
        raise RuntimeError("Audio Release Prep: incomplete FFmpeg loudnorm JSON output.")
    return json.loads(stderr[start:end+1])


def _safe_float(value, default=float("nan")):
    try:
        return float(value)
    except Exception:
        return default


def _preset_values(preset: str, custom_lufs: float, custom_tp: float):
    if preset == "Streaming Safe -14 LUFS / -1 dBTP":
        return -14.0, -1.0
    if preset == "Modern Music -12 LUFS / -2 dBTP":
        return -12.0, -2.0
    if preset == "Loud Electronic -10 LUFS / -2 dBTP":
        return -10.0, -2.0
    if preset == "Custom":
        return float(custom_lufs), float(custom_tp)
    return None, None


def _measure_bs1770(data_tc: np.ndarray, sr: int) -> Dict[str, float]:
    if sf is None:
        raise RuntimeError(f"Audio Release Prep requires soundfile. Import error: {_SF_ERR}")
    ffmpeg = _find_ffmpeg()
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        sf.write(path, data_tc, sr, format="WAV", subtype="FLOAT")
        # We use loudnorm ONLY as an ITU-R BS.1770 / true-peak meter here. No processed audio
        # from this filter is used. This prevents loudnorm from silently falling back to its
        # dynamic mode and changing the song's internal dynamics.
        filt = "loudnorm=I=-23:TP=-1:LRA=11:print_format=json"
        p = _run([ffmpeg, "-hide_banner", "-nostdin", "-i", path, "-af", filt, "-f", "null", "-"])
        m = _extract_loudnorm_json(p.stderr)
        return {
            "integrated_lufs": _safe_float(m.get("input_i")),
            "true_peak_dbtp": _safe_float(m.get("input_tp")),
            "lra_lu": _safe_float(m.get("input_lra")),
            "threshold_lufs": _safe_float(m.get("input_thresh")),
        }
    finally:
        if path:
            try: os.remove(path)
            except OSError: pass


def _static_gain_for_targets(measured_i: float, measured_tp: float, target_i: float, target_tp: float):
    if not math.isfinite(measured_i) or not math.isfinite(measured_tp):
        return 0.0, 0.0, False
    requested = float(target_i - measured_i)
    tp_headroom = float(target_tp - measured_tp)
    # A single constant gain is used for the complete programme. If the requested LUFS gain
    # would violate the true-peak ceiling, we stop at the TP-safe gain instead of compressing
    # or dynamically riding the level.
    applied = min(requested, tp_headroom)
    limited_by_tp = applied < requested - 1e-7
    return requested, applied, limited_by_tp


class AudioReleasePrep:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "target_sample_rate": (["44100", "48000", "keep"], {"default": "44100"}),
                "processing": ([
                    "Resample only",
                    "Streaming Safe -14 LUFS / -1 dBTP",
                    "Modern Music -12 LUFS / -2 dBTP",
                    "Loud Electronic -10 LUFS / -2 dBTP",
                    "Custom",
                    "Bypass",
                ], {"default": "Resample only"}),
                "custom_target_lufs": ("FLOAT", {"default": -14.0, "min": -24.0, "max": -5.0, "step": 0.1}),
                "custom_true_peak_dbtp": ("FLOAT", {"default": -1.0, "min": -6.0, "max": -0.1, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "release_prep_json", "info")
    FUNCTION = "process"
    CATEGORY = "MiniMax Music Production Toolkit/mastering"

    def process(self, audio, target_sample_rate, processing, custom_target_lufs, custom_true_peak_dbtp):
        waveform, sr_in = _validate_audio(audio)
        if processing == "Bypass":
            report = {"schema": "audio_release_prep_v2", "enabled": False, "input_sample_rate": sr_in, "output_sample_rate": sr_in, "processing": "Bypass"}
            return (audio, json.dumps(report, ensure_ascii=False, indent=2), f"Bypass | {sr_in} Hz")

        sr_out = sr_in if target_sample_rate == "keep" else int(target_sample_rate)
        x = waveform.detach().to(device="cpu", dtype=torch.float32).numpy()
        # SRC is always performed first. Loudness and true peak are measured at the actual final sample rate.
        y = _resample_hq(x, sr_in, sr_out)
        reports = []
        target_lufs, target_tp = _preset_values(processing, custom_target_lufs, custom_true_peak_dbtp)

        if target_lufs is None:
            peak_in = float(np.max(np.abs(x))) if x.size else 0.0
            peak_out = float(np.max(np.abs(y))) if y.size else 0.0
            reports.append({"peak_input_linear": peak_in, "peak_output_linear": peak_out})
            gain_strategy = "none"
        else:
            gain_strategy = "static_full_program_gain_tp_capped"
            for b in range(y.shape[0]):
                data_tc = np.ascontiguousarray(y[b].T, dtype=np.float32)
                before = _measure_bs1770(data_tc, sr_out)
                requested_db, applied_db, tp_limited = _static_gain_for_targets(
                    before["integrated_lufs"], before["true_peak_dbtp"], target_lufs, target_tp
                )
                gain = np.float32(10.0 ** (applied_db / 20.0))
                y[b] *= gain
                after = _measure_bs1770(np.ascontiguousarray(y[b].T, dtype=np.float32), sr_out)
                shortfall = max(0.0, float(target_lufs - after["integrated_lufs"])) if math.isfinite(after["integrated_lufs"]) else float("nan")
                reports.append({
                    "input_integrated_lufs": before["integrated_lufs"],
                    "input_true_peak_dbtp": before["true_peak_dbtp"],
                    "input_lra_lu": before["lra_lu"],
                    "target_lufs": float(target_lufs),
                    "target_true_peak_dbtp": float(target_tp),
                    "requested_gain_db": float(requested_db),
                    "applied_constant_gain_db": float(applied_db),
                    "gain_limited_by_true_peak": bool(tp_limited),
                    "output_integrated_lufs": after["integrated_lufs"],
                    "output_true_peak_dbtp": after["true_peak_dbtp"],
                    "output_lra_lu": after["lra_lu"],
                    "lufs_target_shortfall_lu": float(shortfall),
                    "target_lufs_reached": bool(math.isfinite(shortfall) and shortfall <= 0.25),
                    "normalization_type": "static full-program gain; no compressor, no AGC, no dynamic loudnorm",
                })

        out = {"waveform": torch.from_numpy(np.ascontiguousarray(y)).to(dtype=torch.float32), "sample_rate": sr_out}
        report = {
            "schema": "audio_release_prep_v2",
            "enabled": True,
            "processing": processing,
            "input_sample_rate": int(sr_in),
            "output_sample_rate": int(sr_out),
            "resampler": "scipy.signal.resample_poly Kaiser beta=14.77",
            "loudness_meter": None if target_lufs is None else "ITU-R BS.1770 / EBU R128 input metrics via FFmpeg loudnorm meter",
            "gain_strategy": gain_strategy,
            "time_varying_gain": False,
            "dynamic_range_processing": False,
            "target_lufs": target_lufs,
            "target_true_peak_dbtp": target_tp,
            "batch_reports": reports,
        }
        info = f"{processing} | {sr_in} -> {sr_out} Hz"
        if target_lufs is not None:
            info += f" | STATIC target {target_lufs:.1f} LUFS / {target_tp:.1f} dBTP"
            if any(r.get("gain_limited_by_true_peak") for r in reports):
                info += " | TP cap prevented full LUFS target on at least one item"
        LOGGER.info("%s", info)
        return (out, json.dumps(report, ensure_ascii=False, indent=2), info)


NODE_CLASS_MAPPINGS = {"AudioReleasePrep": AudioReleasePrep}
NODE_DISPLAY_NAME_MAPPINGS = {"AudioReleasePrep": "Audio Release Prep – Static LUFS / True Peak / SRC"}
