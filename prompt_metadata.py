"""Structured prompt metadata: front-matter parsing, library aggregation and prompt assembly.

Prompt library files can *optionally* carry a small metadata block at the very
top of the file, so that selecting a prompt can prefill the structured fields
of ``MiniMaxStructuredPromptV20`` (genre, tempo, meter, key, lyrics, language,
voice, lyrics theme, target length).  Everything after the closing delimiter is
the "further description" part of the prompt.

Example::

    ---
    Genre: Melodic Techno
    Tempo: Midtempo (100-120 BPM)
    Meter: 4/4 (common time)
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
STRUCTURED_FIELDS = (
    "genre", "tempo", "meter", "key", "lyrics", "language", "voice", "theme", "length",
)

# "custom" means: do not include this part at all, let the LLM decide.
CUSTOM = "custom"

# Canonical lyrics vocabulary the UI and the assembled prompt understand.
# "only voice - no words" means wordless vocalization (humming, syllables,
# vocalise) - a vocal track without real words.
LYRICS_CHOICES = ("yes", "sparse", "only voice - no words", "instrumental")

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
        # Contemporary & electronic subgenres
        "Synth-Pop", "Psytrance", "Jungle", "Trap", "Punk Rock", "Indie Rock", "Power Metal",
        "Opera", "Afrobeats", "Amapiano", "Dancehall", "Dub", "Reggae",
        # African styles
        "Ethio-Jazz", "Highlife", "Desert Blues",
        # Asian styles
        "K-Pop", "J-Pop / City Pop", "Anime / Game Music", "Chinese Traditional",
        "Indian Classical", "Bollywood",
        # Latin American styles
        "Bossa Nova", "Samba", "Salsa", "Cumbia", "Tango", "Reggaeton", "Bachata",
        # European styles
        "Flamenco", "Fado", "Chanson", "Schlager", "Klezmer", "Balkan Folk",
        # --- Electronic: umbrella + house / techno subgenres
        "Electronic", "Progressive House", "Afro House", "Organic House", "Bass House",
        "Electro House", "Disco House", "French House", "Acid House", "Future Rave",
        "Melodic Techno", "Peak Time Techno", "Hardgroove Techno", "Minimal / Deep Tech",
        # --- Electronic: bass, breaks & rave
        "Liquid Drum & Bass", "Neurofunk", "UK Garage", "2-Step / Speed Garage", "Grime",
        "Footwork / Juke", "Hardstyle", "Hardcore / Gabber", "Big Room / Festival EDM",
        "Future Bass", "Eurodance", "Progressive Trance", "Uplifting Trance", "Goa Trance",
        # --- Electronic: leftfield, retro & chill
        "IDM / Experimental Electronic", "Glitch Hop", "Electro Swing", "Vaporwave",
        "Chiptune / 8-Bit", "Berlin School / Kosmische", "EBM / Darkwave", "Dark Ambient",
        "Drone", "Lo-Fi Hip-Hop", "Downtempo / Balearic",
        # --- Disco & funk
        "Disco", "Nu-Disco", "Italo Disco", "P-Funk / Classic Funk", "Boogie / Post-Disco",
        # --- Hip-Hop subgenres
        "Boom Bap", "Drill", "Cloud Rap", "Phonk", "Conscious Hip-Hop", "Old School Hip-Hop",
        "Hyperpop",
        # --- Pop subgenres
        "Dance-Pop", "Indie Pop", "Dream Pop", "Electropop", "Bedroom Pop", "Art Pop",
        "Power Ballad", "Singer-Songwriter", "Acoustic Pop", "Pop Rock", "Britpop",
        "New Wave", "Post-Punk", "Shoegaze",
        # --- Rock subgenres
        "Classic Rock", "Blues Rock", "Southern Rock", "Psychedelic Rock", "Progressive Rock",
        "Post-Rock", "Garage Rock", "Stoner Rock", "Surf Rock", "Rockabilly", "Grunge",
        "Pop-Punk / Emo", "Hardcore Punk", "Ska Punk", "Folk Punk", "Math Rock",
        # --- Metal subgenres
        "Melodic Metal", "Symphonic Metal", "Thrash Metal", "Death Metal", "Black Metal",
        "Doom Metal", "Sludge / Post-Metal", "Metalcore", "Nu Metal", "Folk Metal",
        "Gothic Metal", "Progressive Metal / Djent", "Industrial Metal",
        # --- Jazz subgenres
        "Swing / Big Band", "Bebop", "Cool Jazz", "Modal Jazz", "Jazz Fusion", "Smooth Jazz",
        "Gypsy Jazz", "Vocal Jazz / Crooner", "Nu Jazz", "Dixieland / New Orleans Jazz",
        "Ragtime", "Boogie-Woogie",
        # --- Soul, R&B & gospel
        "Motown / Classic Soul", "Neo-Soul", "Soul Ballad", "Doo-Wop", "Gospel",
        "Contemporary Worship", "Hymn / Sacred",
        # --- Blues subgenres
        "Delta Blues", "Chicago Blues", "Electric Blues", "Blues Ballad",
        # --- Country & Americana
        "Modern Country Pop", "Outlaw Country", "Country Rock", "Honky Tonk", "Bluegrass",
        "Americana", "Country Ballad",
        # --- Folk & traditional
        "Celtic Folk", "Nordic Folk", "Medieval / Renaissance", "Appalachian Folk",
        "Sea Shanty", "Alpine Folk / Volksmusik", "Russian Folk", "Polka", "Waltz",
        # --- Classical subgenres
        "Baroque", "Classical Period", "Romantic Classical", "Impressionist Classical",
        "Minimalism", "Chamber Music", "String Quartet", "Symphonic / Orchestral",
        "Solo Piano", "Choral / Sacred Choir", "Gregorian Chant",
        # --- Cinematic & functional
        "Epic Trailer", "Orchestral Action", "Horror / Suspense Score",
        "Documentary Underscore", "Corporate / Advertising", "Fantasy / Adventure Score",
        "Video Game Orchestral", "Sports / Stadium Anthem", "Fanfare / March",
        "Musical / Broadway",
        # --- Kids, wellness & seasonal
        "Children's Song", "Lullaby", "Nursery Rhyme", "Meditation / Healing",
        "Nature Soundscape", "Focus / Study Music", "Sleep Music",
        "Christmas / Holiday", "Wedding / Ceremonial",
        # --- More world styles
        "Afrobeat (Classic)", "Gqom", "Soukous", "Kwaito", "Mbalax",
        "Arabic Pop", "Turkish Folk", "Persian Classical", "Rai", "Gnawa",
        "Qawwali", "Bhangra", "Carnatic", "Gamelan", "Mongolian Throat Singing",
        "Andean Folk", "Mariachi", "Ranchera", "Norteño / Corrido", "Vallenato",
        "Merengue", "Son Cubano", "Calypso / Soca", "Ska (Jamaican)", "Rocksteady",
        "Mandopop", "Cantopop", "Enka", "V-Pop", "Hawaiian",
    ),
    "tempo": (
        # Curated BPM ranges (not fixed values) so a selection always leaves
        # the LLM a comfortable musical window; "custom" comes first in the UI.
        "Slow (40-70 BPM)",
        "Laid-back (70-100 BPM)",
        "Midtempo (100-120 BPM)",
        "Dancefloor (120-130 BPM)",
        "Uptempo (130-145 BPM)",
        "Fast (145-175 BPM)",
        "Very fast (175-200 BPM)",
    ),
    "key": (
        # Circle of fifths: minor keys first, then major keys.
        "A minor", "E minor", "B minor", "F# minor", "C# minor", "G# minor",
        "D# minor", "Bb minor", "F minor", "C minor", "G minor", "D minor",
        "C major", "G major", "D major", "A major", "E major", "B major",
        "F# major", "Db major", "Ab major", "Eb major", "Bb major", "F major",
    ),
    "meter": (
        # Time signature - most common first, then rarer / odd meters.
        "4/4 (common time)",
        "3/4 (waltz)",
        "6/8",
        "2/4 (march / polka)",
        "12/8 (shuffle / slow blues)",
        "2/2 (cut time)",
        "6/4",
        "5/4",
        "7/8",
        "7/4",
        "9/8",
        "5/8",
        "11/8",
        "changing time signatures",
        "free time / rubato",
    ),
    "lyrics": LYRICS_CHOICES,
    "language": (
        # Most important languages first (same order as before), then more
        # languages in alphabetical order.
        "English", "Deutsch (German)", "Español (Spanish)", "Français (French)",
        "Italiano (Italian)", "Português (Portuguese)", "日本語 (Japanese)", "한국어 (Korean)",
        "中文 (Chinese)", "हिन्दी (Hindi)", "Русский (Russian)",
        "العربية (Arabic)", "বাংলা (Bengali)", "Български (Bulgarian)", "Čeština (Czech)",
        "Dansk (Danish)", "Nederlands (Dutch)", "Suomi (Finnish)", "Ελληνικά (Greek)",
        "עברית (Hebrew)", "Magyar (Hungarian)", "Bahasa Indonesia (Indonesian)",
        "Bahasa Melayu (Malay)", "Norsk (Norwegian)", "فارسی (Persian)", "Polski (Polish)",
        "Română (Romanian)", "Српски (Serbian)", "Kiswahili (Swahili)", "Svenska (Swedish)",
        "Tagalog", "ไทย (Thai)", "Türkçe (Turkish)", "Українська (Ukrainian)",
        "اردو (Urdu)", "Tiếng Việt (Vietnamese)",
        # Further languages (alphabetical), incl. regional variants and
        # languages needed for specific traditional genres.
        "Afrikaans", "Shqip (Albanian)", "አማርኛ (Amharic)", "Հայերեն (Armenian)",
        "Azərbaycanca (Azerbaijani)", "Euskara (Basque)", "Беларуская (Belarusian)",
        "Bosanski (Bosnian)", "Català (Catalan)", "Hrvatski (Croatian)", "Eesti (Estonian)",
        "Galego (Galician)", "ქართული (Georgian)", "Gaeilge (Irish)", "Íslenska (Icelandic)",
        "Latina (Latin)", "Latviešu (Latvian)", "Lietuvių (Lithuanian)",
        "Lëtzebuergesch (Luxembourgish)", "Македонски (Macedonian)", "Malti (Maltese)",
        "ਪੰਜਾਬੀ (Punjabi)", "தமிழ் (Tamil)", "తెలుగు (Telugu)", "मराठी (Marathi)",
        "ગુજરાતી (Gujarati)", "മലയാളം (Malayalam)", "ಕನ್ನಡ (Kannada)", "नेपाली (Nepali)",
        "සිංහල (Sinhala)", "ဗမာ (Burmese)", "ខ្មែរ (Khmer)", "ລາວ (Lao)",
        "Қазақша (Kazakh)", "Oʻzbekcha (Uzbek)", "Монгол (Mongolian)",
        "Slovenčina (Slovak)", "Slovenščina (Slovenian)", "Gàidhlig (Scottish Gaelic)",
        "Cymraeg (Welsh)", "ייִדיש (Yiddish)", "Yorùbá (Yoruba)", "isiZulu (Zulu)",
        "Hausa", "Igbo", "ʻŌlelo Hawaiʻi (Hawaiian)", "Te Reo Māori (Maori)",
        "Runa Simi (Quechua)",
        # German regional variants (useful for Volksmusik, Schlager, comedy)
        "Bairisch (Bavarian)", "Schwiizerdütsch (Swiss German)", "Plattdeutsch (Low German)",
        # Special cases
        "Multilingual / mixed", "Invented / gibberish language",
        "No lyrics / n/a",
    ),
    "voice": (
        # Most frequently used first, then character / age / mood variants,
        # then ensembles and special vocal types.
        "female vocal", "male vocal",
        "female vocal, soft & airy", "male vocal, deep & warm",
        "female vocal, powerful & belting", "male vocal, powerful & belting",
        "female vocal, raspy & raw", "male vocal, raspy & raw",
        "female vocal, young & bright", "male vocal, young & energetic",
        "mature female vocal", "mature male vocal", "child vocal",
        "happy & uplifting vocal", "sad & melancholic vocal",
        "angry & aggressive vocal", "funny & playful vocal",
        "warm & comforting vocal", "cool & detached vocal",
        "whispered & intimate vocal", "breathy & sensual vocal",
        "smoky & soulful vocal", "bright & clean pop vocal",
        "female lead + male backing", "male lead + female backing",
        "duet (female & male)", "layered harmony vocals",
        "female choir", "male choir", "mixed choir", "children's choir",
        "gospel choir", "group vocals / gang vocals",
        "rap flow, male", "rap flow, female",
        "operatic soprano", "operatic tenor", "baritone vocal", "falsetto vocal",
        "growled / screamed vocal", "throat singing",
        "robotic / vocoder vocal", "auto-tuned vocal",
        "spoken word", "narrator / voice-over",
        "no vocals / n/a",
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
    "meter": "Time signature",
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
    "meter": "meter",
    "taktart": "meter",
    "time_signature": "meter",
    "time signature": "meter",
    "timesignature": "meter",
    "signature": "meter",
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
    "only voice - no words": "only voice - no words", "no words": "only voice - no words",
    "wordless": "only voice - no words", "vocalise": "only voice - no words",
    "vocalese": "only voice - no words", "scat": "only voice - no words",
    "humming": "only voice - no words",
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
    Tempo values are curated BPM ranges (e.g. ``Uptempo (130-145 BPM)``) that
    are passed through verbatim.  The description (the "further description"
    part) is appended verbatim.
    """
    parts: list[str] = []
    for field in STRUCTURED_FIELDS:
        raw = fields.get(field)
        value = str(raw).strip() if raw is not None else ""
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
