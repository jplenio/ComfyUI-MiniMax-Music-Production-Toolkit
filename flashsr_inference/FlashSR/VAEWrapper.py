from typing import Union, Optional
from numpy import ndarray
from torch import Tensor

import os

import torch
import torch.nn as nn

from TorchJaekwon.Util.UtilData import UtilData
from TorchJaekwon.Util.UtilAudioMelSpec import UtilAudioMelSpec

from FlashSR.AudioSR.autoencoder import AutoencoderKL
from TorchJaekwon.Util.UtilTorch import UtilTorch

class VAEWrapper:
    def __init__(self,
                 autoencoder_ckpt_path:str,
                 sr:int = '48000',
                 frame_sec:float = 5.12,
                 device:torch.device = torch.device('cpu'),
                 scale_factor_z:float = 0.3342
                 ) -> None:
        vocoder_config_dir:str = f'{os.path.dirname(os.path.abspath(__file__))}/AudioSR/args'

        self.sr:int = sr
        self.frame_sec:float = frame_sec
        self.scale_factor_z:float = scale_factor_z
        self.device:torch.device = device

        autoencoder:nn.Module = AutoencoderKL(**UtilData.yaml_load(f'{vocoder_config_dir}/model_argument.yaml'))
        autoencoder_ckpt = torch.load(autoencoder_ckpt_path, map_location='cpu')
        autoencoder.load_state_dict(autoencoder_ckpt)
        autoencoder = autoencoder.to(device)
        self.autoencoder = UtilTorch.freeze_param(autoencoder)

        self.mel_config:dict = UtilData.yaml_load(f'{vocoder_config_dir}/mel_argument.yaml')
        self.util_mel_spec = UtilAudioMelSpec(**self.mel_config)
    
    def to(self, device):
        self.device = device
        self.autoencoder = self.autoencoder.to(self.device)

    @torch.no_grad()
    def encode_to_z(self, 
                    audio:Union[ndarray,Tensor], # [batch, time]
                    normalize:bool = True,
                    scale_dict:dict = None,
                    ) -> dict: #[batch, 16, time / (hop * 8), mel_bin / 8] mel_bin: 256
        assert len(audio.shape) == 2, f'audio shape must be [batch, time] but got {audio.shape}'
        result_dict:dict = {'wav': audio}

        if normalize: 
            audio, scale_dict = self.normalize_wav(audio, scale_dict=scale_dict)
            result_dict['norm_wav'] = audio
            result_dict.update(scale_dict)

        mel_spec:Tensor = self.audio_to_mel(audio)
        result_dict['mel_spec'] = mel_spec

        encoder_posterior = self.autoencoder.encode(mel_spec)
        z = encoder_posterior.sample() * self.scale_factor_z

        result_dict['z'] = z
        return result_dict
        
    def normalize_wav(self, waveform:Union[Tensor], scale_dict:dict):
        mean_scale_factor = torch.mean(waveform, dim=1, keepdim=True) if scale_dict is None else scale_dict['mean_scale_factor']
        waveform = waveform - mean_scale_factor

        var_scale_factor = torch.max(torch.abs(waveform), dim=1, keepdim=True)[0] if scale_dict is None else scale_dict['var_scale_factor']

        waveform = waveform / (var_scale_factor + 1e-8)
        return waveform * 0.5, {'mean_scale_factor':mean_scale_factor, 'var_scale_factor':var_scale_factor}
    
    def denormalize_wav(self, waveform:Union[Tensor], scale_dict:dict):
        waveform = waveform * 2.0
        waveform = waveform * (scale_dict['var_scale_factor'] + 1e-8)
        waveform = waveform + scale_dict['mean_scale_factor']
        return waveform
    
    def get_mel_spec(self, audio:Union[ndarray,Tensor]):
        return self.util_mel_spec.get_hifigan_mel_spec(audio).to(self.device)
    
    @torch.no_grad()
    def audio_to_mel(self, audio):
        mel_spec:Tensor = self.util_mel_spec.get_hifigan_mel_spec(audio).to(self.device)
        if len(mel_spec.shape) == 3: #to make [batch, channel, freq, time]
            mel_spec = mel_spec.unsqueeze(1)
        return mel_spec.permute(0, 1, 3, 2)
    
    def z_to_audio(self,z:Tensor, scale_dict:dict = None, with_no_grad:bool = True): 
        if with_no_grad:
            with torch.no_grad():
                mel_spec = self.z_to_mel(z)
                audio = self.mel_to_audio(mel_spec, scale_dict)
                return audio
        else:
            mel_spec = self.z_to_mel(z, with_no_grad=False)
            audio = self.mel_to_audio(mel_spec, scale_dict, with_no_grad=False)
            return audio
    
    def z_to_mel(self,z:Tensor, with_no_grad:bool = True): 
        if with_no_grad:
            with torch.no_grad():
                z = (1.0 / self.scale_factor_z) * z
                mel_spec = self.autoencoder.decode(z)
                return mel_spec
        else:
            z = (1.0 / self.scale_factor_z) * z
            mel_spec = self.autoencoder.decode(z)
            return mel_spec
    
    def mel_to_audio(self, mel_spec:Tensor, scale_dict:dict = None, with_no_grad:bool = True):
        if with_no_grad:
            with torch.no_grad():
                mel_spec = mel_spec.permute(0, 1, 3, 2).squeeze(1)
                audio = self.autoencoder.vocoder(mel_spec)
                if scale_dict is not None: audio = self.denormalize_wav(audio)
                return audio
        else:
            mel_spec = mel_spec.permute(0, 1, 3, 2).squeeze(1)
            audio = self.autoencoder.vocoder(mel_spec)
            if scale_dict is not None: audio = self.denormalize_wav(audio)
            return audio