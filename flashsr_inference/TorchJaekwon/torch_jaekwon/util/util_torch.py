from typing import Any,Dict,Tuple, List, Optional
from torch import Tensor, dtype, device
from numpy import ndarray

import os
from collections import OrderedDict
from contextlib import contextmanager
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE

def to_np(tensor:Tensor, do_squeeze:bool = True) -> ndarray:
    if do_squeeze:
        return tensor.squeeze().detach().cpu().numpy()
    else:
        return tensor.detach().cpu().numpy()

def to_torch(numpy_array:ndarray, dtype:dtype = torch.float32) -> Tensor:
    return torch.tensor(numpy_array, dtype=dtype)

def register_buffer(
    model:nn.Module,
    variable_name:str,
    value:Any,
    dtype:dtype = torch.float32
) -> Any:
    if type(value) != Tensor:
        value = torch.tensor(value, dtype=dtype)
    model.register_buffer(variable_name, value)
    return getattr(model,variable_name)

def get_param_num(model:nn.Module) -> Dict[str,int]:
    num_param : int = sum(param.numel() for param in model.parameters())
    trainable_param : int = sum(param.numel() for param in model.parameters() if param.requires_grad)
    return {'total':num_param, 'trainable':trainable_param}

def freeze_param(model:nn.Module) -> nn.Module:
    model = model.eval()
    model.train = lambda *args, **kwargs: model #override train() to a no-op so the model stays frozen/eval
    for param in model.parameters():
        param.requires_grad = False
    return model

def get_model_device(model:nn.Module) -> device:
    return next(model.parameters()).device

def interpolate_2d(
    input:Tensor, #[width, height] | [batch, width, height] | [batch, channels, width, height]
    size_after_interpolation:tuple, #(width, height)
    mode:str = 'nearest'
) -> Tensor:
    if len(input.shape) == 2:
        shape_after_interpolation = size_after_interpolation
        input = input.view(1,1,*(input.shape))
    elif len(input.shape) == 3:
        shape_after_interpolation = (input.shape[0],*(size_after_interpolation))
        input = input.unsqueeze(1)
    elif len(input.shape) == 4:
        shape_after_interpolation = (input.shape[0],input.shape[1],*(size_after_interpolation))
    return F.interpolate(input, size = size_after_interpolation, mode=mode).view(shape_after_interpolation)

def tsne_plot(
    save_file_path:str,
    class_array:ndarray, #[the number of data, 1] data must be integer for class. ex) [[1],[3],...]
    embedding_array:ndarray,  #[the number of data, channel_size]
    figure_size:tuple = (10,10),
    legend:str = 'full',
    point_size:float = None #s=200
) -> None:
    import pandas as pd
    import seaborn as sns
    assert os.path.splitext(save_file_path)[-1] == '.png', 'save_file_path should be *.png'

    print('generating t-SNE plot...')
    tsne = TSNE(random_state=0)
    tsne_output:ndarray = tsne.fit_transform(embedding_array)

    df = pd.DataFrame(tsne_output, columns=['x', 'y'])
    df['class'] = class_array

    plt.rcParams['figure.figsize'] = figure_size
    
    scatterplot_args:dict = {'x':'x', 'y':'y', 'hue':'class',  'palette':sns.color_palette("hls", 10),
                                'data':df, 'marker':'o', 'legend':legend, 'alpha':0.5}
    if point_size is not None: scatterplot_args['s'] = point_size
    sns.scatterplot(**scatterplot_args)

    plt.xticks([])
    plt.yticks([])
    plt.xlabel('')
    plt.ylabel('')

    plt.savefig(save_file_path, bbox_inches='tight')

def update_ema(ema_model:nn.Module, model:nn.Module, decay:float=0.9999) -> None:
    """
    Step the EMA model towards the current model.
    """
    with torch.no_grad():
        ema_params = OrderedDict(ema_model.named_parameters())
        model_params = OrderedDict(model.named_parameters())

        for name, param in model_params.items():
            name = name.replace("module.", "")
            # TODO: Consider applying only to params that require_grad to avoid small numerical changes of pos_embed
            ema_params[name].mul_(decay).add_(param.data, alpha=1 - decay)

def mean_flat(tensor):
    """
    Take the mean over all non-batch dimensions.
    """
    return tensor.mean(dim=list(range(1, len(tensor.shape))))

def kl_div_gaussian(mean1:Tensor, logvar1:Tensor, mean2:Tensor, logvar2:Tensor) -> Tensor:
    """
    Compute the KL divergence between two gaussians.
    Shapes are automatically broadcasted, so batches can be compared to
    scalars, among other use cases.
    """

    return 0.5 * ( -1.0 + logvar2 - logvar1 + torch.exp(logvar1 - logvar2) + ((mean1 - mean2) ** 2) * torch.exp(-logvar2))

def load_model(model:nn.Module, state_dict:dict, strict:bool = True) -> nn.Module:
    is_model_comiled: bool = "_orig_mod." in list(model.state_dict().keys())[0]
    is_state_dict_comiled: bool = "_orig_mod." in list(state_dict.keys())[0]
    if is_model_comiled == is_state_dict_comiled:
        model.load_state_dict(state_dict, strict=strict)
    elif not is_model_comiled and is_state_dict_comiled:
        state_dict = state_dict_unwrap_torch_compile(state_dict)
        model.load_state_dict(state_dict, strict=strict)
    else:
        raise NotImplementedError("Model is compiled but state_dict is not compiled")
    return model

def state_dict_unwrap_torch_compile(state_dict: dict) -> dict:
    new_state_dict = {}
    for key in state_dict.keys():
        if "_orig_mod." in key:
            new_state_dict[key.replace("_orig_mod.", "")] = state_dict[key]
        else:
            new_state_dict[key] = state_dict[key]
    return new_state_dict

def checkpoint(function, *args, **kwargs):
    kwargs.setdefault("use_reentrant", False)
    return torch.utils.checkpoint.checkpoint(function, *args, **kwargs)

def get_params(
    model:nn.Module,
    excluded_param_name_list:list,
) -> Tuple[list, Dict[str, list]]:
    parameters = list()
    param_names_dict = {'included':[], 'excluded':[]}
    for name, param in model.named_parameters():
        if not any([ excluded_param_name in name for excluded_param_name in excluded_param_name_list]):
            parameters.append(param)
            param_names_dict['included'].append(name)
        else:
            param_names_dict['excluded'].append(name)
    return parameters, param_names_dict

def chunk_list(data_list, size):
    return [data_list[i:i + size] for i in range(0, len(data_list), size)]

def get_batch_dict(data_list:List[dict]) -> dict:
    batch_dict = dict()
    for key in data_list[0].keys():
        value_list = [data[key] for data in data_list]
        if isinstance(value_list[0], Tensor):
            batch_dict[key] = torch.stack(value_list, dim=0)
        elif isinstance(value_list[0], ndarray):
            batch_dict[key] = np.stack(value_list, axis=0)
        else:
            batch_dict[key] = value_list
    return batch_dict

def unwrap_batch_dict(batch_dict:dict) -> List[dict]:
    data_list = list()
    batch_size:int = len(batch_dict[list(batch_dict.keys())[0]])
    for i in range(batch_size):
        unwrapped_data_dict = dict()
        for key, value in batch_dict.items():
            unwrapped_data_dict[key] = value[i]
        data_list.append(unwrapped_data_dict)
    return data_list

def suggest_batch_knob_for_target_memory(
    current_knob:float,   # the batch knob you probed with (batch_size, or batch_duration in sec, etc.)
    baseline_bytes:int,   # VRAM held by fixed cost: model + optimizer state + workspaces (does NOT scale with the knob)
    peak_bytes:int,       # peak VRAM during a step at current_knob
    total_bytes:int,      # VRAM budget (e.g. torch.cuda.get_device_properties(i).total_memory, or the card's total)
    target_fraction:float = 0.85,  # aim peak at this fraction of total (leave headroom for fragmentation/spikes)
    safety_margin:float = 0.9,      # shrink the extrapolated knob so the linear estimate doesn't overshoot into OOM
) -> Dict[str, float]:
    """Suggest a batch knob (batch_size / batch_duration / ...) that lands peak VRAM near a target fraction.

    Model: peak = baseline + slope * knob, i.e. activation memory scales ~linearly with the batch knob
    while the fixed cost (weights + optimizer moments + cudnn/nccl workspaces) does not. From ONE probe:
        activation = peak - baseline
        target_activation = target_fraction * total - baseline
        new_knob = current_knob * (target_activation / activation) * safety_margin

    Source-agnostic: feed bytes from torch.cuda stats OR nvidia-smi (whichever measures your real peak).
    torch.cuda under-counts the true device peak (ignores caching-allocator reserve, fragmentation,
    non-torch libs), so for an absolute ceiling prefer nvidia-smi and keep safety_margin < 1.

    Typical torch.cuda probe (run a couple steps first so optimizer state exists):
        torch.cuda.reset_peak_memory_stats(dev)
        baseline_bytes = torch.cuda.memory_allocated(dev)   # captured right before the forward
        ... forward + backward + optimizer.step() ...
        peak_bytes = torch.cuda.max_memory_allocated(dev)

    Returns current/target/suggested knob plus the fractions, so you can log and decide whether to re-probe.
    """
    activation:float = peak_bytes - baseline_bytes
    target_activation:float = target_fraction * total_bytes - baseline_bytes
    if activation <= 0 or target_activation <= 0:
        # Fixed cost alone already exceeds target, or peak<=baseline (bad measurement): don't extrapolate.
        suggested = current_knob
    else:
        suggested = current_knob * (target_activation / activation) * safety_margin
    return {
        'current_knob': float(current_knob),
        'suggested_knob': float(suggested),
        'current_peak_fraction': float(peak_bytes) / float(total_bytes),
        'target_fraction': float(target_fraction),
    }

def to_device(obj: Any, device) -> Any:
    """Recursively move tensors inside dicts/lists/tuples to ``device`` (e.g. a batch to GPU for inference,
    or to CPU to save after an OOM). Non-tensors pass through. Matches ``tensor.to`` semantics (no detach)."""
    if torch.is_tensor(obj):           return obj.to(device)
    if isinstance(obj, dict):          return {k: to_device(v, device) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return type(obj)(to_device(v, device) for v in obj)
    return obj

def peak_vram_gb(device=None) -> Tuple[float, float]:
    """Running-peak (reserved, allocated) VRAM in GB since the last reset; (0.0, 0.0) if CUDA is unavailable."""
    if not torch.cuda.is_available():
        return (0.0, 0.0)
    return (torch.cuda.max_memory_reserved(device) / 1024**3,
            torch.cuda.max_memory_allocated(device) / 1024**3)

@contextmanager
def oom_dump_guard(payload: Any, save_path: Optional[str]):
    """Run a block; if it raises a CUDA OutOfMemoryError, dump ``payload`` (tensors moved to CPU) to
    ``save_path``, then re-raise. If ``save_path is None`` nothing is dumped (a passthrough that still
    re-raises) — so a caller can always wrap a shared code path and choose save-or-not via the path
    itself, with no separate enable flag. The OOM is unrecoverable — this only RECORDS the offending
    batch for offline replay; it does NOT rescue the run. Crash-path only => zero cost on the normal
    path. Best-effort: a failed dump is swallowed, but the OOM is always re-raised (never masked).
    Moving tensors to CPU reads GPU memory without allocating more, so it works even when GPU is full.

    Example — capture the OOM-triggering batch for offline replay (a path enables the dump, None disables):
        oom_path = f"{log_dir}/oom_batches/rank{rank}_step{step}.pt" if save_on_oom else None
        with oom_dump_guard(batch, oom_path):
            loss = model.training_step(batch)   # on OOM: `batch` is dumped to oom_path, then re-raised
        # then, offline on a smaller run:  batch = torch.load(oom_path)  ->  probe model(batch) VRAM
    """
    try:
        yield
    except torch.cuda.OutOfMemoryError:
        if save_path is not None:
            try:
                os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
                torch.save(to_device(payload, "cpu"), save_path)
            except Exception:
                pass
        raise