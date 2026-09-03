#!/usr/bin/env python3
"""Annotate bundled user prompt files with structured metadata front-matter.

The metadata block is optional and consumed by ``MiniMaxStructuredPromptV20``
to prefill its structured fields.  This helper derives safe values from the
file path and the prompt text itself:

- Genre      -> capitalized library directory name
- Lyrics     -> ``instrumental`` / ``sparse`` / ``yes`` from the filename
- Language   -> ``Deutsch`` when the filename contains ``german``
- Tempo      -> first ``NNN BPM`` match in the prompt text
- Key        -> first ``A minor``-style key/scale match in the prompt text
- Length     -> first ``N-N minutes``-style duration match in the prompt text

The script is idempotent: files that already contain a metadata block are
left untouched.  Use ``--dry-run`` to preview changes without writing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_PROMPTS = ROOT / "prompts" / "user"

_GENRE_ACRONYMS = {"edm": "EDM"}

_BPM_RE = re.compile(r"\b(\d{2,3})\s*(?:-|–|to|—)?\s*BPM\b", re.IGNORECASE)
_KEY_RE = re.compile(
    r"\bkey\s+of\s+([A-G][#b]?\s*(?:major|minor))|([A-G][#b]?\s*(?:major|minor))\b",
    re.IGNORECASE,
)
_LENGTH_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:-|–|to|—)\s*(\d+(?:\.\d+)?)\s*(?:min(?:ute)?s?|min\.?)\b", re.IGNORECASE)


def has_front_matter(text: str) -> bool:
    first = text.splitlines()[0].strip() if text.strip() else ""
    return first == "---"


def derive_metadata(relative_path: Path, text: str) -> dict:
    parts = relative_path.parts
    genre_dir = parts[0] if len(parts) > 1 else ""
    stem = relative_path.stem.lower()

    metadata = {}
    if genre_dir:
        metadata["Genre"] = _GENRE_ACRONYMS.get(genre_dir.lower(), genre_dir.replace("-", " ").title())
    if "instrumental" in stem:
        metadata["Lyrics"] = "instrumental"
    elif "sparse-vocal" in stem or "sparse" in stem:
        metadata["Lyrics"] = "sparse"
    elif "vocal" in stem:
        metadata["Lyrics"] = "yes"
    if "german" in stem:
        metadata["Language"] = "Deutsch"

    bpm = _BPM_RE.search(text)
    if bpm:
        metadata["Tempo"] = f"{bpm.group(1)} BPM"
    key = _KEY_RE.search(text)
    if key:
        metadata["Key"] = (key.group(1) or key.group(2)).strip()
    length = _LENGTH_RE.search(text)
    if length:
        metadata["Length"] = f"{length.group(1)}-{length.group(2)} minutes"

    return metadata


def build_block(metadata: dict) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="preview changes without writing files")
    args = parser.parse_args()

    changed = 0
    skipped = 0
    for path in sorted(USER_PROMPTS.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".txt", ".md", ".prompt"}:
            continue
        text = path.read_text(encoding="utf-8-sig").strip()
        if has_front_matter(text):
            skipped += 1
            continue
        relative = path.relative_to(USER_PROMPTS)
        metadata = derive_metadata(relative, text)
        if not metadata:
            skipped += 1
            continue
        block = build_block(metadata)
        new_text = block + "\n\n" + text + "\n"
        changed += 1
        if args.dry_run:
            print(f"[dry-run] {relative}: {', '.join(f'{k}={v}' for k, v in metadata.items())}")
            continue
        path.write_text(new_text, encoding="utf-8", newline="\n")

    print(f"annotate_prompt_metadata: {changed} file(s) annotated, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
