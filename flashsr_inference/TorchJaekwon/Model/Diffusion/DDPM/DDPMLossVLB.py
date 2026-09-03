from typing import Union, Callable, Literal, Optional, Tuple
from numpy import ndarray
from torch import Tensor, device

from tqdm import tqdm
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

from TorchJaekwon.GetModule import GetModule
from TorchJaekwon.Util.UtilData import UtilData
from TorchJaekwon.Util.UtilTorch import UtilTorch
from TorchJaekwon.Model.Diffusion.DDPM.DiffusionUtil import DiffusionUtil
from TorchJaekwon.Model.Diffusion.DDPM.BetaSchedule import BetaSchedule
from TorchJaekwon.Model.Diffusion.DDPM.DDPM import DDPM

class DDPMLossVLB(DDPM):
    def __init__(self, 
                 use_vlb_loss:bool = True,
                 loss_simple_weight:float=1.0,
                 original_elbo_weight:float=0.0,
                 logvar_init:float=0.0,
                 learn_logvar:bool=False,
                 *args, 
                 **kwargs):
        self.use_vlb_loss = use_vlb_loss
        super().__init__(*args, **kwargs)

        self.loss_simple_weight:float = loss_simple_weight
        self.original_elbo_weight:float = original_elbo_weight
        self.logvar:float = torch.full(fill_value=logvar_init, size=(self.timesteps,))
        self.learn_logvar:bool = learn_logvar
        if self.learn_logvar:
            self.logvar = nn.Parameter(self.logvar, requires_grad=True)
        else:
            self.logvar = nn.Parameter(self.logvar, requires_grad=False)
    
    def set_noise_schedule(self,
                           betas: Optional[ndarray] = None, 
                           beta_schedule_type:Literal['linear','cosine'] = 'linear',
                           beta_arg_dict:dict = dict(),
                           timesteps:int = 1000,
                           ) -> None:
        if betas is None:
            beta_arg_dict.update({'timesteps':timesteps})
            betas = getattr(BetaSchedule,beta_schedule_type)(**beta_arg_dict)
        
        alphas:ndarray = 1. - betas
        alphas_cumprod:ndarray = np.cumprod(alphas, axis=0)
        alphas_cumprod_prev:ndarray = np.append(1., alphas_cumprod[:-1])

        self.betas:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'betas', value = betas)
        self.alphas_cumprod:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'alphas_cumprod', value = alphas_cumprod)
        self.alphas_cumprod_prev:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'alphas_cumprod_prev', value = alphas_cumprod_prev)

        # calculations for diffusion q(x_t | x_{t-1}) and others
        self.sqrt_alphas_cumprod:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'sqrt_alphas_cumprod', value = np.sqrt(alphas_cumprod))
        self.sqrt_one_minus_alphas_cumprod:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'sqrt_one_minus_alphas_cumprod', value = np.sqrt(1. - alphas_cumprod))
        self.log_one_minus_alphas_cumprod:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'log_one_minus_alphas_cumprod', value = np.log(1. - alphas_cumprod))
        self.sqrt_recip_alphas_cumprod:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'sqrt_recip_alphas_cumprod', value = np.sqrt(1. / alphas_cumprod))
        self.sqrt_recipm1_alphas_cumprod:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'sqrt_recipm1_alphas_cumprod', value = np.sqrt(1. / alphas_cumprod - 1))

        # calculations for posterior q(x_{t-1} | x_t, x_0)
        posterior_variance = betas * (1. - alphas_cumprod_prev) / (1. - alphas_cumprod)
        # above: equal to 1. / (1. / (1. - alpha_cumprod_tm1) + alpha_t / beta_t)
        self.posterior_variance:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'posterior_variance', value = posterior_variance)
        # below: log calculation clipped because the posterior variance is 0 at the beginning of the diffusion chain
        self.posterior_log_variance_clipped:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'posterior_log_variance_clipped', value = np.log(np.maximum(posterior_variance, 1e-20)))
        self.posterior_mean_coef1:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'posterior_mean_coef1', value = betas * np.sqrt(alphas_cumprod_prev) / (1. - alphas_cumprod))
        self.posterior_mean_coef2:Tensor = UtilTorch.register_buffer(model = self, variable_name = 'posterior_mean_coef2', value = (1. - alphas_cumprod_prev) * np.sqrt(alphas) / (1. - alphas_cumprod))
    
        if self.use_vlb_loss:
            if self.model_output_type == 'noise':
                lvlb_weights = self.betas**2 / (
                    2
                    * self.posterior_variance
                    * torch.tensor(alphas, dtype=torch.float32)
                    * (1 - self.alphas_cumprod)
                )
            elif self.model_output_type == 'x_start':
                lvlb_weights = (
                    0.5
                    * np.sqrt(torch.Tensor(alphas_cumprod))
                    / (2.0 * 1 - torch.Tensor(alphas_cumprod))
                )
            elif self.model_output_type == 'v_prediction':
                lvlb_weights = torch.ones_like(
                    self.betas**2
                    / (
                        2
                        * self.posterior_variance
                        * torch.tensor(alphas, dtype=torch.float32)
                        * (1 - self.alphas_cumprod)
                    )
                )
            else:
                raise NotImplementedError("mu not supported")
            # TODO how to choose this term
            lvlb_weights[0] = lvlb_weights[1]
            self.register_buffer("lvlb_weights", lvlb_weights, persistent=False)
            self.lvlb_weights = self.lvlb_weights
            assert not torch.isnan(self.lvlb_weights).all()

    def p_losses(self, 
                 x_start:Tensor,
                 cond:Optional[Union[dict,Tensor]],
                 is_cond_unpack:bool,
                 t:Tensor, 
                 noise:Optional[Tensor] = None):
        if not self.use_vlb_loss:
            return super().p_losses(x_start, cond, is_cond_unpack, t, noise)
        
        noise:Tensor = UtilData.default(noise, lambda: torch.randn_like(x_start))
        x_noisy:Tensor = self.q_sample(x_start=x_start, t=t, noise=noise)
        model_output:Tensor = self.apply_model(x_noisy, t, cond, is_cond_unpack)

        if self.model_output_type == 'x_start':
            target:Tensor = x_start
        elif self.model_output_type == 'noise':
            target:Tensor = noise
        elif self.model_output_type == 'v_prediction':
            target:Tensor = self.get_v(x_start, noise, t)
        else:
            print(f'''model output type is {self.model_output_type}. It should be in [x_start, noise]''')
            raise NotImplementedError()
        if target.shape != model_output.shape: print(f'warning: target shape({target.shape}) and model shape({model_output.shape}) are different')
        
        loss_dict = dict()
        loss_simple:Tensor = self.get_loss(model_output, target, mean=False)
        loss_simple = loss_simple.mean(dim = list(range(len(loss_simple.shape)))[1:])
        loss_dict.update({f"loss_simple": loss_simple.mean()})

        logvar_t = self.logvar[t]
        loss = loss_simple / torch.exp(logvar_t) + logvar_t
        
        if self.learn_logvar:
            loss_dict.update({f"loss_gamma": loss.mean()})
            loss_dict.update({"logvar": self.logvar.data.mean()})

        loss = self.loss_simple_weight * loss.mean()

        loss_vlb:Tensor = self.get_loss(model_output, target, mean=False)
        loss_vlb = loss_vlb.mean(dim=list(range(len(loss_vlb.shape)))[1:])
        loss_vlb = (self.lvlb_weights[t] * loss_vlb).mean()
        loss_dict.update({f"loss_vlb": loss_vlb})
        loss += self.original_elbo_weight * loss_vlb
        loss_dict.update({f"loss": loss})
        return loss_dict

    def get_loss(self, pred:Tensor, target:Tensor, mean=True) -> Tensor:
        if self.loss_func == 'l1':
            loss = (target - pred).abs()
            if mean:
                loss = loss.mean()
        elif self.loss_func == F.mse_loss:
            if mean:
                loss = self.loss_func(target, pred)
            else:
                loss = self.loss_func(target, pred, reduction='none')
        else:
            raise NotImplementedError("unknown loss type '{loss_type}'")

        return loss


if __name__ == '__main__':
    ddpm = DDPMLossVLB(model = lambda x, t: x, model_output_type = 'v_prediction')
    ddpm.p_losses(x_start = torch.randn(2,3,64,64), cond = None, is_cond_unpack = False, t = torch.tensor([30, 23]))
    print('finish')