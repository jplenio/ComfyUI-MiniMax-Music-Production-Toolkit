from typing import Union,Dict,List
from numpy import ndarray
from torch import Tensor

import os
from tqdm import tqdm
import random
import copy
import numpy as np
import torch
import torch.nn.functional as F
import pickle, yaml, csv, json
from pathlib import Path
from inspect import isfunction

class UtilData:

    @staticmethod
    def get_file_name(file_path:str, with_ext:bool = False) -> str:
        if file_path is None:
            print("warning: path is None")
            return ""
        path_pathlib = Path(file_path)
        if with_ext:
            return path_pathlib.name
        else:
            return path_pathlib.stem
    
    @staticmethod
    def pickle_save(save_path:str, data:Union[ndarray,Tensor]) -> None:
        if not (os.path.splitext(save_path)[1] == ".pkl"):
            print("file extension should be '.pkl'")
            save_path = f'{save_path}.pkl'

        os.makedirs(os.path.dirname(save_path),exist_ok=True)
        
        with open(save_path,'wb') as file_writer:
            pickle.dump(data,file_writer)
    
    @staticmethod
    def pickle_load(data_path:str) -> Union[ndarray,Tensor]:
        with open(data_path, 'rb') as pickle_file:
            data:Union[ndarray,Tensor] = pickle.load(pickle_file)
        return data
    
    @staticmethod
    def yaml_save(save_path:str, data:Union[dict,list], sort_keys:bool = False) -> None:
        assert(os.path.splitext(save_path)[1] == ".yaml") , "file extension should be '.yaml'"

        with open(save_path, 'w') as file:
            yaml.dump(data, file, sort_keys = sort_keys, allow_unicode=True)
    
    @staticmethod
    def yaml_load(data_path:str) -> dict:
        yaml_file = open(data_path, 'r')
        return yaml.safe_load(yaml_file)
    
    @staticmethod
    def csv_load(data_path:str) -> list:
        row_result_list = list()
        with open(data_path, newline='') as csvfile:
            spamreader = csv.reader(csvfile)#, delimiter=' ', quotechar='|')
            for row in spamreader:
                row_result_list.append(row)
        return row_result_list
    
    @staticmethod
    def txt_load(data_path:str) -> list:
        with open(data_path, 'r') as txtfile:
            return txtfile.readlines()
    
    @staticmethod
    def txt_save(save_path:str, string_list:List[str], new_file:bool = True) -> list:
         os.makedirs(os.path.dirname(save_path), exist_ok=True)
         with open(save_path, 'w' if new_file else 'a') as file:
            for line in string_list:
                file.write(f'{line}\n')
    
    @staticmethod
    def csv_save(file_path:str,
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
    
    @staticmethod
    def json_load(file_path:str) -> dict:
        with open(file_path) as f: data = f.read()
        return json.loads(data)

    @staticmethod
    def save_data_segment(save_dir:str,data:ndarray,segment_len:int,segment_axis:int=-1,remainder:str = ['discard','pad','maintain'][1],ext:str = ['pkl'][0]):
        os.makedirs(save_dir,exist_ok=True)
        data_total = copy.deepcopy(data)
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
                UtilData.pickle_save(f'{save_dir}/{start_idx}.{ext}',data_segment)
    
    @staticmethod
    def fit_shape_length(feature:Union[Tensor,ndarray],shape_length:int, dim:int = 0) -> Tensor:
        if shape_length == len(feature.shape):
            return feature
        if type(feature) != torch.Tensor:
            feature = torch.from_numpy(feature)
        
        feature = torch.squeeze(feature)

        for _ in range(shape_length - len(feature.shape)):
            feature = torch.unsqueeze(feature, dim=dim)
        
        return feature
    
    @staticmethod
    def sort_dict_list( dict_list: List[dict], key:str, reverse:bool = False):
        return sorted(dict_list, key = lambda dictionary: dictionary[key], reverse=reverse)
    
    @staticmethod
    def random_segment(data:ndarray, data_length:int) -> ndarray:
        max_data_start = len(data) - data_length
        data_start = random.randint(0, max_data_start)
        return data[data_start:data_start+data_length]
    
    @staticmethod
    def default(val, d):
        if val is not None:
            return val
        return d() if isfunction(d) else d
    
    @staticmethod
    def fix_length(data:Union[ndarray,Tensor],
                   length:int,
                   dim:int = -1
                   ) -> Tensor:
        assert len(data.shape) in [1,2,3], "Error[UtilData.fix_length] only support when data.shape is 1, 2 or 3"
        if data.shape[dim] < length:
            if isinstance(data,Tensor):
                return F.pad(data, (0,length - data.shape[dim]), "constant", 0)
            else:
                return F.pad(torch.from_numpy(data), (0,length - data.shape[dim]), "constant", 0).numpy()
        elif data.shape[dim] == length:
            return data
        else:
            assert dim == -1, "Error[UtilData.fix_length] slicing when dim is not -1 not implemented yet"
            return data[..., :length]
    
    @staticmethod
    def listdir(dir_name:str, ext:Union[str,list] = ['.wav', '.mp3', '.flac']) -> list:
        if ext is None:
            return os.listdir(dir_name)
        elif isinstance(ext,list):
            return [{'file_name': file_name, 'file_path':f'{dir_name}/{file_name}'} for file_name in os.listdir(dir_name) if os.path.splitext(file_name)[1] in ext]
        else:
            return [{'file_name': file_name, 'file_path':f'{dir_name}/{file_name}'} for file_name in os.listdir(dir_name) if os.path.splitext(file_name)[1] == ext]
    
    @staticmethod
    def walk(dir_name:str, ext:list = ['.wav', '.mp3', '.flac']) -> list:
        file_meta_list:list = list()
        for root, _, files in os.walk(dir_name):
            for filename in tqdm(files, desc=f'walk {root}'):
                if os.path.splitext(filename)[-1] in ext:
                    file_meta_list.append({
                        'file_name': UtilData.get_file_name( file_path = filename ),
                        'file_path': f'{root}/{filename}',
                        'dir_name': root.replace(dir_name,'').replace('/',''),
                        'dir_path': root,
                    })
        return file_meta_list
    
    @staticmethod
    def get_dir_name_list(root_dir:str) -> list:
        return [dir_name for dir_name in os.listdir(root_dir) if os.path.isdir(f'{root_dir}/{dir_name}')]
    
    @staticmethod
    def pretty_num(number:float) -> str:
        if number < 1000:
            return str(number)
        elif number < 1000000:
            return f'{round(number/1000,5)}K'
        elif number < 1000000000:
            return f'{round(number/1000000,5)}M'
        else:
            return f'{round(number/1000000000,5)}B'
    
    @staticmethod
    def extract_num_from_str(string:str) -> float:
        return float(''.join([c for c in string if c.isdigit() or c == '.']))

        
