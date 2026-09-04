"""Markdown report node: shows exactly what MiniMax Music 3 received.

The report is built with ComfyUI's OWN prompt builder
(``comfy.ldm.minimax_music.prompt``) wherever it is importable, so the
"verbatim" section is character-for-character identical to the text the
MiniMax tokenizer actually consumed.  The caption and lyrics sections are
cleaned the same way and shown separately for readability, and the FLUX.2
image prompt is appended clearly marked as NOT part of the MiniMax prompt.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .toolkit_logging import get_logger

LOGGER = get_logger("prompt_report")


def _minimax_prompt_builder() -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
    """Import ComfyUI's own prompt builder, or return None on older builds."""
    try:
        from comfy.ldm.minimax_music.prompt import (  # type: ignore
            build_prompt,
            clean_caption,
            normalize_lyrics,
        )
        return build_prompt, clean_caption, normalize_lyrics
    except Exception as exc:  # pragma: no cover - depends on the ComfyUI build
        LOGGER.debug("comfy.ldm.minimax_music.prompt not importable: %s", exc)
        return None, None, None


def build_prompt_report(caption: str, lyrics: str, title: str, image_prompt: str) -> str:
    caption = (caption or "").strip()
    lyrics = (lyrics or "").strip()
    title = (title or "").strip()
    image_prompt = (image_prompt or "").strip()

    build_prompt, clean_caption, normalize_lyrics = _minimax_prompt_builder()
    lines = ["# MiniMax Music 3 – Prompt Report", ""]
    if title:
        lines += [f"**Title:** {title}", ""]

    if build_prompt is not None:
        verbatim = build_prompt(caption, lyrics)
        lines += [
            "## Caption (musical brief, as sent to MiniMax)",
            "",
            clean_caption(caption) or "_(empty)_",
            "",
            "## Lyrics (as sent to MiniMax)",
            "",
            normalize_lyrics(lyrics) or "_(none)_",
            "",
            "## Final prompt sent to MiniMax (verbatim)",
            "",
            "```",
            verbatim,
            "```",
            "",
        ]
    else:  # pragma: no cover - fallback for other ComfyUI builds
        lines += [
            "## Caption (raw)",
            "",
            caption or "_(empty)_",
            "",
            "## Lyrics (raw)",
            "",
            lyrics or "_(none)_",
            "",
            "_Note: the exact final prompt could not be reconstructed because "
            "`comfy.ldm.minimax_music.prompt` is not importable in this ComfyUI build; "
            "the raw values are shown instead._",
            "",
        ]

    lines += [
        "---",
        "",
        "## Image Prompt (FLUX.2 cover – NOT sent to MiniMax)",
        "",
        image_prompt or "_(none)_",
        "",
    ]
    return "\n".join(lines)


class MiniMaxPromptReport:
    """MiniMax Prompt Report – shows exactly what MiniMax Music 3 received, as Markdown."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "caption": ("STRING", {"forceInput": True, "multiline": True}),
                "lyrics": ("STRING", {"forceInput": True, "multiline": True}),
                "title": ("STRING", {"forceInput": True}),
                "image_prompt": ("STRING", {"forceInput": True, "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("markdown",)
    # The report is a pure display node with no downstream consumer, so it must
    # be marked as an output node - otherwise ComfyUI's executor does not
    # include it in the execution set and the node never produces its ui text.
    OUTPUT_NODE = True
    FUNCTION = "report"
    CATEGORY = "MiniMax Music Production Toolkit/prompt"
    DESCRIPTION = (
        "Builds a readable Markdown report of the exact prompt text MiniMax Music 3 "
        "received (caption + lyrics, cleaned exactly like the MiniMax tokenizer, plus "
        "the verbatim final prompt) and appends the FLUX.2 image prompt, clearly marked "
        "as not part of the MiniMax prompt."
    )

    def report(self, caption: str, lyrics: str, title: str, image_prompt: str):
        markdown = build_prompt_report(caption, lyrics, title, image_prompt)
        LOGGER.info("MiniMaxPromptReport generated %d chars.", len(markdown))
        return {"ui": {"text": (markdown,)}, "result": (markdown,)}


NODE_CLASS_MAPPINGS = {
    "MiniMaxPromptReport": MiniMaxPromptReport,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxPromptReport": "MiniMax Prompt Report (Markdown)",
}
