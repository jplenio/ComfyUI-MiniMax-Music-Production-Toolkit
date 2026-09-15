from __future__ import annotations

import json

from .model_profiles import SongModelProfile, default_profile, profile_from_payload
from .toolkit_logging import get_logger

LOGGER = get_logger("settings")

MAX_SEED = 9223372036854775806

# Sampler/scheduler vocabularies come from the host ComfyUI.  The fallbacks keep
# node registration alive when the toolkit is imported outside ComfyUI (tests,
# scripts, documentation builds).
try:
    import comfy.samplers

    SAMPLER_CHOICES = list(comfy.samplers.KSampler.SAMPLERS)
    SCHEDULER_CHOICES = list(comfy.samplers.KSampler.SCHEDULERS)
except Exception:  # pragma: no cover - only outside a real ComfyUI install
    SAMPLER_CHOICES = ["euler", "dpm_2"]
    SCHEDULER_CHOICES = ["simple", "sgm_uniform"]


def _combo_choice(options, wanted: str, fallback: str = "") -> str:
    """Return *wanted* when the host offers it, else *fallback* (or the first option)."""
    wanted = str(wanted or "").strip()
    if wanted and wanted in options:
        return wanted
    fallback = str(fallback or "").strip()
    if fallback and fallback in options:
        return fallback
    return options[0] if options else wanted or fallback


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


class MiniMaxMusicModelSettings:
    """Generation settings for the selected song model.

    The toolkit drives two song models with different sampling vocabularies, so
    this node keeps one value group per model and publishes the group that
    belongs to the model selected on the profile node.  Every widget is visible
    and editable at the same time - nothing is silently re-derived - while the
    duration window and the recommended sampler values follow the profile.

    The node also records both groups in ``settings_json`` so a production JSON
    can show what the other model would have used and which group was active.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "generation_seed": ("INT", {"forceInput": True}),
                "max_duration": ("FLOAT", {"default": 300.0, "min": 1.0, "max": 900.0, "step": 1.0}),
                "ksampler_seed_offset": ("INT", {"default": 0, "min": -1000000, "max": 1000000, "step": 1}),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "minimax_steps": ("INT", {"default": 40, "min": 1, "max": 200, "step": 1}),
                "minimax_cfg": ("FLOAT", {"default": 1.7, "min": 0.0, "max": 20.0, "step": 0.05}),
                "minimax_sampler_name": (SAMPLER_CHOICES, {"default": _combo_choice(SAMPLER_CHOICES, "euler")}),
                "minimax_scheduler": (SCHEDULER_CHOICES, {"default": _combo_choice(SCHEDULER_CHOICES, "simple")}),
                "minimax_text_cfg_scale": ("FLOAT", {"default": 1.7, "min": 0.0, "max": 10.0, "step": 0.05}),
                "minimax_text_top_k": ("INT", {"default": 50, "min": 1, "max": 1000, "step": 1}),
                "yue2_steps": ("INT", {"default": 32, "min": 1, "max": 200, "step": 1}),
                "yue2_cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 20.0, "step": 0.05}),
                "yue2_sampler_name": (SAMPLER_CHOICES, {"default": _combo_choice(SAMPLER_CHOICES, "dpm_2")}),
                "yue2_scheduler": (SCHEDULER_CHOICES, {"default": _combo_choice(SCHEDULER_CHOICES, "sgm_uniform")}),
                "yue2_mode": (["full", "melody"], {"default": "full"}),
                "yue2_temperature": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 5.0, "step": 0.05}),
                "yue2_top_p": ("FLOAT", {"default": 0.95, "min": 0.01, "max": 1.0, "step": 0.01}),
                "yue2_top_k": ("INT", {"default": 100, "min": 1, "max": 32768, "step": 1}),
                "yue2_repetition_penalty": ("FLOAT", {"default": 1.2, "min": 0.01, "max": 10.0, "step": 0.01}),
            },
            "optional": {
                # Appended so the optional group keeps its historic position. The
                # profile wire is what makes the values model-aware.
                "profile_json": ("STRING", {"forceInput": True, "multiline": True}),
                "yue2_max_duration": ("FLOAT", {"default": 360.0, "min": 1.0, "max": 900.0, "step": 1.0}),
            },
        }

    RETURN_TYPES = (
        "FLOAT", "INT", "FLOAT", "INT",
        "STRING", "FLOAT", "FLOAT", "INT", "FLOAT",
        "INT", "INT", "FLOAT", "STRING", "STRING", "FLOAT",
        "STRING",
    )
    RETURN_NAMES = (
        "max_duration", "text_seed", "text_cfg_scale", "text_top_k",
        "yue2_mode", "yue2_temperature", "yue2_top_p", "yue2_top_k", "yue2_repetition_penalty",
        "ksampler_seed", "ksampler_steps", "ksampler_cfg", "sampler_name", "scheduler", "denoise",
        "settings_json",
    )
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/config"
    DESCRIPTION = (
        "Generation settings that follow the selected song model. The active value group (MiniMax Music 3 "
        "or YuE2) is chosen by the profile wire, the duration is clamped to that model's window, and "
        "settings_json records both groups plus everything that was active."
    )

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        # Sampler/scheduler lists are host-dependent; validate at run time so an
        # unknown value can be replaced with a clear log line instead of an
        # opaque validation error.
        return True

    def build(
        self,
        generation_seed,
        max_duration,
        ksampler_seed_offset,
        denoise,
        minimax_steps,
        minimax_cfg,
        minimax_sampler_name,
        minimax_scheduler,
        minimax_text_cfg_scale,
        minimax_text_top_k,
        yue2_steps,
        yue2_cfg,
        yue2_sampler_name,
        yue2_scheduler,
        yue2_mode,
        yue2_temperature,
        yue2_top_p,
        yue2_top_k,
        yue2_repetition_penalty,
        profile_json="",
        yue2_max_duration=None,
    ):
        profile = profile_from_payload(profile_json) or default_profile()
        notes = []

        requested_duration = yue2_max_duration if profile.is_yue2 and yue2_max_duration is not None else max_duration
        duration, note = profile.clamp_duration(requested_duration)
        if note:
            notes.append(note)

        text_seed = int(generation_seed) % (MAX_SEED + 1)
        ksampler_seed = (text_seed + int(ksampler_seed_offset)) % (MAX_SEED + 1)

        minimax_group = {
            "steps": int(minimax_steps),
            "cfg": float(minimax_cfg),
            "sampler_name": str(minimax_sampler_name),
            "scheduler": str(minimax_scheduler),
        }
        yue2_group = {
            "steps": int(yue2_steps),
            "cfg": float(yue2_cfg),
            "sampler_name": str(yue2_sampler_name),
            "scheduler": str(yue2_scheduler),
        }
        active_group = yue2_group if profile.is_yue2 else minimax_group

        sampler_name = _combo_choice(SAMPLER_CHOICES, active_group["sampler_name"], profile.sampler_defaults.get("sampler_name", ""))
        if sampler_name != active_group["sampler_name"]:
            notes.append(f"sampler '{active_group['sampler_name']}' is not offered by this ComfyUI; using '{sampler_name}'")
        scheduler = _combo_choice(SCHEDULER_CHOICES, active_group["scheduler"], profile.sampler_defaults.get("scheduler", ""))
        if scheduler != active_group["scheduler"]:
            notes.append(f"scheduler '{active_group['scheduler']}' is not offered by this ComfyUI; using '{scheduler}'")

        report = {
            "schema": "minimax_music_model_settings_v1",
            "song_model": profile.id,
            "song_model_name": profile.display_name,
            "active_group": "yue2" if profile.is_yue2 else "minimax_music3",
            "generation_seed": int(generation_seed),
            "text_seed": text_seed,
            "ksampler_seed": ksampler_seed,
            "ksampler_seed_offset": int(ksampler_seed_offset),
            "max_duration": duration,
            "requested_max_duration": float(requested_duration),
            "minimax_max_duration": float(max_duration),
            "yue2_max_duration": float(yue2_max_duration) if yue2_max_duration is not None else float(max_duration),
            "duration_ceiling": profile.duration_ceiling(),
            "denoise": float(denoise),
            "minimax_music3": {
                **minimax_group,
                "text_cfg_scale": float(minimax_text_cfg_scale),
                "text_top_k": int(minimax_text_top_k),
            },
            "yue2": {
                **yue2_group,
                "mode": str(yue2_mode),
                "temperature": float(yue2_temperature),
                "top_p": float(yue2_top_p),
                "top_k": int(yue2_top_k),
                "repetition_penalty": float(yue2_repetition_penalty),
            },
            "active": {
                "steps": active_group["steps"],
                "cfg": active_group["cfg"],
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": float(denoise),
            },
            "notes": notes,
        }
        # Retain the effective central switches in the generation receipt.
        try:
            source_profile = json.loads(profile_json) if isinstance(profile_json, str) else profile_json
        except (ValueError, TypeError):
            source_profile = None
        if isinstance(source_profile, dict) and isinstance(source_profile.get("production_stages"), dict):
            report["production_stages"] = dict(source_profile["production_stages"])
        for line in notes:
            LOGGER.info("Music settings: %s", line)
        LOGGER.info(
            "Music settings for %s: duration=%g s, seed=%d, steps=%d, cfg=%g, %s/%s%s",
            profile.display_name, duration, text_seed, active_group["steps"], active_group["cfg"],
            sampler_name, scheduler, f", mode={yue2_mode}" if profile.is_yue2 else "",
        )
        return (
            duration, text_seed, float(minimax_text_cfg_scale), int(minimax_text_top_k),
            str(yue2_mode), float(yue2_temperature), float(yue2_top_p), int(yue2_top_k),
            float(yue2_repetition_penalty),
            ksampler_seed, int(active_group["steps"]), float(active_group["cfg"]),
            sampler_name, scheduler, float(denoise),
            json.dumps(report, ensure_ascii=False),
        )


NODE_CLASS_MAPPINGS["MiniMaxMusicModelSettings"] = MiniMaxMusicModelSettings
NODE_DISPLAY_NAME_MAPPINGS["MiniMaxMusicModelSettings"] = (
    "Music settings · adapts to the selected song model"
)
