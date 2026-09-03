from typing import Dict, Optional, Union, Literal
from numpy import ndarray

import os
import psutil
import time
import torch.nn as nn
from datetime import datetime
from datetime import timedelta
try: import wandb
except: print('Didnt import following packages: wandb')
try: from tensorboardX import SummaryWriter
except: print('Didnt import following packages: tensorboardX')

from ...util import util, util_torch, util_torch_distributed, util_data, util_audio_stft, util_audio

class Logger():
    def __init__(
        self,
        experiment_name:str,
        use_time_on_experiment_name:bool,
        project_name:str,
        visualizer_type:Literal['wandb','tensorboard'],
        root_dir_path:str,
        is_resume:bool = False,
    ) -> None:
        self.experiment_start_time:float = time.time()
        self.experiment_name:str = experiment_name
        if use_time_on_experiment_name: self.experiment_name = "[" +datetime.now().strftime('%y%m%d-%H%M%S') + "] " + self.experiment_name
        
        self.log_path:dict[str,str] = {
            "root": root_dir_path,
            "console": f'{root_dir_path}/log.txt',
            "debug": f'{root_dir_path}/log_debug.txt',
            "visualizer":f'{root_dir_path}/tb',
            "log_media": f'{root_dir_path}/log_media'
        }
        os.makedirs(self.log_path["visualizer"],exist_ok=True)

        self.visualizer_type:Literal['wandb','tensorboard'] = visualizer_type
        self.is_resume:bool = is_resume
        if self.is_resume: util.log('resume the training', 'info')

        if not util_torch_distributed.is_main_process(): return

        if self.visualizer_type == 'wandb':
            if self.is_resume:
                try:
                    wandb_meta_data:dict = util_data.yaml_load(f'''{self.log_path['root']}/wandb_meta.yaml''')
                    wandb.init(id=wandb_meta_data['id'], project=project_name, resume = 'must')
                except:
                    util.log("Failed to resume wandb. Please check the wandb_meta.yaml file", msg_type='error')
                    wandb.init(project=project_name)
            else: 
                wandb.init(project=project_name)
            wandb.run.name = self.experiment_name

            util_data.yaml_save(f'''{self.log_path['root']}/wandb_meta.yaml''', data={
                'id': wandb.run.id,
                'name': wandb.run.name,
            })
        elif self.visualizer_type == 'tensorboard':
            self.tensorboard_writer = SummaryWriter(log_dir=self.log_path["visualizer"])
        else:
            print('visualizer should be either wandb or tensorboard')
            exit()
    
    def get_time_took(self) -> str:
        time_took_second:int = int(time.time() - self.experiment_start_time)
        time_took:str = str(timedelta(seconds=time_took_second))
        return time_took
        
    def print_and_log(self, log_message:str) -> None:
        log_message_with_time_took:str = f"{log_message} ({self.get_time_took()} took)"
        print(log_message_with_time_took)
        self.log_write(log_message_with_time_took)
    
    def init_logger(self, model:nn.Module) -> None:
        write_mode:str = 'a' if self.is_resume else 'w'
        file = open(self.log_path["console"], write_mode)
        file.write("========================================="+'\n')
        file.write(f'pid: {os.getpid()} / parent_pid: {psutil.Process(os.getpid()).ppid()} \n')
        file.write("========================================="+'\n')
        self.log_model_parameters(file, model)
        file.close()

        file = open(self.log_path["debug"], write_mode)
        file.close()

        if self.visualizer_type == 'wandb':
            while not isinstance(model, nn.Module):
                model = model[list(model.keys())[0]]
            wandb.watch(model)
    
    def log_model_parameters(self, file, model: Union[nn.Module, dict], model_name:str = ''):
        if isinstance(model, nn.Module):
            file.write(f'''Model {model_name} Total parameters: {format(util_torch.get_param_num(model)['total'], ',d')}'''+'\n')
            file.write(f'''Model {model_name} Trainable parameters: {format(util_torch.get_param_num(model)['trainable'], ',d')}'''+'\n')
        else:
            for model_name in model:
                self.log_model_parameters(file, model[model_name], model_name)

    def log_write(self,log_message:str, log_type:Literal['console', 'debug']='console')->None:
        file = open(self.log_path[log_type],'a')
        file.write(log_message+'\n')
        file.close()

    def visualizer_log(
        self,
        x_axis_name:str, #epoch, step, ...
        x_axis_value:float,
        y_axis_name:str, #metric name
        y_axis_value:float
    ) -> None:

        if self.visualizer_type == 'tensorboard':
            self.tensorboard_writer.add_scalar(y_axis_name,y_axis_value,x_axis_value)
        else:
            wandb.log({y_axis_name: y_axis_value, x_axis_name: x_axis_value})
    
    def plot_audio(
        self, 
        name:str, #test case name, you could make structure by using /. ex) 'taskcase_1/test_set_1'
        audio_dict:Dict[str,ndarray], #{'audio name': 1d audio array}.
        global_step:int,
        sample_rate:int = 16000,
        is_plot_spec:bool = False,
        is_plot_mel:bool = True,
        mel_spec_args:Optional[dict] = None,
        log_local:bool = False, # if True, save audio in local path
    ) -> None:

        self.plot_wav(name = name + '_audio', audio_dict = audio_dict, sample_rate=sample_rate, global_step=global_step, log_local=log_local)
        if is_plot_mel:
            from ...util.util_audio_mel import UtilAudioMelSpec, get_default_config
            if mel_spec_args is None:
                mel_spec_args = get_default_config(sample_rate=sample_rate)
            mel_spec_util = UtilAudioMelSpec(**mel_spec_args)
            mel_dict = dict()
            for audio_name in audio_dict:
                mel_dict[audio_name] = mel_spec_util.get_hifigan_mel_spec(audio=audio_dict[audio_name],return_type='ndarray')
            self.plot_spec(name = name + '_mel_spec', spec_dict = mel_dict, global_step=global_step, log_local=log_local)


    def plot_wav(
        self, 
        name:str, #test case name, you could make structure by using /. ex) 'audio/test_set_1'
        audio_dict:Dict[str,ndarray], #{'audio name': 1d audio array},
        sample_rate:int,
        global_step:int,
        log_local:bool = False, # if True, save audio in local path
    ) -> None:
        if self.visualizer_type == 'tensorboard':
            for audio_name in audio_dict:
                self.tensorboard_writer.add_audio(f'{name}/{audio_name}', audio_dict[audio_name], sample_rate=sample_rate, global_step=global_step)
        else:
            wandb_audio_list = list()
            for audio_name in audio_dict:
                wandb_audio_list.append(wandb.Audio(audio_dict[audio_name], caption=f'{audio_name}({util_data.pretty_num(global_step)})', sample_rate=sample_rate))
                if log_local:
                    util_audio.write(f"{self.log_path['log_media']}/{global_step:09d}/{name}_{audio_name}.wav", audio_dict[audio_name], sample_rate=sample_rate)
            wandb.log({name: wandb_audio_list, 'global_step': global_step})
    
    def plot_spec(
        self, 
        name:str, #test case name, you could make structure by using /. ex) 'mel/test_set_1'
        spec_dict:Dict[str,ndarray], #{'name': 2d array},
        vmin=-6.0, 
        vmax=1.5,
        transposed=False, 
        global_step=0,
        log_local:bool = False, # if True, save spec in local path
    ) -> None:
        if self.visualizer_type == 'tensorboard':
            for audio_name in spec_dict:
                figure = util_audio_stft.spec_to_figure(spec_dict[audio_name], vmin=vmin, vmax=vmax,transposed=transposed)
                self.tensorboard_writer.add_figure(f'{name}/{audio_name}',figure,global_step=global_step)
        else:
            wandb_mel_list = list()
            for audio_name in spec_dict:
                util_audio_stft.spec_to_figure(spec_dict[audio_name], vmin=vmin, vmax=vmax,transposed=transposed,save_path=f'''{self.log_path['root']}/temp_img_{audio_name}.png''')
                wandb_mel_list.append(wandb.Image(f'''{self.log_path['root']}/temp_img_{audio_name}.png''', caption=f'{audio_name}({util_data.pretty_num(global_step)})'))
            wandb.log({name: wandb_mel_list, 'global_step': global_step})
    
    def log_every_epoch(self,model:nn.Module):
        pass