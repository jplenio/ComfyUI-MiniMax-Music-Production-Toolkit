from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import torch
from tqdm import tqdm
from ...path import ARTIFACTS_DIRS
from ...instantiate import instantiate_class_meta

class Preprocessor():
    def __init__(
        self,
        data_name:str = 'all_data',
        dataset_manager_class_meta_dict:dict = dict(),
        root_dir:str = ARTIFACTS_DIRS.preprocessed_data,
        device:torch.device = None,
        num_workers:int = 1,
    ) -> None:
        # args to class variable
        self.data_name:str = data_name
        self.dataset_manager_dict = {k: instantiate_class_meta(class_meta=v) for k, v in dataset_manager_class_meta_dict.items()}
        self.root_dir:str = root_dir
        self.num_workers:int = num_workers
        self.device:torch.device = device
        self.max_meta_data_len:int = 10000
    
    # ==========================
    # Methods to Override (Start)
    # ==========================
    
    def get_meta_data_param(self) -> list:
        '''
        meta_data_param_list = list().
        you may want to set output path to each meta_data
        '''
        for dataset_name, dataset_manager in self.dataset_manager_dict.items():
            raise NotImplementedError
    
    @staticmethod
    def preprocess_one_data(param:dict) -> None:
        '''
        ex) (subset, file_name) = param
        '''
        raise NotImplementedError
    
    def final_process(self, result_list:list) -> None:
        print("Finish preprocess")
    
    # ==========================
    # Methods to Override (End)
    # ==========================
    
    def preprocess_data(self) -> None:
        meta_param_list: list = self.get_meta_data_param()

        print(f'Total meta data count: {len(meta_param_list)}')
        result_list = list()
        start_time: float = time.time()
        process_func = self.__class__.preprocess_one_data

        # 2. Open the pool ONCE for the entire dataset
        if self.num_workers > 1:
            print(f"Starting {self.num_workers} workers...")
            with ProcessPoolExecutor(max_workers=self.num_workers) as pool:
                futures = {pool.submit(process_func, param): param for param in meta_param_list}
                
                with tqdm(total=len(futures), desc='Parallel Preprocess') as pbar:
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            if result is not None:
                                result_list.append(result)
                        except Exception as e:
                            failed_param = futures[future]
                            print(f"\n[ERROR] Worker failed on {failed_param.get('tar_path')}: {e}")
                        
                        pbar.update(1)
        else:
            for meta_param in tqdm(meta_param_list, desc='Serial Preprocess'):
                try:
                    result = process_func(meta_param)
                    if result is not None:
                        result_list.append(result)
                except Exception as e:
                    print(f"\n[ERROR] Failed on {meta_param.get('tar_path')}: {e}")

        self.final_process(result_list)
        print("\n--- Preprocessing Complete ---")
        print("Total time: {:.3f} s".format(time.time() - start_time))