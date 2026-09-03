from torch import Tensor

import torch

class Functional:
    @staticmethod
    def slerp(low:Tensor,
              high:Tensor,
              val:float = 0.5
              ):
        '''
        Spherical Linear Interpolation (Slerp)
        Slerp(q_0,q_1;t)    = q_0(q_0^-1 q_1)^t
                            = ( sin(1-t) theta ) / sin(theta) * q_0 * sin(t * theta)/sin(theta) * q_1
                            where dot_product(q_0,q_1) = cos(theta)
        
        theta = np.arccos(np.dot(low/np.linalg.norm(low), high/np.linalg.norm(high)))
        so = np.sin(theta)
        return np.sin((1.0-val)*theta) / so * low + np.sin(val*theta)/so * high
        '''
        assert tuple(low.shape) == tuple(high.shape), f'low shape({low.shape}) must be same as high shape({high.shape})'
        feature_shape:tuple = tuple(low.shape)
        # Normalize the vectors to get the directions and angles
        low_1d:Tensor = low.reshape(feature_shape[0],-1)
        high_1d:Tensor = high.reshape(feature_shape[0],-1)
        low_norm = low_1d/torch.norm(low_1d, dim=1, keepdim=True)
        high_norm = high_1d/torch.norm(high_1d, dim=1, keepdim=True)

        dot_product = (low_norm*high_norm).sum(dim = 1)
        theta = torch.acos(dot_product)
        so = torch.sin(theta)
        res = (torch.sin((1.0-val)*theta)/so).unsqueeze(1)*low_1d + (torch.sin(val*theta)/so).unsqueeze(1) * high_1d
        return res.reshape(feature_shape)