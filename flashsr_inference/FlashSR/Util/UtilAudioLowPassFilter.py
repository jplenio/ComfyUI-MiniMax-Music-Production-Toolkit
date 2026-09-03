
#from TorchJaekwon.Util.Util import Util
#Util.set_sys_path_to_parent_dir(__file__, 2)

from typing import Literal
from numpy import ndarray

import numpy as np
from scipy.signal import butter, cheby1, cheby2, ellip, bessel, sosfiltfilt, resample_poly

class UtilAudioLowPassFilter:
    # this code is refactored version of https://github.com/haoheliu/ssr_eval

    @staticmethod
    def lowpass(audio:ndarray, #[time] 1d array
                sr:int,
                filter_name:Literal["cheby","butter","bessel","ellip"],
                filter_order:int,
                cutoff_freq:int,
                upsample_to_original:bool = True   
                ):
        assert len(audio.shape) == 1 or (len(audio.shape) == 2 and (audio.shape[0] == 1 or audio.shape[0] == 2))
        if filter_name == "cheby": filter_name = "cheby1"
        assert filter_order >= 2 and filter_order <= 10, f"filter_order should be between 2 and 10, but {filter_order} is given"
        if cutoff_freq == sr: cutoff_freq -= 1
        if len(audio.shape) == 2:
            lowpassed_audio = np.zeros_like(audio)
            for i in range(audio.shape[0]):
                lowpassed_audio[i] = UtilAudioLowPassFilter.lowpass_filter( x=audio[i], highcutoff_freq=int(cutoff_freq), fs=sr, order=filter_order, ftype=filter_name, upsample_to_original = upsample_to_original)
        else:
            lowpassed_audio = UtilAudioLowPassFilter.lowpass_filter( x=audio, highcutoff_freq=int(cutoff_freq), fs=sr, order=filter_order, ftype=filter_name, upsample_to_original = upsample_to_original)
        if upsample_to_original:
            assert lowpassed_audio.shape == audio.shape, f'error lowpass_butterworth: {str((lowpassed_audio.shape, audio.shape))}'
        return lowpassed_audio.copy() # avoid the problem [Torch.from_numpy not support negative strides]
    

    
    @staticmethod
    def lowpass_filter(x:ndarray, #[time] 1d array
                       highcutoff_freq:float, #high cutoff frequency
                       fs:int, 
                       order:int, #the order of filter
                       ftype:Literal['butter', 'cheby1', 'cheby2', 'ellip', 'bessel'],
                       upsample_to_original:bool = True
                       ) -> ndarray: #[time] 1d array
        nyq = 0.5 * fs
        hi = highcutoff_freq / nyq
        if ftype == "butter":
            sos = butter(order, hi, btype="low", output="sos")
        elif ftype == "cheby1":
            sos = cheby1(order, 0.1, hi, btype="low", output="sos")
        elif ftype == "cheby2":
            sos = cheby2(order, 60, hi, btype="low", output="sos")
        elif ftype == "ellip":
            sos = ellip(order, 0.1, 60, hi, btype="low", output="sos")
        elif ftype == "bessel":
            sos = bessel(order, hi, btype="low", output="sos")
        else:
            raise Exception(f"The lowpass filter {ftype} is not supported!")

        y = sosfiltfilt(sos, x)

        if len(y) != len(x):
            y = UtilAudioLowPassFilter.align_length(x, y)
        # After low pass filtering. Resample the audio signal
        y = UtilAudioLowPassFilter.subsampling(y, lowpass_ratio=highcutoff_freq / int(fs / 2), fs_ori=fs, upsample_to_original = upsample_to_original)
        return y
    
    @staticmethod
    def align_length(x, y):
        """align the length of y to that of x

        Args:
            x (np.array): reference signal
            y (np.array): the signal needs to be length aligned

        Return:
            yy (np.array): signal with the same length as x
        """
        Lx = len(x)
        Ly = len(y)

        if Lx == Ly:
            return y
        elif Lx > Ly:
            # pad y with zeros
            return np.pad(y, (0, Lx - Ly), mode="constant")
        else:
            # cut y
            return y[:Lx]
    
    @staticmethod
    def subsampling(data, lowpass_ratio, fs_ori=44100, upsample_to_original:bool = True):
        assert len(data.shape) == 1
        fs_down = int(lowpass_ratio * fs_ori)
        # downsample to the low sampling rate
        y = resample_poly(data, fs_down, fs_ori)

        if upsample_to_original:
            # upsample to the original sampling rate
            y = resample_poly(y, fs_ori, fs_down)

            if len(y) != len(data):
                y = UtilAudioLowPassFilter.align_length(data, y)
        return y
    
if __name__ == "__main__":
    util = UtilAudioLowPassFilter()
    util.lowpass(np.zeros(24000),48000, filter_name="cheby", filter_order=8, cutoff_freq=8000)