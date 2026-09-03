from torch import Tensor

import math
import torch
import torch.nn as nn

class FourierFeatures(nn.Module):
    def __init__(
        self, 
        in_features:int = 1, # dimention of time is mostly 1
        out_features:int = 256, 
        std:float = 1.
    ) -> None:
        
        super().__init__()
        assert out_features % 2 == 0
        self.weight = nn.Parameter(
            torch.randn( [out_features // 2, in_features] ) * std
        )

    def forward(
        self, 
        input:Tensor # time [0, 1]
    ) -> Tensor:
        f = 2 * math.pi * input @ self.weight.T
        return torch.cat([f.cos(), f.sin()], dim=-1)