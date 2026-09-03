from __future__ import annotations

import json
from pathlib import Path

from .metadata_schema import CURRENT_PRODUCTION_METADATA_SCHEMA


class MiniMaxSongMetadata:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "title": ("STRING", {"forceInput": True}),
                "caption": ("STRING", {"forceInput": True}),
                "lyrics": ("STRING", {"forceInput": True}),
                "image_prompt": ("STRING", {"forceInput": True}),
                "source_name": ("STRING", {"forceInput": True}),
                "source_path": ("STRING", {"forceInput": True}),
                "prompt_origin": ("STRING", {"forceInput": True}),
                "prompt_provenance_json": ("STRING", {"forceInput": True}),
                "run_index": ("INT", {"forceInput": True}),
                "variant_count": ("INT", {"forceInput": True}),
                "generation_seed": ("INT", {"forceInput": True}),
                "max_duration": ("FLOAT", {"forceInput": True}),
                "text_seed": ("INT", {"forceInput": True}),
                "text_cfg_scale": ("FLOAT", {"forceInput": True}),
                "text_top_k": ("INT", {"forceInput": True}),
                "ksampler_seed": ("INT", {"forceInput": True}),
                "ksampler_steps": ("INT", {"forceInput": True}),
                "ksampler_cfg": ("FLOAT", {"forceInput": True}),
                "sampler_name": ("STRING", {"forceInput": True}),
                "scheduler": ("STRING", {"forceInput": True}),
                "denoise": ("FLOAT", {"forceInput": True}),
                "pre_preset": ("STRING", {"forceInput": True}),
                "pre_settings_json": ("STRING", {"forceInput": True}),
                "post_preset": ("STRING", {"forceInput": True}),
                "post_settings_json": ("STRING", {"forceInput": True}),
                "flashsr_lowpass_input": ("BOOLEAN", {"default": False}),
                "workflow_name": ("STRING", {"default": "MiniMax Music 3 – Reproducible Batch + External ComfyUI-LLM + FlashSR + Flux2", "multiline": False}),
            },
            "optional": {
                "llm_system_prompt": ("STRING", {"forceInput": True}),
                "release_prep_json": ("STRING", {"forceInput": True}),
                "hybrid_crossover_json": ("STRING", {"forceInput": True}),
                "hf_repair_json": ("STRING", {"forceInput": True}),
                "declip_json": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("metadata_json", "summary")
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/metadata"

    def build(self, title, caption, lyrics, image_prompt, source_name, source_path, prompt_origin, prompt_provenance_json,
              run_index, variant_count, generation_seed, max_duration, text_seed, text_cfg_scale, text_top_k,
              ksampler_seed, ksampler_steps, ksampler_cfg, sampler_name, scheduler, denoise,
              pre_preset, pre_settings_json, post_preset, post_settings_json,
              flashsr_lowpass_input, workflow_name, llm_system_prompt="", release_prep_json="", hybrid_crossover_json="", hf_repair_json="", declip_json=""):
        try:
            provenance = json.loads(prompt_provenance_json) if prompt_provenance_json else {}
        except Exception:
            provenance = {"raw": prompt_provenance_json}
        try:
            pre_settings = json.loads(pre_settings_json) if pre_settings_json else {}
        except Exception:
            pre_settings = {"raw": pre_settings_json}
        try:
            post_settings = json.loads(post_settings_json) if post_settings_json else {}
        except Exception:
            post_settings = {"raw": post_settings_json}
        try:
            release_prep = json.loads(release_prep_json) if release_prep_json else {}
        except Exception:
            release_prep = {"raw": release_prep_json}
        try:
            hybrid_crossover = json.loads(hybrid_crossover_json) if hybrid_crossover_json else {}
        except Exception:
            hybrid_crossover = {"raw": hybrid_crossover_json}
        try:
            hf_repair = json.loads(hf_repair_json) if hf_repair_json else {}
        except Exception:
            hf_repair = {"raw": hf_repair_json}
        try:
            declip = json.loads(declip_json) if declip_json else {}
        except Exception:
            declip = {"raw": declip_json}

        data = {
            "schema": CURRENT_PRODUCTION_METADATA_SCHEMA,
            "workflow": workflow_name,
            "llm": {
                "system_prompt": llm_system_prompt or "",
            },
            "title": title,
            "caption": caption,
            "lyrics": lyrics,
            "image_prompt": image_prompt,
            "source": {
                "name": source_name,
                "path": source_path,
                "origin": prompt_origin,
                "run_index": int(run_index),
                "variant_count": int(variant_count),
                "prompt_provenance": provenance,
            },
            "generation_seed": int(generation_seed),
            "restoration": {
                "declip": declip,
            },
            "minimax_music3": {
                "max_duration": float(max_duration),
                "text_encode": {
                    "seed": int(text_seed),
                    "cfg_scale": float(text_cfg_scale),
                    "top_k": int(text_top_k),
                },
                "ksampler": {
                    "seed": int(ksampler_seed),
                    "steps": int(ksampler_steps),
                    "cfg": float(ksampler_cfg),
                    "sampler_name": sampler_name,
                    "scheduler": scheduler,
                    "denoise": float(denoise),
                },
            },
            "flashsr": {
                "lowpass_input": bool(flashsr_lowpass_input),
                "pre_lowpass": {
                    "preset": pre_preset,
                    "settings": pre_settings,
                },
                "hybrid_crossover": hybrid_crossover,
                "hf_cymbal_shimmer_repair": hf_repair,
                "post_lowpass": {
                    "preset": post_preset,
                    "settings": post_settings,
                },
            },
            "release_prep": release_prep,
        }
        metadata_json = json.dumps(data, ensure_ascii=False, indent=2)
        summary = (
            f"{title} | seed={generation_seed} | TextEncode seed={text_seed}, cfg={text_cfg_scale}, top_k={text_top_k} | "
            f"KSampler seed={ksampler_seed}, steps={ksampler_steps}, cfg={ksampler_cfg}, {sampler_name}/{scheduler}, denoise={denoise} | "
            f"PRE={pre_preset} | POST={post_preset}"
        )
        return (metadata_json, summary)


class MiniMaxMetadataLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"metadata_file": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = (
        "STRING", "STRING", "STRING", "STRING", "FLOAT", "INT", "INT", "FLOAT", "INT", "INT", "INT",
        "FLOAT", "STRING", "STRING", "FLOAT", "STRING", "STRING", "STRING"
    )
    RETURN_NAMES = (
        "title", "caption", "lyrics", "image_prompt", "max_duration", "generation_seed", "text_seed", "text_cfg_scale",
        "text_top_k", "ksampler_seed", "ksampler_steps", "ksampler_cfg", "sampler_name", "scheduler", "denoise",
        "pre_preset", "post_preset", "metadata_json"
    )
    FUNCTION = "load"
    CATEGORY = "MiniMax Music Production Toolkit/metadata"

    def load(self, metadata_file):
        raw = (metadata_file or "").strip()
        if not raw:
            raise ValueError("MiniMax Metadata Loader: metadata_file is empty.")
        p = Path(raw).expanduser()
        if not p.is_absolute():
            try:
                import folder_paths
                p = Path(folder_paths.get_output_directory()) / p
            except Exception:
                p = Path.cwd() / p
        data = json.loads(p.read_text(encoding="utf-8"))
        mm = data.get("minimax_music3", {})
        te = mm.get("text_encode", {})
        ks = mm.get("ksampler", {})
        fsr = data.get("flashsr", {})
        return (
            str(data.get("title", "")), str(data.get("caption", "")), str(data.get("lyrics", "")), str(data.get("image_prompt", "")),
            float(mm.get("max_duration", 300.0)), int(data.get("generation_seed", 0)), int(te.get("seed", 0)),
            float(te.get("cfg_scale", 1.7)), int(te.get("top_k", 50)), int(ks.get("seed", 0)),
            int(ks.get("steps", 40)), float(ks.get("cfg", 1.7)), str(ks.get("sampler_name", "euler")),
            str(ks.get("scheduler", "simple")), float(ks.get("denoise", 1.0)),
            str(fsr.get("pre_lowpass", {}).get("preset", "")), str(fsr.get("post_lowpass", {}).get("preset", "")),
            json.dumps(data, ensure_ascii=False, indent=2),
        )


NODE_CLASS_MAPPINGS = {
    "MiniMaxSongMetadata": MiniMaxSongMetadata,
    "MiniMaxMetadataLoader": MiniMaxMetadataLoader,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxSongMetadata": "MiniMax Song Metadata",
    "MiniMaxMetadataLoader": "MiniMax Metadata Loader",
}
