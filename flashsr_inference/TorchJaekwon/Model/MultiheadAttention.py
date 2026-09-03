from typing import Optional
from torch import Tensor

import numpy as np
import torch
import torch.nn as nn

class MultiheadAttention(nn.Module):
    def __init__(self,
                 query_channels:int,
                 key_channels:int,
                 value_channels:int,
                 total_hidden_channels:int,
                 out_channels:int,
                 num_heads: int = 8
                 ) -> None:
        super().__init__()
        assert total_hidden_channels % num_heads == 0, f'hidden channel size({total_hidden_channels}) must be factorized by the number of heads({num_heads})'
        self.num_heads:int = num_heads
        self.hidden_channels:int = total_hidden_channels // num_heads
        self.projection_query:nn.Module = nn.Conv1d(in_channels=query_channels, out_channels=total_hidden_channels, kernel_size=1)
        self.projection_key:nn.Module = nn.Conv1d(in_channels=key_channels, out_channels=total_hidden_channels, kernel_size=1)
        self.projection_value:nn.Module = nn.Conv1d(in_channels=value_channels, out_channels=total_hidden_channels, kernel_size=1)
        self.projection_out:nn.Module = nn.Conv1d(in_channels=total_hidden_channels, out_channels=out_channels, kernel_size=1)

    def forward(self,
                queries:Tensor, #torch.float32 [batch, query_channels, number_of_queries]
                keys:Tensor, #torch.float32 [batch, key_channels, number_of_keys/values]
                values:Tensor, #torch.float32 [batch, value_channels, number_of_keys/values]
                mask: Optional[Tensor] = None #torch.float32 [batch, number_of_keys/values, number_of_queries]
                ) -> Tensor: #torch.float32 [batch, out_channels, number_of_queries]
        batch_size:int = queries.shape[0] 
        number_of_queries:int = queries.shape[-1]
        number_of_keys_and_values:int = keys.shape[-1]
        assert(keys.shape[-1] == values.shape[-1]), f'number of keys({keys.shape[-1]}) and number of values({values.shape[-1]}) must be the same'
        #[batch, num_heads, hidden_channels, number_of_queries]
        queries = self.projection_query(queries).view(batch_size, self.num_heads, -1, number_of_queries)
        #[batch, num_heads, hidden_channels, number_of_keys/values]
        keys = self.projection_key(keys).view(batch_size, self.num_heads, -1, number_of_keys_and_values)
        values = self.projection_key(values).view(batch_size, self.num_heads, -1, number_of_keys_and_values)
        #[batch, num_heads, number_of_keys/values,number_of_queries] martix mul of [number_of_keys/values, hidden_channels], [hidden_channels,number_of_queries]
        score:Tensor = torch.matmul(keys.transpose(2, 3), queries) * (self.hidden_channels ** -0.5)
        if mask is not None:
            score.masked_fill_(~mask[:, None, :, :1].to(torch.bool), -np.inf)
        #[batch, num_heads, number_of_keys/values,number_of_queries]
        weights:Tensor = torch.softmax(score, dim=2)
        #[batch, out_channels, number_of_queries]
        out = self.projection_out(torch.matmul(values, weights).view(batch_size, -1, number_of_queries))
        if mask is not None:
            out = out * mask[:, :1]
        return out