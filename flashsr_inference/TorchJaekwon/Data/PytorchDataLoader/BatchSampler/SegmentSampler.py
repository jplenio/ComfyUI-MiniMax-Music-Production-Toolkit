import pickle
from typing import Dict, List, NoReturn

import numpy as np
from HParams import HParams
from TorchJAEKWON.DataProcess.Util.UtilData import UtilData

class SegmentSampler:
    def __init__(
        self,
        args_dict: dict
    ):
        r"""Sample training indexes of sources.
        Args:
            indexes_path: str, path of indexes dict
            input_source_types: list of str, e.g., ['vocals', 'accompaniment']
            target_source_types: list of str, e.g., ['vocals']
            segment_samplers: int
            mixaudio_dict, dict, mix-audio data augmentation parameters,
                e.g., {'voclas': 2, 'accompaniment': 2}
            batch_size: int
            steps_per_epoch: int, #steps_per_epoch is called an `epoch`
            random_seed: int
        """
        self.h_params = HParams()
        self.config = args_dict
        self.subset = args_dict["subset"]

        self.mix_data_augmentation_num = self.config["mix_data_augmentation_num"]
        self.mix_data_augmentation = self.config["mix_data_augmentation"]
        self.batch_size = self.h_params.pytorch_data.dataloader[self.subset]["batch_size"]
        self.steps_per_epoch = self.config["steps_per_epoch"]
        self.source_list:list = self.h_params.preprocess.feature_list

        self.meta_dict = UtilData.pickle_load(self.config["indexes_dict_path"])
        # E.g., {
        #     'vocals': [
        #         {'hdf5_path': 'songA.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 0, 'end_sample': 132300}，
        #         {'hdf5_path': 'songB.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 4410, 'end_sample': 445410},
        #         ... (e.g., 225752 dicts)
        #     ],
        #     'accompaniment': [
        #         {'hdf5_path': 'songA.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 0, 'end_sample': 132300}，
        #         {'hdf5_path': 'songB.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 4410, 'end_sample': 445410},
        #         ... (e.g., 225752 dicts)
        #     ]
        # }

        self.pointers_dict = {source_type: 0 for source_type in self.source_list}
        # E.g., {'vocals': 0, 'accompaniment': 0}

        self.indexes_dict = {
            source_type: np.arange(len(self.meta_dict[source_type]))
            for source_type in self.source_list
        }
        # E.g. {
        #     'vocals': [0, 1, ..., 225751],
        #     'accompaniment': [0, 1, ..., 225751]
        # }

        random_state_for_source_random_seed = np.random.RandomState(self.config["random_seed"])
        self.random_state_dict = {}

        for source_type in self.source_list:

            if self.mix_data_augmentation:
                # Use different seeds for different sources.
                source_random_seed = random_state_for_source_random_seed.randint(low=0, high=10000)

            else:
                # Use same seeds for different sources.
                source_random_seed = self.config["random_seed"]

            self.random_state_dict[source_type] = np.random.RandomState(
                source_random_seed
            )

            self.random_state_dict[source_type].shuffle(self.indexes_dict[source_type])
            # E.g., [198036, 196736, ..., 103408]

            print("{}: {}".format(source_type, len(self.indexes_dict[source_type])))

    def __iter__(self) -> List[Dict]:
        r"""Yield a batch of meta info.
        Returns:
            batch_meta_list: (batch_size,) e.g., when mix-audio is 2, looks like [
                {'vocals': [
                    {'hdf5_path': 'songA.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 13406400, 'end_sample': 13538700},
                    {'hdf5_path': 'songB.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 4440870, 'end_sample': 4573170}]
                'accompaniment': [
                    {'hdf5_path': 'songE.h5', 'key_in_hdf5': 'accompaniment', 'begin_sample': 14579460, 'end_sample': 14711760},
                    {'hdf5_path': 'songF.h5', 'key_in_hdf5': 'accompaniment', 'begin_sample': 3995460, 'end_sample': 4127760}]
                },
                ...
            ]
        """
        batch_size = self.batch_size

        while True:
            batch_meta_dict = {source_type: [] for source_type in self.source_list}

            for source_type in self.source_list:
                # E.g., ['vocals', 'accompaniment']

                # Loop until get a mini-batch.
                while len(batch_meta_dict[source_type]) != batch_size:

                    if source_type in self.mix_data_augmentation_num.keys():
                        mix_audios_num = self.mix_data_augmentation_num[source_type]

                    else:
                        mix_audios_num = 1

                    largest_index = len(self.indexes_dict[source_type]) - mix_audios_num
                    # E.g., 225750 = 225752 - 2

                    if self.pointers_dict[source_type] > largest_index:

                        # Reset pointer, and shuffle indexes.
                        self.pointers_dict[source_type] = 0
                        self.random_state_dict[source_type].shuffle(
                            self.indexes_dict[source_type]
                        )

                    source_metas = []

                    for _ in range(mix_audios_num):

                        pointer = self.pointers_dict[source_type]
                        # E.g., 1

                        index = self.indexes_dict[source_type][pointer]
                        # E.g., 12231

                        self.pointers_dict[source_type] += 1

                        source_meta = self.meta_dict[source_type][index]
                        # E.g., {
                        #     'hdf5_path': 'xx/song_A.h5',
                        #     'key_in_hdf5': 'vocals',
                        #     'begin_sample': 13406400,
                        # }

                        source_metas.append(source_meta)

                    batch_meta_dict[source_type].append(source_metas)

            # When mix-audio is 2, batch_meta_dict looks like: {
            #     'vocals': [
            #         [{'hdf5_path': 'songA.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 13406400, 'end_sample': 13538700},
            #          {'hdf5_path': 'songB.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 4440870, 'end_sample': 4573170}
            #         ],
            #         ... (batch_size)
            #     ]
            #     'accompaniment': [
            #         [{'hdf5_path': 'songG.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 24232950, 'end_sample': 24365250},
            #          {'hdf5_path': 'songH.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 1569960, 'end_sample': 1702260}
            #         ],
            #         ... (batch_size)
            #     ]
            # }

            batch_meta_list = [
                {
                    source_type: batch_meta_dict[source_type][i]
                    for source_type in self.source_list
                }
                for i in range(batch_size)
            ]
            # When mix-audio is 2, batch_meta_list looks like: [
            #     {'vocals': [
            #         {'hdf5_path': 'songA.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 13406400, 'end_sample': 13538700},
            #         {'hdf5_path': 'songB.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 4440870, 'end_sample': 4573170}]
            #      'accompaniment': [
            #         {'hdf5_path': 'songE.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 14579460, 'end_sample': 14711760},
            #         {'hdf5_path': 'songF.h5', 'key_in_hdf5': 'vocals', 'begin_sample': 3995460, 'end_sample': 4127760}]
            #     }
            #     ... (batch_size)
            # ]

            yield batch_meta_list

    def __len__(self) -> int:
        return self.steps_per_epoch

    def state_dict(self) -> Dict:
        state = {'pointers_dict': self.pointers_dict, 'indexes_dict': self.indexes_dict}
        return state

    def load_state_dict(self, state) -> NoReturn:
        self.pointers_dict = state['pointers_dict']
        self.indexes_dict = state['indexes_dict']