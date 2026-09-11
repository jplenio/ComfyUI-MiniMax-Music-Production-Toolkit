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
consumed roughly 3.68 characters per token in the lowest measured case, English
4.2-6.2.  3.5 characters per token plus a fixed overhead for the
``build_prompt`` special tags stayed above the real token count for those
languages.

It is a heuristic, **not a guarantee**.  Languages whose tokenizer merges are
denser per character (CJK, Urdu and other non-Latin scripts, unusual Unicode
sequences, future tokenizers) can exceed 3.5 characters per token, so a prompt
that fits the estimate is not proven to fit the 5000-token limit.  Callers that
need certainty use :func:`count_prompt_tokens`, which runs the real MiniMax
tokenizer whenever its checkpoint is available and otherwise reports the value
as an *estimate*.

The budget here is the MiniMax **text-encoder** budget.  The LLM's own context
(``n_ctx`` in ``llm_chat``) is a different tokenizer and a different budget; the
two must not be conflated.
"""
from __future__ import annotations

import math
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .toolkit_logging import get_logger

LOGGER = get_logger("prompt_budget")

# Hard limit enforced by ComfyUI's MiniMax Music 3 text encoder.
MINIMAX_MAX_PROMPT_TOKENS = 5000

# Default parser budget: safety margin below the hard limit so estimation
# error can never push a trimmed prompt over 5000.
DEFAULT_PROMPT_TOKEN_BUDGET = 4500

# Heuristic calibration (lowest measured case: German ~3.68 chars/token).  This
# is an estimate basis, not a proven lower bound - see the module docstring.
_CHARS_PER_TOKEN = 3.5

# Fixed overhead of build_prompt(): special tags + [start] prefix + cleanup.
_FIXED_OVERHEAD_TOKENS = 24

_TAG_LINE_RE = re.compile(r"^\s*\[[^\]]+\]\s*$")


def estimate_prompt_tokens(caption: str, lyrics: str) -> int:
    """Estimate of the token count MiniMax will see, without a tokenizer.

    Mirrors the length of ``build_prompt(caption, lyrics)`` from ComfyUI
    (caption + lyrics + special tags).  The estimate stayed at or above the
    real count for the calibrated languages (German/English), but it is a
    heuristic and may undershoot for denser scripts - use
    :func:`count_prompt_tokens` when an exact number matters.
    """
    text = f"{caption or ''}\n{lyrics or ''}"
    if not text.strip():
        return 0
    return math.ceil(len(text) / _CHARS_PER_TOKEN) + _FIXED_OVERHEAD_TOKENS


# ---------------------------------------------------------------------------
# Exact counting (optional): the real MiniMax tokenizer, read from the
# text-encoder checkpoint's ``tokenizer_json`` metadata tensor only.
# ---------------------------------------------------------------------------

MINIMAX_TEXT_ENCODER_PATTERNS = (
    "minimax_music3_text_encoder*.safetensors",
    "*minimax_music3*text_encoder*.safetensors",
)
_TOKENIZER_META_KEY = "tokenizer_json"
_TOKENIZER_CACHE_MAX = 2
# Bounded by checkpoint identity (path name + size + mtime), never unbounded.
_TOKENIZER_CACHE: "OrderedDict[str, Tuple[Any, str]]" = OrderedDict()


def _safe_import_tokenizer_runtime():
    """Return ``(Tokenizer, safe_open)`` or ``None`` when unavailable.

    ``tokenizers``/``safetensors`` are optional: on a machine without them the
    exact-count path simply does not exist and callers fall back to the
    estimate.  Importing them never loads weights and never touches a GPU.
    """
    try:
        from safetensors import safe_open  # type: ignore
        from tokenizers import Tokenizer  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on the environment
        LOGGER.debug("MiniMax tokenizer runtime unavailable: %s", exc)
        return None
    return Tokenizer, safe_open


def _tensor_bytes(tensor: Any) -> bytes:
    """Bytes of a ``tokenizer_json`` tensor for either safetensors framework."""
    if hasattr(tensor, "tobytes"):
        return tensor.tobytes()
    return tensor.numpy().tobytes()  # pragma: no cover - torch fallback


def resolve_minimax_tokenizer_checkpoint() -> Optional[Path]:
    """Best-effort lookup of the MiniMax text-encoder checkpoint.

    Uses ComfyUI's ``folder_paths`` when this runs inside ComfyUI and returns
    ``None`` otherwise - never raises, never downloads, never opens the file.
    """
    try:
        import folder_paths  # type: ignore
    except Exception as exc:
        LOGGER.debug("folder_paths not importable: %s", exc)
        return None
    try:
        names = list(folder_paths.get_filename_list("text_encoders"))
    except Exception as exc:  # pragma: no cover - host dependent
        LOGGER.debug("text_encoders listing failed: %s", exc)
        return None
    matches = sorted(
        name for name in names if Path(name).name.lower().startswith("minimax_music3_text_encoder")
    )
    for name in matches:
        try:
            full = Path(folder_paths.get_full_path("text_encoders", name))
        except Exception:  # pragma: no cover - host dependent
            continue
        if full.is_file():
            return full
    return None


def _tokenizer_identity(path: Path) -> str:
    """Stable cache identity: file name plus its size/mtime signature."""
    try:
        stat = path.stat()
        return f"{path.name}::{stat.st_size}::{stat.st_mtime_ns}"
    except OSError:  # pragma: no cover - race with a deleted file
        return f"{path.name}::missing"


def _cache_put(identity: str, tokenizer: Any) -> None:
    _TOKENIZER_CACHE[identity] = (tokenizer, identity)
    _TOKENIZER_CACHE.move_to_end(identity)
    while len(_TOKENIZER_CACHE) > _TOKENIZER_CACHE_MAX:
        _TOKENIZER_CACHE.popitem(last=False)


def load_minimax_tokenizer(
    checkpoint: Optional[Any] = None,
) -> Tuple[Optional[Any], Optional[str]]:
    """Load the MiniMax tokenizer from a checkpoint, cached by its identity.

    Reads only the ``tokenizer_json`` metadata tensor via ``safe_open`` - never
    the text-encoder weights, never a GPU.  Second and later calls for the same
    checkpoint signature reuse the cached tokenizer; the cache holds at most
    :data:`_TOKENIZER_CACHE_MAX` tokenizers.

    Returns ``(tokenizer, identity)`` or ``(None, None)`` when the runtime, the
    checkpoint or the metadata is unavailable.
    """
    runtime = _safe_import_tokenizer_runtime()
    if runtime is None:
        return None, None
    Tokenizer, safe_open = runtime
    path = Path(checkpoint) if checkpoint is not None else resolve_minimax_tokenizer_checkpoint()
    if path is None or not Path(path).is_file():
        return None, None
    path = Path(path)
    identity = _tokenizer_identity(path)
    cached = _TOKENIZER_CACHE.get(identity)
    if cached is not None:
        _TOKENIZER_CACHE.move_to_end(identity)
        return cached[0], identity
    try:
        with safe_open(str(path), framework="np") as handle:
            blob = _tensor_bytes(handle.get_tensor(_TOKENIZER_META_KEY))
        tokenizer = Tokenizer.from_str(blob.decode("utf-8"))
    except Exception as exc:
        LOGGER.warning(
            "Could not read tokenizer_json from %s (falling back to the estimate): %s: %s",
            path.name,
            type(exc).__name__,
            exc,
        )
        return None, None
    _cache_put(identity, tokenizer)
    return tokenizer, identity


def _comfy_build_prompt() -> Optional[Callable[[str, str], str]]:
    """ComfyUI's own ``build_prompt`` when importable, else ``None``."""
    try:
        from comfy.ldm.minimax_music.prompt import build_prompt  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on the ComfyUI build
        LOGGER.debug("comfy.ldm.minimax_music.prompt not importable: %s", exc)
        return None
    return build_prompt


def token_counter(
    checkpoint: Optional[Any] = None,
    tokenizer: Optional[Any] = None,
) -> Tuple[Optional[Callable[[str, str], int]], Optional[str]]:
    """Return ``(counter, tokenizer_id)`` counting real MiniMax tokens.

    ``counter(caption, lyrics)`` returns the exact token count of the text
    MiniMax would tokenize, or ``-1`` when that particular call fails.  Returns
    ``(None, None)`` when no tokenizer is available, so callers keep the
    estimated path unchanged.
    """
    if tokenizer is None:
        tokenizer, identity = load_minimax_tokenizer(checkpoint)
    else:
        identity = "injected"
    if tokenizer is None:
        return None, None
    build_prompt = _comfy_build_prompt()

    def _count(caption: str, lyrics: str) -> int:
        text = build_prompt(caption or "", lyrics or "") if build_prompt else f"{caption or ''}\n{lyrics or ''}"
        try:
            return len(tokenizer.encode(text, add_special_tokens=False).ids)
        except Exception as exc:  # pragma: no cover - tokenizer dependent
            LOGGER.warning("MiniMax tokenizer encode failed: %s: %s", type(exc).__name__, exc)
            return -1

    return _count, identity


def count_prompt_tokens(
    caption: str,
    lyrics: str,
    checkpoint: Optional[Any] = None,
    tokenizer: Optional[Any] = None,
) -> Dict[str, object]:
    """Count MiniMax prompt tokens exactly when possible, else estimate.

    Returns a dict with ``tokens``, ``method`` (``tokenizer`` for the real
    ``build_prompt`` text, ``tokenizer_text_only`` when ComfyUI's builder is
    not importable, ``estimate`` for the heuristic), ``exact``,
    ``tokenizer_id``, ``estimate`` (the heuristic value, always present) and
    ``estimate_covers_real`` (``True``/``False``/``None`` - whether the
    heuristic stayed at or above the measured count).
    """
    estimate = estimate_prompt_tokens(caption, lyrics)
    counter, identity = token_counter(checkpoint=checkpoint, tokenizer=tokenizer)
    if counter is None:
        return {
            "tokens": estimate,
            "method": "estimate",
            "exact": False,
            "tokenizer_id": None,
            "estimate": estimate,
            "estimate_covers_real": None,
        }
    measured = counter(caption, lyrics)
    if measured < 0:
        return {
            "tokens": estimate,
            "method": "estimate",
            "exact": False,
            "tokenizer_id": identity,
            "estimate": estimate,
            "estimate_covers_real": None,
        }
    method = "tokenizer" if _comfy_build_prompt() is not None else "tokenizer_text_only"
    return {
        "tokens": measured,
        "method": method,
        "exact": method == "tokenizer",
        "tokenizer_id": identity,
        "estimate": estimate,
        "estimate_covers_real": estimate >= measured,
    }


def _combined_char_limit(max_tokens: int) -> int:
    """Largest caption+lyrics character count that keeps the estimate in budget.

    One token of slack absorbs the ``ceil()`` in :func:`estimate_prompt_tokens`,
    so ``total <= limit`` always implies ``estimate <= max_tokens``.
    """
    return int((max_tokens - _FIXED_OVERHEAD_TOKENS - 1) * _CHARS_PER_TOKEN)


def _shorten_to_fit(text: str, other: str, max_tokens: int) -> Tuple[str, bool]:
    """Character-level fallback that enforces the combined postcondition.

    Line-wise trimming judges each field against the budget alone, so the
    residual of the other field can still push the combination over.  This is
    the last resort (while the combined estimate exceeds the budget) and it is
    always reported as a hard cut.
    """
    if not text:
        return text, False
    limit = _combined_char_limit(max_tokens)
    if len(text) + 1 + len(other) <= limit:
        return text, False
    allowed = max(0, limit - len(other) - 1)
    return text[:allowed].rstrip(), True


def _drop_orphan_tags(lines: list) -> list:
    # Remove trailing section tags whose content was trimmed away.  A single
    # remaining tag (usually [Intro]) is kept: MiniMax still gets at least one
    # structural section instead of a completely empty lyrics block.
    while len(lines) > 1 and _TAG_LINE_RE.match(lines[-1] or ""):
        lines.pop()
    return lines


def _trim_lines_to_budget(
    caption: str,
    lines: list,
    max_tokens: int,
    hard_cut: bool,
    count: Callable[[str, str], int] = None,
) -> Tuple[list, bool]:
    """Drop whole lines from the end until the count fits.  A single line
    that alone exceeds the budget is hard-cut to the character limit."""
    count = count or estimate_prompt_tokens
    while lines and count(caption, "\n".join(lines)) > max_tokens:
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


def _shorten_to_fit_measured(
    text: str,
    other: str,
    max_tokens: int,
    count: Callable[[str, str], int],
) -> Tuple[str, bool]:
    """Measured-counter fallback that enforces the combined postcondition.

    Used only when an exact tokenizer is active.  Shrinks ``text`` in 10 % steps
    until the measured count fits; dropping the field entirely is the strongest
    available action when even one character does not fit.
    """
    if not text:
        return text, False
    if count(text, other) <= max_tokens:
        return text, False
    while len(text) > 1:
        text = text[: max(1, int(len(text) * 0.9))].rstrip()
        if count(text, other) <= max_tokens:
            return text, True
    if count("", other) <= max_tokens:
        return "", True
    return "", True


def _count_section_tags(lines: List[str]) -> int:
    return sum(1 for line in lines if _TAG_LINE_RE.match(line or ""))


def trim_prompt_to_budget(
    caption: str,
    lyrics: str,
    max_tokens: int = DEFAULT_PROMPT_TOKEN_BUDGET,
    counter: Optional[Callable[[str, str], int]] = None,
) -> Dict[str, object]:
    """Softly trim caption+lyrics so the prompt fits ``max_tokens``.

    ``counter`` is the token-counting function used for the fitting decision.
    The default ``None`` keeps the historical behaviour (the conservative
    :func:`estimate_prompt_tokens`); passing a real tokenizer counter (see
    :func:`token_counter`) makes the decision exact, which is the only way to
    be safe for scripts the heuristic may underestimate.

    Returns a dict with ``caption``, ``lyrics``, ``trimmed``,
    ``hard_cut_used``, ``estimated_tokens``, ``original_estimated_tokens``,
    ``count_method``, ``removed_lines`` and ``removed_sections``.  Never raises
    for oversized input; the worst case is a hard-cut line, which is flagged so
    the caller can log it prominently.
    """
    count = counter or estimate_prompt_tokens
    caption = (caption or "").rstrip()
    lyrics = (lyrics or "").strip()
    original_estimate = count(caption, lyrics)
    original_lines = lyrics.splitlines()

    result: Dict[str, object] = {
        "caption": caption,
        "lyrics": lyrics,
        "trimmed": False,
        "hard_cut_used": False,
        "estimated_tokens": original_estimate,
        "original_estimated_tokens": original_estimate,
        "count_method": "tokenizer" if counter is not None else "estimate",
        "removed_lines": 0,
        "removed_sections": 0,
    }
    if original_estimate <= max_tokens:
        return result

    lines = lyrics.splitlines()
    lines, hard_cut = _trim_lines_to_budget(caption, lines, max_tokens, hard_cut=True, count=count)
    lines = _drop_orphan_tags(lines)
    lyrics_out = "\n".join(lines).strip()

    # If even an empty lyrics section plus the caption does not fit, trim the
    # caption the same soft way (line-wise, tags do not apply there).
    caption_out = caption
    if count(caption_out, lyrics_out) > max_tokens:
        caption_lines = caption.splitlines()
        caption_lines, caption_hard_cut = _trim_lines_to_budget(
            "", caption_lines, max_tokens, hard_cut=True, count=count
        )
        caption_out = "\n".join(caption_lines).strip()
        # Accumulate the flag across both fields: either one may have needed a
        # hard cut, and the caller must be told about all of them.
        hard_cut = hard_cut or caption_hard_cut

    # Postcondition.  Each field was trimmed against the *other* field's
    # residual text, so the combination can still exceed the budget (the
    # 20,000/20,000 reproduction ended at 4501/4500).  Shorten the lyrics
    # remainder first - they are the soft field - then the caption, and recheck
    # the final count instead of trusting the intermediate steps.
    if counter is None:
        lyrics_out, cut = _shorten_to_fit(lyrics_out, caption_out, max_tokens)
        hard_cut = hard_cut or cut
        caption_out, cut = _shorten_to_fit(caption_out, lyrics_out, max_tokens)
        hard_cut = hard_cut or cut
    else:
        lyrics_out, cut = _shorten_to_fit_measured(lyrics_out, caption_out, max_tokens, count)
        hard_cut = hard_cut or cut
        caption_out, cut = _shorten_to_fit_measured(caption_out, lyrics_out, max_tokens, count)
        hard_cut = hard_cut or cut

    remaining_lines = lyrics_out.splitlines()
    result.update({
        "caption": caption_out,
        "lyrics": lyrics_out,
        "trimmed": True,
        "hard_cut_used": hard_cut,
        "estimated_tokens": count(caption_out, lyrics_out),
        "original_estimated_tokens": original_estimate,
        "removed_lines": max(0, len(original_lines) - len(remaining_lines)),
        "removed_sections": max(
            0, _count_section_tags(original_lines) - _count_section_tags(remaining_lines)
        ),
    })
    return result
