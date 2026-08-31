from __future__ import annotations

from .toolkit_logging import get_logger

LOGGER = get_logger("audio_hf_repair")

import json
import math
from fractions import Fraction
from typing import Any, Dict, Tuple

import numpy as np
import torch

try:
    from scipy.signal import butter, firwin, kaiserord, lfilter, oaconvolve, resample_poly, sosfiltfilt
except Exception as exc:
    butter = firwin = kaiserord = lfilter = oaconvolve = resample_poly = sosfiltfilt = None
    _SCIPY_ERR = exc
else:
    _SCIPY_ERR = None


def _validate_audio(audio: Any, label: str = "audio") -> Tuple[torch.Tensor, int]:
    if not isinstance(audio, dict) or "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError(f"{label}: expected ComfyUI AUDIO with waveform and sample_rate.")
    waveform = audio["waveform"]
    sr = int(audio["sample_rate"])
    if not isinstance(waveform, torch.Tensor) or waveform.ndim != 3:
        raise ValueError(f"{label}: waveform must be torch.Tensor [B,C,T].")
    return waveform, sr


def _require_scipy():
    if resample_poly is None:
        raise RuntimeError(f"HF Audio Repair requires scipy. Import error: {_SCIPY_ERR}")


def _resample_hq(x_bct: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    _require_scipy()
    if sr_in == sr_out:
        return np.asarray(x_bct, dtype=np.float32)
    frac = Fraction(sr_out, sr_in).limit_denominator(10000)
    y = resample_poly(x_bct, frac.numerator, frac.denominator, axis=-1, window=("kaiser", 14.769656459379492))
    return np.asarray(y, dtype=np.float32)


def _match_length(x: np.ndarray, n: int) -> np.ndarray:
    if x.shape[-1] == n:
        return x
    if x.shape[-1] > n:
        return x[..., :n]
    y = np.zeros((*x.shape[:-1], n), dtype=x.dtype)
    y[..., :x.shape[-1]] = x
    return y


def _fir_lowpass(x: np.ndarray, sr: int, cutoff_hz: float, transition_hz: float, attenuation_db: float = 90.0) -> Tuple[np.ndarray, int]:
    _require_scipy()
    nyq = sr * 0.5
    cutoff_hz = float(np.clip(cutoff_hz, 100.0, nyq * 0.96))
    transition_hz = float(np.clip(transition_hz, 200.0, nyq * 0.35))
    width = min(0.99, transition_hz / nyq)
    taps, beta = kaiserord(float(attenuation_db), width)
    taps = int(max(257, min(8191, taps)))
    if taps % 2 == 0:
        taps += 1
    h = firwin(taps, cutoff_hz, fs=sr, window=("kaiser", beta), pass_zero="lowpass")
    y = np.empty_like(x, dtype=np.float32)
    for b in range(x.shape[0]):
        for c in range(x.shape[1]):
            y[b, c] = oaconvolve(x[b, c], h, mode="same").astype(np.float32, copy=False)
    return y, taps


def _db_to_gain(db: float) -> float:
    return float(10.0 ** (float(db) / 20.0))


class FlashSRHybridCrossover:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_audio": ("AUDIO",),
                "flashsr_audio": ("AUDIO",),
                "mode": ([
                    "Original + FlashSR air",
                    "Hybrid replace above crossover",
                    "Original SRC only",
                    "FlashSR only",
                ], {"default": "Original + FlashSR air"}),
                "crossover_hz": ("FLOAT", {"default": 14500.0, "min": 7000.0, "max": 18000.0, "step": 100.0}),
                "transition_hz": ("FLOAT", {"default": 2000.0, "min": 300.0, "max": 6000.0, "step": 100.0}),
                "flashsr_hf_mix": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.5, "step": 0.05}),
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "hybrid_crossover_json", "info")
    FUNCTION = "process"
    CATEGORY = "MiniMax Music Production Toolkit/audio restoration"

    def process(self, original_audio, flashsr_audio, mode, crossover_hz, transition_hz, flashsr_hf_mix):
        ow, osr = _validate_audio(original_audio, "FlashSR Hybrid original_audio")
        fw, fsr = _validate_audio(flashsr_audio, "FlashSR Hybrid flashsr_audio")
        o = ow.detach().to("cpu", torch.float32).numpy()
        f = fw.detach().to("cpu", torch.float32).numpy()
        if o.shape[0] != f.shape[0] or o.shape[1] != f.shape[1]:
            raise ValueError(f"FlashSR Hybrid: batch/channels differ: original={o.shape[:2]}, FlashSR={f.shape[:2]}")

        o48 = _resample_hq(o, osr, fsr)
        o48 = _match_length(o48, f.shape[-1])
        mix = float(flashsr_hf_mix)
        taps = 0

        if mode == "Original SRC only":
            y = o48
        elif mode == "FlashSR only":
            y = f
        else:
            low_o, taps = _fir_lowpass(o48, fsr, crossover_hz, transition_hz)
            low_f, _ = _fir_lowpass(f, fsr, crossover_hz, transition_hz)
            high_f = f - low_f
            if mode == "Hybrid replace above crossover":
                y = low_o + np.float32(mix) * high_f
            else:  # Original + FlashSR air
                # Preserve all real source information after clean SRC and add only a restrained
                # high-passed FlashSR contribution. This intentionally avoids replacing the source
                # cymbal/transient band with reconstructed audio.
                y = o48 + np.float32(mix) * high_f

        y = np.asarray(y, dtype=np.float32)
        report = {
            "schema": "flashsr_hybrid_crossover_v1",
            "mode": mode,
            "original_sample_rate": int(osr),
            "flashsr_sample_rate": int(fsr),
            "output_sample_rate": int(fsr),
            "original_resampler": "scipy.signal.resample_poly Kaiser beta=14.77",
            "crossover_hz": float(crossover_hz),
            "transition_hz": float(transition_hz),
            "flashsr_hf_mix": mix,
            "crossover_filter": "linear-phase Kaiser FIR / overlap-add convolution",
            "fir_taps": int(taps),
            "hidden_peak_normalization": False,
        }
        info = f"{mode} | original {osr}->{fsr} Hz | crossover {crossover_hz:.0f} Hz | FlashSR HF mix {mix:.2f}"
        LOGGER.info("%s", info)
        return ({"waveform": torch.from_numpy(np.ascontiguousarray(y)), "sample_rate": fsr}, json.dumps(report, ensure_ascii=False, indent=2), info)


def _preset_repair(mode: str, start_hz: float, sustain_db: float, fast_ms: float, slow_ms: float,
                   sensitivity: float, side_db: float, hf_trim_db: float, min_hf_dbfs: float, mix: float):
    if mode == "Gentle":
        return 8000.0, 1.25, 8.0, 180.0, 0.35, 0.75, -0.4, -58.0, 1.0
    if mode == "Cymbal clarity":
        return 7000.0, 2.25, 5.0, 180.0, 0.30, 1.0, -0.5, -58.0, 1.0
    if mode == "Reverb / shimmer control":
        return 7000.0, 3.25, 8.0, 260.0, 0.38, 1.75, -0.9, -60.0, 1.0
    return float(start_hz), float(sustain_db), float(fast_ms), float(slow_ms), float(sensitivity), float(side_db), float(hf_trim_db), float(min_hf_dbfs), float(mix)


def _ema_envelope(x: np.ndarray, sr: int, time_ms: float) -> np.ndarray:
    # Exponential envelope using scipy lfilter. x is [T].
    t = max(float(time_ms), 0.5) / 1000.0
    a = math.exp(-1.0 / max(sr * t, 1.0))
    return lfilter([1.0 - a], [1.0, -a], x).astype(np.float32, copy=False)


def _highpass_zero_phase(x_bct: np.ndarray, sr: int, start_hz: float) -> np.ndarray:
    _require_scipy()
    nyq = sr * 0.5
    start_hz = float(np.clip(start_hz, 500.0, nyq * 0.92))
    sos = butter(4, start_hz, btype="highpass", fs=sr, output="sos")
    y = np.empty_like(x_bct, dtype=np.float32)
    for b in range(x_bct.shape[0]):
        for c in range(x_bct.shape[1]):
            y[b, c] = sosfiltfilt(sos, x_bct[b, c]).astype(np.float32, copy=False)
    return y


class HFCymbalShimmerRepair:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "mode": (["Gentle", "Cymbal clarity", "Reverb / shimmer control", "Custom", "Bypass"], {"default": "Gentle"}),
                "start_frequency_hz": ("FLOAT", {"default": 8000.0, "min": 3000.0, "max": 16000.0, "step": 100.0}),
                "sustain_reduction_db": ("FLOAT", {"default": 1.25, "min": 0.0, "max": 8.0, "step": 0.1}),
                "fast_envelope_ms": ("FLOAT", {"default": 8.0, "min": 1.0, "max": 50.0, "step": 1.0}),
                "slow_envelope_ms": ("FLOAT", {"default": 180.0, "min": 40.0, "max": 1000.0, "step": 10.0}),
                "transient_sensitivity": ("FLOAT", {"default": 0.35, "min": 0.05, "max": 1.5, "step": 0.05}),
                "side_hf_reduction_db": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 8.0, "step": 0.1}),
                "static_hf_trim_db": ("FLOAT", {"default": -0.4, "min": -8.0, "max": 2.0, "step": 0.1}),
                "min_hf_level_dbfs": ("FLOAT", {"default": -58.0, "min": -90.0, "max": -20.0, "step": 1.0}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05}),
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "hf_repair_json", "info")
    FUNCTION = "process"
    CATEGORY = "MiniMax Music Production Toolkit/audio restoration"

    def process(self, audio, mode, start_frequency_hz, sustain_reduction_db, fast_envelope_ms, slow_envelope_ms,
                transient_sensitivity, side_hf_reduction_db, static_hf_trim_db, min_hf_level_dbfs, mix):
        waveform, sr = _validate_audio(audio, "HF Cymbal / Shimmer Repair")
        if mode == "Bypass":
            rep = {"schema": "hf_cymbal_shimmer_repair_v1", "enabled": False, "mode": "Bypass", "sample_rate": sr}
            return (audio, json.dumps(rep, ensure_ascii=False, indent=2), f"Bypass | {sr} Hz")

        vals = _preset_repair(mode, start_frequency_hz, sustain_reduction_db, fast_envelope_ms, slow_envelope_ms,
                              transient_sensitivity, side_hf_reduction_db, static_hf_trim_db, min_hf_level_dbfs, mix)
        start_hz, sustain_db, fast_ms, slow_ms, sens, side_db, trim_db, floor_db, wet = vals
        x = waveform.detach().to("cpu", torch.float32).numpy()
        hf = _highpass_zero_phase(x, sr, start_hz)
        low = x - hf
        y = np.empty_like(x, dtype=np.float32)
        batch_stats = []
        static_gain = _db_to_gain(trim_db)

        for b in range(x.shape[0]):
            # One shared envelope for all channels avoids stereo image movement.
            mono_energy = np.sqrt(np.mean(np.square(hf[b], dtype=np.float64), axis=0) + 1e-18).astype(np.float32)
            fast = _ema_envelope(mono_energy, sr, fast_ms)
            slow = _ema_envelope(mono_energy, sr, slow_ms)
            ratio = fast / (slow + 1e-9)
            transient_score = np.clip((ratio - 1.0) / max(sens, 1e-6), 0.0, 1.0)
            active = slow > _db_to_gain(floor_db)
            reduction_db = -float(sustain_db) * (1.0 - transient_score)
            reduction_db = np.where(active, reduction_db, 0.0)
            gain = np.power(10.0, reduction_db / 20.0, dtype=np.float32) * np.float32(static_gain)
            proc = low[b] + hf[b] * gain[None, :]

            # Static M/S high-frequency narrowing. This is intentionally not envelope-driven,
            # so it cannot create broadband pumping or image wandering.
            if proc.shape[0] == 2 and side_db > 0.0:
                L, R = proc[0], proc[1]
                mid = 0.5 * (L + R)
                side = 0.5 * (L - R)
                side_bct = side[None, None, :]
                side_hf = _highpass_zero_phase(side_bct, sr, start_hz)[0, 0]
                side = side - side_hf + side_hf * np.float32(_db_to_gain(-side_db))
                proc = np.stack((mid + side, mid - side), axis=0).astype(np.float32)

            y[b] = x[b] * np.float32(1.0 - wet) + proc * np.float32(wet)
            batch_stats.append({
                "mean_hf_reduction_db": float(np.mean(reduction_db[active])) if np.any(active) else 0.0,
                "max_hf_reduction_db": float(np.min(reduction_db)) if reduction_db.size else 0.0,
                "active_fraction": float(np.mean(active)) if active.size else 0.0,
            })

        report = {
            "schema": "hf_cymbal_shimmer_repair_v1",
            "enabled": True,
            "mode": mode,
            "sample_rate": int(sr),
            "start_frequency_hz": float(start_hz),
            "sustain_reduction_db": float(sustain_db),
            "fast_envelope_ms": float(fast_ms),
            "slow_envelope_ms": float(slow_ms),
            "transient_sensitivity": float(sens),
            "side_hf_reduction_db": float(side_db),
            "static_hf_trim_db": float(trim_db),
            "min_hf_level_dbfs": float(floor_db),
            "mix": float(wet),
            "processing_note": "Only the high-frequency band is dynamically shaped; low/mid-band gain is untouched. Shared channel envelope prevents stereo pumping.",
            "batch_stats": batch_stats,
        }
        info = f"{mode} | HF>{start_hz:.0f} Hz | sustain max -{sustain_db:.2f} dB | side -{side_db:.2f} dB | trim {trim_db:+.2f} dB"
        LOGGER.info("%s", info)
        return ({"waveform": torch.from_numpy(np.ascontiguousarray(y)), "sample_rate": sr}, json.dumps(report, ensure_ascii=False, indent=2), info)


NODE_CLASS_MAPPINGS = {
    "FlashSRHybridCrossover": FlashSRHybridCrossover,
    "HFCymbalShimmerRepair": HFCymbalShimmerRepair,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FlashSRHybridCrossover": "FlashSR Hybrid Crossover – Preserve Original / Blend Air",
    "HFCymbalShimmerRepair": "HF Cymbal / Shimmer Repair",
}
