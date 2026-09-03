from typing import Optional
from torch import Tensor, device

import torch
from tqdm import tqdm
from TorchJaekwon.Util.UtilTorch import UtilTorch
from TorchJaekwon.Model.Diffusion.DDPM import DDPM

class DiffusersWrapper:
    @staticmethod
    def get_diffusers_output_type_name(ddpm_module: DDPM) -> str:
        output_type_dict = {
            'v_prediction': 'v_prediction',
            'noise': 'epsilon',
            'x_start': 'sample'
        }
        return output_type_dict[ddpm_module.model_output_type]
    
    @staticmethod
    def get_diffusers_scheduler_config(ddpm_module: DDPM, scheduler_args: dict):
        config:dict = {
            'num_train_timesteps': ddpm_module.timesteps,
            'trained_betas': ddpm_module.betas.to('cpu'),
            'prediction_type': DiffusersWrapper.get_diffusers_output_type_name(ddpm_module),
        }
        config.update(scheduler_args)
        return config
    
    @staticmethod
    def infer(
        ddpm_module: DDPM, 
        diffusers_scheduler_class,
        x_shape:tuple,
        cond:Optional[dict] = None,
        is_cond_unpack:bool = False,
        num_steps: int = 20,
        scheduler_args: dict = {'timestep_spacing': 'trailing'},
        cfg_scale: float = None,
        device:device = None
        ) -> Tensor:
        
        noise_scheduler = diffusers_scheduler_class(**DiffusersWrapper.get_diffusers_scheduler_config(ddpm_module, scheduler_args))
        _, cond, additional_data_dict = ddpm_module.preprocess(x_start = None, cond=cond)
        if x_shape is None: x_shape = ddpm_module.get_x_shape(cond=cond)
        noise_scheduler.set_timesteps(num_steps)
        model_device:device = UtilTorch.get_model_device(ddpm_module) if device is None else device
        x:Tensor = torch.randn(x_shape, device = model_device)
        x = x * noise_scheduler.init_noise_sigma
        for t in tqdm(noise_scheduler.timesteps, desc='sample time step'):
            denoiser_input = noise_scheduler.scale_model_input(x, t)
            model_output = ddpm_module.apply_model(denoiser_input, 
                                                   torch.full((x_shape[0],), t, device=model_device, dtype=torch.long), 
                                                   cond, 
                                                   is_cond_unpack, 
                                                   cfg_scale = ddpm_module.cfg_scale if cfg_scale is None else cfg_scale)
            x = noise_scheduler.step( model_output, t, x, return_dict=False)[0]
        
        return ddpm_module.postprocess(x, additional_data_dict)
        

        