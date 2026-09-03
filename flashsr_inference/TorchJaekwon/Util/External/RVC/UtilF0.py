try: import parselmouth
except: print('[Import Error] parselmouth')
try: import pyworld
except: print('[Import Error] pyworld')

from typing import Literal

import numpy as np

class UtilF0(object):
    def __init__(self,
                 samplerate=16000, 
                 hop_size=160):
        self.fs = samplerate
        self.hop = hop_size

        self.f0_mel_bin = 256
        self.f0_max = 1100.0
        self.f0_min = 50.0
        self.f0_mel_min = 1127 * np.log(1 + self.f0_min / 700)
        self.f0_mel_max = 1127 * np.log(1 + self.f0_max / 700)
    
    def printt(self, strr):
        print(strr)
        self.f.write("%s\n" % strr)
        self.f.flush()

    def compute_f0(self, 
                   audio:np.ndarray,#[time]
                   f0_method:Literal['pm','harvest','dio'] = 'harvest'
                   )->np.ndarray: #[time//hop]
        p_len = audio.shape[0] // self.hop
        if f0_method == "pm":
            time_step = 160 / 16000 * 1000
            f0_min = 50
            f0_max = 1100
            f0 = (
                parselmouth.Sound(audio, self.fs)
                .to_pitch_ac(
                    time_step=time_step / 1000,
                    voicing_threshold=0.6,
                    pitch_floor=f0_min,
                    pitch_ceiling=f0_max,
                )
                .selected_array["frequency"]
            )
            pad_size = (p_len - len(f0) + 1) // 2
            if pad_size > 0 or p_len - len(f0) - pad_size > 0:
                f0 = np.pad(
                    f0, [[pad_size, p_len - len(f0) - pad_size]], mode="constant"
                )
        elif f0_method == "harvest":
            f0, t = pyworld.harvest(
                audio.astype(np.double),
                fs=self.fs,
                f0_ceil=self.f0_max,
                f0_floor=self.f0_min,
                frame_period=1000 * self.hop / self.fs,
            )
            f0 = pyworld.stonemask(audio.astype(np.double), f0, t, self.fs)
        elif f0_method == "dio":
            f0, t = pyworld.dio(
                audio.astype(np.double),
                fs=self.fs,
                f0_ceil=self.f0_max,
                f0_floor=self.f0_min,
                frame_period=1000 * self.hop / self.fs,
            )
            f0 = pyworld.stonemask(audio.astype(np.double), f0, t, self.fs)
        elif f0_method == "rmvpe":
            if hasattr(self, "model_rmvpe") == False:
                from lib.rmvpe import RMVPE

                print("loading rmvpe model")
                self.model_rmvpe = RMVPE("rmvpe.pt", is_half=False, device="cpu")
            f0 = self.model_rmvpe.infer_from_audio(x, thred=0.03)
        return f0

    def get_f0_mel_index(self, f0):
        f0_mel = 1127 * np.log(1 + f0 / 700)
        f0_mel[f0_mel > 0] = (f0_mel[f0_mel > 0] - self.f0_mel_min) * (
            self.f0_mel_bin - 2
        ) / (self.f0_mel_max - self.f0_mel_min) + 1

        # use 0 or 1
        f0_mel[f0_mel <= 1] = 1
        f0_mel[f0_mel > self.f0_mel_bin - 1] = self.f0_mel_bin - 1
        f0_coarse = np.rint(f0_mel).astype(int)
        assert f0_coarse.max() <= 255 and f0_coarse.min() >= 1, (
            f0_coarse.max(),
            f0_coarse.min(),
        )
        return f0_coarse