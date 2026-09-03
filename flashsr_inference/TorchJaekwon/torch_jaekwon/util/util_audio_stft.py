#type
from typing import Union,Dict
from numpy import ndarray
from torch import Tensor

import os
import matplotlib.pyplot as plt
import numpy as np
import torch
import librosa
try: import librosa.display
except: print('can not import librosa display')

from . import util, util_audio, util_torch

def spec_to_figure(
    spec,
    vmin:float = -6.0, 
    vmax:float = 1.5,
    fig_size:tuple = (12,6),
    dpi = 400,
    transposed=False,
    save_path=None
) -> None:
    if isinstance(spec, torch.Tensor):
        spec = spec.squeeze().cpu().numpy()
    spec = spec.squeeze()
    fig = plt.figure(figsize=fig_size, dpi = dpi)
    plt.pcolor(spec.T if transposed else spec, vmin=vmin, vmax=vmax)
    if save_path is not None:
        plt.savefig(save_path,dpi=dpi)
    plt.close()
    return fig

def plot(
    save_path:str, #'*.png'
    spec:ndarray, #[freq, time]
    fig_size:tuple=(12,4),
    dpi:int = 150,
    hop_size:int = None,
    sr:int = None,
    show_time:bool = True,
    background:str = 'white',
    line_dict:dict = dict(), # {'feature_name': {'value': 1d_array[time], 'color':str , 'scale':bool}}
    h_line_dict:dict = dict(), # {'feature_name': List[{'start':int, 'end':int, value:float}]}
    text_dict:dict = dict(), #{ 'feature_name': List[{ x:int, y:int, value_dict:List[{'value':str}] }] }
) -> None:
    COLOR_DICT:dict = {
        'blue': 'blue',
        'darkblue':'darkblue',
        'red': 'red',
        'darkred': 'darkred',
        'purple': '#9370DB',
        'darkpurple': '#4B0082',
    }
    COLOR_LIST:list = ['darkblue', 'blue', 'darkmagenta', 'darkorange', 'darkgreen', 'darkblue', 'darkred', 'darkcyan', 'darkviolet', 'darkgoldenrod', 'darkolivegreen', 'darkslategray']
    
    assert(os.path.splitext(save_path)[1] == ".png") , "file extension should be '.png'"
    util.make_parent_dir(save_path)
    # set plt
    plt.rc('font', size=4)
    plt.rc('legend', labelcolor='white')
    plt.grid(False)
    if isinstance(spec, Tensor):
        spec = util_torch.to_np(spec)
    _, axes = plt.subplots(1, 1, figsize=fig_size, sharex=True)
    if show_time:
        axes.grid(True, axis='x', linestyle='--', color='black', linewidth=0.5)
    else:
        axes.grid(False)
    # set x axis
    if show_time:
        axes.set_xlim([0, spec.shape[-1]])
        axes.set_xticks(np.linspace(0, spec.shape[-1], num=10))
        time_axis = np.arange(spec.shape[-1]) * hop_size / sr
        axes.set_xticklabels(np.round(np.linspace(0, time_axis[-1], num=10), 2))
    else:
        axes.set_xticks([])
        axes.set_xticklabels([])

    # set y axis
    axes.set_ylim([0, spec.shape[0]])
    axes.imshow(spec, origin='lower', aspect='auto', cmap='viridis')
    axes.set_yticks([])
    # plot line
    for key, value in line_dict.items():
        y = value['value']
        if y is None: continue
        if value.get('scale', False):
            y = y * spec.shape[0]
        color = COLOR_DICT.get(value.get('color', ''), COLOR_LIST.pop())
        axes.plot(y, color = color, linewidth=1, label=key)
    # plot horizontal line
    for key, value in h_line_dict.items():
        for plot_dict in value:
            plt.plot((plot_dict['start'], plot_dict['end']), (plot_dict['value'], plot_dict['value']), 'k', linewidth=1)
    # plot text
    text_y_offset = 4
    for key, value in text_dict.items():
        for plot_dict in value:
            for i, value_dict in enumerate(plot_dict['value_dict']):
                axes.text(
                    x=plot_dict['x'],
                    y=max(plot_dict['y'] - text_y_offset * (i + 1), 0),
                    s=value_dict['value'],
                    color='black',
                    horizontalalignment='center',
                    verticalalignment='center'
                )
    if line_dict:
        axes.legend()
    plt.tight_layout()
    background_plt_args_dict = {
        'white': {},
        'black': {'facecolor':'black'},
        'transparent': {'transparent':True}
    }
    plt.savefig(save_path,dpi=dpi, **background_plt_args_dict[background])
    plt.close()
class UtilAudioSTFT():
    def __init__(self,nfft:int, hop_size:int = None):
        super().__init__()
        self.nfft = nfft
        self.hop_size = hop_size if hop_size is not None else nfft // 4
        self.hann_window = torch.hann_window(self.nfft)
    
    def stft(
        self,
        audio:Union[ndarray,Tensor] # [time] or [batch, time] or [batch, channel, time]
    ) -> Dict[str,Tensor]:
        
        audio_torch:Tensor = torch.from_numpy(audio) if type(audio) == np.ndarray else audio
        
        assert(len(audio_torch.shape) <= 3), f'Error: stft() audio torch shape is {audio_torch.shape}'

        if (len(audio_torch.shape) == 1): audio_torch = audio_torch.unsqueeze(0)

        shape_is_three = True if len(audio_torch.shape) == 3 else False
        if shape_is_three:
            batch_size, channels_num, segment_samples = audio_torch.shape
            audio_torch = audio_torch.reshape(batch_size * channels_num, segment_samples)
        
        spec_dict:Dict[str,Tensor] = dict()

        audio_torch = torch.nn.functional.pad(audio_torch.unsqueeze(1), (int((self.nfft-self.hop_size)/2), int((self.nfft-self.hop_size)/2)), mode='reflect').squeeze(1)
        spec_dict['stft'] = torch.stft(
            input = audio_torch, 
            n_fft = self.nfft, 
            hop_length = self.hop_size, 
            window = self.hann_window.to(audio_torch.device),
            center = False,
            pad_mode = 'reflect',
            normalized = False,
            onesided = True,
            return_complex = True
        )

        spec_dict['mag'] = spec_dict['stft'].abs()
        spec_dict['angle'] = spec_dict['stft'].angle()

        if shape_is_three:
            _, time_steps, freq_bins = spec_dict['stft'].shape
            for feature_name in spec_dict:
                spec_dict[feature_name] = spec_dict[feature_name].reshape(batch_size, channels_num, time_steps, freq_bins)

        return spec_dict
    
    def istft(self, mag:Tensor, angle:Tensor) -> Tensor:
        stft_complex:Tensor = torch.polar(abs = mag, angle = angle)
        return torch.istft(stft_complex, self.nfft, hop_length=self.hop_size,window=self.hann_window.to(stft_complex.device), center=True, onesided=True)

    def plot_stft(self, audio_path:str, save_path:str, dpi:int = 300, **kwargs) -> None:
        audio, sr = util_audio.read(audio_path, mono=True)
        stft_mag:np.ndarray = util_torch.to_np(self.stft(audio)['mag'])
        stft_mag = librosa.amplitude_to_db(stft_mag)
        plot(
            save_path=save_path,
            spec=stft_mag,
            fig_size=(12,4),
            dpi=dpi,
            hop_size=self.hop_size,
            sr=sr,
            **kwargs
        )