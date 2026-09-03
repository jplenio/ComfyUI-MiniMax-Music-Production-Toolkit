from torch import Tensor

import torch.nn as nn
from torch.nn import functional as F

from ....util import UtilAudioMelSpec

class MelSpectrogramLoss(nn.Module):
    def __init__(
        self, 
        sampling_rate:int = 44100,
        nfft:int = 2048,
        hop_size:int = 512,
        mel_size:int = 128,
        frequency_min:int = 0,
        frequency_max:int = None
    ) -> None:
        super().__init__()
        self.mel_spec_util = UtilAudioMelSpec(
            nfft = nfft, 
            hop_size = hop_size, 
            sample_rate = sampling_rate, 
            mel_size = mel_size, 
            frequency_min = frequency_min, 
            frequency_max = frequency_max
        )
    
    def forward(
        self, 
        pred:Tensor, 
        target:Tensor
    ) -> Tensor:
        target_mel = self.mel_spec_util.get_hifigan_mel_spec(target)
        pred_mel = self.mel_spec_util.get_hifigan_mel_spec(pred)
        return F.l1_loss(target_mel, pred_mel)