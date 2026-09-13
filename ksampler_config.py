from __future__ import annotations

import re

from .toolkit_logging import get_logger

LOGGER = get_logger("ksampler")

# Raised when the sampler result contains NaN/Infinity. Kept as a module constant so
# tests and the troubleshooting guide can refer to the exact same text.
NON_FINITE_LATENT_ERROR = (
    "MiniMax sampler returned NaN or Infinity; no invalid audio was passed to the decoder. "
    "The MiniMax Music 3 diffusion model runs in fp16 with the official fp16 checkpoint and "
    "reproducibly returns non-finite latents for some seed/prompt/length combinations. Repeating "
    "the identical sampling would reproduce the same values, so this node does not retry. Queue "
    "the prompt again with a new seed, or start ComfyUI with --fp32-unet (or use a MiniMax "
    "FP32/BF16 diffusion model). See TROUBLESHOOTING.md."
)

try:
    import comfy.samplers
    _SAMPLERS = list(comfy.samplers.KSampler.SAMPLERS)
    _SCHEDULERS = list(comfy.samplers.KSampler.SCHEDULERS)
except Exception:
    _SAMPLERS = ["euler"]
    _SCHEDULERS = ["simple"]


class KSamplerWithConfig:
    """Core KSampler-compatible wrapper that also returns the actual sampler/scheduler names."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "latent_image": ("LATENT",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "steps": ("INT", {"default": 40, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 1.7, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (_SAMPLERS, {"default": "euler" if "euler" in _SAMPLERS else _SAMPLERS[0]}),
                "scheduler": (_SCHEDULERS, {"default": "simple" if "simple" in _SCHEDULERS else _SCHEDULERS[0]}),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("LATENT", "STRING", "STRING")
    RETURN_NAMES = ("LATENT", "sampler_name", "scheduler")
    FUNCTION = "sample"
    CATEGORY = "MiniMax Music Production Toolkit/utilities"

    @staticmethod
    def _finite_latent(result):
        """Return ``False`` for a sampler result containing NaN/Infinity."""
        try:
            import torch
            latent = result[0] if isinstance(result, tuple) else result
            samples = latent.get("samples") if isinstance(latent, dict) else None
            if not isinstance(samples, torch.Tensor):
                return True
            if getattr(samples, "is_nested", False):
                return all(bool(torch.isfinite(item).all().item()) for item in samples.unbind())
            return bool(torch.isfinite(samples).all().item())
        except Exception:
            # Keep compatibility with older ComfyUI latent wrappers. The safe
            # decoder remains the final publication boundary in that case.
            return True

    @staticmethod
    def _recoverable_error(exc):
        text = str(exc).lower()
        return isinstance(exc, RuntimeError) and bool(
            re.search(r"nan|infinity|cuda.?graph|cudagraph|capture|overwritten", text)
        )

    def sample(self, model, positive, negative, latent_image, seed, steps, cfg, sampler_name, scheduler, denoise=1.0):
        import nodes
        def run_once():
            return nodes.common_ksampler(
                model, int(seed), int(steps), float(cfg), str(sampler_name), str(scheduler),
                positive, negative, latent_image, denoise=float(denoise),
            )

        try:
            result = run_once()
        except RuntimeError as exc:
            # Capture/CUDA-graph/backend-state errors are the one failure class where
            # clearing the captured state and repeating the sampling can help.
            if not self._recoverable_error(exc):
                raise
            from .runtime_safety import prepare_sampler_retry, restore_sampler_retry_state
            retry_state = prepare_sampler_retry()
            LOGGER.warning("Sampler backend error detected; retrying MiniMax sampling once: %s", exc)
            try:
                result = run_once()
            finally:
                restore_sampler_retry_state(retry_state)

        if not self._finite_latent(result):
            # The noise comes from this node's seed and the conditioning/weights are
            # unchanged, so an identical second pass reproduces the same values; it only
            # doubles the longest stage of the prompt. Fail fast with the real remedy.
            raise ValueError(NON_FINITE_LATENT_ERROR)

        latent = result[0] if isinstance(result, tuple) else result
        return (latent, str(sampler_name), str(scheduler))


NODE_CLASS_MAPPINGS = {"KSamplerWithConfig": KSamplerWithConfig}
NODE_DISPLAY_NAME_MAPPINGS = {"KSamplerWithConfig": "KSampler + Config Output"}
