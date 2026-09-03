from numpy import ndarray
from torch import Tensor

import numpy as np
import librosa
import torch
import torchaudio
from TorchJaekwon.Evaluater.Package.pysepm.qualityMeasures import fwSNRseg

from TorchJaekwon.Util.UtilData import UtilData
from TorchJaekwon.Util.UtilAudio import UtilAudio

class MetricSound:
    @staticmethod
    def fwssnr(target_wave:Tensor, #[batch, channel, signal_length]
               pred_wave:Tensor, #[batch, channel, signal_length]
               batch_size:int = 1,
               sample_rate:int = 16000):
        '''
        the frequency-weighted segmental SNR (fwSSNR)
        Y. Hu and Philipos C. Loizou, “Evaluation of objective quality measures for speech enhancement,” IEEE TASLP, 2008.
        '''
        target_wave = UtilData.fit_shape_length(target_wave, 3)
        pred_wave = UtilData.fit_shape_length(pred_wave, 3)
        target_wave, pred_wave = MetricSound.trim_samples(target_wave, pred_wave)
        target_wave = UtilAudio.normalize_by_fro_norm(target_wave)
        pred_wave = UtilAudio.normalize_by_fro_norm(pred_wave)
        
        fwSNRseg_vectorized = np.vectorize(fwSNRseg, signature='(n),(n),()->()')
        values = []
        for i in range(0, target_wave.shape[0], batch_size):
            target_batch = target_wave[i:i+batch_size, 0, :].detach().cpu().numpy()
            pred_batch = pred_wave[i:i+batch_size, 0, :].detach().cpu().numpy()
            batch_values = fwSNRseg_vectorized(target_batch, pred_batch, fs = sample_rate)
            values.extend(batch_values.tolist())
        return float(np.mean(values))
    
    def multi_resolution_spectrogram_distance(target_wave:Tensor, #[batch, channel, signal_length]
                                              pred_wave:Tensor, #[batch, channel, signal_length]
                                              batch_size:int = 1):
        target_wave = UtilData.fit_shape_length(target_wave, 3)
        pred_wave = UtilData.fit_shape_length(pred_wave, 3)
        target_wave, pred_wave = MetricSound.trim_samples(target_wave, pred_wave)
        target_wave = UtilAudio.normalize_by_fro_norm(target_wave)
        pred_wave = UtilAudio.normalize_by_fro_norm(pred_wave)

        n_ffts = [512, 1024, 2048]
        hop_lengths = [128, 256, 512]
        spec_transforms = [torchaudio.transforms.Spectrogram(n_fft=n_fft, hop_length=hop_length, power=1) for n_fft, hop_length in zip(n_ffts, hop_lengths)]
        values = []
        for i in range(0, target_wave.shape[0], batch_size):
            clean_batch = target_wave[i:i+batch_size]
            estimated_batch = pred_wave[i:i+batch_size]
            clean_specs = [(spec_transform(clean_batch) + 1e-10).reshape(clean_batch.shape[0], -1)  for spec_transform in spec_transforms]
            estimated_specs = [(spec_transform(estimated_batch) + 1e-10).reshape(estimated_batch.shape[0], -1) for spec_transform in spec_transforms]
        
            losses_sc = [(torch.square(clean_spec - estimated_spec).sum(1) / torch.square(clean_spec).sum(1)) for clean_spec, estimated_spec in zip(clean_specs, estimated_specs)]
            losses_mag = [(clean_spec.log() - estimated_spec.log()).abs().mean(dim=1) for clean_spec, estimated_spec in zip(clean_specs, estimated_specs)]
            losses = [(loss_sc + loss_mag).detach().cpu().numpy() for loss_sc, loss_mag in zip(losses_sc, losses_mag)]
            loss_batch = np.mean(losses, axis=0)
            values.extend(loss_batch.tolist())
        return float(np.mean(values))
    
    def spectrogram_l1(target_wave:Tensor, #[batch, channel, signal_length]
                       pred_wave:Tensor, #[batch, channel, signal_length]
                       batch_size:int = 1):
        target_wave = UtilData.fit_shape_length(target_wave, 3)
        pred_wave = UtilData.fit_shape_length(pred_wave, 3)
        target_wave, pred_wave = MetricSound.trim_samples(target_wave, pred_wave)
        target_wave = UtilAudio.normalize_by_fro_norm(target_wave)
        pred_wave = UtilAudio.normalize_by_fro_norm(pred_wave)

        melspec_transform = torchaudio.transforms.Spectrogram(n_fft=1024, hop_length=256)
        values = []
        for i in range(0, target_wave.shape[0], batch_size):
            clean_batch = target_wave[i:i+batch_size]
            estimated_batch = pred_wave[i:i+batch_size]
            clean_spec = (melspec_transform(clean_batch) + 1e-10).log()
            estimated_spec = (melspec_transform(estimated_batch) + 1e-10).log()
            clean_spec, estimated_spec = clean_spec.reshape(clean_spec.shape[0], -1), estimated_spec.reshape(estimated_spec.shape[0], -1)
            values.extend((clean_spec - estimated_spec).abs().mean(dim=1).detach().cpu().numpy().tolist())
        return float(np.mean(values))
    
    def signal_to_noise(self,pred_waveform:ndarray,target_waveform:ndarray) -> float:
        return 10.*np.log10(np.sqrt(np.sum(target_waveform**2))/np.sqrt(np.sum((target_waveform - pred_waveform)**2)))
    
    @staticmethod
    def trim_samples(sample1, sample2):
        min_length = min(sample1.shape[2], sample2.shape[2])
        return sample1[:,:,:min_length], sample2[:,:,:min_length]