# source: https://github.com/haoheliu/versatile_audio_super_resolution
import librosa
import numpy as np
import torch

from TorchJaekwon.Util.UtilData import UtilData
from TorchJaekwon.Util.UtilTorch import UtilTorch

class UtilAudioSR:

    @staticmethod
    def mel_replace_ops(predict_mel:torch.Tensor,       #[batch, 1, time, melbin], log mel spectrogram
                        gt_low_pass_mel:torch.Tensor,   #[batch, 1, time, melbin], log mel spectrogram
                        debug_message:bool=False
                        ) -> torch.Tensor:              #[batch, 1, time, melbin]
        batch_size = predict_mel.size(0)
        for i in range(batch_size):
            cutoff_melbin = UtilAudioSR.locate_cutoff_freq(torch.exp(gt_low_pass_mel[i].squeeze()))

            if debug_message:
                ratio = predict_mel[i][...,:cutoff_melbin]/gt_low_pass_mel[i][...,:cutoff_melbin]
                print(torch.mean(ratio), torch.max(ratio), torch.min(ratio))

            predict_mel[i][..., :cutoff_melbin] = gt_low_pass_mel[i][..., :cutoff_melbin]
        return predict_mel
    
    @staticmethod
    def locate_cutoff_freq(stft, percentile=0.985):
        magnitude = torch.abs(stft)
        energy = torch.cumsum(torch.sum(magnitude, dim=0), dim=0)
        return UtilAudioSR.find_cutoff(energy, percentile)
    
    @staticmethod
    def find_cutoff(x, percentile=0.95):
        percentile = x[-1] * percentile
        for i in range(1, x.shape[0]):
            if x[-i] < percentile:
                return x.shape[0] - i
        return 0
    
    @staticmethod
    def wav_replace_ops(pred_wav:torch.Tensor,          #[batch, 1, time]
                        gt_low_pass_wav:torch.Tensor    #[batch, 1, time]
                        ) -> torch.Tensor:              #[batch, 1, time]
        device = pred_wav.device
        pred_wav = UtilData.fit_shape_length(pred_wav, 2).cpu().detach().numpy()
        gt_low_pass_wav = UtilData.fit_shape_length(gt_low_pass_wav, 2).cpu().detach().numpy()
        for i in range(pred_wav.shape[0]):

            out = pred_wav[i]
            x = gt_low_pass_wav[i]
            cutoffratio = UtilAudioSR.get_cutoff_index_np(x)

            length = out.shape[0]
            stft_gt = librosa.stft(x)

            stft_out = librosa.stft(out)
            energy_ratio = np.mean(
                np.sum(np.abs(stft_gt[cutoffratio]))
                / np.sum(np.abs(stft_out[cutoffratio, ...]))
            )
            energy_ratio = min(max(energy_ratio, 0.8), 1.2)
            stft_out[:cutoffratio, ...] = stft_gt[:cutoffratio, ...] / energy_ratio

            out_renewed = librosa.istft(stft_out, length=length)
            pred_wav[i] = out_renewed
        
        return torch.FloatTensor(pred_wav).to(device)
    
    @staticmethod
    def get_cutoff_index_np(x):
        stft_x = np.abs(librosa.stft(x))
        energy = np.cumsum(np.sum(stft_x, axis=-1))
        return UtilAudioSR.find_cutoff(energy, 0.985)
    
    @staticmethod
    def find_cutoff_freq(audio:torch.Tensor) -> int:
        stft_spec = torch.stft(
            input = audio,
            n_fft = 2048,
            hop_length=480,
            win_length=2048,
            window=torch.hann_window(2048).to(audio.device),
            center=False,
            pad_mode="reflect",
            normalized=False,
            onesided=True,
            return_complex=True,
        )

        stft_spec = stft_spec[0].T.float()
        cutoff_freq = (UtilAudioSR.locate_cutoff_freq(stft_spec, percentile=0.983) / 1024) * 24000
        if(cutoff_freq < 1000):
            cutoff_freq = 24000
        return cutoff_freq