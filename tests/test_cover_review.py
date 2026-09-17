"""Regression cases found while reviewing the cover path; no model downloads."""
import importlib
import json
from pathlib import Path
import tempfile
import sys
import types
import unittest
from unittest.mock import patch

from _toolkit_bootstrap import load_entry_point
import test_cover_lyrics as fixtures
ABC = fixtures.ABC


class CoverReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.score = importlib.import_module(cls.pkg.__name__ + '.cover_score')
        cls.contract = importlib.import_module(cls.pkg.__name__ + '.cover_lyrics_contract')
        cls.whisper = importlib.import_module(cls.pkg.__name__ + '.whisper_lyrics')

    def test_instrumental_transfers_notes_and_preserves_native_fields_and_chords(self):
        abc = ABC.replace('"Cmaj7"C2 D2', 'M:3/4\nK:G\n"Cmaj7"C2 D2')
        result = self.score.adapt_cover_score(abc, 'instrumental', 'Piano')['abc']
        before, after = map(self.score.parse_cover_score, (abc, result))
        self.assertEqual(after.voices, ['Vocal', 'Ins'])
        for old, new in zip(before.sections, after.sections):
            self.assertEqual(new.syllables(), 0)
            self.assertEqual(new.syllables('Ins'), old.syllables())
            def pitched_events(music):
                return [(m.group('note'), bool(m.group('tie')))
                        for m in self.score._EVENT_RE.finditer(self.score.music_content(music))
                        if m.group('note')]
            self.assertEqual(pitched_events(old.melody()), pitched_events(new.melody('Ins')))
            # The mute operation must retain every duration in the same order.
            import re
            old_grid = re.sub(r"[=_^]{0,2}[A-Ga-g][,']*", 'z',
                              re.sub(r'"[^"\n]*"', '', self.score.music_content(old.melody())))
            new_grid = re.sub(r'"[^"\n]*"', '', self.score.music_content(new.melody()))
            self.assertEqual(old_grid.replace('-', ''), new_grid)
        self.assertIn('"Cmaj7"z2', result)
        self.assertIn('M:3/4\nK:G', result)
        self.assertEqual(self.score.adapt_cover_score(result, 'instrumental', 'Piano')['abc'], result)

    def test_multiblock_sections_and_instrumental_interlude_survive(self):
        abc = ABC.replace('% verse', 'V: Vocal\nz8|\nV: Ins\nC2D2E2F2|\n% verse')
        before = self.score.parse_cover_score(abc)
        self.assertEqual(len(before.sections), 3)
        self.assertEqual(before.sections[0].syllables(), 4)
        out = self.score.adapt_cover_score(abc, 'instrumental')['abc']
        self.assertIn('V: Ins\nC2D2E2F2|', out)
        self.assertEqual([x.label for x in self.score.parse_cover_score(out).sections], ['intro', 'verse', 'chorus'])

    def test_fractional_ties_fields_and_missing_vocal_are_not_syllables(self):
        self.assertEqual(self.score.count_melody_notes('K:F\nM:3/4\nC/2-C/2 z2 D2 !fermata!E2'), 3)
        section = self.score.ScoreSection('solo', 1, {'Ins': 'C2D2E2F2|'})
        self.assertEqual(section.syllables(), 0)
        self.assertIn('NOT measured sung syllables', self.score.score_syllable_brief({'sections': [], 'total_syllables': 0}))

    def test_original_lyrics_enforce_order_short_words_and_repetitions(self):
        for wrong in ('we go', 'go we we go', 'we go we go we go', 'we no we go'):
            with self.assertRaisesRegex(ValueError, 'changed, reordered'):
                self.contract.apply_cover_lyrics('original lyrics', 'folk', '[Verse]\n'+wrong, 'we go we go')
        self.contract.apply_cover_lyrics('original lyrics', 'folk', '[Verse]\nWe go!\n[Chorus]\nWe go.', 'we go we go')

    def test_rejects_copied_new_lyrics_and_mismatched_arrangement(self):
        with self.assertRaisesRegex(ValueError, 'copied'):
            self.contract.apply_cover_lyrics('new lyrics', 'folk', '[Verse]\nwe go', 'we go')
        with self.assertRaisesRegex(ValueError, 'sections and Lyrics tags differ'):
            self.contract.apply_cover_lyrics('new lyrics', '01 [Verse]: soft\n02 [Chorus]: loud',
                                            '[Chorus]\nwe go\n[Verse]\nwe stay')

    def test_instrumental_removes_words_and_positive_vocal_style_instructions(self):
        style, lyrics = self.contract.apply_cover_lyrics('instrumental',
            'Folk. Female voice with choir. Piano rises.', '[Verse]\nSing to me\n[Chorus]\nla la')
        self.assertEqual(lyrics, '[Verse]\n[Chorus]')
        self.assertNotIn('Female', style)
        self.assertIn('Piano rises', style)
        self.assertIn('No human voices', style)

    def test_whisper_lazy_cuda_failure_retries_and_drops_partial_result(self):
        mod = self.whisper
        devices = []
        def get_model(_folder, device, compute):
            devices.append(device)
            def transcribe(_samples, **kwargs):
                self.assertTrue(kwargs['word_timestamps'])
                def segments():
                    if device == 'cuda':
                        yield types.SimpleNamespace(start=0, end=1, text='partial wrong text')
                        raise RuntimeError('CUDA failure during iteration')
                    yield types.SimpleNamespace(start=0, end=1, text='complete text',
                        words=[types.SimpleNamespace(word='complete', start=0, end=.5)])
                return segments(), types.SimpleNamespace(language='en', duration=1)
            return types.SimpleNamespace(transcribe=transcribe)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(mod, 'whisper_model_dir', return_value=Path(tmp)), \
             patch.object(mod, '_load_engine'), patch.object(mod, '_get_model', side_effect=get_model), \
             patch.object(mod, '_resolve_device', return_value=('cuda', 'float16')), \
             patch.object(mod, 'load_audio_mono', return_value=[0]*16000):
            result = mod.transcribe('source.wav')
        self.assertEqual(devices, ['cuda', 'cpu'])
        self.assertEqual(result['text'], 'complete text')
        self.assertEqual(result['segments'][0]['words'][0]['start'], 0)
        self.assertEqual(result['device'], 'cpu')

    def test_new_lyrics_receives_time_reference_with_distinct_role(self):
        helper = fixtures.StructuredPromptCoverTests()
        helper.pkg = self.pkg
        helper.node = self.pkg.NODE_CLASS_MAPPINGS['MiniMaxStructuredPromptV20']()
        record = {'schema': 'music_cover_lyrics_v1', 'text': 'Original words', 'language': 'en',
                  'segments': [{'start': 3, 'end': 5, 'text': 'Original words'}]}
        system, user, _, summary = helper.node.build(**helper.args('new lyrics', 'no', json.dumps(record)))
        self.assertIn('completely NEW', user)
        self.assertIn('"start": 3', user)
        self.assertIn('melisma', system)
        self.assertEqual(json.loads(summary)['fields']['lyrics'], 'yes')

    def test_both_lyric_modes_run_whisper_but_instrumental_does_not(self):
        profile = self.pkg.NODE_CLASS_MAPPINGS['MusicProductionControl']().build('YuE2 Cover')[0]
        source = {'schema':'music_cover_source_v1','audio':'source.wav','mode':'melody','audio_encoder':'sheet'}
        with patch.object(self.whisper, 'transcribe', return_value={'text':'words'}) as run, \
             patch.dict(sys.modules, {'folder_paths': types.SimpleNamespace(get_annotated_filepath=lambda value: value)}):
            for mode in ('new lyrics', 'original lyrics', 'instrumental'):
                source['lyrics_mode'] = mode
                self.whisper.MusicCoverLyrics().transcribe_lyrics(profile, json.dumps(source))
            self.assertEqual(run.call_count, 2)

    def test_workflow_passes_whisper_record_to_both_text_consumers(self):
        workflow = json.loads((Path(__file__).resolve().parents[1]/'example_workflows/Music_Production_Toolkit.json').read_text(encoding='utf8'))
        for target in (80, 53):
            self.assertTrue(any(l[1:4] == [126, 1, target] for l in workflow['links']))


if __name__ == '__main__': unittest.main()
