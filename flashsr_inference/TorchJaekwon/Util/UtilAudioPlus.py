from typing import Dict
from numpy import ndarray

import resampy
import torch
import torchcrepe
import numpy as np

from TorchJAEKWON.DataProcess.Util.UtilAudio import UtilAudio

class UtilAudioPlus(UtilAudio):
    def get_pitch_crepe(self,
                        wav:ndarray, #mono 1d array
                        sample_rate:float,
                        hop_size:int,
                        spec_time_bin_length:int,
                        f0_min:float = 50.0,
                        f0_max:float = 1100.0,
                        threshold:float=0.05,
                        device = torch.device("cuda")) -> Dict[str,ndarray]:
        
        wav16k = resampy.resample(wav, sample_rate, 16000)
        wav16k_torch = torch.FloatTensor(wav16k).unsqueeze(0).to(device)

        f0, pd = torchcrepe.predict(wav16k_torch, 16000, 80, f0_min, f0_max, pad=True, model='full', batch_size=1024, device=device, return_periodicity=True)

        pd = torchcrepe.filter.median(pd, 3)
        pd = torchcrepe.threshold.Silence(-60.)(pd, wav16k_torch, 16000, 80)
        f0 = torchcrepe.threshold.At(threshold)(f0, pd)
        f0 = torchcrepe.filter.mean(f0, 3)

        f0 = torch.where(torch.isnan(f0), torch.full_like(f0, 0), f0)
        
        nzindex = torch.nonzero(f0[0]).squeeze()
        f0 = torch.index_select(f0[0], dim=0, index=nzindex).cpu().numpy()
        time_org = 0.005 * nzindex.cpu().numpy()
        time_frame = np.arange(spec_time_bin_length) * hop_size / sample_rate
        if f0.shape[0] == 0:
            f0 = torch.FloatTensor(time_frame.shape[0]).fill_(0)
            print('f0 all zero!')
        else:
            f0 = np.interp(time_frame, time_org, f0, left=f0[0], right=f0[-1])
        pitch_coarse = self.f0_to_coarse(f0)
        return {'f0':f0, 'pitch':pitch_coarse}

    def f0_to_coarse(self,
                     f0:ndarray,
                     f0_bin:int = 256,
                     f0_min:float = 50.0,
                     f0_max:float = 1100.0) -> ndarray:
        
        is_torch = isinstance(f0, torch.Tensor)
        f0_mel_min = 1127 * np.log(1 + f0_min / 700)
        f0_mel_max = 1127 * np.log(1 + f0_max / 700)
        f0_mel = 1127 * (1 + f0 / 700).log() if is_torch else 1127 * np.log(1 + f0 / 700)
        f0_mel[f0_mel > 0] = (f0_mel[f0_mel > 0] - f0_mel_min) * (f0_bin - 2) / (f0_mel_max - f0_mel_min) + 1

        f0_mel[f0_mel <= 1] = 1
        f0_mel[f0_mel > f0_bin - 1] = f0_bin - 1
        f0_coarse = (f0_mel + 0.5).long() if is_torch else np.rint(f0_mel).astype(int)
        assert f0_coarse.max() <= 255 and f0_coarse.min() >= 1, (f0_coarse.max(), f0_coarse.min())
        return f0_coarse