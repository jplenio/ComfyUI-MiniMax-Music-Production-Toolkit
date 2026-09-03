import torch
from torch.optim import Optimizer
from torch.optim import lr_scheduler

class LinearWarmupScheduler(lr_scheduler.SequentialLR):
    def __init__(
        self, 
        optimizer: Optimizer, 
        warmup_steps:int,
        scheduler_name:str,
        scheduler_arg_dict:dict,
        last_epoch: int = -1,
    ) -> None:
        warmup_lambda = lambda current_step: (current_step + 1) / (warmup_steps + 1)
        warmup_scheduler = lr_scheduler.LambdaLR(optimizer, lr_lambda=warmup_lambda)
        scheduler_class = getattr(lr_scheduler, scheduler_name, None)
        scheduler = scheduler_class(optimizer, **scheduler_arg_dict)

        super().__init__(
            optimizer=optimizer,
            schedulers=[warmup_scheduler, scheduler],
            milestones=[warmup_steps],
            last_epoch=last_epoch,
        )