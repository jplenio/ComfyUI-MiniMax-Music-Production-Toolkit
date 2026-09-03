"""Integrated Audio Super Resolution (FlashSR) node.

Replaces the external ``ComfyUI-Egregora-Audio-Super-Resolution`` custom node
with a self-contained toolkit node.  The processing behavior (48 kHz inference,
5.12 s chunks, 0.50 s overlap, Hann windowed overlap-add stitching, optional
post-resample) is kept identical so existing chains sound the same.

The FlashSR *inference code* is bundled with this package in
:file:`flashsr_inference/` (vendored from the upstream FlashSR_Inference and
TorchJaekwon repositories; see ``flashsr_inference/NOTICE.md``).  Only the
model *weights* are fetched on first use from the ``jakeoneijk/FlashSR_weights``
Hugging Face dataset into ``models/audio/flashsr`` (per :file:`models_config.json`,
with progress logging, then the run continues).  Auto-download can be disabled
per node.

No external custom nodes and no runtime code downloads are involved.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .model_downloader import (
    check_file_entries,
    load_models_config,
    resolve_target,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("flashsr")

REQ_SR = 48000
CHUNK_S = 5.12
OVERLAP_S = 0.50
CHUNK_SAMPLES = int(REQ_SR * CHUNK_S)  # 245760

# Vendored inference code bundled with this package (see flashsr_inference/NOTICE.md).
VENDOR_ROOT = Path(__file__).resolve().parent / "flashsr_inference"


def _resample_hq(x_cs: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Resample [C, S] float32 along the sample axis, best quality available."""
    if src_sr == dst_sr:
        return x_cs.astype(np.float32)
    try:
        import soxr  # type: ignore
        out = [soxr.resample(x_cs[c], src_sr, dst_sr) for c in range(x_cs.shape[0])]
        length = min(len(channel) for channel in out)
        return np.stack([channel[:length] for channel in out], axis=0).astype(np.float32)
    except Exception:
        pass
    try:
        from scipy.signal import resample_poly  # type: ignore
        g = math.gcd(int(src_sr), int(dst_sr))
        up, down = int(dst_sr) // g, int(src_sr) // g
        out = [resample_poly(x_cs[c], up=up, down=down).astype(np.float32) for c in range(x_cs.shape[0])]
        length = min(len(channel) for channel in out)
        return np.stack([channel[:length] for channel in out], axis=0)
    except Exception:
        pass
    ratio = dst_sr / float(src_sr)
    n_out = int(round(x_cs.shape[1] * ratio))
    t_in = np.linspace(0.0, 1.0, x_cs.shape[1], endpoint=False, dtype=np.float64)
    t_out = np.linspace(0.0, 1.0, n_out, endpoint=False, dtype=np.float64)
    return np.stack([np.interp(t_out, t_in, channel) for channel in x_cs], axis=0).astype(np.float32)


def _to_channel_samples(audio: Any) -> Tuple[np.ndarray, int]:
    """Normalize a ComfyUI AUDIO dict or (array, sr) tuple to [C, S] float32."""
    if isinstance(audio, dict) and "waveform" in audio and "sample_rate" in audio:
        waveform = audio["waveform"]
        sr = int(audio["sample_rate"])
        if waveform.dim() == 3:
            waveform = waveform[0]
        if waveform.dim() != 2:
            raise RuntimeError(f"Unexpected AUDIO tensor shape {tuple(waveform.shape)}; expected [C, T].")
        return waveform.detach().cpu().float().numpy(), sr
    if isinstance(audio, (list, tuple)) and len(audio) == 2:
        array, sr = audio
        array = np.asarray(array, dtype=np.float32)
        if array.ndim == 1:
            return array[None, :], int(sr)
        if array.ndim == 2:
            if array.shape[0] >= array.shape[1] and array.shape[1] <= 8:
                return array.T.astype(np.float32), int(sr)
            return array.astype(np.float32), int(sr)
    raise RuntimeError("MiniMax FlashSR: no valid AUDIO provided.")


def _make_audio(sr: int, samples_cs: np.ndarray) -> Dict[str, Any]:
    import torch
    samples = np.asarray(samples_cs, dtype=np.float32)
    if samples.ndim == 1:
        samples = samples[None, :]
    return {"waveform": torch.from_numpy(samples).unsqueeze(0).contiguous(), "sample_rate": int(sr)}


def _iter_chunks(total_samples: int, window: int, hop: int) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    index = 0
    while index < total_samples:
        length = min(window, total_samples - index)
        spans.append((index, length))
        if index + length >= total_samples:
            break
        index += hop
    return spans


def _wola_stitch(predictions: List[Tuple[np.ndarray, int, int]], total_len: int, window: int) -> np.ndarray:
    if not predictions:
        return np.zeros((1, max(1, total_len)), np.float32)
    channels = predictions[0][0].shape[0]
    acc = np.zeros((channels, total_len), np.float32)
    weight_sum = np.zeros(total_len, np.float32)
    window_full = np.hanning(window).astype(np.float32)
    for pred, start, valid_len in predictions:
        pred_len = pred.shape[1]
        length = min(valid_len, pred_len)
        weight = window_full[:length] if length <= window else np.ones(length, np.float32)
        acc[:, start:start + length] += pred[:, :length] * weight[None, :]
        weight_sum[start:start + length] += weight
    weight_sum[weight_sum == 0] = 1.0
    return (acc / weight_sum[None, :]).astype(np.float32)


def _ensure_flashsr_weights(auto_download: bool) -> Path:
    """Check/download the FlashSR weights; return the weights directory.

    The inference code is bundled in ``flashsr_inference/`` and needs no
    download.  Only the three weight files (student_ldm.pth, sr_vocoder.pth,
    vae.pth) are fetched from the configured Hugging Face dataset on first use.
    """
    config = load_models_config().get("flashsr", {})
    weights_section = config.get("weights", {})
    weights_target = weights_section.get("target", "models/audio/flashsr")
    weights_entries = [
        {**entry, "target": entry.get("target") or weights_target}
        for entry in weights_section.get("files", [])
    ]

    report = check_file_entries(weights_entries, base_path=None, auto_download=auto_download)
    failed = [item for item in report if item["status"] == "failed"]
    if failed:
        raise RuntimeError("FlashSR weights could not be prepared: " + "; ".join(f"{i['name']} ({i['message']})" for i in failed))
    if auto_download:
        for item in report:
            if item["status"] in {"downloaded", "missing"}:
                LOGGER.info("FlashSR model file: %s -> %s", item["status"], item["target"])
        missing = [item for item in report if item["status"] == "missing"]
        if missing:
            raise RuntimeError(
                "FlashSR weights are missing and auto-download is disabled. "
                "Required: " + ", ".join(i["name"] for i in missing)
            )
    return resolve_target(weights_target)


_runner_cache: Dict[str, Any] = {}
_vendor_path_added = False


def _ensure_vendor_on_path() -> Path:
    """Make the bundled ``flashsr_inference/`` code importable (idempotent).

    Only the vendor root is added - never the inner ``FlashSR`` folder itself.
    Adding the inner folder makes ``FlashSR/FlashSR.py`` shadow the ``FlashSR``
    package, which breaks the upstream code's ``FlashSR.AudioSR`` imports with
    "'FlashSR' is not a package".
    """
    global _vendor_path_added
    if not VENDOR_ROOT.is_dir():
        raise RuntimeError(
            f"Bundled FlashSR inference code missing at {VENDOR_ROOT}. "
            "Reinstall the toolkit package so flashsr_inference/ is present."
        )
    if not _vendor_path_added:
        sys.path.insert(0, str(VENDOR_ROOT))
        _vendor_path_added = True
    return VENDOR_ROOT


def _import_flashsr_model():
    """Import the vendored FlashSR class quietly.

    The upstream code prints helper noise ("There is no Hparams", deprecation
    warnings) on import; the toolkit keeps its own log clean and only surfaces
    real import failures.
    """
    import contextlib
    import io

    _ensure_vendor_on_path()
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from FlashSR.FlashSR import FlashSR  # type: ignore  # vendored code
        return FlashSR
    except Exception as exc:
        raise RuntimeError(
            "Could not import the bundled FlashSR inference code "
            f"(flashsr_inference/). Details: {type(exc).__name__}: {exc}"
        ) from exc


def _get_runner(weights_dir: Path) -> Any:
    """Return a cached FlashSR runner for the given weights location."""
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    key = f"{weights_dir}|{device}"
    cached = _runner_cache.get(key)
    if cached is not None:
        return cached

    FlashSR = _import_flashsr_model()

    student = weights_dir / "student_ldm.pth"
    vocoder = weights_dir / "sr_vocoder.pth"
    vae = weights_dir / "vae.pth"
    for path in (student, vocoder, vae):
        if not path.is_file():
            raise RuntimeError(f"FlashSR weight missing: {path}")

    LOGGER.info("Loading FlashSR model (%s, %s)", device, student.name)
    model = FlashSR(str(student), str(vocoder), str(vae))
    model.eval()
    try:
        model.to(device)
    except Exception:
        LOGGER.warning("Could not move FlashSR model to %s; continuing on CPU", device)

    runner = {"model": model, "device": device}
    _runner_cache[key] = runner
    return runner


def clear_flashsr_cache() -> int:
    """Free all cached FlashSR runners; returns how many were released."""
    count = len(_runner_cache)
    _runner_cache.clear()
    if count:
        LOGGER.info("Released %d cached FlashSR model instance(s)", count)
    return count


class MiniMaxFlashSRAudio:
    """Audio Super Resolution (FlashSR) – integrated replacement for the external Egregora node."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "lowpass_input": ("BOOLEAN", {"default": False}),
                "output_sr": (["48000", "44100", "96000"], {"default": "48000"}),
                "auto_download": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "settings_json")
    FUNCTION = "upscale"
    CATEGORY = "MiniMax Music Production Toolkit/audio"

    def upscale(self, audio=None, lowpass_input=False, output_sr="48000", auto_download=True):
        import torch

        in_cs, in_sr = _to_channel_samples(audio)
        weights_dir = _ensure_flashsr_weights(bool(auto_download))

        if in_sr != REQ_SR:
            LOGGER.info("Resampling input to FlashSR rate: %d Hz -> %d Hz", in_sr, REQ_SR)
            in_cs = _resample_hq(in_cs, in_sr, REQ_SR)

        runner = _get_runner(weights_dir)
        model = runner["model"]
        device = runner["device"]

        window = CHUNK_SAMPLES
        hop = int((CHUNK_S - OVERLAP_S) * REQ_SR)
        if hop <= 0 or hop >= window:
            hop = window // 2

        total = in_cs.shape[1]
        predictions: List[Tuple[np.ndarray, int, int]] = []
        for start, length in _iter_chunks(total, window, hop):
            chunk = in_cs[:, start:start + length]
            if length < window:
                chunk = np.concatenate([chunk, np.zeros((in_cs.shape[0], window - length), np.float32)], axis=1)
            x = torch.from_numpy(chunk).to(device).float()
            # The vendored diffusion wrapper prints a tqdm progress bar per
            # chunk; the toolkit logs its own per-chunk progress instead.
            with torch.inference_mode(), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                y = model(x, lowpass_input=bool(lowpass_input))
            predictions.append((y.detach().to("cpu").float().numpy(), start, length))
            LOGGER.debug("FlashSR chunk %d/%d done", len(predictions), len(_iter_chunks(total, window, hop)))

        out_48k = _wola_stitch(predictions, total_len=total, window=window)

        target_sr = int(output_sr)
        if target_sr != REQ_SR:
            out = _resample_hq(out_48k, REQ_SR, target_sr)
        else:
            out = out_48k

        LOGGER.info("FlashSR upscale finished: %d Hz -> %d Hz, %d samples", in_sr, target_sr, out.shape[1])
        settings_json = json.dumps({
            "schema": "flashsr_settings_v1",
            "inference_sr": REQ_SR,
            "chunk_s": CHUNK_S,
            "overlap_s": OVERLAP_S,
            "lowpass_input": bool(lowpass_input),
            "output_sr": target_sr,
            "device": runner["device"],
        }, ensure_ascii=False, indent=2)
        return (_make_audio(target_sr, out), settings_json)


NODE_CLASS_MAPPINGS = {
    "MiniMaxFlashSRAudio": MiniMaxFlashSRAudio,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxFlashSRAudio": "Audio Super Resolution (FlashSR, integrated)",
}
