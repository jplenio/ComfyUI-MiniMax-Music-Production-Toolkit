# Copyright (c) 2022 NVIDIA CORPORATION. 
#   Licensed under the MIT license.

# Adapted from https://github.com/jik876/hifi-gan under the MIT license.
#   LICENSE is in incl_licenses directory.
from torch import Tensor

from TorchJaekwon.Util.Util import Util
from TorchJaekwon.Util.UtilData import UtilData
from TorchJaekwon.Util.UtilAudioMelSpec import UtilAudioMelSpec
#from easydict import EasyDict
#Util.set_sys_path_to_parent_dir(__file__, depth_to_dir_from_file=2)

import torch
import torch.nn.functional as F
import torch.nn as nn
from torch.nn import Conv1d, ConvTranspose1d, Conv2d
from torch.nn.utils import weight_norm, remove_weight_norm, spectral_norm

import FlashSR.BigVGAN.activations as activations
from FlashSR.BigVGAN.utils import init_weights, get_padding
from FlashSR.BigVGAN.alias_free_torch import *

LRELU_SLOPE = 0.1

class SRVocoder(torch.nn.Module):
    def __init__(self,
                 num_mels = 256,
                 upsample_initial_channel = 1536,
                 resblock_kernel_sizes = [3, 7, 11],
                 resblock_dilation_sizes = [[1, 3, 5], [1, 3, 5], [1, 3, 5]],
                 upsample_rates = [10, 6, 2, 2, 2], #[4, 4, 2, 2, 2, 2], upsample_rates = [5, 4, 3, 2, 2, 2], #[4, 4, 2, 2, 2, 2],
                 upsample_kernel_sizes = None, # upsample_kernel_sizes = [7,8,7,4,4,4],
                 activation = 'snakebeta',
                 snake_logscale = True
                 ):
        super(SRVocoder, self).__init__()
        if upsample_kernel_sizes is None:
            upsample_kernel_sizes = [upsample_rate * 2 for upsample_rate in upsample_rates]

        self.audio_block = nn.ModuleDict()
        self.audio_block["downsamples"] = nn.ModuleList()
        self.audio_block["emb"] = Conv1d( 1, upsample_initial_channel // (2 ** len(upsample_rates)), 7, bias=True, padding=(7 - 1) // 2, )
        for i in reversed(range(len(upsample_kernel_sizes))):
            self.audio_block["downsamples"] += [
                nn.Sequential(
                    nn.Conv1d(
                        upsample_initial_channel // (2 ** (i + 1)),
                        upsample_initial_channel // (2 ** i),
                        upsample_kernel_sizes[i],
                        upsample_rates[i],
                        padding=upsample_rates[i] - (upsample_kernel_sizes[i] % 2 == 0),
                        bias=True,
                    ),
                    nn.LeakyReLU(negative_slope = 0.1)
                )
            ]

        self.num_kernels = len(resblock_kernel_sizes)
        self.num_upsamples = len(upsample_rates)

        # pre conv
        self.conv_pre = weight_norm(Conv1d(num_mels, upsample_initial_channel, 7, 1, padding=3))

        # define which AMPBlock to use. BigVGAN uses AMPBlock1 as default
        resblock = AMPBlock1

        # transposed conv-based upsamplers. does not apply anti-aliasing
        self.ups = nn.ModuleList()
        for i, (u, k) in enumerate(zip(upsample_rates, upsample_kernel_sizes)):
            self.ups.append(nn.ModuleList([
                weight_norm(ConvTranspose1d(upsample_initial_channel // (2 ** i),
                                            upsample_initial_channel // (2 ** (i + 1)),
                                            k, u, padding=(k - u) // 2))
            ]))

        # residual blocks using anti-aliased multi-periodicity composition modules (AMP)
        self.resblocks = nn.ModuleList()
        for i in range(len(self.ups)):
            ch = upsample_initial_channel // (2 ** (i + 1))
            for j, (k, d) in enumerate(zip(resblock_kernel_sizes, resblock_dilation_sizes)):
                self.resblocks.append(resblock(ch, k, d, activation=activation))

        # post conv
        if activation == "snake": # periodic nonlinearity with snake function and anti-aliasing
            activation_post = activations.Snake(ch, alpha_logscale=snake_logscale)
            self.activation_post = Activation1d(activation=activation_post)
        elif activation == "snakebeta": # periodic nonlinearity with snakebeta function and anti-aliasing
            activation_post = activations.SnakeBeta(ch, alpha_logscale=snake_logscale)
            self.activation_post = Activation1d(activation=activation_post)
        else:
            raise NotImplementedError("activation incorrectly specified. check the config file and look for 'activation'.")

        self.conv_post = weight_norm(Conv1d(ch, 1, 7, 1, padding=3))

        # weight initialization
        for i in range(len(self.ups)):
            self.ups[i].apply(init_weights)
        self.conv_post.apply(init_weights)
        '''
        In audio sr
        sampling_rate = 48000
        filter_length = 2048
        hop_length = 480
        win_length = 2048
        n_mel = 256
        mel_fmin = 20
        mel_fmax = 24000
        '''

    def forward(self, 
                mel_spec:Tensor, #[batch, mel_size, time//hop]
                lr_audio:Tensor, #[batch, time]
                ) -> Tensor: #[batch, time]
        
        audio_emb:Tensor = self.audio_block["emb"](lr_audio.unsqueeze(1))
        audio_emb_list:list = [audio_emb]
        for i in range(self.num_upsamples - 1):
            audio_emb = self.audio_block["downsamples"][i](audio_emb)
            audio_emb_list += [audio_emb]

        # pre conv
        x = self.conv_pre(mel_spec)

        for i in range(self.num_upsamples):
            # upsampling
            for i_up in range(len(self.ups[i])):
                x = self.ups[i][i_up](x) + audio_emb_list[-1-i]
            # AMP blocks
            xs = None
            for j in range(self.num_kernels):
                if xs is None:
                    xs = self.resblocks[i * self.num_kernels + j](x)
                else:
                    xs += self.resblocks[i * self.num_kernels + j](x)
            x = xs / self.num_kernels

        # post conv
        x = self.activation_post(x)
        x = self.conv_post(x)
        x = torch.tanh(x).squeeze(1)

        return {'pred_hr_audio': x }

    def remove_weight_norm(self):
        print('Removing weight norm...')
        for l in self.ups:
            for l_i in l:
                remove_weight_norm(l_i)
        for l in self.resblocks:
            l.remove_weight_norm()
        remove_weight_norm(self.conv_pre)
        remove_weight_norm(self.conv_post)


class AMPBlock1(torch.nn.Module):
    def __init__(self, channels, kernel_size=3, dilation=(1, 3, 5), activation=None, snake_logscale = 'snakebeta'):
        super(AMPBlock1, self).__init__()

        self.convs1 = nn.ModuleList([
            weight_norm(Conv1d(channels, channels, kernel_size, 1, dilation=dilation[0],
                               padding=get_padding(kernel_size, dilation[0]))),
            weight_norm(Conv1d(channels, channels, kernel_size, 1, dilation=dilation[1],
                               padding=get_padding(kernel_size, dilation[1]))),
            weight_norm(Conv1d(channels, channels, kernel_size, 1, dilation=dilation[2],
                               padding=get_padding(kernel_size, dilation[2])))
        ])
        self.convs1.apply(init_weights)

        self.convs2 = nn.ModuleList([
            weight_norm(Conv1d(channels, channels, kernel_size, 1, dilation=1,
                               padding=get_padding(kernel_size, 1))),
            weight_norm(Conv1d(channels, channels, kernel_size, 1, dilation=1,
                               padding=get_padding(kernel_size, 1))),
            weight_norm(Conv1d(channels, channels, kernel_size, 1, dilation=1,
                               padding=get_padding(kernel_size, 1)))
        ])
        self.convs2.apply(init_weights)

        self.num_layers = len(self.convs1) + len(self.convs2) # total number of conv layers

        if activation == 'snake': # periodic nonlinearity with snake function and anti-aliasing
            self.activations = nn.ModuleList([
                Activation1d(
                    activation=activations.Snake(channels, alpha_logscale=snake_logscale))
                for _ in range(self.num_layers)
            ])
        elif activation == 'snakebeta': # periodic nonlinearity with snakebeta function and anti-aliasing
            self.activations = nn.ModuleList([
                Activation1d(
                    activation=activations.SnakeBeta(channels, alpha_logscale=snake_logscale))
                 for _ in range(self.num_layers)
            ])
        else:
            raise NotImplementedError("activation incorrectly specified. check the config file and look for 'activation'.")

    def forward(self, x):
        acts1, acts2 = self.activations[::2], self.activations[1::2]
        for c1, c2, a1, a2 in zip(self.convs1, self.convs2, acts1, acts2):
            xt = a1(x)
            xt = c1(xt)
            xt = a2(xt)
            xt = c2(xt)
            x = xt + x

        return x

    def remove_weight_norm(self):
        for l in self.convs1:
            remove_weight_norm(l)
        for l in self.convs2:
            remove_weight_norm(l)
