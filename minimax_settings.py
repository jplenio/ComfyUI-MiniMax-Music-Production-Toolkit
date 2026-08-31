from __future__ import annotations

MAX_SEED = 9223372036854775806


class MiniMaxMusic3GenerationSettings:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "generation_seed": ("INT", {"forceInput": True}),
                "max_duration": ("FLOAT", {"default": 300.0, "min": 1.0, "max": 360.0, "step": 1.0}),
                "text_cfg_scale": ("FLOAT", {"default": 1.7, "min": 0.0, "max": 10.0, "step": 0.05}),
                "text_top_k": ("INT", {"default": 50, "min": 1, "max": 1000, "step": 1}),
                "ksampler_seed_offset": ("INT", {"default": 0, "min": -1000000, "max": 1000000, "step": 1}),
                "ksampler_steps": ("INT", {"default": 40, "min": 1, "max": 200, "step": 1}),
                "ksampler_cfg": ("FLOAT", {"default": 1.7, "min": 0.0, "max": 20.0, "step": 0.05}),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("FLOAT", "INT", "FLOAT", "INT", "INT", "INT", "FLOAT", "FLOAT")
    RETURN_NAMES = (
        "max_duration", "text_seed", "text_cfg_scale", "text_top_k", "ksampler_seed",
        "ksampler_steps", "ksampler_cfg", "denoise",
    )
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/config"

    def build(self, generation_seed, max_duration, text_cfg_scale, text_top_k, ksampler_seed_offset,
              ksampler_steps, ksampler_cfg, denoise):
        text_seed = int(generation_seed) % (MAX_SEED + 1)
        ksampler_seed = (text_seed + int(ksampler_seed_offset)) % (MAX_SEED + 1)
        return (
            float(max_duration), text_seed, float(text_cfg_scale), int(text_top_k), ksampler_seed,
            int(ksampler_steps), float(ksampler_cfg), float(denoise),
        )


NODE_CLASS_MAPPINGS = {"MiniMaxMusic3GenerationSettings": MiniMaxMusic3GenerationSettings}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxMusic3GenerationSettings": "MiniMax Music 3 Generation Settings"}


class FlashSRProcessingSettings:
    @classmethod
    def INPUT_TYPES(cls):
        from .audio_lowpass import PRESETS
        choices = list(PRESETS.keys())
        return {
            "required": {
                "pre_preset": (choices, {"default": "PRE 12 kHz - recommended"}),
                "pre_custom_cutoff_hz": ("FLOAT", {"default": 12000.0, "min": 20.0, "max": 96000.0, "step": 10.0}),
                "pre_custom_order": ("INT", {"default": 2, "min": 1, "max": 12, "step": 1}),
                "pre_custom_phase": (["zero_phase", "causal"], {"default": "zero_phase"}),
                "pre_bypass": ("BOOLEAN", {"default": False}),
                "post_preset": (choices, {"default": "POST 19 kHz - slightly stronger"}),
                "post_custom_cutoff_hz": ("FLOAT", {"default": 19000.0, "min": 20.0, "max": 96000.0, "step": 10.0}),
                "post_custom_order": ("INT", {"default": 2, "min": 1, "max": 12, "step": 1}),
                "post_custom_phase": (["zero_phase", "causal"], {"default": "causal"}),
                "post_bypass": ("BOOLEAN", {"default": False}),
                "flashsr_lowpass_input": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = (
        "STRING", "FLOAT", "INT", "STRING", "BOOLEAN", "STRING",
        "STRING", "FLOAT", "INT", "STRING", "BOOLEAN", "STRING",
        "BOOLEAN"
    )
    RETURN_NAMES = (
        "pre_preset", "pre_cutoff_hz", "pre_order", "pre_phase", "pre_bypass", "pre_settings_json",
        "post_preset", "post_cutoff_hz", "post_order", "post_phase", "post_bypass", "post_settings_json",
        "flashsr_lowpass_input"
    )
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/config"

    def build(self, pre_preset, pre_custom_cutoff_hz, pre_custom_order, pre_custom_phase, pre_bypass,
              post_preset, post_custom_cutoff_hz, post_custom_order, post_custom_phase, post_bypass,
              flashsr_lowpass_input):
        import json
        from .audio_lowpass import _resolve_settings
        pre_cut, pre_order, pre_phase, pre_desc = _resolve_settings(pre_preset, pre_custom_cutoff_hz, pre_custom_order, pre_custom_phase)
        post_cut, post_order, post_phase, post_desc = _resolve_settings(post_preset, post_custom_cutoff_hz, post_custom_order, post_custom_phase)
        pre_json = json.dumps({
            "preset": pre_preset, "cutoff_hz": pre_cut, "order": pre_order,
            "phase_mode": pre_phase, "bypass": bool(pre_bypass), "description": pre_desc,
        }, ensure_ascii=False)
        post_json = json.dumps({
            "preset": post_preset, "cutoff_hz": post_cut, "order": post_order,
            "phase_mode": post_phase, "bypass": bool(post_bypass), "description": post_desc,
        }, ensure_ascii=False)
        return (
            str(pre_preset), float(pre_cut), int(pre_order), str(pre_phase), bool(pre_bypass), pre_json,
            str(post_preset), float(post_cut), int(post_order), str(post_phase), bool(post_bypass), post_json,
            bool(flashsr_lowpass_input),
        )


NODE_CLASS_MAPPINGS["FlashSRProcessingSettings"] = FlashSRProcessingSettings
NODE_DISPLAY_NAME_MAPPINGS["FlashSRProcessingSettings"] = "FlashSR Processing Settings"
