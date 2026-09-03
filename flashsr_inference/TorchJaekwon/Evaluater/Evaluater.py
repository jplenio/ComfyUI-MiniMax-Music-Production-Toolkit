#type
from typing import List,Dict,Union
#import
import os
from tqdm import tqdm
import numpy as np
import torch
#torchjaekwon import
from TorchJaekwon.Util.UtilData import UtilData
#internal import

class Evaluater():
    def __init__(self,
                 source_dir:str,
                 reference_dir:str = None,
                 sort_result_by_metric:bool = True,
                 device:torch.device = torch.device('cpu')
                 ) -> None:
        self.source_dir:str = source_dir
        self.reference_dir:str = reference_dir
        self.sort_result_by_metric = sort_result_by_metric
        self.device:torch.device = device
    
    '''
    ==============================================================
    abstract method start
    ==============================================================
    '''
    def get_eval_dir_list(self) -> List[str]:
        return [self.source_dir]

    def get_meta_data_list(self, eval_dir:str) -> List[dict]:
        pass

    def get_result_dict_for_one_testcase(
        self,
        meta_data:dict
        ) -> dict: #{'name':name_of_testcase,'metric_name1':value1,'metric_name2':value2... }
        pass
    '''
    ==============================================================
    abstract method end
    ==============================================================
    '''
    def evaluate(self) -> None:
        eval_dir_list:List[str] = self.get_eval_dir_list()

        evaluation_result_dir:str = f"{self.source_dir}/_evaluation"
        os.makedirs(evaluation_result_dir,exist_ok=True)

        for eval_dir in tqdm(eval_dir_list, desc='evaluate eval dir'):
            meta_data_list: List[dict] = self.get_meta_data_list(eval_dir)
            result_dict:dict = self.get_result_dict(meta_data_list)
            result_dict['statistic'].update(self.set_eval(eval_dir=eval_dir))

            test_set_name:str = eval_dir.split('/')[-1]
            UtilData.yaml_save(f'{evaluation_result_dir}/{test_set_name}_mean_median_std.yaml',result_dict['statistic'])
            if self.sort_result_by_metric:
                for metric_name in result_dict['metric_name_list']:
                    UtilData.yaml_save(f'{evaluation_result_dir}/{test_set_name}_sort_by_{metric_name}.yaml',UtilData.sort_dict_list( dict_list = result_dict['result'], key = metric_name))
    
    def get_result_dict(self,meta_data_list:List[dict]) -> dict:
        result_dict_list:List[dict] = list()
        for meta_data in tqdm(meta_data_list,desc='get result'):
            result_dict_list.append(self.get_result_dict_for_one_testcase(meta_data))
        
        metric_name_list:list = [metric_name for metric_name in list(result_dict_list[0].keys()) if type(result_dict_list[0][metric_name]) in [float,np.float_]]
        metric_name_list.sort()
        mean_median_std_dict:dict = self.get_mean_median_std_from_dict_list(result_dict_list,metric_name_list)

        return {'metric_name_list': metric_name_list, 'result':result_dict_list, 'statistic':mean_median_std_dict}
    
    def get_mean_median_std_from_dict_list(self,dict_list:List[dict],metric_name_list:List[str]):
        result_list_dict:dict = {metric_name: list() for metric_name in metric_name_list}
        for result in dict_list:
            for metric_name in metric_name_list:
                result_list_dict[metric_name].append(result[metric_name])
        result_dict = dict()
        for metric_name in metric_name_list:
            result_dict[metric_name] = dict()
            result_dict[metric_name]['mean'] = float(np.mean(result_list_dict[metric_name]))
            result_dict[metric_name]['median'] = float(np.median(result_list_dict[metric_name]))
            result_dict[metric_name]['std'] = float(np.std(result_list_dict[metric_name]))
        return result_dict
    
    def set_eval(self, eval_dir:str) -> dict: #key: metric_name
        return dict()