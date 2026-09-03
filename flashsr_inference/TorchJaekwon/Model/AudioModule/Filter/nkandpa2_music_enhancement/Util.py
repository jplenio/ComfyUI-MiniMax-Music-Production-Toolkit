from torch import Tensor

import torch
import torch.nn.functional as F

class Util:
    @staticmethod
    def batch_convolution(x, f, pad_both_sides=True):
        """
        Do batch-elementwise convolution between a batch of signals `x` and batch of filters `f`
        x: (batch_size x channels x signal_length) size tensor
        f: (batch_size x channels x filter_length) size tensor
        pad_both_sides: Whether to zero-pad x on left and right or only on left (Default: True)
        """
        batch_size = x.shape[0]
        f = torch.flip(f, (2,))
        if pad_both_sides:
            x = F.pad(x, (f.shape[2]//2, f.shape[2]-f.shape[2]//2-1))
        else:
            x = F.pad(x, (f.shape[2]-1, 0))
        #TODO: This assumes single-channel audio, fine for now 
        return F.conv1d(x.view(1, batch_size, -1), f, groups=batch_size).view(batch_size, 1, -1)
    
    @staticmethod
    def augment(sample, rir=None, noise=None, eq_model=None, low_cut_model=None, rate=16000, nsr_range=[-30,-5], normalize=True, eps=1e-6):
        sample = Util.perturb_silence(sample, eps=eps)
        clean_sample = torch.clone(sample)
        if not noise is None:
            nsr_target = ((nsr_range[1] - nsr_range[0])*torch.rand(noise.shape[0]) + nsr_range[0]).to(noise)
            sample = Util.apply_noise(sample, noise, nsr_target)
        if not rir is None:
            sample = Util.apply_reverb(sample, rir, None, rate=rate)
        if not eq_model is None:
            sample = eq_model(sample)
        if not low_cut_model is None:
            sample = low_cut_model(sample)
        if normalize:
            sample = 0.95*sample/sample.abs().max(dim=2, keepdim=True)[0]

        return clean_sample, sample
    
    @staticmethod
    def perturb_silence(sample, eps=1e-6):
        """
        Some samples have periods of silence which can cause numerical issues when taking log-spectrograms. Add a little noise
        """
        return sample + eps*torch.randn_like(sample)
    
    @staticmethod
    def apply_reverb(sample, rir, drr_target, rate=16000):
        """
        Convolve batch of samples with batch of room impulse responses scaled to achieve a target direct-to-reverberation ratio
        """
        if not drr_target is None:
            direct_ir, reverb_ir = Util.decompose_rir(rir, rate=rate)
            drr_db = Util.drr(direct_ir, reverb_ir)
            scale = 10**((drr_db - drr_target)/20)
            reverb_ir_scaled = scale[:, None, None]*reverb_ir
            rir_scaled = torch.cat((direct_ir, reverb_ir_scaled), axis=2)
        else:
            rir_scaled = rir
        return Util.batch_convolution(sample, rir_scaled, pad_both_sides=False)

    @staticmethod
    def apply_noise(sample, noise, nsr_target, peak=False):
        """
        Apply additive noise scaled to achieve target noise-to-signal ratio
        """
        if peak:
            nsr_curr = Util.pnsr(sample, noise)
            noise_flat = noise.view(noise.shape[0], -1)
            peak_noise = noise_flat.max(dim=1)[0] - noise_flat.min(dim=1)[0]
            scale = 10**((nsr_target - nsr_curr)/20)
        else:
            nsr_curr = Util.nsr(sample, noise)
            scale = torch.sqrt(10**((nsr_target - nsr_curr)/10))

        return sample + scale[:, None, None]*noise
    
    @staticmethod
    def apply_noise_wrt_snr(sample:Tensor, # [channel, signal_length]
                            noise:Tensor, # [channel, signal_length]
                            snr_target:float):
        """
        Apply additive noise scaled to achieve target noise-to-signal ratio
        """
        snr_curr = Util.nsr(noise, sample)
        scale = 1/torch.sqrt(10**((snr_target - snr_curr)/10))

        return sample + scale * noise

    @staticmethod
    def nsr(sample, noise):
        """
        Compute noise-to-signal ratio
        """
        sample, noise = sample.view(sample.shape[0], -1), noise.view(noise.shape[0], -1)
        signal_power = torch.square(sample).mean(dim=1)
        noise_power = torch.square(noise).mean(dim=1)
        return 10*torch.log10(noise_power/signal_power)

    @staticmethod
    def pnsr(sample, noise):
        """
        Compute peak noise-to-signal-ratio
        """
        sample, noise = sample.view(sample.shape[0], -1), noise.view(noise.shape[0], -1)
        peak_noise = noise.max(dim=1)[0] - noise.min(dim=1)[0]
        signal = torch.square(sample).mean(dim=1)
        return 20*torch.log10(peak_noise) - 10*torch.log10(signal)

    @staticmethod
    def drr(direct_ir, reverb_ir):
        """
        Compute direct-to-reverberation ratio
        """
        direct_ir_flat = direct_ir.view(direct_ir.shape[0], -1)
        reverb_ir_flat = reverb_ir.view(reverb_ir.shape[0], -1)
        drr_db = 10*torch.log10(torch.square(direct_ir_flat).sum(dim=1)/torch.square(reverb_ir_flat).sum(dim=1))
        return drr_db

    @staticmethod
    def decompose_rir(rir, rate=16000, window_ms=5):
        direct_window = int(window_ms/1000*rate)
        direct_ir, reverb_ir = rir[:,:,:direct_window], rir[:,:,direct_window:]
        return direct_ir, reverb_ir
    
    @staticmethod
    def preprocess_rir_wrt_window(rir, #[channel, signal_length]
                                  rate=16000, 
                                  window_ms=2.5):
        direct_impulse_index = rir.argmax().item()
        window_len = int(window_ms/1000*rate)
        if direct_impulse_index < window_len:
            rir = torch.cat((torch.zeros(1, window_len - direct_impulse_index), rir), dim=1)
        rir = rir[:, direct_impulse_index - window_len:]
        return rir