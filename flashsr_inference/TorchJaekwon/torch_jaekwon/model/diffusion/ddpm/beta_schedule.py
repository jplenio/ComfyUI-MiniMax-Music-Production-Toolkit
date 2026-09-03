from numpy import ndarray
from torch import Tensor

import numpy as np

class BetaSchedule:

    @staticmethod
    def linear(timesteps:int, start:float=1e-4, end:float =2e-2) -> ndarray:
        """
        linear schedule
        """
        return np.linspace(start, end, timesteps)
        

    @staticmethod
    def cosine(timesteps:int, s:float=0.008) -> ndarray:
        """
        cosine schedule
        as proposed in https://openreview.net/forum?id=-NEXDKk8gZ
        """
        steps:int = timesteps + 1
        x = np.linspace(0, steps, steps)
        alphas_cumprod = np.cos(((x / steps) + s) / (1 + s) * np.pi * 0.5) ** 2
        alphas_cumprod = alphas_cumprod / alphas_cumprod[0]
        betas:ndarray = 1 - (alphas_cumprod[1:] / alphas_cumprod[:-1])
        return np.clip(betas, a_min=0, a_max=0.999)
