"""Requested duration survives prompt assembly, parsing and native expansion."""
import importlib
import inspect
import json
from pathlib import Path
import re
import sys
import types
import unittest
from unittest.mock import patch

from _toolkit_bootstrap import load_entry_point
from test_cover_lyrics import ABC
from test_yue2 import Graph

ROOT = Path(__file__).resolve().parents[1]


class DurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.duration = importlib.import_module(cls.pkg.__name__ + '.song_duration')

    def node(self, name):
        return self.pkg.NODE_CLASS_MAPPINGS[name]()

    def profile(self, model='YuE2'):
        return self.node('MusicProductionControl').build(model)[0]

    def parse(self, length, model='YuE2', **overrides):
        args = dict(song_count=1, seed_mode='increment_from_base', base_seed=1,
                    user_prompt='Musical brief:\nLength: 4-5 minutes', source_name_override='',
                    fallback_title='Song', manual_caption='Instrumental piano.\n01 [Intro]: Motif.\n02 [Outro]: Resolve.',
                    manual_lyrics='[Intro]\nWe follow the road\n[Outro]' if model == 'YuE2 Cover' else '[Intro]\n\n[Outro]', model_profile_json=self.profile(model),
                    structured_summary_json=json.dumps({'fields': {'length': length}}))
        args.update(overrides)
        return self.node('MiniMaxParseExternalLLMOutputV16').parse(**args)

    def settings(self, parsed, model='YuE2', ceiling=360, **kwargs):
        node = self.node('MiniMaxMusicModelSettings')
        args = {k: v[1]['default'] for k, v in node.INPUT_TYPES()['required'].items() if 'default' in v[1]}
        args.update(generation_seed=parsed[5][0], profile_json=self.profile(model),
                    prompt_provenance_json=parsed[10][0], yue2_max_duration=ceiling)
        args.update(kwargs)
        return node.build(**args)[-1]

    def test_duration_units_and_ranges(self):
        for text, bounds in [('30 seconds', (30, 30)), ('1 minute', (60, 60)),
                             ('1-2 minutes', (60, 120)), ('2-3 minutes', (120, 180)),
                             ('3-4 minutes', (180, 240)), ('4-5 minutes', (240, 300)),
                             ('3:30', (210, 210)), ('2:30–3:00', (150, 180)),
                             ('30 seconds to 2 minutes', (30, 120)), ('2 min - 3 min', (120, 180)),
                             ('ca. 2,5 Minuten', (150, 150)), ('90 s', (90, 90))]:
            with self.subTest(text=text):
                request = self.duration.duration_request(text)
                self.assertEqual((request['minimum_seconds'], request['maximum_seconds']), bounds)
                self.assertEqual(request['target_seconds'], sum(bounds)/2)
        for text in ['custom', '', '0 seconds', '-3 minutes', '3:90', '4-2 minutes',
                     '120 BPM', '120', 'nan seconds', 'inf minutes', 'a short song']:
            with self.subTest(text=text):
                self.assertIsNone(self.duration.duration_request(text))

    def test_length_guides_native_prompts_without_reducing_generation_room(self):
        for length, target in [('30 seconds', 30), ('1 minute', 60),
                               ('1-2 minutes', 90), ('2-3 minutes', 150),
                               ('3-4 minutes', 210), ('4-5 minutes', 270)]:
            with self.subTest(length=length):
                parsed = self.parse(length)
                style, lyrics = parsed[0][0], parsed[1][0]
                settings = self.settings(parsed)
                self.assertTrue(style.startswith(f'Target duration: {target} seconds'))
                self.assertEqual(json.loads(settings)['max_duration'], 360)
                self.assertEqual(json.loads(settings)['duration_policy'], 'approximate_target_natural_ending')
                self.assertIn('even if they run beyond the target', style)
                fake = types.SimpleNamespace(GraphBuilder=Graph)
                with patch.dict(sys.modules, {'comfy_execution.graph_utils': fake}):
                    result = self.node('MusicGeneration').generate(self.profile(), settings, style, lyrics,
                                                                  'yue', 'dit', 'clip', 'vae')
                graph = {n['class_type']: n['inputs'] for n in result['expand'].values()}
                for kind in ['YuE2GenerateABC', 'YuE2GenerateMusic']:
                    self.assertEqual(graph[kind]['style'], style)
                    self.assertEqual(graph[kind]['lyrics'], lyrics)
                self.assertEqual(graph['YuE2GenerateMusic']['max_duration'], 360)
                md = self.node('MiniMaxPromptReport').report(style, lyrics, 'Song', 'Cover', self.profile())['result'][0]
                self.assertIn(style, md)
                receipt = json.loads(self.node('MusicGenerationReceipt').build(settings, 'ABC', target-10, '{}')[0])
                self.assertEqual(receipt['duration_result']['difference_from_target_seconds'], -10)
                self.assertEqual(receipt['duration_request']['requested_length'], length)

    def test_user_prompt_and_summary_keep_same_authoritative_target(self):
        workflow = json.loads((ROOT/'example_workflows/Music_Production_Toolkit.json').read_text(encoding='utf-8'))
        node = next(n for n in workflow['nodes'] if n['id'] == 80)
        values = {k: v for k, v in node['widgets_values_named'].items()
                  if k in inspect.signature(self.node('MiniMaxStructuredPromptV20').build).parameters}
        values.update(user_prompt_source='manual', user_prompt_file='custom',
                      length='3-4 minutes', description_override='Instrumental piano',
                      model_profile_json=self.profile())
        result = self.node('MiniMaxStructuredPromptV20').build(**values)
        self.assertIn('Target duration: 210 seconds; requested range: 180-240 seconds.', result[1])
        self.assertEqual(json.loads(result[3])['fields']['length'], '3-4 minutes')

    def test_ceiling_conflict_fails_instead_of_silently_shortening(self):
        with self.assertRaisesRegex(ValueError, 'Increase yue2_max_duration'):
            self.settings(self.parse('4-5 minutes'), ceiling=240)
        settings = json.loads(self.settings(self.parse('3-4 minutes'), ceiling=220))
        self.assertEqual(settings['max_duration'], 220)
        self.assertEqual(settings['duration_request']['target_seconds'], 210)

    def test_one_minute_song_can_finish_after_sixty_seconds(self):
        source = json.dumps(dict(schema='music_cover_source_v1', audio='Theme.wav', mode='full',
                                 audio_encoder='sheetsage2_bf16.safetensors'))
        for model in ['YuE2', 'YuE2 Cover']:
            with self.subTest(model=model):
                extra = {'cover_source_json': source} if model == 'YuE2 Cover' else {}
                parsed = self.parse('1 minute', model=model, **extra)
                settings = self.settings(parsed, model=model, ceiling=300, **extra)
                fake = types.SimpleNamespace(GraphBuilder=Graph)
                with patch.dict(sys.modules, {'comfy_execution.graph_utils': fake}):
                    result = self.node('MusicGeneration').generate(self.profile(model), settings,
                        parsed[0][0], parsed[1][0], 'yue', 'dit', 'clip', 'vae',
                        cover_abc=ABC, **extra)
                graph = {n['class_type']: (key, n['inputs']) for key, n in result['expand'].items()}
                music_id, music = graph['YuE2GenerateMusic']
                self.assertEqual(music['max_duration'], 300)
                # Decode the model's full returned duration, not the 60-second target.
                self.assertEqual(graph['EmptyYuE2LatentAudio'][1]['seconds'], [music_id, 1])
                self.assertEqual(result['result'][0], [graph['MiniMaxSafeAudioDecode'][0], 0])
                receipt = json.loads(self.node('MusicGenerationReceipt').build(
                    settings, 'ABC', 68.4, '{}', **extra)[0])
                self.assertEqual(receipt['generated_seconds'], 68.4)
                self.assertAlmostEqual(receipt['duration_result']['difference_from_target_seconds'], 8.4)
                self.assertEqual(receipt['max_duration'], 300)

    def test_manual_fallback_and_custom_do_not_restore_inherited_length(self):
        parsed = self.parse('custom')
        self.assertNotIn('duration_request', json.loads(parsed[10][0]))
        self.assertNotIn('Target duration:', parsed[0][0])
        self.assertEqual(json.loads(self.settings(parsed))['max_duration'], 360)
        legacy = self.parse('custom', structured_summary_json='', user_prompt='Length: 90 seconds')
        self.assertEqual(json.loads(self.settings(legacy))['max_duration'], 360)
        replaced = self.parse('30 seconds', manual_caption='Target duration: 400 seconds.\nInstrumental piano.')
        self.assertNotIn('400 seconds', replaced[0][0])
        self.assertEqual(replaced[0][0].count('Target duration:'), 1)
        freeform = self.parse('custom', manual_caption='Target duration: 180 seconds.\nInstrumental piano.')
        free_settings = json.loads(self.settings(freeform))
        self.assertEqual(free_settings['max_duration'], 360)
        self.assertEqual(free_settings['duration_source'], 'style_duration_plan')

    def test_minimax_runtime_and_manual_prompt_remain_compatible(self):
        parsed = self.parse('30 seconds', model='MiniMax Music 3')
        self.assertNotIn('Target duration:', parsed[0][0])
        settings = json.loads(self.settings(parsed, model='MiniMax Music 3', max_duration=285))
        self.assertEqual(settings['max_duration'], 285)
        self.assertNotIn('duration_request', settings)

    def test_timed_arrangement_cannot_be_silently_trimmed(self):
        with self.assertRaisesRegex(ValueError, 'timed arrangement'):
            self.parse('3 minutes', max_prompt_tokens=500, manual_lyrics='[Verse]\n' + 'Sung phrase\n'*1000)

    def test_cover_keeps_original_score_and_target(self):
        source = json.dumps(dict(schema='music_cover_source_v1', audio='Theme.wav', mode='melody',
                                 audio_encoder='sheetsage2_bf16.safetensors',
                                 lyrics_mode='new lyrics'))
        parsed = self.parse('2-3 minutes', model='YuE2 Cover', cover_source_json=source)
        settings = self.settings(parsed, model='YuE2 Cover', cover_source_json=source)
        abc = ABC
        native = importlib.import_module(self.pkg.__name__ + '.third_party.yue2_abc')
        fake = types.SimpleNamespace(GraphBuilder=Graph)
        with patch.dict(sys.modules, {'comfy_execution.graph_utils': fake}):
            result = self.node('MusicGeneration').generate(self.profile('YuE2 Cover'), settings,
                parsed[0][0], parsed[1][0], 'yue', 'dit', 'clip', 'vae', cover_source_json=source, cover_abc=abc)
        graph = {n['class_type']: n['inputs'] for n in result['expand'].values()}
        self.assertNotIn('YuE2GenerateABC', graph)
        self.assertEqual(graph['YuE2GenerateMusic']['abc'], native.strip_chords(abc))
        self.assertEqual(graph['YuE2GenerateMusic']['max_duration'], 360)
        self.assertEqual(parsed[2][0], 'Theme-cover')
        self.assertIn('do not invent score extensions', parsed[0][0])

    def test_workflow_duration_wires_are_connected_by_name(self):
        workflow = json.loads((ROOT/'example_workflows/Music_Production_Toolkit.json').read_text(encoding='utf-8'))
        nodes = {n['id']: n for n in workflow['nodes']}
        for source, output, target, field in [(80, 3, 53, 'structured_summary_json'),
                                              (53, 10, 55, 'prompt_provenance_json')]:
            slot = next(i for i, inp in enumerate(nodes[target]['inputs']) if inp['name'] == field)
            link_id = nodes[target]['inputs'][slot]['link']
            self.assertIn([link_id, source, output, target, slot, 'STRING'], workflow['links'])

    def test_all_active_templates_have_explicit_duration_plan(self):
        for path in (ROOT/'prompts/system').rglob('*.txt'):
            text = path.read_text(encoding='utf-8')
            with self.subTest(path=path.name):
                self.assertIn('REQUESTED DURATION: PLAN' if path.parent.name == 'yue2' else 'EXPLICIT TIME PLAN', text)
                self.assertIn('Approximate length, natural ending', text)
        example = (ROOT/'prompts/examples/yue2-instrumental-arrangement.txt').read_text(encoding='utf-8')
        spans = re.findall(r'^\d{2} \[[^\]]+\]: (\d{2}:\d{2})-(\d{2}:\d{2}), (\d+) bars', example, re.M)
        end = 0
        for start_text, end_text, bars in spans:
            start, stop = [sum(int(v)*factor for v, factor in zip(t.split(':'), (60, 1))) for t in [start_text, end_text]]
            self.assertEqual(start, end)
            self.assertEqual(stop-start, int(bars)*4*60/120)
            end = stop
        self.assertEqual(len(spans), 8)
        self.assertEqual(end, 240)


if __name__ == '__main__':
    unittest.main()
