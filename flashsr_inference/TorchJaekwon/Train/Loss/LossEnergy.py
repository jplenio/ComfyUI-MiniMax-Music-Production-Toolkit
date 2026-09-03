import torch.nn as nn
import torch

class LossEnergy(nn.Module):
    def __init__(self) -> None:
        super(LossEnergy,self).__init__()
        self.l1_loss:nn.Module = nn.L1Loss()
    
    def forward(self, gt_mel:torch.Tensor, pred_mel:torch.Tensor) -> torch.Tensor:
        square_gt_mel:torch.Tensor = gt_mel * gt_mel
        square_pred_mel:torch.Tensor = pred_mel * pred_mel
        energy_gt_mel:torch.Tensor = torch.sum(square_gt_mel,axis=2)
        energy_pred_mel:torch.Tensor = torch.sum(square_pred_mel,axis=2)
        loss:torch.Tensor = self.l1_loss(energy_gt_mel, energy_pred_mel)
        return loss
        