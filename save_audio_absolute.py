"""
Save Audio Absolute Path - ComfyUI custom node

Saves ComfyUI AUDIO directly to an arbitrary absolute directory.

Supported:
- FLAC: 16/24-bit PCM
- WAV: 16/24-bit PCM or 32-bit float
- MP3: LAME V0/V2 or fixed 192/256/320 kbps

Design goals:
- Absolute paths (including Windows drive paths and UNC paths).
- Optional automatic directory creation.
- Safe automatic file numbering.
- No hidden normalization by default.
- Preserves the AUDIO sample rate.
- Batch-safe: one file per batch element.
"""

from __future__ import annotations

from .audio_utils import validate_audio
from .ffmpeg_utils import (
    find_ffmpeg as _find_ffmpeg_impl,
    prepare_samples as _prepare_samples_impl,
    write_mp3 as _write_mp3_impl,
)
from .file_writes import staged_write
from .filename_utils import MAX_COMPONENT_LENGTH, truncate_to_utf16
from .toolkit_logging import get_logger

LOGGER = get_logger("save_audio_absolute")

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

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


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _validate_audio(audio: Any) -> Tuple[torch.Tensor, int]:
    """Delegates to :func:`audio_utils.validate_audio` (same messages/policy)."""
    return validate_audio(audio, error_label="Save Audio Absolute Path", template="separate", require_positive_rate=True)


def _clean_filename(filename: str) -> str:
    name = (filename or "").strip()

    # Users sometimes enter an extension. The node adds the selected extension itself.
    lower = name.lower()
    for ext in (".flac", ".wav", ".mp3"):
        if lower.endswith(ext):
            name = name[:-len(ext)]
            break

    # filename is deliberately a file name, not a path. The directory has its own input.
    name = _INVALID_FILENAME_CHARS.sub("_", name)
    name = name.strip(" .")

    # Keep the component inside the filesystem's UTF-16 component budget; the
    # extension stripping and the "audio" fallback above stay unchanged, so
    # ordinary names keep their existing paths.
    if len(name.encode("utf-16-le")) // 2 > MAX_COMPONENT_LENGTH:
        name = truncate_to_utf16(name, MAX_COMPONENT_LENGTH).strip(" .")

    if not name:
        name = "audio"

    # Windows reserved device names.
    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if name.upper() in reserved:
        name = "_" + name

    return name


def _expand_directory(directory: str) -> str:
    directory = os.path.expandvars(os.path.expanduser((directory or "").strip()))
    if not directory:
        raise ValueError("Save Audio Absolute Path: absolute_directory is empty.")
    if not os.path.isabs(directory):
        raise ValueError(
            "Save Audio Absolute Path: absolute_directory must be an absolute path, "
            r"for example D:\Music\MiniMax\Preview or \\server\share\folder."
        )
    return os.path.normpath(directory)


def _pick_output_path(
    directory: str,
    base_name: str,
    extension: str,
    collision_mode: str,
) -> str:
    candidate = os.path.join(directory, f"{base_name}.{extension}")

    if collision_mode == "overwrite":
        return candidate

    if collision_mode == "error_if_exists":
        if os.path.exists(candidate):
            raise FileExistsError(f"Save Audio Absolute Path: file already exists: {candidate}")
        return candidate

    if collision_mode != "auto_increment":
        raise ValueError(f"Save Audio Absolute Path: unknown collision_mode '{collision_mode}'.")

    if not os.path.exists(candidate):
        return candidate

    i = 1
    while True:
        numbered = os.path.join(directory, f"{base_name}_{i:03d}.{extension}")
        if not os.path.exists(numbered):
            return numbered
        i += 1
        if i > 999999:
            raise RuntimeError("Save Audio Absolute Path: could not find a free auto-increment filename.")


def _find_ffmpeg() -> str:
    # Prefer the user's/system FFmpeg when available, then the imageio-ffmpeg
    # fallback installed by install_requirements.bat.
    return _find_ffmpeg_impl(
        "Save Audio Absolute Path: MP3 output requires FFmpeg. "
        "Run install_requirements.bat; it installs imageio-ffmpeg as a fallback."
    )


def _subtype_for_flac(bit_depth: str) -> str:
    return {
        "24-bit": "PCM_24",
        "16-bit": "PCM_16",
    }[bit_depth]


def _subtype_for_wav(bit_depth: str) -> str:
    return {
        "32-bit float": "FLOAT",
        "24-bit": "PCM_24",
        "16-bit": "PCM_16",
    }[bit_depth]


def _prepare_samples(samples: np.ndarray, peak_handling: str) -> Tuple[np.ndarray, float, float]:
    return _prepare_samples_impl(
        samples,
        peak_handling,
        unknown_peak_message="Save Audio Absolute Path: unknown peak_handling '{peak_handling}'.",
    )


def _write_mp3(
    target: str,
    data_tc: np.ndarray,
    sample_rate: int,
    mp3_quality: str,
) -> None:
    """Compatibility wrapper around :func:`ffmpeg_utils.write_mp3`.

    This saver keeps its historic ``-map_metadata -1``: it deliberately strips
    any pre-existing container metadata before writing the file.
    """
    _write_mp3_impl(
        target,
        data_tc,
        sample_rate,
        mp3_quality,
        not_found_message=(
            "Save Audio Absolute Path: MP3 output requires FFmpeg. "
            "Run install_requirements.bat; it installs imageio-ffmpeg as a fallback."
        ),
        failure_message="Save Audio Absolute Path: FFmpeg MP3 encoding failed:",
        invalid_quality_message=f"Save Audio Absolute Path: unknown MP3 quality '{mp3_quality}'.",
        strip_metadata=True,
        soundfile_missing_message=(
            "Save Audio Absolute Path requires soundfile. "
            f"Original import error: {_SOUNDFILE_IMPORT_ERROR}"
        ),
    )


class SaveAudioAbsolutePath:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "absolute_directory": (
                    "STRING",
                    {
                        "default": r"D:\Music\MiniMax\Preview",
                        "multiline": False,
                    },
                ),
                "filename": (
                    "STRING",
                    {
                        "default": "track",
                        "multiline": False,
                    },
                ),
                "format": (
                    ["mp3", "flac", "wav"],
                    {"default": "mp3"},
                ),
                "collision_mode": (
                    ["auto_increment", "overwrite", "error_if_exists"],
                    {"default": "auto_increment"},
                ),
                "create_directories": (
                    "BOOLEAN",
                    {"default": True},
                ),
                "mp3_quality": (
                    [
                        "V0 (~245 kbps)",
                        "V2 (~190 kbps)",
                        "320 kbps",
                        "256 kbps",
                        "192 kbps",
                    ],
                    {"default": "V0 (~245 kbps)"},
                ),
                "flac_bit_depth": (
                    ["24-bit", "16-bit"],
                    {"default": "24-bit"},
                ),
                "wav_bit_depth": (
                    ["32-bit float", "24-bit", "16-bit"],
                    {"default": "32-bit float"},
                ),
                "peak_handling": (
                    ["leave_unchanged", "normalize_only_if_clipping"],
                    {"default": "leave_unchanged"},
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_paths",)
    FUNCTION = "save"
    CATEGORY = "MiniMax Music Production Toolkit/save"
    OUTPUT_NODE = True

    def save(
        self,
        audio,
        absolute_directory,
        filename,
        format,
        collision_mode,
        create_directories,
        mp3_quality,
        flac_bit_depth,
        wav_bit_depth,
        peak_handling,
    ):
        if sf is None:
            raise RuntimeError(
                "Save Audio Absolute Path requires soundfile. "
                "Run install_requirements.bat. "
                f"Original import error: {_SOUNDFILE_IMPORT_ERROR}"
            )

        waveform, sample_rate = _validate_audio(audio)
        directory = _expand_directory(absolute_directory)

        if os.path.exists(directory):
            if not os.path.isdir(directory):
                raise NotADirectoryError(
                    f"Save Audio Absolute Path: destination exists but is not a directory: {directory}"
                )
        elif create_directories:
            os.makedirs(directory, exist_ok=True)
        else:
            raise FileNotFoundError(
                f"Save Audio Absolute Path: destination directory does not exist: {directory}"
            )

        base = _clean_filename(filename)
        fmt = format.lower()
        if fmt not in ("mp3", "flac", "wav"):
            raise ValueError(f"Save Audio Absolute Path: unsupported format '{format}'.")

        # CPU float32; shape remains [B,C,T].
        x = waveform.detach().to(device="cpu", dtype=torch.float32).numpy()

        saved: List[str] = []
        warnings: List[str] = []

        batch_size = x.shape[0]
        for b in range(batch_size):
            batch_base = base if batch_size == 1 else f"{base}_b{b + 1:03d}"
            target = _pick_output_path(directory, batch_base, fmt, collision_mode)

            samples_ct, peak, applied_gain = _prepare_samples(x[b], peak_handling)
            data_tc = np.ascontiguousarray(samples_ct.T, dtype=np.float32)

            if peak > 1.0 and peak_handling == "leave_unchanged":
                warnings.append(
                    f"batch {b + 1}: peak={peak:.4f} > 1.0; PCM FLAC/WAV or MP3 encoding may clip"
                )

            # Stage the encode in the same directory: the final path only ever
            # receives a finished file, and the collision policy is re-checked
            # at publication so a name taken meanwhile is not overwritten.
            with staged_write(
                target,
                reserve=lambda: _pick_output_path(directory, batch_base, fmt, collision_mode),
                error_prefix="Save Audio Absolute Path",
            ) as staged:
                if fmt == "flac":
                    sf.write(
                        staged.staging,
                        data_tc,
                        sample_rate,
                        format="FLAC",
                        subtype=_subtype_for_flac(flac_bit_depth),
                    )
                elif fmt == "wav":
                    sf.write(
                        staged.staging,
                        data_tc,
                        sample_rate,
                        format="WAV",
                        subtype=_subtype_for_wav(wav_bit_depth),
                    )
                else:
                    _write_mp3(
                        staged.staging,
                        data_tc,
                        sample_rate,
                        mp3_quality,
                    )
            target = staged.target

            saved.append(target)
            LOGGER.info(
                "Saved %s | sr=%d | channels=%d | peak=%.4f | gain=%.6f",
                target, sample_rate, data_tc.shape[1] if data_tc.ndim == 2 else 1, peak, applied_gain,
            )

        if warnings:
            LOGGER.warning("%s", " | ".join(warnings))

        return ("\n".join(saved),)


NODE_CLASS_MAPPINGS = {
    "SaveAudioAbsolutePath": SaveAudioAbsolutePath,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveAudioAbsolutePath": "Save Audio Absolute Path",
}
