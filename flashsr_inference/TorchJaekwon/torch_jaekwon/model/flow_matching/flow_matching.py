from functools import partial
from typing import Union, Callable, List, Literal, Optional, Sequence, Tuple
from torch import Tensor, device

import torch
from torch import nn
import torch.nn.functional as F

from ...instantiate import import_class
from ...util import util_data, util_torch
from ..diffusion.ddpm.time_sampler import TimeSampler
from ..diffusion.cfg import cfg, model_forward as cfg_model_forward
from .sampler import Sampler as flow_sampler

class FlowMatching(nn.Module):
    '''
    Note: This implementation uses a reversed time convention compared to the original Flow Matching paper (https://arxiv.org/abs/2210.02747).
    In the paper, t=0 corresponds to a standard normal distribution and t=1 to a distribution approximately equal to the data.
    Here, t=0 corresponds to the data-like distribution and t=1 to noise.
    '''
    def __init__(
        self,
        # model
        model_class_meta:Optional[dict] = None, #{path: '<module>.<ClassName>', args: {}}
        model:Optional[nn.Module] = None,
        # time
        timestep_sampler:Literal['uniform', 'logit_normal'] = 'logit_normal',
        # loss
        loss_func:Union[nn.Module, Callable, Tuple[str,str]] = F.mse_loss, # if tuple (package name, func name). ex) (torch.nn.functional, mse_loss)
        # classifier free guidance
        unconditional_prob:float = 0, #if unconditional_prob > 0, this model works as classifier free guidance    
        cfg_scale:Optional[Union[float, Sequence[float]]] = None, # CFG scale; a sequence guides one condition per entry
        cfg_rescale:Optional[float] = None,
        cfg_calc_type:Literal['batch', 'sequential'] = 'batch'
    ) -> None:
        super().__init__()
        # model
        if model_class_meta is not None:
            model_class = import_class(module_name = model_class_meta['path'])
            self.model = model_class(**model_class_meta['args'])
        else:
            self.model:nn.Module = model
        # time
        self.time_sampler = TimeSampler(time_type = 'continuous', sampler_type = timestep_sampler)
        # loss
        self.loss_func:Union[nn.Module, Callable] = loss_func
        # classifier free guidance
        self.unconditional_prob:float = unconditional_prob
        self.cfg_scale:Optional[Union[float, Sequence[float]]] = cfg_scale
        self.cfg_rescale:Optional[float] = cfg_rescale
        self.cfg_calc_type:Literal['batch', 'sequential'] = cfg_calc_type
    
    def forward(
        self,
        x_start:Tensor,
        cond:Optional[dict] = None,
    ) -> Tensor: # return loss
        x_start, cond, _ = self.preprocess(x_start, cond)
        batch_size:int = x_start.shape[0] 
        input_device:device = x_start.device
        t:Tensor = self.time_sampler.sample(batch_size).to(input_device)
        if self.unconditional_prob > 0:
            uncond_dict:dict = self.get_unconditional_condition(cond=cond, condition_device=input_device)
            for cond_name, uncond in uncond_dict.items():
                dropout_mask = torch.bernoulli(torch.full((uncond.shape[0], *[1 for _ in range(len(uncond.shape) - 1)]), self.unconditional_prob, device=input_device)).to(torch.bool)
                cond[cond_name] = torch.where(dropout_mask, uncond, cond[cond_name])
        return self.get_loss(x_start, cond, t)
    
    @torch.no_grad()
    def infer(
        self,
        x_shape:tuple = None,
        cond:Optional[Union[dict, List[dict]]] = None,  # one conditioning, or every one of them
        sampler_type:Literal['discrete_euler', 'rk4', 'flow_dpmpp'] = 'discrete_euler',
        steps:int = 100,
        time_sampler_type:Literal['linear', 'linear_quadratic'] = 'linear_quadratic',
        sigma_max:float = 1,
        temperature:float = 1.0,
        cfg_scale:Optional[Union[float, Sequence[float]]] = None,  # defaults to the ctor value
        cfg_forward:Callable = cfg,           # guidance method, see model/diffusion/cfg.py
    ) -> Tensor:
        _, cond, additional_data_dict = self.preprocess(None, cond)

        if x_shape is None: x_shape = self.get_x_shape(cond, additional_data_dict)
        model_device:device = util_torch.get_model_device(self.model)
        x:Tensor = torch.randn(x_shape, device = model_device) * (temperature ** 0.5)

        sigma_max = min(sigma_max, 1)

        sampling_func = getattr(flow_sampler, sampler_type)
        x = sampling_func(
            model = self.apply_model, 
            x = x, 
            steps = steps, 
            sigma_max = sigma_max, 
            time_sampler_type = time_sampler_type,
            cond = cond, 
            cfg_scale = self.cfg_scale if cfg_scale is None else cfg_scale,
            cfg_rescale = self.cfg_rescale,
            cfg_forward = cfg_forward
        )

        return self.postprocess(x, additional_data_dict = additional_data_dict)
    
    def get_loss(
        self, 
        x_start:Tensor,
        cond:Optional[dict],
        t:Tensor, 
        noise:Optional[Tensor] = None
    ):
        noise:Tensor = util_data.default(noise, lambda: torch.randn_like(x_start))
        x_noisy:Tensor = self.q_sample(x_start=x_start, t=t, noise=noise)
        model_output:Tensor = self.apply_model(x_noisy, t, cond)

        target:Tensor = self.get_target(x_start, noise, t)
        
        if target.shape != model_output.shape: print(f'warning: target shape({target.shape}) and model shape({model_output.shape}) are different')
        return self.loss_func(target, model_output)
    
    def apply_model(
        self,
        x:Tensor,
        t:Tensor,
        cond:Optional[Union[dict, List[dict]]],
        cfg_scale:Optional[Union[float, Sequence[float]]] = None,
        cfg_rescale:Optional[float] = None,
        cfg_forward:Callable = cfg,
    ) -> Tensor:
        if cond is None:
            cond = dict()
        if cfg_scale is None or cfg_scale == 1.0:
            assert isinstance(cond, dict), "unguided sampling takes one conditioning, not a list"
            return self.model(x, t, **cond)
        uncond_dict:Optional[dict] = self.get_unconditional_condition(cond=cond)
        cfg_conds:List[dict] = (
            cond if uncond_dict is None
            else [cond, {key: uncond_dict.get(key, cond[key]) for key in cond}]
        )
        run_multiple_conds = partial(
            cfg_model_forward, self.model, x, t, sequential=self.cfg_calc_type == 'sequential'
        )
        return cfg_forward(run_multiple_conds, cfg_conds, cfg_scale, cfg_rescale)

    def q_sample(self, x_start:Tensor, t:Tensor, noise=None) -> Tensor:
        '''
        noisy x sample
        '''
        alphas, sigmas = self.t_to_alpha_sigma(t)
        alphas = alphas[:, *[ None for _ in range(len(x_start.shape) - 1) ]]
        sigmas = sigmas[:, *[ None for _ in range(len(x_start.shape) - 1) ]]
        
        noise = util_data.default(noise, lambda: torch.randn_like(x_start))
        return x_start * alphas + noise * sigmas
    
    def get_target(self, x_start, noise, t):
        return noise - x_start
    
    def t_to_alpha_sigma(self, t:Tensor) -> Tuple[Tensor,Tensor]:
        return 1-t, t
    
    def make_decision(
        self,
        probability:float #[0,1]
    ) -> bool:
        if probability == 0:
            return False
        if float(torch.rand(1)) < probability:
            return True
        else:
            return False
    
    def get_unconditional_condition(
        self,
        cond:Optional[dict] = None,
        condition_device:Optional[device] = None
    ) -> dict:
        return dict()

    def preprocess(self, x_start:Tensor, cond:Optional[dict] = None) -> Tuple[Tensor, Optional[Union[dict,Tensor]], dict]:
        return x_start, cond, None

    def postprocess(self, x:Tensor, additional_data_dict:dict) -> Tensor:
        return x
    
    def get_x_shape(self, cond:Optional[Union[dict, List[dict]]] = None, additional_data_dict:Optional[dict] = None):
        return None