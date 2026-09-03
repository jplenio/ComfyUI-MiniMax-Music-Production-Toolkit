from torch import Tensor

import torch
import torch.nn as nn
import numpy as np
from scipy import signal

from TorchJaekwon.Model.AudioModule.Filter.nkandpa2_music_enhancement.Util import Util  

class MicrophoneEQ(nn.Module):
    """
    Apply a random EQ on bands demarcated by `bands`
    """
    def __init__(self, low_db=-15, hi_db=15, bands=[200, 1000, 4000], filter_length=8192, rate=16000):
        super(MicrophoneEQ, self).__init__()
        self.low_db = low_db
        self.hi_db = hi_db
        self.rate = rate
        self.filter_length = filter_length
        self.firs = nn.Parameter(self.create_filters(bands))

    def create_filters(self, bands):
        """
        Generate bank of FIR bandpass filters with band cutoffs specified by `bands`
        """
        ir = np.zeros([self.filter_length])
        ir[0] = 1
        bands = [35] + bands
        fir = np.zeros([len(bands) + 1, self.filter_length])
        for j in range(len(bands)):
            freq = bands[j] / (self.rate/2)
            bl, al = signal.butter(4, freq, btype='low')
            bh, ah = signal.butter(4, freq, btype='high')
            fir[j] = signal.lfilter(bl, al, ir)
            ir = signal.lfilter(bh, ah, ir)
        fir[-1] = ir
        pfir = np.square(np.abs(np.fft.fft(fir,axis=1)))
        pfir = np.real(np.fft.ifft(pfir, axis=1))
        fir = np.concatenate((pfir[:,self.filter_length//2:self.filter_length], pfir[:,0:self.filter_length//2]), axis=1)
        return torch.tensor(fir, dtype=torch.float32)

    def get_eq_filter(self, band_gains):
        """
        Apply `band_gains` to bank of FIR bandpass filters to get the final EQ filter
        """
        band_gains = 10**(band_gains/20)
        eq_filter = (band_gains[:,:,None] * self.firs[None,:,:]).sum(dim=1, keepdim=True)
        return eq_filter

    def forward(self, 
                x, # [batch, signal, length]
                gain=None):
        gains = self.get_random_gain(batch_size=x.shape[0]) if gain is None else gain
        gains = torch.cat((torch.zeros((x.shape[0], 1), device=self.firs.device), gains), dim=1)
        eq_filter = self.get_eq_filter(gains)
        eq_x = Util.batch_convolution(x, eq_filter, pad_both_sides=True)
        return eq_x
    
    def get_random_gain(self, batch_size:int = 1) -> Tensor:
        return (self.hi_db - self.low_db)*torch.rand(batch_size, self.firs.shape[0]-1, device=self.firs.device) + self.low_db
    