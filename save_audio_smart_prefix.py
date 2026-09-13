from __future__ import annotations

from .audio_utils import validate_audio, require_finite_samples
from .audio_file_io import write_soundfile
from .ffmpeg_utils import (
    find_ffmpeg as _find_ffmpeg_impl,
    prepare_samples as _prepare_samples_impl,
    write_mp3 as _write_mp3_impl,
)
from .audio_tags import (
    CoverCache as _CoverCache,
    _load_cover_bytes as _load_cover_bytes_impl,
    _write_standard_tags as _write_standard_tags_impl,
)
from .file_writes import reserve_target as _reserve_target, staged_write
from .filename_utils import apply_filename_mode
from .output_paths import (
    expand_date_macros as _output_expand_date_macros,
    is_abs_any_platform as _output_is_abs_any_platform,
    javaish_date_to_strftime as _output_javaish_date_to_strftime,
    pick_path as _pick_path_impl,
    preview_output_files as _preview_output_files_impl,
    resolve_prefix as _resolve_prefix_impl,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("save_audio_smart_prefix")

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
try:
    import torch  # type: ignore
except ImportError:  # torch ships with ComfyUI; absent only in bare CI/test environments
    torch = None  # type: ignore[assignment]

try:
    import soundfile as sf
except Exception as exc:
    sf = None
    _SOUNDFILE_IMPORT_ERROR = exc
else:
    _SOUNDFILE_IMPORT_ERROR = None


def _validate_audio(audio: Any) -> Tuple[torch.Tensor, int]:
    """Delegates to :func:`audio_utils.validate_audio` (same messages/policy)."""
    return validate_audio(audio, error_label="Save Audio Smart Prefix", template="compact", require_positive_rate=True)


def _javaish_date_to_strftime(pattern: str) -> str:
    return _output_javaish_date_to_strftime(pattern)


def _expand_date_macros(value: str) -> str:
    return _output_expand_date_macros(value)


def _is_abs_any_platform(path: str) -> bool:
    return _output_is_abs_any_platform(path)


def _comfy_output_dir() -> str:
    from .output_paths import comfy_output_dir

    return comfy_output_dir()


def _resolve_prefix(prefix: str) -> str:
    """Compatibility wrapper around :func:`output_paths.resolve_prefix`."""
    return _resolve_prefix_impl(prefix, error_prefix="Save Audio Smart Prefix")


def _pick_path(prefix: str, ext: str, collision_mode: str) -> str:
    """Compatibility wrapper around :func:`output_paths.pick_path`."""
    return _pick_path_impl(prefix, ext, collision_mode, error_prefix="Save Audio Smart Prefix")



def _find_ffmpeg() -> str:
    return _find_ffmpeg_impl(
        "Save Audio Smart Prefix: MP3 needs FFmpeg. Run install_requirements.bat."
    )


def _prepare(samples: np.ndarray, peak_handling: str):
    return _prepare_samples_impl(
        samples,
        peak_handling,
        unknown_peak_message="Save Audio Smart Prefix: unknown peak_handling '{peak_handling}'.",
    )


def _write_mp3(target: str, data_tc: np.ndarray, sample_rate: int, quality: str) -> None:
    """Compatibility wrapper around :func:`ffmpeg_utils.write_mp3`."""
    _write_mp3_impl(
        target,
        data_tc,
        sample_rate,
        quality,
        not_found_message="Save Audio Smart Prefix: MP3 needs FFmpeg. Run install_requirements.bat.",
        failure_message="Save Audio Smart Prefix: FFmpeg failed:",
        invalid_quality_message=f"Save Audio Smart Prefix: invalid MP3 quality '{quality}'.",
        strip_metadata=False,
    )


def _parse_json_maybe(text: str) -> Dict[str, Any]:
    if not (text or "").strip():
        return {}
    value = json.loads(text)
    return value if isinstance(value, dict) else {"value": value}


def _write_sidecar(target: str, meta: Dict[str, Any], audio_tags: Dict[str, Any], fmt: str, sample_rate: int, peak: float, gain: float, filename_mode: str = "album - title", embedded_cover_size: int = 512) -> str:
    payload = dict(meta) if isinstance(meta, dict) else {"metadata": meta}
    if audio_tags:
        payload["standard_audio_tags"] = dict(audio_tags)
    payload["output"] = {
        "audio_path": os.path.abspath(target),
        "audio_file": os.path.basename(target),
        "format": fmt,
        "sample_rate": int(sample_rate),
        "peak_before_save": float(peak),
        "applied_gain": float(gain),
        "filename_mode": str(filename_mode),
        "embedded_cover_size": int(embedded_cover_size),
    }
    sidecar = os.path.splitext(target)[0] + ".json"
    tmp = sidecar + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, sidecar)
    return sidecar


def _load_cover_bytes(path: str, target_side: int = 512) -> bytes:
    """Compatibility wrapper around :func:`audio_tags._load_cover_bytes`."""
    return _load_cover_bytes_impl(path, target_side)


def _write_standard_tags(
    target: str,
    fmt: str,
    tags_data: Dict[str, Any],
    cover_image_path: str = "",
    embedded_cover_size: int = 512,
    *,
    cover_cache: Any = None,
) -> None:
    """Compatibility wrapper around :func:`audio_tags._write_standard_tags`."""
    return _write_standard_tags_impl(
        target, fmt, tags_data, cover_image_path, embedded_cover_size, cover_cache=cover_cache
    )


class SaveAudioSmartPrefix:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "filename_prefix": ("STRING", {"forceInput": True}),
                "format": (["flac", "mp3", "wav"], {"default": "flac"}),
                "collision_mode": (["auto_increment", "overwrite", "error_if_exists"], {"default": "auto_increment"}),
                "create_directories": ("BOOLEAN", {"default": True}),
                "mp3_quality": (["V0 (~245 kbps)", "V2 (~190 kbps)", "320 kbps", "256 kbps", "192 kbps"], {"default": "V0 (~245 kbps)"}),
                "flac_bit_depth": (["24-bit", "16-bit"], {"default": "24-bit"}),
                "wav_bit_depth": (["32-bit float", "24-bit", "16-bit"], {"default": "32-bit float"}),
                "peak_handling": (["leave_unchanged", "normalize_only_if_clipping"], {"default": "leave_unchanged"}),
                "write_json_sidecar": ("BOOLEAN", {"default": True}),
                "embed_basic_metadata": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "title": ("STRING", {"forceInput": True}),
                "metadata_json": ("STRING", {"forceInput": True}),
                "audio_tags_json": ("STRING", {"forceInput": True}),
                "cover_image_path": ("STRING", {"forceInput": True}),
                "filename_mode": (["album - title", "title only", "prefix as provided"], {"default": "album - title"}),
                "embedded_cover_size": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 64}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "saved_path", "metadata_path", "save_info_json")
    FUNCTION = "save"
    CATEGORY = "MiniMax Music Production Toolkit/save"
    OUTPUT_NODE = True

    def save(self, audio, filename_prefix, format, collision_mode, create_directories, mp3_quality,
             flac_bit_depth, wav_bit_depth, peak_handling, write_json_sidecar, embed_basic_metadata,
             title="", metadata_json="", audio_tags_json="", cover_image_path="", filename_mode="album - title", embedded_cover_size=512):
        if sf is None:
            raise RuntimeError(
                "Save Audio Smart Prefix requires soundfile. Run install_requirements.bat. "
                f"Original import error: {_SOUNDFILE_IMPORT_ERROR}"
            )

        waveform, sample_rate = _validate_audio(audio)
        resolved_prefix = _resolve_prefix(filename_prefix)
        directory = os.path.dirname(resolved_prefix)
        if directory and not os.path.exists(directory):
            if create_directories:
                os.makedirs(directory, exist_ok=True)
            else:
                raise FileNotFoundError(f"Save Audio Smart Prefix: directory does not exist: {directory}")

        x = waveform.detach().to(device="cpu", dtype=torch.float32).numpy()
        # Validate the entire batch before the first encode/peak calculation:
        # NaN poisons peak normalization and can cause libsndfile's FLAC writer
        # to return a short write, exposed by soundfile as a blank AssertionError.
        require_finite_samples(x, error_label="Save Audio Smart Prefix")
        saved: List[str] = []
        sidecars: List[str] = []
        save_infos: List[Dict[str, Any]] = []
        fmt = format.lower()
        base_meta = _parse_json_maybe(metadata_json) if (metadata_json or "").strip() else {}
        tags_meta = _parse_json_maybe(audio_tags_json) if (audio_tags_json or "").strip() else {}
        if title and not tags_meta.get("title"):
            tags_meta["title"] = title
        if title and not base_meta.get("title"):
            base_meta["title"] = title

        # Filesystem naming is independent from metadata TITLE. In the default
        # mode the directory comes from filename_prefix while the basename is
        # rebuilt from standard Album + Title tags.
        resolved_prefix = apply_filename_mode(
            resolved_prefix, tags_meta, title, filename_mode, error_prefix="Save Audio Smart Prefix"
        )
        embedded_cover_size = max(64, min(4096, int(embedded_cover_size or 512)))

        # One cover decode/resize per save invocation, shared by every batch
        # element and format; the cache never outlives this call.
        cover_cache = _CoverCache()

        for b in range(x.shape[0]):
            prefix = resolved_prefix if x.shape[0] == 1 else f"{resolved_prefix}_b{b+1:03d}"
            target = _pick_path(prefix, fmt, collision_mode)
            samples_ct, peak, gain = _prepare(x[b], peak_handling)
            data_tc = np.ascontiguousarray(samples_ct.T, dtype=np.float32)

            # Write into a same-directory staging file and add the tags there:
            # the final path only ever receives a finished, tagged file.  The
            # collision policy is re-checked at publication, so a name taken
            # while we were encoding is not overwritten.
            with staged_write(
                target,
                reserve=lambda: _reserve_target(prefix, fmt, collision_mode, error_prefix="Save Audio Smart Prefix"),
                error_prefix="Save Audio Smart Prefix",
            ) as staged:
                if fmt == "flac":
                    subtype = "PCM_24" if flac_bit_depth == "24-bit" else "PCM_16"
                    write_soundfile(sf, staged.staging, data_tc, sample_rate, format="FLAC", subtype=subtype,
                                    error_label="Save Audio Smart Prefix")
                elif fmt == "wav":
                    subtype = {"32-bit float": "FLOAT", "24-bit": "PCM_24", "16-bit": "PCM_16"}[wav_bit_depth]
                    write_soundfile(sf, staged.staging, data_tc, sample_rate, format="WAV", subtype=subtype,
                                    error_label="Save Audio Smart Prefix")
                elif fmt == "mp3":
                    _write_mp3(staged.staging, data_tc, sample_rate, mp3_quality)
                else:
                    raise ValueError(f"Save Audio Smart Prefix: unsupported format '{format}'.")

                if embed_basic_metadata and tags_meta:
                    _write_standard_tags(
                        staged.staging, fmt, tags_meta, cover_image_path, embedded_cover_size,
                        cover_cache=cover_cache,
                    )
            target = staged.target

            sidecar = ""
            if write_json_sidecar and base_meta:
                sidecar = _write_sidecar(target, base_meta, tags_meta, fmt, sample_rate, peak, gain, filename_mode, embedded_cover_size)
                sidecars.append(sidecar)

            saved.append(target)
            save_infos.append({
                "path": os.path.abspath(target),
                "file": os.path.basename(target),
                "format": fmt,
                "sample_rate": int(sample_rate),
                "peak_before_save": float(peak),
                "applied_gain": float(gain),
                "filename_mode": str(filename_mode),
                "embedded_cover_size": int(embedded_cover_size),
                "legacy_sidecar_path": os.path.abspath(sidecar) if sidecar else "",
            })
            LOGGER.info(
                "Saved %s | sr=%d | peak=%.4f | gain=%.6f%s",
                target, sample_rate, peak, gain, f" | metadata={sidecar}" if sidecar else "",
            )

        info_payload: Dict[str, Any]
        if len(save_infos) == 1:
            info_payload = save_infos[0]
        else:
            info_payload = {"batch": save_infos}
        return (audio, "\n".join(saved), "\n".join(sidecars), json.dumps(info_payload, ensure_ascii=False, indent=2))


def preview_output_files(
    filename_prefix: str,
    format: str,
    collision_mode: str = "auto_increment",
    filename_mode: str = "album - title",
    tags_meta: Optional[Dict[str, Any]] = None,
    title: str = "",
) -> Dict[str, Any]:
    """Compatibility wrapper around :func:`output_paths.preview_output_files`."""
    return _preview_output_files_impl(
        filename_prefix, format, collision_mode, filename_mode, tags_meta, title,
        error_prefix="Save Audio Smart Prefix",
    )


NODE_CLASS_MAPPINGS = {"SaveAudioSmartPrefix": SaveAudioSmartPrefix}
NODE_DISPLAY_NAME_MAPPINGS = {"SaveAudioSmartPrefix": "Save Audio Smart Prefix"}
