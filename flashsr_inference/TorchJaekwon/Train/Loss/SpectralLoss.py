import torch
import torch.nn as nn
from HParams import HParams

class SpectralLoss(nn.Module):
    def __init__(self):
        super(SpectralLoss,self).__init__()
        self.l1_loss = nn.L1Loss()
        self.weight = torch.linspace(1,0.7,60).unsqueeze(-1)
    
    def forward(self,gt_spectral,pred_spectral):
        if self.weight.device != gt_spectral.device:
            self.weight = self.weight.to(gt_spectral.device)
        weighted_gt_spectral = torch.mul(gt_spectral, self.weight)
        weighted_pred_spectral = torch.mul(pred_spectral, self.weight)
        loss = self.l1_loss(weighted_pred_spectral, weighted_gt_spectral)
        return loss