"""Load the YuE2 Cover Studio role prompts.

The studio keeps no large system prompt inside Python: the planner and the
transformer roles are ordinary UTF-8 files under ``resources/yue2/``.

They are deliberately **not** placed in ``prompts/system/``.  That directory is
the user-facing template library whose contents are offered in the
``system_prompt_file`` dropdown of the prompt nodes; an internal role prompt
listed there would pollute a public contract and confuse anyone who selected it
as a song template.  ``resources/`` holds fixed, code-owned text the same way
``docs/references/`` holds the ABC reference.

A short built-in copy is kept as a fallback so a partial checkout - code without
the ``resources/`` tree - still produces a usable prompt instead of an exception.
"""
from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
COVER_RESOURCE_DIR = PACKAGE_ROOT / "resources" / "yue2"

# Fixed, code-owned names: no user input ever reaches this path.
PLANNER_FILE = "cover-planner.txt"
TRANSFORMER_FILE = "abc-transformer.txt"

MAX_PROMPT_BYTES = 64 * 1024

# Only used when the bundled file cannot be read. The files on disk are the
# authoritative text; keeping the fallback short avoids two long copies drifting.
_PLANNER_FALLBACK = """\
You are the cover planner of a YuE2 cover studio. You read one existing song's
score analysis and answer with a short, concrete production plan. You do not
write music notation and you do not write lyrics. You output a single JSON object
with the keys preserve, change, target and warnings, and nothing else."""

_TRANSFORMER_FALLBACK = """\
You are the score transformer of a YuE2 cover studio. You receive a native
two-voice ABC score, a structured interpretation profile and a cover plan, and
you return one revised score in the same dialect. You output a single JSON object
with the keys abc, changes and warnings, and nothing else."""


def load_cover_prompt(name: str, fallback: str) -> str:
    """The text of one ``resources/yue2/<name>`` role prompt."""
    path = COVER_RESOURCE_DIR / name
    try:
        if path.stat().st_size > MAX_PROMPT_BYTES:
            return fallback.strip()
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return fallback.strip()
    return text.strip() or fallback.strip()


def planner_role() -> str:
    return load_cover_prompt(PLANNER_FILE, _PLANNER_FALLBACK)


def transformer_role() -> str:
    return load_cover_prompt(TRANSFORMER_FILE, _TRANSFORMER_FALLBACK)


__all__ = [
    "COVER_RESOURCE_DIR",
    "PLANNER_FILE",
    "TRANSFORMER_FILE",
    "load_cover_prompt",
    "planner_role",
    "transformer_role",
]
