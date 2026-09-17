"""Mode constraints shared by the cover parser and native graph boundary."""
import re
import unicodedata

TAG = re.compile(r'^\s*\[([^\]\n]+)\]\s*$', re.M)


def lyric_words(text):
    """Ordered Unicode words, retaining short words and every repetition."""
    text = TAG.sub('', str(text or ''))
    text = unicodedata.normalize('NFKC', text).replace('’', "'").casefold()
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", text, re.UNICODE)


def apply_cover_lyrics(mode, style, lyrics, transcript=None, lyrics_locked=False):
    """Mode constraints for one cover result.

    ``lyrics_locked`` marks a deliberate user decision to reuse known words
    verbatim.  It only relaxes the check that would otherwise treat those words
    as an LLM that lazily copied the source; every other mode rule still applies.
    """
    arrangement = re.findall(r'^\s*\d+[.)]?\s*\[([^\]\n]+)\]', style, re.M)
    if arrangement and [t.casefold() for t in arrangement] != [t.casefold() for t in TAG.findall(lyrics)]:
        raise ValueError('YuE2 Cover: numbered Style sections and Lyrics tags differ in order/count. '
                         'Retry the LLM or align both section lists before generating.')
    if mode == 'instrumental':
        tags = TAG.findall(lyrics)
        lyrics = '\n'.join('[' + tag + ']' for tag in tags) or '[Instrumental]'
        # Remove positive vocal instructions from a disobedient LLM/manual Style.
        # Keep instrumental arrangement clauses; the explicit rule is always last.
        clauses = re.split(r'(?<=[.!?;])\s+|\n', style)
        vocal = re.compile(r'\b(vocals?|voices?|singers?|singing|sung|spoken|choirs?|humming|rap|rapping|scat)\b', re.I)
        cleaned = []
        for clause in clauses:
            if not vocal.search(clause):
                cleaned.append(clause)
            else:
                section = re.match(r'\s*(?:\d+[.)]?\s*)?\[[^\]]+\]', clause)
                if section:
                    cleaned.append(section.group(0) + ': instrumental melody and accompaniment.')
        style = '\n'.join(cleaned).strip()
        style += '\nInstrumental only. No human voices, singing, speech, humming, choir or vocalizations.'
        return style.strip(), lyrics
    if not lyric_words(lyrics):
        raise ValueError('YuE2 Cover: this lyrics_mode requires sung words in [Lyrics]. Retry the LLM or fill manual_lyrics.')
    if mode == 'new lyrics' and transcript and not lyrics_locked and lyric_words(transcript) == lyric_words(lyrics):
        raise ValueError('YuE2 Cover: new lyrics copied the complete source transcript. '
                         'Ask the LLM for new words matching your selected template and the source phrasing.')
    if mode == 'original lyrics' and transcript is not None:
        if not lyric_words(transcript):
            raise ValueError('YuE2 Cover: original lyrics require a non-empty Whisper transcription or a reviewed transcript.')
        if lyric_words(transcript) != lyric_words(lyrics):
            raise ValueError('YuE2 Cover: the LLM changed, reordered, repeated or omitted transcribed original lyrics. '
                             'Retry the LLM or put the complete transcript in manual_lyrics with section tags. '
                             'Every word and repetition must remain in its original order.')
    return style, lyrics
