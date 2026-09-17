"""Reported English/en failure and input-error retry regression (no weights)."""
import importlib
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from _toolkit_bootstrap import load_entry_point


class WhisperLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package, _ = load_entry_point()
        cls.mod = importlib.import_module(package.__name__ + '.whisper_lyrics')

    def test_names_codes_case_and_auto(self):
        for raw, expected in [('English','en'),(' EN ','en'),('German','de'),
                              ('Deutsch','de'),('French','fr'),('Japanese','ja'),
                              ('Chinese','zh'),('Cantonese','yue'),('haw','haw'),
                              ('AUTO',None),('',None),(None,None)]:
            with self.subTest(raw=raw):
                self.assertEqual(self.mod.normalize_whisper_language(raw), expected)
        for code,name in self.mod._LANGUAGE_NAMES.items():
            self.assertEqual(self.mod.normalize_whisper_language(name), code)

    def test_unknown_language_fails_before_models_or_audio(self):
        with patch.object(self.mod, '_load_engine') as engine, \
             patch.object(self.mod, 'whisper_model_dir') as model_dir, \
             patch.object(self.mod, 'load_audio_mono') as audio:
            with self.assertRaisesRegex(ValueError, 'unsupported Whisper source language'):
                self.mod.transcribe('song.wav', language='Klingon')
            engine.assert_not_called()
            model_dir.assert_not_called()
            audio.assert_not_called()

    def run_transcription(self, implementation):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(self.mod, 'whisper_model_dir', return_value=Path(directory)), \
             patch.object(self.mod, '_load_engine'), \
             patch.object(self.mod, '_get_model', return_value=types.SimpleNamespace(transcribe=implementation)) as model, \
             patch.object(self.mod, '_resolve_device', return_value=('cuda','float16')), \
             patch.object(self.mod, 'load_audio_mono', return_value=[0]*16000):
            try:
                return self.mod.transcribe('song.wav', language='English'), model.call_count
            finally:
                self.assertEqual(model.call_count, 1, 'Input errors must not reload the model on CPU')

    def test_english_reaches_engine_as_en_and_records_requested_value(self):
        def transcribe(samples, **kwargs):
            self.assertEqual(kwargs['language'], 'en')
            self.assertTrue(kwargs['word_timestamps'])
            self.assertFalse(kwargs['vad_filter'])
            return iter([types.SimpleNamespace(start=0,end=1,text='the words',words=[])]), \
                types.SimpleNamespace(language='en',duration=1,duration_after_vad=.035)
        record,_ = self.run_transcription(transcribe)
        self.assertEqual(record['language_forced'], 'en')
        self.assertEqual(record['language_requested'], 'English')
        self.assertEqual(record['device'], 'cuda')
        self.assertFalse(record['vad_filter_requested'])
        self.assertNotIn('warning', record)

    def test_invalid_input_during_lazy_iteration_does_not_retry_on_cpu(self):
        def transcribe(samples, **kwargs):
            def segments():
                raise ValueError('invalid transcription input')
                yield
            return segments(), types.SimpleNamespace(language='en')
        with self.assertRaisesRegex(ValueError, 'invalid transcription input'):
            self.run_transcription(transcribe)
        self.assertEqual(self.mod._MODEL_CACHE, {})


if __name__ == '__main__': unittest.main()
