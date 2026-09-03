from typing import Optional
from torch import Tensor, device

import torch

from TorchJaekwon.Util.UtilTorch import UtilTorch
from TorchJaekwon.Model.Diffusion.DDPM.DDPM import DDPM
from TorchJaekwon.Model.Diffusion.Sampler.dpm_solver_pytorch import DPM_Solver, NoiseScheduleVP, model_wrapper

class DpmSolverForDDPM:
    def __init__(self,ddpm_module:DDPM) -> None:
        self.ddpm_module = ddpm_module

    @torch.no_grad()
    def infer(self,
              x_shape:tuple,
              cond:Optional[dict] = None,
              steps:int = 20,
              order:Optional[int] = None,
              ) -> Tensor:
        model_device:device = UtilTorch.get_model_device(self.ddpm_module)
        noise_schedule = NoiseScheduleVP(schedule='discrete', betas=self.ddpm_module.betas)
        model_fn = model_wrapper(self.get_model_wrapper_args(noise_schedule, cond))
        dpm_solver = DPM_Solver(model_fn, noise_schedule, algorithm_type="dpmsolver++")
        x_T:Tensor = torch.randn(x_shape, device=model_device)
        if order is None: order = 3 if cond is None else 2
        x = dpm_solver.sample(
            x_T,
            steps=steps,
            order=order,
            skip_type="time_uniform",
            method="multistep",
            )
        return x
    
    def get_model_wrapper_args(self, noise_schedule:NoiseScheduleVP, cond:Optional[dict] = None) -> dict:
        model_type_dict:dict = {'noise':'noise', 'x_start':'x_start', 'v_prediction':'v', 'score':'score'} 
        args:dict = {'model': self.ddpm_module.model, 'noise_schedule':noise_schedule, 'model_type': model_type_dict[self.ddpm_module.model_output_type], 'model_kwargs':{}}
        if cond is not None:
            args['model_kwargs'] = cond
        if self.ddpm_module.cfg_scale is not None:
            args['guidance_type'] = 'classifier-free'
            args['unconditional_condition'] = self.ddpm_module.get_unconditional_condition()
            args['guidance_scale'] = self.ddpm_module.cfg_scale
        return args