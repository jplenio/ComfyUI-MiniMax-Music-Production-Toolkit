"""Native SheetSage2 score analysis and instrumental adaptation.

The two native voices are Vocal and Ins; chord symbols belong to Vocal even
when its melody rests. Instrumental mode mutes Vocal notes, retaining harmony,
and transfers the lead into Ins blocks. Overlapping Ins material is replaced
and reported. Analysis counts note onsets, not actual sung syllables. Rewrites
preserve native block/field boundaries; no audio-realization guarantee is made.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional, Sequence

# --------------------------------------------------------------------------
# Lyrics modes
# --------------------------------------------------------------------------
# The user-facing choice.  ``instrumental`` rewrites the score, ``new lyrics``
# keeps it and asks for newly written, syllable-synchronized words, and
# ``original lyrics`` keeps it and uses the Whisper transcription as the words.
LYRICS_MODE_INSTRUMENTAL = "instrumental"
LYRICS_MODE_NEW = "new lyrics"
LYRICS_MODE_ORIGINAL = "original lyrics"

# Dropdown order: the two lyric-writing modes first, the score rewrite last.
LYRICS_MODES = (LYRICS_MODE_NEW, LYRICS_MODE_ORIGINAL, LYRICS_MODE_INSTRUMENTAL)
# The standard mode (user decision, 2026-09-18): an instrumental cover needs no
# Whisper engine and no transcription, so it is the mode that works out of the box.
DEFAULT_LYRICS_MODE = LYRICS_MODE_INSTRUMENTAL

# Case-insensitive aliases so an archived workflow or an API caller written
# against an older spelling still resolves instead of silently falling back.
_LYRICS_MODE_ALIASES = {
    "instrumental": LYRICS_MODE_INSTRUMENTAL,
    "instrumental cover": LYRICS_MODE_INSTRUMENTAL,
    "no vocals": LYRICS_MODE_INSTRUMENTAL,
    "new": LYRICS_MODE_NEW,
    "new lyrics": LYRICS_MODE_NEW,
    "new vocals": LYRICS_MODE_NEW,
    "original": LYRICS_MODE_ORIGINAL,
    "original lyrics": LYRICS_MODE_ORIGINAL,
    "original vocals": LYRICS_MODE_ORIGINAL,
    "transcribed lyrics": LYRICS_MODE_ORIGINAL,
    "whisper": LYRICS_MODE_ORIGINAL,
}

# What plays the melodic line that used to carry the vocals.  The special
# REMOVE_LEAD_INSTRUMENT value drops that line instead of reassigning it.
REMOVE_LEAD_INSTRUMENT = "Remove vocal line (accompaniment only)"
LEAD_INSTRUMENTS = (
    "Lead synth",
    "Electric piano",
    "Piano",
    "Electric guitar",
    "Acoustic guitar",
    "Strings",
    "Saxophone",
    "Trumpet",
    "Flute",
    "Organ",
    "Vibraphone",
    REMOVE_LEAD_INSTRUMENT,
)
DEFAULT_LEAD_INSTRUMENT = "Lead synth"

# SheetSage2's fixed voice identifiers and the label it writes for the vocal
# melody.  The identifier stays (the body switches on it); the *instrument
# name* is what the rewrite replaces.
VOCAL_VOICE = "Vocal"
INSTRUMENT_VOICE = "Ins"
VOCAL_VOICE_LABEL = "Vocal Melody"

# One ABC event: a chord symbol, an inline key change, a note (with optional
# accidental/octave/duration/tie) or a rest.  Order matters: the quoted chord
# symbol must win over its contents.
_EVENT_RE = re.compile(
    r"""
      (?P<chord>"[^"]*")
    | (?P<key>\[[KM]:[^\]]*\]|![^!]*!)
    | (?P<note>[=_^]{0,2}[A-Ga-g][,']*[0-9]*(?:/[0-9]*)*)(?P<tie>-)?
    | (?P<rest>[zZxX][0-9]*(?:/[0-9]*)*)
    """,
    re.VERBOSE,
)
_HEADER_VOICE_RE = re.compile(r"^V:\s*(?P<id>[^\s=]+)\s*(?P<rest>.*)$")
_BODY_VOICE_RE = re.compile(r"^V:\s*(?P<id>[^\s=]+)\s*$")
_LYRIC_LINE_RE = re.compile(r"^[wW]:")
_NAME_RE = re.compile(r'\bname="[^"]*"')
_SHORT_NAME_RE = re.compile(r'\bsnm="[^"]*"')


def normalize_lyrics_mode(value) -> str:
    """Map a stored/typed value onto one of :data:`LYRICS_MODES`.

    Missing legacy values use the default; unknown explicit modes raise instead
    of silently selecting a different vocal behavior.
    """
    text = str(value or "").strip().casefold()
    if not text:
        return DEFAULT_LYRICS_MODE
    if text not in _LYRICS_MODE_ALIASES:
        raise ValueError('YuE2 Cover: lyrics_mode must be new lyrics, original lyrics or instrumental.')
    return _LYRICS_MODE_ALIASES[text]


def normalize_lead_instrument(value) -> str:
    """Map a stored/typed instrument onto :data:`LEAD_INSTRUMENTS`."""
    text = str(value or "").strip()
    if not text:
        return DEFAULT_LEAD_INSTRUMENT
    for instrument in LEAD_INSTRUMENTS:
        if instrument.casefold() == text.casefold():
            return instrument
    return text if text else DEFAULT_LEAD_INSTRUMENT


def count_melody_notes(music: str) -> int:
    """Melody onsets in one ABC voice line - approximate phrasing evidence.

    A tie continuation (``C2-C2``) is one onset, not two, and rests never carry
    a syllable.  Chord symbols and inline key changes are ignored.
    """
    count = 0
    continuation = False
    music = music_content(music)
    for match in _EVENT_RE.finditer(music):
        if match.group("chord") or match.group("key"):
            continue
        if match.group("rest"):
            continuation = False
            continue
        if not continuation:
            count += 1
        continuation = bool(match.group("tie"))
    return count


def music_content(music: str) -> str:
    """Ignore ABC fields/comments when counting music, preserving line boundaries."""
    return '\n'.join(line.split('%', 1)[0] for line in str(music or '').splitlines()
                     if not re.match(r'^\s*[A-Za-z]:', line))


def note_to_rest(match):
    note = match.group('note')
    if not note:
        return match.group(0)
    duration = re.sub(r"^[=_^]{0,2}[A-Ga-g][,']*", '', note)
    return 'z' + duration


def mute_music(line: str) -> str:
    if re.match(r'^\s*[A-Za-z]:', line) or line.lstrip().startswith('%'):
        return line
    return _EVENT_RE.sub(note_to_rest, line)


@dataclass
class ScoreSection:
    """One ``%`` labelled measure group of the SheetSage2 score."""

    label: str
    index: int
    voices: Dict[str, str] = field(default_factory=dict)

    def melody(self, voice: str = VOCAL_VOICE) -> str:
        """Missing vocal material is not an invitation to sing instrumental notes."""
        return self.voices.get(voice, "")

    def syllables(self, voice: str = VOCAL_VOICE) -> int:
        return count_melody_notes(self.melody(voice))


@dataclass
class CoverScore:
    """A parsed SheetSage2 ABC score."""

    header: List[str]
    sections: List[ScoreSection]
    lyrics_lines: List[str] = field(default_factory=list)

    @property
    def voices(self) -> List[str]:
        seen: List[str] = []
        for line in self.header:
            match = _HEADER_VOICE_RE.match(line.strip())
            if match and "=" in line:
                seen.append(match.group("id"))
        for section in self.sections:
            for voice in section.voices:
                if voice not in seen:
                    seen.append(voice)
        return seen

    @property
    def has_vocal_voice(self) -> bool:
        return VOCAL_VOICE in self.voices

    def total_syllables(self, voice: str = VOCAL_VOICE) -> int:
        return sum(section.syllables(voice) for section in self.sections)

    def syllable_map(self, voice: str = VOCAL_VOICE) -> Dict:
        """Per-section syllable counts, phrasing evidence for new lyrics (legacy field names retained)."""
        sections = [
            {
                "index": section.index,
                "label": section.label,
                "melody_notes": section.syllables(voice),
                "phrases_abc": music_content(section.melody(voice)).splitlines(),
            }
            for section in self.sections
        ]
        return {
            "voice": voice,
            "measurement": "note onsets, not measured sung syllables; melismas allowed",
            "section_count": len(sections),
            "sections": sections,
            "total_syllables": sum(item["melody_notes"] for item in sections),
        }


def parse_cover_score(abc: str) -> CoverScore:
    """Parse the score into its header and its labelled measure groups.

    Tolerant by design: an unrecognized line is kept as-is rather than dropped,
    so re-serializing a score never silently loses content.  ``K:`` terminates
    the ABC header block, which is what makes the split unambiguous.
    """
    text = str(abc or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    header: List[str] = []
    body: List[str] = []
    in_header = True
    for line in lines:
        stripped = line.strip()
        if in_header:
            header.append(line)
            if stripped.startswith("K:"):
                in_header = False
            continue
        body.append(line)

    sections: List[ScoreSection] = []
    lyrics_lines: List[str] = []
    pending_labels: List[str] = []
    current: Optional[ScoreSection] = None
    current_voice: Optional[str] = None

    for line in body:
        stripped = line.strip()
        if not stripped:
            continue
        if _LYRIC_LINE_RE.match(stripped):
            lyrics_lines.append(stripped)
            continue
        if stripped.startswith("% toolkit-instrumental:") or stripped.startswith('%%'):
            continue
        if stripped.startswith("%"):
            pending_labels.append(stripped.lstrip("%").strip())
            continue
        voice_match = _BODY_VOICE_RE.match(stripped)
        if voice_match:
            current_voice = voice_match.group("id")
            if current is None or pending_labels:
                current = ScoreSection(
                    label=" / ".join(label for label in pending_labels if label),
                    index=len(sections) + 1,
                )
                sections.append(current)
                pending_labels = []
            current.voices.setdefault(current_voice, "")
            continue
        if current is None:
            # Music before any voice switch: keep it in an unlabelled section.
            current = ScoreSection(label="", index=len(sections) + 1)
            sections.append(current)
        voice = current_voice or (next(iter(current.voices), VOCAL_VOICE))
        current.voices[voice] = current.voices.get(voice, "") + stripped + '\n'

    for section in sections:
        if not section.label:
            section.label = f"section {section.index}"
    return CoverScore(header=header, sections=sections, lyrics_lines=lyrics_lines)


def _instrument_voice_line(line: str, instrument: str) -> str:
    """Rewrite one header voice line so its melodic line is instrument-led.

    Existing ``name``/``snm`` fields are replaced, missing ones are appended.
    The check is on the *pattern*, not on whether the text changed: comparing
    the substituted text with the input would append a second ``name`` field on
    every repeat, which would make the rewrite non-idempotent.
    """
    label = f"{instrument} Melody"
    if _NAME_RE.search(line):
        line = _NAME_RE.sub(f'name="{label}"', line, count=1)
    else:
        line = line.rstrip() + f' name="{label}"'
    if _SHORT_NAME_RE.search(line):
        line = _SHORT_NAME_RE.sub(f'snm="{instrument}"', line, count=1)
    else:
        line = line.rstrip() + f' snm="{instrument}"'
    return line


def _drop_voice_from_header(header: Sequence[str], voice: str) -> List[str]:
    kept: List[str] = []
    for line in header:
        match = _HEADER_VOICE_RE.match(line.strip())
        if match and "=" in line and match.group("id") == voice:
            continue
        kept.append(line)
    return kept


def score_syllable_brief(score_map: Dict, max_sections: int = 32) -> str:
    """Compact, LLM-readable form of :meth:`CoverScore.syllable_map`."""
    sections = list(score_map.get("sections") or [])
    lines = [
        "MELODY PHRASING MAP (note onsets, NOT measured sung syllables; a syllable may span several notes):"
    ]
    for item in sections[:max_sections]:
        lines.append(f"- {item['index']:02d} [{item['label']}]: {item['melody_notes']} note onsets")
        lines.extend('  Phrase grid (ABC durations/rests): ' + phrase for phrase in item.get('phrases_abc', []))
    if len(sections) > max_sections:
        remaining = sum(item["melody_notes"] for item in sections[max_sections:])
        # Do not silently omit the ending of a long cover.
        lines.extend(f"- {item['index']:02d} [{item['label']}]: {item['melody_notes']} note onsets"
                     for item in sections[max_sections:])
    lines.append(f"- Total: {score_map.get('total_syllables', 0)} note onsets (legacy total_syllables field)")
    return "\n".join(lines)


def adapt_cover_score(abc: str, lyrics_mode: str, lead_instrument: str = DEFAULT_LEAD_INSTRUMENT) -> Dict:
    """Adapt the cover score for the selected lyrics mode.

    Returns a record with the possibly rewritten score, whether it changed and
    why, plus the syllable map.  For ``instrumental`` the melodic line that
    carried the vocals becomes an instrument part (or is removed entirely when
    ``lead_instrument`` asks for accompaniment only); the other modes hand the
    score back byte-identical, because the words - not the notation - are what
    changes there.
    """
    mode = normalize_lyrics_mode(lyrics_mode)
    instrument = normalize_lead_instrument(lead_instrument)
    text = str(abc or "")

    if mode != LYRICS_MODE_INSTRUMENTAL:
        score = parse_cover_score(text)
        return {
            "lyrics_mode": mode,
            "lead_instrument": instrument,
            "adapted": False,
            "removed_voice": None,
            "changes": [],
            "abc": text,
            "syllables": score.syllable_map(),
        }

    score = parse_cover_score(text)
    # Operate on native voice blocks, never rebuild music from the analysis map.
    # In particular, key/meter fields and one-to-four-bar groups must survive.
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    switches = [(i, _BODY_VOICE_RE.match(line.strip()).group('id'))
                for i,line in enumerate(lines) if _BODY_VOICE_RE.match(line.strip())]
    replacements = {}
    moved = replaced = 0
    for index, (start, voice) in enumerate(switches):
        if voice != VOCAL_VOICE:
            continue
        end = switches[index+1][0] if index+1 < len(switches) else len(lines)
        block = lines[start+1:end]
        has_notes = count_melody_notes('\n'.join(block)) > 0
        # Strip lyric lines even if this voice contains rests only.
        muted = [mute_music(line) for line in block if not _LYRIC_LINE_RE.match(line.strip())]
        replacements[start] = (end, [lines[start]] + muted)
        if not has_notes or instrument == REMOVE_LEAD_INSTRUMENT:
            continue
        if index+1 >= len(switches) or switches[index+1][1] != INSTRUMENT_VOICE:
            raise ValueError("YuE2 instrumental cover: expected paired Vocal/Ins blocks from SheetSage2; review the source ABC.")
        ins_start = end
        ins_end = switches[index+2][0] if index+2 < len(switches) else len(lines)
        ins_block = lines[ins_start+1:ins_end]
        replaced += count_melody_notes('\n'.join(ins_block))
        # Preserve trailing structure labels attached to the next group.
        suffix = [line for line in ins_block if line.lstrip().startswith('%')]
        lead = [line for line in block if not line.lstrip().startswith('%')
                and not _LYRIC_LINE_RE.match(line.strip())]
        # Chord symbols stay in Vocal, including its new rests, as in native ABC.
        lead = [re.sub(r'"[^"\n]*"', '', line) if not re.match(r'^\s*[A-Za-z]:', line) else line
                for line in lead]
        replacements[ins_start] = (ins_end, [lines[ins_start]] + lead + suffix)
        moved += 1
    output = []
    i = 0
    while i < len(lines):
        if i in replacements:
            i, block = replacements[i]
            output.extend(block)
            continue
        line = lines[i]
        match = _HEADER_VOICE_RE.match(line.strip())
        if match and '=' in line:
            if match.group('id') == VOCAL_VOICE:
                line = 'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"'
            elif match.group('id') == INSTRUMENT_VOICE:
                line = 'V: Ins clef=treble name="Ins Melody" snm="Inst."'
        if not _LYRIC_LINE_RE.match(line.strip()) and not line.startswith('% toolkit-instrumental:'):
            output.append(line)
        i += 1
    adapted = '\n'.join(output) + ('\n' if text.endswith('\n') else '')
    changes = [f"vocal_notes_replaced_with_rests; lead_blocks_moved_to_Ins:{moved}",
               f"original_Ins_notes_replaced_in_lead_blocks:{replaced}"]
    return {"lyrics_mode": mode, "lead_instrument": instrument, "adapted": adapted != text,
            "removed_voice": VOCAL_VOICE if instrument == REMOVE_LEAD_INSTRUMENT else None,
            "changes": changes, "abc": adapted, "syllables": score.syllable_map()}



def cover_lyrics_request(payload: Dict) -> Dict:
    """The lyrics-mode fields of a cover source record, normalized."""
    return {
        "lyrics_mode": normalize_lyrics_mode(payload.get("lyrics_mode")),
        "lead_instrument": normalize_lead_instrument(payload.get("lead_instrument")),
    }
