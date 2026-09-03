from torch import Tensor

import torch
import torch.nn as nn
import torch.nn.functional as F

class ConditionalLayerNormalization(nn.Module):
    def __init__(self,
                 input_channels:int,
                 style_condition_channels:int) -> None:
        super().__init__()
        self.gain_bias_conv1d = nn.Conv1d(style_condition_channels, input_channels * 2, 1)
    
    def forward(self,
                input:Tensor, #[batch,input_channels,N]
                style_condition:Tensor #[batch,style_condition_channels,N]
                ):
        normalized_input:Tensor = F.layer_norm(input,normalized_shape=input.shape[1:])
        weight, bias = self.gain_bias_conv1d(style_condition).chunk(2, dim=1)
        return normalized_input * weight + bias