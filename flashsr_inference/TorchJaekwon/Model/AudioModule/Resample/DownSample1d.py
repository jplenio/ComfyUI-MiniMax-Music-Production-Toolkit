import torch.nn as nn
from TorchJaekwon.Model.AudioModule.Filter.LowPassFilter1d import LowPassFilter1d
class DownSample1d(nn.Module):
    def __init__(self, ratio=2, kernel_size=None):
        super().__init__()
        self.ratio = ratio
        self.kernel_size = int(6 * ratio // 2) * 2 if kernel_size is None else kernel_size
        self.lowpass = LowPassFilter1d(cutoff=0.5 / ratio,
                                       half_width=0.6 / ratio,
                                       stride=ratio,
                                       kernel_size=self.kernel_size)

    def forward(self, x):
        xx = self.lowpass(x)

        return xx