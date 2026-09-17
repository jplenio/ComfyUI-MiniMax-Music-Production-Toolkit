"""Keep detailed production prose out of the instrumental model's text channel.

This is a bounded vocabulary compiler, not a voice-removal algorithm. Reports
retain the full arrangement. Native tags carry its instrumental identity and arc.
"""
import re
from .cover_lyrics_contract import TAG
from .prompt_metadata import CURATED_FIELD_OPTIONS

IDENTITY = ('deep house', 'house', 'techno', 'disco', 'funk', 'jazz', 'blues', 'rock',
            'pop', 'ambient', 'cinematic', 'classical', 'orchestral', 'folk', 'country',
            'reggae', 'soul', 'metal', 'trance', 'drum and bass', 'lo-fi', 'hip hop',
            'synthwave', 'electronic', 'acoustic', 'latin', 'bossa nova', 'swing')
SOUNDS = ('Rhodes', 'electric piano', 'piano', 'electric guitar', 'acoustic guitar',
          'guitar', 'strings', 'brass', 'flute', 'saxophone', 'trumpet', 'organ',
          'vibraphone', 'lead synth', 'synth', 'pad', 'sub-bass', 'bass', 'drums',
          'kick', 'hi-hat', 'hi-hats', 'shaker', 'congas', 'tambourine', 'handclaps',
          'warm', 'soft', 'bright', 'dark', 'lush', 'sparse', 'restrained', 'full',
          'intimate', 'hypnotic', 'syncopated', 'sustained', 'staccato', 'legato',
          'filtered', 'arpeggios', 'octave', 'countermelody', 'solo', 'breakdown',
          'build', 'buildup', 'crescendo', 'fade-out', 'reverb', 'delay', 'tape')
SECTIONS = ('Intro', 'Verse', 'Pre-Chorus', 'Chorus', 'Bridge', 'Interlude', 'Solo', 'Outro', 'Instrumental')


def _matches(text, vocabulary):
    return [term for term in vocabulary if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)', text, re.I)]


# A clause that could smuggle a voice, a language, a duration instruction or a
# narrative back into the native text channel is dropped whole.  The rule is
# deliberately blunt: losing one identity clause is cheap, letting a singer back
# into an instrumental is not.
_HAZARD = re.compile(
    r'\b(vocals?|voices?|singer|singers|singing|sung|spoken|choir|humming|rap|scat|'
    r'lyrics?|words?|languages?|duration|seconds|minutes|instructions?|prompts?|'
    r'read|reads|says?|speak|speaks)\b', re.I)

# Scheduling and score-supervision sentences are not style.  A real Style begins
# with them ("Target duration ... follow the supplied ABC ... the source score may
# end earlier") before it ever names the music, so they have to be recognised or
# they consume the whole identity budget.
_SCORE_TALK = re.compile(
    r'\b(score|abc|target|range|boundar|phrase order|measured|span|cadence|decay|'
    r'stretch|trim|cropp?|clock|supplied|follows?|follow|approximate|bar\s|bars\b|'
    r'complete[sd]?\s+around|arrangement (?:follows|below)|section)\b', re.I)

INSTRUMENTAL_RULE = (
    "Instrumental only. No human voices, singing, speech, humming, choir or vocalizations."
)
IDENTITY_MAX_CHARS = 600

# Section labels the bundled instrumentals instruction forbids: they read as an
# invitation to sing.  The source score's own labels are kept for the report, but
# the text the engine receives uses the instrumental vocabulary instead.
VOCAL_ORIENTED_TAGS = frozenset({"Verse", "Pre-Chorus", "Chorus"})
INSTRUMENTAL_TAG = "Instrumental"


# The curated language names the toolkit already offers.  An instrumental has no
# language, so an item carrying one is dropped rather than passed on.
def _language_terms() -> tuple:
    terms = []
    for item in CURATED_FIELD_OPTIONS.get("language", ()) or ():
        for part in re.split(r"[/()]", str(item)):
            cleaned = part.strip()
            if len(cleaned) > 2 and cleaned.casefold() not in {"and", "the"}:
                terms.append(cleaned)
    return tuple(dict.fromkeys(terms))


_LANGUAGE_TERMS = _language_terms()
_LANGUAGE_RE = re.compile("|".join(re.escape(term) for term in _LANGUAGE_TERMS), re.I) \
    if _LANGUAGE_TERMS else None


def identity_sentence(style: str) -> str:
    """The Style's opening identity prose, reduced to the items that may travel.

    Everything from the first numbered arrangement entry onward belongs to the
    section arc and is handled separately, so only the identity paragraph is read
    here.  The prose is split into its individual items and each item is judged on
    its own, because a blanket clause rule would let "English, synth-pop, ..."
    either through or away as a whole.
    """
    head = re.split(r'^\s*\d+[.)]?\s*\[', str(style or ''), maxsplit=1, flags=re.M)[0]
    head = re.split(r'Arrangement\s*\(section order\)\s*:?', head, maxsplit=1, flags=re.I)[0]
    head = re.sub(r'^\s*\[\s*Style\s*\]\s*', '', head.strip(), flags=re.I)
    items = [item.strip(' .;,:') for item in re.split(r'[,;\n]|\.\s+|:\s+', head)]
    kept = []
    for item in items:
        if not item or _HAZARD.search(item) or _SCORE_TALK.search(item):
            continue
        if _LANGUAGE_RE is not None and _LANGUAGE_RE.search(item):
            continue
        kept.append(item)
    return ', '.join(kept)[:IDENTITY_MAX_CHARS]


def instrumental_conditioning(style, lyrics, abc, lead, cot_mode="full"):
    from .cover_alignment import score_timeline
    timeline = score_timeline(abc)
    # Deliberately no arbitrary text: a singer, language, title, quoted phrase,
    # duration instruction or LLM narrative cannot leak through this vocabulary.
    genres = tuple(dict.fromkeys([*IDENTITY, *(part.strip() for item in CURATED_FIELD_OPTIONS['genre']
                                              for part in item.split('/') if part.strip())]))
    identity = _matches(style, genres)
    sounds = _matches(style, SOUNDS)
    instrument = next((term for term in SOUNDS[:16] if term.casefold() == str(lead).casefold()), 'instrumental ensemble')
    tags = ['instrumental', *identity, *sounds, instrument+' melody',
            str(timeline['bpm'])+' BPM']
    if str(lead) == 'Remove vocal line (accompaniment only)':
        tags.remove(instrument+' melody')
        tags.append('accompaniment only')
        instrument = 'accompaniment'
    tags += [line[2:] for line in abc.splitlines() if line.startswith(('M:','K:'))][:2]
    blocks = re.split(r'^\s*\d+[.)]?\s*\[[^\]]+\]', style, flags=re.M)[1:]
    arc = []
    section_tags = []
    tag_map = {}
    for index, section in enumerate(timeline['sections']):
        source_tag = next((tag for tag in SECTIONS
                           if section['tag'].casefold() == tag.casefold()), INSTRUMENTAL_TAG)
        # Style and Lyrics have to stay one-to-one, so both sides get the same
        # instrumental label.
        tag = INSTRUMENTAL_TAG if source_tag in VOCAL_ORIENTED_TAGS else source_tag
        if tag != source_tag:
            tag_map[f"{index + 1} {source_tag}"] = tag
        section_tags.append(tag)
        texture = _matches(blocks[index] if index < len(blocks) else '', SOUNDS)
        arc.append(f"{index+1} {tag}: "+', '.join(texture or [instrument]))
    # The requested style leads, the compiled tags anchor it, the arc schedules
    # it and the explicit rule closes the vocal door.  Dropping the identity
    # prose was what made an instrumental sound unrelated to its template.
    identity_text = identity_sentence(style)
    native_style = '\n'.join(part for part in (
        identity_text,
        ', '.join(dict.fromkeys(tags)),
        '\n'.join(arc),
        INSTRUMENTAL_RULE,
    ) if part)
    native_lyrics = '\n\n'.join('['+tag+']' for tag in section_tags)
    mode_warning = ""
    if str(cot_mode) != 'melody':
        mode_warning = (
            "This instrumental cover used full conditioning, which asks the engine for melody and "
            "harmony from a score whose vocal part is empty by design; that is the one remaining "
            "structural invitation to sing. The upstream cover guide prescribes melody "
            "conditioning for a stylistic cover. If vocal-like artefacts appear, select 'melody' "
            "on Cover song / source audio and compare.")
    return native_style, native_lyrics, {'policy': 'instrumental_musical_tags_v3',
        'section_tag_map': tag_map,
        'cot_mode': str(cot_mode),
        'mode_note': mode_warning,
        'native_style': native_style, 'native_lyrics': native_lyrics,
        'style_identity': identity_text,
        'report_arrangement_tags': TAG.findall(lyrics), 'score_timeline': timeline,
        'note': ('Requested-style identity plus bounded musical tags, native ABC headers and '
                 'empty lyric sections; the identity prose is hazard-filtered. No acoustic '
                 'voice-free guarantee.')}
