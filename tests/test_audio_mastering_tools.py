"""Signal, state, boundary and actual FFmpeg checks for sections 8–10."""
from __future__ import annotations

import importlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

import numpy as np
from scipy.signal import sosfilt, sosfreqz
import torch
from _toolkit_bootstrap import load_entry_point

PACKAGE, _ = load_entry_point()
def module(name):
    return importlib.import_module(f"{PACKAGE.__name__}.{name}")
eq = module("eq_config")
audio_eq = module("audio_eq")
analysis = module("audio_analysis")
auto = module("audio_auto_eq")
compressor = module("audio_compressor")
limiter = module("audio_limiter")
master = module("audio_mastering")


def config(kind="peak", gain=6, freq=1000, q=1):
    return eq.parse_settings({"schema": eq.SCHEMA, "preamp_db": 0,
                              "bands": [{"type": kind, "frequency_hz": freq, "gain_db": gain, "q": q}]}, 48000)


def audio(x, sr=48000):
    return {"waveform": torch.from_numpy(np.asarray(x, dtype=np.float32)), "sample_rate": sr}


class EQTests(unittest.TestCase):
    def test_workflow_rate_is_kept_with_full_mastering_bypass(self):
        prep = module("audio_release_prep").AudioReleasePrep()
        signal = audio(np.zeros((1,2,4800),dtype=np.float32))
        for rate in (44100,48000):
            converted = prep.process(signal,str(rate),"Resample only",-14,-1)[0]
            output = master.MiniMaxMasteringCompressor().process(converted,bypass=True)["result"][0]
            self.assertEqual(output["sample_rate"],rate)
            self.assertEqual(output["waveform"].shape[-1],rate//10)
            self.assertIs(output,converted)

    def test_auto_eq_off_skips_analysis_and_manual_bypass_is_independent(self):
        signal = audio(np.ones((1,2,1000),dtype=np.float32)*0.05)
        with patch.object(auto,"spectral_profile",side_effect=AssertionError("Must not analyze")):
            settings = auto.MiniMaxAutoEQAnalyze().analyze(signal,enabled=False)["result"][0]
        automatic = audio_eq.MiniMaxParametricEQ().process(signal,settings)["result"][0]
        self.assertIs(automatic,signal)
        manual_settings = json.dumps({"schema":"minimax_eq_v1","preamp_db":-6,"bands":[]})
        for enabled in (False,True):
            output = audio_eq.MiniMaxParametricEQ().process(automatic,manual_settings,bypass=not enabled)["result"][0]
            expected = signal["waveform"] * (10**(-6/20) if enabled else 1)
            torch.testing.assert_close(output["waveform"],expected)

    def test_peak_center_gain_and_inverse(self):
        for sr in (8000, 44100, 48000, 96000):
            for gain in (-12, -6, 0, 6, 12):
                c = config(gain=gain)
                self.assertAlmostEqual(eq.response_db(c, sr, np.array([1000]))[0], gain, places=8)
                grid = np.geomspace(20, sr*0.45, 300)
                np.testing.assert_allclose(eq.response_db(c, sr, grid)+eq.response_db(config(gain=-gain), sr, grid), 0, atol=1e-8)

    def test_shelf_endpoints_and_filter_corners(self):
        for kind in ("low_shelf", "high_shelf"):
            values = eq.response_db(config(kind), 48000, np.array([0., 24000.]))
            np.testing.assert_allclose(values, [6, 0] if kind=="low_shelf" else [0, 6], atol=1e-8)
        for kind in ("lowpass", "highpass"):
            self.assertAlmostEqual(eq.response_db(config(kind,q=1/math.sqrt(2)),48000,np.array([1000]))[0], -3.01029995664,places=7)
        self.assertLess(eq.response_db(config("notch"),48000,np.array([1000]))[0], -200)

    def test_extreme_allowed_poles(self):
        for kind in eq.FILTER_TYPES:
            for f in (20, 20000):
                for q in (0.2, 10):
                    for g in (-12, 12):
                        row = eq.band_sos(config(kind,g,f,q)["bands"][0],48000)
                        self.assertLess(np.abs(np.roots(row[3:])).max(),1)

    def test_block_parity_and_input_ownership(self):
        x=np.random.default_rng(21).normal(0,0.1,(2,70000)).astype('float32');before=x.copy()
        c=config("high_shelf",-5,9000)
        y=audio_eq.apply_eq(x,48000,c,block_frames=127)
        expected=sosfilt(eq.design_sos(c,48000),x,axis=-1).astype('float32')
        np.testing.assert_array_equal(x,before)
        np.testing.assert_array_equal(y,expected)

    def test_sine_gain_measured_in_signal(self):
        t=np.arange(48000)/48000;x=np.sin(2*np.pi*1000*t)[None,:].astype('float32')*.1
        y=audio_eq.apply_eq(x,48000,config())
        self.assertAlmostEqual(20*np.log10(np.std(y[:,4800:])/np.std(x[:,4800:])),6,places=4)

    def test_bypass_and_unity_identity(self):
        x=audio(np.ones((2,2,100),dtype='float32')*.1)
        for bypass in (False,True):
            out=audio_eq.MiniMaxParametricEQ().process(x,bypass=bypass)['result'][0]
            self.assertIs(out,x)

    def test_batch_proposals_and_mismatch(self):
        x=audio(np.ones((2,1,1024),dtype='float32')*.1)
        items=[eq.parse_settings(json.loads(eq.DEFAULT_SETTINGS)) for _ in range(2)]
        items[1]['preamp_db']=-6
        settings=json.dumps({'schema':eq.BATCH_SCHEMA,'items':items})
        y=audio_eq.MiniMaxParametricEQ().process(x,settings)['result'][0]['waveform'].numpy()
        np.testing.assert_allclose(y[0],.1,rtol=1e-6);np.testing.assert_allclose(y[1],.1*10**(-6/20),rtol=1e-6)
        with self.assertRaises(ValueError):eq.settings_for_batch(settings,1,48000)

    def test_invalid_json_and_parameters(self):
        for value in ('[]','{"schema":"other"}','{"schema":"minimax_eq_v1","preamp_db":NaN}',
                      '{"schema":"minimax_eq_v1","bands":[{"enabled":"false"}]}'):
            with self.subTest(value=value),self.assertRaises(ValueError):eq.parse_settings(value)
        with self.assertRaises(ValueError):eq.parse_settings(config(freq=20000),8000)
        with self.assertRaises(ValueError):eq.parse_settings({'schema':eq.SCHEMA,'bands':[{}]*9})

    def test_invalid_audio_and_cancellation(self):
        for x in (np.empty((1,1,0)),np.array([[[np.nan]]]),np.array([[[np.inf]]])):
            with self.assertRaises(ValueError):audio_eq.MiniMaxParametricEQ().process(audio(x))
        with patch.object(audio_eq,'check_cancelled',side_effect=RuntimeError('cancel')):
            with self.assertRaisesRegex(RuntimeError,'cancel'):audio_eq.apply_eq(np.ones((1,1000)),48000,config())


class AutoEQTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.x=np.random.default_rng(15).normal(0,.1,(2,96000)).astype('float32')
        cls.profile=analysis.spectral_profile(cls.x,48000)

    def test_antiphase_has_same_spectrum(self):
        x=np.stack([self.x[0],-self.x[0]])
        a=analysis.spectral_profile(x,48000);b=analysis.spectral_profile(x[:1],48000)
        np.testing.assert_allclose(a['power_db'],b['power_db'],atol=1e-10)

    def test_gain_change_does_not_equalize(self):
        other=analysis.spectral_profile(self.x*2,48000)
        c,r=auto.fit_eq(self.profile,other,48000)
        self.assertEqual(c['bands'],[]);self.assertTrue(r['accepted'])

    def test_known_wide_color_is_improved(self):
        grid=np.asarray(self.profile['frequency_hz'])
        desired=eq.response_db(config(gain=4,freq=1700,q=.6),48000,grid)
        target=dict(self.profile,power_db=(np.asarray(self.profile['power_db'])+desired).tolist())
        c,r=auto.fit_eq(self.profile,target,48000,strength=1,max_bands=3,max_gain=6)
        self.assertTrue(r['accepted']);self.assertLess(r['after_error_db'],r['before_error_db']*.5)
        self.assertLessEqual(np.abs(eq.response_db(c,48000,np.geomspace(20,20000,4096))).max(),6.01)

    def test_silence_and_short_reference_return_unity(self):
        for x in (np.zeros((1,96000)), np.ones((1,64))*.1):
            profile=analysis.spectral_profile(x,48000)
            c,r=auto.fit_eq(profile,profile,48000)
            self.assertFalse(r['accepted']);self.assertEqual(c['bands'],[])

    def test_reference_required_and_no_source_mutation(self):
        source=audio(self.x[None,:,:]);before=source['waveform'].clone()
        with self.assertRaises(ValueError):auto.MiniMaxAutoEQAnalyze().analyze(source)
        result=auto.MiniMaxAutoEQAnalyze().analyze(source,reference_audio=source)['result']
        self.assertEqual(json.loads(result[0])['bands'],[])
        self.assertTrue(torch.equal(before,source['waveform']))

    def test_mismatched_reference_batch(self):
        with self.assertRaises(ValueError):auto.MiniMaxAutoEQAnalyze().analyze(audio(self.x[None]),reference_audio=audio(np.zeros((3,1,1024))))


class CompressorTests(unittest.TestCase):
    def test_knee_continuity_and_ratio(self):
        f=compressor.soft_knee_reduction_db
        self.assertEqual(f(-40,-18,2,6),0)
        self.assertEqual(f(-6,-18,2,6),-6)
        self.assertAlmostEqual(f(-15-1e-7,-18,2,6),f(-15+1e-7,-18,2,6),places=6)
        self.assertEqual(f(-6,-18,1,6),0)

    def test_steady_state_reduction(self):
        x=np.ones((2,96000),dtype='float32')*10**(-12/20)
        y,r=compressor.compress(x,48000,threshold_db=-18,ratio=2,knee_db=0,sidechain_hz=0,attack_ms=10)
        self.assertAlmostEqual(20*np.log10(y[0,-1]/x[0,-1]),-3,places=3)
        self.assertAlmostEqual(r['max_reduction_db'],3,places=3)

    def test_stereo_link_and_no_mutation(self):
        x=np.stack([np.full(10000,.8),np.full(10000,-.4)]).astype('float32');before=x.copy()
        y,_=compressor.compress(x,48000,sidechain_hz=0)
        np.testing.assert_array_equal(x,before);np.testing.assert_allclose(y[0],-2*y[1],atol=1e-7)

    def test_disabled_and_unity(self):
        x=np.random.default_rng(8).normal(0,.1,(2,1000)).astype('float32')
        for options in ({'enabled':False},{'ratio':1}):
            y,_=compressor.compress(x,48000,**options);np.testing.assert_array_equal(x,y)


class LimiterTests(unittest.TestCase):
    def test_tile_parity_and_boundaries(self):
        x=np.random.default_rng(1).normal(0,.5,(2,70000)).astype('float32')
        x[:,[0,1023,1024,32767,32768,-1]]=3
        a,_=limiter.limit_peaks(x,48000,block_frames=1024)
        b,r=limiter.limit_peaks(x,48000,block_frames=32768)
        np.testing.assert_allclose(a,b,atol=2e-6)
        self.assertEqual(a.shape,x.shape);self.assertLess(np.abs(b).max(),10**(-1/20))
        self.assertGreater(r['max_reduction_db'],0)

    def test_short_silence_and_stereo_link(self):
        for n in (1,17,255,1000):
            x=np.zeros((2,n),dtype='float32');out,_=limiter.limit_peaks(x,44100)
            np.testing.assert_array_equal(out,x)
        t=np.arange(48000)/48000;x=np.stack([2*np.sin(2*np.pi*700*t),-np.sin(2*np.pi*700*t)]).astype('float32')
        y,_=limiter.limit_peaks(x,48000);np.testing.assert_allclose(y[0],-2*y[1],atol=1e-6)


class MeterAndMasterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not module('ffmpeg_utils').discover_ffmpeg():
            raise unittest.SkipTest('FFmpeg is required for real meter acceptance tests')

    def test_integrated_target_and_tp(self):
        t=np.arange(96000)/48000;x=np.stack([.2*np.sin(2*np.pi*1000*t)]*2).astype('float32')
        y,r=master.master_track(x,48000)
        self.assertTrue(r['target_reached']);self.assertLessEqual(abs(r['output']['integrated_lufs']+14),.3)
        independent=analysis.measure_loudness(y,48000)
        self.assertLessEqual(independent['true_peak_dbtp'],-1)

    def test_inter_sample_peaks_after_limit(self):
        # Quarter-rate sine with phase offset has intersample peaks above samples.
        t=np.arange(48000)/48000;x=(1.4*np.sin(2*np.pi*12000*t+np.pi/4))[None,:].astype('float32')
        # Exercise the complete protection path, including independent metering.
        # A different resampler can reveal boundary peaks missed by 4x DSP.
        y,report=master.master_track(x,48000,target_lufs=-5,ceiling_dbtp=-6,
                                     enabled=False,max_limiter_reduction_db=18)
        measured=analysis.measure_loudness(y,48000)
        self.assertLessEqual(measured['true_peak_dbtp'],-6)
        self.assertTrue(any(attempt['safety_gain_db'] < 0 for attempt in report['attempts']))

    def test_silence_json_is_standard_and_bypass_identity(self):
        source=audio(np.zeros((2,1,1000)))
        out=master.MiniMaxMasteringCompressor().process(source,bypass=True)['result'][0]
        self.assertIs(out,source)
        y,r=master.master_track(np.zeros((1,1000),dtype='float32'),48000)
        self.assertFalse(r['target_reached']);self.assertEqual(r['reason'],'silence_or_unmeasurable_loudness')
        json.dumps(r,allow_nan=False);np.testing.assert_array_equal(y,0)

    def test_makeup_budget_reports_unreached(self):
        t=np.arange(48000)/48000;x=(.005*np.sin(2*np.pi*1000*t))[None,:].astype('float32')
        y,r=master.master_track(x,48000,max_makeup_db=0,enabled=False)
        self.assertFalse(r['target_reached']);self.assertEqual(r['reason'],'makeup_budget')

    def test_src_batch_and_input_ownership(self):
        t=np.arange(24000)/24000;x=np.stack([.1*np.sin(2*np.pi*1000*t)]*2)[:,None,:].astype('float32')
        source=audio(x,24000);before=source['waveform'].clone()
        out,rep,_=master.MiniMaxMasteringCompressor().process(source,target_sample_rate='44100')['result']
        self.assertEqual(tuple(out['waveform'].shape),(2,1,44100));self.assertEqual(out['sample_rate'],44100)
        self.assertTrue(torch.equal(before,source['waveform']));self.assertEqual(len(json.loads(rep)['batch_reports']),2)

    def test_surround_rejected(self):
        with self.assertRaises(ValueError):master.MiniMaxMasteringCompressor().process(audio(np.zeros((1,6,100))))


if __name__ == '__main__':
    unittest.main()
