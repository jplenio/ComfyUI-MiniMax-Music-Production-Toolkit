from typing import Union
from torch import Tensor
from numpy import ndarray

import os
import json
import torch

from HParams import HParams
from DataProcess.Util.UtilAudioMelSpec import UtilAudioMelSpec
from Model.vocoder.hifigan.env import AttrDict
from Model.vocoder.hifigan.models import Generator

class UtilHiFiGanWrapper:
    def __init__(self,h_params:HParams):
        self.h_params:HParams = h_params

        self.util_mel = UtilAudioMelSpec(self.h_params)

        self.hifi_gan_generator : Generator
        self.load_hifi_gan()
    
    def load_hifi_gan(self):
        pretrain_name = self.h_params.process.hi_fi_gan_pretrained_name_list[self.h_params.process.hi_fi_gan_pretrain_idx]
        pretrain_path = "./Model/vocoder/hifigan/pretrained/" + pretrain_name
        config_file = os.path.join(pretrain_path, 'config.json')
        with open(config_file) as f:
            data = f.read()
        json_config = json.loads(data)
        h = AttrDict(json_config)
        self.hifi_gan_generator = Generator(h)
        if "MUS_DB" in pretrain_name:
            state_dict_g = torch.load(pretrain_path + "/generator.pt", map_location='cpu')
            self.hifi_gan_generator.load_state_dict(state_dict_g)
        else:
            state_dict_g = torch.load(pretrain_path + "/generator", map_location='cpu')
            self.hifi_gan_generator.load_state_dict(state_dict_g['generator'])
        self.hifi_gan_generator = self.hifi_gan_generator.to(self.h_params.resource.device)
        self.hifi_gan_generator.eval()
        self.hifi_gan_generator.remove_weight_norm()
    
    def audio_to_hifi_gan_mel(self,audio:Union[Tensor,ndarray]) -> Tensor:
        audio_tensor:Tensor = audio if type(audio) == Tensor else torch.from_numpy(audio)
        spectrogram:Tensor = self.util_mel.stft_torch(audio_tensor)["mag"]
        mel:Tensor =  self.util_mel.spec_to_mel_spec(spectrogram)
        return self.util_mel.dynamic_range_compression(mel)
    
    def generate_audio_by_hifi_gan(self,input_feature:Union[Tensor,ndarray]) -> ndarray:
        final_shape_len = 3

        if type(input_feature) != torch.Tensor:
            input_feature = torch.from_numpy(input_feature)

        for _ in range(final_shape_len - len(input_feature.shape)):
            input_feature = torch.unsqueeze(input_feature, 0)

        input_feature = input_feature.to(self.h_params.resource.device)
        
        with torch.no_grad():
            #in: (batch,mel_size,time) , out: (batch,channel,time)
            audio = self.hifi_gan_generator(input_feature)
            audio = audio.squeeze()
            audio = audio.cpu().numpy()
        return audio