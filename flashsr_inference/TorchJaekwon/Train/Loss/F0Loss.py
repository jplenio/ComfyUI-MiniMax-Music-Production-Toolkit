import torch.nn as nn
import torch

class F0Loss(nn.Module):
    def __init__(self):
        super(F0Loss,self).__init__()
        self.l1_loss = nn.L1Loss()
    
    def forward(self, pred_f0_not_pitch_dict:dict, gt_f0):
        pred_pitch = (1-pred_f0_not_pitch_dict["not_pitch"])
        weighted_gt_f0 = torch.mul(gt_f0, pred_pitch)
        weighted_pred_f0 = torch.mul(pred_f0_not_pitch_dict["f0"], pred_pitch)
        loss = self.l1_loss(weighted_pred_f0, weighted_gt_f0)
        return loss
        