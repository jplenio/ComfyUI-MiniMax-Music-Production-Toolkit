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

from .prompt_budget import (
    MINIMAX_MAX_PROMPT_TOKENS,
    count_prompt_tokens,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("prompt_report")


def literal_block(text: str) -> str:
    """Preserve line breaks and literal section tags in Markdown renderers."""
    import re
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    fence = "`" * max(3, 1 + max((len(m.group()) for m in re.finditer(r"`+", text)), default=0))
    return f"{fence}text\n{text}\n{fence}"


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


def build_token_budget_lines(caption: str, lyrics: str):
    """Markdown block reporting the measured (or estimated) MiniMax token count.

    The distinction is explicit: a measured count came from the real MiniMax
    tokenizer, an estimated one did not, and the report must never present the
    estimate as a measurement.
    """
    info = count_prompt_tokens(caption, lyrics)
    tokens = int(info["tokens"])
    if info["exact"]:
        value = f"**{tokens} tokens** (measured with the MiniMax tokenizer)"
    elif str(info["method"]).startswith("tokenizer"):
        value = (
            f"**{tokens} tokens** (measured on the caption+lyrics text; ComfyUI's "
            "`build_prompt` wrapper was not importable, so the fixed tag overhead may differ slightly)"
        )
    else:
        value = (
            f"**~{tokens} tokens** (conservative *estimate* - the MiniMax tokenizer/checkpoint "
            "was not available; dense scripts can tokenize above this estimate)"
        )
    lines = [
        "---",
        "",
        "## Token budget (MiniMax text encoder)",
        "",
        f"- {value}",
        f"- Conservative estimate: {int(info['estimate'])} tokens",
        f"- Hard limit enforced by MiniMax: {MINIMAX_MAX_PROMPT_TOKENS} tokens",
    ]
    if info["estimate_covers_real"] is False:
        lines.append(
            "- **Warning:** the estimate was *below* the measured count for this text; treat the "
            "heuristic as an estimate only."
        )
    lines.append("")
    return lines


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
            literal_block(clean_caption(caption) or "(empty)"),
            "",
            "## Lyrics (as sent to MiniMax)",
            "",
            literal_block(normalize_lyrics(lyrics) or "(none)"),
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
            literal_block(caption or "(empty)"),
            "",
            "## Lyrics (raw)",
            "",
            literal_block(lyrics or "(none)"),
            "",
            "_Note: the exact final prompt could not be reconstructed because "
            "`comfy.ldm.minimax_music.prompt` is not importable in this ComfyUI build; "
            "the raw values are shown instead._",
            "",
        ]

    lines += build_token_budget_lines(caption, lyrics)

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
            },
            "optional": {"model_profile_json": ("STRING", {"forceInput": True})},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("markdown",)
    # The report is a pure display node with no downstream consumer, so it must
    # be marked as an output node - otherwise ComfyUI's executor does not
    # include it in the execution set and the node never produces its ui text.
    OUTPUT_NODE = True
    FUNCTION = "report"
    CATEGORY = "Music Production Toolkit/prompt"
    DESCRIPTION = (
        "Builds a readable Markdown report of the exact prompt text MiniMax Music 3 "
        "received (caption + lyrics, cleaned exactly like the MiniMax tokenizer, plus "
        "the verbatim final prompt) and appends the FLUX.2 image prompt, clearly marked "
        "as not part of the MiniMax prompt."
    )

    def report(self, caption: str, lyrics: str, title: str, image_prompt: str, model_profile_json=""):
        from .model_profiles import profile_from_payload
        profile = profile_from_payload(model_profile_json)
        if profile is not None and profile.is_yue2:
            markdown = (f"# YuE2 – Prompt Report\n\n**Title:** {title}\n\n"
                        f"## Style (raw input)\n\n{literal_block(caption)}\n\n## Lyrics (raw input)\n\n{literal_block(lyrics)}\n\n"
                        "The native ABC and music nodes build their own conditioning. These are the input "
                        "strings, not a reconstructed tokenizer prompt. ABC and effective settings are in "
                        "the production JSON under generation.\n\n"
                        f"## Image Prompt (FLUX.2 cover)\n\n{image_prompt}\n")
        else:
            markdown = build_prompt_report(caption, lyrics, title, image_prompt)
        LOGGER.info("MiniMaxPromptReport generated %d chars.", len(markdown))
        return {"ui": {"text": (markdown,)}, "result": (markdown,)}


NODE_CLASS_MAPPINGS = {
    "MiniMaxPromptReport": MiniMaxPromptReport,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxPromptReport": "MiniMax Prompt Report (Markdown)",
}
