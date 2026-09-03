#!/usr/bin/env python3
"""Normalize bundled prompt descriptions to the structured metadata format.

Ensures every prompt file follows the new structure completely:

- Values that live in the metadata block (Song length, Tempo/BPM) no longer
  appear in the free description text.
- Files whose description contained a duration but no ``Length`` metadata get
  the value added to the metadata block (normalized to the 5-minute cap).
- Redundant standalone "Instrumental." labels are removed when the Lyrics
  field already says ``instrumental``.

Idempotent: running it twice changes nothing.  Run from the repository root:

    python scripts/normalize_prompt_descriptions.py [--write]

Without --write it only prints what would change.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_DIR = ROOT / "prompts" / "user"

pkg_name = "_prompt_normalize_pkg"
pkg = types.ModuleType(pkg_name)
pkg.__path__ = [str(ROOT)]
sys.modules[pkg_name] = pkg
for module_name in ("toolkit_logging", "prompt_metadata"):
    full = f"{pkg_name}.{module_name}"
    spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

prompt_metadata = sys.modules[f"{pkg_name}.prompt_metadata"]
parse_prompt_front_matter = prompt_metadata.parse_prompt_front_matter
STRUCTURED_FIELDS = prompt_metadata.STRUCTURED_FIELDS

# "4:00–5:00 minutes", "4–5 Minuten", "5:00 minutes", "around 4:30-5:00",
# "3:30-4:00 minutes", "4–5 Minuten Länge"
DURATION_RE = re.compile(
    r"(?:(?:around|approx\.?|ca\.?|total length (?:around|of) )\s*)?"
    r"(?:\d{1,2}:\d{2}|\d{1,3})"
    r"(?:\s*[\u2013\u2014-]\s*(?:\d{1,2}:\d{2}|\d{1,3}))?"
    # "minuten" must come before "minutes?" or the latter eats "Minute"
    # and leaves a dangling "n Länge".  The unit is optional so colon-style
    # ranges like "4:30-5:00" are recognized too; bare number ranges without
    # a unit or colon are rejected below to avoid false positives.
    r"(?:\s*(?:minuten|minutes?|min\.?))?(?:\s+L(?:ä|ae)nge)?\s*[.;]?",
    re.IGNORECASE,
)
_DURATION_UNIT_RE = re.compile(r"(?:minuten|minutes?|min\.?)", re.IGNORECASE)
BPM_RE = re.compile(r"\b\d{2,3}\s*(?:[\u2013\u2014-]\s*\d{2,3})?\s*BPM\b[.,]?", re.IGNORECASE)
INSTRUMENTAL_LABEL_RE = re.compile(r"(?:^|\s)Instrumental\s*[.;]\s*", re.IGNORECASE)
LEADING_INSTRUMENTAL_RE = re.compile(r"^Instrumental[\s.,:]+", re.IGNORECASE)


def _minutes_to_label(value: str) -> str:
    """Map a matched duration phrase to a canonical Length metadata value."""
    text = value.replace(",", ".").lower()
    numbers = re.findall(r"\d{1,2}(?::\d{2})?", text)
    if not numbers:
        return ""
    converted = []
    for num in numbers:
        if ":" in num:
            minutes, seconds = num.split(":")
            converted.append(int(minutes) + int(seconds) / 60.0)
        else:
            converted.append(int(num))
    low = max(0.5, min(converted))
    high = min(5.0, max(converted))  # hard 5-minute cap
    import math as _math
    low_label = _math.floor(low)
    high_label = _math.ceil(high)
    if high <= 1.0:
        return "1 minute"
    if low_label == high_label:
        return f"{high_label} minutes"
    return f"{low_label}-{high_label} minutes"


def normalize_file(path: Path, write: bool) -> bool:
    text = path.read_text(encoding="utf-8-sig")
    original_text = text

    # Repair artifacts of an earlier normalization pass:
    # - the metadata key must be "Length" (the display label "Target length"
    #   is not recognized by the front-matter parser),
    # - dangling pieces of German "Minuten Länge" phrases,
    # - orphan tempo numbers left behind by range phrases like "130-138 BPM".
    text = re.sub(r"(?m)^Target length:", "Length:", text)
    fields, description = parse_prompt_front_matter(text)
    description = re.sub(r"\s+n\s+L(?:ä|ae)nge\s*[.;]", " ", description)
    description = re.sub(r"(?<=[.])\s+\d{2,3}\s*$", "", description)
    description = re.sub(r"\s+", " ", description).strip()
    base_fields = fields.copy()
    base_description = description

    # 1. Move durations into the metadata block; remove them from the text.
    accepted_spans = []
    for match in DURATION_RE.finditer(description):
        phrase = match.group(0)
        # Only treat as a duration when a unit word or a colon time is present;
        # a bare number range (e.g. "2-3 layers") is not a duration.
        if ":" in phrase or _DURATION_UNIT_RE.search(phrase):
            accepted_spans.append(match.span())
    label = ""
    for start, end in accepted_spans:
        candidate = _minutes_to_label(description[start:end])
        if candidate:
            label = candidate
            break
    if accepted_spans:
        cleaned = []
        cursor = 0
        for start, end in accepted_spans:
            cleaned.append(description[cursor:start])
            cursor = end
        cleaned.append(description[cursor:])
        description = re.sub(r"\s+", " ", " ".join(cleaned)).strip()
    if label and not fields.get("length"):
        fields["length"] = label

    # 2. Remove BPM mentions that duplicate the Tempo metadata.
    if fields.get("tempo"):
        description = BPM_RE.sub(" ", description)
        description = re.sub(r"\s+", " ", description).strip()

    # 3. Remove redundant standalone "Instrumental." labels when the Lyrics
    #    field already says instrumental.
    if (fields.get("lyrics") or "").lower() == "instrumental":
        description = LEADING_INSTRUMENTAL_RE.sub("", description)
        description = INSTRUMENTAL_LABEL_RE.sub(" ", description)

    # 4. Cleanup artifacts and orphan separators.
    description = re.sub(r"\s+", " ", description).strip(" -–—.")
    description = re.sub(r"^\s*[\u2013\u2014-]+\s*", "", description)
    description = re.sub(r"(\s*[\u2013\u2014-]\s*)+$", "", description)
    # A removed duration phrase can leave a dangling article:
    # "...and a 4:30-5:00." -> "...and a Add sparse lyrics".
    description = re.sub(r"(?<=\band)\s+a\s+(?=[A-Z])", " ", description)
    description = re.sub(r"(?<=,)\s+a\s+(?=[A-Z])", " ", description)
    # "...and Add sparse lyrics" -> "...and add sparse lyrics".
    description = re.sub(r"\band\s+Add\b", "and add", description)
    description = re.sub(r"\s+", " ", description).strip()
    if not description:
        description = "Free-form musical description."

    changed = (text != original_text) or (fields != base_fields) or (description != base_description)
    if not changed:
        return False

    if write:
        front_matter_keys = {
            "genre": "Genre", "tempo": "Tempo", "key": "Key", "lyrics": "Lyrics",
            "language": "Language", "voice": "Voice", "theme": "Theme", "length": "Length",
        }
        lines = ["---"]
        for field in STRUCTURED_FIELDS:
            if fields.get(field):
                lines.append(f"{front_matter_keys[field]}: {fields[field]}")
        lines.append("---")
        lines.append("")
        lines.append(description)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="apply the changes (default: dry run)")
    args = parser.parse_args()

    changed = []
    for path in sorted(USER_DIR.rglob("*.txt")):
        if normalize_file(path, write=args.write):
            changed.append(path.relative_to(USER_DIR).as_posix())

    mode = "updated" if args.write else "would update"
    print(f"{mode} {len(changed)} prompt file(s):")
    for name in changed:
        print(f"  - {name}")
    if not args.write and changed:
        print("\nRe-run with --write to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
