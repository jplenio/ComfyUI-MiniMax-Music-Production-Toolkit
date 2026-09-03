import torch
import torch.nn as nn

from HParams import HParams

class OptimizerControl:
    def __init__(self, model:nn.Module = None) -> None:
        self.h_params = HParams()
        self.optimizer = None
        self.lr_scheduler = None

        self.scheduler_config = None
        self.num_lr_scheduler_step = 0

        if model is not None:
            self.set_optimizer(model)
            self.set_lr_scheduler()
    
    def set_optimizer(self,model:nn.Module):
        optimizer_name:str = self.h_params.train.optimizer["name"]

        optimizer_config:dict = self.h_params.train.optimizer["config"]
        optimizer_config["params"] = filter(lambda p: p.requires_grad, model.parameters())

        for float_parameter in ['lr','eps']:
            if float_parameter in optimizer_config:
                optimizer_config[float_parameter] = float(optimizer_config[float_parameter])

        optimizer_class = getattr(torch.optim,optimizer_name,None)
        if optimizer_class is not None:
            self.optimizer = optimizer_class(**optimizer_config)
    
    def optimizer_step(self):
        self.optimizer.step()
    
    def optimizer_zero_grad(self):
        self.optimizer.zero_grad()
    
    def optimizer_state_dict(self):
        return self.optimizer.state_dict()
    
    def optimizer_load_state_dict(self, state_dict):
        self.optimizer.load_state_dict(state_dict)
    
    def lr_scheduler_state_dict(self):
        if self.lr_scheduler is not None:
            return self.lr_scheduler.state_dict()
    
    def lr_scheduler_load_state_dict(self, state_dict):
        if self.lr_scheduler is not None:
            self.lr_scheduler.load_state_dict(state_dict)
    
    def set_lr_scheduler(self):
        scheduler_dict:dict= getattr(self.h_params.train,'scheduler',None)
        if scheduler_dict is not None:
            self.scheduler_config = scheduler_dict
            scheduler_parameter_dict = scheduler_dict['config']
            scheduler_parameter_dict['optimizer'] = self.optimizer
            scheduler_class = getattr(torch.optim.lr_scheduler,scheduler_dict['name'],None)
            self.lr_scheduler = scheduler_class(**scheduler_parameter_dict)

    def lr_scheduler_step(self,interval_type="step",args = None):
        if self.lr_scheduler == None or (self.num_lr_scheduler_step % self.scheduler_config["frequency"]) != 0 or interval_type != self.scheduler_config["interval"]:
            return 

        self.lr_scheduler.step()
        self.num_lr_scheduler_step += 1
    
    def get_lr(self):
        return self.optimizer.param_groups[0]["lr"]