from __future__ import annotations

from .toolkit_logging import get_logger

LOGGER = get_logger("audio_declip")

import json
import math
from typing import Any, Dict, List, Tuple

import numpy as np
import torch


def _validate_audio(audio: Any, label: str = "audio") -> Tuple[torch.Tensor, int]:
    if not isinstance(audio, dict) or "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError(f"{label}: expected ComfyUI AUDIO with waveform and sample_rate.")
    waveform = audio["waveform"]
    sr = int(audio["sample_rate"])
    if not isinstance(waveform, torch.Tensor) or waveform.ndim != 3:
        raise ValueError(f"{label}: waveform must be torch.Tensor [B,C,T].")
    return waveform, sr


def _db_to_gain(db: float) -> float:
    return float(10.0 ** (float(db) / 20.0))


def _preset(mode: str, threshold_pct: float, plateau_tol_pct: float, min_flat_samples: int,
            context_samples: int, max_repair_ms: float, max_extension_db: float,
            ceiling_dbfs: float, mix: float):
    if mode == "Auto / conservative":
        return 98.0, 0.001, 3, 3, 8.0, 4.0, -1.0, 1.0
    if mode == "Standard":
        return 96.0, 0.010, 2, 4, 12.0, 6.0, -1.0, 1.0
    if mode == "Strong":
        return 93.0, 0.100, 1, 6, 20.0, 8.0, -1.0, 1.0
    return (float(threshold_pct), float(plateau_tol_pct), int(min_flat_samples),
            int(context_samples), float(max_repair_ms), float(max_extension_db),
            float(ceiling_dbfs), float(mix))


def _runs(mask: np.ndarray) -> List[Tuple[int, int]]:
    """Return inclusive [start,end] runs for a boolean mask."""
    if mask.size == 0 or not np.any(mask):
        return []
    v = mask.astype(np.int8, copy=False)
    d = np.diff(v, prepend=0, append=0)
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def _estimate_slope(x: np.ndarray, idx: int, context: int, side: str) -> float:
    n = x.size
    context = max(1, int(context))
    if side == "left":
        j = max(0, idx - context)
        h = idx - j
        if h <= 0:
            return 0.0
        return float((x[idx] - x[j]) / h)
    j = min(n - 1, idx + context)
    h = j - idx
    if h <= 0:
        return 0.0
    return float((x[j] - x[idx]) / h)


def _hermite_repair(x: np.ndarray, start: int, end: int, context: int,
                    clip_level_abs: float, sign: float, max_extension_db: float) -> np.ndarray:
    """Cubic-Hermite reconstruction between samples just outside a clipped run.

    The original samples are not mutated. Returned values correspond only to start..end.
    A gentle smooth peak bump is added only when the Hermite curve fails to rise above
    the detected clip ceiling. This avoids replacing a flat top with another flat/dipped top.
    """
    n = x.size
    i0 = start - 1
    i1 = end + 1
    if i0 < 0 or i1 >= n or i1 <= i0 + 1:
        return x[start:end + 1].copy()

    y0 = float(x[i0])
    y1 = float(x[i1])
    m0 = _estimate_slope(x, i0, context, "left")
    m1 = _estimate_slope(x, i1, context, "right")
    h = float(i1 - i0)
    js = np.arange(start, end + 1, dtype=np.float64)
    t = (js - float(i0)) / h

    t2 = t * t
    t3 = t2 * t
    h00 = 2.0 * t3 - 3.0 * t2 + 1.0
    h10 = t3 - 2.0 * t2 + t
    h01 = -2.0 * t3 + 3.0 * t2
    h11 = t3 - t2
    pred = h00 * y0 + h10 * (h * m0) + h01 * y1 + h11 * (h * m1)

    # Keep the repaired crest physically plausible. A hard-clipped positive crest should
    # remain positive (and vice versa), and it should normally rise above the clip ceiling.
    # Estimate the missing height from the entry/exit slopes, but cap it to a user-defined
    # maximum extension so one pathological region cannot create a huge reconstructed spike.
    abs_pred_peak = float(np.max(np.abs(pred))) if pred.size else 0.0
    max_allowed = float(clip_level_abs * _db_to_gain(max_extension_db))
    # Usually the Hermite slopes already create the missing arch. Only if they fail to
    # rise measurably above the detected clip ceiling do we add a very small smooth bump;
    # do not force a large speculative peak merely because the incoming slopes are steep.
    if abs_pred_peak <= clip_level_abs * 1.002:
        slope_extra = 0.10 * (abs(m0) + abs(m1)) * h
        modest_extra = min(clip_level_abs * 0.03, max(clip_level_abs * 0.008, slope_extra))
        desired = min(max_allowed, clip_level_abs + modest_extra)
        bump = np.sin(np.pi * t)
        pred = pred + float(sign) * max(0.0, desired - abs_pred_peak) * bump

    # Prevent sign inversions inside an obviously clipped same-sign crest. This is only a
    # safety clamp; normal Hermite reconstructions never hit it.
    pred = np.where(sign > 0.0, np.maximum(pred, 0.0), np.minimum(pred, 0.0))
    pred = np.clip(pred, -max_allowed, max_allowed)
    return pred.astype(np.float32)


def _repair_channel(x: np.ndarray, sr: int, threshold_pct: float, plateau_tol_pct: float,
                    min_flat_samples: int, context_samples: int, max_repair_ms: float,
                    max_extension_db: float, analyze_only: bool) -> Tuple[np.ndarray, Dict[str, Any]]:
    y = x.copy()
    mag = np.abs(x)
    peak = float(np.max(mag)) if mag.size else 0.0
    if peak <= 1e-12:
        return y, {
            "input_peak_linear": peak,
            "threshold_linear": 0.0,
            "candidate_regions": 0,
            "repaired_regions": 0,
            "skipped_long_regions": 0,
            "clipped_samples": 0,
            "near_peak_plateau_samples": 0,
            "max_candidate_run_ms": 0.0,
        }

    threshold = peak * float(threshold_pct) / 100.0
    flat_step_limit = peak * float(plateau_tol_pct) / 100.0
    above = mag >= threshold
    runs = _runs(above)
    max_samples = max(1, int(round(float(max_repair_ms) * sr / 1000.0)))

    repaired = 0
    skipped_long = 0
    clipped_samples = 0
    plateau_samples_total = 0
    candidate_count = 0
    max_run = 0

    for s, e in runs:
        # Split a threshold run if it crosses zero/sign; a real clipped crest is same-sign.
        seg = x[s:e + 1]
        signs = np.sign(seg)
        # zeros at high threshold are impossible except degenerate data; inherit neighbors.
        signs[signs == 0] = 1
        change = np.flatnonzero(signs[1:] != signs[:-1])
        sub_starts = [s] + [s + int(i) + 1 for i in change]
        sub_ends = [s + int(i) for i in change] + [e]

        for ss, ee in zip(sub_starts, sub_ends):
            run_len = ee - ss + 1
            max_run = max(max_run, run_len)
            sub_mag = mag[ss:ee + 1]
            sub_x = x[ss:ee + 1]
            if run_len <= 1:
                flat_samples = 1
            else:
                flat_edges = np.abs(np.diff(sub_x)) <= flat_step_limit
                longest_edges = 0
                current_edges = 0
                for is_flat in flat_edges:
                    if bool(is_flat):
                        current_edges += 1
                        longest_edges = max(longest_edges, current_edges)
                    else:
                        current_edges = 0
                flat_samples = longest_edges + 1 if longest_edges > 0 else 1
            plateau_samples_total += int(flat_samples)
            if flat_samples < int(min_flat_samples):
                continue
            candidate_count += 1
            clipped_samples += run_len
            if run_len > max_samples or ss <= context_samples or ee >= x.size - context_samples - 1:
                skipped_long += 1
                continue
            if analyze_only:
                continue
            sign = 1.0 if float(np.mean(x[ss:ee + 1])) >= 0.0 else -1.0
            repaired_vals = _hermite_repair(
                x, ss, ee, context_samples, clip_level_abs=float(np.max(sub_mag)),
                sign=sign, max_extension_db=max_extension_db,
            )
            y[ss:ee + 1] = repaired_vals
            repaired += 1

    return y, {
        "input_peak_linear": peak,
        "threshold_linear": float(threshold),
        "flat_step_limit_linear": float(flat_step_limit),
        "candidate_regions": int(candidate_count),
        "repaired_regions": int(repaired),
        "skipped_long_regions": int(skipped_long),
        "clipped_samples": int(clipped_samples),
        "near_peak_plateau_samples": int(plateau_samples_total),
        "max_candidate_run_ms": float(max_run * 1000.0 / sr),
    }


class AudioDeclipRepair:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "mode": (["Auto / conservative", "Standard", "Strong", "Custom", "Analyze only", "Bypass"], {"default": "Auto / conservative"}),
                "detection_threshold_percent": ("FLOAT", {"default": 98.0, "min": 85.0, "max": 99.99, "step": 0.1}),
                "plateau_tolerance_percent": ("FLOAT", {"default": 0.001, "min": 0.0001, "max": 1.0, "step": 0.001}),
                "min_flat_samples": ("INT", {"default": 3, "min": 1, "max": 32, "step": 1}),
                "slope_context_samples": ("INT", {"default": 3, "min": 2, "max": 64, "step": 1}),
                "max_repair_ms": ("FLOAT", {"default": 8.0, "min": 0.1, "max": 50.0, "step": 0.5}),
                "max_peak_extension_db": ("FLOAT", {"default": 4.0, "min": 0.5, "max": 12.0, "step": 0.5}),
                "output_ceiling_dbfs": ("FLOAT", {"default": -1.0, "min": -12.0, "max": -0.1, "step": 0.1}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05}),
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "declip_json", "info")
    FUNCTION = "process"
    CATEGORY = "MiniMax Music Production Toolkit/audio restoration"

    def process(self, audio, mode, detection_threshold_percent, plateau_tolerance_percent,
                min_flat_samples, slope_context_samples, max_repair_ms,
                max_peak_extension_db, output_ceiling_dbfs, mix):
        waveform, sr = _validate_audio(audio, "Audio Declip / Overload Repair")
        if mode == "Bypass":
            report = {
                "schema": "audio_declip_repair_v1",
                "enabled": False,
                "mode": "Bypass",
                "sample_rate": int(sr),
            }
            return (audio, json.dumps(report, ensure_ascii=False, indent=2), f"Bypass | {sr} Hz")

        threshold_pct, plateau_tol_pct, min_flat, context, max_ms, extension_db, ceiling_dbfs, wet = _preset(
            mode, detection_threshold_percent, plateau_tolerance_percent, min_flat_samples,
            slope_context_samples, max_repair_ms, max_peak_extension_db, output_ceiling_dbfs, mix,
        )
        analyze_only = mode == "Analyze only"
        x = waveform.detach().to("cpu", torch.float32).numpy()
        y = x.copy()
        channel_reports: List[Dict[str, Any]] = []

        for b in range(x.shape[0]):
            batch_channels = []
            for c in range(x.shape[1]):
                repaired, stats = _repair_channel(
                    x[b, c], sr, threshold_pct, plateau_tol_pct, min_flat, context,
                    max_ms, extension_db, analyze_only,
                )
                if not analyze_only:
                    y[b, c] = x[b, c] * np.float32(1.0 - wet) + repaired * np.float32(wet)
                stats["batch_index"] = int(b)
                stats["channel_index"] = int(c)
                batch_channels.append(stats)
                channel_reports.append(stats)

        total_candidates = int(sum(r["candidate_regions"] for r in channel_reports))
        total_repaired = int(sum(r["repaired_regions"] for r in channel_reports))
        total_skipped = int(sum(r["skipped_long_regions"] for r in channel_reports))
        total_samples = int(sum(r["clipped_samples"] for r in channel_reports))

        applied_gain_db = 0.0
        output_peak_before_gain = float(np.max(np.abs(y))) if y.size else 0.0
        if not analyze_only and total_repaired > 0:
            ceiling = _db_to_gain(ceiling_dbfs)
            if output_peak_before_gain > ceiling and output_peak_before_gain > 0.0:
                gain = ceiling / output_peak_before_gain
                y *= np.float32(gain)
                applied_gain_db = float(20.0 * math.log10(max(gain, 1e-20)))

        output_peak = float(np.max(np.abs(y))) if y.size else 0.0
        duration_samples = max(1, int(np.prod(x.shape)))
        clipped_fraction = float(total_samples / duration_samples)
        if total_candidates == 0:
            severity = "none detected"
        elif clipped_fraction < 0.0001:
            severity = "light"
        elif clipped_fraction < 0.002:
            severity = "moderate"
        else:
            severity = "heavy"

        report = {
            "schema": "audio_declip_repair_v1",
            "enabled": True,
            "mode": mode,
            "sample_rate": int(sr),
            "algorithm": "near-ceiling plateau detection + cubic-Hermite peak reconstruction with slope context",
            "detection_threshold_percent": float(threshold_pct),
            "plateau_tolerance_percent": float(plateau_tol_pct),
            "min_flat_samples": int(min_flat),
            "slope_context_samples": int(context),
            "max_repair_ms": float(max_ms),
            "max_peak_extension_db": float(extension_db),
            "output_ceiling_dbfs": float(ceiling_dbfs),
            "mix": float(wet),
            "analyze_only": bool(analyze_only),
            "candidate_regions": total_candidates,
            "repaired_regions": total_repaired,
            "skipped_long_regions": total_skipped,
            "candidate_samples": total_samples,
            "candidate_fraction_of_all_channel_samples": clipped_fraction,
            "severity_estimate": severity,
            "output_peak_before_safety_gain_linear": output_peak_before_gain,
            "applied_constant_safety_gain_db": applied_gain_db,
            "output_peak_linear": output_peak,
            "time_varying_gain": False,
            "channel_reports": channel_reports,
            "limitations": "True hard-clipping removes information permanently. This node reconstructs plausible peak shape; it cannot recover the exact original waveform. Soft-clipping/limiter distortion without near-ceiling plateaus may not be detected.",
        }
        info = (
            f"{mode} | {severity} | candidates {total_candidates} | repaired {total_repaired} | "
            f"skipped {total_skipped} | safety gain {applied_gain_db:+.2f} dB"
        )
        LOGGER.info("%s", info)
        out = {"waveform": torch.from_numpy(np.ascontiguousarray(y)).to(torch.float32), "sample_rate": sr}
        return (out, json.dumps(report, ensure_ascii=False, indent=2), info)


NODE_CLASS_MAPPINGS = {"AudioDeclipRepair": AudioDeclipRepair}
NODE_DISPLAY_NAME_MAPPINGS = {"AudioDeclipRepair": "Audio Declip / Overload Repair"}
