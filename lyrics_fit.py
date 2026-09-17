"""Lyrics-to-melody fit for the YuE2 Cover Studio.

New lyrics have to land on the melodic material that is already there.  This
module measures, per section, how much room the score offers - note onsets,
phrase lengths and rests - and compares it with the syllable count the supplied
words actually need.

Everything here is an estimate and is labelled as one.  Note onsets are not
measured sung syllables (a syllable may span several notes), and the syllable
counter is a language-neutral vowel-group heuristic.  The value of the report is
that a gross mismatch becomes visible *before* a render is spent, and that the
advice says which side should give.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Dict, List

from .cover_lyrics_contract import TAG, lyric_words
from .cover_score import VOCAL_VOICE, count_melody_notes, music_content, parse_cover_score

# Fit verdicts, from best to worst.
FIT_OK = "ok"
FIT_TIGHT = "tight"
FIT_POOR = "poor"
FIT_UNKNOWN = "unknown"

_VOWEL_GROUP_RE = re.compile(r"[aeiouy\u00e4\u00f6\u00fc\u00e0-\u00ff]+", re.IGNORECASE)


def estimate_syllables(text: str) -> int:
    """Language-neutral vowel-group estimate for one word or line.

    Deliberately simple and documented as an estimate: it counts vowel clusters,
    guarantees at least one syllable for a word that has letters, and never
    claims to be a pronunciation model.
    """
    total = 0
    for word in lyric_words(text):
        groups = _VOWEL_GROUP_RE.findall(word)
        total += max(1, len(groups))
    return total


@dataclass(frozen=True)
class SectionFit:
    index: int
    label: str
    note_onsets: int
    phrases: int
    measures: int
    rests: int
    lyric_syllables: int
    verdict: str
    advice: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "index": self.index, "label": self.label,
            "note_onsets": self.note_onsets, "phrases": self.phrases,
            "measures": self.measures, "rests": self.rests,
            "lyric_syllables": self.lyric_syllables,
            "delta": self.lyric_syllables - self.note_onsets,
            "verdict": self.verdict, "advice": self.advice,
        }


@dataclass(frozen=True)
class LyricsFit:
    """The whole report, serializable for the debug output."""

    sections: List[SectionFit] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    note: str = (
        "Estimates only: note onsets are not measured sung syllables (melismas are "
        "allowed) and the syllable count is a vowel-group heuristic."
    )

    @property
    def verdict(self) -> str:
        order = {FIT_POOR: 3, FIT_TIGHT: 2, FIT_UNKNOWN: 1, FIT_OK: 0}
        return max((section.verdict for section in self.sections), key=lambda v: order[v],
                   default=FIT_UNKNOWN)

    def as_report(self) -> Dict[str, object]:
        return {
            "schema": "cover_lyrics_fit_v1",
            "verdict": self.verdict,
            "sections": [section.as_dict() for section in self.sections],
            "warnings": list(self.warnings),
            "note": self.note,
        }

    def summary_lines(self) -> List[str]:
        lines = [
            f"LYRICS / MELODY FIT ({self.verdict.upper()}; estimates, not a pronunciation model):"
        ]
        for section in self.sections:
            lines.append(
                f"- {section.index:02d} [{section.label}]: {section.lyric_syllables} syllables "
                f"vs {section.note_onsets} note onsets in {section.phrases} phrase(s), "
                f"{section.measures} measure(s) -> {section.verdict}"
                + (f" ({section.advice})" if section.advice else ""))
        if self.warnings:
            lines.extend(f"- warning: {warning}" for warning in self.warnings)
        return lines


def _section_lyrics(lyrics: str) -> List[str]:
    """The ``[tag]`` blocks of a lyrics field, in order, tags stripped."""
    text = str(lyrics or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(TAG.finditer(text))
    if not matches:
        return [text.strip()] if text.strip() else []
    blocks: List[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append(text[match.end():end].strip())
    return blocks


def _fit_for(syllables: int, onsets: int) -> (str, str):
    """Verdict and advice for one section, ratio-based and deliberately lenient."""
    if onsets <= 0:
        if syllables == 0:
            return FIT_OK, ""
        return FIT_POOR, "the score has no vocal notes here; the words need another section"
    ratio = syllables / float(onsets)
    if ratio > 1.6:
        return FIT_TIGHT, "more syllables than note onsets; the words will be compressed"
    if ratio < 0.6:
        return FIT_TIGHT, "fewer syllables than note onsets; notes will stretch or repeat"
    return FIT_OK, ""


def analyse_lyrics_fit(abc: str, lyrics: str) -> LyricsFit:
    """Per-section fit between the supplied words and the score's vocal line."""
    warnings: List[str] = []
    blocks = _section_lyrics(lyrics)
    if not blocks:
        return LyricsFit([], ["no lyrics supplied; nothing to fit"])

    try:
        score = parse_cover_score(abc)
    except (ValueError, TypeError) as exc:  # pragma: no cover - defensive
        return LyricsFit([], [f"the score could not be analysed: {exc}"])

    sections: List[SectionFit] = []
    for position, section in enumerate(score.sections):
        melody = music_content(section.melody(VOCAL_VOICE))
        onsets = count_melody_notes(section.melody(VOCAL_VOICE))
        phrases = len([line for line in melody.splitlines() if line.strip()])
        measures = melody.count("|")
        rests = len(re.findall(r"[zZ][0-9]*(?:/[0-9]*)?", melody))
        words = blocks[position] if position < len(blocks) else ""
        syllables = estimate_syllables(words)
        verdict, advice = _fit_for(syllables, onsets)
        sections.append(SectionFit(position + 1, section.label, onsets, phrases, measures,
                                   rests, syllables, verdict, advice))

    if len(blocks) > len(score.sections):
        warnings.append(
            f"{len(blocks)} lyric blocks for {len(score.sections)} score sections; "
            "the extra blocks have no musical place")
    elif len(blocks) < len(score.sections):
        warnings.append(
            f"{len(score.sections)} score sections but only {len(blocks)} lyric blocks; "
            "some sections have no words")

    return LyricsFit(sections, warnings)


def repair_hint(fit: LyricsFit) -> str:
    """The one-line instruction the transform/repair stage needs, if any."""
    tight = [section for section in fit.sections if section.verdict == FIT_TIGHT]
    poor = [section for section in fit.sections if section.verdict == FIT_POOR]
    if not tight and not poor:
        return ""
    parts: List[str] = []
    if poor:
        parts.append("sections without matching melodic material: "
                     + ", ".join(section.label or str(section.index) for section in poor))
    if tight:
        parts.append("sections whose syllable density differs from the note density: "
                     + ", ".join(section.label or str(section.index) for section in tight))
    return ("Adjust the words first, and the melody only if the interpretation freedom "
            "explicitly allows it - " + "; ".join(parts) + ".")


__all__ = [
    "FIT_OK",
    "FIT_POOR",
    "FIT_TIGHT",
    "FIT_UNKNOWN",
    "LyricsFit",
    "SectionFit",
    "analyse_lyrics_fit",
    "estimate_syllables",
    "repair_hint",
]
