"""Shared prompt-source helpers: decoding, discovery, naming, seeds, variants.

``minimax_batch`` (legacy strict folder/manual source) and
``minimax_prompt_source`` (rich source + rich parser) each grew their own copy
of the same file handling.  This module owns the parts that are genuinely
identical, while every place where the two dialects differ on purpose stays a
caller decision:

* the node name inside error messages (``error_prefix``),
* whether an empty ``extensions`` list is an error (legacy: yes) or simply
  matches nothing (rich: no),
* the discovery sort key (legacy sorts by path relative to the directory, rich
  sorts by the absolute path),
* the ``[Count]`` policy - legacy treats ``0`` as "zero songs", rich treats a
  falsy override as "use ``song_count``" (strict versus tolerant).

The variant/seed loop itself is shared, because that is where an independent
second implementation would silently change generated seeds.
"""
from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Sequence, Set, Tuple

from .toolkit_logging import get_logger

_LOGGER = get_logger("prompt_sources")

_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

DEFAULT_SYSTEM_PROMPT_FILE = "minimax-music3-production.txt"
DEFAULT_USER_PROMPT = (
    "Instrumental Progressive House with melodic and subtle trance influences, highly "
    "atmospheric and spacious, driven by memorable signature motifs and distinctive recurring "
    "synth riffs. Emotional, smooth, modern, with strong progression and evolving layers. "
    "create a 4\u20135 minutes long melodic story in the track."
)


def _bundled_system_prompt_path() -> Path:
    return Path(__file__).resolve().parent / "prompts" / "system" / DEFAULT_SYSTEM_PROMPT_FILE


def load_bundled_default_system_prompt() -> str:
    """Load the shipped production prompt from its canonical library file.

    Keeping the large prompt in one file avoids silent drift between the default
    text shown in the node and the bundled system-prompt library.  A concise
    fallback keeps node discovery alive if an installation is incomplete; file
    mode will still surface the precise missing-file error at execution time.
    """
    path = _bundled_system_prompt_path()
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            raise ValueError("bundled system prompt is empty")
        return text
    except Exception as exc:
        _LOGGER.warning("Could not load bundled default system prompt %s: %s", path, exc)
        return (
            "You are a music-production prompt rewriter for MiniMax Music 3. "
            "Return only [Caption], [Lyrics], [Title], and [Image_Prompt], in that order."
        )


# Loaded once at import time, exactly like the previous node-local constant.
DEFAULT_SYSTEM_PROMPT = load_bundled_default_system_prompt()


def clean_source_name(value: str) -> str:
    """Portable source/basename component (Windows-invalid characters replaced)."""
    name = _WINDOWS_INVALID.sub("_", (value or "").strip()).strip(" .")
    return name or "song"


def new_seed() -> int:
    """Random seed below signed int64 (backend/serialization safe)."""
    return secrets.randbelow(2**63 - 1)


def read_prompt_text(path: Path) -> str:
    """Decode a prompt file: UTF-8 (with/without BOM), then CP1252 fallback."""
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise UnicodeDecodeError("utf-8", data, 0, 1, f"Could not decode {path}")


def resolve_prompt_directory(value: str, *, error_prefix: str) -> Path:
    """Expand and resolve a prompt directory, relative to the ComfyUI base path.

    ``error_prefix`` keeps each node's historic message (the two callers named
    themselves differently).
    """
    raw = os.path.expandvars(os.path.expanduser((value or "").strip()))
    if not raw:
        raise ValueError(f"{error_prefix}: prompt_directory is empty.")
    p = Path(raw)
    if not p.is_absolute():
        try:
            import folder_paths

            p = Path(folder_paths.base_path) / p
        except Exception:
            p = Path.cwd() / p
    return p.resolve()


def normalize_extensions(extensions: str) -> Set[str]:
    """Parse a comma-separated extension list into a set of ``.ext`` strings."""
    allowed: Set[str] = set()
    for ext in (extensions or "").split(","):
        ext = ext.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        allowed.add(ext)
    return allowed


def iter_prompt_files(
    directory: Path,
    allowed: Iterable[str],
    recursive: bool,
    *,
    relative_sort: bool,
) -> List[Path]:
    """Return the prompt files below *directory* in the caller's historic order.

    ``relative_sort=True`` matches the legacy loader (path relative to the
    directory); ``False`` matches the rich source (absolute path).  Both are
    deterministic; the difference is preserved rather than normalised.
    """
    allowed = set(allowed)
    iterator = directory.rglob("*") if recursive else directory.glob("*")
    files = [p for p in iterator if p.is_file() and p.suffix.lower() in allowed]
    if relative_sort:
        return sorted(files, key=lambda p: str(p.relative_to(directory)).lower())
    return sorted(files, key=lambda p: str(p).lower())


def iter_variants(
    entries: Sequence[Dict[str, Any]],
    *,
    song_count: int,
    seed_mode: str,
    base_seed: int,
    count_of: Callable[[Dict[str, Any]], int],
) -> Iterator[Tuple[Dict[str, Any], int, int, int, int]]:
    """Yield ``(entry, variant, count, seed, global_index)`` in generation order.

    Seeds follow the historic rule exactly: a fresh random seed per song, or
    ``(base_seed + global_index) % (2**63 - 1)`` where ``global_index`` counts
    across *all* entries (not per file).  ``count_of`` carries each caller's
    ``[Count]`` policy.
    """
    global_index = 0
    for entry in entries:
        count = int(count_of(entry))
        for variant in range(1, count + 1):
            if seed_mode == "random_each_song":
                seed = new_seed()
            else:
                seed = (int(base_seed) + global_index) % (2**63 - 1)
            yield entry, variant, count, seed, global_index
            global_index += 1
