"""Expand only the selected music engine into native ComfyUI nodes.

Expansion keeps scheduling, caching and memory management with ComfyUI. No
weights (or host modules) are loaded at import or for the unselected engine.
"""
from __future__ import annotations

import json

from .model_profiles import profile_from_payload


class MusicGeneration:
    DESCRIPTION = (
        "Generates one song with the selected model profile (YuE2, YuE2 Cover or MiniMax Music 3) "
        "and returns the decoded audio plus a receipt. For a YuE2 instrumental cover with the vocal "
        "check enabled it builds one take per allowed attempt and keeps the least vocal one."
    )

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
        }, "optional": {
            "cover_source_json": ("STRING", {"forceInput": True}),
            "cover_abc": ("STRING", {"forceInput": True}),
        }}

    RETURN_TYPES = ("AUDIO", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "sampler_name", "scheduler", "generation_json")
    FUNCTION = "generate"
    CATEGORY = "MiniMax Music Production Toolkit/generation"

    def generate(self, profile_json, settings_json, style, lyrics,
                 yue2_checkpoint, minimax_model, minimax_encoder, minimax_vae,
                 tiled_decode=True, cover_source_json="", cover_abc=""):  # noqa: C901
        profile = profile_from_payload(profile_json)
        settings = json.loads(settings_json)
        if profile is None or profile.id not in {"yue2", "yue2_cover", "minimax_music3"}:
            raise ValueError("Connect a supported song model profile.")
        if settings.get("song_model") != profile.id:
            raise ValueError("Song model and generation settings disagree; connect the same profile to both.")
        from comfy_execution.graph_utils import GraphBuilder

        graph = GraphBuilder()
        seed = settings["text_seed"]
        duration = settings["max_duration"]
        abc = ""
        cover_lyrics_mode = ""
        if profile.is_yue2:
            from .song_duration import duration_line, generation_duration
            length_request = settings.get("duration_request")
            if length_request:
                duration = generation_duration(length_request, duration)
                if not style.startswith(duration_line(length_request) + "\n"):
                    raise ValueError("YuE2 Style and requested duration disagree; connect Style and settings from the same parsed prompt.")
            loader = graph.node("CheckpointLoaderSimple", ckpt_name=yue2_checkpoint)
            model, clip, vae = loader.out(0), loader.out(1), loader.out(2)
            text = settings["yue2"]
            if profile.is_cover:
                from .cover_score import adapt_cover_score
                from .music_cover import cover_source
                source = cover_source(cover_source_json)
                cover_lyrics_mode = source["lyrics_mode"]
                if not isinstance(cover_abc, str) or not cover_abc.strip():
                    raise ValueError("YuE2 Cover requires non-empty SheetSage2 ABC transcription.")
                from .cover_lyrics_contract import apply_cover_lyrics
                style, lyrics = apply_cover_lyrics(source['lyrics_mode'], style, lyrics)
                if text["mode"] != source["mode"]:
                    raise ValueError("Cover transcription and generation modes disagree.")
                # The engine receives the score the selected cover mode calls
                # for.  The rewrite is idempotent, so a graph that already ran
                # it through the score node lands on the same string.
                abc = adapt_cover_score(
                    cover_abc, source["lyrics_mode"], source["lead_instrument"])["abc"]
                from .cover_alignment import score_timeline
                if source['mode'] == 'melody':
                    from .third_party.yue2_abc import strip_chords
                    abc = strip_chords(abc)
                settings['cover_timeline'] = score_timeline(abc)
                settings.pop('cover_conditioning', None)
                if source['lyrics_mode'] == 'instrumental':
                    from .cover_conditioning import instrumental_conditioning
                    style, lyrics, settings['cover_conditioning'] = instrumental_conditioning(
                        style, lyrics, abc, source['lead_instrument'], source['mode'])
                settings['cover_conditioning'] = {**settings.get('cover_conditioning', {}),
                    'native_style': style, 'native_lyrics': lyrics, 'native_abc': abc}
            else:
                abc = graph.node("YuE2GenerateABC", clip=clip, style=style, lyrics=lyrics,
                             seed=seed, mode=text["mode"], max_abc_tokens=8192,
                             temperature=0.7, top_p=0.9, top_k=30,
                             repetition_penalty=1.005, penalty_window=100).out(0)
            # One repeatable take: encode -> sampler -> decode.  The retry loop
            # below adds takes without duplicating this model-specific wiring.
            encode_kind = "YuE2GenerateMusic"
            encode_kwargs = {
                "clip": clip, "style": style, "lyrics": lyrics, "abc": abc,
                "max_duration": duration,
                **{k: text[k] for k in ("mode", "temperature", "top_p", "top_k", "repetition_penalty")},
            }
            latent_kind = "EmptyYuE2LatentAudio"
            negative_via_zero_out = False
            files = {"checkpoint": yue2_checkpoint}
            if profile.is_cover:
                files["audio_encoder"] = source["audio_encoder"]
        else:
            model = graph.node("UNETLoader", unet_name=minimax_model, weight_dtype="default").out(0)
            clip = graph.node("CLIPLoader", clip_name=minimax_encoder, type="minimax", device="default").out(0)
            vae = graph.node("VAELoader", vae_name=minimax_vae).out(0)
            text = settings["minimax_music3"]
            encode_kind = "MiniMaxMusic3TextEncode"
            encode_kwargs = {
                "clip": clip, "caption": style, "lyrics": lyrics, "max_duration": duration,
                "cfg_scale": text["text_cfg_scale"], "top_k": text["text_top_k"],
            }
            latent_kind = "EmptyMiniMaxMusic3LatentAudio"
            negative_via_zero_out = True
            files = {"diffusion_model": minimax_model, "text_encoder": minimax_encoder, "vae": minimax_vae}

        # The vocal check is opt-in, covers only, and only ever means anything for
        # an instrumental.  Ignoring it elsewhere keeps every other path byte for
        # byte as it was.
        check_settings = settings.get("instrumental_check") or {}
        check_active = bool(check_settings.get("enabled")) and profile.is_cover \
            and cover_lyrics_mode == "instrumental"
        from .instrumental_check import MAX_RETRIES as INSTRUMENTAL_MAX_RETRIES
        from .instrumental_check import RETRY_SEED_STRIDE
        attempts = 1
        if check_active:
            retries = max(0, min(int(check_settings.get("max_retries") or 0), INSTRUMENTAL_MAX_RETRIES))
            attempts = retries + 1

        takes = []
        for attempt in range(attempts):
            offset = attempt * RETRY_SEED_STRIDE
            encoded = graph.node(encode_kind, seed=seed + offset, **encode_kwargs)
            if negative_via_zero_out:
                positive = encoded.out(0)
                negative = graph.node("ConditioningZeroOut", conditioning=positive).out(0)
            else:
                positive = negative = encoded.out(0)
            latent = graph.node(latent_kind, seconds=encoded.out(1), batch_size=1)
            sampler = graph.node("KSamplerWithConfig", model=model, positive=positive, negative=negative,
                                 latent_image=latent.out(0),
                                 seed=settings["ksampler_seed"] + offset, **settings["active"])
            audio = graph.node("MiniMaxSafeAudioDecode", samples=sampler.out(0), vae=vae,
                               tiled=tiled_decode, tile_size=1920 if profile.is_yue2 else 1536,
                               overlap=128 if profile.is_yue2 else 64)
            takes.append((encoded, sampler, audio))
        encoded, sampler, audio = takes[0]

        if check_active:
            check_inputs = {}
            tolerance = max(0, int(check_settings.get("word_tolerance") or 0))
            for index, (_encoded, _sampler, candidate) in enumerate(takes):
                checked = graph.node("MiniMaxInstrumentalVocalCheck", audio=candidate.out(0),
                                     word_tolerance=tolerance,
                                     candidate_label=f"take-{index + 1}")
                check_inputs[f"candidate_{index}"] = candidate.out(0)
                check_inputs[f"report_{index}"] = checked.out(1)
            picker = graph.node("MiniMaxInstrumentalPick",
                                max_retries=max(0, attempts - 1),
                                word_tolerance=tolerance, **check_inputs)
            audio_output = picker.out(0)
            check_report = picker.out(1)
        else:
            audio_output = audio.out(0)
            check_report = None
        receipt = graph.node("MusicGenerationReceipt", settings_json=json.dumps(settings),
                             abc=abc, seconds=encoded.out(1), model_files_json=json.dumps(files),
                             cover_source_json=cover_source_json if profile.is_cover else "",
                             instrumental_check_json=check_report if check_report is not None else "")
        return {"result": (audio_output, sampler.out(1), sampler.out(2), receipt.out(0)),
                "expand": graph.finalize()}


class MusicGenerationReceipt:
    DESCRIPTION = (
        "Collects the generation record - resolved settings, the score that was sent, requested "
        "duration, model files used and the optional instrumental vocal-check result - into one "
        "JSON string for the production record."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "settings_json": ("STRING", {"forceInput": True}),
            "abc": ("STRING", {"forceInput": True}),
            "seconds": ("FLOAT", {"forceInput": True}),
            "model_files_json": ("STRING", {"forceInput": True}),
        }, "optional": {
            "cover_source_json": ("STRING", {"forceInput": True}),
            # Appended optional input (3.1.0): the instrumental vocal check summary.
            "instrumental_check_json": ("STRING", {"forceInput": True}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("generation_json",)
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/generation"

    def build(self, settings_json, abc, seconds, model_files_json, cover_source_json="",
              instrumental_check_json=""):
        data = json.loads(settings_json)
        data.update(model_files=json.loads(model_files_json), generated_seconds=float(seconds))
        request = data.get("duration_request")
        if request:
            actual = float(seconds)
            data["duration_result"] = {
                "target_seconds": request["target_seconds"],
                "difference_from_target_seconds": actual - request["target_seconds"],
                "within_requested_range": request["minimum_seconds"] <= actual <= request["maximum_seconds"],
                "note": "Measured model output; the requested length is approximate. Finishing beyond the target is allowed within max_duration, which is a separate ceiling.",
            }
        if str(instrumental_check_json or "").strip():
            try:
                data["instrumental_check_result"] = json.loads(instrumental_check_json)
            except ValueError:
                data["instrumental_check_result"] = {"raw": instrumental_check_json}
        if data["song_model"] == "yue2_cover":
            from .music_cover import cover_record
            data.update(abc=abc, abc_source="SheetSage2 audio transcription", cover_source=cover_record(cover_source_json))
        elif data["song_model"] == "yue2":
            data["abc"] = abc
            data["abc_settings"] = dict(max_abc_tokens=8192, temperature=0.7, top_p=0.9,
                                        top_k=30, repetition_penalty=1.005, penalty_window=100)
        return (json.dumps(data, ensure_ascii=False),)


NODE_CLASS_MAPPINGS = {"MusicGeneration": MusicGeneration, "MusicGenerationReceipt": MusicGenerationReceipt}
NODE_DISPLAY_NAME_MAPPINGS = {"MusicGeneration": "Generate song · MiniMax / YuE2",
                              "MusicGenerationReceipt": "Music generation record"}
