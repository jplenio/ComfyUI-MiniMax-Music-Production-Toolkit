"""Model switching, native graph wiring and request preservation without weights."""
import importlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from _toolkit_bootstrap import load_entry_point

ROOT = Path(__file__).resolve().parents[1]


class Graph:
    def __init__(self): self.nodes = {}
    def node(self, kind, **inputs):
        key = str(len(self.nodes))
        self.nodes[key] = {"class_type": kind, "inputs": inputs}
        return types.SimpleNamespace(out=lambda index: [key, index])
    def finalize(self): return self.nodes


class Yue2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, _ = load_entry_point()
        cls.profiles = importlib.import_module(cls.package.__name__ + '.model_profiles')
        cls.prompts = importlib.import_module(cls.package.__name__ + '.minimax_prompt_source')
        cls.structured = importlib.import_module(cls.package.__name__ + '.minimax_structured_prompt')

    def settings(self, model):
        profile = self.profiles.get_profile(model).as_payload()
        node = self.package.NODE_CLASS_MAPPINGS['MiniMaxMusicModelSettings']()
        args = {k:v[1]['default'] for k,v in node.INPUT_TYPES()['required'].items() if 'default' in v[1]}
        args.update(generation_seed=51, profile_json=json.dumps(profile))
        return json.dumps(profile), node.build(**args)[-1]

    def expand(self, model):
        profile, settings = self.settings(model)
        fake = types.ModuleType('comfy_execution.graph_utils'); fake.GraphBuilder = Graph
        with patch.dict(sys.modules, {'comfy_execution.graph_utils': fake}):
            return self.package.NODE_CLASS_MAPPINGS['MusicGeneration']().generate(
                profile, settings, 'English, folk, piano', '[Verse]\nA lantern in the rain',
                'yue2.safetensors', 'minimax.safetensors', 'encoder.safetensors', 'vae.safetensors')

    def test_only_selected_models_are_loaded(self):
        for model, expected, absent in [('YuE2', 'CheckpointLoaderSimple', 'UNETLoader'),
                                        ('MiniMax Music 3', 'UNETLoader', 'CheckpointLoaderSimple')]:
            graph = self.expand(model)['expand']
            kinds = {v['class_type'] for v in graph.values()}
            self.assertIn(expected, kinds); self.assertNotIn(absent, kinds)

    def test_yue_abc_and_actual_duration_feed_music_and_latents(self):
        graph = self.expand('YuE2')['expand']
        by_type = {v['class_type']: (k,v['inputs']) for k,v in graph.items()}
        abc_id, abc = by_type['YuE2GenerateABC']
        music_id, music = by_type['YuE2GenerateMusic']
        self.assertEqual(music['abc'], [abc_id,0])
        for key in ('clip','style','lyrics','seed','mode'):self.assertEqual(music[key],abc[key])
        self.assertEqual(by_type['EmptyYuE2LatentAudio'][1]['seconds'], [music_id,1])
        self.assertEqual(by_type['MusicGenerationReceipt'][1]['abc'], [abc_id,0])
        self.assertEqual(by_type['KSamplerWithConfig'][1]['positive'], [music_id,0])
        self.assertEqual(by_type['KSamplerWithConfig'][1]['negative'], [music_id,0])

    def test_sampler_defaults_follow_model(self):
        for model, expected in [('YuE2',(32,1.0,'dpm_2','sgm_uniform')),('MiniMax Music 3',(40,1.7,'euler','simple'))]:
            sampler = next(v['inputs'] for v in self.expand(model)['expand'].values() if v['class_type']=='KSamplerWithConfig')
            self.assertEqual(tuple(sampler[k] for k in ('steps','cfg','sampler_name','scheduler')),expected)

    def test_mismatched_settings_stop_before_loading(self):
        profile,_ = self.settings('YuE2');_, settings = self.settings('MiniMax Music 3')
        with self.assertRaisesRegex(ValueError,'disagree'):
            self.package.NODE_CLASS_MAPPINGS['MusicGeneration']().generate(profile,settings,'s','l','a','b','c','d')

    def test_yue_parser_never_loads_minimax_tokenizer(self):
        profile = self.profiles.get_profile('YuE2')
        with patch.object(self.prompts,'token_counter',side_effect=AssertionError('wrong tokenizer')):
            _, lyrics, info = self.prompts.MiniMaxParseExternalLLMOutputV16._apply_prompt_budget('folk','[Verse]\nSong',4500,False,profile)
        self.assertEqual(lyrics,'[Verse]\nSong');self.assertEqual(info['prompt_token_count_method'],'estimate')

    def test_style_and_lyrics_parse_separately(self):
        result=self.prompts._parse_sections('[Style]\nEnglish, folk\n[Lyrics]\n[Verse]\nLight in rain\n[Title]\nLight\n[Image_Prompt]\nA lantern','Style')
        self.assertEqual(result['caption'],'English, folk')
        self.assertEqual(result['lyrics'],'[Verse]\nLight in rain')

    def test_all_minimax_templates_have_yue_versions(self):
        for p in (ROOT/'prompts/system').glob('minimax-music3-*.txt'):
            target=ROOT/'prompts/system/yue2'/p.name.removeprefix('minimax-music3-')
            text=target.read_text(encoding='utf-8')
            for tag in ('[Style]','[Lyrics]','[Title]','[Image_Prompt]'):self.assertIn(tag,text)
            self.assertNotIn('roughly twice as many sections',text)
            self.assertNotIn('[Caption]',text)
            self.assertNotIn('recommended section counts',text)

    def test_backend_switches_bundled_family_and_preserves_custom(self):
        yue=self.profiles.get_profile('YuE2')
        text,origin=self.structured._resolve_system_prompt('bundled_library','','minimax-music3-production.txt','old MiniMax text',yue)
        self.assertEqual(origin,'yue2/production.txt');self.assertIn('[Style]',text)
        text,origin=self.structured._resolve_system_prompt('manual','','','my edited system',yue)
        self.assertEqual(text,'my edited system')
        text,_=self.structured._resolve_system_prompt('bundled_library','','yue2/production.txt','edited Yue2',yue)
        self.assertEqual(text,'edited Yue2')

    def test_report_uses_selected_model(self):
        node=self.package.NODE_CLASS_MAPPINGS['MiniMaxPromptReport']()
        result=node.report('folk','[Verse]\nHello','Hello','Lantern',self.settings('YuE2')[0])['result'][0]
        self.assertIn('YuE2',result);self.assertNotIn('MiniMax tokenizer',result)

    def test_metadata_records_actual_model_and_abc(self):
        profile,settings=self.settings('YuE2')
        receipt=self.package.NODE_CLASS_MAPPINGS['MusicGenerationReceipt']().build(settings,'X:1\nK:C\nC',42,'{"checkpoint":"yue.safetensors"}')[0]
        metadata=importlib.import_module(self.package.__name__+'.production_metadata')
        result=metadata.build_generation_metadata({},model_identity_json=receipt,caption='folk',max_duration=300)
        self.assertNotIn('minimax_music3',result)
        self.assertEqual(result['generation']['generated_seconds'],42)
        self.assertEqual(result['generation']['abc'],'X:1\nK:C\nC')
        self.assertEqual(result['style'],'folk')

    def test_yue_workflow_links_and_types(self):
        w=json.loads((ROOT/'example_workflows/Yue2_MM3_Production_Toolkit.json').read_text(encoding='utf-8'))
        ns={n['id']:n for n in w['nodes']}
        self.assertEqual(ns[37]['type'],'MusicGeneration')
        self.assertEqual(ns[118]['widgets_values'],['YuE2', True, 'Model default', True])
        seen=set()
        for lid,src,ss,dst,ds,typ in w['links']:
            self.assertNotIn((dst,ds),seen);seen.add((dst,ds))
            self.assertEqual(ns[dst]['inputs'][ds]['link'],lid)
            self.assertIn(lid,ns[src]['outputs'][ss]['links'])
            self.assertIn(ns[dst]['inputs'][ds]['type'],(typ,'*','COMBO'))
        links={l[0]:l for l in w['links']}
        for name,source in [('user_prompt',80),('model_check_report',101),('llm_status',81)]:
            inp=next(i for i in ns[53]['inputs'] if i['name']==name)
            self.assertEqual(links[inp['link']][1],source)

    def test_yue_duration_is_independent_and_legacy_falls_back(self):
        profile,_=self.settings('YuE2')
        node=self.package.NODE_CLASS_MAPPINGS['MiniMaxMusicModelSettings']()
        args={k:v[1]['default'] for k,v in node.INPUT_TYPES()['required'].items() if 'default' in v[1]}
        args.update(generation_seed=1,max_duration=210,profile_json=profile)
        self.assertEqual(node.build(**args)[0],210)
        self.assertEqual(node.build(**args,yue2_max_duration=360)[0],360)
        args['profile_json']=self.settings('MiniMax Music 3')[0]
        self.assertEqual(node.build(**args,yue2_max_duration=360)[0],210)

    def test_yue_workflow_requested_defaults(self):
        w=json.loads((ROOT/'example_workflows/Yue2_MM3_Production_Toolkit.json').read_text(encoding='utf-8'))
        nodes={n['type']:n for n in w['nodes']}
        self.assertEqual(nodes['MiniMaxMusicModelSettings']['widgets_values_named']['yue2_steps'],40)
        self.assertEqual(nodes['MiniMaxMusicModelSettings']['widgets_values_named']['yue2_max_duration'],360)
        self.assertEqual(nodes['MusicGeneration']['widgets_values_named']['yue2_checkpoint'],'yue2_3b_bf16.safetensors')
        check=nodes['MiniMaxModelAutodownload']
        self.assertTrue(check['widgets_values_named']['yue2_models'])
        self.assertTrue(check['widgets_values_named']['auto_download'])
        self.assertIsNotNone(next(i['link'] for i in check['inputs'] if i['name']=='model_profile_json'))

    def test_model_check_yue_selection_and_download_switch(self):
        module=importlib.import_module(self.package.__name__+'.minimax_autodownload')
        node=module.MiniMaxModelAutodownload()
        for model,enabled,expected in [('YuE2',True,1),('YuE2',False,0),('MiniMax Music 3',True,0)]:
            for download in (True,False):
                with patch.object(module,'preflight_models',return_value={'entries':[]}) as preflight, patch.object(module,'format_preflight_report',return_value=[]):
                    node.check(minimax_models=False,flux2_models=False,flashsr_models=False,llm_model=False,
                               yue2_models=enabled,auto_download=download,model_profile_json=self.settings(model)[0])
                    entries=preflight.call_args.args[0]
                    self.assertEqual(len(entries),expected)
                    self.assertEqual(preflight.call_args.kwargs['auto_download'],download)
                    if expected:
                        self.assertEqual(entries[0]['name'],'yue2_3b_bf16.safetensors')
                        self.assertEqual(entries[0]['bytes'],7799983228)
                        self.assertEqual(entries[0]['target'],'models/checkpoints')

    def test_markdown_preserves_lyric_lines_for_both_models(self):
        node=self.package.NODE_CLASS_MAPPINGS['MiniMaxPromptReport']()
        for model in ('YuE2','MiniMax Music 3'):
            report=node.report('folk','[Verse]\nFirst line\nSecond line','T','Cover',self.settings(model)[0])['result'][0]
            self.assertIn('```text\n[Verse]\nFirst line\nSecond line\n```',report)

    def test_mastering_preset_catalog(self):
        module=importlib.import_module(self.package.__name__+'.mastering_presets')
        cls=self.package.NODE_CLASS_MAPPINGS['MiniMaxMasteringCompressor']
        schema=cls.INPUT_TYPES()['required']
        self.assertEqual(len(module.PRESETS),12)
        self.assertIsNone(module.preset_settings('Custom'))
        for name,values in module.PRESETS.items():
            for key,value in values.items():
                kind,limits=schema[key]
                if isinstance(kind,list):self.assertIn(value,kind)
                if 'min' in limits:self.assertGreaterEqual(value,limits['min'])
                if 'max' in limits:self.assertLessEqual(value,limits['max'])
        with self.assertRaises(ValueError):module.preset_settings('Not a preset')
