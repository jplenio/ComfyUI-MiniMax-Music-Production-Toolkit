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

from .file_writes import reserve_target, staged_write, write_text_staged
from .filename_utils import apply_filename_mode
from .metadata_schema import CURRENT_PRODUCTION_METADATA_SCHEMA
from .production_metadata import (
    DEFAULT_WORKFLOW_NAME,
    build_generation_metadata,
    overlay,
    parse_object,
)
from .output_paths import pick_path as _pick_path_impl, resolve_prefix as _resolve_prefix_impl
from .toolkit_logging import get_logger

LOGGER = get_logger("production_json")



def _resolve_prefix(prefix: str) -> str:
    """Resolve the configuration prefix with this node's error label."""
    return _resolve_prefix_impl(prefix, error_prefix="Save Production JSON")


def _pick_path(prefix: str, ext: str, collision_mode: str, exists=None) -> str:
    """Select the artifact path with this node's error label."""
    return _pick_path_impl(prefix, ext, collision_mode, error_prefix="Save Production JSON", exists=exists)


def _pair_is_taken(candidate: str) -> bool:
    """Report a JSON target as taken when its Markdown companion is taken too.

    A standalone ``Album - Title.md`` left by another producer must not be
    silently overwritten by the canonical JSON's companion.  The predicate uses
    the same "exists already" semantics as ``output_paths.pick_path``.
    """
    return (
        os.path.exists(candidate)
        or os.path.exists(str(Path(candidate).with_suffix(".md")))
    )


def _artifact_from_save_info(text: str, fallback_label: str) -> Dict[str, Any]:
    """Da zum Saver-Output-Format gehörender Adapter bleibt im Node."""
    info = _parse_object(text, fallback_label)
    # SaveAudioSmartPrefix emits a stable object. Preserve it as-is so future
    # fields can be added without changing this aggregation node.
    return info


def _parse_object(text: str, label: str) -> Dict[str, Any]:
    """Compatibility wrapper around :func:`production_metadata.parse_object`."""
    return parse_object(text, label)


def _overlay(base: Dict[str, Any], key: str, value: Any) -> None:
    """Compatibility wrapper around :func:`production_metadata.overlay`."""
    return overlay(base, key, value)


def _generation_metadata(*args, **kwargs) -> Dict[str, Any]:
    """Compatibility wrapper around :func:`production_metadata.build_generation_metadata`."""
    return build_generation_metadata(*args, **kwargs)


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
                # V01 additive reports.  The EQ / auto-EQ / mastering nodes emit
                # self-describing JSON (``minimax_eq_report_v1``,
                # ``minimax_auto_eq_report_v1``, ``minimax_mastering_v1``), and
                # the runtime stages report what they actually used.  All seven
                # are optional and appended at the end on purpose: a stored
                # workflow keeps its existing input slots and widget values.
                "eq_report_json": ("STRING", {"forceInput": True}),
                "auto_eq_analysis_json": ("STRING", {"forceInput": True}),
                "mastering_json": ("STRING", {"forceInput": True}),
                "resource_profile_json": ("STRING", {"forceInput": True}),
                "llm_runtime_json": ("STRING", {"forceInput": True}),
                "model_identity_json": ("STRING", {"forceInput": True}),
                "template_version": ("STRING", {"forceInput": True}),
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
        eq_report_json: str = "",
        auto_eq_analysis_json: str = "",
        mastering_json: str = "",
        resource_profile_json: str = "",
        llm_runtime_json: str = "",
        model_identity_json: str = "",
        template_version: str = "",
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
            eq_report_json=eq_report_json,
            auto_eq_analysis_json=auto_eq_analysis_json,
            mastering_json=mastering_json,
            resource_profile_json=resource_profile_json,
            llm_runtime_json=llm_runtime_json,
            model_identity_json=model_identity_json,
            template_version=template_version,
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

        # The MiniMax prompt report is written as a Markdown file beside the
        # canonical JSON with exactly the same basename (Album - Title.md).
        markdown_text = (minimax_prompt_md or "").strip()

        # A standalone Markdown companion left by another producer must count as
        # a collision too - otherwise the JSON would take a free "Album - Title"
        # name and silently overwrite that Markdown.
        if markdown_text and collision_mode != "overwrite":
            target = _pick_path(
                resolved_prefix, "json", collision_mode, _pair_is_taken,
            )
        else:
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

        prompt_report_target: Optional[str] = None
        if markdown_text:
            prompt_report_target = str(Path(target).with_suffix(".md"))
            outputs["prompt_report"] = {
                "path": os.path.abspath(prompt_report_target),
                "file": os.path.basename(prompt_report_target),
            }
        payload["outputs"] = outputs

        # Publish the canonical JSON first and its Markdown companion second.
        # A filesystem offers no multi-file atomicity: this order guarantees a
        # companion file can never exist without its JSON, at the cost of a
        # possible JSON without its companion if the second write fails.  The
        # recorded path is part of the JSON, so it must be complete *before*
        # the payload is serialized.
        write_text_staged(
            target,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            reserve=lambda: reserve_target(resolved_prefix, "json", collision_mode, error_prefix="Save Production JSON"),
            error_prefix="Save Production JSON",
        )
        if prompt_report_target:
            body = markdown_text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
            body = body.replace("\n", "\r\n")
            write_text_staged(prompt_report_target, body, error_prefix="Save Production JSON")
            LOGGER.info("Saved MiniMax prompt report: %s", prompt_report_target)

        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        LOGGER.info("Saved canonical production JSON: %s", target)
        return (target, rendered)


NODE_CLASS_MAPPINGS = {"MiniMaxSaveProductionJSON": MiniMaxSaveProductionJSON}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxSaveProductionJSON": "Save Production JSON"}
