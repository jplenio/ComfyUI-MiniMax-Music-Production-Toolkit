from typing import Optional, Literal, Union, Final, List
from numpy import ndarray

import os
from tqdm import tqdm
import torch.nn as nn
import numpy as np
import soundfile as sf
import librosa
from scipy.signal import resample_poly

try: import torch 
except: print('import error: torch')
try: from torch import Tensor
except: print('')
try: import torchaudio
except: print('import error: torch')
try: from pydub import AudioSegment  
except: print('import error: pydub')

from . import util, util_data

DATA_TYPE_MIN_MAX_DICT:Final[dict] = {'float32':(-1,1), 'float64':(-1,1), 'int16':(-2**15, 2**15-1), 'int32':(-2**31,2**31-1)}

def change_dtype(
    audio:ndarray,
    current_dtype:Literal['float32', 'float64', 'int16', 'int32'],
    target_dtype:Literal['float32', 'float64', 'int16', 'int32']
) -> ndarray:
    audio = np.clip(audio, a_min = DATA_TYPE_MIN_MAX_DICT[current_dtype][0], a_max = DATA_TYPE_MIN_MAX_DICT[current_dtype][1])
    audio = audio / DATA_TYPE_MIN_MAX_DICT[current_dtype][1]
    audio = (audio * DATA_TYPE_MIN_MAX_DICT[target_dtype][1])
    audio = audio.astype(getattr(np,target_dtype))
    return audio


def resample(
    audio:Union[ndarray, Tensor], #[shape=(channel, num_samples) or (num_samples)]
    origin_sr:int,
    target_sr:int,
    resample_module:Literal['librosa', 'resample_poly', 'torchaudio'] = 'torchaudio',
    resample_type:str = None,
) -> Union[ndarray, Tensor]:
    if(origin_sr == target_sr): return audio
    #print(f"resample audio {origin_sr} to {target_sr}")
    if resample_module == 'librosa':
        return librosa.resample(audio, orig_sr=origin_sr, target_sr=target_sr, res_type=resample_type if resample_type is not None else "kaiser_fast")
    elif resample_module == 'resample_poly':
        return resample_poly(x = audio, up = target_sr, down = origin_sr)
    elif resample_module == 'torchaudio':
        if isinstance(audio, ndarray): audio = torch.FloatTensor(audio)
        resampler:nn.Module = get_torch_resampler(origin_sr, target_sr, resample_type, device=audio.device)
        return resampler(audio)

def get_torch_resampler(
    origin_sr:int,
    target_sr:int,
    resample_type:str = None,
    device:Optional[torch.device] = None
) -> nn.Module:
    #transforms.Resample precomputes and caches the kernel used for resampling, while functional.resample computes it on the fly
    #so using torchaudio.transforms.Resample will result in a speedup when resampling multiple waveforms using the same parameters
    if resample_type is None:
        resampler = torchaudio.transforms.Resample(orig_freq = origin_sr, new_freq = target_sr)
    elif resample_type == 'kaiser_best':
        # https://pytorch.org/audio/stable/tutorials/audio_resampling_tutorial.html#kaiser-best
        resampler = torchaudio.transforms.Resample(
            orig_freq = origin_sr,
            new_freq = target_sr,
            lowpass_filter_width=64,
            rolloff=0.9475937167399596,
            resampling_method='sinc_interp_kaiser',
            beta=14.769656459379492,
        )
    else:
        raise ValueError(f"Unknown resample_type: {resample_type}")
    if device is not None:
        resampler = resampler.to(device)
    return resampler

def get_duration(audio_path:str) -> float: # seconds
    # metadata only: no decode, so this is cheap on long files
    info = sf.info(audio_path)
    return info.frames / info.samplerate


def read(
    audio_path:str,
    # result parameters
    sample_rate:Optional[int] = None, # Output sample rate. If None, original sample rate will be used
    mono:Optional[bool] = None,
    sample_length:Optional[int] = None,
    return_type:Union[ndarray, Tensor] = Tensor,
    # segment parameters
    start:Optional[int] = None,
    end:Optional[int] = None,
    segment_type:Literal['time','sample'] = 'time',
    origin_sample_rate:Optional[int] = None,
    # module parameters
    module_name:Literal['soundfile','librosa', 'torchaudio'] = 'torchaudio',
) -> Union[ndarray, Tensor]: # shape=(channel, num_samples)
    # error check
    if segment_type == 'time' and [start, end] != [None, None] and origin_sample_rate is None: 
        origin_sample_rate = sf.info(audio_path).samplerate
    if start is not None: assert module_name == 'torchaudio', f'[Error] currently only torchaudio module supports start and end parameter'
    
    if module_name == "soundfile":
        audio_data, original_sr = sf.read(audio_path)
        if len(audio_data.shape) > 1 : audio_data = audio_data.T
        if len(audio_data.shape) == 1: audio_data = audio_data.reshape(1, -1)
        if sample_rate is not None and sample_rate != original_sr:
            audio_data = resample(audio_data,original_sr,sample_rate)
    elif module_name == "librosa":
        audio_data, original_sr = librosa.load( audio_path, sr=sample_rate, mono=mono)
    elif module_name == 'torchaudio':
        if start is None:
            frame_offset = 0
        else:
            frame_offset = round(start * origin_sample_rate) if segment_type == 'time' else start
        if end is None:
            num_frames = -1
        else:
            num_frames = round((end - start) * origin_sample_rate) if segment_type == 'time' else end - start
        audio_data, original_sr = torchaudio.load(
            audio_path, 
            frame_offset = frame_offset, 
            num_frames = num_frames
        )
        if origin_sample_rate is not None: assert origin_sample_rate == original_sr, f'[Error] origin_sample_rate {origin_sample_rate} is different from the original sample rate {original_sr}'
        if sample_rate is not None and sample_rate != original_sr:
            audio_data = resample(audio = audio_data, origin_sr=original_sr, target_sr = sample_rate, resample_module='torchaudio')
    
    if sample_length is not None:
        audio_data = util_data.fix_length(audio_data, sample_length, dim = -1)
        
    audio_data = convert_audio_channels(audio_data, mono=mono)
    
    if isinstance(audio_data, Tensor) and return_type == ndarray:
        audio_data = audio_data.cpu().detach().numpy()
    elif isinstance(audio_data, ndarray) and return_type == Tensor:
        audio_data = torch.from_numpy(audio_data).float()

    return audio_data, original_sr if sample_rate is None else sample_rate

def convert_audio_channels(
    audio: Tensor, #[channel, time]
    mono:bool = None,
) -> Tensor:
    assert len(audio.shape) == 2, f'[Error] audio must be [channel, time], but got {audio.shape}'
    assert audio.shape[0] in [1,2], f'[Error] audio must be mono or stereo, but got {audio.shape[0]} channels'
    
    if mono is None: return audio
    if mono and audio.shape[0] == 2:
        audio = torch.mean(audio, axis=0, keepdim=True)
    elif not mono and audio.shape[0] == 1:
        stereo_audio = torch.zeros((2,len(audio.squeeze())))
        stereo_audio[0,...] = audio.squeeze()
        stereo_audio[1,...] = audio.squeeze()
        audio = stereo_audio
    return audio

def write(
    audio_path:str,
    audio:Union[ndarray, Tensor],
    sample_rate:int,
) -> None:
    util.make_parent_dir(audio_path)
    if isinstance(audio, Tensor):
        audio = audio.squeeze().cpu().detach().numpy()
    assert len(audio.shape) <= 2, f'[Error] shape of {audio_path}: {audio.shape}'
    if len(audio.shape) == 2 and audio.shape[0] < audio.shape[1]: audio = audio.T
    sf.write(file = audio_path, data = audio, samplerate = sample_rate)

def get_segment_index_list(
    audio:ndarray, #[time]
    sample_rate:int,
    segment_sample_length:int,
    hop_seconds:float = 0.1
) -> list:
    begin_sample:int = 0
    hop_samples = int(hop_seconds * sample_rate)
    segment_index_list = list()
    while (begin_sample == 0) or (begin_sample + segment_sample_length < len(audio)):
        segment_index_list.append({'begin':begin_sample, 'end':begin_sample + segment_sample_length})
        begin_sample += hop_samples
    return segment_index_list

def audio_to_batch(
    audio:Tensor, #[Length]
    segment_length:int,
    overlap_length:int = 48000 #recommend: int(sr * 0.5)
) -> Tensor:
    
    assert len(audio.shape) == 1, f'[Error] audio shape must be 1, but {audio.shape}'
    start_idx:int = 0
    audio_list = list()
    while start_idx < len(audio):
        audio_segment = audio[start_idx:start_idx+segment_length]
        audio_segment = util_data.fix_length(audio_segment, segment_length)
        audio_list.append(audio_segment)
        start_idx += segment_length - overlap_length
    return torch.stack(audio_list)

def merge_batch_w_cross_fade(
    batch_audio:Union[List[ndarray],ndarray,Tensor],
    segment_length:int,
    overlap_length:int = 48000 #recommend: int(sr * 0.5)
) -> ndarray:
    '''
    reference from https://github.com/nkandpa2/music_enhancement/blob/master/scripts/generate_from_wav.py
    '''
    if isinstance(batch_audio, ndarray) and len(batch_audio.shape) == 1:
        batch_audio = [batch_audio]
    output_audio_length:int = len(batch_audio) * segment_length - (len(batch_audio) - 1) * overlap_length
    output_audio:Union[ndarray,Tensor] = torch.zeros(output_audio_length) if isinstance(batch_audio, torch.Tensor) else np.zeros(output_audio_length)
    hop_length:int = segment_length - overlap_length
    
    cross_fade_in:ndarray = np.linspace(0, 1, overlap_length)
    cross_fade_out:ndarray = 1 - cross_fade_in
    if isinstance(batch_audio, torch.Tensor):
        cross_fade_in = torch.tensor(cross_fade_in, device = batch_audio.device)
        cross_fade_out = torch.tensor(cross_fade_out, device = batch_audio.device)
    
    for i in range(0,len(batch_audio)):
        start_idx:int = i * hop_length
        if i != 0:
            batch_audio[i][:overlap_length] *= cross_fade_in
        if i != len(batch_audio) - 1:
            batch_audio[i][-overlap_length:] *= cross_fade_out
        output_audio[start_idx:start_idx+segment_length] += batch_audio[i]
    return output_audio

def analyze_dataset(
    data_dir_list:Union[str, list], 
    result_save_dir:str = './meta',
    sanity_check_sr:Union[int,List[int]] = None,
    save_each_meta:bool = False
) -> None:
    if isinstance(data_dir_list, str): data_dir_list = [data_dir_list]
    result_meta_dict = dict()
    
    for data_dir in tqdm(data_dir_list, desc="Dataset list"):
        dir_name:str = util_data.get_file_name(data_dir)
        result_meta_dict[dir_name] = {
            'total_duration_second': 0,
            'total_duration_minutes': 0,
            'total_duration_hours': 0,

            'longest_sample_meta': {
                'file_name': '',
                'duration_second':0
            },

            'sample_rate': list(),
            'error_file_list': list()
        }
        if sanity_check_sr is not None: result_meta_dict[dir_name]['sample_rate'] = sanity_check_sr
        
        audio_meta_data_list = util_data.walk(dir_path=data_dir, ext=['.wav', '.mp3', '.flac'])
        for meta_data in tqdm(audio_meta_data_list):
            try:
                audio, sr = read(meta_data['file_abspath'], mono=True)
            except:
                print(f'Error: {meta_data["file_path"]}')
                result_meta_dict[dir_name]['error_file_list'].append(meta_data['file_abspath'])
                continue
            if sanity_check_sr is not None: 
                if isinstance(sanity_check_sr, int): assert sr == sanity_check_sr, f'''{meta_data['file_abspath']}'s sample rate is {sr}'''
                if isinstance(sanity_check_sr, list): assert sr in sanity_check_sr, f'''{meta_data['file_abspath']}'s sample rate is {sr}'''
            
            meta_data_of_this_file = {
                'file_name': meta_data['file_name'],
                'file_path': os.path.abspath(meta_data['file_abspath']),
                'sample_length': audio.shape[-1],
                'sample_rate': sr,
            }
            meta_data_of_this_file['duration_second'] = meta_data_of_this_file['sample_length'] / meta_data_of_this_file['sample_rate']
            
            if save_each_meta: 
                util_data.pickle_save(f"{result_save_dir}/per_sample/{dir_name}/{meta_data['file_abspath'].split(dir_name)[-1]}.pkl".replace('//','/'), meta_data_of_this_file)

            result_meta_dict[dir_name]['total_duration_second'] += meta_data_of_this_file['duration_second']
            if result_meta_dict[dir_name]['longest_sample_meta']['duration_second'] < meta_data_of_this_file['duration_second']:
                result_meta_dict[dir_name]['longest_sample_meta'] = meta_data_of_this_file
            if meta_data_of_this_file['sample_rate'] not in result_meta_dict[dir_name]['sample_rate']:
                result_meta_dict[dir_name]['sample_rate'].append(meta_data_of_this_file['sample_rate'])

        result_meta_dict[dir_name]['total_duration_minutes'] = result_meta_dict[dir_name]['total_duration_second'] / 60
        result_meta_dict[dir_name]['total_duration_hours'] = result_meta_dict[dir_name]['total_duration_second'] / 3600
    util_data.yaml_save(save_path = f'{result_save_dir}/meta.yaml', data = result_meta_dict)

def resample_dataset(
    data_dir_list:Union[str, list], 
    sr:int,
    save_dir:str = None,
) -> None:
    if isinstance(data_dir_list, str): data_dir_list = [data_dir_list]
    for data_dir in tqdm(data_dir_list, desc="Dataset list"):
        audio_meta_data_list = util_data.walk(dir_path=data_dir, ext=['.wav', '.mp3', '.flac'])
        for meta_data in tqdm(audio_meta_data_list):
            audio, _ = librosa.load(meta_data['file_abspath'], sr = sr)
            if save_dir is None:
                out_dir = meta_data['dir_abspath'].replace(meta_data['dir_name'], f"{meta_data['dir_name']}_{sr}")
            else:
                out_dir = os.path.join(save_dir, os.path.dirname(meta_data['file_relpath'])) # mirror the source tree under save_dir
            write(f"{out_dir}/{meta_data['file_name']}.wav", audio, sr)


def normalize_loudness(
    wav: Tensor,
    sample_rate: int,
    loudness_headroom_db: float = 18,
    energy_floor: float = 2e-3,
) -> Tensor:
    """
    Original code: https://github.com/kyutai-labs/moshi
    Normalize an input signal to a user loudness in dB LKFS.
    Audio loudness is defined according to the ITU-R BS.1770-4 recommendation.

    Copied verbatim from Kyutai Moshi's `scripts/tts_make_voice.py`
    (and identical to `rust/moshi-server/voice.py`). DC removal is performed
    as the first step, so calling this also centers the waveform.

    Args:
        wav (torch.Tensor): Input multichannel audio data.
        sample_rate (int): Sample rate.
        loudness_headroom_db (float): Target loudness of the output in dB LUFS.
            Moshi default (and what the production rust server uses): 18.
        energy_floor (float): anything below that RMS level will not be rescaled.
    Returns:
        torch.Tensor: Loudness normalized output data.
    """
    if loudness_headroom_db < 0:
        raise ValueError("loudness_headroom_db must be non-negative.")

    wav = wav - wav.mean(dim=-1, keepdim=True)
    energy = wav.std()
    if energy < energy_floor:
        return wav
    transform = torchaudio.transforms.Loudness(sample_rate)
    try:
        input_loudness_db = transform(wav).item()
    except RuntimeError:
        return wav
    delta_loudness = -loudness_headroom_db - input_loudness_db
    gain = 10.0 ** (delta_loudness / 20.0)
    output = gain * wav
    assert output.isfinite().all(), (input_loudness_db, wav.pow(2).mean().sqrt())
    return output

    

