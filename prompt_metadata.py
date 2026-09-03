"""Structured prompt metadata: front-matter parsing, library aggregation and prompt assembly.

Prompt library files can *optionally* carry a small metadata block at the very
top of the file, so that selecting a prompt can prefill the structured fields
of ``MiniMaxStructuredPromptV20`` (genre, tempo, key, lyrics, language, voice,
lyrics theme, target length).  Everything after the closing delimiter is the
"further description" part of the prompt.

Example::

    ---
    Genre: Melodic Techno
    Tempo: 128 BPM
    Key: A minor
    Lyrics: sparse
    Language: English
    Voice: female vocal, airy
    Theme: escape into the night
    Length: 4-5 minutes
    ---
    Free text describing the track in more detail.

Files without a metadata block are still valid: every structured field simply
defaults to ``custom`` (the part is left out of the LLM prompt) and the whole
file content becomes the description.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .toolkit_logging import get_logger

LOGGER = get_logger("prompt_metadata")

# Field order used by the node and the assembled prompt.
STRUCTURED_FIELDS = ("genre", "tempo", "key", "lyrics", "language", "voice", "theme", "length")

# "custom" means: do not include this part at all, let the LLM decide.
CUSTOM = "custom"

# Canonical lyrics vocabulary the UI and the assembled prompt understand.
LYRICS_CHOICES = ("yes", "sparse", "instrumental")

# Curated vocabulary shown in every combo list, independent of what the
# bundled prompt library happens to contain.  File-derived values are merged
# on top so library-specific entries still appear.
CURATED_FIELD_OPTIONS = {
    "genre": (
        "House", "Deep House", "Tech House", "Melodic House", "Techno", "Trance", "EDM",
        "Drum & Bass", "Breakbeat", "Dubstep", "Pop", "Rock", "Alternative Rock", "Hard Rock",
        "Metal", "Heavy Metal", "Industrial", "Jazz", "Funk", "Soul / R&B", "Hip-Hop / Rap",
        "Blues", "Folk", "Country", "Classical", "Neoclassical", "Cinematic / Film Score",
        "Ambient", "Chillout / Downtempo", "Lo-Fi", "Synthwave / Retro", "Trip-Hop",
        "Reggae / Dub", "Latin", "World Music", "Comedy / Novelty",
    ),
    "tempo": (
        "Slow (60-90 BPM)", "70 BPM", "80 BPM", "90 BPM", "Midtempo (100-120 BPM)", "100 BPM",
        "110 BPM", "120 BPM", "124 BPM", "128 BPM", "130 BPM", "Uptempo (125-140 BPM)",
        "134 BPM", "138 BPM", "140 BPM", "Fast (>140 BPM)", "150 BPM", "160 BPM", "174 BPM",
    ),
    "key": (
        "A minor", "D minor", "E minor", "B minor", "F# minor", "G minor", "C minor",
        "F minor", "C# minor", "C major", "G major", "D major", "A major", "E major",
        "F major", "Bb major", "Eb major", "Ab major",
    ),
    "lyrics": LYRICS_CHOICES,
    "language": (
        "English", "Deutsch (German)", "Español (Spanish)", "Français (French)",
        "Italiano (Italian)", "Português (Portuguese)", "日本語 (Japanese)", "한국어 (Korean)",
        "中文 (Chinese)", "Русский (Russian)", "No lyrics / n/a",
    ),
    "voice": (
        "female vocal", "male vocal", "female lead + male backing", "male lead + female backing",
        "duet (female & male)", "female choir", "male choir", "children's choir",
        "group vocals / gang vocals", "spoken word", "no vocals / n/a",
    ),
    "theme": (
        "love & romance", "heartbreak & loss", "freedom & escape", "night & city lights",
        "nature & seasons", "hope & resilience", "self-discovery & growth",
        "celebration & party", "nostalgia & memories", "dreams & fantasy",
        "social commentary", "storytelling & adventure", "spirituality & inner peace",
        "friendship & togetherness", "melancholy & longing", "mystery & darkness",
    ),
    "length": (
        "30 seconds", "1 minute", "1-2 minutes", "2-3 minutes", "3-4 minutes", "4-5 minutes",
    ),
}

FIELD_LABELS = {
    "genre": "Genre",
    "tempo": "Tempo",
    "key": "Key",
    "lyrics": "Lyrics",
    "language": "Language",
    "voice": "Voice",
    "theme": "Lyrics theme",
    "length": "Length",
}

# Recognized front-matter key aliases, mapped to canonical field names.
_ALIASES = {
    "genre": "genre",
    "tempo": "tempo",
    "bpm": "tempo",
    "key": "key",
    "tonart": "key",
    "lyrics": "lyrics",
    "vocals": "lyrics",
    "language": "language",
    "sprache": "language",
    "voice": "voice",
    "stimme": "voice",
    "vocal": "voice",
    "theme": "theme",
    "lyrics_theme": "theme",
    "lyrics theme": "theme",
    "length": "length",
    "song_length": "length",
    "song length": "length",
    "duration": "length",
    "description": "description",
    "beschreibung": "description",
}

_LYRICS_NORMALIZATION = {
    "yes": "yes", "ja": "yes", "y": "yes", "vocals": "yes", "gesang": "yes",
    "sparse": "sparse", "wenig": "sparse", "minimal": "sparse", "few": "sparse",
    "instrumental": "instrumental", "no": "instrumental", "nein": "instrumental",
    "none": "instrumental", "ohne": "instrumental", "instrumentals": "instrumental",
}

_FRONT_MATTER_LINE_RE = re.compile(r"^---\s*$")


def _normalize_key(raw_key: str) -> Optional[str]:
    key = " ".join((raw_key or "").strip().lower().split())
    key = key.replace("-", "_")
    return _ALIASES.get(key)


def normalize_lyrics_value(value: str) -> str:
    """Normalize common lyrics spellings to the canonical vocabulary.

    Unrecognized values are kept verbatim so library-specific phrasing still
    reaches the LLM instead of being silently dropped.
    """
    text = (value or "").strip()
    if not text:
        return ""
    return _LYRICS_NORMALIZATION.get(text.lower(), text)


def parse_prompt_front_matter(text: str) -> tuple[Dict[str, str], str]:
    """Parse an optional metadata block from a prompt file.

    Returns ``(fields, description)``.  ``fields`` contains only non-empty,
    recognized entries (description excluded); ``description`` is the free text
    after the closing delimiter (or the whole text if no valid block exists).
    """
    text = (text or "").strip()
    lines = text.splitlines()
    if not lines or not _FRONT_MATTER_LINE_RE.match(lines[0]):
        return {}, text

    end = None
    for index in range(1, len(lines)):
        if _FRONT_MATTER_LINE_RE.match(lines[index]):
            end = index
            break
    if end is None:
        # No closing delimiter: the file is a plain prompt that merely starts
        # with "---".  Treat it as description instead of guessing metadata.
        return {}, text

    fields: Dict[str, str] = {}
    description_key_value = ""
    for raw in lines[1:end]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key_text, sep, value = line.partition(":")
        if not sep:
            LOGGER.debug("Ignoring front-matter line without colon: %r", raw)
            continue
        key = _normalize_key(key_text)
        value = value.strip()
        if key is None:
            LOGGER.debug("Ignoring unknown front-matter key: %r", key_text.strip())
            continue
        if not value:
            continue
        if key == "description":
            description_key_value = value
            continue
        if key == "lyrics":
            value = normalize_lyrics_value(value)
        fields[key] = value

    description = "\n".join(lines[end + 1:]).strip()
    if not description and description_key_value:
        description = description_key_value
    return fields, description


def assemble_structured_user_prompt(fields: Dict[str, str], description: str) -> str:
    """Build the LLM user prompt from resolved structured fields plus description.

    Fields with empty values or the value ``custom`` are left out entirely.
    The description (the "further description" part) is appended verbatim.
    """
    parts: list[str] = []
    for field in STRUCTURED_FIELDS:
        value = (fields.get(field) or "").strip()
        if not value or value == CUSTOM:
            continue
        parts.append(f"{FIELD_LABELS[field]}: {value}")

    brief = ""
    if parts:
        brief = "Musical brief:\n" + "\n".join(parts)
    description = (description or "").strip()
    if brief and description:
        return brief + "\n\n" + description
    if brief:
        return brief
    if description:
        return description
    raise ValueError(
        "Structured Song Prompt: every field is 'custom' and no description text is available. "
        "Select a prompt file, fill at least one field or write a description."
    )


def merge_field_options(file_values: Dict[str, list[str]]) -> Dict[str, list[str]]:
    """Merge the curated combo vocabulary with values found in prompt files.

    Curated options come first (predictable, always available); unique
    file-derived values are appended so library-specific entries still appear.
    The ``custom`` sentinel is not part of either list - the node and the
    frontend prepend it themselves.
    """
    merged: Dict[str, list[str]] = {}
    for field in STRUCTURED_FIELDS:
        options: list[str] = []
        for value in list(CURATED_FIELD_OPTIONS.get(field, ())) + list(file_values.get(field, ())):
            value = (value or "").strip()
            if value and value != CUSTOM and value not in options:
                options.append(value)
        merged[field] = options
    return merged


def collect_file_field_values(paths: Iterable[Path], max_options: int = 200) -> Dict[str, list[str]]:
    """Aggregate unique structured field values from prompt files.

    Used for the node's COMBO option lists and for the frontend refresh.  Files
    that cannot be decoded or contain no metadata simply contribute nothing.
    """
    collected: Dict[str, set[str]] = {field: set() for field in STRUCTURED_FIELDS}
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            fields, _description = parse_prompt_front_matter(text)
        except Exception:  # never let one broken file break option discovery
            LOGGER.debug("Could not parse prompt metadata from %s", path, exc_info=True)
            continue
        for field, value in fields.items():
            if field in collected and value and value != CUSTOM:
                collected[field].add(value)

    result: Dict[str, list[str]] = {}
    for field in STRUCTURED_FIELDS:
        options = sorted(collected[field], key=str.casefold)
        if field == "lyrics":
            # Canonical choices first, then anything custom from the library.
            ordered = [choice for choice in LYRICS_CHOICES if choice in options]
            ordered += [value for value in options if value not in LYRICS_CHOICES]
            options = ordered
        result[field] = options[:max_options]
    return result
