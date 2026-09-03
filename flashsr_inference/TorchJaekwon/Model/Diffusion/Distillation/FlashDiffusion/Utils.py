from typing import Tuple    

import torch

def gaussian_mixture(k, locs, var, mode_probs=None):
    if mode_probs is None:
        mode_probs = [1 / len(locs)] * len(locs)

    def _gaussian(x):
        prob = [
            mode_probs[i] * torch.exp(-torch.tensor([(x - loc) ** 2 / var]))
            for i, loc in enumerate(locs)
        ]
        # prob.append(mode_prob * torch.exp(-torch.tensor([(x) ** 2 / var])))
        return sum(prob)

    return _gaussian

def append_dims(x: torch.Tensor, target_dims: int) -> torch.Tensor:
    """Appends dimensions to the end of a tensor until it has target_dims dimensions."""
    dims_to_append = target_dims - x.ndim
    if dims_to_append < 0:
        raise ValueError(
            f"input has {x.ndim} dims but target_dims is {target_dims}, which is less"
        )
    return x[(...,) + (None,) * dims_to_append]

def extract_into_tensor(
    a: torch.Tensor, t: torch.Tensor, x_shape: Tuple[int, ...]
) -> torch.Tensor:
    """
    Extracts values from a tensor into a new tensor using indices from another tensor.

    :param a: the tensor to extract values from.
    :param t: the tensor containing the indices.
    :param x_shape: the shape of the tensor to extract values into.
    :return: a new tensor containing the extracted values.
    """

    b, *_ = t.shape
    out = a.gather(-1, t)
    return out.reshape(b, *((1,) * (len(x_shape) - 1)))