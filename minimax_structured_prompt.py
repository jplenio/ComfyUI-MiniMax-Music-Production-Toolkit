"""Structured Song Prompt node (MiniMaxStructuredPromptV20).

This node is the user-facing prompt control introduced in 2.0.0.  Instead of a
single free-form ``user_prompt`` text field, it exposes structured fields
(Genre, Tempo, Time signature, Key, Lyrics, Language, Voice, Lyrics theme,
Target length) plus a "further description" area.  Prompt library files may *optionally* carry a
metadata block that prefills these fields when the file is selected; the user
can still override every field, and selecting ``custom`` leaves a part out of
the LLM prompt entirely.

The assembled user prompt is a short structured brief followed by the
description text, and is intended to be consumed by the integrated LLM chat
node (or any other LLM node that accepts user/system prompt strings).

The system prompt mirrors the user prompt: selecting a bundled/external system
prompt file copies its text into the editable ``system_prompt`` field, which is
authoritative from then on (so the selection can still be tweaked by hand).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .prompt_sources import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_SYSTEM_PROMPT_FILE,
    clean_source_name as _clean_source_name,
)
from .prompt_library import (
    PLACEHOLDER,
    PromptLibraryError,
    default_combo_values,
    invalidate_library_options,
    library_options,
    prompt_selection_fingerprint,
    resolve_prompt,
)
from .prompt_metadata import (
    CUSTOM,
    STRUCTURED_FIELDS,
    assemble_structured_user_prompt,
    parse_prompt_front_matter,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("structured_prompt")

_SOURCES = ["manual", "bundled_library", "external_directory"]

# Default user-prompt file shown by the dropdown (a bundled library entry).
DEFAULT_USER_PROMPT_FILE = "electronic/synth-pop-vocal.txt"

# The aggregated option values are library data; the cache and its invalidation
# live in prompt_library so this node is not a service dependency of the route
# layer.  The historic names stay as delegates.
def invalidate_library_options_cache() -> None:
    """Refresh the aggregated combo options after prompt files changed on disk."""
    invalidate_library_options("user")


def _collect_options() -> dict:
    """Curated vocabulary plus unique values from all bundled user prompt files."""
    return library_options("user")


def _combo(field: str) -> list:
    values = [CUSTOM]
    values += [v for v in _collect_options().get(field, []) if v and v != CUSTOM]
    return values


def _safe_choices(default: list) -> list:
    # Keep the COMBO non-empty even if option discovery failed completely.
    return default or [CUSTOM]


def _resolve_system_prompt(system_prompt_source, system_prompt_directory, system_prompt_file, system_prompt):
    """Resolve the effective system prompt text and its origin.

    The ``system_prompt`` field is authoritative in every mode: the frontend
    copies the selected system-prompt file into it on selection (exactly like
    ``description_override`` for the user prompt), so editing the field always
    changes the prompt the LLM receives.  Headless/API runs without the
    frontend prefill fall back to loading the selected file directly.
    """
    source = (system_prompt_source or "manual").strip().lower()
    if source == "manual":
        text = (system_prompt or "").strip()
        if not text:
            raise ValueError("Structured Song Prompt: manual system prompt is empty.")
        return text, "<manual>"

    text = (system_prompt or "").strip()
    if text:
        origin = (system_prompt_file or "").strip() or PLACEHOLDER
        return text, origin
    return resolve_prompt("system", source, system_prompt_directory, system_prompt_file)


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
                "user_prompt_file": (user_file_options, {"default": DEFAULT_USER_PROMPT_FILE}),
                "genre": (_safe_choices(_combo("genre")), {"default": CUSTOM}),
                "tempo": (_safe_choices(_combo("tempo")), {"default": CUSTOM}),
                "meter": (_safe_choices(_combo("meter")), {"default": CUSTOM}),
                "key": (_safe_choices(_combo("key")), {"default": CUSTOM}),
                "lyrics": (_safe_choices(_combo("lyrics")), {"default": CUSTOM}),
                "language": (_safe_choices(_combo("language")), {"default": CUSTOM}),
                "voice": (_safe_choices(_combo("voice")), {"default": CUSTOM}),
                "theme": (_safe_choices(_combo("theme")), {"default": CUSTOM}),
                "length": (_safe_choices(_combo("length")), {"default": CUSTOM}),
                "description_override": ("STRING", {"default": "", "multiline": True}),
                "system_prompt_source": (_SOURCES, {"default": "bundled_library"}),
                "system_prompt_directory": ("STRING", {"default": "", "multiline": False}),
                "system_prompt_file": (default_combo_values("system"), {"default": DEFAULT_SYSTEM_PROMPT_FILE}),
                "source_name_override": ("STRING", {"default": "", "multiline": False}),
                "system_prompt": ("STRING", {"default": DEFAULT_SYSTEM_PROMPT, "multiline": True}),
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
        meter,
        key,
        lyrics,
        language,
        voice,
        theme,
        length,
        description_override,
        system_prompt_source,
        system_prompt_directory,
        system_prompt_file,
        source_name_override="",
        system_prompt="",
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
        # The system_prompt field is authoritative in every mode, so its text is
        # part of the fingerprint even when a file is selected.
        system_text_fp = hashlib.sha256((system_prompt or "").encode("utf-8", errors="replace")).hexdigest()[:16]
        system_fp = f"{system_fp}|text={system_text_fp}"
        field_state = "|".join(
            f"{f}={v}" for f, v in (
                ("genre", genre), ("tempo", tempo), ("meter", meter), ("key", key),
                ("lyrics", lyrics), ("language", language), ("voice", voice),
                ("theme", theme), ("length", length),
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
        meter,
        key,
        lyrics,
        language,
        voice,
        theme,
        length,
        description_override,
        system_prompt_source,
        system_prompt_directory,
        system_prompt_file,
        source_name_override="",
        system_prompt="",
    ):
        resolved_system, system_origin = _resolve_system_prompt(
            system_prompt_source, system_prompt_directory, system_prompt_file, system_prompt
        )

        widget_values = {
            "genre": genre, "tempo": tempo, "meter": meter, "key": key,
            "lyrics": lyrics, "language": language, "voice": voice,
            "theme": theme, "length": length,
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
    "MiniMaxStructuredPromptV20": "Structured Song Prompt (Genre / Tempo / Time signature / Lyrics ...)",
}
