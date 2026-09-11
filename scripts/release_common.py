"""Shared selection and privacy rules for the release tooling.

``package_release.py`` and ``validate_release.py`` each had their own copy of
the archive selection and the privacy patterns.  They disagreed: the packager's
Windows-path pattern matched a real single-backslash path while the validator's
required doubled backslashes (so it could never fire), and the packager included
generated release assets from ``dist/`` in a new ZIP.  Both now use this module.

Nothing here imports ComfyUI, Torch or the toolkit: it is pure path/text logic.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set, Tuple

# --- archive selection ------------------------------------------------------

# VCS state, caches and build output.  ``dist`` holds the generated release
# assets themselves - a re-packaged ZIP must not swallow the previous build.
ARCHIVE_EXCLUDED_PARTS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist",
}
ARCHIVE_EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}
# Local-only handoff files: present on the maintainer machine, never pushed and
# never published.
LOCAL_ONLY_NAMES = {"KONTEXT.md", "PROJECT_STATE.md"}

# Maintainer planning documents that stay out of every release artifact (the
# GitHub ZIP and the Comfy Registry package) but may still live under version
# control.  REFACTOR-PLAN.md and IMPROVE-TODO.md were explicitly excluded here
# by the maintainer: internal working documents stay out of the published
# package but may remain under version control (they are not in .gitignore).
PACKAGING_EXCLUDED_NAMES = LOCAL_ONLY_NAMES | {"REFACTOR-PLAN.md", "IMPROVE-TODO.md"}

ARCHIVE_EXCLUDED_NAMES = PACKAGING_EXCLUDED_NAMES | {"SHA256SUMS.txt"}


def archive_should_include(root: Path, path: Path) -> bool:
    """Return whether *path* belongs in a release archive built from *root*."""
    rel = path.relative_to(root)
    if any(part in ARCHIVE_EXCLUDED_PARTS for part in rel.parts):
        return False
    if path.suffix.lower() in ARCHIVE_EXCLUDED_SUFFIXES:
        return False
    if path.name in ARCHIVE_EXCLUDED_NAMES:
        return False
    return True


# --- privacy / placeholder scan --------------------------------------------

TEXT_EXTENSIONS = {".py", ".js", ".md", ".txt", ".toml", ".json", ".yml", ".yaml", ".bat"}

# Generic leak patterns only: the repository deliberately contains the public
# author name/GitHub URL, so those are not treated as privacy violations.
PRIVATE_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"']+", re.I),
    re.compile(r"[A-Za-z]:/Users/[^/\s\"']+", re.I),
    re.compile(r"(?:192\.168\.|10\.\d+\.\d+\.|172\.(?:1[6-9]|2\d|3[01])\.)\d+\.\d+"),
    re.compile("YOUR_" + "GITHUB_USERNAME|YOUR_" + "COMFY_PUBLISHER_ID"),
)

SCAN_SKIPPED_PARTS = {".git", "__pycache__", "dist"}


def privacy_hits(
    root: Path,
    *,
    extensions: Optional[Iterable[str]] = None,
    skip_names: Optional[Set[str]] = None,
    published_only: bool = False,
) -> List[Tuple[str, str]]:
    """Return ``(relative_path, pattern)`` for every privacy-pattern hit.

    ``published_only=True`` also applies the archive selection, so the scan
    reports exactly what a release would contain and never trips over the
    local-only handoff files on the maintainer machine.
    """
    allowed = {extension.lower() for extension in (extensions or TEXT_EXTENSIONS)}
    skip_names = skip_names if skip_names is not None else (LOCAL_ONLY_NAMES if published_only else set())
    hits: List[Tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        if any(part in SCAN_SKIPPED_PARTS for part in path.parts):
            continue
        if path.name in skip_names:
            continue
        if published_only and not archive_should_include(root, path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in PRIVATE_PATTERNS:
            if pattern.search(text):
                hits.append((str(path.relative_to(root)), pattern.pattern))
                break
    return hits
