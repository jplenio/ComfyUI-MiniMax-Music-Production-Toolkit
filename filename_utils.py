from __future__ import annotations

import os
import re
from typing import Any, Mapping

_FILENAME_INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows device names are reserved regardless of extension (CON.txt is just
# as invalid as CON); a trailing underscore makes the component legal again.
_WINDOWS_RESERVED_RE = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$", re.IGNORECASE)

# Keep one filename component well below the Windows MAX_PATH component limit
# (255 UTF-16 units) with headroom for suffixes such as "_001" or "_b001".
MAX_COMPONENT_LENGTH = 180


def safe_filename_component(value: str) -> str:
    """Return one portable filename component for Windows/macOS/Linux.

    Invalid characters are replaced, trailing dots/spaces removed, Windows
    reserved device names neutralized and over-long titles truncated on a
    character boundary.
    """
    text = _FILENAME_INVALID_RE.sub("_", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" .")
    if len(text) > MAX_COMPONENT_LENGTH:
        text = text[:MAX_COMPONENT_LENGTH].rstrip(" .")
        try:
            text.encode("utf-8")
        except UnicodeEncodeError:
            # Never leave a lone surrogate behind after truncation.
            text = text[:-1]
    if not text or not text.strip("_"):
        return "song"
    if _WINDOWS_RESERVED_RE.match(text.split(".")[0]):
        # Neutralize before the first extension: "CON.txt" -> "CON_.txt" so
        # the base name is no longer the reserved device name.
        text = text.replace(".", "_.", 1) if "." in text else text + "_"
    return text


def apply_filename_mode(
    resolved_prefix: str,
    tags_meta: Mapping[str, Any] | None,
    title: str,
    filename_mode: str,
    *,
    error_prefix: str = "Output",
) -> str:
    """Replace only the basename while preserving the directory from a prefix.

    The function is shared by the audio and artwork savers so ``album - title``
    produces exactly the same basename across FLAC, MP3, WAV, JPG and the
    centralized production JSON naming convention.
    """
    mode = str(filename_mode or "album - title").strip().lower()
    directory = os.path.dirname(resolved_prefix)
    fallback_base = os.path.basename(resolved_prefix)
    meta = tags_meta or {}

    tag_title = str(meta.get("title", "") or title or fallback_base).strip()
    album = str(meta.get("album", "") or "").strip()

    if mode == "prefix as provided":
        base = fallback_base
    elif mode == "title only":
        base = safe_filename_component(tag_title or fallback_base)
    elif mode == "album - title":
        clean_title = safe_filename_component(tag_title or fallback_base)
        clean_album = safe_filename_component(album) if album else ""
        base = f"{clean_album} - {clean_title}" if clean_album else clean_title
    else:
        raise ValueError(
            f"{error_prefix}: filename_mode must be "
            "'album - title', 'title only', or 'prefix as provided'."
        )

    return os.path.join(directory, base) if directory else base
