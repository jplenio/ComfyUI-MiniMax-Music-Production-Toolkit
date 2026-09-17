"""Validate model-produced ABC before YuE2 ever sees it.

The rule this module exists for: a language model is never the only source of
truth for the score.  Whatever the transformer stage returns is extracted,
structurally checked against the bounded native dialect and compared with its
source before it is allowed to travel on to ``MusicGeneration``.

Two independent checks are used:

1. :func:`validate_abc` - header presence, markdown fences, prose leakage,
   empty voice blocks and the strict structural parse of
   :mod:`third_party.yue2_abc` (the vendored upstream portable checker).
2. :func:`compare_with_source` - which musical invariants actually changed,
   reported per voice instead of silently accepted.

No heavy dependency is introduced: the vendored checker is standard library
only and already ships with the toolkit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List, Optional, Sequence, Tuple

from .third_party.yue2_abc import AbcError, compare as abc_compare, parse_abc

PACKAGE_ROOT = Path(__file__).resolve().parent

# Curated, compact YuE2 ABC rule sheet.  It is injected verbatim into the
# transformer's system prompt, so the model always receives an explicit local
# reference instead of relying on its own memory of ABC.
ABC_COVER_RULES_PATH = PACKAGE_ROOT / "docs" / "references" / "YUE2_ABC_COVER_RULES.md"
# The verified upstream snapshot the curated sheet is derived from.
ABC_UPSTREAM_REFERENCE_PATH = PACKAGE_ROOT / "docs" / "references" / "YUE2_ABC_REFERENCE.md"

_FENCE_RE = re.compile(r"^\s*```[A-Za-z0-9_+-]*\s*$", re.M)
_X_HEADER_RE = re.compile(r"^X:\s*\d+\s*$", re.M)
_FIELD_RE = re.compile(r"^([A-Za-z]):(.*)$")
_MUSIC_LINE_HINT_RE = re.compile(r"\|\s*$")
_HEADER_FIELDS = ("X", "T", "M", "L", "Q", "K")
_VOICE_DEFINITION_RE = re.compile(r"^V:\s*(?P<id>[^\s=]+)\s*(?P<rest>.*)$")
_VOICE_SWITCH_RE = re.compile(r"^V:\s*(?P<id>[^\s=]+)\s*$")
_SECTION_RE = re.compile(r"^%\s+(?P<label>.+?)\s*$")

# A compact fallback for the unlikely case that the documentation file is not
# shipped next to the code (for example a partial source checkout).  It carries
# the rules that actually change model behaviour; the full curated sheet is the
# file on disk.
_BUILTIN_RULES = """\
YuE2 native ABC dialect (bounded, two monophonic voices):
- Required header, in this order and with no field between them:
  X:1 / T: (blank) / M:4/4 / L:1/32 / Q:1/4=<integer BPM> /
  V: Vocal clef=treble name="Vocal Melody" snm="Vocal" /
  V: Ins clef=treble name="Ins Melody" snm="Inst." / K:<standard major or minor key>
- The body groups one to four measures: a "% section" comment, then a "V: Vocal"
  block and a "V: Ins" block with identical measure counts. Both parts are
  monophonic. Chord symbols are quoted and belong in Vocal, even while it rests.
- Music lines end with a plain "|". Supported durations: 1, 2, 3, 4, 6, 8, 12,
  16, 24, 32, 48. Express 10 units as "C8-C2". Full-measure rests are Z, Z2, Z3, Z4.
- A tie "-" joins equal sounding pitches and merges them into one note.
- Accidentals ^ _ = ^^ __ stay active through the bar and propagate by letter
  across octaves. A meter or key change starts a new group and needs matching
  M:/K: fields in both voices.
- Not supported: tuplets, grace notes, note stacks, repeats, slurs, decorations,
  w: lyric fields, extra voices, and any chord quality outside
  major, m, dim, aug, 7, maj7, m7, dim7, m7b5, sus4, sus2, 6, m6, 7sus4, m(maj7).
"""


@dataclass(frozen=True)
class AbcValidation:
    """Outcome of one validation, safe to serialize into a debug output."""

    ok: bool
    abc: str
    errors: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    facts: Dict[str, object] = field(default_factory=dict)

    def as_report(self) -> Dict[str, object]:
        return {
            "schema": "cover_abc_validation_v1",
            "valid": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "facts": self.facts,
        }


def abc_reference(path: Optional[Path] = None) -> str:
    """The explicit local ABC/YuE2 reference injected into the system prompt."""
    target = Path(path) if path is not None else ABC_COVER_RULES_PATH
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return _BUILTIN_RULES.strip()
    body = _strip_front_matter(text).strip()
    return body or _BUILTIN_RULES.strip()


def _strip_front_matter(text: str) -> str:
    """Drop a leading Markdown title so the injected block starts with content."""
    lines = str(text).replace("\r\n", "\n").split("\n")
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("#")):
        lines.pop(0)
    return "\n".join(lines)


def extract_abc(text: str) -> Tuple[str, List[str]]:
    """Pull the score out of a possibly chatty model answer.

    Returns ``(abc, notes)``.  Markdown fences are removed and everything before
    the first ``X:`` header is discarded; the notes explain what was dropped so
    the caller can record it rather than silently accepting it.
    """
    notes: List[str] = []
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return "", ["empty response"]
    if _FENCE_RE.search(raw):
        notes.append("removed markdown code fence")
        raw = _FENCE_RE.sub("", raw)
    match = _X_HEADER_RE.search(raw)
    if match is None:
        return raw.strip("\n"), notes + ["no X: header found"]
    if raw[: match.start()].strip():
        notes.append("removed prose before the X: header")
    body = raw[match.start():]
    lines = body.split("\n")
    # Drop trailing prose: every real ABC line is a field, a voice switch, a
    # section comment or a music line ending in ``|``.  Cut back to the last
    # line that looks like one of those.
    end = len(lines)
    while end > 0 and not _looks_like_abc_line(lines[end - 1].strip()):
        end -= 1
    if end < len(lines) and any(line.strip() for line in lines[end:]):
        notes.append("removed prose after the score")
    return "\n".join(lines[:end]).rstrip() + "\n", notes


def _looks_like_abc_line(line: str) -> bool:
    if line.startswith("%"):
        return True
    if _FIELD_RE.match(line):
        return True
    return bool(_MUSIC_LINE_HINT_RE.search(line))


def section_labels(abc: str) -> List[str]:
    """The ``%`` structure comments in order, without their marker."""
    labels: List[str] = []
    for line in str(abc or "").splitlines():
        match = _SECTION_RE.match(line)
        if match:
            labels.append(match.group("label"))
    return labels


def validate_abc(text: str, source: Optional[str] = None) -> AbcValidation:
    """Structural validation of one score, with the source as extra context."""
    errors: List[str] = []
    warnings: List[str] = []
    abc, extract_notes = extract_abc(text)
    warnings.extend(extract_notes)
    abc = abc.strip("\n")

    if not abc.strip():
        return AbcValidation(False, "", ("The ABC score is empty.",), tuple(warnings), {})

    facts: Dict[str, object] = {"characters": len(abc), "lines": abc.count("\n") + 1}

    if _FENCE_RE.search(abc):
        errors.append("The ABC still contains a markdown code fence.")

    header, body = _split_header(abc)
    facts["header_fields"] = [match.group(1).upper() for match in
                              (_FIELD_RE.match(line) for line in header) if match]
    for name in _HEADER_FIELDS:
        if not any(line.startswith(f"{name}:") for line in header):
            errors.append(f"The ABC header is missing the required {name}: field.")
    voice_lines = [line for line in header if line.startswith("V:")]
    if len(voice_lines) < 2:
        errors.append("The ABC header must define both native voices (Vocal and Ins).")
    for line in voice_lines:
        match = _VOICE_DEFINITION_RE.match(line)
        if match and "=" not in line:
            errors.append(f"Voice '{match.group('id')}' is declared without its native voice definition.")

    prose = [line for line in body if line.strip() and not _looks_like_abc_line(line.strip())]
    if prose:
        errors.append(
            "The response contains text that is not ABC music notation "
            f"(first offender: {prose[0].strip()[:60]!r})."
        )

    empty_blocks = _empty_voice_blocks(body)
    if empty_blocks:
        errors.append("Empty voice block(s) without music: " + ", ".join(empty_blocks) + ".")

    score = None
    if not errors:
        try:
            score = parse_abc(abc)
        except AbcError as exc:
            errors.append(f"Native ABC structure check failed: {exc}")
        except (ValueError, ZeroDivisionError) as exc:  # pragma: no cover - defensive
            errors.append(f"Native ABC structure check failed: {exc}")

    if score is not None:
        facts.update({
            "bpm": score.bpm,
            "unit_length": str(score.unit),
            "duration_seconds": round(
                float(score.voices["Vocal"].time * 60 / score.bpm), 3),
            "measures": len(score.voices["Vocal"].bars),
            "vocal_notes": len(score.voices["Vocal"].notes),
            "ins_notes": len(score.voices["Ins"].notes),
            "chords": len(score.voices["Vocal"].chords),
            "sections": section_labels(abc),
        })
        if len(score.voices["Vocal"].bars) == 0:
            errors.append("The ABC contains no measures.")
        if not score.voices["Vocal"].chords and source:
            warnings.append("The transformed score carries no chord symbols.")

    if source is not None and score is not None:
        facts["comparison"] = compare_with_source(source, abc)

    return AbcValidation(not errors, abc, tuple(errors), tuple(warnings), facts)


def _split_header(abc: str) -> Tuple[List[str], List[str]]:
    """Split at ``K:`` exactly like the rest of the toolkit does."""
    header: List[str] = []
    body: List[str] = []
    in_header = True
    for line in abc.split("\n"):
        if in_header:
            header.append(line)
            if line.strip().startswith("K:"):
                in_header = False
            continue
        body.append(line)
    return header, body


def _empty_voice_blocks(body: Sequence[str]) -> List[str]:
    """Voice blocks that are declared but carry no music before the next one."""
    empty: List[str] = []
    current: Optional[str] = None
    current_has_music = False
    for line in list(body) + ["V: <end>"]:
        stripped = line.strip()
        if not stripped:
            continue
        match = _VOICE_SWITCH_RE.match(stripped)
        if match or stripped.startswith("V: <end>"):
            if current is not None and not current_has_music:
                empty.append(current)
            current = match.group("id") if match else None
            current_has_music = False
            continue
        if stripped.startswith("%"):
            continue
        if _MUSIC_LINE_HINT_RE.search(stripped):
            current_has_music = True
    return empty


def compare_with_source(source: str, target: str) -> Dict[str, object]:
    """Which musical invariants the transformation actually changed.

    A structural difference is not automatically an error - a reinterpretation is
    allowed to change the melody.  It is reported so the caller can decide, and
    so a "faithful cover" that silently rewrote every note is visible.

    ``changes`` breaks the comparison down per element (tempo, bars, notes,
    chords, each voice), because "something differs" is not actionable when the
    question is which invariant a specific profile pinned.
    """
    try:
        before = parse_abc(str(source).strip())
        after = parse_abc(str(target).strip())
    except (AbcError, ValueError) as exc:
        return {"comparable": False, "reason": str(exc), "differences": [], "changes": {}}
    raw = abc_compare(before, after)
    # ``compare`` answers "does anything differ".  A profile pins individual
    # elements, so the caller also needs to know *which* one moved.
    voice = "Vocal"
    ins = "Ins"
    changes = {
        "tempo": before.bpm != after.bpm,
        "bars": {voice: before.voices[voice].bars != after.voices[voice].bars,
                 ins: before.voices[ins].bars != after.voices[ins].bars},
        "notes": {voice: before.voices[voice].notes != after.voices[voice].notes,
                  ins: before.voices[ins].notes != after.voices[ins].notes},
        "chords": {voice: before.voices[voice].chords != after.voices[voice].chords,
                   ins: before.voices[ins].chords != after.voices[ins].chords},
    }
    return {
        "comparable": True,
        "match": raw["match"],
        "differences": list(raw["differences"]),
        "changes": changes,
        "scope": raw["scope"],
        "source_notes": {"Vocal": len(before.voices["Vocal"].notes),
                         "Ins": len(before.voices["Ins"].notes)},
        "target_notes": {"Vocal": len(after.voices["Vocal"].notes),
                         "Ins": len(after.voices["Ins"].notes)},
    }


__all__ = [
    "ABC_COVER_RULES_PATH",
    "ABC_UPSTREAM_REFERENCE_PATH",
    "AbcValidation",
    "abc_reference",
    "compare_with_source",
    "extract_abc",
    "section_labels",
    "validate_abc",
]
