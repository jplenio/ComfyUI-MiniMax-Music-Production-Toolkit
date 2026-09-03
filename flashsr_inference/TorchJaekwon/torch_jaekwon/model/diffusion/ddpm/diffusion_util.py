from torch import Tensor,device

import torch
import numpy as np

class DiffusionUtil:
    @staticmethod
    def extract(array:Tensor, t, x_shape):
        batch_size, *_ = t.shape
        out = array.gather(dim = -1, index = t).contiguous()
        return out.reshape(batch_size, *((1,) * (len(x_shape) - 1))).contiguous()

    @staticmethod
    def noise_like(shape:tuple, device:device, repeat:bool = False):
        repeat_noise = lambda: torch.randn((1, *shape[1:]), device=device).repeat(shape[0], *((1,) * (len(shape) - 1)))
        noise = lambda: torch.randn(shape, device=device)
        return repeat_noise() if repeat else noise()
    
    @staticmethod
    def discretized_gaussian_log_likelihood(x, means, log_scales):
        """
        Compute the log-likelihood of a Gaussian distribution discretizing to a
        given image.
        :param x: the target images. It is assumed that this was uint8 values,
                rescaled to the range [-1, 1].
        :param means: the Gaussian mean Tensor.
        :param log_scales: the Gaussian log stddev Tensor.
        :return: a tensor like x of log probabilities (in nats).
        """
        assert x.shape == means.shape == log_scales.shape
        centered_x = x - means
        inv_stdv = torch.exp(-log_scales)
        plus_in = inv_stdv * (centered_x + 1.0 / 255.0)
        cdf_plus = DiffusionUtil.approx_standard_normal_cdf(plus_in)
        min_in = inv_stdv * (centered_x - 1.0 / 255.0)
        cdf_min = DiffusionUtil.approx_standard_normal_cdf(min_in)
        log_cdf_plus = torch.log(cdf_plus.clamp(min=1e-12))
        log_one_minus_cdf_min = torch.log((1.0 - cdf_min).clamp(min=1e-12))
        cdf_delta = cdf_plus - cdf_min
        log_probs = torch.where(
            x < -0.999,
            log_cdf_plus,
            torch.where(x > 0.999, log_one_minus_cdf_min, torch.log(cdf_delta.clamp(min=1e-12))),
        )
        assert log_probs.shape == x.shape
        return log_probs
    
    @staticmethod
    def approx_standard_normal_cdf(x):
        """
        A fast approximation of the cumulative distribution function of the
        standard normal.
        """
        return 0.5 * (1.0 + torch.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * torch.pow(x, 3))))
