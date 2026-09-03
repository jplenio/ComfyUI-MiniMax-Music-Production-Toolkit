from torch import Tensor, device
from typing import Optional, Union, Literal

import math
import torch

from ....util import util_data, util_torch
from .ddpm import DDPM
from ..external.k_diffusion import sampling as e_sampling
from ..external.k_diffusion.utils import append_dims

class EDM(DDPM):
    '''
    Elucidating the Design Space of Diffusion-Based Generative Models (Karras et al., 2022)
    aka k-dissusion / KDiffusion / Karras Diffusion
    '''
    def __init__(self, **kwargs) -> None:
        default_args = dict()
        default_args['model_output_type'] = 'v_prediction'
        default_args['time_type'] = 'continuous'
        default_args['timesteps'] = None 
        default_args['betas'] = None
        default_args['beta_schedule_type'] = None
        default_args['beta_arg_dict'] = None
        assert not any([key in kwargs for key in default_args]), f"Can't change the following params: {list(default_args.keys())}"
        kwargs.update(default_args)
        super().__init__(**kwargs)

        self.schedule_type:Literal['cosine', 'edm'] = 'cosine'
        self.sigma_data = 1.
        
    def forward(
        self,
        x:Optional[Tensor] = None,
        sigma: Tensor = torch.Tensor([0]),
        x_shape:Optional[tuple] = None,
        cond:Optional[Union[dict,Tensor]] = None,
        stage: Literal['train', 'infer'] = 'train'
    ) -> Tensor: # return loss value or sample
        '''
        if stage == 'train': return loss value
        if stage == 'infer': return the output of the model. for full inference, use infer() method
        '''
        if stage == 'train':
            return super().forward(x_start = x, x_shape = x_shape, cond = cond, stage = stage)
        else:
            c_skip, c_out, c_in = [append_dims(scaling, x.ndim) for scaling in self.get_scalings(sigma)]
            t = self.sigma_to_t(sigma)
            model_output = self.apply_model(x = x * c_in, t = t, cond = cond, cfg_scale=self.cfg_scale)
            return model_output * c_out + x * c_skip
            
    def q_sample(self, x_start:Tensor, t:Tensor, noise=None) -> Tensor:
        '''
        noisy x sample for forward process
        '''
        alphas, sigmas = self.t_to_alpha_sigma(t)
        alphas = alphas[:, *[ None for _ in range(len(x_start.shape) - 1) ]]
        sigmas = sigmas[:, *[ None for _ in range(len(x_start.shape) - 1) ]]
        
        noise = util_data.default(noise, lambda: torch.randn_like(x_start))
        return x_start * alphas + noise * sigmas
    
    @torch.no_grad()
    def infer(
        self,
        noise:Optional[Tensor] = None,
        x_shape:tuple = None,
        cond:Optional[Union[dict,Tensor]] = None,
        sampler_type:Literal['heun', 'lms', 'dpmpp_2s_ancestral', 'dpm_2', 'dpm_fast', 'dpm_adaptive', 'dpmpp_2m_sde', 'dpmpp_3m_sde'] = 'dpmpp_3m_sde',
        steps:int = 100,
        sigma_min:float = 0.3, #0.5, 
        sigma_max:float = 500, #50, 
        rho:float = 1.0,
    ) -> Tensor:
        _, cond, additional_data_dict = self.preprocess(None, cond)
        model_device:device = util_torch.get_model_device(self.model)
        sigmas = e_sampling.get_sigmas_polyexponential(steps, sigma_min, sigma_max, rho, device=model_device)

        if noise is None:
            if x_shape is None: x_shape = self.get_x_shape(cond)
            noise:Tensor = torch.randn(x_shape, device = model_device)
            noise = noise * sigmas[0]

        sampling_args:dict = { 
            'model': self, 
            'x': noise, 
            'disable': False, 
            'extra_args':{
                'cond': cond,
                'stage': 'infer'
            }
        }
        if sampler_type in ['dpm_adaptive', 'dpm_fast']:
            sampling_args['sigma_min'] = sigma_min
            sampling_args['sigma_max'] = sigma_max
            if sampler_type == 'dpm_adaptive':
                sampling_args['rtol'] = 0.01
                sampling_args['atol'] = 0.01
            elif sampler_type == 'dpm_fast':
                sampling_args['n'] = steps
        else:
            sampling_args['sigmas'] = sigmas
        
        sampler_func_name:str = f'sample_{sampler_type}'
        sampler_func:callable = getattr(e_sampling, sampler_func_name)
        x = sampler_func(**sampling_args)

        return self.postprocess(x, additional_data_dict = additional_data_dict)

    def alpha_sigma_to_t(self, alpha, sigma):
        """
        Source: https://github.com/crowsonkb/v-diffusion-pytorch
        Paper: https://arxiv.org/abs/2202.00512
        Returns a timestep, given the scaling factors for the clean image and for the noise.
        """
        return torch.atan2(sigma, alpha) / math.pi * 2

    def t_to_alpha_sigma(self, t):
        """
        Source: https://github.com/crowsonkb/v-diffusion-pytorch
        Paper: https://arxiv.org/abs/2202.00512
        Returns the scaling factors for the clean image and for the noise, given a timestep."""
        return torch.cos(t * math.pi / 2), torch.sin(t * math.pi / 2)
    
    def sigma_to_t(self, sigma):
        return sigma.atan() / math.pi * 2

    def t_to_sigma(self, t):
        return (t * math.pi / 2).tan()
    
    def get_v(self, x_start, noise, t):
        '''
        Progressive Distillation for Fast Sampling of Diffusion Models
        https://arxiv.org/abs/2202.00512
        '''
        alphas, sigmas = self.t_to_alpha_sigma(t)
        alphas = alphas[:, *[ None for _ in range(len(x_start.shape) - 1) ]]
        sigmas = sigmas[:, *[ None for _ in range(len(x_start.shape) - 1) ]]
        return noise * alphas - x_start * sigmas
    
    def get_scalings(self, sigma):
        c_skip = self.sigma_data ** 2 / (sigma ** 2 + self.sigma_data ** 2)
        c_out = -sigma * self.sigma_data / (sigma ** 2 + self.sigma_data ** 2) ** 0.5
        c_in = 1 / (sigma ** 2 + self.sigma_data ** 2) ** 0.5
        return c_skip, c_out, c_in
    
    '''
    def loss(self, input, noise, sigma, **kwargs):
        c_skip, c_out, c_in = [utils.append_dims(x, input.ndim) for x in self.get_scalings(sigma)]
        noised_input = input + noise * utils.append_dims(sigma, input.ndim)
        model_output = self.inner_model(noised_input * c_in, self.sigma_to_t(sigma), **kwargs)
        target = (input - c_skip * noised_input) / c_out
        return (model_output - target).pow(2).flatten(1).mean(1)'
    '''
