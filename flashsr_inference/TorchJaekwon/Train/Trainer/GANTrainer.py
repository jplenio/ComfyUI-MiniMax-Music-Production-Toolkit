
from typing import Union, Literal

import os
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from TorchJaekwon.Util.UtilData import UtilData
from TorchJaekwon.Train.Trainer.Trainer import Trainer, TrainState

from TorchJaekwon.Train.AverageMeter import AverageMeter

class GANTrainer(Trainer):
    def __init__(self, 
                 model_class_name:Union[str, list], # { 'generator': ['generatorname'] , 'discriminator': ['discriminatorname'] }
                 optimizer_class_meta_dict:dict, # { 'generator': {'name': 'AdamW', args: {'lr':1.0e-3}, model_name_list: ['gemeratorname'] } , 'discriminator': ... }
                 discriminator_freeze_step:int = 0, 
                 **kwargs):
        super().__init__(model_class_name=model_class_name, optimizer_class_meta_dict = optimizer_class_meta_dict, **kwargs)
        self.discriminator_freeze_step:int = discriminator_freeze_step
    
    def backprop(self,loss):
        pass

    def lr_scheduler_step(self, call_state:Literal['step','epoch'], args = None):
        pass
    