from typing import Dict
from torch.utils.data import Dataset, DataLoader

from HParams import HParams
from TorchJaekwon.GetModule import GetModule

class PytorchDataLoader:
    def __init__(self):
        self.h_params = HParams()
        self.data_loader_config:dict = self.h_params.pytorch_data.dataloader
    
    def get_pytorch_data_loaders(self) -> Dict[str,DataLoader]: #subset,dataloader
        pytorch_dataset_dict:Dict[str,Dataset] = self.get_pytorch_data_set_dict() #key: subset, value: dataset
        pytorch_data_loader_config_dict:dict = self.get_pytorch_data_loader_args(pytorch_dataset_dict)
        pytorch_data_loader_dict:Dict[str,DataLoader] = self.get_pytorch_data_loaders_from_config(pytorch_data_loader_config_dict)
        return pytorch_data_loader_dict
    
    def get_pytorch_data_set_dict(self) -> Dict[str,Dataset]:
        pytorch_dataset_dict:Dict[str,Dataset] = dict()
        for subset in self.data_loader_config:
            dataset_args:dict = self.data_loader_config[subset]["dataset"]['class_meta']['args']
            pytorch_dataset_dict[subset] = GetModule.get_module_class('./Data/PytorchDataset',self.data_loader_config[subset]["dataset"]['class_meta']["name"])(**dataset_args)
        return pytorch_dataset_dict
    
    def get_pytorch_data_loader_args(self,pytorch_dataset:dict) -> dict:
        pytorch_data_loader_config_dict:dict = {subset:dict() for subset in pytorch_dataset}

        for subset in pytorch_dataset:
            args_exception_list = self.get_exception_list_of_dataloader_parameters(subset)
            pytorch_data_loader_config_dict[subset]["dataset"] = pytorch_dataset[subset]
            for arg_name in self.data_loader_config[subset]:
                if arg_name in args_exception_list:
                    continue
                if arg_name == 'batch_sampler':
                    arguments_for_args_class:dict = self.h_params.pytorch_data.dataloader[subset]['batch_sampler']
                    arguments_for_args_class.update({"pytorch_dataset":pytorch_dataset[subset],"subset":subset})
                    pytorch_data_loader_config_dict[subset][arg_name] = GetModule.get_module_class('./Data/PytorchDataLoader',
                                                                                             self.data_loader_config[subset][arg_name]["class_name"]
                                                                                             )(arguments_for_args_class)
                elif arg_name == 'collate_fn':
                    if self.data_loader_config[subset][arg_name] == True: pytorch_data_loader_config_dict[subset][arg_name] = pytorch_data_loader_config_dict[subset]["dataset"].collate_fn
                else:
                    pytorch_data_loader_config_dict[subset][arg_name] = self.data_loader_config[subset][arg_name]
        
        return pytorch_data_loader_config_dict
    
    def get_exception_list_of_dataloader_parameters(self,subset):
        args_exception_list = ["dataset"]
        if "batch_sampler" in self.data_loader_config[subset]:
            args_exception_list += ["batch_size", "shuffle", "sampler", "drop_last"]
        return args_exception_list

    def get_pytorch_data_loaders_from_config(self,dataloader_config:dict) -> dict:
        pytorch_data_loader_dict = dict()
        for subset in dataloader_config:
            pytorch_data_loader_dict[subset] = DataLoader(**dataloader_config[subset])
        return pytorch_data_loader_dict



    