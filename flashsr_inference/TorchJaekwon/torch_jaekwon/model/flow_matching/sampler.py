'''
Source: https://github.com/Stability-AI/stable-audio-tools
'''
from typing import Literal
import torch
from tqdm import tqdm, trange

import math

def time_sampler(type:str = 'linear', sigma_max:float = 1, steps:int = 50):
    if type == 'linear':
        t = torch.linspace(sigma_max, 0, steps + 1)
    elif type == 'linear_quadratic':
        #Movie Gen: A Cast of Media Foundation Models
        linear_ref_steps:int = 1000
        linear_steps:int = steps // 2
        quadratic_steps:int = steps - linear_steps
        t_ref = torch.linspace(sigma_max, 0.0, linear_ref_steps + 1)
        t_linear = t_ref[:linear_steps + 1] 
        s = torch.linspace(1, quadratic_steps, quadratic_steps) / quadratic_steps
        t_quadratic = t_linear[-1] * (1 - s**2)     
        t = torch.cat([t_linear, t_quadratic])
    else:
        raise ValueError(f"Unknown time sampler type: {type}")
    return t
class Sampler:
    @staticmethod
    @torch.no_grad()
    def discrete_euler(model, x, steps, sigma_max=1, time_sampler_type: Literal['linear', 'linear_quadratic'] = 'linear', callback=None, dist_shift=None, **extra_args):
        """Draws samples from a model given starting noise. Euler method"""

        # Make tensor of ones to broadcast the single t values
        ts = x.new_ones([x.shape[0]])

        # Create the noise schedule
        t = time_sampler(type=time_sampler_type, sigma_max=sigma_max, steps=steps)

        if dist_shift is not None:
            t = dist_shift.time_shift(t, x.shape[-1])

        #alphas, sigmas = 1-t, t

        for i, (t_curr, t_prev) in enumerate(tqdm(zip(t[:-1], t[1:]))):
            # Broadcast the current timestep to the correct shape
            t_curr_tensor = t_curr * torch.ones(
                (x.shape[0],), dtype=x.dtype, device=x.device
            )
            dt = t_prev - t_curr  # we solve backwards in our formulation
            v = model(x, t_curr_tensor, **extra_args)
            x = x + dt * v

            if callback is not None:
                denoised = x - t_prev * v
                callback({'x': x, 't': t_curr, 'sigma': t_curr, 'i': i+1, 'denoised': denoised })

        # If we are on the last timestep, output the denoised data
        return x

    @staticmethod
    @torch.no_grad()
    def rk4(model, x, steps, sigma_max=1, callback=None, dist_shift=None, **extra_args):
        """Draws samples from a model given starting noise. 4th-order Runge-Kutta"""

        # Make tensor of ones to broadcast the single t values
        ts = x.new_ones([x.shape[0]])

        # Create the noise schedule
        t = torch.linspace(sigma_max, 0, steps + 1)

        if dist_shift is not None:
            t = dist_shift.time_shift(t, x.shape[-1])

        #alphas, sigmas = 1-t, t

        for i, (t_curr, t_prev) in enumerate(tqdm(zip(t[:-1], t[1:]))):
            # Broadcast the current timestep to the correct shape
            t_curr_tensor = t_curr * ts
            dt = t_prev - t_curr  # we solve backwards in our formulation
            
            k1 = model(x, t_curr_tensor, **extra_args)
            k2 = model(x + dt / 2 * k1, (t_curr + dt / 2) * ts, **extra_args)
            k3 = model(x + dt / 2 * k2, (t_curr + dt / 2) * ts, **extra_args)
            k4 = model(x + dt * k3, t_prev * ts, **extra_args)
            
            x = x + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)

            if callback is not None:
                denoised = x - t_prev * k4
                callback({'x': x, 't': t_curr, 'sigma': t_curr, 'i': i+1, 'denoised': denoised })

        # If we are on the last timestep, output the denoised data
        return x

    @staticmethod
    @torch.no_grad()
    def flow_dpmpp(model, x, steps, sigma_max=1, callback=None, dist_shift=None, **extra_args):
        """Draws samples from a model given starting noise. DPM-Solver++ for RF models"""

        # Make tensor of ones to broadcast the single t values
        ts = x.new_ones([x.shape[0]])

        # Create the noise schedule
        t = torch.linspace(sigma_max, 0, steps + 1)

        if dist_shift is not None:
            t = dist_shift.time_shift(t, x.shape[-1])

        old_denoised = None

        log_snr = lambda t: ((1-t) / t).log()

        for i in trange(len(t) - 1, disable=False):
            denoised = x - t[i] * model(x, t[i] * ts, **extra_args)
            if callback is not None:
                callback({'x': x, 'i': i, 'sigma': t[i], 'sigma_hat': t[i], 'denoised': denoised})
            t_curr, t_next = t[i], t[i + 1]
            alpha_t = 1-t_next
            h = log_snr(t_next) - log_snr(t_curr)
            if old_denoised is None or t_next == 0:
                x = (t_next / t_curr) * x - alpha_t * (-h).expm1() * denoised
            else:
                h_last = log_snr(t_curr) - log_snr(t[i - 1])
                r = h_last / h
                denoised_d = (1 + 1 / (2 * r)) * denoised - (1 / (2 * r)) * old_denoised
                x = (t_next / t_curr) * x - alpha_t * (-h).expm1() * denoised_d
            old_denoised = denoised
        return x

class DistributionShift:
    def __init__(self, base_shift=0.5, max_shift=1.15, max_length=4096, min_length=256, use_sine=False):
        self.base_shift = base_shift
        self.max_shift = max_shift
        self.max_length = max_length
        self.min_length = min_length
        self.use_sine = use_sine
    
    def time_shift(self, t: torch.Tensor, seq_len: int):
        sigma = 1.0
        mu = - (self.base_shift + (self.max_shift - self.base_shift) * (seq_len - self.min_length) / (self.max_length - self.min_length))
        t_out = 1 - math.exp(mu) / (math.exp(mu) + (1 / (1 - t) - 1) ** sigma)

        if self.use_sine:
            t_out = torch.sin(t_out * math.pi / 2)

        return t_out