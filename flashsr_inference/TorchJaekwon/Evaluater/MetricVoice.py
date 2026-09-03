#type
from typing import Optional,Dict
from torch import Tensor
from numpy import ndarray
#import
import numpy as np
import torch
try: import pyworld as pw
except: print('Warning: pyworld is not installed')
try: import pysptk
except: print('Warning: pysptk is not installed')
try: from pesq import pesq
except: print('Warning: pesq is not installed')
try: from fastdtw import fastdtw
except: print('Warning: fastdtw is not installed')
try: from skimage.metrics import structural_similarity as ssim
except: print('Warning: skimage is not installed')
#torchjaekwon import
from TorchJaekwon.Util.UtilAudioMelSpec import UtilAudioMelSpec
from TorchJaekwon.Util.UtilAudio import UtilAudio
#internal import

class MetricVoice:
    def __init__(self,
                 sample_rate:int = 16000,
                 nfft:Optional[int] = None,
                 hop_size:Optional[int] = None,
                 mel_size:Optional[int] = None,
                 frequency_min:Optional[float] = None,
                 frequency_max:Optional[float] = None) -> None:
        
        spec_config_of_sr_dict:Dict[int,dict] = {
            '''
            16000:{
                nfft: 512,
                hop_size: 256,
                mel_size: 80,
                frequency_min: 0,
                frequency_max: float(sample_rate // 2)
            },
            44100:{
                nfft: 1024,
                hop_size: 512,
                mel_size: 128,
                frequency_min: 0,
                frequency_max: float(sample_rate // 2)
            }
            '''
        }
        spec_config_of_sr:dict = UtilAudioMelSpec.get_default_mel_spec_config(sample_rate = sample_rate) if sample_rate not in spec_config_of_sr_dict else spec_config_of_sr_dict[sample_rate]
        
        self.util_mel = UtilAudioMelSpec(nfft = spec_config_of_sr['nfft'] if nfft is None else nfft, 
                                         hop_size = spec_config_of_sr['hop_size'] if hop_size is None else hop_size, 
                                         sample_rate = sample_rate, 
                                         mel_size = spec_config_of_sr['mel_size'] if mel_size is None else mel_size, 
                                         frequency_min = spec_config_of_sr['frequency_min'] if frequency_min is None else frequency_min, 
                                         frequency_max = spec_config_of_sr['frequency_max'] if frequency_max is None else frequency_max)
        
    def get_spec_metrics_from_audio(
            self,
            pred, #linear scale spectrogram [time]
            target,
            metric_list:list = ['lsd','ssim','sispnr', 'l1', 'l2']
        ) -> Dict[str,float]:
        
        source_spec_dict = self.get_spec_dict_of_audio(pred)
        target_spec_dict = self.get_spec_dict_of_audio(target)

        metric_dict = dict()
        for spec_name in source_spec_dict:
            if 'lsd' in metric_list:
                metric_dict[f'lsd_{spec_name}'] = MetricVoice.get_lsd_from_spec(source_spec_dict[spec_name],target_spec_dict[spec_name])
            if 'ssim' in metric_list:
                metric_dict[f'ssim_{spec_name}'] = self.get_ssim(source_spec_dict[spec_name], target_spec_dict[spec_name])
        
        linear_spec_name = list(source_spec_dict.keys())
        for spec_name in linear_spec_name:
            source_spec_dict[f'{spec_name}_log'] = np.log10(np.clip(source_spec_dict[spec_name], a_min=1e-8, a_max=None))
            target_spec_dict[f'{spec_name}_log'] = np.log10(np.clip(target_spec_dict[spec_name], a_min=1e-8, a_max=None))
        
        for spec_name in source_spec_dict:
            if 'l1' in metric_list: metric_dict[f'l1_{spec_name}'] = float(np.mean(np.abs(source_spec_dict[spec_name] - target_spec_dict[spec_name])))
            if 'l2' in metric_list: metric_dict[f'l2_{spec_name}'] = float(np.mean(np.square(source_spec_dict[spec_name] - target_spec_dict[spec_name])))
            if 'sispnr' in metric_list: metric_dict[f'sispnr_{spec_name}'] = MetricVoice.get_sispnr(torch.from_numpy(source_spec_dict[spec_name]),torch.from_numpy(target_spec_dict[spec_name]))
        
        return metric_dict
        
    
    def get_lsd_from_audio(self,
                           pred, # [time]
                           target # [time]
                           ) -> Dict[str,float] :
        pred_spec_dict = self.get_spec_dict_of_audio(pred)
        target_spec_dict = self.get_spec_dict_of_audio(target)
        lsd_dict = dict()
        for spec_name in pred_spec_dict:
            lsd_dict[spec_name] = MetricVoice.get_lsd_from_spec(pred_spec_dict[spec_name],target_spec_dict[spec_name])
        return lsd_dict
    
    def get_spec_dict_of_audio(self,audio):
        spectrogram_mag = self.util_mel.stft_torch(audio)['mag'].float()
        mel_spec = self.util_mel.spec_to_mel_spec(spectrogram_mag)
        return {'spec_mag':spectrogram_mag.squeeze().detach().cpu().numpy(), 'mel': mel_spec.squeeze().detach().cpu().numpy()}

    @staticmethod
    def get_lsd_from_spec(pred, #linear scale spectrogram [freq, time]
                          target,
                          eps = 1e-12):
        #log_spectral_distance
        # in non-log scale
        lsd = ((target + eps)**2)/((pred + eps)**2)
        lsd = lsd + eps
        lsd = np.log10(lsd)**2 #torch.log10((target**2/((source + eps)**2)) + eps)**2
        lsd = np.mean(np.mean(lsd,axis=0)**0.5,axis=0) #torch.mean(torch.mean(lsd,dim=3)**0.5,dim=2)
        return float(lsd)
    
    @staticmethod
    def get_si_sdr(source, target):
        alpha = np.dot(target, source)/np.linalg.norm(source)**2   
        sdr = 10*np.log10(np.linalg.norm(alpha*source)**2/np.linalg.norm(
            alpha*source - target)**2)
        return sdr
    
    @staticmethod
    def get_pesq(source:ndarray, #[time]
                 target:ndarray, #[time]
                 sample_rate:int = [8000,16000][1],
                 band:str = ['wide-band','narrow-band'][0]):
        assert (sample_rate in [8000,16000]), f'sample rate must be either 8000 or 16000. current sample rate {sample_rate}'
        if (sample_rate == 16000 and band == 'narrow-band'): print('Warning: narrowband (nb) mode only when sampling rate is 8000Hz')
        if band == 'wide-band':
            return pesq(sample_rate, target, source, 'wb')
        else:
            return pesq(sample_rate, target, source, 'nb')
        
    @staticmethod
    def get_mcd(source:ndarray, #[time]
                target:ndarray, #[time]
                sample_rate:int, 
                frame_period=5):
        cost_function = MetricVoice.dB_distance
        mgc_source = MetricVoice.get_mgc(source, sample_rate, frame_period)
        mgc_target = MetricVoice.get_mgc(target, sample_rate, frame_period)

        length = min(mgc_source.shape[0], mgc_target.shape[0])
        mgc_source = mgc_source[:length]
        mgc_target = mgc_target[:length]

        mcd, _ = fastdtw(mgc_source[..., 1:], mgc_target[..., 1:], dist=cost_function)
        mcd = mcd/length

        return float(mcd), length
    
    @staticmethod
    def get_mgc(audio, sample_rate, frame_period, fft_size=512, mcep_size=60, alpha=0.65):
        if isinstance(audio, Tensor):
            if audio.ndim > 1:
                audio = audio[0]

            audio = audio.numpy()

        _, sp, _ = pw.wav2world(
            audio.astype(np.double), fs=sample_rate, frame_period=frame_period, fft_size=fft_size)
        mgc = pysptk.sptk.mcep(
            sp, order=mcep_size, alpha=alpha, maxiter=0, etype=1, eps=1.0E-8, min_det=0.0, itype=3)

        return mgc
    
    @staticmethod
    def dB_distance(source, target):
        dB_const = 10.0/np.log(10.0)*np.sqrt(2.0)
        distance = source - target

        return dB_const*np.sqrt(np.inner(distance, distance))
    
    @staticmethod
    def get_sispnr(source, target, eps = 1e-12):
        # scale_invariant_spectrogram_to_noise_ratio
        # in log scale
        output, target = UtilAudio.energy_unify(source, target)
        noise = output - target
        # print(pow_p_norm(target) , pow_p_norm(noise), pow_p_norm(target) / (pow_p_norm(noise) + EPS))
        sp_loss = 10 * torch.log10((UtilAudio.pow_p_norm(target) / (UtilAudio.pow_p_norm(noise) + eps) + eps))
        return float(sp_loss)
    
    @staticmethod
    def get_ssim(source, target, data_range=None):
        if data_range is None:
            data_range = max(source.max(), target.max()) - min(source.min(), target.min())
        return float(ssim(source, target, win_size=7, data_range=data_range))
    
    
'''

    
    
    def get_sdr_torchmetrics(self,pred_audio:Union[Tensor,ndarray], target_audio:Union[Tensor,ndarray]) -> dict:
        result_dict = dict()
        audio_spec_tensor_dict:dict = self.get_audio_and_spec_tensor_pred_target_dict(pred_audio, target_audio)
        for data_type in audio_spec_tensor_dict["pred"]:
            sdr = SignalDistortionRatio()
            result_dict[f"sdr_torchmetrics_{data_type}"] = float(sdr(audio_spec_tensor_dict["pred"][data_type].clone(),audio_spec_tensor_dict["target"][data_type].clone()))

        return result_dict

    
    
def get_f0(audio, sample_rate, frame_period=5, method='dio'):
    if isinstance(audio, torch.Tensor):
        if audio.ndim > 1:
            audio = audio[0]

        audio = audio.numpy()

    hop_size = int(frame_period*sample_rate/1000)
    if method == 'dio':
        f0, _ = pw.dio(audio.astype(np.double), sample_rate, frame_period=frame_period)
    elif method == 'harvest':
        f0, _ = pw.harvest(audio.astype(np.double), sample_rate, frame_period=frame_period)
    elif method == 'swipe':
        f0 = pysptk.sptk.swipe(audio.astype(np.double), sample_rate, hopsize=hop_size)
    elif method == 'rapt':
        f0 = pysptk.sptk.rapt(audio.astype(np.double), sample_rate, hopsize=hop_size)
    else:
        raise ValueError(f'No such f0 extract method, {method}.')

    f0 = torch.from_numpy(f0)
    vuv = 1*(f0 != 0.0)

    return f0, vuv


def get_f0_rmse(source, target, sample_rate, frame_period=5, method='dio'):
    length = min(source.shape[-1], target.shape[-1])

    source_f0, source_v = get_f0(source[...,:length], sample_rate, frame_period, method)
    target_f0, target_v = get_f0(target[...,:length], sample_rate, frame_period, method)

    source_uv = 1 - source_v
    target_uv = 1 - target_v
    tp_mask = source_v*target_v

    length = tp_mask.sum().item()

    f0_rmse = 1200.0*torch.abs(torch.log2(target_f0 + target_uv) - torch.log2(source_f0 + source_uv))
    f0_rmse = tp_mask*f0_rmse
    f0_rmse = f0_rmse.sum()/length

    return f0_rmse.item(), length
'''