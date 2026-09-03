from typing import List

from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor
import os
import time
import torch
from tqdm import tqdm

class Preprocessor(ABC):
    def __init__(self,
                 data_name:str = None,
                 root_dir:str = None,
                 device:torch.device = None,
                 num_workers:int = 1,
                 ) -> None:
        # args to class variable
        self.data_name:str = data_name
        self.root_dir:str = root_dir
        self.num_workers:int = num_workers
        self.device:torch.device = device
        if self.root_dir is not None and self.data_name is not None:
            self.output_dir = self.get_output_dir()
            os.makedirs(self.output_dir,exist_ok=True)
        else:
            print('Warning: root_dir or data_name is None')
    
    def get_output_dir(self) -> str:
        return os.path.join(self.root_dir, self.data_name)
    
    def write_message(self,message_type:str,message:str) -> None:
        with open(f"{self.preprocessed_data_path}/{message_type}.txt",'a') as file_writer:
            file_writer.write(message+'\n')
    
    def preprocess_data(self) -> None:
        meta_param_list:list = self.get_meta_data_param()
        if meta_param_list is None:
            print('meta_param_list is None, So we skip preprocess data')
            return
        start_time:float = time.time()
        if self.num_workers > 2:
            with ProcessPoolExecutor(max_workers=self.num_workers) as pool:
                pool.map(self.preprocess_one_data, meta_param_list)
        else:
            for meta_param in tqdm(meta_param_list,desc='preprocess data'):
                self.preprocess_one_data(meta_param)

        self.final_process()
        print("{:.3f} s".format(time.time() - start_time))

    @abstractmethod
    def get_meta_data_param(self) -> list:
        '''
        meta_data_param_list = list()
        '''
        raise NotImplementedError
    
    @abstractmethod
    def preprocess_one_data(self,param: tuple) -> None:
        '''
        ex) (subset, file_name) = param
        '''
        raise NotImplementedError
    
    def final_process(self) -> None:
        print("Finish preprocess")