import librosa
import numpy as np
import pyworld as pw
import pysptk.sptk as pysptk
import torch

from HParams import HParams
class UtilWorldVocoder:
    def __init__(self,h_params:HParams):
        self.h_params = h_params
        self.sample_rate = self.h_params.preprocess.sample_rate
        self.n_fft = self.h_params.preprocess.nfft
        self.hop_length = self.h_params.preprocess.hopsize
        self.window_size = self.n_fft
        self.world_frame_period = (self.hop_length / self.sample_rate) * 1000

    def mag_phase_stft(self,audio):
        stft = librosa.stft(audio,n_fft=self.h_params.preprocess.nfft, hop_length=self.h_params.preprocess.hopsize)
        mag = abs(stft)
        phase = np.exp(1.j * np.angle(stft))
        return {"mag":mag,"phase":phase}
    
    
    def dynamic_range_compression(self, x, C=1, clip_val=1e-5):
        return np.log(np.clip(x, a_min=clip_val, a_max=None) * C)
    
    def dynamic_range_compression_torch(self, x, C=1, clip_val=1e-5):
        return torch.log(torch.clamp(x, min=clip_val) * C)
    
    def normalize(self,x, min_db = -80.0, max_db = 20.0, clip_val = 0.8):
        x = 2.0*(x - min_db)/(max_db - min_db) - 1.0
        x = torch.clamp(clip_val*x, -clip_val, clip_val)
        return x

    def denormalize(self, x, min_db = -80.0, max_db = 20.0, clip_val = 0.8):
        x = x/clip_val
        x = (max_db - min_db)*(x + 1.0)/2.0 + min_db
        return x
        
    def get_pred_accom_by_subtract_pred_vocal(self,pred_vocal,is_pred_vocal_audio,mix_audio):
        pred_vocal_mag = pred_vocal
        if is_pred_vocal_audio:
            pred_vocal_mag = self.mag_phase_stft(pred_vocal)["mag"]
        mix_stft = self.mag_phase_stft(mix_audio)
        mix_mag = mix_stft["mag"]
        mix_phase = mix_stft["phase"]
        pred_accom_mag = mix_mag - pred_vocal_mag
        pred_accom_mag[pred_accom_mag < 0] = 0
        pred_accom = librosa.istft(pred_accom_mag*mix_phase,hop_length=self.h_params.preprocess.hopsize,length=len(mix_audio))
        return pred_accom
    
    def get_compressed_world_parameters_from_audio(self,audio_mono):
        print("start: compressed_world_parameters_from_audio")
        world_parameters = pw.wav2world(audio_mono.astype("double"), self.sample_rate, frame_period=self.world_frame_period)
        
        f0 = world_parameters[0]
        f0_midi = self.pitch_to_midi(f0)
        interpolated_f0_midi,not_pitch = self.interpolate_f0_midi_nan_value(f0_midi)

        spectral_envelope = world_parameters[1]
        spectral_envelope = 10*np.log10(spectral_envelope)

        aperiodic = world_parameters[2]
        aperiodic = 10.*np.log10(aperiodic**2)

        if self.h_params.preprocess.compress_method_world_parameter == 'mfsc':
            print("start: spectral sp_to_mfsc")
            compressed_spectral = self.sp_to_mfsc(spectral_envelope, self.h_params.preprocess.num_spectral_coefficients,0.45)
            print("start: aperiodic sp_to_mfsc")
            compressed_aperiodic = self.sp_to_mfsc(aperiodic, self.h_params.preprocess.num_aperiodic_coefficients,0.45)
        elif self.h_params.preprocess.compress_method_world_parameter == 'mgc':
            print("start: spectral sp_to_mgc")
            compressed_spectral = self.sp_to_mgc(spectral_envelope, self.h_params.preprocess.num_spectral_coefficients,0.45)
            print("start: aperiodic sp_to_mgc")
            compressed_aperiodic = self.sp_to_mgc(aperiodic, self.h_params.preprocess.num_aperiodic_coefficients,0.45)

        return { "f0": np.transpose(interpolated_f0_midi),"not_pitch":np.transpose(not_pitch.astype(int)), "spectral": np.transpose(compressed_spectral), "aperiodic": np.transpose(compressed_aperiodic) }

    def pitch_to_midi(self,frequency):
        midi = 69 + 12 * np.log2(frequency/440)
        return midi
    
    def midi_to_pitch(self,midi):
        frequency = 440 * pow(2, (midi - 69) / 12)
        return frequency
    
    def interpolate_f0_midi_nan_value(self,f0_midi):
        infinite_conditional_index = np.isinf(f0_midi)
        not_infinite_conditional_index = ~infinite_conditional_index
        infinite_int_index = infinite_conditional_index.nonzero()[0]
        not_infinite_int_index = (not_infinite_conditional_index).nonzero()[0]
        
        interpolated_f0_midi = f0_midi.copy()
        interpolated_f0_midi[infinite_conditional_index] = np.interp(infinite_int_index,not_infinite_int_index,f0_midi[not_infinite_conditional_index])
        
        interpolated_f0_midi = interpolated_f0_midi
        not_pitch = infinite_conditional_index
        
        return (interpolated_f0_midi,not_pitch)
    
    def sp_to_mfsc(self,sp, ndim, fw, noise_floor_db=-120.0):
        # helper function, sp->mgc->mfsc in a single step
        mgc = self.sp_to_mgc(sp, ndim, fw, noise_floor_db)
        mfsc = self.mgc_to_mfsc(mgc)
        return mfsc
    
    def sp_to_mgc(self,sp, ndim, fw, noise_floor_db=-120.0):
        # HTS uses -80, but we shift WORLD/STRAIGHT by -20 dB (so would be -100); use a little more headroom (SPTK uses doubles internally, so eps 1e-12 should still be OK)
        dtype = sp.dtype
        sp = sp.astype(np.float64)  # required for pysptk
        mgc = np.apply_along_axis(pysptk.mcep, 1, np.atleast_2d(sp), order=ndim-1, alpha=fw, maxiter=0, etype=1, eps=10**(noise_floor_db/10), min_det=0.0, itype=1)
        if sp.ndim == 1:
            mgc = mgc.flatten()
        mgc = mgc.astype(dtype)
        return mgc

    def mgc_to_mfsc(self,mgc):
        is_1d = mgc.ndim == 1
        mgc = np.atleast_2d(mgc)
        ndim = mgc.shape[1]

        # mirror cepstrum
        mgc1 = np.concatenate([mgc[:, :], mgc[:, -2:0:-1]], axis=-1)

        # re-scale 'dc' and 'nyquist' cepstral bins (see mcep())
        mgc1[:, 0] *= 2
        mgc1[:, ndim-1] *= 2
        
        # fft, truncate, to decibels
        mfsc = np.real(np.fft.fft(mgc1))
        mfsc = mfsc[:, :ndim]
        mfsc = 10*mfsc/np.log(10)

        if is_1d:
            mfsc = mfsc.flatten()

        return mfsc
    
    def mfsc_to_mgc(self,mfsc):
        # mfsc -> mgc -> sp is a much slower alternative to mfsc_to_sp()
        is_1d = mfsc.ndim == 1
        mfsc = np.atleast_2d(mfsc)
        ndim = mfsc.shape[1]

        mfsc = mfsc/10*np.log(10)
        mfsc1 = np.concatenate([mfsc[:, :], mfsc[:, -2:0:-1]], axis=-1)
        mgc = np.real(np.fft.ifft(mfsc1))
        mgc[:, 0] /= 2
        mgc[:, ndim-1] /= 2
        mgc = mgc[:, :ndim]

        if is_1d:
            mgc = mgc.flatten()
        
        return mgc
    
    def mgc_to_sp(self,mgc, spec_size, fw):
        dtype = mgc.dtype
        mgc = mgc.astype(np.float64)  # required for pysptk
        fftlen = 2*(spec_size - 1)
        sp = np.apply_along_axis(pysptk.mgc2sp, 1, np.atleast_2d(mgc), alpha=fw, gamma=0.0, fftlen=fftlen)
        sp = 20*np.real(sp)/np.log(10)
        if mgc.ndim == 1:
            sp = sp.flatten()
        sp = sp.astype(dtype)
        return sp
    
    def get_audio_from_compressed_world_parameters(self, f0, not_pitch, spectral_compressed, aperiodic_compressed):
        print("start: audio_from_compressed_world_parameters")
        
        is_pitch = (1-np.transpose(not_pitch))
        interpolated_f0 = self.midi_to_pitch(np.transpose(f0))
        f0_hz = (interpolated_f0 * is_pitch).astype('double')

        spectral = np.transpose(spectral_compressed)
        aperiodic = np.transpose(aperiodic_compressed)

        if self.h_params.preprocess.compress_method_world_parameter == 'mfsc':
            print("start: spectral mfsc_to_mgc")
            spectral = self.mfsc_to_mgc(spectral)
            print("start: aperiodic mfsc_to_mgc")
            aperiodic = self.mfsc_to_mgc(aperiodic)
            
        print("start: spectral mgc_to_sp")
        spectral = self.mgc_to_sp(spectral, self.h_params.preprocess.world_parameter_dimension, 0.45)
        print("start: aperiodic mgc_to_sp")
        aperiodic = self.mgc_to_sp(aperiodic, self.h_params.preprocess.world_parameter_dimension, 0.45)
        
        spectral = (10**(spectral/10)).astype('double')
        aperiodic = (10**(aperiodic/20)).astype('double')

        print("start: synthesize audio")
        audio = pw.synthesize(f0_hz,spectral,aperiodic,self.sample_rate,self.world_frame_period)
        
        return audio

    
    def torch_A_weighting(self, frequencies, min_db = -45.0):
        """
        Compute A-weighting weights in Decibel scale (codes from librosa) and 
        transform into amplitude domain (with DB-SPL equation).
        
        Argument: 
            frequencies : tensor of frequencies to return amplitude weight
            min_db : mininum decibel weight. appropriate min_db value is important, as 
                exp/log calculation might raise numeric error with float32 type. 
        
        Returns:
            weights : tensor of amplitude attenuation weights corresponding to the frequencies tensor.
        """
        
        # Calculate A-weighting in Decibel scale.
        frequencies_squared = frequencies ** 2 
        const = torch.tensor([12200, 20.6, 107.7, 737.9]) ** 2.0
        weights_in_db = 2.0 + 20.0 * (torch.log10(const[0]) + 4 * torch.log10(frequencies)
                               - torch.log10(frequencies_squared + const[0])
                               - torch.log10(frequencies_squared + const[1])
                               - 0.5 * torch.log10(frequencies_squared + const[2])
                               - 0.5 * torch.log10(frequencies_squared + const[3]))
        
        # Set minimum Decibel weight.
        if min_db is not None:
            weights_in_db = torch.max(weights_in_db, torch.tensor([min_db], dtype = torch.float32))
        
        # Transform Decibel scale weight to amplitude scale weight.
        weights = torch.exp(torch.log(torch.tensor([10.], dtype = torch.float32)) * weights_in_db / 10) 
        
        return weights
    
    
        
if __name__ == '__main__':
    pa = HParams()
    wo = UtilWorldVocoder(pa)
    

