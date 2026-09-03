from torch import Tensor

import torch

from DataProcess.Util.UtilAudio import UtilAudio

class UtilAudioVocalPresence(UtilAudio):
    def __init__(self) -> None:
        super().__init__()
        self.energy_threshold:float = 4 #1
    
    def get_vocal_presence_from_raw_vocal_spec(
        self,
        raw_vocal_spec_mag:Tensor # (batch, audio_channel, frequency, time)
        ) -> Tensor:

        freq_dim = len(raw_vocal_spec_mag.shape) - 2

        vocal_energy:Tensor = raw_vocal_spec_mag * raw_vocal_spec_mag
        vocal_energy = torch.sum(vocal_energy, dim=freq_dim, keepdim=True)
        vocal_energy[vocal_energy<self.energy_threshold] = 0
        vocal_energy[vocal_energy>=self.energy_threshold] = 1

        return vocal_energy
    
    def apply_vocal_presence_to_spec(
        self,
        raw_vocal_spec_mag:Tensor, # (batch, audio_channel, frequency, time)
        voice_presence:Tensor
        )->Tensor:
        assert len(raw_vocal_spec_mag.shape) == 4, f"The shape of raw_vocal_spec_mag shpuld be (batch, audio_channel, frequency, time)"
        vocal_presence_mask:Tensor = voice_presence.repeat(1,1,raw_vocal_spec_mag.shape[2],1)
        return raw_vocal_spec_mag * vocal_presence_mask