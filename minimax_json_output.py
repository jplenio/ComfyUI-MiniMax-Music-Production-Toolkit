from __future__ import annotations

"""Central production-configuration JSON writer.

The recommended workflow writes one canonical JSON record per song into
its own configurable directory instead of duplicating sidecar JSON files beside
every audio encoding.  The node depends on the audio/artwork save results, which
makes it execute only after those artifacts have been written successfully.

Since 2.0.0 the node assembles the **complete generation record** itself: the
LLM prompt and raw answer, the structured prompt summary, the parsed
Caption/Lyrics/Title/Image_Prompt with provenance and seeds, the MiniMax
generation settings and every audio-enhancement report (declip, PRE/POST
low-pass, FlashSR, hybrid crossover, HF repair, release prep).  Together with
the standard audio tags and the `outputs` section this is enough to re-create a
song (with modified settings) from the JSON file alone.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .filename_utils import apply_filename_mode
from .metadata_schema import CURRENT_PRODUCTION_METADATA_SCHEMA
from .save_audio_smart_prefix import _pick_path, _resolve_prefix
from .toolkit_logging import get_logger

LOGGER = get_logger("production_json")

DEFAULT_WORKFLOW_NAME = "MiniMax Music Production Toolkit 2.0.0"


def _parse_object(text: str, label: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Save Production JSON: invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Save Production JSON: {label} must contain a JSON object.")
    return value


def _artifact_from_save_info(text: str, fallback_label: str) -> Dict[str, Any]:
    info = _parse_object(text, fallback_label)
    # SaveAudioSmartPrefix emits a stable object. Preserve it as-is so future
    # fields can be added without changing this aggregation node.
    return info


def _overlay(base: Dict[str, Any], key: str, value: Any) -> None:
    """Set ``base[key]`` only when the value carries real content."""
    if isinstance(value, str):
        value = value.strip()
    if value is None or value == "":
        return
    base[key] = value


def _generation_metadata(
    legacy_metadata: Dict[str, Any],
    *,
    llm_system_prompt: str = "",
    llm_user_prompt: str = "",
    llm_output: str = "",
    llm_status: str = "",
    llm_thinking: str = "",
    structured_summary_json: str = "",
    caption: str = "",
    lyrics: str = "",
    image_prompt: str = "",
    source_name: str = "",
    source_path: str = "",
    prompt_origin: str = "",
    prompt_provenance_json: str = "",
    generation_seed: Optional[int] = None,
    run_index: Optional[int] = None,
    variant_count: Optional[int] = None,
    max_duration: Optional[float] = None,
    text_seed: Optional[int] = None,
    text_cfg_scale: Optional[float] = None,
    text_top_k: Optional[int] = None,
    ksampler_seed: Optional[int] = None,
    ksampler_steps: Optional[int] = None,
    ksampler_cfg: Optional[float] = None,
    denoise: Optional[float] = None,
    flashsr_settings_json: str = "",
    pre_preset: str = "",
    pre_settings_json: str = "",
    post_preset: str = "",
    post_settings_json: str = "",
    hybrid_crossover_json: str = "",
    hf_repair_json: str = "",
    declip_json: str = "",
    release_prep_json: str = "",
    workflow_name: str = DEFAULT_WORKFLOW_NAME,
) -> Dict[str, Any]:
    """Assemble the complete generation metadata payload (schema v7).

    A legacy ``metadata_json`` payload (pre-2.0.0 song-metadata node) is used
    as the base; every directly wired input overlays it.  The schema key is
    rewritten to the current version at the end.
    """
    payload: Dict[str, Any] = dict(legacy_metadata)

    payload["schema"] = CURRENT_PRODUCTION_METADATA_SCHEMA
    _overlay(payload, "workflow", workflow_name or DEFAULT_WORKFLOW_NAME)

    llm: Dict[str, Any] = dict(payload.get("llm") or {})
    _overlay(llm, "system_prompt", llm_system_prompt)
    _overlay(llm, "user_prompt", llm_user_prompt)
    _overlay(llm, "output", llm_output)
    _overlay(llm, "status", llm_status)
    _overlay(llm, "thinking", llm_thinking)
    if llm:
        payload["llm"] = llm

    structured = _parse_object(structured_summary_json, "structured_summary_json")
    if structured:
        payload["structured_prompt"] = structured

    _overlay(payload, "caption", caption)
    _overlay(payload, "lyrics", lyrics)
    _overlay(payload, "image_prompt", image_prompt)

    source: Dict[str, Any] = dict(payload.get("source") or {})
    _overlay(source, "name", source_name)
    _overlay(source, "path", source_path)
    _overlay(source, "origin", prompt_origin)
    if run_index is not None:
        source["run_index"] = int(run_index)
    if variant_count is not None:
        source["variant_count"] = int(variant_count)
    provenance = _parse_object(prompt_provenance_json, "prompt_provenance_json")
    if provenance:
        source["prompt_provenance"] = provenance
    if source:
        payload["source"] = source

    if generation_seed is not None:
        payload["generation_seed"] = int(generation_seed)

    minimax: Dict[str, Any] = dict(payload.get("minimax_music3") or {})
    if max_duration is not None:
        minimax["max_duration"] = float(max_duration)
    text_encode: Dict[str, Any] = dict(minimax.get("text_encode") or {})
    if text_seed is not None:
        text_encode["seed"] = int(text_seed)
    if text_cfg_scale is not None:
        text_encode["cfg_scale"] = float(text_cfg_scale)
    if text_top_k is not None:
        text_encode["top_k"] = int(text_top_k)
    if text_encode:
        minimax["text_encode"] = text_encode
    ksampler: Dict[str, Any] = dict(minimax.get("ksampler") or {})
    if ksampler_seed is not None:
        ksampler["seed"] = int(ksampler_seed)
    if ksampler_steps is not None:
        ksampler["steps"] = int(ksampler_steps)
    if ksampler_cfg is not None:
        ksampler["cfg"] = float(ksampler_cfg)
    if denoise is not None:
        ksampler["denoise"] = float(denoise)
    if ksampler:
        minimax["ksampler"] = ksampler
    if minimax:
        payload["minimax_music3"] = minimax

    flashsr: Dict[str, Any] = dict(payload.get("flashsr") or {})
    flashsr_settings = _parse_object(flashsr_settings_json, "flashsr_settings_json")
    if flashsr_settings:
        flashsr["settings"] = flashsr_settings
    pre_settings = _parse_object(pre_settings_json, "pre_settings_json")
    if pre_preset or pre_settings:
        flashsr["pre_lowpass"] = {
            "preset": (pre_preset or "").strip(),
            "settings": pre_settings,
        }
    post_settings = _parse_object(post_settings_json, "post_settings_json")
    if post_preset or post_settings:
        flashsr["post_lowpass"] = {
            "preset": (post_preset or "").strip(),
            "settings": post_settings,
        }
    hybrid = _parse_object(hybrid_crossover_json, "hybrid_crossover_json")
    if hybrid:
        flashsr["hybrid_crossover"] = hybrid
    hf_repair = _parse_object(hf_repair_json, "hf_repair_json")
    if hf_repair:
        flashsr["hf_cymbal_shimmer_repair"] = hf_repair
    if flashsr:
        payload["flashsr"] = flashsr

    declip = _parse_object(declip_json, "declip_json")
    if declip:
        payload.setdefault("restoration", {})["declip"] = declip

    release_prep = _parse_object(release_prep_json, "release_prep_json")
    if release_prep:
        payload["release_prep"] = release_prep

    return payload


class MiniMaxSaveProductionJSON:
    """Write one final, canonical configuration JSON after all song files exist."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "configuration_prefix": ("STRING", {"forceInput": True}),
                "audio_tags_json": ("STRING", {"forceInput": True}),
                "title": ("STRING", {"forceInput": True}),
                "original_audio_save_json": ("STRING", {"forceInput": True}),
                "release_flac_save_json": ("STRING", {"forceInput": True}),
                "release_mp3_save_json": ("STRING", {"forceInput": True}),
                "artwork_path": ("STRING", {"forceInput": True}),
                "collision_mode": (["auto_increment", "overwrite", "error_if_exists"], {"default": "auto_increment"}),
                "filename_mode": (["album - title", "title only", "prefix as provided"], {"default": "album - title"}),
                "create_directories": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                # Legacy payload from the pre-2.0.0 song-metadata node (used as
                # the base; direct inputs below overlay it).
                "metadata_json": ("STRING", {"forceInput": True}),
                # LLM stage
                "llm_system_prompt": ("STRING", {"forceInput": True}),
                "llm_user_prompt": ("STRING", {"forceInput": True}),
                "llm_output": ("STRING", {"forceInput": True}),
                "llm_status": ("STRING", {"forceInput": True}),
                "llm_thinking": ("STRING", {"forceInput": True}),
                "structured_summary_json": ("STRING", {"forceInput": True}),
                # Parsed prompt sections / provenance
                "caption": ("STRING", {"forceInput": True}),
                "lyrics": ("STRING", {"forceInput": True}),
                "image_prompt": ("STRING", {"forceInput": True}),
                "source_name": ("STRING", {"forceInput": True}),
                "source_path": ("STRING", {"forceInput": True}),
                "prompt_origin": ("STRING", {"forceInput": True}),
                "prompt_provenance_json": ("STRING", {"forceInput": True}),
                "generation_seed": ("INT", {"forceInput": True}),
                "run_index": ("INT", {"forceInput": True}),
                "variant_count": ("INT", {"forceInput": True}),
                # MiniMax Music 3 generation settings
                "max_duration": ("FLOAT", {"forceInput": True}),
                "text_seed": ("INT", {"forceInput": True}),
                "text_cfg_scale": ("FLOAT", {"forceInput": True}),
                "text_top_k": ("INT", {"forceInput": True}),
                "ksampler_seed": ("INT", {"forceInput": True}),
                "ksampler_steps": ("INT", {"forceInput": True}),
                "ksampler_cfg": ("FLOAT", {"forceInput": True}),
                "denoise": ("FLOAT", {"forceInput": True}),
                # Audio processing reports
                "flashsr_settings_json": ("STRING", {"forceInput": True}),
                "pre_preset": ("STRING", {"forceInput": True}),
                "pre_settings_json": ("STRING", {"forceInput": True}),
                "post_preset": ("STRING", {"forceInput": True}),
                "post_settings_json": ("STRING", {"forceInput": True}),
                "hybrid_crossover_json": ("STRING", {"forceInput": True}),
                "hf_repair_json": ("STRING", {"forceInput": True}),
                "declip_json": ("STRING", {"forceInput": True}),
                "release_prep_json": ("STRING", {"forceInput": True}),
                "workflow_name": ("STRING", {"default": DEFAULT_WORKFLOW_NAME, "multiline": False}),
                # Since 2.0.4: the MiniMax prompt report (Markdown) is written
                # next to the canonical JSON with the same basename.
                "minimax_prompt_md": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("saved_path", "configuration_json")
    FUNCTION = "save"
    CATEGORY = "MiniMax Music Production Toolkit/save"
    OUTPUT_NODE = True

    def save(
        self,
        configuration_prefix: str,
        audio_tags_json: str,
        title: str,
        original_audio_save_json: str,
        release_flac_save_json: str,
        release_mp3_save_json: str,
        artwork_path: str,
        collision_mode: str = "auto_increment",
        filename_mode: str = "album - title",
        create_directories: bool = True,
        metadata_json: str = "",
        llm_system_prompt: str = "",
        llm_user_prompt: str = "",
        llm_output: str = "",
        llm_status: str = "",
        llm_thinking: str = "",
        structured_summary_json: str = "",
        caption: str = "",
        lyrics: str = "",
        image_prompt: str = "",
        source_name: str = "",
        source_path: str = "",
        prompt_origin: str = "",
        prompt_provenance_json: str = "",
        generation_seed: Optional[int] = None,
        run_index: Optional[int] = None,
        variant_count: Optional[int] = None,
        max_duration: Optional[float] = None,
        text_seed: Optional[int] = None,
        text_cfg_scale: Optional[float] = None,
        text_top_k: Optional[int] = None,
        ksampler_seed: Optional[int] = None,
        ksampler_steps: Optional[int] = None,
        ksampler_cfg: Optional[float] = None,
        denoise: Optional[float] = None,
        flashsr_settings_json: str = "",
        pre_preset: str = "",
        pre_settings_json: str = "",
        post_preset: str = "",
        post_settings_json: str = "",
        hybrid_crossover_json: str = "",
        hf_repair_json: str = "",
        declip_json: str = "",
        release_prep_json: str = "",
        workflow_name: str = DEFAULT_WORKFLOW_NAME,
        minimax_prompt_md: str = "",
    ):
        metadata = _parse_object(metadata_json, "metadata_json")
        payload = _generation_metadata(
            metadata,
            llm_system_prompt=llm_system_prompt,
            llm_user_prompt=llm_user_prompt,
            llm_output=llm_output,
            llm_status=llm_status,
            llm_thinking=llm_thinking,
            structured_summary_json=structured_summary_json,
            caption=caption,
            lyrics=lyrics,
            image_prompt=image_prompt,
            source_name=source_name,
            source_path=source_path,
            prompt_origin=prompt_origin,
            prompt_provenance_json=prompt_provenance_json,
            generation_seed=generation_seed,
            run_index=run_index,
            variant_count=variant_count,
            max_duration=max_duration,
            text_seed=text_seed,
            text_cfg_scale=text_cfg_scale,
            text_top_k=text_top_k,
            ksampler_seed=ksampler_seed,
            ksampler_steps=ksampler_steps,
            ksampler_cfg=ksampler_cfg,
            denoise=denoise,
            flashsr_settings_json=flashsr_settings_json,
            pre_preset=pre_preset,
            pre_settings_json=pre_settings_json,
            post_preset=post_preset,
            post_settings_json=post_settings_json,
            hybrid_crossover_json=hybrid_crossover_json,
            hf_repair_json=hf_repair_json,
            declip_json=declip_json,
            release_prep_json=release_prep_json,
            workflow_name=workflow_name,
        )
        audio_tags = _parse_object(audio_tags_json, "audio_tags_json")

        resolved_prefix = _resolve_prefix(configuration_prefix)
        resolved_prefix = apply_filename_mode(
            resolved_prefix, audio_tags, title, filename_mode, error_prefix="Save Production JSON"
        )
        directory = os.path.dirname(resolved_prefix)
        if directory and not os.path.exists(directory):
            if create_directories:
                os.makedirs(directory, exist_ok=True)
            else:
                raise FileNotFoundError(f"Save Production JSON: directory does not exist: {directory}")

        target = _pick_path(resolved_prefix, "json", collision_mode)

        if title and not payload.get("title"):
            payload["title"] = title
        if audio_tags:
            payload["standard_audio_tags"] = audio_tags

        outputs = {
            "original_audio": _artifact_from_save_info(original_audio_save_json, "original_audio_save_json"),
            "release_flac": _artifact_from_save_info(release_flac_save_json, "release_flac_save_json"),
            "release_mp3": _artifact_from_save_info(release_mp3_save_json, "release_mp3_save_json"),
            "artwork": {
                "path": os.path.abspath(artwork_path) if (artwork_path or "").strip() else "",
                "file": os.path.basename(artwork_path) if (artwork_path or "").strip() else "",
            },
            "configuration": {
                "path": os.path.abspath(target),
                "file": os.path.basename(target),
                "filename_mode": str(filename_mode),
            },
        }

        # The MiniMax prompt report is written as a Markdown file beside the
        # canonical JSON, using exactly the same basename (Album - Title.md).
        markdown_text = (minimax_prompt_md or "").strip()
        prompt_report_target: Optional[str] = None
        if markdown_text:
            prompt_report_target = str(Path(target).with_suffix(".md"))
            markdown_tmp = prompt_report_target + ".tmp"
            try:
                with open(markdown_tmp, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(markdown_text)
                    if not markdown_text.endswith("\n"):
                        handle.write("\n")
                os.replace(markdown_tmp, prompt_report_target)
            except Exception:
                try:
                    if os.path.exists(markdown_tmp):
                        os.remove(markdown_tmp)
                except OSError:
                    pass
                raise
            outputs["prompt_report"] = {
                "path": os.path.abspath(prompt_report_target),
                "file": os.path.basename(prompt_report_target),
            }
            LOGGER.info("Saved MiniMax prompt report: %s", prompt_report_target)
        payload["outputs"] = outputs

        tmp = target + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(tmp, target)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise

        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        LOGGER.info("Saved canonical production JSON: %s", target)
        return (target, rendered)


NODE_CLASS_MAPPINGS = {"MiniMaxSaveProductionJSON": MiniMaxSaveProductionJSON}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxSaveProductionJSON": "Save Production JSON"}
