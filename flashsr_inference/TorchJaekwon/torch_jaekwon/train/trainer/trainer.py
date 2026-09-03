#type
from typing import Dict, Union, Literal, Type
from enum import Enum,unique
#import
import os
import random
import numpy as np
import torch
import torch.nn as nn
import torch.utils.data.dataset as dataset
from torch.utils.data import DataLoader
from torch.nn.parallel import DistributedDataParallel as DDP
try: from ema_pytorch import EMA
except: print("ema_pytorch is not installed")
#torchjaekwon import
from ...instantiate import instantiate, import_class
from ...util import util, util_data, util_torch, util_torch_distributed
from ..logger.logger import Logger
from ..average_meter import AverageMeter
#internal import

@unique
class TrainState(Enum):
    TRAIN = "train"
    VALIDATE = "valid"
    TEST = "test"
 
class Trainer():
    def __init__(
        self,
        # resource
        device:Union[torch.device, int] = torch.device('cuda' if torch.cuda.is_available() else 'cpu'),
        # data
        data_class_meta_dict:dict = None,
        # model
        model_class_meta_dict:dict = None, #{path: '<module>.<ClassName>', args: {}}
        model_ckpt_path:str = None,
        # loss
        loss_meta_dict:dict = None,
        # optimizer
        optimizer_class_meta_dict:dict = None,        # meta_dict or {key_name: meta_dict} / meta_dict: {'path': 'Adam', 'args': {'lr': 0.0001}, model_name_list: []}
        grad_accum_steps:int = 1,
        lr_scheduler_class_meta_dict:dict = None,
        lr_scheduler_interval:Literal['step','epoch'] = 'step',
        max_grad_norm:float = None,
        use_ema:bool = False,
        # train paremeters
        total_step:int = np.inf,
        total_epoch:int = int(1e20),
        seed:int = None, # None -> derive from the current RNG at __init__ (see below); avoids calling CUDA at import time
        seed_strict:bool = False,
        # logging
        logger:Logger = None,
        save_model_step_interval:int = None,
        save_model_epoch_interval:int = 1,
        log_step_interval:int = 100,
        start_logging_epoch:int = 0,
        # additional
        check_evalstep_first:bool = False,
        debug_mode:bool = False,
        use_torch_compile:bool = True
    ) -> None:
        # resource
        self.device:Union[torch.device, int] = device

        # data
        self.data_loader_dict:dict = self.set_data_loader(data_class_meta_dict)

        # model
        self.model:Union[nn.Module, list, dict] = self.init_model(model_class_meta_dict = model_class_meta_dict, model_ckpt_path=model_ckpt_path, use_torch_compile=use_torch_compile, debug_mode=debug_mode)

        # loss
        self.loss_fn_dict:dict = self.init_loss(loss_meta_dict)

        # optimizer
        self.optimizer:torch.optim.Optimizer = self.init_optimizer(optimizer_class_meta_dict)
        self.grad_accum_steps:int = grad_accum_steps
        self.lr_scheduler_interval:Literal['step','epoch'] = lr_scheduler_interval
        self.lr_scheduler:torch.optim.lr_scheduler = self.init_lr_scheduler(self.optimizer, lr_scheduler_class_meta_dict)
        self.max_grad_norm:float = max_grad_norm
        self.use_ema:bool = use_ema
        self.model_ema:nn.Module = self.get_model_ema() if use_ema else None
        
        # train paremeters
        self.total_step:int = total_step
        self.total_epoch:int = total_epoch
        if seed is None:
            seed = int(torch.cuda.initial_seed() / (2**32)) if torch.cuda.is_available() else int(torch.initial_seed() / (2**32))
        self.seed:int = seed
        self.seed_strict:bool = seed_strict
        self.set_seeds(self.seed, self.seed_strict)
        self.current_epoch:int = 1
        self.global_step:int = 0
        self.local_step:int = 0

        # logging
        self.logger:Logger = logger
        if util_torch_distributed.is_main_process():
            self.logger.init_logger(model=self.model)
        self.save_model_step_interval:int = save_model_step_interval
        self.save_model_epoch_interval:int = save_model_epoch_interval
        self.log_step_interval:int = log_step_interval
        assert log_step_interval % self.grad_accum_steps == 0, "log_step_interval should be multiple of grad_accum_steps"
        self.start_logging_epoch:int = start_logging_epoch

        # additional
        self.check_evalstep_first:bool = check_evalstep_first
        self.debug_mode = debug_mode
        self.use_torch_compile = use_torch_compile
        if debug_mode:
            util.log("debug mode is on", msg_type='warning')
            torch.autograd.set_detect_anomaly(True)
        else:
            util.log("debug mode is off. \n  - [off] torch.autograd.set_detect_anomaly", msg_type='info')
            if self.use_torch_compile: 
                util.log("\n  - [on] torch.compile", msg_type='info')
            else:
                util.log("\n  - [off] torch.compile", msg_type='warning')

        # evaluation
        self.best_valid_metric:dict[str,AverageMeter] = None
        self.best_valid_epoch:int = 0
        
    '''
    ==============================================================
    abstract method start
    ==============================================================
    '''
    
    def run_step(self,data,metric,train_state:TrainState):
        """
        run 1 step
        1. get data
        2. use model
        3. calculate loss
        4. put the loss in metric (append)
            metric = self.update_metric(metric, loss_dict, data.shape[0])
        5. return loss_dict["total_loss"],metric
        """
        raise NotImplementedError

    @torch.no_grad()
    def log_media(self) -> None:
        pass

    '''
    ==============================================================
    abstract method end
    ==============================================================
    '''

    def save_best_model( self, prev_best_metric, current_metric ):
        return None
    
    def update_metric(self, metric:Dict[str,AverageMeter], loss_dict:Dict[str,torch.Tensor], batch_size:int) -> dict:
        for loss_name in loss_dict:
            if loss_name not in metric:
                metric[loss_name] = AverageMeter()
            metric[loss_name].update(loss_dict[loss_name].item(), batch_size)
        return metric
    
    def log_metric(
        self, 
        metrics:Dict[str,AverageMeter],
        data_size: int,
        train_state=TrainState.TRAIN,
        x_axis:Literal['global_step', 'epoch'] = 'global_step'
    ) -> None:
        if not util_torch_distributed.is_main_process(): return None
        """
        log and visualizer log
        """
        if x_axis == 'global_step':
            x_axis_name:str = "global_step"
            x_axis_value:int = self.global_step
        else:
            x_axis_name:str = "epoch"
            x_axis_value:int = self.current_epoch

        log:str = f'Epoch ({train_state.value}): {self.current_epoch:03} ({self.local_step}/{data_size}) global_step: {self.global_step} lr: {self.get_current_lr(self.optimizer)}\n'
        
        for metric_name in metrics:
            if isinstance(metrics[metric_name], AverageMeter):
                val:float = metrics[metric_name].avg
            elif isinstance(metrics[metric_name], (float, int)):
                val:float = metrics[metric_name]
            log += f' {metric_name}: {val:.06f}'
            self.logger.visualizer_log(
                x_axis_name=x_axis_name,
                x_axis_value=x_axis_value,
                y_axis_name=f'{train_state.value}/{metric_name}',
                y_axis_value=val
            )

        self.logger.print_and_log(log)

    def set_seeds(self, seed:float, strict=False) -> None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            if strict:
                torch.backends.cudnn.deterministic = True
        np.random.seed(seed)
        random.seed(seed)
        os.environ["PYTHONHASHSEED"] = str(seed)
    
    def get_model_ema(self) -> nn.Module:
        model_ema = EMA(
            self.model,
            beta=0.9999,
            power=3/4,
            update_every=1,
            update_after_step=1,
            include_online_model=False
        )
        model_ema = model_ema.to(self.device)
        return model_ema
    
    def init_model(self, model_class_meta_dict:dict, model_ckpt_path:str, use_torch_compile:bool, debug_mode:bool) -> Union[nn.Module, list, dict]:
        self.model:Union[nn.Module, list, dict] = self.get_model(model_class_meta_dict, debug_mode=debug_mode, use_torch_compile=use_torch_compile)
        if model_ckpt_path is not None:
            ckpt:dict = torch.load(model_ckpt_path, map_location='cpu')
            self.model = self.load_state_dict(self.model, ckpt, is_model=True)
        self.model_to_device(self.model, device=self.device)
        return self.model

    def get_model(self, model_class_meta_dict:Union[list, dict], debug_mode:bool = False, use_torch_compile:bool = True) -> None:
        model_class_name = model_class_meta_dict.get('path', None)
        if model_class_name is None:
            model = dict()
            for name in model_class_meta_dict:
                model[name] = self.get_model(model_class_meta_dict[name], debug_mode=debug_mode, use_torch_compile=use_torch_compile)
        else:
            model_class = import_class(module_name = model_class_name)
            model:nn.Module = model_class(**model_class_meta_dict['args'])
            if not debug_mode and use_torch_compile:
                model = torch.compile(model)
        return model
    
    def init_optimizer(self, optimizer_class_meta_dict:dict) -> torch.optim.Optimizer:
        if optimizer_class_meta_dict is None: return None
        optimizer_class_name = optimizer_class_meta_dict.get('path',None)
        if optimizer_class_name is None:
            optimizer = dict()
            for key in optimizer_class_meta_dict:
                optimizer[key] = self.init_optimizer(optimizer_class_meta_dict[key])
        else:
            optimizer_class = getattr(torch.optim, optimizer_class_name)
            model_name_list:list = optimizer_class_meta_dict.get('model_name_list', None)
            if model_name_list is None:
                params = self.model.parameters()
            else:
                params = self.get_params(self.model, model_name_list)

            optimizer_args:dict = {"params": params}
            optimizer_args.update(optimizer_class_meta_dict['args'])
            optimizer_args['lr'] = float(optimizer_args['lr'])
            optimizer = optimizer_class(**optimizer_args)
        return optimizer
    
    def get_all_parameters(self, model:Union[nn.Module, dict]) -> list: # collect params across a single model or a (possibly nested) dict of models
        if isinstance(model, dict):
            params = list()
            for sub_model in model.values(): params += self.get_all_parameters(sub_model)
            return params
        return list(model.parameters())

    def get_params(
        self,
        model:dict,
        model_name_list:list
    ) -> dict:
        params = list()
        for model_name in model:
            if isinstance(model[model_name], nn.Module):
                if model_name in model_name_list:
                    params += list(model[model_name].parameters())
            else:
                #model[model_name] is dict
                params += self.get_params(model[model_name], model_name_list)
        return params

    def init_lr_scheduler(self, optimizer, lr_scheduler_class_meta_dict) -> None:
        if lr_scheduler_class_meta_dict is None: return None
        if isinstance(optimizer, dict):
            lr_scheduler = dict()
            for key in optimizer:
                lr_scheduler[key] = self.init_lr_scheduler(optimizer[key], lr_scheduler_class_meta_dict[key])
        else:
            lr_scheduler_name:str = lr_scheduler_class_meta_dict.get('path',None)
            lr_scheduler_class = getattr(torch.optim.lr_scheduler, lr_scheduler_name, None) # torch built-in first (e.g. 'StepLR')
            if lr_scheduler_class is None: # otherwise a custom class named by fully-qualified dotted path
                lr_scheduler_class = import_class(module_name=lr_scheduler_name)
            lr_scheduler_args:dict = {**lr_scheduler_class_meta_dict['args'], 'optimizer': optimizer} # copy so the caller's config dict isn't mutated with a live optimizer
            lr_scheduler = lr_scheduler_class(**lr_scheduler_args)
            if hasattr(lr_scheduler, 'interval') and getattr(lr_scheduler, 'interval', None) != self.lr_scheduler_interval:
                util.log(
                    text = f'lr_scheduler interval ({self.lr_scheduler_interval}) is not same as interval of {lr_scheduler_name} ({lr_scheduler.interval}).', 
                    msg_type='warning'
                )
        return lr_scheduler

    def init_loss(self, loss_meta_dict) -> dict:
        if loss_meta_dict is None: return
        loss_fn_dict = dict()
        for loss_name in loss_meta_dict:
            loss_class_name:str = loss_meta_dict[loss_name]['class_meta']['path']
            loss_args:dict = loss_meta_dict[loss_name]['class_meta']['args']
            loss_class:Type[torch.nn.Module] = getattr(torch.nn, loss_class_name, None) # torch built-in first (e.g. 'L1Loss')
            if loss_class is None: # otherwise a custom class named by fully-qualified dotted path
                loss_class = import_class(module_name=loss_class_name)
            loss_fn_dict[loss_name] = loss_class(**loss_args)
        return loss_fn_dict
    
    def model_to_device(self, model:Union[nn.Module, dict], device = None) -> None:
        if isinstance(model, dict):
            for model_name in model:
                model[model_name] = self.model_to_device(model[model_name], device)
        else:
            model = model.to(device if device is not None else self.device)
        return model

    def data_dict_to_device(self,data_dict:dict) -> dict:
        for feature_name in data_dict:
            if isinstance(data_dict[feature_name],dict):
                data_dict[feature_name] = self.data_dict_to_device(data_dict[feature_name])
            else:
                if data_dict[feature_name].dtype in [torch.int64, torch.int32]:
                    data_dict[feature_name] = data_dict[feature_name].to(self.device)
                else:
                    data_dict[feature_name] = data_dict[feature_name].float().to(self.device)
        return data_dict
    
    def set_data_loader(self, data_class_meta_dict:dict) -> dict:
        data_loader_dict:dict = {state.value: None for state in TrainState}
        for subset_name in data_loader_dict:
            subset_meta_dict:dict = data_class_meta_dict.get(subset_name, None)
            if subset_meta_dict is None: continue
            dataset = instantiate(
                module_name = subset_meta_dict['dataset_class_meta']["path"],
                arg_dict = subset_meta_dict['dataset_class_meta']['args']
            )
            data_loader_args:dict = {'worker_init_fn': getattr(dataset, 'worker_init_fn', None), **subset_meta_dict['args']}
            if 'collater_class_meta' in subset_meta_dict:
                collater_class:type = import_class(
                    module_name = subset_meta_dict['collater_class_meta']["path"]
                )
                collater = collater_class(**subset_meta_dict['collater_class_meta']['args'])
                data_loader_args['collate_fn'] = collater
            data_loader_dict[subset_name] = self.get_data_loader(dataset, data_loader_args, subset_name)
        return data_loader_dict
    
    def get_data_loader(self, dataset:dataset.Dataset, data_loader_args:dict, subset_name:Literal['train','valid','test']) -> DataLoader:
        return DataLoader(dataset=dataset, **data_loader_args)
    
    def fit(self) -> None:
        if self.check_evalstep_first:
            print("check evaluation step first whether there is no error")
            with torch.no_grad():
                valid_metric = self.run_epoch(self.data_loader_dict['valid'],TrainState.VALIDATE, metric_range = "epoch")
                self.log_current_state()
                
        for _ in range(self.current_epoch, self.total_epoch):
            if util_torch_distributed.is_main_process():
                self.logger.print_and_log(f'----------------------- Start epoch : {self.current_epoch} / {self.total_epoch} -----------------------')
                self.logger.print_and_log(f'current best epoch: {self.best_valid_epoch}')
                if self.best_valid_metric is not None:
                    for loss_name in self.best_valid_metric:
                        self.logger.print_and_log(f'{loss_name}: {self.best_valid_metric[loss_name].avg}')
                self.logger.print_and_log(f'-------------------------------------------------------------------------------------------------------')
    
            #Train
            if util_torch_distributed.is_main_process(): self.logger.print_and_log('train_start')
            self.run_epoch(self.data_loader_dict['train'],TrainState.TRAIN, metric_range = "step")

            #Valid
            if util_torch_distributed.is_main_process(): self.logger.print_and_log('valid_start')

            with torch.no_grad():
                valid_metric = self.run_epoch(self.data_loader_dict['valid'],TrainState.VALIDATE, metric_range = "epoch")
                self.lr_scheduler_step(call_state='epoch') #args=valid_metric)
            
            self.best_valid_metric = self.save_best_model(self.best_valid_metric, valid_metric)

            if self.current_epoch > self.start_logging_epoch and self.current_epoch % self.save_model_epoch_interval == 0:
                self.save_module(self.model, name=f"step{self.global_step}_epoch{self.current_epoch}")
                self.log_current_state()
            
            self.current_epoch += 1
            if util_torch_distributed.is_main_process(): self.logger.log_every_epoch(model=self.model)

            if self.global_step >= self.total_step:
                break

        if util_torch_distributed.is_main_process():
            self.logger.print_and_log(f'best_epoch: {self.best_valid_epoch}')
            self.logger.print_and_log('Training complete')
    
    def run_epoch(self, dataloader: DataLoader, train_state:TrainState, metric_range:str = "step") -> dict:
        assert metric_range in ["step","epoch"], "metric range should be 'step' or 'epoch'"

        if train_state == TrainState.TRAIN:
            self.set_model_train_valid_mode(self.model, 'train')
        else:
            self.set_model_train_valid_mode(self.model, 'valid')

        try: dataset_size = len(dataloader)
        except TypeError: dataset_size = len(dataloader.dataset)

        if metric_range == "epoch":
            metric = dict()

        for step,data in enumerate(dataloader):

            if metric_range == "step":
                metric = dict()

            self.local_step = step
            loss, metric = self.run_step(data,metric,train_state)

            if isinstance(loss, torch.Tensor) and torch.isnan(loss).any():
                path = os.path.join(self.logger.log_path["root"],f'nan_loss_data_{self.global_step}.pkl')
                util_data.pickle_save(path,data)
                self.save_module(self.model, name=f"nan_loss_step{self.global_step}")
                self.save_checkpoint(f"nan_loss_step{self.global_step}.pth")
                raise ValueError(f'loss is nan at step {self.global_step}')
        
            if train_state == TrainState.TRAIN:
                loss = self.backprop(loss).detach()
                
                if self.global_step % self.log_step_interval == 0:
                    metric['loss (step)'] = loss.item() * self.grad_accum_steps
                    self.log_metric(metrics=metric,data_size=dataset_size)
                
                if self.save_model_step_interval is not None and self.global_step % self.save_model_step_interval == 0 and not self.global_step == 0:
                    self.save_module(self.model, name=f"step{self.global_step}")
                    self.log_current_state()

                self.global_step += 1
                if self.global_step >= self.total_step:
                    return metric
        
        if train_state == TrainState.VALIDATE or train_state == TrainState.TEST:
            self.log_metric(metrics=metric,data_size=dataset_size,train_state=train_state)
            
        return metric
    
    def log_current_state(self,train_state:TrainState = None, is_log_media:bool = True) -> None:
        if not util_torch_distributed.is_main_process(): return None
        self.logger.print_and_log(f'-------------------------------------------------------------------------------------------------------')
        self.logger.print_and_log(f'save current state')
        self.logger.print_and_log(f'-------------------------------------------------------------------------------------------------------')

        if train_state == TrainState.TRAIN or train_state == None:
            checkpoint_path:str = self.save_checkpoint()
            if checkpoint_path is not None:
                util.cp(checkpoint_path, checkpoint_path.replace(".pth", "_backup.pth"))

        if is_log_media:
            with torch.no_grad():
                self.log_media()

        self.logger.print_and_log(f'-------------------------------------------------------------------------------------------------------')
        self.logger.print_and_log(f'-------------------------------------------------------------------------------------------------------')
    
    def backprop(self, loss: torch.Tensor) -> torch.Tensor:
        loss = loss / self.grad_accum_steps
        loss = self.loss_backward(loss)
        if (self.global_step + 1) % self.grad_accum_steps == 0:
            if self.max_grad_norm is not None:
                grad_norm = torch.nn.utils.clip_grad_norm_(self.get_all_parameters(self.model), self.max_grad_norm)
            optimizer_list:list = list(self.optimizer.values()) if isinstance(self.optimizer, dict) else [self.optimizer] # support a dict of optimizers
            for optimizer in optimizer_list: optimizer.step()
            self.on_before_zero_grad()
            for optimizer in optimizer_list: optimizer.zero_grad()
            self.lr_scheduler_step(call_state='step')
        return loss # for logging
    
    def loss_backward(self, loss: torch.Tensor) -> torch.Tensor:
        loss.backward()
        return loss # for logging
    
    def on_before_zero_grad(self) -> None:
        if self.model_ema is not None:
            self.model_ema.update()
    
    def set_model_train_valid_mode(self, model, mode: Literal['train','valid']):
        if isinstance(model, dict):
            for model_name in model:
                self.set_model_train_valid_mode(model[model_name], mode)
        else:
            if mode == 'train':
                model.train()
            else:
                model.eval()
                model.zero_grad()
    
    def save_module(self, model, model_name = '', name = 'pretrained_best_epoch') -> None:
        if not util_torch_distributed.is_main_process(): return None
        if isinstance(model, dict):
            for model_type in model:
                self.save_module(model[model_type], model_name + f'{model_type}_', name)
        else:
            path = os.path.join(self.logger.log_path["root"],f'{model_name}{name}.pth')
            if self.model_ema is not None:
                state_dict = self.model_ema.ema_model.state_dict()
            else:
                raw_model = model.module if isinstance(model, DDP) else model
                state_dict = raw_model.state_dict()
            torch.save(state_dict, path)
    
    def get_current_lr(self, optimizer:Union[ dict, torch.optim.Optimizer]):
        if isinstance(optimizer, dict):
            return self.get_current_lr(optimizer[list(optimizer.keys())[0]])
        else:
            return optimizer.param_groups[0]['lr']
    
    def lr_scheduler_step(self, call_state:Literal['step','epoch'], kwargs = dict()) -> None:
        if self.lr_scheduler is None or self.lr_scheduler_interval != call_state:
            return
        if isinstance(self.lr_scheduler, dict):
            for key in self.lr_scheduler:
                self.lr_scheduler[key].step(**kwargs)
        else:
            self.lr_scheduler.step(**kwargs)
    
    def save_checkpoint(self, save_name:str = 'train_checkpoint.pth') -> str:
        if not util_torch_distributed.is_main_process(): return None
        train_state = {
            'epoch': self.current_epoch,
            'step': self.global_step,
            'seed': self.seed,
            'model': self.get_state_dict(self.model),
            'optimizers': self.get_state_dict(self.optimizer),
            'best_metric': self.best_valid_metric,
            'best_model_epoch' :  self.best_valid_epoch,
            'rng_state': {
                'torch_cpu': torch.get_rng_state(),
                'torch_cuda': torch.cuda.get_rng_state() if torch.cuda.is_available() else None,
                'numpy': np.random.get_state(),
                'python': random.getstate(),
            },
        }

        if self.lr_scheduler is not None:
            train_state['lr_scheduler'] = self.get_state_dict(self.lr_scheduler)
        
        if self.use_ema:
            train_state['model_ema'] = self.get_state_dict(self.model_ema)

        path = os.path.join(self.logger.log_path["root"],save_name)
        self.logger.print_and_log(save_name)
        torch.save(train_state,path)
        return path
    
    def get_state_dict(self, module:Union[dict, nn.Module]) -> Union[dict, nn.Module]:
        if isinstance(module, DDP):
            return module.module.state_dict()
        elif hasattr(module, 'state_dict'):
            return module.state_dict()
        elif isinstance(module, dict):
            state_dict = dict()
            for key in module:
                state_dict[key] = self.get_state_dict(module[key])
            return state_dict
        else:
            raise ValueError(f'Cannot get state_dict from {module}')
    
    def load_state_dict(self, module:Union[dict, nn.Module], state_dict:dict, is_model:bool = False) -> Union[dict, nn.Module]:
        if isinstance(module, DDP):
            module.module = util_torch.load_model(module.module, state_dict)
            return module
        elif hasattr(module, 'load_state_dict'):
            if is_model:
                module = util_torch.load_model(module, state_dict)
            else:
                module.load_state_dict(state_dict)
            return module
        elif isinstance(module, dict):
            for key in module:
                module[key] = self.load_state_dict(module[key], state_dict[key], is_model)
            return module
        else:
            raise ValueError(f'Cannot load state_dict to {module}')

    def set_rng_state(self, rng_state:dict) -> None:
        torch.set_rng_state(rng_state['torch_cpu'])
        if rng_state['torch_cuda'] is not None and torch.cuda.is_available():
            torch.cuda.set_rng_state(rng_state['torch_cuda'])
        np.random.set_state(rng_state['numpy'])
        random.setstate(rng_state['python'])

    def load_train(self, filename:str, map_location:str = 'cpu') -> None:
        self.logger.print_and_log(f'load train from {filename}')
        cpt:dict = torch.load(filename,map_location=map_location)
        self.seed = cpt['seed']
        self.set_seeds(self.seed, self.seed_strict)
        if 'rng_state' in cpt: # continue the RNG stream from the checkpoint instead of resetting to the base seed
            self.set_rng_state(cpt['rng_state'])
        self.current_epoch = cpt['epoch']
        self.global_step = cpt['step'] + 1

        if map_location == 'cpu':
            self.model_to_device(self.model, torch.device('cpu'))
        self.model = self.load_state_dict(self.model, cpt['model'], is_model=True)  
        if map_location == 'cpu':
            self.model_to_device(self.model)
        if self.use_ema:
            self.model_ema = self.load_state_dict(self.model_ema, cpt['model_ema'])
            if map_location == 'cpu':
                self.model_to_device(self.model_ema)

        self.optimizer = self.load_state_dict(self.optimizer, cpt['optimizers'])
        if self.lr_scheduler is not None:
            self.lr_scheduler = self.load_state_dict(self.lr_scheduler, cpt['lr_scheduler'])
        self.best_valid_metric = cpt['best_metric']
        self.best_valid_epoch = cpt['best_model_epoch']