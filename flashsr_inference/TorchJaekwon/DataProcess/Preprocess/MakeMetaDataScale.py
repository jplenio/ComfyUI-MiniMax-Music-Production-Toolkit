import os
from DataProcess.MakeMetaData.MakeMetaData import MakeMetaData
import sklearn.preprocessing
import copy
import tqdm
import numpy as np
from HParams import HParams
from GetModule import GetModule
from Data.PytorchDataLoader.PytorchDataLoader import PytorchDataLoader
from DataProcess.Process.Process import Process

class MakeMetaDataScale(MakeMetaData):

    def __init__(self,h_params:HParams, make_meta_data_config:dict) -> None:
        super().__init__(h_params,make_meta_data_config)
        
        self.get_module = GetModule()
        self.data_loader_loader:PytorchDataLoader = self.get_module.get_module('pytorch_dataLoader',self.h_params.pytorch_data.name,self.h_params)
        
        if self.h_params.process.name is not None:
            self.data_processor:Process = self.get_module.get_module("process",self.h_params.process.name, {"h_params":self.h_params},arg_unpack=True)
        else:
            self.data_processor = None

    def make_meta_data(self):
        train_data_path = self.data_loader_loader.get_data_path_dict()["train"]
        pytorch_data_set = self.get_pytorch_data_set(train_data_path=train_data_path)
        result = self.get_statistics(pytorch_data_set)
        print("end")
    
    def get_pytorch_data_set(self,train_data_path) -> dict:
        dataset_config = self.h_params.make_meta_data.make_meta_data_dict["MakeMetaDataScale"]["dataset"]
        config_for_dataset = {
                "h_params": self.h_params,
                "data_path_list": train_data_path,
                "subset": "train",
                "data_set_config": dataset_config
        }
        pytorch_dataset = self.get_module.get_module("pytorch_dataset", dataset_config["name"],config_for_dataset)
        return pytorch_dataset
    
    def get_statistics(self, dataset):
        standard_scaler = dict()
        minmax_scaler = dict()

        pbar = tqdm.tqdm(range(len(dataset)), disable=False)
        for ind in pbar:
            feature_dict = dataset[ind]
            for feature_name in feature_dict:
                feature_dict[feature_name] = feature_dict[feature_name].astype(np.float32)
            pbar.set_description("Compute dataset statistics")

            if self.data_processor is not None:
                dataset_config = self.h_params.pytorch_data.dataloader["train"]['dataset']
                train_data_name_dict = dict()
                train_data_name_dict["input_name"] = dataset_config["train_source_name_dict"]["input"]
                train_data_name_dict["target_name"] = dataset_config["train_source_name_dict"]["target"]
                train_data_dict = self.data_processor.preprocess_training_data(feature_dict,additional_dict=train_data_name_dict)
            else:
                train_data_dict = feature_dict

            for feature_name in train_data_dict:
                if feature_name not in standard_scaler:
                    standard_scaler[feature_name] = sklearn.preprocessing.StandardScaler()
                    minmax_scaler[feature_name] = sklearn.preprocessing.MinMaxScaler()
                
                train_data_dict[feature_name] = train_data_dict[feature_name].squeeze()
                train_data_dict[feature_name] = np.transpose(train_data_dict[feature_name],(0,2,1))
                train_data_dict[feature_name] = train_data_dict[feature_name].reshape(-1,train_data_dict[feature_name].shape[-1])
                
                standard_scaler[feature_name].partial_fit(train_data_dict[feature_name])
                minmax_scaler[feature_name].partial_fit(train_data_dict[feature_name])

        result = dict()
        for feature_name in standard_scaler:
            result[feature_name] = dict()
            result[feature_name]["mean"] = standard_scaler[feature_name].mean_
            result[feature_name]["std"] = np.maximum(standard_scaler[feature_name].scale_, 1e-4 * np.max(standard_scaler[feature_name].scale_))
            result[feature_name]["max_by_bin"] = minmax_scaler[feature_name].data_max_
            result[feature_name]["min_by_bin"] = minmax_scaler[feature_name].data_min_
            result[feature_name]["max"] = np.max(result[feature_name]["max_by_bin"])
            result[feature_name]["min"] = np.min(result[feature_name]["min_by_bin"])

        return result