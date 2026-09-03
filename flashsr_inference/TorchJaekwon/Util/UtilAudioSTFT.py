#type
from typing import Union,Dict
from numpy import ndarray
from torch import Tensor

import matplotlib.pyplot as plt
import numpy as np
import torch
import librosa
import librosa.display

from TorchJaekwon.Util.UtilAudio import UtilAudio

class UtilAudioSTFT(UtilAudio):
    def __init__(self,nfft:int, hop_size:int):
        super().__init__()
        self.nfft = nfft
        self.hop_size = hop_size
        self.hann_window = torch.hann_window(self.nfft)
    
    def get_mag_phase_stft_np(self,audio):
        stft = librosa.stft(audio,n_fft=self.nfft, hop_length=self.hop_size)
        mag = abs(stft)
        phase = np.exp(1.j * np.angle(stft))
        return {"mag":mag,"phase":phase}
    
    def get_mag_phase_stft_np_mono(self,audio):
        if audio.shape[0] == 2:
            return self.get_mag_phase_stft_np(np.mean(audio,axis=0))
        else:
            return self.get_mag_phase_stft_np(audio)

    
    def stft_torch(self,
                   audio:Union[ndarray,Tensor] # [time] or [batch, time] or [batch, channel, time]
                   ) -> Dict[str,Tensor]:
        
        audio_torch:Tensor = torch.from_numpy(audio) if type(audio) == np.ndarray else audio
        
        assert(len(audio_torch.shape) <= 3), f'Error: stft_torch() audio torch shape is {audio_torch.shape}'

        if (len(audio_torch.shape) == 1): audio_torch = audio_torch.unsqueeze(0)

        shape_is_three = True if len(audio_torch.shape) == 3 else False
        if shape_is_three:
            batch_size, channels_num, segment_samples = audio_torch.shape
            audio_torch = audio_torch.reshape(batch_size * channels_num, segment_samples)
        
        spec_dict:Dict[str,Tensor] = dict()

        audio_torch = torch.nn.functional.pad(audio_torch.unsqueeze(1), (int((self.nfft-self.hop_size)/2), int((self.nfft-self.hop_size)/2)), mode='reflect').squeeze(1)
        spec_dict['stft'] = torch.stft(audio_torch, 
                          self.nfft, 
                          hop_length=self.hop_size, 
                          window=self.hann_window.to(audio_torch.device),
                          center=False,
                          pad_mode='reflect',
                          normalized=False,
                          onesided=True,
                          return_complex=True)
        '''
        spec_dict['stft'] = torch.stft(audio_torch,
                                 n_fft=self.nfft,
                                 hop_length=self.hop_size,
                                 window=self.hann_window.to(audio_torch.device),
                                 return_complex=True)
        '''
        spec_dict['mag'] = spec_dict['stft'].abs()
        spec_dict['angle'] = spec_dict['stft'].angle()

        if shape_is_three:
            _, time_steps, freq_bins = spec_dict['stft'].shape
            for feature_name in spec_dict:
                spec_dict[feature_name] = spec_dict[feature_name].reshape(batch_size, channels_num, time_steps, freq_bins)

        return spec_dict
    
    def istft_torch_from_mag_and_angle(self,
                                       mag:Tensor,
                                       angel:Tensor):
        stft_complex:Tensor = torch.polar(abs = mag, angle = angel)
        return torch.istft(stft_complex, self.nfft, hop_length=self.hop_size,window=self.hann_window.to(stft_complex.device),
                          center=True, onesided=True)
    
    def get_pred_accom_by_subtract_pred_vocal_audio(self,pred_vocal,mix_audio):
        pred_vocal_mag = self.get_mag_phase_stft_np_mono(pred_vocal)["mag"]
        mix_stft = self.get_mag_phase_stft_np_mono(mix_audio)
        mix_mag = mix_stft["mag"]
        mix_phase = mix_stft["phase"]
        pred_accom_mag = mix_mag - pred_vocal_mag
        pred_accom_mag[pred_accom_mag < 0] = 0
        pred_accom = librosa.istft(pred_accom_mag*mix_phase,hop_length=self.hop_size,length=mix_audio.shape[-1])
        return pred_accom
    
    def stft_plot_from_audio_path(self,audio_path:str,save_path:str = None, dpi:int = 500) -> None:
        audio, sr = librosa.load(audio_path)
        stft_audio:ndarray = librosa.stft(audio)
        spectrogram_db_scale:ndarray = librosa.amplitude_to_db(np.abs(stft_audio), ref=np.max)
        plt.figure(dpi=dpi)
        librosa.display.specshow(spectrogram_db_scale)
        plt.colorbar()
        if save_path is not None:
            plt.savefig(save_path,dpi=dpi)

    @staticmethod
    def spec_to_figure(spec,
                       vmin:float = -6.0, 
                       vmax:float = 1.5,
                       fig_size:tuple = (12,6),
                       dpi = 400,
                       transposed=False,
                       save_path=None):
        if isinstance(spec, torch.Tensor):
            spec = spec.squeeze().cpu().numpy()
        spec = spec.squeeze()
        fig = plt.figure(figsize=fig_size, dpi = dpi)
        plt.pcolor(spec.T if transposed else spec, vmin=vmin, vmax=vmax)
        if save_path is not None:
            plt.savefig(save_path,dpi=dpi)
        plt.close()
        return fig