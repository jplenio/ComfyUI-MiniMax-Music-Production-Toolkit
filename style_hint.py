"""A style text the Cover Studio can use, taken from a prompt file or typed here.

Why this node exists
--------------------
`Song request · template & fields` is the master for what a track sounds like, but
it *consumes* the Cover Studio's rewritten score (the final prompt has to describe
the rewritten key, tempo and structure). It is therefore downstream of the studio,
and any link from it back into the studio is a dependency cycle - ComfyUI rejects
such a prompt with "Dependency cycle detected".

The studio can still be told which style to aim its rework at, as long as the text
comes from a node that is *not* downstream of it. This node is that source: it
resolves the same prompt library the master uses, or takes typed text, and hands the
result to the studio's `target_style` input.

It never overrides the song request. The value is a hint for how the source material
is reworked; the rendering style stays with the master, whose prompt carries the
STYLE PRIORITY rule. See docs/YUE2.md, "Where each instruction comes from".
"""
from __future__ import annotations

import hashlib
from typing import Tuple

from .prompt_library import (
    PLACEHOLDER,
    default_combo_values,
    prompt_selection_fingerprint,
    resolve_prompt,
)
from .prompt_metadata import CUSTOM, parse_prompt_front_matter
from .toolkit_logging import get_logger

LOGGER = get_logger("style_hint")

SOURCES = ["bundled_library", "external_directory", "manual"]


def style_hint_text(
    style_text: str = "",
    source: str = "bundled_library",
    directory: str = "",
    selected_file: str = CUSTOM,
    warn: bool = True,
) -> Tuple[str, str]:
    """Return ``(text, origin)`` for the configured hint; never raises.

    A selected prompt file wins over the typed text, so the hint follows the file
    the moment it is chosen. An empty configuration returns an empty string: the
    hint is optional and must never stop a run. ``warn=False`` keeps the cache
    check (IS_CHANGED) from repeating the resolve warnings.
    """
    manual = str(style_text or "").strip()
    selected = str(selected_file or "").strip()
    if source != "manual" and selected and selected not in (CUSTOM, PLACEHOLDER):
        try:
            text, origin = resolve_prompt("user", source, directory, selected, manual)
            text = str(text or "").strip()
            # The file's front matter is metadata, not prose: the master node puts
            # only the body into its description, so the hint must match it or a
            # link into `description_override` would leak a YAML block into the prompt.
            _fields, body = parse_prompt_front_matter(text)
            text = (body or text).strip()
            if text:
                return text, origin
            if warn:
                LOGGER.warning("Style hint: '%s' is empty; using the typed text instead.", selected)
        except Exception as exc:  # a missing file must not break the graph
            if warn:
                LOGGER.warning(
                    "Style hint: could not read '%s' (%s); using the typed text instead.", selected, exc)
    if manual:
        return manual, "<typed text>"
    return "", "<empty>"


class MiniMaxStyleHint:
    """Hands a style text to the Cover Studio's target_style input."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "style_text": ("STRING", {
                    "default": "", "multiline": True,
                    "tooltip": "The style hint as free text, used when no prompt file is selected "
                               "below. It is a hint for how the Cover Studio reworks the source "
                               "material, never a replacement for the style the song request sets. "
                               "Leave it empty to send no hint at all.",
                }),
            },
            "optional": {
                "user_prompt_source": (list(SOURCES), {
                    "default": "bundled_library",
                    "tooltip": "Where the hint text comes from. bundled_library uses the prompt "
                               "files shipped with the toolkit, external_directory reads them "
                               "from a folder on the ComfyUI machine, and manual uses only the "
                               "typed text above.",
                }),
                "user_prompt_directory": ("STRING", {
                    "default": "", "multiline": False,
                    "tooltip": "Folder to read prompt files from when prompt_source is "
                               "external_directory. Environment variables and ~ are expanded; "
                               "files stay inside this folder. Ignored in the other modes.",
                }),
                "user_prompt_file": ([CUSTOM, *default_combo_values("user")], {
                    "default": CUSTOM,
                    "tooltip": "The template whose text becomes the hint. Select the same file you "
                               "use in 'Song request · template & fields' so both use one style "
                               "definition; picking a file here wins over the typed text.",
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("style_hint",)
    FUNCTION = "resolve"
    CATEGORY = "Music Production Toolkit/prompts"
    DESCRIPTION = (
        "Provides the style text the Cover Studio may use as a hint for reworking the source "
        "material. Use it when you want the studio's planning and transformation calls to see the "
        "style you asked for: select the same prompt template here that 'Song request · template & "
        "fields' uses, and the studio receives that template's text.\n\n"
        "WHAT IT IS NOT: this node never overrides the song request. The requested style - template, "
        "fields and description - is the master for what the track sounds like, and the master node "
        "consumes the studio's rewritten score, so it cannot feed the studio (that would be a "
        "dependency cycle). This hint only guides how the material is reworked and must not "
        "contradict the request.\n\n"
        "PRECEDENCE: a selected prompt file wins over the typed text; with neither, the output is "
        "empty and the studio works from the interpretation profile alone."
    )

    def resolve(self, style_text="", user_prompt_source="bundled_library", user_prompt_directory="",
                user_prompt_file=CUSTOM):
        text, origin = style_hint_text(style_text, user_prompt_source, user_prompt_directory,
                                       user_prompt_file)
        LOGGER.info("Style hint resolved from %s (%d characters).", origin, len(text))
        return (text,)

    @classmethod
    def IS_CHANGED(cls, style_text="", user_prompt_source="bundled_library", user_prompt_directory="",
                   user_prompt_file=CUSTOM):
        # The resolved text is what matters, so the fingerprint covers the file
        # (selection and content) *and* the resolved value. The library fingerprint
        # alone is not enough: for a manual or 'custom' selection it degrades to a
        # constant error string and would hide an edited hint text.
        try:
            selection = prompt_selection_fingerprint(
                "user", user_prompt_source, user_prompt_directory, user_prompt_file, style_text)
        except Exception as exc:  # pragma: no cover - the library reports its own errors
            selection = f"unavailable:{type(exc).__name__}"
        text, origin = style_hint_text(style_text, user_prompt_source, user_prompt_directory,
                                       user_prompt_file, warn=False)
        return hashlib.sha256(f"{selection}|{origin}|{text}".encode("utf-8")).hexdigest()


NODE_CLASS_MAPPINGS = {
    "MiniMaxStyleHint": MiniMaxStyleHint,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxStyleHint": "Style hint · template or text",
}


__all__ = [
    "MiniMaxStyleHint",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "SOURCES",
    "style_hint_text",
]
