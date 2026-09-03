#type
from typing import Type, Literal

#package
import os
import sys
import ast
import argparse
import yaml
import numpy as np
import torch

#torchjaekwon
from .instantiate import import_class, instantiate_class_meta
from .util import util, util_data
from . import path as tj_path

def coerce_override_value(raw_value:str): # YAML-typed, with a Python-literal fallback so '1e-4', '1e5' etc. parse as numbers (PyYAML leaves those as strings)
    value = yaml.safe_load(raw_value)
    if isinstance(value, str):
        try: return ast.literal_eval(value)
        except (ValueError, SyntaxError): return value
    return value

def run() -> None:
    config_dict:dict = set_argparse()
    config_name:str = config_dict['cli']['config_name']
    stage: Literal['preprocess', 'train', 'inference', 'evaluate'] = config_dict['cli']['stage']

    util.log(f"[{stage}] {config_name} start.", msg_type='info')
    getattr(sys.modules[__name__],stage)(config_dict)
    util.log(f"[{stage}] {config_name} finish.", msg_type='success')

def set_argparse() -> dict:
    parser = argparse.ArgumentParser()

    # common arguments
    parser.add_argument('--config_path', type=str, help='config file path')
    parser.add_argument('--config_name', type=str, help='config name for logging', required=False)
    parser.add_argument('--project_name', type=str, help='project name for logging')
    parser.add_argument('--stage', type=str, help='stage: preprocess | train | inference | evaluate')

    # train arguments
    parser.add_argument('-r', '--resume', help='train resume', action='store_true')
    parser.add_argument('--train_resume_path', type=str, help='train resume path', required=False)
    parser.add_argument('--log_tool', type=str, help='log tool: tensorboard | wandb', default='tensorboard')

    # inference arguments
    parser.add_argument('--infer_data_path', nargs='*', type=str, help='inference data path when set type is single or dir', required=False)
    parser.add_argument('--ckpt_name', type=str, help='checkpoint name for inference', default='last')

    # evaluate arguments
    parser.add_argument('--eval_gt_dir_path', type=str, help='evaluation directory path for groundtruth', required=False)
    parser.add_argument('--eval_pred_dir_path', type=str, help='evaluation directory path for prediction', required=False)

    # generic config override: --set SECTION.KEY=VALUE [SECTION.KEY=VALUE ...] (VALUE is YAML-typed; overrides the config file)
    parser.add_argument('--set', nargs='*', default=[], metavar='SECTION.KEY=VALUE', help='e.g. --set train.seed=42 mode.debug_mode=false train.optimizer.args.lr=1e-4')

    args = parser.parse_args()

    config_dict = util_data.yaml_load(args.config_path, interpolate=True)
    assert 'cli' not in config_dict, "Reserved key 'cli' found in config file."
    config_dict['cli'] = vars(args)
    config_dict['cli']['config_name'] = config_dict['cli']['config_name'] or os.path.splitext(tj_path.relpath(args.config_path, start_dir_path=tj_path.CONFIG_DIR) or os.path.basename(args.config_path))[0] # relpath is None when config isn't under ./config -> fall back to basename
    config_dict['cli']['train_resume_path'] = config_dict['cli'].get('train_resume_path') or f"{tj_path.ARTIFACTS_DIRS.train}/{config_dict['cli']['config_name']}" # 'cli' always has the key (=None); '.get(k, default)' would keep None, so use 'or'

    # Defaults for config values the pipeline reads but a config may omit (applied only when absent).
    config_default_list:list = [ # (section, key, default)
        ('resource', 'num_workers',               1),
        ('mode',     'debug_mode',                 True),
        ('mode',     'use_torch_compile',          True),
        ('train',    'check_evalstep_first',       True),
        ('train',    'save_model_epoch_interval',  100),
        ('train',    'start_logging_epoch',        0),
        ('log',      'log_step_interval',          40),
    ]
    for section, key, default in config_default_list:
        config_dict.setdefault(section, dict()).setdefault(key, default)

    # Apply generic '--set section.key=value' overrides. Precedence: defaults < config file < --set
    for override in config_dict['cli']['set']:
        assert '=' in override, f"--set expects 'section.key=value', got {override!r}"
        dotted_key, raw_value = override.split('=', 1)
        key_list:list = dotted_key.strip().split('.')
        node:dict = config_dict
        for key in key_list[:-1]: node = node.setdefault(key, dict())
        node[key_list[-1]] = coerce_override_value(raw_value) # '42'->42, 'false'->False, '1e-4'->0.0001, '[1,2]'->[1,2], else str
    return config_dict

def preprocess(config_dict:dict) -> None:
    from .data.preprocess.preprocessor import Preprocessor
    preprocessor_class_meta_list:list = config_dict['data']['preprocessor_class_meta_list']
    num_workers:int = config_dict['resource']['num_workers']
    device:torch.device = config_dict.get('resource', {}).get('device')
    
    for preprocessor_meta in preprocessor_class_meta_list:
        preprocessor_meta['args']['num_workers'] = preprocessor_meta['args'].get('num_workers', num_workers)
        preprocessor_meta['args']['device'] = preprocessor_meta['args'].get('device', device)
        preprocessor:Preprocessor = instantiate_class_meta(class_meta=preprocessor_meta)
        preprocessor.preprocess_data()                           

def train(config_dict:dict) -> None:
    import torch
    from torch_jaekwon.train.trainer.trainer import Trainer
    from torch_jaekwon.train.logger.logger import Logger

    logger = Logger(
        experiment_name = config_dict['cli']['config_name'],
        use_time_on_experiment_name = False,
        project_name = config_dict['cli'].get('project_name') or 'default_project',
        visualizer_type = config_dict['cli']['log_tool'],
        root_dir_path = f'{tj_path.ARTIFACTS_DIRS.train}/{config_dict["cli"]["config_name"]}',
        is_resume = config_dict['cli']['resume'],
    )
    config_dict['dataloader']['train']['dataset_class_meta']['args']['logger'] = logger

    train_config:dict = config_dict['train']
    trainer_args = {
        # data
        'data_class_meta_dict': config_dict['dataloader'],
        # model
        'model_class_meta_dict': config_dict['model']['class_meta'],
        # loss
        'loss_meta_dict': train_config.get('loss'),
        # optimizer
        'optimizer_class_meta_dict': train_config['optimizer']['class_meta'],
        'lr_scheduler_class_meta_dict': train_config['scheduler']['class_meta'],
        'lr_scheduler_interval': train_config['scheduler']['interval'],
        # train paremeters
        'seed': train_config.get('seed'), # None -> Trainer derives a CUDA-safe seed itself
        'seed_strict': train_config.get('seed_strict', False),
        # logging
        'logger': logger,
        'save_model_step_interval': train_config.get('save_model_step_interval'),
        'save_model_epoch_interval': train_config['save_model_epoch_interval'],
        'log_step_interval': config_dict['log']['log_step_interval'],
        'start_logging_epoch': train_config['start_logging_epoch'],
        # additional
        'check_evalstep_first': train_config['check_evalstep_first'],
        'debug_mode': config_dict['mode']['debug_mode'],
        'use_torch_compile': config_dict['mode']['use_torch_compile'],
    }

    train_class_meta:dict = train_config['class_meta'] # {'path': 'torch_jaekwon.train.trainer.trainer.Trainer', 'args': {}}
    trainer_class_name:str = train_class_meta['path']
    trainer_args.update(train_class_meta['args'])
    
    trainer_class:Type[Trainer] = import_class(module_name = trainer_class_name)
    trainer:Trainer = trainer_class(**trainer_args)
    
    if config_dict['cli']['resume']:
        util.log('load the checkpoint', 'info')
        trainer.load_train(config_dict['cli']['train_resume_path'] + "/train_checkpoint.pth")
    
    trainer.fit()

def inference(config_dict:dict) -> None:
    from torch_jaekwon.inference.inferencer import Inferencer
    
    infer_class_meta:dict = config_dict['inference']['class_meta']
    inferencer_args:dict = {
        'output_dir': tj_path.ARTIFACTS_DIRS.inference,
        'model':  None,
        'model_class_meta': config_dict['model']['class_meta'],
        'input_data_path': config_dict['cli']['infer_data_path'],
    }
    inferencer_args.update(infer_class_meta['args'])
    if 'save_dir_name' not in inferencer_args: inferencer_args['save_dir_name'] =  config_dict['cli']['config_name']

    inferencer_class:Type[Inferencer] = import_class(module_name = infer_class_meta['path'])
    inferencer:Inferencer = inferencer_class(**inferencer_args)
    inferencer.inference(
        pretrained_root_dir = tj_path.ARTIFACTS_DIRS.train,
        pretrained_dir_name = config_dict['cli']['config_name'],
        ckpt_name = config_dict['cli']['ckpt_name']
    )

def evaluate(config_dict:dict) -> None:
    from torch_jaekwon.evaluate.evaluator.evaluator import Evaluator
    eval_class_meta:dict = config_dict['evaluate']['class_meta']
    config_name:str = config_dict['cli']['config_name']
    gt_dir_path:str = config_dict['cli']['eval_gt_dir_path']
    pred_dir_path:str = config_dict['cli']['eval_pred_dir_path']

    evaluater_class:Type[Evaluator] = import_class(module_name=eval_class_meta['path'])
    evaluater_args:dict = eval_class_meta['args']
    evaluater_args.update({'pred_dir_path': pred_dir_path, 'gt_dir_path': gt_dir_path, 'result_dir_path': f'{tj_path.ARTIFACTS_DIRS.evaluate}/{config_name}'})
    evaluater:Evaluator = evaluater_class(**evaluater_args)
    evaluater.evaluate()
