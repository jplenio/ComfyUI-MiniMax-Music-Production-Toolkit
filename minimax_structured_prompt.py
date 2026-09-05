"""Structured Song Prompt node (MiniMaxStructuredPromptV20).

This node is the user-facing prompt control introduced in 2.0.0.  Instead of a
single free-form ``user_prompt`` text field, it exposes structured fields
(Genre, Tempo, Key, Lyrics, Language, Voice, Lyrics theme, Target length) plus
a "further description" area.  Prompt library files may *optionally* carry a
metadata block that prefills these fields when the file is selected; the user
can still override every field, and selecting ``custom`` leaves a part out of
the LLM prompt entirely.

The assembled user prompt is a short structured brief followed by the
description text, and is intended to be consumed by the integrated LLM chat
node (or any other LLM node that accepts user/system prompt strings).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .minimax_prompt_source import DEFAULT_SYSTEM_PROMPT, _clean_source_name
from .prompt_library import (
    PLACEHOLDER,
    PromptLibraryError,
    bundled_root,
    default_combo_values,
    prompt_selection_fingerprint,
    resolve_prompt,
)
from .prompt_metadata import (
    CUSTOM,
    LYRICS_CHOICES,
    STRUCTURED_FIELDS,
    assemble_structured_user_prompt,
    collect_file_field_values,
    merge_field_options,
    parse_prompt_front_matter,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("structured_prompt")

_SOURCES = ["manual", "bundled_library", "external_directory"]

# Cached aggregated option values; invalidated by the frontend route when the
# library changes while ComfyUI is running.
_library_options_cache = None
_library_options_version = 0


def invalidate_library_options_cache() -> None:
    """Refresh the aggregated combo options after prompt files changed on disk."""
    global _library_options_cache, _library_options_version
    _library_options_cache = None
    _library_options_version += 1


def _collect_options() -> dict:
    """Curated vocabulary plus unique values from all bundled user prompt files."""
    global _library_options_cache
    if _library_options_cache is not None:
        return _library_options_cache
    collected = {field: [] for field in STRUCTURED_FIELDS}
    try:
        root = bundled_root("user")
        collected = collect_file_field_values(p for p in root.rglob("*") if p.is_file())
    except Exception as exc:  # keep ComfyUI node discovery alive on broken installs
        LOGGER.warning("Could not aggregate bundled prompt metadata: %s", exc)
    options = merge_field_options(collected)
    if not options.get("lyrics"):
        options["lyrics"] = list(LYRICS_CHOICES)
    _library_options_cache = options
    return options


def _combo(field: str) -> list:
    values = [CUSTOM]
    values += [v for v in _collect_options().get(field, []) if v and v != CUSTOM]
    return values


def _safe_choices(default: list) -> list:
    # Keep the COMBO non-empty even if option discovery failed completely.
    return default or [CUSTOM]


class MiniMaxStructuredPromptV20:
    """Structured prompt control: metadata-prefilled fields assembled into one LLM user prompt."""

    @classmethod
    def INPUT_TYPES(cls):
        # "custom" as the first real choice of the prompt-file dropdown selects
        # the free mode: no prompt file is loaded and nothing is prefilled, so
        # the user composes every field themselves.  It must stay distinct from
        # the per-field "custom" sentinel (which omits a single field).
        user_file_options = [CUSTOM, *default_combo_values("user")]
        return {
            "required": {
                "user_prompt_source": (_SOURCES, {"default": "bundled_library"}),
                "user_prompt_directory": ("STRING", {"default": "", "multiline": False}),
                "user_prompt_file": (user_file_options, {"default": PLACEHOLDER}),
                "genre": (_safe_choices(_combo("genre")), {"default": CUSTOM}),
                "tempo": (_safe_choices(_combo("tempo")), {"default": CUSTOM}),
                "key": (_safe_choices(_combo("key")), {"default": CUSTOM}),
                "lyrics": (_safe_choices(_combo("lyrics")), {"default": CUSTOM}),
                "language": (_safe_choices(_combo("language")), {"default": CUSTOM}),
                "voice": (_safe_choices(_combo("voice")), {"default": CUSTOM}),
                "theme": (_safe_choices(_combo("theme")), {"default": CUSTOM}),
                "length": (_safe_choices(_combo("length")), {"default": CUSTOM}),
                "description_override": ("STRING", {"default": "", "multiline": True}),
                "system_prompt": ("STRING", {"default": DEFAULT_SYSTEM_PROMPT, "multiline": True}),
                "system_prompt_source": (_SOURCES, {"default": "manual"}),
                "system_prompt_directory": ("STRING", {"default": "", "multiline": False}),
                "system_prompt_file": (default_combo_values("system"), {"default": PLACEHOLDER}),
            },
            "optional": {
                "source_name_override": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("system_prompt", "user_prompt", "source_name", "structured_summary_json")
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/prompts"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        # Prompt file choices and structured combos can be populated dynamically,
        # so static COMBO membership checks must not reject runtime selections.
        return True

    @classmethod
    def IS_CHANGED(
        cls,
        user_prompt_source,
        user_prompt_directory,
        user_prompt_file,
        genre,
        tempo,
        key,
        lyrics,
        language,
        voice,
        theme,
        length,
        description_override,
        system_prompt,
        system_prompt_source,
        system_prompt_directory,
        system_prompt_file,
        source_name_override="",
        **kwargs,
    ):
        # "custom" selects free mode (no file is loaded); fingerprint it as such
        # instead of attempting to resolve a file literally named "custom".
        if (user_prompt_file or "").strip() == CUSTOM:
            user_fp = f"user:{CUSTOM}"
        else:
            user_fp = prompt_selection_fingerprint(
                "user", user_prompt_source, user_prompt_directory, user_prompt_file, description_override
            )
        # description_override is authoritative in file mode too, so editing it
        # must invalidate the cache even though the file fingerprint is unchanged.
        description_fp = hashlib.sha256((description_override or "").encode("utf-8", errors="replace")).hexdigest()[:16]
        user_fp = f"{user_fp}|desc={description_fp}"
        system_fp = prompt_selection_fingerprint(
            "system", system_prompt_source, system_prompt_directory, system_prompt_file, system_prompt
        )
        field_state = "|".join(
            f"{f}={v}" for f, v in (
                ("genre", genre), ("tempo", tempo), ("key", key), ("lyrics", lyrics),
                ("language", language), ("voice", voice), ("theme", theme), ("length", length),
            )
        )
        return f"{user_fp}|{system_fp}|{field_state}|source={source_name_override or ''}"

    def build(
        self,
        user_prompt_source,
        user_prompt_directory,
        user_prompt_file,
        genre,
        tempo,
        key,
        lyrics,
        language,
        voice,
        theme,
        length,
        description_override,
        system_prompt,
        system_prompt_source,
        system_prompt_directory,
        system_prompt_file,
        source_name_override="",
    ):
        resolved_system, system_origin = resolve_prompt(
            "system", system_prompt_source, system_prompt_directory, system_prompt_file, system_prompt
        )

        widget_values = {
            "genre": genre, "tempo": tempo, "key": key, "lyrics": lyrics,
            "language": language, "voice": voice, "theme": theme, "length": length,
        }

        source = (user_prompt_source or "manual").strip().lower()
        # Free mode: the prompt-file dropdown is set to "custom", which means no
        # file is loaded and no fields are touched - the user fills them freely.
        if source != "manual" and (user_prompt_file or "").strip() == CUSTOM:
            source = "manual"
        if source == "manual":
            file_fields = {}
            description = (description_override or "").strip()
            user_origin = "<manual>"
        else:
            try:
                text, user_origin = resolve_prompt(
                    "user", user_prompt_source, user_prompt_directory, user_prompt_file
                )
            except (PromptLibraryError, ValueError) as exc:
                raise ValueError(f"Structured Song Prompt: {exc}") from exc
            file_fields, _file_description = parse_prompt_front_matter(text)
            # description_override is the single source of truth for the
            # description once a prompt file is selected: the frontend copies
            # the file's body text into the field on selection, and only that
            # field content is used from then on.  Clearing the field removes
            # the description; the file body is never used as a silent fallback.
            description = (description_override or "").strip()

        # Precedence: explicit widget choice > file metadata > omit.  An
        # explicit "custom" means the user wants NO specification for this
        # field - it must not fall back to the file's metadata value.
        resolved = {}
        overrides = {}
        for field in STRUCTURED_FIELDS:
            widget_value = widget_values.get(field)
            widget_value = str(widget_value or "").strip()
            if widget_value == CUSTOM:
                continue
            if widget_value:
                resolved[field] = widget_value
                overrides[field] = widget_value
            elif file_fields.get(field):
                # Only reachable when the widget carries no value at all
                # (headless/API runs without the frontend prefill).
                resolved[field] = file_fields[field]

        if not resolved and not description:
            raise ValueError(
                "Structured Song Prompt: every field is 'custom' and no description is available. "
                "Select a prompt file, set at least one field, or write a description."
            )

        user_prompt = assemble_structured_user_prompt(resolved, description)

        if (source_name_override or "").strip():
            source_name = _clean_source_name(source_name_override)
        elif user_origin not in {"<manual>", PLACEHOLDER}:
            source_name = _clean_source_name(Path(user_origin).stem)
        else:
            source_name = ""

        summary = json.dumps({
            "user_prompt_origin": user_origin,
            "system_prompt_origin": system_origin,
            "fields": {field: resolved.get(field, CUSTOM) for field in STRUCTURED_FIELDS},
            "overrides": overrides,
            "description_chars": len(description),
            "user_prompt_chars": len(user_prompt),
        }, ensure_ascii=False)

        LOGGER.info(
            "Structured prompt resolved: user=%s, system=%s, fields=%d, user_prompt_chars=%d",
            user_origin, system_origin, len(resolved), len(user_prompt),
        )
        return (resolved_system, user_prompt, source_name, summary)


NODE_CLASS_MAPPINGS = {
    "MiniMaxStructuredPromptV20": MiniMaxStructuredPromptV20,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxStructuredPromptV20": "Structured Song Prompt (Genre / Tempo / Lyrics ...)",
}
