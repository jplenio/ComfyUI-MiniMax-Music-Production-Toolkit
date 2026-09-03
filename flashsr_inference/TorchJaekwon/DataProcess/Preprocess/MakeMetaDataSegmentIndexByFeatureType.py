import os
import pickle

from HParams import HParams
from DataProcess.MakeMetaData.MakeMetaData import MakeMetaData

class MakeMetaDataSegmentIndexByFeatureType(MakeMetaData):
    r"""Create and write out training indexes into disk. The indexes may contain
    information from multiple datasets. During training, training indexes will
    be shuffled and iterated for selecting segments to be mixed. E.g., the
    training indexes_dict looks like: {
        'audio_vocals': [
            {'name':..}
            ...
        ]
        'audio_accompaniment': [
            {'name':..}
            ...
        ]
    }
    """

    def __init__(self, h_params:HParams, make_meta_data_config:dict) -> None:
        super().__init__(h_params,make_meta_data_config)
        config:dict = make_meta_data_config

        self.feature_list = config["feature_list"]
        self.config_of_subset_dict:dict = config["config_of_subset"]
        
        self.sample_rate:int = self.h_params.preprocess.sample_rate
        self.file_ext = ".pkl"

        self.result_file_name = config["result_file_name"]
        
    def make_meta_data(self):
        for subset in self.config_of_subset_dict:
            segment_index_dict:dict = {feature_type: [] for feature_type in self.feature_list}
            segment_samples_length = int(self.h_params.make_meta_data.segment_seconds * self.sample_rate)
            
            if "hopsize" in self.config_of_subset_dict[subset]:
                segment_samples_hop_size:int = self.config_of_subset_dict[subset]["hopsize"]
            else:
                segment_samples_hop_size = int(self.config_of_subset_dict[subset]["hop_seconds"] * self.sample_rate)

            for feature_type in segment_index_dict:
                print("--- {} ---".format(feature_type))
                segment_data_num = 0

                for data_root_path in self.data_root_path_list:
                    data_path = os.path.join(data_root_path,subset)
                    data_name_list = sorted(os.listdir(data_path))

                    for i, data_name in enumerate(data_name_list):
                        print(f"{feature_type} of {data_name} ({i+1} / {len(data_name_list)})")
                        file_path = os.path.join(os.path.join(data_path,data_name),feature_type) + self.file_ext
                        with open(file_path, 'rb') as pickle_file:
                            feature = pickle.load(pickle_file)
                        
                        begin_sample = 0
                        while begin_sample + segment_samples_length < feature.shape[-1]:
                            segment_index_dict[feature_type].append(
                                {
                                    "name": data_name,
                                    "data_path": file_path,
                                    "feature_type": feature_type,
                                    "begin_sample":begin_sample,
                                    "end_sample": begin_sample + segment_samples_length
                                })
                            begin_sample += segment_samples_hop_size
                            segment_data_num += 1
                    print("{} indexes: {}".format(data_root_path, segment_data_num))   
                print( "Total indexes for {}: {}".format(feature_type, len(segment_index_dict[feature_type])))
            
            pickle.dump(segment_index_dict, open(os.path.join(self.h_params.data.root_path,self.result_file_name), "wb"))
            print("Write index dict to {}".format(os.path.join(self.h_params.data.root_path,self.result_file_name)))