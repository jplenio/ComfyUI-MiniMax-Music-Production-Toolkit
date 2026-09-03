#%%
from matplotlib import pyplot as plt
import torch
from torch.nn import functional as F
import numpy as np
# %%
def smooth_lbl_loop(lbl, smooth_center, smooth_length, smooth_shape):
    lbl_new = lbl.clone().detach().float()
    lbl_copy = lbl.clone().detach()
    lbl_weight = torch.zeros(smooth_length // 2)

    for i in range(lbl_weight.size(0)):
        if smooth_shape == 'square':
            lbl_weight[i] = 1
        elif smooth_shape == 'triangle':
            lbl_weight[i] = 1 - (i + 1) / (smooth_length // 2 + 1)
        elif smooth_shape == 'hann':
            lbl_weight[i] = np.hanning(smooth_length + 2)[(smooth_length + 2) // 2 + 1 + i]

    for i in range(1, lbl_weight.size(0) + 1):
        if smooth_center:
            lbl_new[i:] += lbl_copy[:-i] * lbl_weight[i - 1]
            lbl_new[:-i] += lbl_copy[i:] * lbl_weight[i - 1]
        else:
            lbl_new[i:] += lbl_copy[:-i]

    lbl_new[lbl_new > 1] = 1

    return lbl_new

# %%
def smooth_lbl_conv(lbl, smooth_center, smooth_length, smooth_shape):
    lbl_new = lbl.clone().detach().cpu().float().unsqueeze(0)  # [N, C, L]
    lbl_weight = torch.zeros(1, 1, smooth_length)

    for i in range(lbl_weight.size(2)):
        if smooth_shape == 'square':
            lbl_weight[:, :, i] = 1
        elif smooth_shape == 'triangle':
            if i < smooth_length // 2:
                lbl_weight[:, :, i] = (i + 1) / (smooth_length // 2 + 1)
            else:
                lbl_weight[:, :, i] = 1 - (i - smooth_length // 2) / (smooth_length // 2 + 1)
        elif smooth_shape == 'hann':
            lbl_weight[:, :, i] = np.hanning(smooth_length + 2)[i + 1]

    if smooth_center:
        lbl_new = F.conv1d(lbl_new, lbl_weight, bias=None, padding=smooth_length // 2).squeeze()
    else:
        lbl_new = F.conv1d(lbl_new, lbl_weight, bias=None).squeeze()

    lbl_new[lbl_new > 1] = 1

    return lbl_new

# %%
signal = torch.randint(0, 2, (50,))
signal_smooth_loop = smooth_lbl_loop(signal, True, 3, 'triangle')
signal_smooth_conv = smooth_lbl_conv(signal, True, 3, 'triangle')

plt.plot(signal)
#plt.plot(signal_smooth_loop, 'r')
plt.plot(signal_smooth_conv.squeeze(), 'g', linestyle='--')
# %%
