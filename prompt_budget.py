"""MiniMax Music 3 prompt token budget: estimation and soft trimming.

The MiniMax Music 3 text encoder hard-rejects prompts longer than
``MAX_PROMPT_TOKENS`` (5000; enforced in ComfyUI's
``comfy/ldm/minimax_music/ar.py``).  The LLM occasionally overshoots, so the
parser node runs a conservative token *estimate* and, when the budget is
exceeded, trims the lyrics **softly**:

- the caption is kept intact whenever possible
- lyrics lines are dropped from the end, never cutting inside a line
- orphaned section tags (``[Outro]`` with no content left) are removed
- a hard character cut is only used for a single oversized line (extreme edge
  case) and is clearly logged

The estimator was calibrated against the real MiniMax tokenizer (loaded from
``minimax_music3_text_encoder_*.safetensors`` ``tokenizer_json``): German text
consumes roughly 3.68 characters per token in the worst measured case, English
4.2-6.2.  Using 3.5 characters per token plus a fixed overhead for the
``build_prompt`` special tags keeps the estimate above the real token count,
so a prompt that fits the estimate always fits the 5000-token limit.
"""
from __future__ import annotations

import math
import re
from typing import Dict, Tuple

from .toolkit_logging import get_logger

LOGGER = get_logger("prompt_budget")

# Hard limit enforced by ComfyUI's MiniMax Music 3 text encoder.
MINIMAX_MAX_PROMPT_TOKENS = 5000

# Default parser budget: safety margin below the hard limit so estimation
# error can never push a trimmed prompt over 5000.
DEFAULT_PROMPT_TOKEN_BUDGET = 4500

# Conservative calibration (worst measured case: German ~3.68 chars/token).
_CHARS_PER_TOKEN = 3.5

# Fixed overhead of build_prompt(): special tags + [start] prefix + cleanup.
_FIXED_OVERHEAD_TOKENS = 24

_TAG_LINE_RE = re.compile(r"^\s*\[[^\]]+\]\s*$")


def estimate_prompt_tokens(caption: str, lyrics: str) -> int:
    """Conservative estimate of the token count MiniMax will see.

    Mirrors the length of ``build_prompt(caption, lyrics)`` from ComfyUI
    (caption + lyrics + special tags).  The estimate is designed to be >= the
    real token count.
    """
    text = f"{caption or ''}\n{lyrics or ''}"
    if not text.strip():
        return 0
    return math.ceil(len(text) / _CHARS_PER_TOKEN) + _FIXED_OVERHEAD_TOKENS


def _drop_orphan_tags(lines: list) -> list:
    # Remove trailing section tags whose content was trimmed away.  A single
    # remaining tag (usually [Intro]) is kept: MiniMax still gets at least one
    # structural section instead of a completely empty lyrics block.
    while len(lines) > 1 and _TAG_LINE_RE.match(lines[-1] or ""):
        lines.pop()
    return lines


def _trim_lines_to_budget(caption: str, lines: list, max_tokens: int, hard_cut: bool) -> Tuple[list, bool]:
    """Drop whole lines from the end until the estimate fits.  A single line
    that alone exceeds the budget is hard-cut to the character limit."""
    while lines and estimate_prompt_tokens(caption, "\n".join(lines)) > max_tokens:
        last = lines[-1]
        lines.pop()
        if not lines and last:
            # Single oversized line: nothing left to drop, cut inside it.
            if hard_cut:
                max_chars = max(1, int((max_tokens - _FIXED_OVERHEAD_TOKENS) * _CHARS_PER_TOKEN) - len(caption or "") - 1)
                cut = last[:max_chars].rstrip()
                if cut:
                    lines.append(cut)
                    return lines, True
            break
    return lines, False


def trim_prompt_to_budget(
    caption: str,
    lyrics: str,
    max_tokens: int = DEFAULT_PROMPT_TOKEN_BUDGET,
) -> Dict[str, object]:
    """Softly trim caption+lyrics so the estimated prompt fits ``max_tokens``.

    Returns a dict with ``caption``, ``lyrics``, ``trimmed``,
    ``hard_cut_used``, ``estimated_tokens`` and ``original_estimated_tokens``.
    Never raises for oversized input; the worst case is a hard-cut line, which
    is flagged so the caller can log it prominently.
    """
    caption = (caption or "").rstrip()
    lyrics = (lyrics or "").strip()
    original_estimate = estimate_prompt_tokens(caption, lyrics)

    result: Dict[str, object] = {
        "caption": caption,
        "lyrics": lyrics,
        "trimmed": False,
        "hard_cut_used": False,
        "estimated_tokens": original_estimate,
        "original_estimated_tokens": original_estimate,
    }
    if original_estimate <= max_tokens:
        return result

    lines = lyrics.splitlines()
    lines, hard_cut = _trim_lines_to_budget(caption, lines, max_tokens, hard_cut=True)
    lines = _drop_orphan_tags(lines)
    lyrics_out = "\n".join(lines).strip()

    # If even an empty lyrics section plus the caption does not fit, trim the
    # caption the same soft way (line-wise, tags do not apply there).
    if estimate_prompt_tokens(caption, lyrics_out) > max_tokens:
        caption_lines = caption.splitlines()
        caption_lines, hard_cut = _trim_lines_to_budget("", caption_lines, max_tokens, hard_cut=True)
        caption_out = "\n".join(caption_lines).strip()
    else:
        caption_out = caption

    result.update({
        "caption": caption_out,
        "lyrics": lyrics_out,
        "trimmed": True,
        "hard_cut_used": hard_cut,
        "estimated_tokens": estimate_prompt_tokens(caption_out, lyrics_out),
        "original_estimated_tokens": original_estimate,
    })
    return result
