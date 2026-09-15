"""Expand only the selected music engine into native ComfyUI nodes.

Expansion keeps scheduling, caching and memory management with ComfyUI. No
weights (or host modules) are loaded at import or for the unselected engine.
"""
from __future__ import annotations

import json

from .model_profiles import profile_from_payload


class MusicGeneration:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "profile_json": ("STRING", {"forceInput": True}),
            "settings_json": ("STRING", {"forceInput": True}),
            "style": ("STRING", {"forceInput": True}),
            "lyrics": ("STRING", {"forceInput": True}),
            "yue2_checkpoint": ("STRING", {"default": "yue2_3b_bf16.safetensors"}),
            "minimax_model": ("STRING", {"default": "minimax_music3_dit_fp16.safetensors"}),
            "minimax_encoder": ("STRING", {"default": "minimax_music3_text_encoder_pruned_int8_convrot.safetensors"}),
            "minimax_vae": ("STRING", {"default": "minimax_music3_dav.safetensors"}),
            "tiled_decode": ("BOOLEAN", {"default": True}),
        }}

    RETURN_TYPES = ("AUDIO", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "sampler_name", "scheduler", "generation_json")
    FUNCTION = "generate"
    CATEGORY = "MiniMax Music Production Toolkit/generation"

    def generate(self, profile_json, settings_json, style, lyrics,
                 yue2_checkpoint, minimax_model, minimax_encoder, minimax_vae,
                 tiled_decode=True):
        profile = profile_from_payload(profile_json)
        settings = json.loads(settings_json)
        if profile is None or profile.id not in {"yue2", "minimax_music3"}:
            raise ValueError("Connect a supported song model profile.")
        if settings.get("song_model") != profile.id:
            raise ValueError("Song model and generation settings disagree; connect the same profile to both.")
        from comfy_execution.graph_utils import GraphBuilder

        graph = GraphBuilder()
        seed = settings["text_seed"]
        duration = settings["max_duration"]
        abc = ""
        if profile.is_yue2:
            loader = graph.node("CheckpointLoaderSimple", ckpt_name=yue2_checkpoint)
            model, clip, vae = loader.out(0), loader.out(1), loader.out(2)
            text = settings["yue2"]
            abc = graph.node("YuE2GenerateABC", clip=clip, style=style, lyrics=lyrics,
                             seed=seed, mode=text["mode"], max_abc_tokens=8192,
                             temperature=0.7, top_p=0.9, top_k=30,
                             repetition_penalty=1.005, penalty_window=100).out(0)
            encoded = graph.node("YuE2GenerateMusic", clip=clip, style=style, lyrics=lyrics,
                                 abc=abc, seed=seed, max_duration=duration,
                                 **{k: text[k] for k in ("mode", "temperature", "top_p", "top_k", "repetition_penalty")})
            positive = negative = encoded.out(0)
            latent = graph.node("EmptyYuE2LatentAudio", seconds=encoded.out(1), batch_size=1)
            files = {"checkpoint": yue2_checkpoint}
        else:
            model = graph.node("UNETLoader", unet_name=minimax_model, weight_dtype="default").out(0)
            clip = graph.node("CLIPLoader", clip_name=minimax_encoder, type="minimax", device="default").out(0)
            vae = graph.node("VAELoader", vae_name=minimax_vae).out(0)
            text = settings["minimax_music3"]
            encoded = graph.node("MiniMaxMusic3TextEncode", clip=clip, caption=style, lyrics=lyrics,
                                 seed=seed, max_duration=duration,
                                 cfg_scale=text["text_cfg_scale"], top_k=text["text_top_k"])
            positive = encoded.out(0)
            negative = graph.node("ConditioningZeroOut", conditioning=positive).out(0)
            latent = graph.node("EmptyMiniMaxMusic3LatentAudio", seconds=encoded.out(1), batch_size=1)
            files = {"diffusion_model": minimax_model, "text_encoder": minimax_encoder, "vae": minimax_vae}
        sampler = graph.node("KSamplerWithConfig", model=model, positive=positive, negative=negative,
                             latent_image=latent.out(0), seed=settings["ksampler_seed"], **settings["active"])
        audio = graph.node("MiniMaxSafeAudioDecode", samples=sampler.out(0), vae=vae,
                           tiled=tiled_decode, tile_size=1920 if profile.is_yue2 else 1536,
                           overlap=128 if profile.is_yue2 else 64)
        receipt = graph.node("MusicGenerationReceipt", settings_json=settings_json,
                             abc=abc, seconds=encoded.out(1), model_files_json=json.dumps(files))
        return {"result": (audio.out(0), sampler.out(1), sampler.out(2), receipt.out(0)),
                "expand": graph.finalize()}


class MusicGenerationReceipt:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "settings_json": ("STRING", {"forceInput": True}),
            "abc": ("STRING", {"forceInput": True}),
            "seconds": ("FLOAT", {"forceInput": True}),
            "model_files_json": ("STRING", {"forceInput": True}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("generation_json",)
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/generation"

    def build(self, settings_json, abc, seconds, model_files_json):
        data = json.loads(settings_json)
        data.update(model_files=json.loads(model_files_json), generated_seconds=float(seconds))
        if data["song_model"] == "yue2":
            data["abc"] = abc
            data["abc_settings"] = dict(max_abc_tokens=8192, temperature=0.7, top_p=0.9,
                                        top_k=30, repetition_penalty=1.005, penalty_window=100)
        return (json.dumps(data, ensure_ascii=False),)


NODE_CLASS_MAPPINGS = {"MusicGeneration": MusicGeneration, "MusicGenerationReceipt": MusicGenerationReceipt}
NODE_DISPLAY_NAME_MAPPINGS = {"MusicGeneration": "Generate song · MiniMax / YuE2",
                              "MusicGenerationReceipt": "Music generation record"}
