from torch import Tensor
from numpy import ndarray

import librosa
import soundfile as sf
import torch
import torch.nn as nn

class ConvReverb(nn.Module):
    def __init__(self):
        super(ConvReverb,self).__init__()
    
    def conv_reverb_by_one_ir(
        self, 
        input_signal:Tensor, #(batch,sampletime_length)
        input_ir:Tensor #(batch,sampletime_length)
        ) -> Tensor:

        zero_padded_input_signal = nn.functional.pad(input_signal, (0, input_ir.shape[-1] - 1))
        input_signal_fft = torch.fft.rfft(zero_padded_input_signal, dim=1) #torch.rfft(zero_padded_input_signal, 1)

        zero_pad_final_fir = nn.functional.pad(input_ir, (0, input_signal.shape[-1] - 1))

        fir_fft = torch.fft.rfft(zero_pad_final_fir, dim=1) #torch.rfft(zero_pad_final_fir, 1)
        output_signal_fft:Tensor = fir_fft * input_signal_fft

        output_signal = torch.fft.irfft(output_signal_fft, dim=1) #torch.irfft(output_signal_fft, 1)

        return output_signal

    def forward(
        self, 
        input_signal:Tensor, #(batch,sampletime_length)
        input_ir:Tensor #(batch,sampletime_length)
        ) -> Tensor:
        assert ((len(input_signal.shape) == 2) or (len(input_signal.shape) == 3)), "input shape is wrong"
        if len(input_signal.shape) == 2:
            return self.conv_reverb_by_one_ir(input_signal,input_ir)
        else:
            left_reverb_audio:Tensor = self.conv_reverb_by_one_ir(input_signal[:,0,:],input_ir[:,0,:]).unsqueeze(1)
            right_reverb_audio:Tensor = self.conv_reverb_by_one_ir(input_signal[:,1,:],input_ir[:,1,:]).unsqueeze(1)
            reverb_audio:Tensor = torch.cat([left_reverb_audio,right_reverb_audio],axis=1)
            return reverb_audio

if __name__ == "__main__":
    vocal_audio_dir:str = "/home/jakeoneijk/220101_data/MusDBMainVocal/train/A Classic Education - NightOwl/A Classic Education - NightOwl_Main Vocal.wav"
    ir_dir:str = "/home/jakeoneijk/220101_data/DetmoldSRIRStereo/SetB_LSandWFSOrchestra/Data/OpenArray/wfs_R1/S1.wav"

    vocal_audio,sr = librosa.load(vocal_audio_dir,sr=None,mono=False)
    ir_audio,sr = librosa.load(ir_dir,sr=sr,mono=False)

    vocal_tensor:Tensor = torch.from_numpy(vocal_audio).unsqueeze(0)
    ir_tensor:Tensor = torch.from_numpy(ir_audio).unsqueeze(0)
    
    conv_reverb = ConvReverb()
    reverberated_audio:Tensor = conv_reverb(vocal_tensor,ir_tensor)
    reverberated_audio_numpy:ndarray = reverberated_audio.squeeze().numpy()
    sf.write("./reverb_audio.wav", data=reverberated_audio_numpy.T, samplerate=sr)