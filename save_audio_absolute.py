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

from .toolkit_logging import get_logger

LOGGER = get_logger("save_audio_absolute")

import os
import re
import shutil
import subprocess
import tempfile
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
    if not isinstance(audio, dict):
        raise ValueError("Save Audio Absolute Path: AUDIO input must be a ComfyUI AUDIO dictionary.")
    if "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError("Save Audio Absolute Path: AUDIO input needs 'waveform' and 'sample_rate'.")

    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])

    if not isinstance(waveform, torch.Tensor):
        raise ValueError("Save Audio Absolute Path: audio['waveform'] must be a torch.Tensor.")
    if waveform.ndim != 3:
        raise ValueError(
            f"Save Audio Absolute Path: expected waveform [B,C,T], got {tuple(waveform.shape)}."
        )
    if sample_rate <= 0:
        raise ValueError(f"Save Audio Absolute Path: invalid sample rate {sample_rate}.")

    return waveform, sample_rate


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
    # Prefer the user's/system FFmpeg when available.
    exe = shutil.which("ffmpeg")
    if exe:
        return exe

    # imageio-ffmpeg provides a bundled executable on common platforms.
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass

    raise RuntimeError(
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
    samples = np.asarray(samples, dtype=np.float32)
    input_peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    applied_gain = 1.0

    if peak_handling == "normalize_only_if_clipping":
        # Preserve the signal exactly when it is already below full scale.
        # Reduce gain only if clipping would otherwise occur.
        if input_peak > 1.0:
            applied_gain = 0.999 / input_peak
            samples = samples * np.float32(applied_gain)
    elif peak_handling == "leave_unchanged":
        pass
    else:
        raise ValueError(f"Save Audio Absolute Path: unknown peak_handling '{peak_handling}'.")

    return samples, input_peak, applied_gain


def _write_mp3(
    target: str,
    data_tc: np.ndarray,
    sample_rate: int,
    mp3_quality: str,
) -> None:
    if sf is None:
        raise RuntimeError(
            "Save Audio Absolute Path requires soundfile. "
            f"Original import error: {_SOUNDFILE_IMPORT_ERROR}"
        )

    ffmpeg = _find_ffmpeg()

    # Use a FLOAT WAV as lossless temporary interchange so the node does not
    # introduce an unnecessary 16-bit conversion before MP3 encoding.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = tmp.name

        sf.write(
            temp_path,
            data_tc,
            sample_rate,
            format="WAV",
            subtype="FLOAT",
        )

        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",
            "-y",
            "-i", temp_path,
            "-map_metadata", "-1",
            "-codec:a", "libmp3lame",
        ]

        if mp3_quality == "V0 (~245 kbps)":
            cmd += ["-q:a", "0"]
        elif mp3_quality == "V2 (~190 kbps)":
            cmd += ["-q:a", "2"]
        elif mp3_quality == "320 kbps":
            cmd += ["-b:a", "320k"]
        elif mp3_quality == "256 kbps":
            cmd += ["-b:a", "256k"]
        elif mp3_quality == "192 kbps":
            cmd += ["-b:a", "192k"]
        else:
            raise ValueError(f"Save Audio Absolute Path: unknown MP3 quality '{mp3_quality}'.")

        cmd += ["-id3v2_version", "3", target]

        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Save Audio Absolute Path: FFmpeg MP3 encoding failed:\n"
                + completed.stderr.strip()
            )
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


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

            if fmt == "flac":
                sf.write(
                    target,
                    data_tc,
                    sample_rate,
                    format="FLAC",
                    subtype=_subtype_for_flac(flac_bit_depth),
                )
            elif fmt == "wav":
                sf.write(
                    target,
                    data_tc,
                    sample_rate,
                    format="WAV",
                    subtype=_subtype_for_wav(wav_bit_depth),
                )
            else:
                _write_mp3(
                    target,
                    data_tc,
                    sample_rate,
                    mp3_quality,
                )

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
