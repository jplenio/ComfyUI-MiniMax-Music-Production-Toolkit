from typing import Union, Dict
from numpy import ndarray

import time
import random
import numpy as np
import torch
from torch.utils.data import IterableDataset
from torch.utils.data.dataset import Dataset

class EvenSampleFromMultipleDataset(IterableDataset):
    def __init__(self,
                 is_multiple_random_seed:bool = True,
                 random_seed:int = (int)(torch.cuda.initial_seed() / (2**32))
                 ) -> None:
        self.data_list_dict: Dict[str,list] = self.init_data_list_dict() # {data_type1: List, data_type2: List}
        self.data_set_class_list = list(self.data_list_dict.keys())

        self.idx_dict = {data_name: 0 for data_name in self.data_list_dict}
        self.idx_dict['data_class'] = 0

        self.random_state_dict = dict()
        self.random_state_dict['data_class'] = np.random.RandomState(random_seed)
        self.random_state_dict['data_class'].shuffle(self.data_set_class_list)

        for data_name in self.data_list_dict:
            random_seed_for_data = np.random.RandomState(random_seed).randint(low=0, high=10000) if is_multiple_random_seed else random_seed
            self.random_state_dict[data_name] = np.random.RandomState(random_seed_for_data)
            self.random_state_dict[data_name].shuffle(self.data_list_dict[data_name])
            print("{}: {}".format(data_name, len(self.data_list_dict[data_name])))
    
    def init_data_list_dict(self) -> Dict[str,list]: # {data_type1: List, data_type2: List}
        pass

    def read_data(self,meta_data):
        pass
    
    def __iter__(self):
        while True:
            self.idx_dict['data_class'] = self.idx_dict['data_class'] + 1
            if self.idx_dict['data_class'] == len(self.data_set_class_list):
                self.idx_dict['data_class'] = 0
                self.random_state_dict['data_class'].shuffle(self.data_set_class_list)
            data_class:str = self.data_set_class_list[self.idx_dict['data_class']]

            self.idx_dict[data_class] = self.idx_dict[data_class] + 1
            if self.idx_dict[data_class] == len(self.data_list_dict[data_class]):
                self.idx_dict[data_class] = 0
                self.random_state_dict[data_class].shuffle(self.data_list_dict[data_class])
            
            data = self.read_data(self.data_list_dict[data_class][self.idx_dict[data_class]])
            
            yield data
    
    def __len__(self):
        return max([len(self.data_list_dict[data_name]) for data_name in self.data_list_dict])

    
