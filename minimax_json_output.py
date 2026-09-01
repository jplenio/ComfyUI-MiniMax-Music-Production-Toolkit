from __future__ import annotations

"""Central production-configuration JSON writer.

The recommended workflow writes one canonical JSON record per song into
its own configurable directory instead of duplicating sidecar JSON files beside
every audio encoding.  The node depends on the audio/artwork save results, which
makes it execute only after those artifacts have been written successfully.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

from .filename_utils import apply_filename_mode
from .toolkit_logging import get_logger
from .save_audio_smart_prefix import _pick_path, _resolve_prefix

LOGGER = get_logger("production_json")


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


class MiniMaxSaveProductionJSON:
    """Write one final, canonical configuration JSON after all song files exist."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "metadata_json": ("STRING", {"forceInput": True}),
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
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("saved_path", "configuration_json")
    FUNCTION = "save"
    CATEGORY = "MiniMax Music Production Toolkit/save"
    OUTPUT_NODE = True

    def save(
        self,
        metadata_json: str,
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
    ):
        metadata = _parse_object(metadata_json, "metadata_json")
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

        payload = dict(metadata)
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
