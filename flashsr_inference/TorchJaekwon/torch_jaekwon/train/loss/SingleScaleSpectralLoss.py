import torch.nn as nn
from torchaudio.transforms import Spectrogram
import torch.nn.functional as F

class SingleScaleSpectralLoss(nn.Module):
    def __init__(self, n_fft, alpha=1.0, overlap=0.75, eps=1e-7):
        super(SingleScaleSpectralLoss,self).__init__()
        self.n_fft = n_fft
        self.alpha = alpha
        self.eps = eps
        self.hop_length = int(n_fft * (1 - overlap))  # 25% of the length
        self.spec = Spectrogram(n_fft=self.n_fft, hop_length=self.hop_length)

    def forward(self, x_pred, x_true):
        #spec = Spectrogram(n_fft=self.n_fft, hop_length=self.hop_length)
        #spec.to(x_pred.device)
        
        S_true = self.spec(x_true)
        S_pred = self.spec(x_pred)

        linear_term = F.l1_loss(S_pred, S_true)
        log_term = F.l1_loss((S_true + self.eps).log2(), (S_pred + self.eps).log2())

        loss = linear_term + self.alpha * log_term
        return loss