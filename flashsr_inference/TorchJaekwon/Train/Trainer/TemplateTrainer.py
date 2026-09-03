#type
from torch import Tensor
#import
import numpy as np
import torch
import torch.nn as nn
#torchjaekwon import
from TorchJaekwon.Train.Trainer.Trainer import Trainer, TrainState
from TorchJaekwon.Train.AverageMeter import AverageMeter
#internal import

class TemplateTrainer(Trainer):

    def __init__(self):
        super().__init__()
    
    def run_step(self,data,metric,train_state):
        """
        run 1 step
        1. get data
        2. use model
        3. calculate loss
        4. put the loss in metric (append)
        return loss,metric
        """
        data_dict = self.data_dict_to_device(data)
        pred_hr_audio:Tensor = self.model['generator'][self.generator_name](audio1 = data_dict['hr_audio'], audio2 = data_dict['lr_audio'])
        current_loss_dict = dict()
        current_loss_dict['disc_total'], current_loss_dict['disc_mrd'], current_loss_dict['disc_mpd'] = self.discriminator_step(data_dict,pred_hr_audio['hr_audio'],train_state)
        current_loss_dict['gen_total'], current_loss_dict['gen_mel'], current_loss_dict['gen_mpd'], current_loss_dict['gen_mrd'], current_loss_dict['gen_mpd_fm'], current_loss_dict['gen_mrd_fm'] = self.generator_step(data_dict,pred_hr_audio['hr_audio'],train_state)

        for loss_name in current_loss_dict: self.metric_update(metric,loss_name,current_loss_dict[loss_name],batch_size)

        return current_loss_dict["gen_total"],metric
    
    def log_media(self) -> None:
        pass