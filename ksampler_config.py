from __future__ import annotations

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

    def sample(self, model, positive, negative, latent_image, seed, steps, cfg, sampler_name, scheduler, denoise=1.0):
        import nodes
        result = nodes.common_ksampler(
            model, int(seed), int(steps), float(cfg), str(sampler_name), str(scheduler),
            positive, negative, latent_image, denoise=float(denoise),
        )
        latent = result[0] if isinstance(result, tuple) else result
        return (latent, str(sampler_name), str(scheduler))


NODE_CLASS_MAPPINGS = {"KSamplerWithConfig": KSamplerWithConfig}
NODE_DISPLAY_NAME_MAPPINGS = {"KSamplerWithConfig": "KSampler + Config Output"}
