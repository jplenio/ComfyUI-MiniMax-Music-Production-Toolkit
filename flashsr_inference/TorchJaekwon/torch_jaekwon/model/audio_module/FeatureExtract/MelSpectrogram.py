from torch import Tensor

import torch
import torch.nn as nn
from librosa.filters import mel as librosa_mel_fn

class MelSpectrogram(nn.Module):
    def __init__(self, 
                 sample_rate:int,
                 nfft: int, 
                 hop_size: int,
                 mel_size:int, 
                 frequency_min:float,
                 frequency_max:float) -> None:
        super().__init__()
        # [mel_size, nfft // 2 + 1]
        self.nfft,self.hop_size,self.mel_size = nfft,hop_size,mel_size
        self.register_buffer(
            'mel_filterbank',
            torch.from_numpy(librosa_mel_fn(sr = sample_rate, 
                                            n_fft = nfft, 
                                            n_mels = mel_size, 
                                            fmin = frequency_min, 
                                            fmax = frequency_max)).float(),
            persistent=False)
        self.register_buffer(
            'hann_window', torch.hann_window(nfft), persistent=False)
    
    def forward(self, 
                audio: Tensor #[torch.float32; [B, T]], audio signal, [-1, 1]-ranged.
                ) -> Tensor: #[torch.float32; [B, mel, T / strides]], mel spectrogram
        if torch.min(audio) < -1.:
            print('min value is ', torch.min(audio))
        if torch.max(audio) > 1.:
            print('max value is ', torch.max(audio))

        # [BatchSize, nfft // 2 + 1, T / hop_size]
        spec:Tensor = torch.stft(  audio,
                            n_fft=self.nfft,
                            hop_length=self.hop_size,
                            window=self.hann_window,
                            center=True, pad_mode='reflect',
                            return_complex=True)
        # [BatchSize, nfft // 2 + 1, T / hop_size]
        mag:Tensor = abs(spec)
        # [BatchSize, mel_size, T / hop_size]
        return torch.matmul(self.mel_filterbank, mag)
    
    def get_log_mel(self, 
                audio: Tensor #[torch.float32; [B, T]], audio signal, [-1, 1]-ranged.
                ) -> Tensor: #[torch.float32; [B, mel, T / strides]], mel spectrogram
        mel_spec:Tensor = self.forward(audio)
        return torch.log(mel_spec + 1e-7)
    
    def get_dynamic_range_compresed_mel(
            self,
            audio: Tensor #[torch.float32; [B, T]], audio signal, [-1, 1]-ranged.
            ) -> Tensor: #[torch.float32; [B, mel, T / strides]], mel spectrogram
        #used in hi-fi gan
        mel_spec:Tensor = self.forward(audio)
        return self.dynamic_range_compression(mel_spec)
    
    def dynamic_range_compression(self, x, C=1, clip_val=1e-5):
        return torch.log(torch.clamp(x, min=clip_val) * C)
