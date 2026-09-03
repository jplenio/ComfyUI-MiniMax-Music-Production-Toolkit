'''
2021_ICML_Improved denoising diffusion probabilistic models
Code Reference: https://github.com/facebookresearch/DiT
'''
#type
from typing import Optional, Union, Dict
from torch import Tensor
#package
import torch
import numpy as np
#torchjaekwon
from TorchJaekwon.Model.Diffusion.DDPM.DiffusionUtil import DiffusionUtil
from TorchJaekwon.Util.UtilTorch import UtilTorch
from TorchJaekwon.Util.UtilData import UtilData
from TorchJaekwon.Model.Diffusion.DDPM.DDPM import DDPM

class DDPMLearningVariances(DDPM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    @torch.no_grad()
    def p_sample(self,
                 x:Tensor, 
                 t:Tensor, 
                 cond:Optional[Union[dict,Tensor]],
                 is_cond_unpack:bool,
                 clip_denoised:bool = True,
                 repeat_noise:bool = False):
        b, *_, device = *x.shape, x.device
        out = self.p_mean_variance(
            x = x,
            t = t,
            cond = cond, 
            is_cond_unpack = is_cond_unpack,
            clip_denoised=clip_denoised,
            cfg_scale=self.cfg_scale
            
        )
        noise = DiffusionUtil.noise_like(x.shape, device, repeat_noise)
        # no noise when t == 0
        nonzero_mask = (1 - (t == 0).float()).reshape(b, *((1,) * (len(x.shape) - 1)))

        return out["pred_mean"] + nonzero_mask * torch.exp(0.5 * out["pred_log_variance"]) * noise
    
    def p_losses(self, 
                 x_start:Tensor,
                 cond:Optional[Union[dict,Tensor]],
                 is_cond_unpack:bool,
                 t:Tensor, 
                 noise:Optional[Tensor] = None):
        noise:Tensor = UtilData.default(noise, lambda: torch.randn_like(x_start))
        x_noisy:Tensor = self.q_sample(x_start=x_start, t=t, noise=noise)
        model_output:Tensor = self.apply_model(x_noisy, t, cond, is_cond_unpack)

        batch_size, channel_size = x_noisy.shape[:2]
        assert model_output.shape == (batch_size, channel_size * 2, *x_noisy.shape[2:]), 'Model output size is expected to be (batch_size, channel_size * 2, ...), because it also predicts variance.'
        model_output, model_var_values = torch.split(model_output, channel_size, dim=1)
        # Learn the variance using the variational bound, but don't let it affect our mean prediction.
        mean_frozen_output = torch.cat([model_output.detach(), model_var_values], dim=1)
        

        vlb_loss = self.vb_terms_bpd(x_start=x_start,
                                     x_t=x_noisy,
                                     t=t,
                                     cond=cond,
                                     is_cond_unpack=is_cond_unpack,
                                     model_output=mean_frozen_output,
                                     clip_denoised=False,
                                     )["output"]

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

        return (self.loss_func(target, model_output) + vlb_loss).mean()
    
    def vb_terms_bpd(self,
                     x_start, 
                     x_t, 
                     t,
                     cond:Optional[Union[dict,Tensor]],
                     is_cond_unpack:bool,
                     model_output:Optional[Tensor] = None,
                     clip_denoised=True, 
                    ):
        """
        Get a term for the variational lower-bound. 
        bits per dimension (bpd).
        The resulting units are bits (rather than nats, as one might expect).
        This allows for comparison to other papers.
        :return: a dict with the following keys:
                 - 'output': a shape [N] tensor of NLLs or KLs.
                 - 'pred_xstart': the x_0 predictions.
        """
        true_mean, _, true_log_variance_clipped = self.q_posterior( x_start=x_start, x_t=x_t, t=t )
        out = self.p_mean_variance(
            x = x_t, 
            t = t, 
            cond = cond,
            is_cond_unpack=is_cond_unpack,
            model_output = model_output,
            clip_denoised=clip_denoised, 
        )
        kl = UtilTorch.kl_div_gaussian( true_mean, true_log_variance_clipped, out["pred_mean"], out["pred_log_variance"])
        kl = UtilTorch.mean_flat(kl) / np.log(2.0)

        decoder_nll = -DiffusionUtil.discretized_gaussian_log_likelihood(
            x_start, means=out["pred_mean"], log_scales=0.5 * out["pred_log_variance"]
        )
        assert decoder_nll.shape == x_start.shape
        decoder_nll = UtilTorch.mean_flat(decoder_nll) / np.log(2.0)

        # At the first timestep return the decoder NLL,
        # otherwise return KL(q(x_{t-1}|x_t,x_0) || p(x_{t-1}|x_t))
        output = torch.where((t == 0), decoder_nll, kl)
        return {"output": output, "pred_x_start": out["pred_x_start"]}
    
    def p_mean_variance(self,
                        x:Tensor,
                        t:Tensor,
                        cond:Optional[Union[dict,Tensor]],
                        is_cond_unpack:bool,
                        model_output:Optional[Tensor] = None,
                        denoised_fn:callable = None,
                        clip_denoised: bool = True, 
                        cfg_scale = None
                        ) -> Dict[str,Tensor]:
        B, C = x.shape[:2]
        assert t.shape == (B,)
        if model_output is None: model_output:Tensor = self.apply_model(x, t, cond, is_cond_unpack, cfg_scale)

        assert model_output.shape == (B, C * 2, *x.shape[2:])

        #model learn variance
        model_output, model_var_values = torch.split(model_output, C, dim=1)
        min_log = DiffusionUtil.extract(self.posterior_log_variance_clipped, t, x.shape)
        max_log = DiffusionUtil.extract(torch.log(self.betas), t, x.shape)
        # The model_var_values is [-1, 1] for [min_var, max_var].
        frac = (model_var_values + 1) / 2
        model_log_variance = frac * max_log + (1 - frac) * min_log
        model_variance = torch.exp(model_log_variance)

        if self.model_output_type == "noise":
            x_recon = self.predict_start_from_noise(x, t=t, noise=model_output)
        elif self.model_output_type == 'x_start':
            x_recon = model_output

        if denoised_fn is not None:
            x = denoised_fn(x)
        if clip_denoised:
            x_recon.clamp_(-1., 1.)

        model_mean, _, _ = self.q_posterior(x_start=x_recon, x_t=x, t=t)
        assert model_mean.shape == model_log_variance.shape == x_recon.shape == x.shape
        return {
            "pred_mean": model_mean,
            "pred_variance": model_variance,
            "pred_log_variance": model_log_variance,
            "pred_x_start": x_recon,
        }
    
    def apply_model(self,
                    x:Tensor,
                    t:Tensor,
                    cond:Optional[Union[dict,Tensor]],
                    is_cond_unpack:bool,
                    cfg_scale:Optional[float] = None
                    ) -> Tensor:
        if cfg_scale is None or cfg_scale == 1.0:
            if cond is None:
                return self.model(x, t)
            elif is_cond_unpack:
                return self.model(x, t, **cond)
            else:
                return self.model(x, t, cond)
        else:
            unconditional_conditioning = self.get_unconditional_condition(cond=cond)
            cond_and_uncond = torch.cat([cond, unconditional_conditioning], dim=0)
            x_for_cond_and_uncond = torch.cat([x, x], dim=0)
            model_output = self.model(x_for_cond_and_uncond, t, **cond_and_uncond) if is_cond_unpack else self.model(x_for_cond_and_uncond, t, cond_and_uncond)
            
            eps, var = torch.split(model_output, model_output.shape[1] // 2, dim=1)
            cond_eps, uncond_eps = torch.split(eps, len(eps) // 2, dim=0)
            cond_var, _ = torch.split(var, len(var) // 2, dim=0)

            cfg_eps = uncond_eps + cfg_scale * (cond_eps - uncond_eps)
            return torch.cat([cfg_eps, cond_var], dim=1)
