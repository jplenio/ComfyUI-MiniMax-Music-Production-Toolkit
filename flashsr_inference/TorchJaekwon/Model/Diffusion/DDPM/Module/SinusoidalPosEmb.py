import math

import torch
import torch.nn as nn

class SinusoidalPosEmb(nn.Module):
    def __init__(self, dim:int = 256):
        super().__init__()
        self.dim:int = dim

    def forward(self, diffusion_step: torch.Tensor) -> torch.Tensor:
        device = diffusion_step.device
        half_dim = self.dim // 2
        emb = math.log(10000) / (half_dim - 1)
        emb = torch.exp(torch.arange(half_dim, device=device) * -emb)
        emb = diffusion_step[:, None] * emb[None, :]
        emb = torch.cat((emb.sin(), emb.cos()), dim=-1)
        return emb