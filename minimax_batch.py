from __future__ import annotations

from .prompt_sources import (
    clean_source_name as _clean_source_name_impl,
    iter_prompt_files,
    iter_variants,
    new_seed as _new_seed_impl,
    normalize_extensions,
    read_prompt_text as _read_text_impl,
    resolve_prompt_directory as _resolve_prompt_directory_impl,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("minimax_batch")

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SECTION_RE = re.compile(r"^\s*\[(Title|Caption|Lyrics|Count|Song-Count)\]\s*$", re.IGNORECASE)


def _resolve_prompt_directory(value: str) -> Path:
    """Compatibility wrapper around :func:`prompt_sources.resolve_prompt_directory`."""
    return _resolve_prompt_directory_impl(value, error_prefix="MiniMax Prompt Batch Loader")


def _read_text(path: Path) -> str:
    """Compatibility wrapper around :func:`prompt_sources.read_prompt_text`."""
    return _read_text_impl(path)


def _clean_source_name(value: str) -> str:
    """Compatibility wrapper around :func:`prompt_sources.clean_source_name`."""
    return _clean_source_name_impl(value)


def _new_seed() -> int:
    """Compatibility wrapper around :func:`prompt_sources.new_seed`."""
    return _new_seed_impl()


def _parse_prompt_file(path: Path) -> Dict[str, Any]:
    text = _read_text(path).replace("\r\n", "\n").replace("\r", "\n")
    sections: Dict[str, List[str]] = {"title": [], "caption": [], "lyrics": [], "count": []}
    current = None

    for line in text.split("\n"):
        m = _SECTION_RE.match(line)
        if m:
            key = m.group(1).lower()
            if key == "song-count":
                key = "count"
            current = key
            continue
        if current is not None:
            sections[current].append(line)

    caption = "\n".join(sections["caption"]).strip()
    lyrics = "\n".join(sections["lyrics"]).strip()
    title = "\n".join(sections["title"]).strip()
    count_text = "\n".join(sections["count"]).strip()

    missing = []
    if not caption:
        missing.append("[Caption]")
    if not lyrics:
        missing.append("[Lyrics]")
    if missing:
        raise ValueError(f"{path.name}: missing or empty {' and '.join(missing)} section(s)")

    count_override = None
    if count_text:
        first = count_text.splitlines()[0].strip()
        try:
            count_override = int(first)
        except ValueError:
            raise ValueError(f"{path.name}: [Count] must contain an integer, got '{first}'")
        if count_override < 1 or count_override > 100:
            raise ValueError(f"{path.name}: [Count] must be between 1 and 100")

    return {
        "title": title or path.stem,
        "caption": caption,
        "lyrics": lyrics,
        "count_override": count_override,
        "source_name": path.stem,
        "source_path": str(path),
    }


class MiniMaxPromptBatchLoader:
    """Folder/manual prompt loader that emits ComfyUI list outputs for automatic mapping."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["folder", "manual"], {"default": "folder"}),
                "prompt_directory": ("STRING", {"default": "", "multiline": False}),
                "song_count": ("INT", {"default": 1, "min": 1, "max": 100, "step": 1}),
                "seed_mode": (["random_each_song", "increment_from_base"], {"default": "random_each_song"}),
                "base_seed": ("INT", {"default": 1, "min": 0, "max": 9223372036854775806, "step": 1}),
                "extensions": ("STRING", {"default": ".txt,.prompt,.md", "multiline": False}),
                "recursive": ("BOOLEAN", {"default": False}),
                "manual_title": ("STRING", {"default": "manual-song", "multiline": False}),
                "manual_caption": ("STRING", {"default": "", "multiline": True}),
                "manual_lyrics": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT", "INT", "STRING")
    RETURN_NAMES = ("caption", "lyrics", "title", "source_name", "seed", "run_index", "source_path")
    OUTPUT_IS_LIST = (True, True, True, True, True, True, True)
    FUNCTION = "load"
    CATEGORY = "MiniMax Music Production Toolkit/batch"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Prompt files and random seeds should be reevaluated every queued execution.
        return float("nan")

    def load(
        self,
        mode,
        prompt_directory,
        song_count,
        seed_mode,
        base_seed,
        extensions,
        recursive,
        manual_title,
        manual_caption,
        manual_lyrics,
    ):
        entries: List[Dict[str, Any]] = []

        if mode == "manual":
            caption = (manual_caption or "").strip()
            lyrics = (manual_lyrics or "").strip()
            if not caption:
                raise ValueError("MiniMax Prompt Batch Loader: manual_caption is empty.")
            if not lyrics:
                raise ValueError("MiniMax Prompt Batch Loader: manual_lyrics is empty.")
            title = (manual_title or "manual-song").strip() or "manual-song"
            entries.append({
                "title": title,
                "caption": caption,
                "lyrics": lyrics,
                "count_override": None,
                "source_name": _clean_source_name(title),
                "source_path": "<manual>",
            })
        else:
            directory = _resolve_prompt_directory(prompt_directory)
            if not directory.exists():
                raise FileNotFoundError(f"MiniMax Prompt Batch Loader: directory does not exist: {directory}")
            if not directory.is_dir():
                raise NotADirectoryError(f"MiniMax Prompt Batch Loader: not a directory: {directory}")

            allowed = normalize_extensions(extensions)
            if not allowed:
                raise ValueError("MiniMax Prompt Batch Loader: extensions list is empty.")

            files = iter_prompt_files(directory, allowed, recursive, relative_sort=True)
            if not files:
                raise ValueError(
                    f"MiniMax Prompt Batch Loader: no prompt files found in {directory} "
                    f"for extensions {sorted(allowed)}"
                )

            errors = []
            for p in files:
                try:
                    entries.append(_parse_prompt_file(p))
                except Exception as exc:
                    errors.append(str(exc))
            if errors:
                raise ValueError("MiniMax Prompt Batch Loader: invalid prompt file(s):\n- " + "\n- ".join(errors))

        captions: List[str] = []
        lyrics_list: List[str] = []
        titles: List[str] = []
        source_names: List[str] = []
        seeds: List[int] = []
        run_indices: List[int] = []
        source_paths: List[str] = []

        global_index = 0
        for entry, variant, _count, seed, global_index in iter_variants(
            entries,
            song_count=song_count,
            seed_mode=seed_mode,
            base_seed=base_seed,
            # Legacy strict count: an explicit [Count] of 0 produces no songs.
            count_of=lambda e: e["count_override"] if e["count_override"] is not None else int(song_count),
        ):
            captions.append(entry["caption"])
            lyrics_list.append(entry["lyrics"])
            titles.append(entry["title"])
            source_names.append(_clean_source_name(entry["source_name"]))
            seeds.append(seed)
            run_indices.append(variant)
            source_paths.append(entry["source_path"])

        LOGGER.info(
            "%d prompt file(s)/entry(ies), %d song generation(s), mode=%s, seed_mode=%s",
            len(entries), len(captions), mode, seed_mode,
        )
        return (captions, lyrics_list, titles, source_names, seeds, run_indices, source_paths)


class MiniMaxOutputPaths:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_name": ("STRING", {"forceInput": True}),
                "base_output": ("STRING", {"default": "audio_minimax3/%date:yyyy-MM-dd%/", "multiline": False}),
                "original_subdir": ("STRING", {"default": "org-32flac/", "multiline": False}),
                "sr_flac_subdir": ("STRING", {"default": "highres-44flac/", "multiline": False}),
                "sr_mp3_subdir": ("STRING", {"default": "highres-44mp3/", "multiline": False}),
                "artwork_subdir": ("STRING", {"default": "artwork/", "multiline": False}),
                "configuration_subdir": ("STRING", {"default": "log/", "multiline": False}),
            },
            "optional": {
                "run_index": ("INT", {"forceInput": True}),
                "variant_count": ("INT", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("original_prefix", "sr_flac_prefix", "sr_mp3_prefix", "artwork_prefix", "configuration_prefix")
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/batch"

    def _join(self, base: str, subdir: str, source: str) -> str:
        base = (base or "").strip().replace("\\", "/")
        subdir = (subdir or "").strip().replace("\\", "/")
        source = _clean_source_name(source)
        pieces = []
        if base:
            pieces.append(base.rstrip("/"))
        if subdir:
            pieces.append(subdir.strip("/"))
        pieces.append(source)
        return "/".join(pieces)

    def build(self, source_name, base_output, original_subdir, sr_flac_subdir, sr_mp3_subdir, artwork_subdir, configuration_subdir="log/", run_index=1, variant_count=1):
        # run_index / variant_count are retained as optional connected batch info
        # for workflow compatibility; the path prefixes no longer append a variant
        # suffix because the downstream savers rebuild the basename from Album +
        # Title via filename_mode.
        source = _clean_source_name(source_name)
        return (
            self._join(base_output, original_subdir, source),
            self._join(base_output, sr_flac_subdir, source),
            self._join(base_output, sr_mp3_subdir, source),
            self._join(base_output, artwork_subdir, source),
            self._join(base_output, configuration_subdir, source),
        )


NODE_CLASS_MAPPINGS = {
    "MiniMaxPromptBatchLoader": MiniMaxPromptBatchLoader,
    "MiniMaxOutputPaths": MiniMaxOutputPaths,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxPromptBatchLoader": "MiniMax Prompt Batch Loader",
    "MiniMaxOutputPaths": "MiniMax Output Paths",
}
