"""Exercise central choices and all reachable workflow consumers, without model weights."""
import importlib
import itertools
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from _toolkit_bootstrap import load_entry_point

ROOT = Path(__file__).resolve().parents[1]


class ProductionControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, _ = load_entry_point()
        cls.control = cls.package.NODE_CLASS_MAPPINGS['MusicProductionControl']()
        cls.gate = cls.package.NODE_CLASS_MAPPINGS['MusicOptionalStage']()

    def test_defaults_and_overrides(self):
        self.assertEqual(self.control.build()[8:], (True, False, True, True))
        for model, default in [('YuE2', False), ('YuE2 Cover', False), ('MiniMax Music 3', True)]:
            for setting, expected in [('Model default', default), ('On', True), ('Off', False)]:
                result = self.control.build(model, False, setting, False)
                self.assertEqual(result[8:], (False, expected, False, True))
                self.assertEqual(json.loads(result[0])['production_stages']['refinement'], expected)

    def test_lazy_gate_only_requests_selected_audio_and_reports(self):
        self.assertEqual(self.gate.check_lazy_status(False, 'Refinement', report_1=None), ['original_audio'])
        self.assertEqual(self.gate.check_lazy_status(False, 'Refinement', original_audio=object(), report_1=None), [])
        self.assertEqual(self.gate.check_lazy_status(True, 'Refinement', report_1=None, report_2='ready'), ['processed_audio', 'report_1'])
        self.assertEqual(self.gate.check_lazy_status(True, 'Mastering', processed_audio=object(), report_1='ready'), [])

    def test_bypass_preserves_audio_and_records_no_processing(self):
        original, processed = object(), object()
        for stage in ('Refinement', 'Mastering'):
            result = self.gate.select(False, stage, original, processed, report_1='stale')
            self.assertIs(result[0], original)
            self.assertEqual(json.loads(result[1])['status'], 'bypassed')
            self.assertNotIn('stale', result)
            result = self.gate.select(True, stage, original, processed, report_1='actual')
            self.assertIs(result[0], processed)
            self.assertEqual(result[1], 'actual')

    def test_cover_preview_skips_render_and_retains_image_when_on(self):
        node = self.package.NODE_CLASS_MAPPINGS['MusicOptionalCoverPreview']()
        self.assertEqual(node.check_lazy_status(False), [])
        self.assertEqual(node.preview(False), {'ui': {'images': []}, 'result': (None,)})
        calls = []
        fake = types.SimpleNamespace(PreviewImage=lambda: types.SimpleNamespace(
            save_images=lambda image, **kwargs: calls.append(image) or {'ui': {'images': ['preview']}}))
        image = object()
        with patch.dict(sys.modules, {'nodes': fake}):
            result = node.preview(True, image)
        self.assertEqual(calls, [image])
        self.assertIs(result['result'][0], image)
        self.assertEqual(result['ui']['images'], ['preview'])

    def test_all_output_paths_respect_switches_including_reports_and_preview(self):
        workflow = json.loads((ROOT/'example_workflows/Yue2_MM3_Production_Toolkit.json').read_text(encoding='utf-8'))
        nodes = {n['id']: n for n in workflow['nodes']}
        links = {link[0]: link for link in workflow['links']}
        refinement_nodes = {45, 49, 50, 93, 94, 95}
        mastering_nodes = {109, 110, 112, 91, 111}
        for model, cover, refinement, mastering, artifacts in itertools.product(
                ['YuE2', 'YuE2 Cover', 'MiniMax Music 3'], [False, True], ['Model default', 'On', 'Off'], [False, True], [False, True]):
            result = self.control.build(model, cover, refinement, mastering, artifacts)
            seen = set()
            def visit(nid):
                if nid in seen: return
                seen.add(nid)
                node = nodes[nid]
                selected = None
                if node['type'] in ('MusicOptionalStage', 'MusicOptionalCoverPreview', 'SaveImageSmartPrefix'):
                    switch = next(i for i in node['inputs'] if i['name'] == 'enabled')
                    link = links[switch['link']]
                    self.assertEqual(link[1], 118)
                    enabled = result[link[2]]
                    if node['type'] == 'MusicOptionalStage':
                        kwargs = {i['name']: None for i in node['inputs'] if i['link'] and i['name'].startswith('report_')}
                        selected = set(self.gate.check_lazy_status(enabled, node['widgets_values'][0], **kwargs))
                    elif not enabled:
                        selected = set()
                cls = self.package.NODE_CLASS_MAPPINGS.get(node['type'])
                schema = cls.INPUT_TYPES() if cls else {}
                specs = {**schema.get('required', {}), **schema.get('optional', {})}
                for inp in node.get('inputs', []):
                    if inp['link'] is None: continue
                    spec = specs.get(inp['name'], ())
                    lazy = len(spec) > 1 and spec[1].get('lazy', False)
                    if selected is not None and lazy and inp['name'] not in selected: continue
                    visit(links[inp['link']][1])
            # Include every output node, not just the final audio socket.
            for nid, node in nodes.items():
                cls = self.package.NODE_CLASS_MAPPINGS.get(node['type'])
                if (cls and getattr(cls, 'OUTPUT_NODE', False)) or node['type'] in ('PreviewImage', 'PreviewAudio'):
                    visit(nid)
            with self.subTest(model=model, cover=cover, refinement=refinement, mastering=mastering, artifacts=artifacts):
                self.assertIn(123, seen)  # Report still records a truthful bypass when off.
                self.assertEqual(refinement_nodes & seen, refinement_nodes if result[9] else set())
                self.assertEqual(mastering_nodes & seen, mastering_nodes if mastering else set())
                self.assertEqual(76 in seen, cover)  # Image decode has no other output consumer.
                for name, index in [('flux2_models', 8), ('flashsr_models', 9)]:
                    inp = next(i for i in nodes[101]['inputs'] if i['name'] == name)
                    self.assertEqual(links[inp['link']][1:3], [118, index])

    def test_instrumental_brief_overrides_inherited_voice(self):
        cls = self.package.NODE_CLASS_MAPPINGS['MiniMaxStructuredPromptV20']
        args = {name: spec[1].get('default', spec[0][0] if isinstance(spec[0], list) else '')
                for name, spec in cls.INPUT_TYPES()['required'].items()}
        args.update(user_prompt_source='manual', lyrics='instrumental', voice='female vocal',
                    language='English', description_override='Piano and strings',
                    system_prompt_source='bundled_library', system_prompt_file='yue2/production.txt', system_prompt='',
                    model_profile_json=self.control.build()[0])
        result = cls().build(**args)
        self.assertIn('INSTRUMENTAL CONSTRAINT', result[1])
        self.assertIn('full chronological arrangement in Style', result[1])
        self.assertIn('exactly the same order and number of occurrences', result[1])
        self.assertIn('no sung or spoken words', result[0])
        for path in (ROOT/'prompts/system/yue2').glob('*.txt'):
            self.assertIn('Lyrics section MUST contain ONLY', path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
