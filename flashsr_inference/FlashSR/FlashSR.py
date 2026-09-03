from typing import Optional, Tuple, Union

import torch

from TorchJaekwon.Model.Diffusion.DDPM.DDPM import DDPM
from TorchJaekwon.Model.Diffusion.External.diffusers.schedulers.scheduling_dpmsolver_multistep import DPMSolverMultistepScheduler
from TorchJaekwon.Model.Diffusion.External.diffusers.DiffusersWrapper import DiffusersWrapper

from FlashSR.AudioSR.AudioSRUnet import AudioSRUnet
from FlashSR.VAEWrapper import VAEWrapper
from FlashSR.SRVocoder import SRVocoder
from FlashSR.Util.UtilAudioSR import UtilAudioSR
from FlashSR.Util.UtilAudioLowPassFilter import UtilAudioLowPassFilter

class FlashSR(DDPM):
    def __init__(
            self, 
            student_ldm_ckpt_path:str,
            sr_vocoder_ckpt_path:str,
            autoencoder_ckpt_path:str,
            model_output_type:str = 'v_prediction',
            beta_schedule_type:str = 'cosine',
            **kwargs
        ) -> None:
        
        super().__init__(model = AudioSRUnet(), model_output_type=model_output_type, beta_schedule_type=beta_schedule_type, **kwargs)
        
        student_ldm_state_dict = torch.load(student_ldm_ckpt_path)
        self.load_state_dict(student_ldm_state_dict)

        self.vae = VAEWrapper(autoencoder_ckpt_path)

        self.sr_vocoder = SRVocoder()
        sr_vocoder_state_dict = torch.load(sr_vocoder_ckpt_path)
        self.sr_vocoder.load_state_dict(sr_vocoder_state_dict)

    def forward(self, 
                lr_audio:torch.Tensor, #[batch, time] ex) [4, 245760]
                num_steps:int = 1,
                lowpass_input:bool = True,
                lowpass_cutoff_freq:int = None
                ) -> torch.Tensor: #[batch, time] ex) [4, 245760]
        
        if lowpass_input:
            device = lr_audio.device
            if lowpass_cutoff_freq is None:
                lowpass_cutoff_freq:int = UtilAudioSR.find_cutoff_freq(lr_audio)
            lr_audio = lr_audio.cpu().numpy()
            lr_audio = UtilAudioLowPassFilter.lowpass(lr_audio, 48000, filter_name='cheby', filter_order=8, cutoff_freq=lowpass_cutoff_freq)
            lr_audio = torch.from_numpy(lr_audio).to(device)

        with torch.no_grad():
            pred_hr_audio = DiffusersWrapper.infer(
                ddpm_module=self, 
                diffusers_scheduler_class=DPMSolverMultistepScheduler, 
                x_shape=None, 
                cond = lr_audio,
                num_steps=num_steps,
                device=lr_audio.device
            )
            pred_hr_audio = pred_hr_audio[...,:lr_audio.shape[-1]]
            return pred_hr_audio
    
    def preprocess(self, 
                   x_start:torch.Tensor, # [batch, time]
                   cond:Optional[Union[dict,torch.Tensor]] = None, # [batch, time]
                   ) -> Tuple[torch.Tensor, torch.Tensor]: #( [batch, 1 , mel, time//hop] ,  [batch, 1 , mel, time//hop] )
        device = cond.device
        if self.vae.device != device:
            self.vae.to(device=device)
        x_dict = dict()

        cond_dict = self.vae.encode_to_z(cond)

        if x_start is not None:
            state_dict:dict = {
                'mean_scale_factor': cond_dict['mean_scale_factor'],
                'var_scale_factor': cond_dict['var_scale_factor']
            }
            x_dict = self.vae.encode_to_z(x_start, scale_dict=state_dict) ##[batch, 16, time / (hop * 8), mel_bin / 8]

        return x_dict.get('z', None), cond_dict['z'], cond_dict
        
    def postprocess(self, 
                    x:torch.Tensor, #[batch, 1, mel, time]
                    additional_data_dict:dict) -> torch.Tensor:
        mel_spec = self.vae.z_to_mel(x)
        mel_spec = mel_spec.squeeze(1).transpose(1,2)
        pred_hr_audio = self.sr_vocoder(mel_spec, additional_data_dict['norm_wav'])['pred_hr_audio']
        pred_hr_audio = self.vae.denormalize_wav(pred_hr_audio, additional_data_dict)
        return pred_hr_audio
    
    def get_x_shape(self, cond):
        return cond.shape
    
    def get_unconditional_condition(self,
                                    cond:Optional[Union[dict,torch.Tensor]] = None, 
                                    cond_shape:Optional[tuple] = None,
                                    condition_device:Optional[torch.device] = None
                                    ) -> torch.Tensor:
        if cond_shape is None: cond_shape = cond.shape
        if cond is not None and isinstance(cond,torch.Tensor): condition_device = cond.device
        return (-11.4981 + torch.zeros(cond_shape)).to(condition_device) * self.vae.scale_factor_z