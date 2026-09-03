from typing import Optional
from torch import Tensor,device

from tqdm import tqdm
import torch
from collections import deque

from TorchJaekwon.Util.UtilTorch import UtilTorch
from TorchJaekwon.Model.Diffusion.DDPM.DDPM import DDPM

from TorchJaekwon.Model.Diffusion.DDPM.DiffusionUtil import DiffusionUtil

class PNDM:
    #Pseudo Numerical methods for Diffusion Models on manifolds (PNDM) is by Luping Liu, Yi Ren, Zhijie Lin and Zhou Zhao

    def __init__(self, ddpm_module:DDPM) -> None:
        self.ddpm_module = ddpm_module

    @torch.no_grad()
    def infer(self,
              x_shape:Optional[tuple],
              cond:Optional[dict] = None,
              is_cond_unpack:bool = False,
              pndm_speedup:int = 10) -> Tensor:
        _, cond, additional_data_dict = self.ddpm_module.preprocess(x_start = None, cond=cond)
        if x_shape is None: x_shape = self.ddpm_module.get_x_shape(cond=cond)
        total_timesteps:int = self.ddpm_module.timesteps
        model_device:device = UtilTorch.get_model_device(self.ddpm_module)
        x:Tensor = torch.randn(x_shape, device = model_device)
        self.noise_list = deque(maxlen=4)

        for i in tqdm(reversed(range(0, total_timesteps, pndm_speedup)), desc='sample time step', total=total_timesteps // pndm_speedup):
            x = self.p_sample_plms(x, torch.full((x_shape[0],), i, device=model_device, dtype=torch.long), pndm_speedup, cond, is_cond_unpack)

        return self.ddpm_module.postprocess(x, additional_data_dict)
    
    @torch.no_grad()
    def p_sample_plms(self, x, t, interval, cond, is_cond_unpack):
        """
        Use the PLMS method from [Pseudo Numerical Methods for Diffusion Models on Manifolds](https://arxiv.org/abs/2202.09778).
        """

        noise_list = self.noise_list
        noise_pred = self.ddpm_module.apply_model(x, t, cond, is_cond_unpack, self.ddpm_module.cfg_scale)
        if self.ddpm_module.model_output_type == 'v_prediction':
            noise_pred = self.ddpm_module.predict_noise_from_v(x, t, noise_pred)

        if len(noise_list) == 0:
            x_pred = self.get_x_pred(x, noise_pred, t, interval)
            noise_pred_prev = self.ddpm_module.apply_model(x_pred, torch.max(t-interval, torch.zeros_like(t)), cond, is_cond_unpack) #max(t-interval, 0)
            noise_pred_prime = (noise_pred + noise_pred_prev) / 2
        elif len(noise_list) == 1:
            noise_pred_prime = (3 * noise_pred - noise_list[-1]) / 2
        elif len(noise_list) == 2:
            noise_pred_prime = (23 * noise_pred - 16 * noise_list[-1] + 5 * noise_list[-2]) / 12
        elif len(noise_list) >= 3:
            noise_pred_prime = (55 * noise_pred - 59 * noise_list[-1] + 37 * noise_list[-2] - 9 * noise_list[-3]) / 24

        x_prev = self.get_x_pred(x, noise_pred_prime, t, interval)
        noise_list.append(noise_pred)

        return x_prev
    
    def get_x_pred(self, x, noise_t, t, interval):
        a_t = DiffusionUtil.extract(self.ddpm_module.alphas_cumprod, t, x.shape)
        a_prev = DiffusionUtil.extract(self.ddpm_module.alphas_cumprod, torch.max(t-interval, torch.zeros_like(t)), x.shape)
        a_t_sq, a_prev_sq = a_t.sqrt(), a_prev.sqrt()

        x_delta = (a_prev - a_t) * ((1 / (a_t_sq * (a_t_sq + a_prev_sq))) * x - 1 / (a_t_sq * (((1 - a_prev) * a_t).sqrt() + ((1 - a_t) * a_prev).sqrt())) * noise_t)
        x_pred = x + x_delta

        return x_pred