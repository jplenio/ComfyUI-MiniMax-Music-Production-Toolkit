from typing import Callable

import torch
import math

class Filter:
    @staticmethod
    def sinc(x: torch.Tensor):
        # This code is adopted from adefossez's julius.core.sinc under the MIT License
        # https://adefossez.github.io/julius/julius/core.html
        #   LICENSE is in incl_licenses directory.
        """
        Implementation of sinc, i.e. sin(pi * x) / (pi * x)
        __Warning__: Different to julius.sinc, the input is multiplied by `pi`!
        """
        return torch.where(x == 0,
                           torch.tensor(1., device=x.device, dtype=x.dtype),
                           torch.sin(math.pi * x) / math.pi / x)
    @staticmethod
    def kaiser_sinc_filter1d(cutoff, half_width, kernel_size): # return filter [1,1,kernel_size]
        even = (kernel_size % 2 == 0)
        half_size = kernel_size // 2

        #For kaiser window
        delta_f = 4 * half_width
        A = 2.285 * (half_size - 1) * math.pi * delta_f + 7.95
        if A > 50.:
            beta = 0.1102 * (A - 8.7)
        elif A >= 21.:
            beta = 0.5842 * (A - 21)**0.4 + 0.07886 * (A - 21.)
        else:
            beta = 0.
        window = torch.kaiser_window(kernel_size, beta=beta, periodic=False)

        # ratio = 0.5/cutoff -> 2 * cutoff = 1 / ratio
        if even:
            time = (torch.arange(-half_size, half_size) + 0.5)
        else:
            time = torch.arange(kernel_size) - half_size
        if cutoff == 0:
            filter_ = torch.zeros_like(time)
        else:
            sinc:Callable = torch.sinc if 'sinc' in dir(torch) else Filter.sinc
            filter_ = 2 * cutoff * window * sinc(2 * cutoff * time)
            # Normalize filter to have sum = 1, otherwise we will have a small leakage
            # of the constant component in the input signal.
            filter_ /= filter_.sum()
            filter = filter_.view(1, 1, kernel_size)

        return filter