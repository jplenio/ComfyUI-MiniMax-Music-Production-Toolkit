import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import torch
from _toolkit_bootstrap import load_entry_point

PACKAGE, _ = load_entry_point()
mod = importlib.import_module(f"{PACKAGE.__name__}.audio_artifact_reduction")


def audio(x, sr=48000):
    return {"waveform": torch.from_numpy(np.asarray(x, dtype=np.float32)), "sample_rate": sr}


def fixture(sr=48000, seconds=2, burst_time=1):
    t = np.arange(round(sr*seconds))/sr
    clean = .08*np.sin(2*np.pi*440*t)+.02*np.sin(2*np.pi*880*t)
    burst = np.zeros_like(t)
    start, length = round(sr*burst_time), round(sr*.06)
    burst[start:start+length] = .20*np.hanning(length)*np.sin(2*np.pi*7000*t[start:start+length])
    return clean.astype(np.float32), burst.astype(np.float32)


class ArtifactReductionTests(unittest.TestCase):
    def test_disabled_and_zero_mix_or_reduction_skip_spectral_work(self):
        source = audio(np.ones((1,2,100),dtype=np.float32)*.1)
        for kwargs in ({"enabled":False}, {"enabled":True,"mix":0}, {"enabled":True,"max_reduction_db":0}):
            with patch.object(mod, "_segment", side_effect=AssertionError("No analysis expected")):
                output, removed, report, _ = mod.AudioArtifactReduction().process(source, **kwargs)
            self.assertIs(output, source)
            self.assertFalse(removed["waveform"].any())
            self.assertFalse(json.loads(report)["audio_changed"])

    def test_burst_attenuation_and_difference_output_at_music_rates(self):
        for sr in (32000,44100,48000):
            clean, burst = fixture(sr)
            source = audio((clean+burst)[None,None,:],sr)
            result = mod.AudioArtifactReduction().process(source, enabled=True)
            out, removed, rep = result[0]["waveform"].numpy()[0,0], result[1]["waveform"].numpy()[0,0], json.loads(result[2])
            self.assertLess(np.linalg.norm(out-clean), np.linalg.norm(burst)*.98)
            np.testing.assert_allclose(out+removed, source["waveform"].numpy()[0,0], atol=1e-7)
            self.assertEqual(out.shape, clean.shape)
            self.assertEqual(result[0]["sample_rate"],sr)
            self.assertGreater(rep["batch_reports"][0]["candidate_frames"],0)
            self.assertLessEqual(rep["batch_reports"][0]["max_proposed_reduction_db"],3)
            self.assertFalse(rep["ai_origin_detection"])
            self.assertFalse(rep["hidden_normalization"])

    def test_analyze_only_is_unchanged_but_reports_candidates(self):
        clean, burst = fixture()
        source = audio((clean+burst)[None,None,:])
        result = mod.AudioArtifactReduction().process(source, enabled=True,mode="Analyze only")
        self.assertIs(result[0],source)
        self.assertFalse(result[1]["waveform"].any())
        self.assertGreater(json.loads(result[2])["batch_reports"][0]["candidate_frames"],0)

    def test_steady_tonal_music_is_not_treated_as_short_outlier(self):
        sr=48000; t=np.arange(sr*2)/sr
        clean=sum(.04*np.sin(2*np.pi*f*t) for f in (220,440,880,3500,7000,10000))
        source=audio(clean[None,None,:])
        output=mod.AudioArtifactReduction().process(source,enabled=True)[0]["waveform"].numpy()[0,0]
        np.testing.assert_allclose(output[sr//4:-sr//4],clean[sr//4:-sr//4],atol=1e-6)

    def test_stereo_image_antiphase_and_independent_batches(self):
        clean, burst=fixture(); x=clean+burst
        source=audio(np.stack([np.stack([x,-x]),np.stack([clean,clean])]))
        output,removed,rep,_=mod.AudioArtifactReduction().process(source,enabled=True)
        np.testing.assert_allclose(output["waveform"][0,0],-output["waveform"][0,1],atol=1e-7)
        self.assertGreater(float(removed["waveform"][0].abs().max()),.001)
        self.assertLess(float(removed["waveform"][1].abs().max()),1e-5)
        self.assertEqual(len(json.loads(rep)["batch_reports"]),2)

    def test_chunk_boundary_matches_contextual_whole_signal_processing(self):
        sr=48000; nfft=2048; hop=512; context=64*hop
        clean,burst=fixture(seconds=4,burst_time=256*hop/sr-.03)
        source=audio((clean+burst)[None,None,:])
        actual=mod.AudioArtifactReduction().process(source,enabled=True)[1]["waveform"].numpy()[0]
        padded=np.pad(source["waveform"].numpy()[0],((0,0),(context,context)))
        expected=mod._segment(padded,sr,nfft,hop,3000,18000,mod.SENSITIVITY["Balanced"],3,True)[0]
        np.testing.assert_allclose(actual,expected[:,context:context+len(clean)],atol=1e-7)

    def test_silence_short_inputs_and_unavailable_band(self):
        for length,sr in ((1,48000),(93,44100),(300,8000),(1000,4000)):
            source=audio(np.zeros((1,1,length)),sr)
            result=mod.AudioArtifactReduction().process(source,enabled=True)
            self.assertIs(result[0],source)
            self.assertEqual(result[1]["waveform"].shape,source["waveform"].shape)
            self.assertFalse(result[1]["waveform"].any())

    def test_invalid_controls_audio_and_cancellation(self):
        source=audio(np.zeros((1,1,1000)))
        for options in ({"mix":float("nan")},{"min_frequency_hz":9000,"max_frequency_hz":5000},
                        {"sensitivity":"bad"},{"max_reduction_db":9}):
            with self.assertRaises(ValueError): mod.AudioArtifactReduction().process(source,**options)
        with self.assertRaises(ValueError):
            mod.AudioArtifactReduction().process(audio(np.full((1,1,10),float("nan"))))
        with patch.object(mod,"check_cancelled",side_effect=RuntimeError("cancel")):
            with self.assertRaisesRegex(RuntimeError,"cancel"):
                mod.AudioArtifactReduction().process(source,enabled=True)

    def test_central_switch_appends_without_moving_old_output_slots(self):
        cls=PACKAGE.NODE_CLASS_MAPPINGS["MusicProductionControl"]
        for model in ("YuE2","YuE2 Cover","MiniMax Music 3"):
            for enabled in (False,True):
                result=cls().build(model=model,artifact_reduction_enabled=enabled)
                self.assertEqual(result[11],enabled)
                self.assertEqual(result[10],True)
                self.assertEqual(json.loads(result[0])["production_stages"]["artifact_reduction"],enabled)

    def test_report_is_preserved_in_canonical_production_metadata(self):
        module=importlib.import_module(f"{PACKAGE.__name__}.production_metadata")
        report={"schema":"music_artifact_reduction_v1","enabled":False,"status":"bypassed"}
        payload=module.build_generation_metadata({},artifact_reduction_json=json.dumps(report))
        self.assertEqual(payload["artifact_reduction"],report)

    def test_workflow_routes_cleaned_audio_to_analysis_application_and_master_bypass(self):
        root=Path(__file__).resolve().parents[1]
        workflow=json.loads((root/'example_workflows/Music_Production_Toolkit.json').read_text(encoding='utf-8'))
        nodes={n['id']:n for n in workflow['nodes']}; links={l[0]:l for l in workflow['links']}
        def origin(nid,name):
            inp=next(i for i in nodes[nid]['inputs'] if i['name']==name)
            return links[inp['link']][1:3]
        for nid,name in ((109,'audio'),(110,'audio'),(120,'original_audio')):
            self.assertEqual(origin(nid,name),[123,0])
        self.assertEqual(origin(123,'audio'),[119,0])
        self.assertEqual(origin(123,'enabled'),[118,11])
        self.assertEqual(origin(99,'artifact_reduction_json'),[123,2])
        self.assertTrue(nodes[118]['widgets_values_named']['artifact_reduction_enabled'])
        self.assertEqual(nodes[123]['widgets_values_named']['sensitivity'],'Balanced')
        catalog=json.loads((root/'web/eq_presets.json').read_text(encoding='utf-8'))
        preset=next(p for p in catalog['auto'] if p['name']=='Warm - gentle (workflow default)')
        for key,value in preset['values'].items():
            self.assertEqual(nodes[109]['widgets_values_named'][key],value)

    def test_onset_protection_backs_off_during_broadband_attacks(self):
        sr=48000; clean,burst=fixture()
        rng=np.random.default_rng(12)
        source=clean+burst
        start=sr; length=sr//100
        source[start:start+length]+=.8*rng.normal(size=length).astype(np.float32)*np.hanning(length)
        a=audio(source[None,None,:])
        protected=mod.AudioArtifactReduction().process(a,enabled=True,protect_transients=True)[1]['waveform']
        unprotected=mod.AudioArtifactReduction().process(a,enabled=True,protect_transients=False)[1]['waveform']
        self.assertLess(float(torch.linalg.vector_norm(protected)),float(torch.linalg.vector_norm(unprotected)))


if __name__ == "__main__": unittest.main()
