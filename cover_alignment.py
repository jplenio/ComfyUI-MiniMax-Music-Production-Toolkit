"""Native-score timing and deterministic placement of authoritative source words."""
import bisect
import hashlib
import re

from .cover_lyrics_contract import TAG, lyric_words
from .third_party.yue2_abc import parse_abc


def score_timeline(abc):
    score = parse_abc(abc.strip())
    bars = score.voices['Vocal'].bars
    sections, bar_index, pending = [], 0, None
    for index, line in enumerate(score.text.splitlines()):
        if line.startswith('% '):
            pending = line[2:].strip()
        if score.music_lines.get(index) != 'Vocal':
            continue
        if pending or not sections:
            label = pending or 'Instrumental'
            sections.append({'tag': label.title(), 'start_seconds': float(bars[bar_index][0] * 60 / score.bpm),
                             'start_bar': bar_index + 1})
            pending = None
        for bar in line.rstrip('|').split('|'):
            rest = re.fullmatch(r'Z([2-4])?', bar.strip())
            bar_index += int(rest.group(1) or 1) if rest else 1
    duration = float(score.voices['Vocal'].time * 60 / score.bpm)
    for index, section in enumerate(sections):
        section['end_seconds'] = sections[index+1]['start_seconds'] if index+1 < len(sections) else duration
        section['bars'] = (sections[index+1]['start_bar'] if index+1 < len(sections) else len(bars)+1) - section['start_bar']
        section['vocal_onsets_seconds'] = [round(float(onset * 60 / score.bpm), 4)
            for onset, pitch, length in score.voices['Vocal'].notes
            if section['start_seconds'] <= float(onset * 60 / score.bpm) < section['end_seconds']]
    return {'abc_sha256': hashlib.sha256(abc.strip().encode()).hexdigest(), 'bpm': score.bpm,
            'duration_seconds': duration, 'sections': sections,
            'validation': 'pinned_upstream_bounded_native_dialect'}


def original_lyrics(transcript, record, sections, proposed):
    """Use ASR words unchanged; the LLM has no authority to rewrite them."""
    if not lyric_words(transcript):
        raise ValueError('YuE2 Cover: original lyrics require a non-empty Whisper transcription or a reviewed transcript.')
    if not sections:
        # Legacy graphs can keep a verified layout. A bad rewrite is repaired
        # from the source, preserving original line breaks, with no guessed times.
        if lyric_words(proposed) == lyric_words(transcript):
            return proposed, {'method': 'verified_llm_layout', 'repaired': False}
        tags = TAG.findall(proposed) or ['Verse']
        return '\n\n'.join('['+tag+']'+('\n'+transcript if i == 0 else '') for i,tag in enumerate(tags)), \
            {'method': 'source_order_no_timing', 'repaired': True}
    segments = (record or {}).get('segments') or []
    timed = bool(segments) and lyric_words('\n'.join(str(s.get('text','')) for s in segments)) == lyric_words(transcript)
    buckets = [[] for _ in sections]
    starts = [s['start_seconds'] for s in sections]
    if timed:
        previous_index = 0
        for segment in segments:
            words = segment.get('words') or []
            if lyric_words(' '.join(str(w.get('word','')) for w in words)) != lyric_words(segment.get('text','')):
                words = [dict(word=segment.get('text',''), start=segment.get('start',0), end=segment.get('end',0))]
            current, line = None, []
            for word in words:
                midpoint = (float(word.get('start',0)) + float(word.get('end',0))) / 2
                index = max(previous_index, min(len(sections)-1, max(0, bisect.bisect_right(starts, midpoint)-1)))
                if current is not None and index != current:
                    buckets[current].append(' '.join(line)); line = []
                current = previous_index = index
                line.append(str(word['word']).strip())
            if line:
                buckets[current].append(' '.join(line))
    else:
        # No timing evidence: preserve the source instead of inventing timestamps.
        buckets[0] = transcript.splitlines()
    result = '\n\n'.join('['+s['tag']+']'+ ('\n'+'\n'.join(lines) if lines else '')
                         for s,lines in zip(sections,buckets))
    if lyric_words(result) != lyric_words(transcript):
        raise ValueError('YuE2 Cover: source-word alignment failed its lossless-word check.')
    return result, {'method': 'whisper_times_to_abc_sections' if timed else 'source_order_no_timing',
                    'repaired': lyric_words(proposed) != lyric_words(transcript),
                    'word_order_verified': True, 'section_count': len(sections)}


def measured_style_headers(style, sections):
    """Replace guessed arrangement times, keeping the musical prose intact."""
    pattern = re.compile(r'^\s*\d+[.)]?\s*\[([^\]\n]+)\]\s*:\s*([^\n]*)', re.M)
    matches = list(pattern.finditer(style))
    if not matches:
        return style
    if len(matches) != len(sections):
        raise ValueError('YuE2 Cover: Style section count differs from the measured score. Retry the arrangement.')
    def clock(value):
        seconds = round(value)
        return f'{seconds//60:02d}:{seconds%60:02d}'
    for index in range(len(matches)-1, -1, -1):
        match, section = matches[index], sections[index]
        body = match.group(2)
        if re.match(r'^\d{1,2}:\d{2}\s*[-–—]', body):
            # Decimal bar counts are not sentence boundaries.
            body = re.sub(r'^.*?\.(?!\d)\s*', '', body, count=1) if re.search(r'\.(?!\d)', body) else ''
        header = (f"{index+1:02d} [{section['tag']}]: {clock(section['start_seconds'])}-"
                  f"{clock(section['end_seconds'])}, {section['bars']} measures. "+body).rstrip()
        style = style[:match.start()] + header + style[match.end():]
    return style
