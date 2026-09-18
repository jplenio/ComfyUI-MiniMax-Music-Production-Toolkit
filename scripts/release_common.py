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
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", ".scratch",
}
ARCHIVE_EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}
# Local-only handoff files: present on the maintainer machine, never pushed and
# never published. Matched by file NAME, so they stay excluded wherever they live
# (they sit in docs/ since the 2026-09-17 documentation tidy-up).
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


# --- branding assets ---------------------------------------------------------

# Text files that may refer to an image. A branding asset nothing points at is dead
# weight in the release archive.
BRANDING_REFERENCE_PATTERNS = ("*.md", "*.toml", "*.html")


def unreferenced_branding_assets(root: Path, directory: str = "assets/branding") -> List[str]:
    """Branding files that no document mentions.

    The 3.1.1 preparation packed ``banner-old.png`` and ``icon-old.png`` - superseded
    art kept as a backup - into the release archive, because the packager walks the
    working tree and nothing said those files were unused. A leftover whose name still
    looks plausible is exactly the kind of file that needs a machine to notice it.
    """
    folder = root / directory
    if not folder.is_dir():
        return []
    names = sorted(path.name for path in folder.iterdir() if path.is_file())
    mentioned: List[str] = []
    for pattern in BRANDING_REFERENCE_PATTERNS:
        for path in root.rglob(pattern):
            if any(part in SCAN_SKIPPED_PARTS for part in path.parts):
                continue
            mentioned.append(path.read_text(encoding="utf-8", errors="replace"))
    return [name for name in names if not any(name in text for text in mentioned)]


# --- requirements installability --------------------------------------------

# Every file a user is told to pass to ``pip install -r``.
REQUIREMENT_FILES = ("requirements.txt", "requirements-whisper.txt")


def requirement_parse_error(path: Path) -> Optional[str]:
    """Return why pip cannot read ``path``, or ``None`` when it can.

    pip is the consumer of these files, so pip decides what is valid. Both
    ``validate_release`` and the tests used to read them by hand, skipping blanks
    and ``#`` comments and taking everything else as a package name - so a Python
    docstring header looked merely like an odd name while pip refused the file with
    an ``Invalid requirement`` error naming that header, and the first step of the
    3.1.0 release workflow died before a single test ran. The hand-rolled readers
    cannot see that class of error; this one asks pip itself.

    It fails closed: if pip cannot be imported, that is reported as an error rather
    than accepted as a pass.
    """
    try:
        from pip._internal.req.constructors import install_req_from_line
        from pip._internal.req.req_file import parse_requirements
    except ImportError as error:  # pragma: no cover - pip ships with every install
        return f"pip is not importable, so installability cannot be verified: {error}"
    try:
        entries = list(parse_requirements(str(path), session=None))
    except Exception as error:  # newer pip releases validate while parsing
        return f"{type(error).__name__}: {error}"
    if not entries:
        return "the file declares no requirements"

    # ``parse_requirements`` is lazy on older pip releases: 22.x strips the comments
    # and hands back the raw line, leaving the validation to the installer. So each
    # entry is put through the same constructor the install command uses - the step
    # that produced the real failure message - which behaves identically on every
    # pip version instead of only on the ones that parse eagerly.
    for entry in entries:
        line = getattr(entry, "requirement", None)
        if not isinstance(line, str):
            continue  # already a parsed requirement, so pip accepted it above
        try:
            install_req_from_line(line, comes_from=str(path))
        except Exception as error:
            return f"{type(error).__name__}: {error}"
    return None
