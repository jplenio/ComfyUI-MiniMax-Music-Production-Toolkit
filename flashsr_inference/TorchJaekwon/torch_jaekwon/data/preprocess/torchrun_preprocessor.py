import torch
from torch.utils.data.dataset import Dataset

from tqdm import tqdm
from torch.utils.data import DataLoader
from torch.utils.data.dataloader import default_collate

from ...util import util, util_torch_distributed
from ...path import ARTIFACTS_DIRS
from ...instantiate import instantiate_class_meta

def filter_none_collate(batch):
    batch = list(filter(lambda x: x is not None, batch))
    if len(batch) == 0:
        return None
    return default_collate(batch)

class TorchrunPreprocessor():
    def __init__(
        self, 
        data_name:str = 'all_data',
        dataset_manager_class_meta_dict:dict = dict(),
        root_dir:str = ARTIFACTS_DIRS.preprocessed_data,
        batch_size:int = 1,
        num_workers:int = 0,
        **kwargs
    ) -> None:
        self.data_name:str = data_name
        self.dataset_manager_dict = {k: instantiate_class_meta(class_meta=v) for k, v in dataset_manager_class_meta_dict.items()}
        self.root_dir:str = root_dir
        self.batch_size:int = batch_size
        self.num_workers:int = num_workers
        util_torch_distributed.torchrun_setup()
    
    # ==========================
    # Methods to Override (Start)
    # ==========================
    
    def get_dataset(self) -> Dataset:
        '''
        Returns the dataset for the preprocessor.
        This method should be overridden in subclasses.
        '''
        raise NotImplementedError("Subclasses must implement this method.")

    def preprocess_batch(self, batch:dict) -> None:
        '''
        Preprocess a batch of data.
        This method should be overridden in subclasses.
        '''
        raise NotImplementedError("Subclasses must implement this method.")

    def final_process(self) -> None:
        util.log("Finish preprocess", msg_type='success')
    
    # ==========================
    # Methods to Override (End)
    # ==========================

    def preprocess_data(self) -> None:
        dataset:Dataset = self.get_dataset()
        dataloader:DataLoader = util_torch_distributed.get_dataloader(
            dataloader_args={
                'dataset': dataset,
                'drop_last': False,
                'batch_size': self.batch_size,
                'num_workers': self.num_workers,
                'collate_fn': filter_none_collate,
            },
            shuffle=False,
        )
        util.log(f'Number of samples: {len(dataset)}', msg_type='info')
        util.log(f'Number of batches: {len(dataloader)}', msg_type='info')
        for data in tqdm(dataloader):
            if data is None: continue
            self.preprocess_batch(data)
        util_torch_distributed.barrier()
        if util_torch_distributed.is_main_process():
            self.final_process()
        util_torch_distributed.finish()

class ExampleDataset(Dataset):
    def __init__(self, meta_data_list:list) -> None:
        self.meta_data_list:list = meta_data_list
    
    def __len__(self):
        return len(self.meta_data_list)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        meta_data:dict = self.meta_data_list[idx]
        try:
            data_dict = meta_data
        except Exception as e:
            util.log(f"Error reading file {meta_data}: {e}", msg_type='error')
            return None
