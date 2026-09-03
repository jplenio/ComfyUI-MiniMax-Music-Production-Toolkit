#type
from torch import Tensor

import torch.nn as nn

from TorchJaekwon.Model.AudioModule.Package.nnAudio.cqt import CQT2010v2

class ConstantQTransform(nn.Module):
    def __init__(self,
                 sample_rate:int = 22050,
                 hop_length:int = 512,
                 fmin:float = 32.7, #C1 ~= 32.70 Hz, fmax = 2 ** (number_of_freq_bins / bins_per_octave) * fmin
                 number_of_freq_bins:int = 84, #starting at fmin
                 bins_per_octave:int = 12
                 ) -> None:
        super().__init__()
        self.cqt = CQT2010v2(
            sr = sample_rate,
            hop_length = hop_length,
            fmin = fmin,
            n_bins = number_of_freq_bins,
            bins_per_octave=bins_per_octave,
            trainable=False,
            output_format='Magnitude')
    
    def forward(self, 
                inputs:Tensor #[torch.float32; [B, T]], input speech signal.
                ) -> Tensor: #[torch.float32; [B, bins, T / strides]], CQT magnitudes.
        
        return self.cqt(inputs[:, None])