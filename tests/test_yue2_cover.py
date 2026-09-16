"""Cover graph, naming and selective loading regressions; no model downloads."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from _toolkit_bootstrap import load_entry_point
from test_yue2 import Graph

ROOT = Path(__file__).resolve().parents[1]
ABC = 'X:1\nM:4/4\nL:1/8\nQ:1/4=100\nK:C\nCDEF G2G2|'


class CoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.mod = importlib.import_module(cls.pkg.__name__ + '.music_cover')
        cls.profiles = importlib.import_module(cls.pkg.__name__ + '.model_profiles')

    def node(self, name): return self.pkg.NODE_CLASS_MAPPINGS[name]()
    def profile(self, name='YuE2 Cover'): return self.node('MusicProductionControl').build(name)[0]
    def source(self, mode='full', audio='Night.theme.wav'):
        return json.dumps(dict(schema='music_cover_source_v1', audio=audio, mode=mode,
                               audio_encoder='sheetsage2_bf16.safetensors', title='Wrong title'))
    def settings(self, mode='full'):
        node = self.node('MiniMaxMusicModelSettings')
        args = {k: s[1]['default'] for k, s in node.INPUT_TYPES()['required'].items() if 'default' in s[1]}
        return node.build(**args, generation_seed=42, profile_json=self.profile(),
                          cover_source_json=self.source(mode), yue2_max_duration=360)[-1]
    def graph_module(self): return types.SimpleNamespace(GraphBuilder=Graph)

    def test_cover_profile_and_stage_defaults_match_yue(self):
        normal, cover = (self.profiles.get_profile(n) for n in ['YuE2', 'YuE2 Cover'])
        self.assertTrue(cover.is_cover and cover.is_yue2)
        for field in ['sampler_defaults', 'text_defaults', 'default_duration_seconds', 'system_prompt_file']:
            self.assertEqual(getattr(normal, field), getattr(cover, field))
        self.assertEqual(self.node('MusicProductionControl').build('YuE2 Cover')[8:], (True, False, True, True))

    def test_non_cover_does_not_touch_file_or_expand_transcription(self):
        with patch.dict(sys.modules, {'folder_paths': None, 'comfy_execution.graph_utils': None}):
            for name in ['YuE2', 'MiniMax Music 3']:
                self.assertEqual(self.node('MusicCoverSource').select(self.profile(name)), ('', ''))
                self.assertEqual(self.node('MusicCoverTranscription').transcribe(self.profile(name)), ('',))

    def test_filename_title_and_source_validation(self):
        for audio, expected in [('Night.theme.wav', 'Night.theme-cover'),
                                ('folder/Étude.flac [input]', 'Étude-cover'),
                                (r'folder\Moon song.mp3', 'Moon song-cover')]:
            self.assertEqual(self.mod.cover_record(self.source(audio=audio))['title'], expected)
        with self.assertRaises(ValueError): self.mod.cover_source('')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'song.wav'; path.write_bytes(b'audio fixture')
            host = types.SimpleNamespace(get_annotated_filepath=lambda _: str(path))
            with patch.dict(sys.modules, {'folder_paths': host}):
                source, title = self.node('MusicCoverSource').select(self.profile(), 'song.wav')
                self.assertEqual(title, 'song-cover')
                self.assertEqual(json.loads(source)['source_bytes'], 13)
                before = self.node('MusicCoverSource').IS_CHANGED(self.profile(), 'song.wav')
                path.write_bytes(b'audio fixture changed')
                self.assertNotEqual(before, self.node('MusicCoverSource').IS_CHANGED(self.profile(), 'song.wav'))

    def test_transcription_and_generation_use_same_abc_and_mode(self):
        for mode in ['melody', 'full']:
            with patch.dict(sys.modules, {'comfy_execution.graph_utils': self.graph_module()}):
                trans = self.node('MusicCoverTranscription').transcribe(self.profile(), self.source(mode))['expand']
                gen = self.node('MusicGeneration').generate(self.profile(), self.settings(mode), 'folk', '[Instrumental]',
                    'yue.safetensors', 'dit', 'clip', 'vae', cover_source_json=self.source(mode), cover_abc=ABC)['expand']
            trans = {n['class_type']: n['inputs'] for n in trans.values()}
            gen = {n['class_type']: n['inputs'] for n in gen.values()}
            self.assertEqual(set(trans), {'LoadAudio', 'AudioEncoderLoader', 'SheetSage2AudioToABC'})
            self.assertEqual(trans['SheetSage2AudioToABC']['mode'], mode)
            self.assertEqual(gen['YuE2GenerateMusic']['mode'], mode)
            self.assertEqual(gen['YuE2GenerateMusic']['abc'], ABC)
            self.assertNotIn('YuE2GenerateABC', gen)
            record = json.loads(self.node('MusicGenerationReceipt').build(**gen['MusicGenerationReceipt'] | {'seconds': 20})[0])
            self.assertEqual(record['abc'], ABC)
            self.assertEqual(record['cover_source']['title'], 'Night.theme-cover')
            self.assertNotIn('abc_settings', record)

    def test_empty_score_cannot_silently_generate_an_unrelated_song(self):
        with patch.dict(sys.modules, {'comfy_execution.graph_utils': self.graph_module()}):
            with self.assertRaisesRegex(ValueError, 'non-empty'):
                self.node('MusicGeneration').generate(self.profile(), self.settings(), 'folk', '[Instrumental]',
                    'yue', 'dit', 'clip', 'vae', cover_source_json=self.source(), cover_abc=' ')

    def test_prompt_uses_score_without_asking_for_new_title(self):
        node = self.node('MiniMaxStructuredPromptV20')
        args = {k: s[1].get('default', s[0][0] if isinstance(s[0], list) else '')
                for k, s in node.INPUT_TYPES()['required'].items()}
        args.update(user_prompt_source='manual', description_override='A varied instrumental piano arrangement',
                    lyrics='instrumental', model_profile_json=self.profile(), cover_source_json=self.source(), cover_abc=ABC)
        system, user, name, summary = node.build(**args)
        self.assertIn('Use source.title verbatim', system)
        self.assertIn('not sung words', system)
        self.assertIn(json.dumps(ABC), user)
        self.assertEqual(json.loads(summary)['cover_source']['title'], 'Night.theme-cover')
        self.assertFalse(json.loads(summary)['model_prompt_mismatch'])
        first = node.IS_CHANGED(**args)
        self.assertNotEqual(first, node.IS_CHANGED(**(args | {'cover_abc': ABC+'C|'})))

    def test_parser_overrides_llm_and_manual_title_and_source_prefix(self):
        node = self.node('MiniMaxParseExternalLLMOutputV16')
        for raw in ['', '[Style]\nfolk\n[Lyrics]\n[Instrumental]\n[Title]\nInvented\n[Image_Prompt]\nA mountain']:
            result = node.parse(1, 'fixed', 1, 'brief', 'Wrong prefix', 'Wrong fallback',
                structured_llm_output=raw, manual_caption='folk', manual_lyrics='[Instrumental]', manual_title='Wrong manual',
                model_profile_json=self.profile(), cover_source_json=self.source())
            self.assertEqual(result[2], ['Night.theme-cover'])
            self.assertNotIn('Wrong', result[4][0])
            self.assertEqual(json.loads(result[-1][0])['title_source'], 'audio_filename')

    def test_sheet_sage_download_only_for_cover_and_enabled_switch(self):
        mod = importlib.import_module(self.pkg.__name__+'.minimax_autodownload')
        for name in ['YuE2', 'YuE2 Cover', 'MiniMax Music 3']:
            for enabled in [True, False]:
                for download in [True, False]:
                    with patch.object(mod, 'preflight_models', return_value={'entries': []}) as run, \
                         patch.object(mod, 'format_preflight_report', return_value=[]):
                        self.node('MiniMaxModelAutodownload').check(False,False,False,False,download,
                            yue2_models=True, model_profile_json=self.profile(name), sheetsage2_models=enabled)
                        names = [e['name'] for e in run.call_args.args[0]]
                        self.assertEqual('sheetsage2_bf16.safetensors' in names, name=='YuE2 Cover' and enabled)
                        self.assertEqual(run.call_args.kwargs['auto_download'], download)

    def test_workflow_is_acyclic_and_cover_score_and_title_feed_all_consumers(self):
        d=json.loads((ROOT/'example_workflows/Yue2_MM3_Production_Toolkit.json').read_text(encoding='utf-8'))
        nodes={n['id']:n for n in d['nodes']};links={l[0]:l for l in d['links']}
        def source(nid,name):
            return links[next(i['link'] for i in nodes[nid]['inputs'] if i['name']==name)][1]
        for nid in [80,37]:self.assertEqual(source(nid,'cover_abc'),122)
        for nid in [80,53,55,37,122]:self.assertEqual(source(nid,'cover_source_json'),121)
        self.assertEqual(source(122,'model_check_report'),101)
        for nid in [35,46,52,63,99,77,108]:self.assertEqual(source(nid,'title'),53)
        for nid in [54,99]:self.assertEqual(source(nid,'source_name'),53)
        done=set()
        def visit(nid,active):
            self.assertNotIn(nid,active)
            if nid in done:return
            for inp in nodes[nid].get('inputs',[]):
                if inp.get('link') is not None:visit(links[inp['link']][1],active|{nid})
            done.add(nid)
        for nid in nodes:visit(nid,set())
