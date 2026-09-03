import torch.nn as nn

from Train.Loss.LossFunction.SingleScaleSpectralLoss import SingleScaleSpectralLoss

class MultiScaleSpectralLoss(nn.Module):

    def __init__(
        self,
        n_ffts: list = [2048, 1024, 512, 256],
        alpha=1.0,
        overlap=0.75,
        eps=1e-7):
        super().__init__()

        self.losses = nn.ModuleList([SingleScaleSpectralLoss(n_fft, alpha, overlap, eps) for n_fft in n_ffts])

    
    def forward(self, x_pred, x_true):

        # cut reverbation off
        x_pred = x_pred[..., : x_true.shape[-1]]

        losses = [loss(x_pred, x_true) for loss in self.losses]

        return sum(losses).sum()