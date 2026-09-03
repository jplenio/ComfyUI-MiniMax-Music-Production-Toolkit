from typing import Union,Dict,List, Literal
from numpy import ndarray
from torch import Tensor

import os
from tqdm import tqdm
import random
import copy
import numpy as np
import torch
import torch.nn.functional as F
import pickle, yaml, csv, json, gzip
from pathlib import Path
from inspect import isfunction

from . import util
from .. import path as tj_path

def get_file_name(file_path:str, with_ext:bool = False) -> str:
    if file_path is None:
        print("warning: path is None")
        return ""
    path_pathlib = Path(file_path)
    if with_ext:
        return path_pathlib.name
    else:
        return path_pathlib.stem

def dict_get_first(d: dict, keys: list, default=None):
    """Return the value for the first existing key in keys, or default if none exist."""
    for k in keys:
        if k in d:
            return d[k]
    return default

def pickle_save(save_path:str, data:Union[ndarray,Tensor]) -> None:
    save_path = util.norm_path(save_path)
    if not (os.path.splitext(save_path)[1] == ".pkl"):
        print("file extension should be '.pkl'")
        save_path = f'{save_path}.pkl'

    os.makedirs(os.path.dirname(save_path),exist_ok=True)
    
    with open(save_path,'wb') as file_writer:
        pickle.dump(data,file_writer)

def pickle_load(data_path:str) -> Union[ndarray,Tensor]:
    with open(data_path, 'rb') as pickle_file:
        data:Union[ndarray,Tensor] = pickle.load(pickle_file)
    return data

def yaml_save(save_path:str, data:Union[dict,list], sort_keys:bool = False) -> None:
    assert(os.path.splitext(save_path)[1] == ".yaml") , "file extension should be '.yaml'"
    util.make_parent_dir(save_path)

    with open(save_path, 'w', encoding="utf-8") as file:
        yaml.dump(data, file, sort_keys = sort_keys, allow_unicode=True)

def yaml_load(data_path:str, interpolate:bool = False) -> dict:
    yaml_file = open(data_path, 'r', encoding="utf-8")
    config_dict:dict = yaml.safe_load(yaml_file)
    return tj_path.resolve_env(config_dict) if interpolate else config_dict

def csv_load(data_path:str) -> list:
    row_result_list = list()
    with open(data_path, newline='') as csvfile:
        spamreader = csv.reader(csvfile)#, delimiter=' ', quotechar='|')
        for row in spamreader:
            row_result_list.append(row)
    return row_result_list

def txt_load(data_path:str) -> list:
    with open(data_path, 'r') as txtfile:
        return txtfile.readlines()

def txt_save(save_path:str, string_list:Union[List[str],str], new_file:bool = True) -> list:
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, 'w' if new_file else 'a') as file:
        if isinstance(string_list, str):
            file.write(string_list)
        else:
            for line in string_list:
                file.write(f'{line}\n')

def csv_save(
    file_path:str,
    data_dict_list:List[Dict[str,object]], #[ {key:object}, ... ]
    order_of_key:list = None # [key1, key2, ...]
) -> list:
    import pandas as pd
    if order_of_key is None:
        order_of_key = list(data_dict_list[0].keys())
    csv_save_dict:dict = {key:list() for key in order_of_key}
    for data_dict in data_dict_list:
        for key in csv_save_dict:
            csv_save_dict[key].append(data_dict[key])
    pd.DataFrame(csv_save_dict).to_csv(file_path)

def json_load(file_path:str) -> Union[dict,list]:
    is_jsonl = '.jsonl' in file_path
    if file_path.endswith('.gz'):
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            data = [json.loads(line) for line in f if line.strip()] if is_jsonl else json.load(f)
    else:
        with open(file_path) as f:
            data = [json.loads(line) for line in f if line.strip()] if is_jsonl else json.load(f)
    return data

def json_save(save_path:str, data:Union[dict,list], indent:int = 2) -> None:
    util.make_parent_dir(save_path)
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)

def jsonl_save(save_path: str, data_list: list[dict]) -> None:
    if Path(save_path).suffix != ".jsonl":
        raise ValueError("save_path must have the '.jsonl' extension")
    util.make_parent_dir(save_path)
    with open(save_path, 'w', encoding='utf-8') as file:
        for data in data_list:
            json.dump(data, file, ensure_ascii=False)
            file.write('\n')

def save_data_segment(save_dir:str,data:ndarray,segment_len:int,segment_axis:int=-1,remainder:str = ['discard','pad','maintain'][1],ext:str = ['pkl'][0]):
    os.makedirs(save_dir,exist_ok=True)
    data_total = data # not deep-copied: only reassigned via .take()/np.pad below, never mutated in place
    total_length_of_data:int = data_total.shape[segment_axis]

    if total_length_of_data % segment_len != 0 and remainder in ['discard','pad']:
        if remainder == 'discard':
            data_total = data_total.take(indices=range(0, total_length_of_data - (total_length_of_data % segment_len)), axis=segment_axis)
        else:
            assert(segment_axis==-1 and (len(data_total.shape) in [1,2])),'Error[UtilData.save_data_segment] not implemented yet' 
            pad_length:int = segment_len - (total_length_of_data % segment_len)
            if len(data_total.shape) == 1:
                data_total = np.pad(data_total, (0, pad_length), 'constant')
            elif len(data_total.shape) == 2:
                data_total = np.pad(data_total, ((0,0),(0,pad_length)), 'constant')
        total_length_of_data:int = data_total.shape[segment_axis]
    
    for start_idx in range(0,total_length_of_data,segment_len):
        end_idx:int = start_idx + segment_len
        if remainder == 'maintain' and end_idx >= total_length_of_data: end_idx = total_length_of_data - 1
        
        data_segment = data_total.take(indices=range(start_idx, end_idx), axis=segment_axis)

        assert(data_segment.shape[segment_axis] == segment_len),'Error[UtilData.save_data_segment] segment length error!!'
        if ext == 'pkl':
            pickle_save(f'{save_dir}/{start_idx}.{ext}',data_segment)

def fit_shape_length(feature:Union[Tensor,ndarray],shape_length:int, dim:int = 0) -> Tensor:
    if shape_length == len(feature.shape):
        return feature
    if type(feature) != torch.Tensor:
        feature = torch.from_numpy(feature)
    
    feature = torch.squeeze(feature)

    for _ in range(shape_length - len(feature.shape)):
        feature = torch.unsqueeze(feature, dim=dim)
    
    return feature

def sort_dict_list( dict_list: List[dict], key:str, reverse:bool = False):
    return sorted(dict_list, key = lambda dictionary: dictionary[key], reverse=reverse)

def random_segment(data:ndarray, data_length:int) -> ndarray:
    max_data_start = len(data) - data_length
    data_start = random.randint(0, max_data_start)
    return data[data_start:data_start+data_length]

def default(val, d):
    if val is not None:
        return val
    return d() if isfunction(d) else d

def fix_length(
    data:Union[ndarray,Tensor],
    length:int,
    dim:int = -1
) -> Tensor:
    assert len(data.shape) in [1,2,3], "Error[util_data.fix_length] only support when data.shape is 1, 2 or 3"
    if data.shape[dim] < length:
        if isinstance(data,Tensor):
            return F.pad(data, (0,length - data.shape[dim]), "constant", 0)
        else:
            return F.pad(torch.from_numpy(data), (0,length - data.shape[dim]), "constant", 0).numpy()
    elif data.shape[dim] == length:
        return data
    else:
        assert dim == -1, "Error[util_data.fix_length] slicing when dim is not -1 not implemented yet"
        return data[..., :length]
    
def walk(dir_path:str, *, ext:Union[list,str] = ['wav', 'mp3', 'flac'], depth:int = None, base_dir:str = None, use_tqdm:bool = True) -> list:
    if isinstance(ext, str): ext = [ext]
    ext = tuple(e.lower() if e.startswith('.') else f'.{e.lower()}' for e in ext) # case-insensitive; str.endswith accepts a tuple
    dir_path = os.path.abspath(dir_path)
    base_dir = os.path.abspath(base_dir) if base_dir is not None else dir_path # portable anchor for *_relpath (e.g. project/source root); default = dir_path

    file_meta_list:list = list()
    with tqdm(desc='walk', unit=' files', disable=not use_tqdm) as pbar: # one overall bar (os.walk is lazy so there's no total), not one bar per directory
        for root, dirs, files in os.walk(dir_path):
            if depth is not None and root.count(os.sep) - dir_path.count(os.sep) >= depth:
                dirs[:] = []
            dir_name, dir_relpath = get_file_name(root), os.path.relpath(root, base_dir) # constant per directory -> hoisted out of the file loop
            for filename in files:
                pbar.update(1)
                if filename.lower().endswith(ext):
                    file_abspath:str = os.path.join(root, filename)
                    file_meta_list.append({
                        'file_name': get_file_name(file_path=filename),
                        'file_abspath': file_abspath,
                        'file_relpath': os.path.relpath(file_abspath, base_dir),
                        'dir_name': dir_name,
                        'dir_abspath': root,
                        'dir_relpath': dir_relpath,
                    })
    return file_meta_list

def get_dir_name_list(root_dir:str) -> list:
    return [dir_name for dir_name in os.listdir(root_dir) if os.path.isdir(f'{root_dir}/{dir_name}')]

def pretty_num(number:float) -> str:
    if number < 1000:
        return str(number)
    elif number < 1000000:
        return f'{round(number/1000,5)}K'
    elif number < 1000000000:
        return f'{round(number/1000000,5)}M'
    else:
        return f'{round(number/1000000000,5)}B'

def extract_num_from_str(string:str) -> float:
    return float(''.join([c for c in string if c.isdigit() or c == '.']))

def welford_parallel_update(count_a, mean_a, m2_a, count_b, mean_b, m2_b):
    """
    Combines two sets of partial statistics using Chan et al. parallel algorithm.
    M2 is defined as: sum((x - mean)^2)
    """
    total_count = count_a + count_b
    delta = mean_b - mean_a
    
    # New Mean
    combined_mean = mean_a + delta * (count_b / total_count)
    
    # New M2
    combined_m2 = m2_a + m2_b + (delta**2) * (count_a * count_b / total_count)
    
    return total_count, combined_mean, combined_m2

def get_global_mean_var(data_list: List[dict], method: Literal["welford", "normal"] = "welford") -> dict:
    """
    Aggregates a list of batch statistics into one.
    Supports input dicts with:
      - {'sum', 'sum_sq', 'count'} 
    """
    if method == "welford":
        count_acc = data_list[0]["count"]
        mean_acc = data_list[0]["sum"] / data_list[0]["count"]
        m2_acc = data_list[0]["sum_sq"] - (data_list[0]["sum"]**2 / data_list[0]["count"])

        # Merge remaining batches
        for i in range(1, len(data_list)):
            b = data_list[i]
            b_count = float(b["count"])
            
            
            b_mean = b["sum"] / b_count
            b_m2 = b["sum_sq"] - (b["sum"]**2 / b_count)

            # Update using the atomic Welford function
            count_acc, mean_acc, m2_acc = welford_parallel_update(
                count_acc, mean_acc, m2_acc,
                b_count, b_mean, b_m2
            )
    else:
        sum_acc, sum_sq_acc, count_acc = 0, 0, 0
        for r in data_list:
            sum_acc += r["sum"]
            sum_sq_acc += r["sum_sq"]
            count_acc += r["count"]
        mean_acc = sum_acc / count_acc
        m2_acc = sum_sq_acc - (sum_acc ** 2 / count_acc)

    return {
        "count": count_acc,
        "mean": mean_acc,
        "m2": m2_acc,
        "variance": np.maximum(m2_acc / count_acc, 0.0)
    }

    
