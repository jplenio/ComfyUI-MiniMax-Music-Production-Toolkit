"""Classifier-free guidance, one function per method.

Every method has the same signature, so a model picks one by passing it in:

    cfg_forward = instruct_pix2pix_cfg      # or cfg, or whatever comes next
    cfg_forward(model_forward, cfg_conds, cfg_scales, cfg_rescale)

``cfg_conds`` holds one conditioning per model output the method needs, most-conditioned first,
and ``cfg_scales`` one scale per move between them -- so the method's arity says what it wants:
``cfg`` takes 2 conditionings and 1 scale, ``instruct_pix2pix_cfg`` takes 3 and 2.

``model_forward`` hides how the conditionings are actually run (one batch or one at a time) and
how the model is called, so these functions only implement the guidance formula.
"""

from typing import Callable, Dict, List, Optional, Sequence, Union

import torch
from torch import Tensor, nn

# One model input set: whatever the model is conditioned on, keyed by name.
CfgCond = Dict[str, Tensor]
# One forward over every conditioning -> their outputs concatenated on the batch dim, same order.
ModelForward = Callable[[List[CfgCond]], Tensor]


def model_forward(
    model: nn.Module, x: Tensor, t: Tensor, cfg_conds: List[CfgCond], sequential: bool = False
) -> Tensor:
    """Run ``model`` over every conditioning, outputs concatenated on the batch dim, same order.

    ``sequential`` runs them one at a time instead of as one batch: same result, less peak memory.
    """
    if sequential:
        return torch.cat([model(x, t, **cfg_cond) for cfg_cond in cfg_conds], dim=0)
    num_cfg_conds: int = len(cfg_conds)
    stacked_cond: CfgCond = {
        key: torch.cat([cfg_cond[key] for cfg_cond in cfg_conds], dim=0) for key in cfg_conds[0]
    }
    return model(
        torch.cat([x] * num_cfg_conds, dim=0), torch.cat([t] * num_cfg_conds, dim=0), **stacked_cond
    )


def cfg(
    model_forward: ModelForward,
    cfg_conds: List[CfgCond],
    cfg_scales: Union[float, Sequence[float]],
    cfg_rescale: Optional[float] = None,
) -> Tensor:
    """Ordinary classifier-free guidance: one condition, one scale.

        out = out_uncond + cfg_scale * (out_cond - out_uncond)

    ``cfg_conds`` is ``[cond, uncond]``. ``cfg_scales`` is that single scale, as a float or a
    one-entry sequence.
    """
    NUM_CFG_CONDS = 2
    assert len(cfg_conds) == NUM_CFG_CONDS, (
        f"expected {NUM_CFG_CONDS} conditionings [cond, uncond], got {len(cfg_conds)}"
    )
    cfg_scale = cfg_scales if isinstance(cfg_scales, float) else cfg_scales[0]
    out_cond, out_uncond = model_forward(cfg_conds).chunk(NUM_CFG_CONDS, dim=0)
    out_cfg = out_uncond + cfg_scale * (out_cond - out_uncond)
    if not cfg_rescale:
        return out_cfg
    # Guidance inflates the spread; pull it back toward the conditioned output (Lin et al., 2024).
    out_cfg_rescaled = out_cfg * (out_cond.std(dim=1, keepdim=True) / out_cfg.std(dim=1, keepdim=True))
    return cfg_rescale * out_cfg_rescaled + (1 - cfg_rescale) * out_cfg


def instruct_pix2pix_cfg(
    model_forward: ModelForward,
    cfg_conds: List[CfgCond],
    cfg_scales: Sequence[float],
    cfg_rescale: Optional[float] = None,
) -> Tensor:
    """InstructPix2Pix guidance (Brooks et al., 2023, https://arxiv.org/abs/2211.09800).

    Ordinary CFG has one condition and one scale; this guides TWO conditions with a scale each:

        out = out_uncond + cfg_scales[0] * (out_one_cond - out_uncond)
                         + cfg_scales[1] * (out_cond     - out_one_cond)

    ``cfg_conds`` is ``[cond, one_cond, uncond]``, most-conditioned first: both conditions, then
    only one of them, then neither. Against the paper's names:

        cfg_scales[0] : image_cfg_scale
        cfg_scales[1] : text_cfg_scale
        out_one_cond  : out_img_cond

    The scales are positional because neither condition outranks the other -- which one
    ``cfg_scales[0]`` governs follows from what the caller puts in ``cfg_conds[1]``.
    """
    NUM_CFG_CONDS, NUM_CFG_SCALES = 3, 2   # fixed by the method: two conditions, three outputs
    assert not cfg_rescale, "the paper defines no rescale for two-condition guidance"
    assert len(cfg_conds) == NUM_CFG_CONDS, (
        f"expected {NUM_CFG_CONDS} conditionings [cond, one_cond, uncond], got {len(cfg_conds)}"
    )
    assert len(cfg_scales) == NUM_CFG_SCALES, (
        f"expected {NUM_CFG_SCALES} scales, got {len(cfg_scales)}"
    )
    # Chunked in the order they were passed, so the caller cannot mismatch the two.
    out_cond, out_one_cond, out_uncond = model_forward(cfg_conds).chunk(NUM_CFG_CONDS, dim=0)
    return (
        out_uncond
        + cfg_scales[0] * (out_one_cond - out_uncond)
        + cfg_scales[1] * (out_cond - out_one_cond)
    )
