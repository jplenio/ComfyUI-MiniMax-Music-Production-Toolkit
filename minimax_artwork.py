from __future__ import annotations

from .filename_utils import apply_filename_mode
from .toolkit_logging import get_logger

LOGGER = get_logger("minimax_artwork")

import json
import os
import re
from pathlib import Path
from typing import Any, Tuple

import numpy as np

try:
    from PIL import Image
except Exception as exc:
    Image = None
    _PIL_IMPORT_ERROR = exc
else:
    _PIL_IMPORT_ERROR = None

_DATE_RE = re.compile(r"%date:([^%]+)%")
_WIN_ABS_RE = re.compile(r"^[A-Za-z]:[\/]")


def _javaish_date_to_strftime(pattern: str) -> str:
    replacements = [
        ("yyyy", "%Y"), ("yy", "%y"),
        ("MM", "%m"), ("dd", "%d"),
        ("HH", "%H"), ("mm", "%M"), ("ss", "%S"),
    ]
    out = pattern
    for src, dst in replacements:
        out = out.replace(src, dst)
    return out


def _expand_date_macros(value: str) -> str:
    import datetime as _dt
    now = _dt.datetime.now()
    def repl(match):
        pattern = match.group(1)
        try:
            return now.strftime(_javaish_date_to_strftime(pattern))
        except Exception:
            return match.group(0)
    return _DATE_RE.sub(repl, value)


def _is_abs_any_platform(path: str) -> bool:
    return os.path.isabs(path) or bool(_WIN_ABS_RE.match(path)) or path.startswith("\\") or path.startswith("//")


def _comfy_output_dir() -> str:
    try:
        import folder_paths
        return folder_paths.get_output_directory()
    except Exception:
        return os.path.join(os.getcwd(), "output")


def _resolve_prefix(prefix: str) -> str:
    raw = (prefix or "").strip()
    if not raw:
        raise ValueError("Save Image Smart Prefix: filename_prefix is empty.")
    raw = _expand_date_macros(raw)
    raw = os.path.expanduser(os.path.expandvars(raw))
    if _is_abs_any_platform(raw):
        return os.path.normpath(raw)
    root = os.path.abspath(_comfy_output_dir())
    candidate = os.path.abspath(os.path.join(root, raw))
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise ValueError("Save Image Smart Prefix: relative filename_prefix may not escape the ComfyUI output directory.")
    except ValueError:
        raise ValueError("Save Image Smart Prefix: invalid relative filename_prefix.")
    return candidate


def _pick_path(prefix: str, ext: str, collision_mode: str) -> str:
    target = f"{prefix}.{ext}"
    if collision_mode == "overwrite":
        return target
    if collision_mode == "error_if_exists":
        if os.path.exists(target):
            raise FileExistsError(f"Save Image Smart Prefix: file exists: {target}")
        return target
    if collision_mode != "auto_increment":
        raise ValueError(f"Save Image Smart Prefix: invalid collision mode '{collision_mode}'.")
    if not os.path.exists(target):
        return target
    for i in range(1, 1_000_000):
        p = f"{prefix}_{i:03d}.{ext}"
        if not os.path.exists(p):
            return p
    raise RuntimeError("Save Image Smart Prefix: no free auto-increment filename found.")


def _image_tensor_to_pil(image_tensor: Any) -> Image.Image:
    if Image is None:
        raise RuntimeError(f"Save Image Smart Prefix requires Pillow. Original import error: {_PIL_IMPORT_ERROR}")
    import torch
    if not isinstance(image_tensor, torch.Tensor):
        raise ValueError("Save Image Smart Prefix: image must be a ComfyUI IMAGE tensor.")
    if image_tensor.ndim not in (3, 4):
        raise ValueError(f"Save Image Smart Prefix: expected [H,W,C] or [B,H,W,C], got {tuple(image_tensor.shape)}")
    if image_tensor.ndim == 4:
        image_tensor = image_tensor[0]
    arr = image_tensor.detach().cpu().numpy()
    arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    if arr.shape[-1] == 1:
        arr = arr[..., 0]
        return Image.fromarray(arr, mode='L')
    if arr.shape[-1] == 3:
        return Image.fromarray(arr, mode='RGB')
    if arr.shape[-1] == 4:
        return Image.fromarray(arr, mode='RGBA').convert('RGB')
    raise ValueError("Save Image Smart Prefix: unsupported channel count.")


class MiniMaxSquareImageSize:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "size_preset": (["256x256", "512x512", "1024x1024", "1536x1536", "2048x2048", "3072x3072", "3096x3096", "custom"], {"default": "512x512"}),
                "custom_size": ("INT", {"default": 768, "min": 64, "max": 4096, "step": 64}),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/artwork"

    def build(self, size_preset, custom_size):
        presets = {
            "256x256": 256,
            "512x512": 512,
            "1024x1024": 1024,
            "1536x1536": 1536,
            "2048x2048": 2048,
            "3072x3072": 3072,
            "3096x3096": 3096,
        }
        if size_preset in presets:
            return (presets[size_preset], presets[size_preset])
        # custom
        return (int(custom_size), int(custom_size))


class SaveImageSmartPrefix:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "filename_prefix": ("STRING", {"forceInput": True}),
                "collision_mode": (["auto_increment", "overwrite", "error_if_exists"], {"default": "auto_increment"}),
                "create_directories": ("BOOLEAN", {"default": True}),
                "jpeg_quality": ("INT", {"default": 95, "min": 50, "max": 100, "step": 1}),
            },
            "optional": {
                "title": ("STRING", {"forceInput": True}),
                "audio_tags_json": ("STRING", {"forceInput": True}),
                "filename_mode": (["album - title", "title only", "prefix as provided"], {"default": "album - title"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_path",)
    FUNCTION = "save"
    CATEGORY = "MiniMax Music Production Toolkit/artwork"
    OUTPUT_NODE = True

    def save(
        self, image, filename_prefix, collision_mode, create_directories, jpeg_quality,
        title="", audio_tags_json="", filename_mode="album - title",
    ):
        pil = _image_tensor_to_pil(image)
        prefix = _resolve_prefix(filename_prefix)

        tags_meta = {}
        if (audio_tags_json or "").strip():
            try:
                parsed = json.loads(audio_tags_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Save Image Smart Prefix: invalid audio_tags_json: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError("Save Image Smart Prefix: audio_tags_json must contain a JSON object.")
            tags_meta = parsed
        if title and not tags_meta.get("title"):
            tags_meta["title"] = title

        prefix = apply_filename_mode(
            prefix, tags_meta, title, filename_mode, error_prefix="Save Image Smart Prefix"
        )
        directory = os.path.dirname(prefix)
        if directory and not os.path.exists(directory):
            if create_directories:
                os.makedirs(directory, exist_ok=True)
            else:
                raise FileNotFoundError(f"Save Image Smart Prefix: directory does not exist: {directory}")
        target = _pick_path(prefix, 'jpg', collision_mode)
        pil.save(target, format='JPEG', quality=int(jpeg_quality), optimize=True, subsampling=0)
        LOGGER.info("Saved artwork: %s", target)
        return (target,)


NODE_CLASS_MAPPINGS = {
    "MiniMaxSquareImageSize": MiniMaxSquareImageSize,
    "SaveImageSmartPrefix": SaveImageSmartPrefix,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxSquareImageSize": "MiniMax Square Image Size",
    "SaveImageSmartPrefix": "Save Image Smart Prefix",
}
