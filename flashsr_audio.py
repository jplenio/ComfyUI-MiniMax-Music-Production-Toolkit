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
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .model_downloader import (
    check_file_entries,
    load_models_config,
    normalize_model_entries,
    resolve_target,
)
from .progress_utils import format_progress_bar, make_progress_bar
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


def _to_batch_channel_samples(audio: Any) -> Tuple[List[np.ndarray], int]:
    """All batch items of a ComfyUI AUDIO as a list of [C, S] float32 arrays.

    A01: the previous conversion silently reduced ``[B, C, T]`` to ``waveform[0]``,
    so a batch of two produced one result.  The batch dimension is preserved here
    and every item is processed by the caller.
    """
    if isinstance(audio, dict) and "waveform" in audio and "sample_rate" in audio:
        waveform = audio["waveform"]
        sr = int(audio["sample_rate"])
        if waveform.dim() == 2:
            waveform = waveform.unsqueeze(0)
        if waveform.dim() != 3:
            raise RuntimeError(
                f"Unexpected AUDIO tensor shape {tuple(waveform.shape)}; expected [B, C, T]."
            )
        return [item.detach().cpu().float().numpy() for item in waveform], sr
    if isinstance(audio, (list, tuple)) and len(audio) == 2:
        array, sr = audio
        array = np.asarray(array, dtype=np.float32)
        if array.ndim == 1:
            return [array[None, :]], int(sr)
        if array.ndim == 2:
            if array.shape[0] >= array.shape[1] and array.shape[1] <= 8:
                return [array.T.astype(np.float32)], int(sr)
            return [array.astype(np.float32)], int(sr)
        if array.ndim == 3:
            return [array[index].astype(np.float32) for index in range(array.shape[0])], int(sr)
    raise RuntimeError("MiniMax FlashSR: no valid AUDIO provided.")


def _to_channel_samples(audio: Any) -> Tuple[np.ndarray, int]:
    """Normalize a ComfyUI AUDIO dict or (array, sr) tuple to [C, S] float32.

    Legacy helper: for a batched input it returns **item 0 only**.  The node uses
    :func:`_to_batch_channel_samples` so no batch item is dropped.
    """
    items, sr = _to_batch_channel_samples(audio)
    return items[0], sr


def _make_audio(sr: int, samples_cs: np.ndarray) -> Dict[str, Any]:
    import torch
    samples = np.asarray(samples_cs, dtype=np.float32)
    if samples.ndim == 1:
        samples = samples[None, :]
    return {"waveform": torch.from_numpy(samples).unsqueeze(0).contiguous(), "sample_rate": int(sr)}


def _make_audio_batch(sr: int, items: List[np.ndarray]) -> Tuple[Dict[str, Any], bool]:
    """Stack per-item [C, S] results into one ``[B, C, S]`` AUDIO tensor.

    Items of different lengths are zero-padded to the longest one (a batch is a
    single tensor); the padding is reported instead of shortening the longer
    item.  Returns ``(audio, padded)``.
    """
    import torch

    if not items:
        raise RuntimeError("MiniMax FlashSR: no audio items to return.")
    channels = max(int(item.shape[0]) for item in items)
    length = max(int(item.shape[1]) for item in items)
    stacked = np.zeros((len(items), channels, length), np.float32)
    padded = False
    for index, item in enumerate(items):
        if item.shape != (channels, length):
            padded = True
        stacked[index, : item.shape[0], : item.shape[1]] = item
    return {"waveform": torch.from_numpy(stacked).contiguous(), "sample_rate": int(sr)}, padded


# The vendor's stochastic steps (``posterior.sample()`` plus diffusion noise) run
# under this lock when a seed is requested: a global ``torch.manual_seed`` would
# leak into other nodes, so the RNG state is saved and restored around the call.
_RNG_LOCK = threading.RLock()


def _processing_interrupted() -> bool:
    """ComfyUI's interrupt flag, when running inside ComfyUI."""
    try:
        import comfy.model_management as model_management  # type: ignore

        checker = getattr(model_management, "processing_interrupted", None)
        return bool(checker()) if callable(checker) else False
    except Exception:
        return False


def _interrupt_exception() -> BaseException:
    """ComfyUI's own interrupt exception when available."""
    try:
        import comfy.model_management as model_management  # type: ignore

        return model_management.InterruptProcessingException()
    except Exception:
        return RuntimeError("FlashSR generation cancelled by the user.")


@contextlib.contextmanager
def _deterministic_rng(seed: Optional[int]):
    """Deterministic RNG context for the vendor's stochastic steps.

    ``seed=None`` keeps the previous random semantics untouched.  With a seed the
    whole section is serialised by :data:`_RNG_LOCK` and the previous CPU/CUDA RNG
    state is restored afterwards, so the seed cannot leak into other nodes.
    """
    if seed is None:
        yield None
        return
    import torch

    with _RNG_LOCK:
        cpu_state = torch.get_rng_state()
        cuda_state = None
        try:
            if torch.cuda.is_available():
                cuda_state = torch.cuda.get_rng_state_all()
        except Exception:  # pragma: no cover - CPU-only or no CUDA runtime
            cuda_state = None
        try:
            torch.manual_seed(int(seed) & ((1 << 63) - 1))
            yield int(seed)
        finally:
            torch.set_rng_state(cpu_state)
            if cuda_state is not None:  # pragma: no cover - needs a GPU
                try:
                    torch.cuda.set_rng_state_all(cuda_state)
                except Exception:
                    pass


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


def _ola_accumulate(
    acc: np.ndarray,
    weight_sum: np.ndarray,
    pred: np.ndarray,
    start: int,
    valid_len: int,
    window: int,
    window_full: np.ndarray,
) -> None:
    """Add one chunk's contribution in place.

    The arithmetic and the addition order are exactly those of the historical
    list-then-stitch implementation, so streaming cannot change the samples.
    """
    pred_len = pred.shape[1]
    length = min(valid_len, pred_len)
    weight = window_full[:length] if length <= window else np.ones(length, np.float32)
    acc[:, start:start + length] += pred[:, :length] * weight[None, :]
    weight_sum[start:start + length] += weight


def _finalize_ola(acc: np.ndarray, weight_sum: np.ndarray) -> np.ndarray:
    """Normalize the overlap-add accumulator **in place**.

    ``acc`` is our own accumulator (never a caller's buffer), so the division
    happens with ``out=acc``: no full-size temporary and no pointless ``astype``
    copy.  A position whose weight is zero keeps the accumulator value, which is
    exactly what the previous ``weights[weights == 0] = 1.0`` produced - without
    mutating the caller's ``weight_sum`` as a side effect.
    """
    np.divide(acc, weight_sum, out=acc, where=(weight_sum != 0))
    return acc


def _wola_stitch(predictions: List[Tuple[np.ndarray, int, int]], total_len: int, window: int) -> np.ndarray:
    """Stitch a list of predictions (compatibility and testing wrapper).

    ``upscale`` no longer retains the prediction list - it accumulates each
    chunk as it is produced - but the list-based path stays available and
    produces identical samples.
    """
    if not predictions:
        return np.zeros((1, max(1, total_len)), np.float32)
    channels = predictions[0][0].shape[0]
    acc = np.zeros((channels, total_len), np.float32)
    weight_sum = np.zeros(total_len, np.float32)
    window_full = np.hanning(window).astype(np.float32)
    for pred, start, valid_len in predictions:
        _ola_accumulate(acc, weight_sum, pred, start, valid_len, window, window_full)
    return _finalize_ola(acc, weight_sum)


def _resolve_execution_device(torch_module: Any) -> str:
    """Concrete device the runner will use.

    The default rule is unchanged (CUDA when available, otherwise CPU), but the
    identity is explicit - ``cuda:0`` instead of the generic ``cuda`` - so the
    cache cannot be shared with a different device index by accident.  An explicit
    choice through ``MINIMAX_FLASHSR_DEVICE`` (``cpu`` or ``cuda:N``) is honoured
    when the runtime supports it; an unusable value warns and falls back to the
    automatic rule instead of failing the run.
    """
    requested = (os.environ.get("MINIMAX_FLASHSR_DEVICE") or "").strip().lower()
    if requested == "cpu":
        LOGGER.info("FlashSR device explicitly set to CPU (MINIMAX_FLASHSR_DEVICE).")
        return "cpu"
    try:
        cuda_available = bool(torch_module.cuda.is_available())
    except Exception:
        cuda_available = False
    if requested.startswith("cuda"):
        if not cuda_available:
            LOGGER.warning(
                "MINIMAX_FLASHSR_DEVICE=%s was requested but CUDA is not available; using CPU.",
                requested,
            )
            return "cpu"
        try:
            count = int(torch_module.cuda.device_count())
        except Exception:
            count = 1
        index = 0
        if ":" in requested:
            try:
                index = int(requested.split(":", 1)[1])
            except ValueError:
                index = 0
        if index < 0 or index >= max(1, count):
            LOGGER.warning(
                "MINIMAX_FLASHSR_DEVICE=%s is not a visible device (0..%d); using the default device.",
                requested,
                max(0, count - 1),
            )
        else:
            LOGGER.info("FlashSR device explicitly set to cuda:%d (MINIMAX_FLASHSR_DEVICE).", index)
            return f"cuda:{index}"
    elif requested:
        LOGGER.warning("Ignoring unknown MINIMAX_FLASHSR_DEVICE=%s; using the automatic device rule.", requested)
    if not cuda_available:
        return "cpu"
    try:
        index = int(torch_module.cuda.current_device())
    except Exception:
        index = 0
    return f"cuda:{index}"


def _ensure_flashsr_weights(auto_download: bool) -> Path:
    """Check/download the FlashSR weights; return the weights directory.

    The inference code is bundled in ``flashsr_inference/`` and needs no
    download.  Only the three weight files (student_ldm.pth, sr_vocoder.pth,
    vae.pth) are fetched from the configured Hugging Face dataset on first use.

    Missing weights fail here, with or without auto-download: this function
    exists to prepare inference, so deferring the failure to runner construction
    only moved the same error later with a less useful message.
    """
    config = load_models_config().get("flashsr", {})
    weights_entries = normalize_model_entries({"flashsr": config}, minimax=False, flux2=False, llm=False)
    weights_section = config.get("weights", {})
    weights_target = weights_section.get("target", "models/audio/flashsr")

    report = check_file_entries(weights_entries, base_path=None, auto_download=auto_download)
    failed = [item for item in report if item["status"] == "failed"]
    if failed:
        raise RuntimeError("FlashSR weights could not be prepared: " + "; ".join(f"{i['name']} ({i['message']})" for i in failed))
    for item in report:
        if item["status"] in {"downloaded", "missing"}:
            LOGGER.info("FlashSR model file: %s -> %s", item["status"], item["target"])
    missing = [item for item in report if item["status"] == "missing"]
    if missing:
        raise RuntimeError(
            "FlashSR weights are missing (auto-download %s). Required: %s"
            % ("enabled" if auto_download else "disabled", ", ".join(i["name"] for i in missing))
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
    """Return a cached FlashSR runner for the given weights location.

    Construction is transactional: the concrete execution device is resolved
    first, the required weight files are checked before the model is built, and
    a failed device transfer is undone so the runner really is wholly on CPU
    instead of reporting CUDA while the model sits on the host.  The cache is
    only published once construction succeeded.
    """
    import torch
    device = _resolve_execution_device(torch)
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
    actual_device = device
    rebuilt = False
    try:
        model.to(device)
    except Exception as exc:
        LOGGER.warning("Could not move FlashSR model to %s (%s); falling back to CPU", device, exc)
        try:
            # Undo a partial transfer: a half-moved model is worse than a CPU one.
            model.to("cpu")
        except Exception as undo_exc:
            # Undoing is not guaranteed either.  Discard the instance and build a
            # clean CPU model rather than publishing something half-moved - an OOM
            # during the transfer must not poison the cache.
            LOGGER.warning(
                "Could not restore the half-moved FlashSR model to CPU (%s); rebuilding it from the checkpoints.",
                undo_exc,
            )
            model = FlashSR(str(student), str(vocoder), str(vae))
            model.eval()
            rebuilt = True
        actual_device = "cpu"

    # ``VAEWrapper`` is not an ``nn.Module``, so ``.to()`` never moves it; the
    # vendor code places it inside ``preprocess()``.  It is deliberately not
    # touched here - making it an ``nn.Module`` would change the state-dict keys.
    runner = {
        "model": model,
        "device": actual_device,
        "requested_device": device,
        "fallback": actual_device != device,
        "rebuilt_on_cpu": rebuilt,
    }
    if actual_device != device:
        LOGGER.info("FlashSR runner published on %s (requested %s)", actual_device, device)
    _runner_cache[key] = runner
    return runner


def clear_flashsr_cache() -> int:
    """Free all cached FlashSR runners; returns how many were released."""
    count = len(_runner_cache)
    _runner_cache.clear()
    if count:
        LOGGER.info("Released %d cached FlashSR model instance(s)", count)
    return count


def _upscale_item(
    model: Any,
    device: str,
    item_cs: np.ndarray,
    lowpass_input: bool,
    pbar: Any,
    progress_offset: int,
    total_progress: int,
    label: str,
    seed: Optional[int] = None,
) -> np.ndarray:
    """Upscale one batch item (``[C, S]``) with streaming overlap-add.

    Each chunk is added to the accumulator as soon as it is produced, so the
    retained memory is the output-sized accumulator instead of every padded chunk
    output; the addition order is unchanged, which keeps the samples bit-identical
    to the historical list-then-stitch path.  The ComfyUI interrupt flag is checked
    between chunks, so a cancel does not have to wait for the whole item.
    """
    import torch

    window = CHUNK_SAMPLES
    hop = int((CHUNK_S - OVERLAP_S) * REQ_SR)
    if hop <= 0 or hop >= window:
        hop = window // 2

    total = int(item_cs.shape[1])
    spans = _iter_chunks(total, window, hop)
    total_chunks = len(spans)
    log_every = max(1, total_chunks // 10)
    window_full = np.hanning(window).astype(np.float32)
    acc: Optional[np.ndarray] = None
    weight_sum = np.zeros(total, np.float32)
    # One reused buffer pair instead of two fresh StringIO objects per chunk;
    # the vendored tqdm bar is suppressed and the tail is kept for a diagnostic.
    vendor_stdout = io.StringIO()
    vendor_stderr = io.StringIO()
    for chunk_index, (start, length) in enumerate(spans):
        if _processing_interrupted():
            LOGGER.info("FlashSR generation cancelled by the user during %s.", label)
            raise _interrupt_exception()
        chunk = item_cs[:, start:start + length]
        if length < window:
            chunk = np.concatenate(
                [chunk, np.zeros((item_cs.shape[0], window - length), np.float32)], axis=1
            )
        x = torch.from_numpy(chunk).to(device).float()
        vendor_stdout.seek(0)
        vendor_stdout.truncate(0)
        vendor_stderr.seek(0)
        vendor_stderr.truncate(0)
        try:
            with _deterministic_rng(seed if seed is None else int(seed) + chunk_index):
                with torch.inference_mode(), contextlib.redirect_stdout(vendor_stdout), contextlib.redirect_stderr(vendor_stderr):
                    y = model(x, lowpass_input=bool(lowpass_input))
        except Exception as exc:
            tail = vendor_stderr.getvalue().strip()[-2000:]
            if tail:
                raise RuntimeError(
                    f"FlashSR inference failed on {label} chunk {chunk_index + 1}/{total_chunks}: {exc}\n{tail}"
                ) from exc
            raise
        pred = y.detach().to("cpu").float().numpy()
        if acc is None:
            # Channel count comes from the first prediction, exactly as the
            # historical stitch did.
            acc = np.zeros((pred.shape[0], total), np.float32)
        _ola_accumulate(acc, weight_sum, pred, start, length, window, window_full)
        del pred, y, x  # release the per-chunk tensors immediately
        pbar.update_absolute(min(total_progress, progress_offset + chunk_index + 1))
        done = chunk_index + 1
        if done % log_every == 0 or done == total_chunks:
            LOGGER.info("FlashSR progress for %s %s", label, format_progress_bar(done, total_chunks))

    if acc is None:
        return np.zeros((max(1, int(item_cs.shape[0])), max(1, total)), np.float32)
    return _finalize_ola(acc, weight_sum)


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
    CATEGORY = "Music Production Toolkit/audio"

    def upscale(self, audio=None, lowpass_input=False, output_sr="48000", auto_download=True, seed=None):
        """Upscale **every** batch item and return one ``[B, C, T]`` AUDIO.

        ``seed=None`` keeps the historical random semantics; an integer seed makes
        the vendor's stochastic steps reproducible through a locked, restored RNG
        context (determinism is only promised for the backend combination that was
        actually tested - see the module tests).
        """
        batch, in_sr = _to_batch_channel_samples(audio)
        weights_dir = _ensure_flashsr_weights(bool(auto_download))
        runner = _get_runner(weights_dir)
        model = runner["model"]
        device = runner["device"]
        target_sr = int(output_sr)

        if in_sr != REQ_SR:
            LOGGER.info("Resampling input to FlashSR rate: %d Hz -> %d Hz", in_sr, REQ_SR)
            batch = [_resample_hq(item, in_sr, REQ_SR) for item in batch]

        total_items = len(batch)
        per_item_chunks = [len(_iter_chunks(int(item.shape[1]), CHUNK_SAMPLES, max(1, int((CHUNK_S - OVERLAP_S) * REQ_SR)))) for item in batch]
        pbar = make_progress_bar(max(1, sum(per_item_chunks)))
        LOGGER.info(
            "FlashSR upscaling: %d batch item(s), %d samples @ %d Hz on %s",
            total_items,
            int(batch[0].shape[1]) if batch else 0,
            REQ_SR,
            device,
        )
        outputs: List[np.ndarray] = []
        offset = 0
        for index, item in enumerate(batch):
            label = f"item {index + 1}/{total_items}" if total_items > 1 else "audio"
            out_item = _upscale_item(
                model, device, item, bool(lowpass_input), pbar, offset,
                max(1, sum(per_item_chunks)), label, seed,
            )
            offset += per_item_chunks[index]
            if target_sr != REQ_SR:
                out_item = _resample_hq(out_item, REQ_SR, target_sr)
            outputs.append(out_item)

        out_batch, padded = _make_audio_batch(target_sr, outputs)
        LOGGER.info(
            "FlashSR upscale finished: %d item(s), %d Hz -> %d Hz, %d samples on %s",
            total_items,
            in_sr,
            target_sr,
            int(out_batch["waveform"].shape[-1]),
            device,
        )
        settings_json = json.dumps({
            "schema": "flashsr_settings_v1",
            "inference_sr": REQ_SR,
            "chunk_s": CHUNK_S,
            "overlap_s": OVERLAP_S,
            "lowpass_input": bool(lowpass_input),
            "output_sr": target_sr,
            "device": device,
            "device_requested": runner.get("requested_device", device),
            "device_fallback": bool(runner.get("fallback")),
            "batch_items": total_items,
            "padded": bool(padded),
            "seed": seed,
            "determinism": (
                "seeded (locked RNG context); only guaranteed for the tested backend combination"
                if seed is not None
                else "unseeded (historical random semantics)"
            ),
        }, ensure_ascii=False, indent=2)
        return (out_batch, settings_json)


NODE_CLASS_MAPPINGS = {
    "MiniMaxFlashSRAudio": MiniMaxFlashSRAudio,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxFlashSRAudio": "Audio Super Resolution (FlashSR, integrated)",
}
