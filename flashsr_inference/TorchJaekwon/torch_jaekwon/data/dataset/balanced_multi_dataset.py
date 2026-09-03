from typing import Dict

import numpy as np
import torch
from torch.utils.data import IterableDataset, get_worker_info
from ...util import util_torch_distributed
from ...train.logger.logger import Logger

class BalancedMultiDataset(IterableDataset):
    def __init__(
        self,
        sampling_schedule_dict:dict = None, # {'data1': 10, 'data2': 2}
        random_seed:int = None, # None -> derive from the current RNG in __init__ (avoids calling CUDA at import time)
        is_random_seed_per_dataset:bool = True,
        logger: Logger = None,
        is_debug: bool = False,
    ) -> None:
        self.data_list_dict: Dict[str,list] = self.init_data_list_dict() # {data_type1: List, data_type2: List}
        is_distributed: bool = util_torch_distributed.is_available()
        if util_torch_distributed.is_main_process():
            for data_name in self.data_list_dict: 
                print("{}: {}".format(data_name, len(self.data_list_dict[data_name])))

        self.distributed_shard_data(is_distributed)
        self.length_of_dataset:int = max([len(self.data_list_dict[data_name]) for data_name in self.data_list_dict])
        
        self.data_name_list_key:str = 'data_name'
        self.data_list_dict[self.data_name_list_key] = list(self.data_list_dict.keys())
        
        self.idx_dict = {data_name: -1 for data_name in self.data_list_dict} # it will start from 0 by adding 1

        self.sampling_schedule_dict = sampling_schedule_dict if sampling_schedule_dict is not None else {data_name: 1 for data_name in self.data_list_dict[self.data_name_list_key]}

        if random_seed is None:
            random_seed = int(torch.cuda.initial_seed() / (2**32)) if torch.cuda.is_available() else int(torch.initial_seed() / (2**32))

        self.random_state_dict = dict()
        self.random_state_dict[self.data_name_list_key] = np.random.RandomState(random_seed)
        self.random_state_dict[self.data_name_list_key].shuffle(self.data_list_dict[self.data_name_list_key])

        seed_rng = np.random.RandomState(random_seed) # one RNG that draws a distinct seed per dataset; re-creating RandomState(random_seed) inside the loop gave every dataset the same seed
        for data_name in self.data_list_dict[self.data_name_list_key]:
            dataset_seed:int = seed_rng.randint(low=0, high=10000) if is_random_seed_per_dataset else random_seed
            self.random_state_dict[data_name] = np.random.RandomState(dataset_seed)
            self.random_state_dict[data_name].shuffle(self.data_list_dict[data_name])
        
        self.logger: Logger = logger
        self.is_debug: bool = is_debug
    
    def distributed_shard_data(self, is_distributed: bool = False) -> None:
        if not is_distributed:
            return
        if not util_torch_distributed.is_available():
            raise RuntimeError("Distributed environment is not initialized. Please call util_torch_distributed.torchrun_setup() before using distributed sharding.")
        util_torch_distributed.log(f"Sharding dataset for distributed training.", msg_type='info', main_only=False)
        for data_name in self.data_list_dict: 
            self.data_list_dict[data_name] = util_torch_distributed.shard_list(self.data_list_dict[data_name])
            assert len(self.data_list_dict[data_name]) > 0, (f"[empty shard for dataset '{data_name}'. Try reducing world_size or check dataset size.")
    
    @staticmethod
    def worker_init_fn(worker_id:int) -> None:
        worker_info = get_worker_info()
        if worker_info is None: return
        assert worker_id == worker_info.id and worker_id < worker_info.num_workers, "worker_id should be same with worker_info.id"
        num_workers:int = worker_info.num_workers
        dataset = worker_info.dataset
        for dataset_name in [dataset_name for dataset_name in dataset.data_list_dict.keys() if dataset_name != dataset.data_name_list_key]:
            dataset.data_list_dict[dataset_name] = util_torch_distributed.shard_list(dataset.data_list_dict[dataset_name], worker_id, num_workers)
            assert len(dataset.data_list_dict[dataset_name]) > 0, f"Each worker should have at least one data. Please set num_workers <= {len(dataset.data_list_dict[dataset_name])}"
    
    # ==========================
    # Methods to Override (Start)
    # ==========================
    
    def init_data_list_dict(self) -> Dict[str,list]: # {data_type1: List, data_type2: List}
        raise NotImplementedError("You must implement the init_data_list_dict method in the subclass.")

    def read_data(self, meta_data:dict):
        raise NotImplementedError("You must implement the read_data method in the subclass.")
    
    # ==========================
    # Methods to Override (End)
    # ==========================

    def __iter__(self):
        while True:
            data_name:str = self.get_value(self.data_name_list_key)
            for _ in range(self.sampling_schedule_dict.get(data_name, 1)): # default 1 so a partial schedule doesn't KeyError mid-iteration
                meta_data = self.get_value(data_name)
                if self.is_debug and self.logger is not None:
                    self.logger.log_write(f"{util_torch_distributed.local_rank()}/{util_torch_distributed.world_size() - 1}: {str(meta_data)}", log_type='debug')
                data = self.read_data(meta_data)
                yield data

    def get_value(self, key:str) -> None:
        self.idx_dict[key] += 1
        if self.idx_dict[key] == len(self.data_list_dict[key]):
            self.idx_dict[key] = 0
            self.random_state_dict[key].shuffle(self.data_list_dict[key])
        value = self.data_list_dict[key][self.idx_dict[key]]
        return value

    def __len__(self):
        return self.length_of_dataset

    
