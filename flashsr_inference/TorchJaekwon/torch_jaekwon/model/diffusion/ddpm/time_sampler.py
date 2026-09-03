from typing import Literal
from torch import Tensor

import torch
import torch.distributions as dist

class TimeSampler:
    def __init__(
        self, 
        time_type:Literal['continuous', 'discrete'] = 'continuous',
        sampler_type:Literal['uniform', 'logit_normal', 'trunc_logit_normal'] = 'logit_normal',
        timesteps:int = 1000, # only for discrete time
    ) -> None:
        self.time_type:Literal['continuous', 'discrete'] = time_type
        if time_type == 'discrete': 
            self.timesteps:int = timesteps
        else:
            self.rng = torch.quasirandom.SobolEngine(1, scramble=True)
        self.sampler_type:Literal['uniform', 'logit_normal'] = sampler_type
    
    def sample(self, batch_size:int) -> Tensor:
        if self.time_type == 'discrete':
            if self.sampler_type == 'uniform':
                return torch.randint(0, self.timesteps, (batch_size,)).long()
            else:
                raise NotImplementedError()
        else:
            if self.sampler_type == 'uniform':
                return torch.rand(batch_size)
            elif self.sampler_type == 'logit_normal':
                return torch.sigmoid(torch.randn(batch_size))
            elif self.sampler_type == 'trunc_logit_normal':
                # Draw from logistic truncated normal distribution
                t = self.truncated_logistic_normal_rescaled(batch_size).to(self.device)

                # Flip the distribution
                t = 1 - t
                return t
    
    def truncated_logistic_normal_rescaled(self, shape, left_trunc=0.075, right_trunc=1):
        """
    
        shape: shape of the output tensor
        left_trunc: left truncation point, fraction of probability to be discarded
        right_trunc: right truncation boundary, should be 1 (never seen at test time)
        """
        
        # Step 1: Sample from the logistic normal distribution (sigmoid of normal)
        logits = torch.randn(shape)
        
        # Step 2: Apply the CDF transformation of the normal distribution
        normal_dist = dist.Normal(0, 1)
        cdf_values = normal_dist.cdf(logits)
        
        # Step 3: Define the truncation bounds on the CDF
        lower_bound = normal_dist.cdf(torch.logit(torch.tensor(left_trunc)))
        upper_bound = normal_dist.cdf(torch.logit(torch.tensor(right_trunc)))

        # Step 4: Rescale linear CDF values into the truncated region (between lower_bound and upper_bound)
        truncated_cdf_values = lower_bound + (upper_bound - lower_bound) * cdf_values
        
        # Step 5: Map back to logistic-normal space using inverse CDF
        truncated_samples = torch.sigmoid(normal_dist.icdf(truncated_cdf_values))
        
        # Step 6: Rescale values so that min is 0 and max is just below 1
        rescaled_samples = (truncated_samples - left_trunc) / (right_trunc - left_trunc)

        return rescaled_samples