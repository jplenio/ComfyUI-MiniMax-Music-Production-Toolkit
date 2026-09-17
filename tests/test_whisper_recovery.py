"""Regression of the 207 s song / 7.3 s VAD result, and native worker isolation."""
import importlib
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

from _toolkit_bootstrap import load_entry_point


class WhisperRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package, _ = load_entry_point()
        cls.mod = importlib.import_module(package.__name__ + '.whisper_lyrics')
        cls.worker = importlib.import_module(package.__name__ + '.whisper_worker')

    def run_transcription(self, implementation, **options):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(self.mod, 'whisper_model_dir', return_value=Path(directory)), \
             patch.object(self.mod, '_load_engine'), \
             patch.object(self.mod, '_get_model', return_value=types.SimpleNamespace(transcribe=implementation)), \
             patch.object(self.mod, '_resolve_device', return_value=('cpu', 'int8')), \
             patch.object(self.mod, 'load_audio_mono', return_value=[0]*3314128):
            return self.mod.transcribe('song.wav', **options)

    def test_destructive_vad_retries_full_song_and_replaces_partial_transcript(self):
        calls = []
        def run(samples, **kwargs):
            calls.append(kwargs['vad_filter'])
            vad = kwargs['vad_filter']
            return iter([types.SimpleNamespace(start=1, end=9 if vad else 202,
                        text='opening fragment' if vad else 'complete source words', words=[])]), \
                   types.SimpleNamespace(language='en', duration=207.133,
                                         duration_after_vad=7.296 if vad else 207.133)
        result = self.run_transcription(run, vad_filter=True)
        self.assertEqual(calls, [True, False])
        self.assertEqual(result['text'], 'complete source words')
        self.assertFalse(result['vad_filter'])
        self.assertTrue(result['vad_filter_requested'])
        self.assertEqual(result['vad_retained_fraction'], .0352)
        self.assertEqual(len(result['attempts']), 2)
        self.assertIn('Retried', result['warning'])

    def test_fragment_without_vad_stops_before_wordless_cover(self):
        def run(samples, **kwargs):
            return iter([types.SimpleNamespace(start=1, end=9, text='only a short fragment', words=[])]), \
                   types.SimpleNamespace(language='en', duration=207.133)
        with self.assertRaisesRegex(ValueError, 'short opening fragment'):
            self.run_transcription(run)

    def test_cached_cuda_failure_only_changes_auto_not_explicit_cuda(self):
        with patch.object(self.mod, '_CUDA_FAILURE', 'cublas64_12.dll unavailable'):
            self.assertEqual(self.mod._resolve_device('auto', 'auto'), ('cpu', 'int8'))
            self.assertEqual(self.mod._resolve_device('cuda', 'auto'), ('cuda', 'float16'))

    def test_interrupt_is_never_retried_on_cpu(self):
        class HostInterrupt(Exception): pass
        def run(samples, **kwargs):
            try:
                raise HostInterrupt('cancelled')
            except HostInterrupt as exc:
                raise self.worker.WhisperCancelled() from exc
        with self.assertRaises(HostInterrupt):
            self.run_transcription(run)

    def test_actual_child_protocol_and_lazy_error(self):
        fake = '''
from types import SimpleNamespace as S
class WhisperModel:
    def __init__(self, path, device, compute_type, local_files_only):
        assert local_files_only
    def transcribe(self, samples, **options):
        def iterator():
            yield S(start=0, end=1, text='known words', words=[S(word='known',start=0,end=.5)])
            if options.get('language') == 'invalid':
                raise ValueError('bad source language')
        return iterator(), S(language='en', language_probability=.9, duration=1, duration_after_vad=1)
'''
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'faster_whisper.py').write_text(fake, encoding='utf-8')
            with patch.dict(os.environ, {'PYTHONPATH': directory}):
                model = self.worker.IsolatedWhisperModel(directory, 'cpu', 'int8')
                segments, info = model.transcribe(np.zeros(16000), language='en')
                segment = list(segments)[0]
                self.assertEqual(segment.text, 'known words')
                self.assertEqual(segment.words[0].end, .5)
                self.assertEqual(info.duration, 1)
                with self.assertRaisesRegex(ValueError, 'bad source language'):
                    model.transcribe(np.zeros(16000), language='invalid')

    def test_timeout_kills_child_and_discards_partial_result(self):
        import numpy as np
        processes = []
        real_popen = subprocess.Popen
        def launch(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            processes.append(proc)
            return proc
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'faster_whisper.py').write_text('import time\ntime.sleep(30)\n', encoding='utf-8')
            with patch.dict(os.environ, {'PYTHONPATH': directory}), \
                 patch.object(self.worker, 'CPU_IDLE_SECONDS', .1), \
                 patch.object(self.worker.subprocess, 'Popen', side_effect=launch):
                with self.assertRaisesRegex(TimeoutError, 'no partial lyrics'):
                    self.worker.IsolatedWhisperModel(directory, 'cpu', 'int8').transcribe(np.zeros(16000))
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())


if __name__ == '__main__': unittest.main()
