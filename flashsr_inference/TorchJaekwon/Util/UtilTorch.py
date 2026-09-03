from typing import Any,Dict
from torch import Tensor, dtype, device
from numpy import ndarray

import os
from collections import OrderedDict
import torch
import torch.nn as nn
import torch.nn.functional as F
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE

class UtilTorch:
    @staticmethod
    def to_np(tensor:Tensor, do_squeeze:bool = True) -> ndarray:
        if do_squeeze:
            return tensor.squeeze().detach().cpu().numpy()
        else:
            return tensor.detach().cpu().numpy()
    
    @staticmethod
    def to_torch(numpy_array:ndarray, dtype:dtype = torch.float32) -> Tensor:
        return torch.tensor(numpy_array, dtype=dtype)
    
    @staticmethod
    def register_buffer(model:nn.Module,
                        variable_name:str,
                        value:Any,
                        dtype:dtype = torch.float32) -> Any:
        if type(value) != Tensor:
            value = torch.tensor(value, dtype=dtype)
        model.register_buffer(variable_name, value)
        return getattr(model,variable_name)
    
    @staticmethod
    def get_param_num(model:nn.Module) -> Dict[str,int]:
        num_param : int = sum(param.numel() for param in model.parameters())
        trainable_param : int = sum(param.numel() for param in model.parameters() if param.requires_grad)
        return {'total':num_param, 'trainable':trainable_param}
    
    @staticmethod
    def freeze_param(model:nn.Module) -> nn.Module:
        model = model.eval()
        model.train = lambda self: self #override train with useless function
        for param in model.parameters():
            param.requires_grad = False
        return model
    
    @staticmethod
    def get_model_device(model:nn.Module) -> device:
        return next(model.parameters()).device
    
    @staticmethod
    def interpolate_2d(input:Tensor, #[width, height] | [batch, width, height] | [batch, channels, width, height]
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
    
    @staticmethod
    def tsne_plot(save_file_path:str,
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
    
    @staticmethod
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
    
    @staticmethod
    def mean_flat(tensor):
        """
        Take the mean over all non-batch dimensions.
        """
        return tensor.mean(dim=list(range(1, len(tensor.shape))))

    @staticmethod
    def kl_div_gaussian(mean1:Tensor, logvar1:Tensor, mean2:Tensor, logvar2:Tensor) -> Tensor:
        """
        Compute the KL divergence between two gaussians.
        Shapes are automatically broadcasted, so batches can be compared to
        scalars, among other use cases.
        """

        return 0.5 * ( -1.0 + logvar2 - logvar1 + torch.exp(logvar1 - logvar2) + ((mean1 - mean2) ** 2) * torch.exp(-logvar2))