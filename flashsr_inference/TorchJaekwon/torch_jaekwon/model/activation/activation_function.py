import numpy as np
import torch

class ActivationFunction:
    @staticmethod
    def exponential_sigmoid(x: torch.Tensor) -> torch.Tensor:
        """Exponential sigmoid.
        Args:
            x: [torch.float32; [...]], input tensors.
        Returns:
            sigmoid outputs.
        """
        return 2.0 * torch.sigmoid(x) ** np.log(10) + 1e-7