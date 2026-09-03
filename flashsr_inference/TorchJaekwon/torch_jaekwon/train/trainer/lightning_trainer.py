#type
from typing import Union
#package
import os
import torch
import torch.nn as nn
#torchjaekwon import
from .trainer import Trainer, TrainState
from ...instantiate import import_class

# LightningTrainer — requires `pytorch_lightning`. Reuses the base Trainer's construction
# (init_model / init_optimizer / init_lr_scheduler / init_loss / set_data_loader) and the
# `run_step` contract, and hands the loop / DDP / FSDP / AMP / grad-accum / multi-node /
# checkpointing to PyTorch Lightning.
#
# Optimization modes (auto-detected from whether `self.optimizer` is a dict):
#   - single optimizer  -> Lightning AUTOMATIC optimization; run_step returns (loss_tensor, metric).
#   - dict of optimizers -> MANUAL optimization; run_step returns ({optimizer_key: loss_tensor}, metric).
#     `self.model` may likewise be a dict of nn.Module (registered as an nn.ModuleDict so Lightning
#     moves + DDP-wraps every sub-model). Optimizer keys drive the per-optimizer backward/step order.
#
# Composition, not multiple inheritance (pl.LightningModule's global_step/device/log collide with
# the base Trainer). The inner adapter forwards to the *_tj hooks below, which subclasses can override
# for custom schemes (e.g. alternating GAN updates that need separate forwards / detach).
#
# `strategy` is either a Lightning string alias ('ddp' | 'ddp_find_unused_parameters_true' | 'fsdp' | 'auto')
# or a {path, args} class-meta dict that is instantiated into a Strategy object, e.g.:
#   strategy: { path: pytorch_lightning.strategies.DDPStrategy,
#               args: { find_unused_parameters: true, gradient_as_bucket_view: true } }
#   strategy: { path: pytorch_lightning.strategies.ModelParallelStrategy,
#               args: { tensor_parallel_size: 1, data_parallel_size: 16 } }   # data_parallel_size = total GPUs
# (data_parallel_size must be explicit — inject it per-run via a CLI override, e.g. --set
#  train.class_meta.args.strategy.args.data_parallel_size=$TOTAL_GPU, like ntd computes TOTAL_GPU in its launcher.)
#
# NOTE: the multi-optimizer + EMA paths are implemented to the documented contract but are NOT
# runtime-verified (need a GPU node); validate with a smoke run before relying on them
# (see the LightningTrainer verification checklist in README.md).

class LightningTrainer(Trainer):
    def __init__(
        self,
        *args,
        num_nodes:int = 1,
        devices:Union[int, str] = 'auto',
        strategy:Union[str, dict] = 'auto', # str alias OR {path, args} to build a Strategy object (see module docstring)
        precision:str = '32-true',    # 'bf16-mixed' | '16-mixed' | '32-true' | ...
        **kwargs
    ) -> None:
        kwargs['device'] = torch.device('cpu') # Lightning owns per-rank device placement
        super().__init__(*args, **kwargs) # builds self.model / optimizer / lr_scheduler / loss_fn_dict / data_loader_dict / logger / model_ema

        self.pl_num_nodes:int = num_nodes
        self.pl_devices:Union[int, str] = devices
        self.pl_strategy:Union[str, dict] = strategy
        self.pl_precision:str = precision
        self._resume_ckpt_path:str = None
        self._optimizer_key_list:list = list(self.optimizer.keys()) if isinstance(self.optimizer, dict) else None
        self._ema_online_backup = None

    def load_train(self, filename:str, map_location:str = 'cpu') -> None:
        # Lightning resumes at fit(ckpt_path=...); its .ckpt format differs from the base's, so
        # resume from the 'last.ckpt' that ModelCheckpoint writes into the same run directory.
        self._resume_ckpt_path = os.path.join(os.path.dirname(filename), 'last.ckpt')

    def is_manual_optimization(self) -> bool:
        return isinstance(self.optimizer, dict)

    # ---------- overridable Lightning hooks (called by the inner adapter) ----------
    def configure_optimizers_tj(self):
        if not self.is_manual_optimization():
            if self.lr_scheduler is None:
                return self.optimizer
            return {
                'optimizer': self.optimizer,
                'lr_scheduler': {'scheduler': self.lr_scheduler, 'interval': self.lr_scheduler_interval, 'frequency': 1},
            }
        optimizer_list:list = [self.optimizer[key] for key in self._optimizer_key_list]
        scheduler_list:list = []
        if isinstance(self.lr_scheduler, dict):
            for key in self._optimizer_key_list:
                scheduler = self.lr_scheduler.get(key)
                if scheduler is not None:
                    scheduler_list.append({'scheduler': scheduler, 'interval': self.lr_scheduler_interval, 'frequency': 1})
        return optimizer_list, scheduler_list

    def training_step_tj(self, module, batch, batch_idx):
        self._sync_state(module, batch_idx)
        loss, metric = self.run_step(batch, dict(), TrainState.TRAIN)

        if not self.is_manual_optimization(): # Lightning does backward / step / zero_grad / clip / accumulation
            module.log('train/loss', loss, prog_bar=True, on_step=True, sync_dist=True)
            self._log_metric_dict(module, metric, 'train', on_step=True)
            return loss

        # ---- manual optimization: one loss per optimizer key ----
        assert isinstance(loss, dict), "multi-optimizer setup: run_step must return ({optimizer_key: loss_tensor}, metric)."
        optimizer_list = module.optimizers()
        if not isinstance(optimizer_list, (list, tuple)): optimizer_list = [optimizer_list]
        scheduler_list = module.lr_schedulers()
        if scheduler_list is not None and not isinstance(scheduler_list, (list, tuple)): scheduler_list = [scheduler_list]

        is_step:bool = (batch_idx + 1) % self.grad_accum_steps == 0
        last_index:int = len(self._optimizer_key_list) - 1
        for index, key in enumerate(self._optimizer_key_list):
            optimizer = optimizer_list[index]
            module.manual_backward(loss[key] / self.grad_accum_steps, retain_graph=(index < last_index)) # retain for shared-graph multi-loss
            module.log(f'train/{key}_loss', loss[key], prog_bar=True, on_step=True, sync_dist=True)
            if is_step:
                if self.max_grad_norm is not None:
                    module.clip_gradients(optimizer, gradient_clip_val=self.max_grad_norm)
                optimizer.step()
                optimizer.zero_grad()
        if is_step and scheduler_list is not None and self.lr_scheduler_interval == 'step':
            for scheduler in scheduler_list: scheduler.step()
        self._log_metric_dict(module, metric, 'train', on_step=True)
        return None

    def validation_step_tj(self, module, batch, batch_idx):
        self._sync_state(module, batch_idx)
        loss, metric = self.run_step(batch, dict(), TrainState.VALIDATE)
        log_loss = sum(loss.values()) if isinstance(loss, dict) else loss
        module.log('valid/loss', log_loss, prog_bar=True, on_epoch=True, sync_dist=True)
        self._log_metric_dict(module, metric, 'valid', on_step=False)
        return log_loss

    def on_train_epoch_end_tj(self, module) -> None:
        # manual mode: step epoch-interval schedulers ourselves (automatic mode does this internally)
        if self.is_manual_optimization() and self.lr_scheduler_interval == 'epoch':
            scheduler_list = module.lr_schedulers()
            if scheduler_list is not None:
                for scheduler in (scheduler_list if isinstance(scheduler_list, (list, tuple)) else [scheduler_list]):
                    scheduler.step()

    # ---------- helpers ----------
    def _sync_state(self, module, batch_idx:int) -> None:
        self.device = module.device
        self.global_step = module.global_step
        self.current_epoch = module.current_epoch
        self.local_step = batch_idx

    def _log_metric_dict(self, module, metric:dict, split:str, on_step:bool) -> None:
        for name, value in metric.items():
            scalar = value.avg if hasattr(value, 'avg') else value
            if isinstance(scalar, (int, float, torch.Tensor)):
                module.log(f'{split}/{name}', scalar, on_step=on_step, on_epoch=not on_step, sync_dist=True)

    def _build_ema_callback(self, pl):
        outer = self
        class EMACallback(pl.Callback):
            def on_fit_start(self, trainer, pl_module) -> None:
                outer.model_ema.to(pl_module.device)
            def on_train_batch_end(self, trainer, pl_module, *args, **kwargs) -> None:
                outer.model_ema.update()
            def on_validation_start(self, trainer, pl_module) -> None:
                outer._ema_online_backup = outer.model # evaluate with EMA weights
                outer.model = outer.model_ema.ema_model
            def on_validation_end(self, trainer, pl_module) -> None:
                if outer._ema_online_backup is not None:
                    outer.model = outer._ema_online_backup
                    outer._ema_online_backup = None
            def state_dict(self) -> dict:
                return {'model_ema': outer.model_ema.state_dict()}
            def load_state_dict(self, state_dict:dict) -> None:
                outer.model_ema.load_state_dict(state_dict['model_ema'])
        return EMACallback()

    def fit(self) -> None:
        import pytorch_lightning as pl # lazy: optional dependency, only needed when this trainer runs
        from pytorch_lightning.callbacks import ModelCheckpoint
        outer = self

        class LightningAdapter(pl.LightningModule):
            """Bridges Lightning's inverted control flow to the base Trainer's *_tj hooks."""
            def __init__(self) -> None:
                super().__init__()
                if isinstance(outer.model, dict): # register every sub-model so Lightning moves + DDP-wraps them
                    for key, sub_model in outer.model.items():
                        assert isinstance(sub_model, nn.Module), f"multi-model expects nn.Module values; '{key}' is {type(sub_model)} (nested dict: TODO)."
                    self.models = nn.ModuleDict(outer.model)
                    outer.model = self.models # repoint so run_step sees the registered/moved modules
                else:
                    self.model = outer.model
                if outer.is_manual_optimization():
                    self.automatic_optimization = False

            def configure_optimizers(self): return outer.configure_optimizers_tj()
            def training_step(self, batch, batch_idx): return outer.training_step_tj(self, batch, batch_idx)
            def validation_step(self, batch, batch_idx): return outer.validation_step_tj(self, batch, batch_idx)
            def on_train_epoch_end(self): outer.on_train_epoch_end_tj(self)
            def train_dataloader(self): return outer.data_loader_dict[TrainState.TRAIN.value]
            def val_dataloader(self): return outer.data_loader_dict[TrainState.VALIDATE.value]

        log_root:str = self.logger.log_path['root'] if self.logger is not None else None
        callback_list:list = [ModelCheckpoint(dirpath=log_root, save_last=True, every_n_epochs=self.save_model_epoch_interval, save_top_k=-1)]
        if self.use_ema and self.model_ema is not None:
            callback_list.append(self._build_ema_callback(pl))

        manual:bool = self.is_manual_optimization()
        strategy = self.pl_strategy
        if isinstance(strategy, dict): # {path, args} -> a Strategy object (DDPStrategy / FSDPStrategy / ModelParallelStrategy / ...)
            strategy = import_class(strategy['path'])(**strategy.get('args', dict()))
        pl_trainer = pl.Trainer(
            num_nodes=self.pl_num_nodes,
            devices=self.pl_devices,
            strategy=strategy,
            precision=self.pl_precision,
            accumulate_grad_batches=(1 if manual else self.grad_accum_steps), # manual mode accumulates itself
            gradient_clip_val=(None if manual else self.max_grad_norm),       # manual mode clips itself
            max_epochs=self.total_epoch,
            max_steps=(-1 if self.total_step == float('inf') else int(self.total_step)),
            default_root_dir=log_root,
            callbacks=callback_list,
        )
        pl_trainer.fit(LightningAdapter(), ckpt_path=self._resume_ckpt_path) # ckpt_path=None -> fresh run
