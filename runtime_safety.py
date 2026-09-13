"""Runtime safeguards for MiniMax Music 3 on recent ComfyUI backends.

ComfyUI 0.35 enables the Comfy compiler's allocation graphs by default. The
MiniMax Music 3 AR decoder and DiT both use dynamic, layer-by-layer weight
loading, which makes a stale graph particularly harmful: it can produce
plausible-looking but incoherent audio, or non-finite diffusion latents on the
next queued run.

The default policy is ``off`` so installing the toolkit never changes ComfyUI's
performance profile. Set ``MINIMAX_MUSIC3_RUNTIME_SAFETY=auto`` to apply the
workaround only when the accelerator is marked risky (Blackwell-class CUDA or
ROCm, where the graph paths are known to corrupt MiniMax Music 3 output), ``=on``
to force it on any backend, or ``=strict`` to disable the compiler as well as
CUDA graphs.
"""
from __future__ import annotations

import os
from typing import Any

from .toolkit_logging import get_logger

LOGGER = get_logger("runtime_safety")


def _policy() -> str:
    value = os.getenv("MINIMAX_MUSIC3_RUNTIME_SAFETY", "off").strip().lower()
    if value in {"off", "0", "false", "no"}:
        return "off"
    # ``auto`` keeps its own policy: ``configure_runtime`` then decides from the
    # detected backend. Folding it into ``off`` made the risky-backend branch
    # below unreachable, so the documented automatic mode silently did nothing.
    if value in {"auto", "detect"}:
        return "auto"
    if value in {"strict", "2"}:
        return "strict"
    if value in {"on", "1", "true", "yes", "force"}:
        return "on"
    return "off"


def _runtime_info() -> dict[str, Any] | None:
    """Return current accelerator information, or ``None`` outside ComfyUI."""
    try:
        import torch
        import comfy.model_management as model_management
    except Exception:
        return None

    try:
        device = model_management.get_torch_device()
        if device is None or getattr(device, "type", None) != "cuda":
            return {"device": device, "risky": False, "kind": "non-cuda"}
        if not torch.cuda.is_available():
            return {"device": device, "risky": False, "kind": "cuda-unavailable"}
        is_hip = bool(getattr(torch.version, "hip", None))
        capability = None
        if not is_hip:
            capability = tuple(int(v) for v in torch.cuda.get_device_capability(device))
        # Blackwell (sm_120+) and current ROCm graph paths need the conservative
        # path. Older CUDA cards retain the normal performance defaults.
        risky = is_hip or (capability is not None and capability[0] >= 12)
        return {
            "device": device,
            "risky": risky,
            "kind": "rocm" if is_hip else "cuda",
            "capability": capability,
        }
    except Exception:
        # A compatibility helper must never prevent ComfyUI from starting.
        LOGGER.debug("Could not inspect the accelerator for runtime safety", exc_info=True)
        return None


def _set_safe_flags(*, strict: bool = False) -> bool:
    """Disable CUDA graph capture, optionally disabling the compiler too."""
    try:
        from comfy.cli_args import args
    except Exception:
        return False

    changed = not bool(getattr(args, "disable_cuda_graphs", False)) or (
        strict and not bool(getattr(args, "disable_comfy_compiler", False))
    )
    # Keep ComfyUI's allocation compiler active in the normal diagnostic mode;
    # it is substantially faster than disabling the whole compiler. The strict
    # mode is reserved for reproducing a backend/compiler failure.
    args.disable_cuda_graphs = True
    if strict:
        args.disable_comfy_compiler = True
    return changed


def configure_runtime() -> dict[str, Any]:
    """Apply the startup policy once and return a diagnostic report.

    ``off`` (the default) is inert by design. ``auto`` enables the workaround only
    for a backend that :func:`_runtime_info` marks risky, ``on``/``strict`` force
    it on any backend.
    """
    policy = _policy()
    # Keep the default path genuinely inert: importing the toolkit must not
    # initialize torch/CUDA or inspect ComfyUI's accelerator just to decide
    # that no diagnostic workaround was requested.
    if policy == "off":
        return {"policy": policy, "enabled": False, "reason": "disabled"}
    info = _runtime_info()
    if info is None:
        return {"policy": policy, "enabled": False, "reason": "disabled-or-unavailable"}
    enabled = policy in {"on", "strict"} or bool(info.get("risky"))
    if not enabled:
        return {"policy": policy, "enabled": False, "reason": "backend-not-marked-risky", **info}

    changed = _set_safe_flags(strict=policy == "strict")
    if changed:
        LOGGER.warning(
            "MiniMax Music 3 diagnostic safety enabled: CUDA graphs are disabled while "
            "the allocation compiler remains active (%s%s). Use "
            "MINIMAX_MUSIC3_RUNTIME_SAFETY=strict only for a slower compatibility test.",
            info.get("kind", "accelerator"),
            f" sm_{info['capability'][0]}{info['capability'][1]}" if info.get("capability") else "",
        )
    return {"policy": policy, "enabled": True, "changed": changed, **info}


def prepare_sampler_retry() -> dict[str, bool]:
    """Drop captured/prefetched state before a one-time sampler retry.

    The returned flag state is restored by :func:`restore_sampler_retry_state`
    after the retry.  This is important for the default performance profile:
    one transient numerical failure must not permanently disable CUDA graphs
    for every later generation in the same ComfyUI process.
    """
    try:
        from comfy.cli_args import args
        previous = {
            "disable_cuda_graphs": bool(getattr(args, "disable_cuda_graphs", False)),
            "disable_comfy_compiler": bool(getattr(args, "disable_comfy_compiler", False)),
        }
    except Exception:
        previous = {}

    changed = _set_safe_flags(strict=False)
    try:
        import comfy.model_prefetch as model_prefetch
        model_prefetch.cleanup_prefetch_queues()
    except Exception:
        LOGGER.debug("Could not clear ComfyUI prefetch queues before sampler retry", exc_info=True)
    try:
        import comfy.model_management as model_management
        reset = getattr(model_management, "reset_cast_buffers", None)
        if callable(reset):
            reset()
    except Exception:
        LOGGER.debug("Could not reset ComfyUI cast buffers before sampler retry", exc_info=True)
    if changed:
        LOGGER.warning("MiniMax sampler retry is running with CUDA graph capture disabled.")
    return previous


def restore_sampler_retry_state(previous: dict[str, bool] | None) -> None:
    """Restore graph/compiler flags saved before a one-time sampler retry."""
    if not previous:
        return
    try:
        from comfy.cli_args import args
        for name, value in previous.items():
            setattr(args, name, value)
    except Exception:
        LOGGER.debug("Could not restore ComfyUI runtime flags after sampler retry", exc_info=True)


__all__ = ["configure_runtime", "prepare_sampler_retry", "restore_sampler_retry_state"]
