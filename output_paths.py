"""Output path planning shared by the savers, the JSON writer and the preview tools.

This module is deliberately dependency-light: it must be importable by the
preview/diagnostic scripts without pulling in audio codecs, Torch, Pillow or any
node class.  It owns exactly three concepts:

* date-macro expansion (``%date:yyyy-MM-dd%``) - preserved byte-for-byte,
  including the expansion of every macro against one timestamp;
* prefix resolution (absolute/UNC vs. relative-to-ComfyUI-output);
* collision selection (``overwrite`` / ``error_if_exists`` / ``auto_increment``).

Error messages keep a caller-supplied ``error_prefix`` so the audio and artwork
savers continue to report their own node names.

Absolute-path policy: a path is "absolute on any platform" when the host
``os.path.isabs`` says so *or* it is a Windows drive path (``C:\\``/``C:/``),
a UNC path (``\\\\server\\share``) or a ``//``-rooted path.  On Windows a single
leading backslash is already covered by ``os.path.isabs``; on POSIX it is a
legal relative filename and stays contained in the output directory.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
from typing import Any, Callable, Dict, Optional

from .filename_utils import apply_filename_mode

DATE_MACRO_RE = re.compile(r"%date:([^%]+)%")
_WIN_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")

_JAVAISH_DATE_REPLACEMENTS = (
    ("yyyy", "%Y"), ("yy", "%y"),
    ("MM", "%m"), ("dd", "%d"),
    ("HH", "%H"), ("mm", "%M"), ("ss", "%S"),
)

COLLISION_MODES = ("overwrite", "error_if_exists", "auto_increment")

MAX_AUTO_INCREMENT = 1_000_000


def javaish_date_to_strftime(pattern: str) -> str:
    """Translate an ICU/Java-ish date pattern into ``strftime`` tokens."""
    out = pattern
    for src, dst in _JAVAISH_DATE_REPLACEMENTS:
        out = out.replace(src, dst)
    return out


def expand_date_macros(value: str, now: Optional[_dt.datetime] = None) -> str:
    """Replace every ``%date:<pattern>%`` with the formatted current time.

    All macros in one call use the same timestamp; an invalid pattern is left
    untouched instead of raising.
    """
    moment = now or _dt.datetime.now()

    def repl(match: "re.Match[str]") -> str:
        pattern = match.group(1)
        try:
            return moment.strftime(javaish_date_to_strftime(pattern))
        except Exception:
            return match.group(0)

    return DATE_MACRO_RE.sub(repl, value or "")


def is_abs_any_platform(path: str) -> bool:
    """Return True when *path* is absolute on the host or on Windows/POSIX."""
    if not path:
        return False
    return (
        os.path.isabs(path)
        or bool(_WIN_ABS_RE.match(path))
        or path.startswith("\\\\")
        or path.startswith("//")
    )


def comfy_output_dir() -> str:
    """Return ComfyUI's output directory, falling back to ``./output``."""
    try:
        import folder_paths

        return folder_paths.get_output_directory()
    except Exception:
        return os.path.join(os.getcwd(), "output")


def resolve_prefix(prefix: str, *, error_prefix: str = "Output") -> str:
    """Expand macros and resolve *prefix* to an absolute output path.

    Absolute inputs (including explicit drive/UNC paths) are normalized and
    returned as-is; relative inputs resolve below ComfyUI's output directory
    and may not escape it.
    """
    raw = (prefix or "").strip()
    if not raw:
        raise ValueError(f"{error_prefix}: filename_prefix is empty.")
    raw = expand_date_macros(raw)
    raw = os.path.expanduser(os.path.expandvars(raw))
    # ComfyUI workflows are exchanged between Windows and Linux.  A saved
    # relative prefix may therefore contain Windows separators even when the
    # current runner is POSIX.  Normalize those separators before joining the
    # relative path.  A *single* leading backslash remains relative on POSIX
    # by policy (UNC paths with two backslashes become // and stay absolute).
    if os.name != "nt" and raw.startswith("\\") and not raw.startswith("\\\\"):
        raw = "\\" + raw[1:].replace("\\", "/")
    else:
        raw = raw.replace("\\", "/")
    if is_abs_any_platform(raw):
        return os.path.normpath(raw)

    root = os.path.abspath(comfy_output_dir())
    candidate = os.path.abspath(os.path.join(root, raw))
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise ValueError(
                f"{error_prefix}: relative filename_prefix may not escape the ComfyUI output directory."
            )
    except ValueError:
        raise ValueError(f"{error_prefix}: invalid relative filename_prefix.")
    return candidate


def pick_path(
    prefix: str,
    ext: str,
    collision_mode: str,
    *,
    error_prefix: str = "Output",
    exists: Optional[Callable[[str], bool]] = None,
) -> str:
    """Select the output path for ``<prefix>.<ext>`` under *collision_mode*.

    ``overwrite`` replaces, ``error_if_exists`` raises and ``auto_increment``
    appends ``_001``, ``_002``, ... until a free name is found.  ``exists`` is
    injectable for tests and previews that must not touch the filesystem.
    """
    exists = exists or os.path.exists
    target = f"{prefix}.{ext}"
    if collision_mode == "overwrite":
        return target
    if collision_mode == "error_if_exists":
        if exists(target):
            raise FileExistsError(f"{error_prefix}: file exists: {target}")
        return target
    if collision_mode != "auto_increment":
        raise ValueError(f"{error_prefix}: invalid collision mode '{collision_mode}'.")
    if not exists(target):
        return target
    for i in range(1, MAX_AUTO_INCREMENT):
        candidate = f"{prefix}_{i:03d}.{ext}"
        if not exists(candidate):
            return candidate
    raise RuntimeError(f"{error_prefix}: no free auto-increment filename found.")


def preview_output_files(
    filename_prefix: str,
    format: str,
    collision_mode: str = "auto_increment",
    filename_mode: str = "album - title",
    tags_meta: Optional[Dict[str, Any]] = None,
    title: str = "",
    *,
    error_prefix: str = "Output",
    exists: Optional[Callable[[str], bool]] = None,
) -> Dict[str, Any]:
    """Non-writing preview of the exact path a saver would produce.

    Mirrors the naming pipeline (``resolve_prefix`` -> ``apply_filename_mode``
    -> ``pick_path``) without creating directories or files, so a batch can be
    checked for output collisions before anything is written.  Returns the
    planned path, its existence state and whether the saver would raise instead
    of writing.
    """
    exists = exists or os.path.exists
    resolved_prefix = resolve_prefix(filename_prefix, error_prefix=error_prefix)
    resolved_prefix = apply_filename_mode(
        resolved_prefix, tags_meta, title, filename_mode, error_prefix=error_prefix
    )
    ext = str(format or "").strip().lower().lstrip(".") or "flac"
    base_target = f"{resolved_prefix}.{ext}"
    present = exists(base_target)
    planned = base_target
    would_raise = False
    if collision_mode == "auto_increment":
        if present:
            planned = pick_path(resolved_prefix, ext, collision_mode, error_prefix=error_prefix, exists=exists)
            present = exists(planned)
    elif collision_mode == "error_if_exists":
        would_raise = present
        if would_raise:
            planned = ""
    return {
        "kind": ext,
        "directory": os.path.dirname(resolved_prefix),
        "basename": os.path.basename(planned or base_target),
        "path": planned,
        "exists": present,
        "would_raise": would_raise,
    }
