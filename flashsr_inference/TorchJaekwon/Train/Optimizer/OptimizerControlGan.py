import torch
from torch.optim import Optimizer
from torch.optim.lr_scheduler import _LRScheduler

from Model.ModelGan import ModelGan
from HParams import HParams

class OptimizerControlGan:
    def __init__(self, model:ModelGan = None) -> None:
        self.h_params = HParams()

        self.generator_optimizer:Optimizer = None
        self.discriminator_optimizer:Optimizer = None

        self.generator_lr_scheduler:_LRScheduler = None
        self.discriminator_lr_scheduler:_LRScheduler = None

        self.scheduler_config:dict = self.h_params.train.scheduler
        self.num_gen_lr_scheduler_step:int = 0
        self.num_dis_lr_scheduler_step:int = 0

        if model is not None:
            self.set_optimizer(model)
            self.set_lr_scheduler()

    def set_optimizer(self,model:ModelGan) -> None:
        generator_optimizer_name:str = self.h_params.train.optimizer["generator_name"]

        generator_optimizer_config:dict = self.h_params.train.optimizer["generator_config"]
        generator_optimizer_config["params"] = model.generator.parameters()
        generator_optimizer_config['lr'] = float(generator_optimizer_config['lr'])
        generator_optimizer_config['eps'] = float(generator_optimizer_config['eps'])

        self.generator_optimizer = self.get_optimizer(generator_optimizer_name,generator_optimizer_config)
        
        discriminator_optimizer_name:str = self.h_params.train.optimizer["generator_name"]

        discriminator_optimizer_config:dict = self.h_params.train.optimizer["discriminator_config"]
        discriminator_optimizer_config["params"] = model.discriminator.parameters()
        discriminator_optimizer_config['lr'] = float(discriminator_optimizer_config['lr'])
        discriminator_optimizer_config['eps'] = float(discriminator_optimizer_config['eps'])

        self.discriminator_optimizer =  self.get_optimizer(discriminator_optimizer_name,discriminator_optimizer_config)
    
    def get_optimizer(self,optimizer_name:str, optimizer_config_dict:dict) -> Optimizer:
        if optimizer_name == "Adam":
            return torch.optim.Adam(**optimizer_config_dict)
    
    def optimizer_state_dict(self) -> dict:
        return {"generator": self.generator_optimizer.state_dict(),"discriminator": self.discriminator_optimizer.state_dict()}
    
    def optimizer_load_state_dict(self, state_dict) -> None:
        self.generator_optimizer.load_state_dict(state_dict['generator'])
        self.discriminator_optimizer.load_state_dict(state_dict['discriminator'])
        
    
    def lr_scheduler_state_dict(self) -> dict:
        state_dict_of_lr_scheduler:dict = dict()

        if self.generator_lr_scheduler is not None:
            state_dict_of_lr_scheduler['generator'] = self.generator_lr_scheduler.state_dict()

        if self.discriminator_lr_scheduler is not None:
            state_dict_of_lr_scheduler['discriminator'] = self.discriminator_lr_scheduler.state_dict()
        
        return state_dict_of_lr_scheduler
    
    def lr_scheduler_load_state_dict(self, state_dict:dict) -> None:
        if self.generator_lr_scheduler is not None:
            self.generator_lr_scheduler.load_state_dict(state_dict['generator'])

        if self.discriminator_lr_scheduler is not None:
            self.discriminator_lr_scheduler.load_state_dict(state_dict['discriminator'])
    
    def set_lr_scheduler(self) -> None:
        pass

    def lr_scheduler_step(self,interval_type:str = "step",args = None) -> None:
        self.gen_lr_scheduler_step(interval_type,args)
        self.disc_lr_scheduler_step(interval_type,args)
    
    def gen_lr_scheduler_step(self,interval_type:str = "step",args = None) -> None:
        if ((self.num_gen_lr_scheduler_step) % self.scheduler_config["generator_config"]["frequency"]) != 0:
            return
        if interval_type != self.scheduler_config["generator_config"]["interval"]:
            return
        
        if self.generator_lr_scheduler is not None:
            self.generator_lr_scheduler.step()
        
        self.num_gen_lr_scheduler_step += 1

    def disc_lr_scheduler_step(self,interval_type:str = "step",args = None) -> None:
        if ((self.num_dis_lr_scheduler_step) % self.scheduler_config["discriminator_config"]["frequency"]) != 0:
            return
        if interval_type != self.scheduler_config["discriminator_config"]["interval"]:
            return
        
        if self.discriminator_lr_scheduler is not None:
            self.discriminator_lr_scheduler.step()
        
        self.num_dis_lr_scheduler_step += 1
    
    def get_lr(self) -> float:
        return self.generator_optimizer.param_groups[0]["lr"]

'''
    def __init__(self,model:MelGan,h_params:HParams) -> None:
        self.h_params = h_params
        self.discriminator_optimizer = torch.optim.Adam(
                            model.discriminator.parameters(),
                            lr=h_params.train.lr, 
                            weight_decay=h_params.train.weight_decay
                            )
        self.generator_optimizer = torch.optim.Adam(
                            model.generator.parameters(),
                            lr=h_params.train.lr, 
                            weight_decay=h_params.train.weight_decay
                            )
        
        self.discriminator_state_name = "discriminator"
        self.generator_state_name = "generator"
        self.current_state = self.generator_state_name

        self.lr_scheduler_discriminator = self.get_lr_scheduler(self.discriminator_optimizer)
        
        self.lr_scheduler_generator = self.get_lr_scheduler(self.generator_optimizer)

    def get_lr_scheduler(self,optimizer):
        if self.h_params.train.optimizer_name == "ReduceLROnPlateau":
            return torch.optim.lr_scheduler.ReduceLROnPlateau(
                            optimizer,
                            factor=self.h_params.train.lr_decay_gamma,
                            patience=self.h_params.train.lr_decay_patience,
                            cooldown=10,
                            )
        elif self.h_params.train.optimizer_name == "StepLR":
            return torch.optim.lr_scheduler.StepLR(optimizer, step_size=self.h_params.train.lr_scheduler_step_size, gamma=self.h_params.train.lr_decay_factor)
    
    def zero_grad(self):
        self.discriminator_optimizer.zero_grad()
        self.generator_optimizer.zero_grad()
    
    def step(self):
        if self.current_state == self.discriminator_state_name:
            self.discriminator_optimizer.step()
        elif self.current_state == self.generator_state_name:
            self.generator_optimizer.step()
    
    def state_dict(self):
        return {"generator": self.generator_optimizer.state_dict(),"discriminator": self.discriminator_optimizer.state_dict()}
    
    def load_state_dict(self, state_dict_dict):
        self.generator_optimizer.load_state_dict(state_dict_dict["generator"])
        self.discriminator_optimizer.load_state_dict(state_dict_dict["discriminator"])
    
    def lr_scheduler_step(self,vaild_loss=None):
        if self.h_params.train.optimizer_name == "ReduceLROnPlateau":
            if self.current_state == self.discriminator_state_name:
                self.lr_scheduler_discriminator.step(vaild_loss)
            elif self.current_state == self.generator_state_name:
                self.lr_scheduler_generator.step(vaild_loss)
        elif self.h_params.train.optimizer_name == "StepLR":
            if self.current_state == self.discriminator_state_name:
                self.lr_scheduler_discriminator.step()
            elif self.current_state == self.generator_state_name:
                self.lr_scheduler_generator.step()
'''
