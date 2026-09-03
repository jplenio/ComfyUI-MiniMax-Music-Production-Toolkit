from typing import Union, Dict
from numpy import ndarray

import time
import random
import numpy as np
import torch
from torch.utils.data import IterableDataset

class IterablePytorchDataset(IterableDataset):
    def __init__(self,
                 data_type:Union[str,list] = None,
                 is_multiple_random_seed:bool = True,
                 random_seed:int = (int)(torch.cuda.initial_seed() / (2**32))
                 ) -> None:
        
        self.is_multiple_data_type:bool = isinstance(data_type,list)

        if self.is_multiple_data_type:
            self.data_type_list:list = data_type
            self.data_dict:Dict[str,ndarray] = self.init_data_dict()
            self.indexes_dict = { data_name: np.arange(len(self.data_dict[data_name])) for data_name in data_type }
            self.pointers_dict = {data_name: 0 for data_name in data_type}

            self.random_state_dict = {}
            for data_name in data_type:
                random_seed_for_data = np.random.RandomState(random_seed).randint(low=0, high=10000) if is_multiple_random_seed else random_seed
                self.random_state_dict[data_name] = np.random.RandomState(random_seed_for_data)
                self.random_state_dict[data_name].shuffle(self.indexes_dict[data_name])
                print("{}: {}".format(data_name, len(self.indexes_dict[data_name])))
        else:
            print('make data list')
            start = time.time()
            self.data_list = self.init_data_list()
            print(f"make data list: took {time.time() - start:.5f} sec")
            self.index:int = 0
            random.shuffle(self.data_list)
    
    def init_data_list(self) -> list:
        pass
    
    def init_data_dict(self) -> Dict[str,ndarray]: # {data_type1: List, data_type2: List}
        pass
    
    def __iter__(self):
        while True:
            data = self.get_data(self)
            yield data
    
    def get_data(self):
        if self.is_multiple_data_type:
            data_dict = dict()
            for data_name in self.data_type_list:
                if self.pointers_dict[data_name] >= len(self.indexes_dict[data_name]):
                    self.pointers_dict[data_name] = 0
                    self.random_state_dict[data_name].shuffle( self.indexes_dict[data_name] )
                data_dict[data_name] = self.read_data(self.data_dict[self.indexes_dict[data_name][self.pointers_dict[data_name]]])
            return data_dict
        else:
            self.index = self.index + 1
            if self.index == len(self.data_list):
                self.index = 0
                random.shuffle(self.data_list)
            return self.read_data(self.data_list[self.index])

    def read_data(self,meta_data):
        pass
