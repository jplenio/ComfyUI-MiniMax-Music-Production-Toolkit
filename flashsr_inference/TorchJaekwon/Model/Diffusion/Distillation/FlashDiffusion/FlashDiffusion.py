import logging
from copy import deepcopy
from typing import Any, Dict, List, Tuple, Union, Literal

try: import lpips
except: print('lpips is not installed')
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from TorchJaekwon.Model.Diffusion.DDPM.DDPM import DDPM
from tqdm import tqdm

from TorchJaekwon.Model.Diffusion.External.diffusers.DiffusersWrapper import DiffusersWrapper
from TorchJaekwon.Model.Diffusion.External.diffusers.schedulers.scheduling_dpmsolver_multistep import DPMSolverMultistepScheduler
from TorchJaekwon.Model.Diffusion.Distillation.FlashDiffusion.Utils import gaussian_mixture, append_dims, extract_into_tensor


class FlashDiffusion(nn.Module):

    def __init__(
        self,
        student_denoiser: DDPM,
        teacher_denoiser: DDPM,
        discriminator: torch.nn.Module = None,
        teacher_noise_scheduler_class = DPMSolverMultistepScheduler,
        distill_loss_type:Literal['l2', 'l1', 'lpips'] = 'l2',
        gan_loss_type:Literal['lsgan', 'wgan', 'hinge', 'non-saturating'] = 'lsgan',
        use_dmd_loss:bool = True,
        distill_loss_scale:list = [1.0, 1.0, 1.0, 1.0],
        adversarial_loss_scale:list = [0.0, 0.1, 0.2, 0.3],
        dmd_loss_scale:list = [0.0, 0.3, 0.5, 0.7],
        use_teacher_as_real:bool = False,
        switch_teacher:bool = False,
        K:list = [32, 32, 32, 32],
        num_iterations_per_K:list=[5000, 5000, 5000, 5000],
        timestep_distribution='mixture',
        mode_probs=[[0.0, 0.0, 0.5, 0.5],
                    [0.1, 0.3, 0.3, 0.3],
                    [0.25, 0.25, 0.25, 0.25],
                    [0.4, 0.2, 0.2, 0.2]],
        guidance_scale_min:float=3.0,
        guidance_scale_max:float=13.0,
        mixture_num_components:int = 4,
        mixture_var:float = 0.5,
    ):
        super().__init__()

        self.student_denoiser = student_denoiser
        self.teacher_denoiser = teacher_denoiser
        teacher_noise_scheduler_args = self.get_diffuser_scheduler_config(teacher_denoiser)
        self.teacher_noise_scheduler = teacher_noise_scheduler_class(**teacher_noise_scheduler_args)

        self.K = K
        self.guidance_scale_min = [guidance_scale_min] * len(self.K)
        self.guidance_scale_max = [guidance_scale_max] * len(self.K)
        
        self.num_iterations_per_K = num_iterations_per_K
        self.distill_loss_type = distill_loss_type
        self.timestep_distribution = timestep_distribution
        self.iter_steps = 0
        self.mixture_num_components = [mixture_num_components] * len(self.K)
        self.mixture_var = [mixture_var] * len(self.K)
        self.use_dmd_loss = use_dmd_loss
        self.dmd_loss_scale = dmd_loss_scale
        self.distill_loss_scale = distill_loss_scale
        self.discriminator = discriminator
        self.adversarial_loss_scale = adversarial_loss_scale
        self.gan_loss_type = gan_loss_type
        self.mode_probs = mode_probs
        self.use_teacher_as_real = use_teacher_as_real
        self.switch_teacher = switch_teacher
        self.disc_update_counter = 0

        if self.discriminator is None:
            logging.warning(
                "No discriminator provided. Adversarial loss will be ignored."
            )
            self.use_adversarial_loss = False
        else:
            self.use_adversarial_loss = True

        self.disc_backbone = self.teacher_denoiser

        if self.distill_loss_type == "lpips":
            self.lpips = lpips.LPIPS(net="vgg")

        self.K_steps = np.cumsum(self.num_iterations_per_K)
        self.K_prev = self.K[0]

        self.register_buffer( "sqrt_alpha_cumprod", torch.sqrt(self.teacher_denoiser.alphas_cumprod),)
        self.register_buffer( "sigmas", torch.sqrt(1 - self.teacher_denoiser.alphas_cumprod),)
    
    def get_diffuser_scheduler_config(self, ddpm_module: DDPM):
        output_type_dict = {
            'v_prediction': 'v_prediction',
            'noise': 'epsilon',
            'x_start': 'sample'
        }
        return {
            'num_train_timesteps': ddpm_module.timesteps,
            'trained_betas': ddpm_module.betas,
            'prediction_type': output_type_dict[ddpm_module.model_output_type],
            'timestep_spacing': "trailing"
            }

    def _encode_inputs(self, batch: Dict[str, Any]):
        """
        Encode the inputs using the VAE
        """
        with torch.no_grad():
            vae_inputs = batch[self.vae.config.input_key]
            return self.vae.encode(vae_inputs)

    def _get_timesteps(
        self, num_samples: int = 1, K: int = 1, K_step: int = 1, device="cpu"
    ):
        # Get the timesteps for the current K
        self.teacher_noise_scheduler.set_timesteps(K)

        if self.timestep_distribution == "uniform":
            prob = torch.ones(K) / K
        elif self.timestep_distribution == "gaussian":
            prob = [torch.exp(-torch.tensor([(i - K / 2) ** 2 / K])) for i in range(K)]
            prob = torch.tensor(prob) / torch.sum(torch.tensor(prob))
        elif self.timestep_distribution == "mixture":
            mixture_num_components = self.mixture_num_components[K_step]
            mode_probs = self.mode_probs[K_step]

            # Define targeted timesteps
            locs = [
                i * (K // mixture_num_components)
                for i in range(0, mixture_num_components)
            ]
            mixture_var = self.mixture_var[K_step]
            prob = [
                gaussian_mixture(
                    K,
                    locs=locs,
                    var=mixture_var,
                    mode_probs=mode_probs,
                )(i)
                for i in range(K)
            ]
            prob = torch.tensor(prob) / torch.sum(torch.tensor(prob))

        start_idx = torch.multinomial(prob, 1)

        # start_idx = torch.randint(0, len(self.teacher_noise_scheduler.timesteps), (1,))

        start_timestep = (
            self.teacher_noise_scheduler.timesteps[start_idx]
            .to(device)
            .repeat(num_samples)
        )

        return start_idx, start_timestep

    def forward(self, 
                x_start, 
                cond, 
                is_cond_unpack:bool = False,
                train_stage:Literal['generator', 'discriminator'] = 'generator'
                ):
        self.iter_steps += 1
        z, preprocessed_cond, additional_data_dict = self.teacher_denoiser.preprocess(x_start, cond)

        # Get conditioning
        conditioning = preprocessed_cond 
        student_conditioning = preprocessed_cond 
        if DDPM.make_decision(self.student_denoiser.unconditional_prob):
            student_conditioning = self.student_denoiser.get_unconditional_condition(cond=cond)
            student_conditioning = self.teacher_denoiser.preprocess(None, student_conditioning)[1]

        # Get K for the current step
        if self.iter_steps > self.K_steps[-1]:
            K_step = len(self.K) - 1
        else:
            K_step = np.argmax(self.iter_steps < self.K_steps)
        K = self.K[K_step]
        guidance_min = self.guidance_scale_min[K_step]
        guidance_max = self.guidance_scale_max[K_step]
        if K != self.K_prev:
            self.K_prev = K
            if self.switch_teacher:
                print("Switching teacher")
                self.teacher_denoiser = deepcopy(self.student_denoiser)
                self.teacher_denoiser.freeze()

        # Create noisy samples
        noise = torch.randn_like(z)

        # Sample the timesteps
        start_idx, start_timestep = self._get_timesteps(
            num_samples=z.shape[0], K=K, K_step=K_step, device=z.device
        )

        if start_idx == 0:
            noisy_sample_init = noise
            noisy_sample_init *= self.teacher_noise_scheduler.init_noise_sigma
            noisy_sample_init_student = noise

        else:
            # Add noise to sample
            noisy_sample_init = self.teacher_noise_scheduler.add_noise(
                z, noise, start_timestep
            )
            noisy_sample_init_student = noisy_sample_init

        noisy_sample_init_ = self.teacher_noise_scheduler.scale_model_input(
            noisy_sample_init_student, start_timestep
        )

        # Get student denoiser output
        student_model_output:torch.Tensor = self.student_denoiser.apply_model(noisy_sample_init_, start_timestep, student_conditioning, is_cond_unpack )

        c_skip, c_out = self._scalings_for_boundary_conditions(start_timestep)

        c_skip = append_dims(c_skip, noisy_sample_init_student.ndim)
        c_out = append_dims(c_out, noisy_sample_init_student.ndim)

        student_output = self._predicted_x_0(
            student_model_output,
            start_timestep.type(torch.int64),
            noisy_sample_init_student,
            DiffusersWrapper.get_diffusers_output_type_name(self.student_denoiser),
            self.sqrt_alpha_cumprod.to(z.device),
            self.sigmas.to(z.device),
            z,
        )

        noisy_sample = noisy_sample_init.clone().detach()

        guidance_scale = (
            torch.rand(1).to(z.device) * (guidance_max - guidance_min) + guidance_min
        )

        with torch.no_grad():
            for t in self.teacher_noise_scheduler.timesteps[start_idx:]:
                timestep = torch.tensor([t], device=z.device).repeat(z.shape[0])

                noisy_sample_ = self.teacher_noise_scheduler.scale_model_input(
                    noisy_sample, t
                )
                teacher_model_output:torch.Tensor = self.teacher_denoiser.apply_model(noisy_sample_, timestep, conditioning, is_cond_unpack , guidance_scale)

                # Make one step on the reverse diffusion process
                noisy_sample = self.teacher_noise_scheduler.step(teacher_model_output, #noise_pred, 
                                                                 t, 
                                                                 noisy_sample, 
                                                                 return_dict=False
                                                                 )[0]

        teacher_output = noisy_sample

        student_output = c_skip * noisy_sample_init + c_out * student_output

        distill_loss = self._distill_loss(student_output, teacher_output)

        loss = (
            distill_loss
            * self.distill_loss_scale[K_step]
        )

        if self.use_dmd_loss:
            dmd_loss = self._dmd_loss(
                student_output,
                student_conditioning,
                conditioning,
                is_cond_unpack,
                K,
                K_step,
            )
            loss += dmd_loss * self.dmd_loss_scale[K_step]

        if self.use_adversarial_loss:
            gan_loss = self._gan_loss(
                z,
                student_output,
                teacher_output,
                conditioning,
                is_cond_unpack,
                train_stage=train_stage,
            )
            print("GAN loss", gan_loss)
            loss += self.adversarial_loss_scale[K_step] * gan_loss[0]
            loss_disc = gan_loss[1]

        result_dict = {
            "loss_dict": {
                'gen_total': loss,
            },
            "teacher_output": teacher_output,
            "student_output": student_output,
            "noisy_sample": noisy_sample_init,
            "start_timestep": start_timestep[0].item(),
        }

        if self.use_adversarial_loss:
            result_dict["loss_dict"]["disc_total"] = loss_disc

        if train_stage == "generator":
            result_dict["loss_dict"]["gen_distill"] = distill_loss * self.distill_loss_scale[K_step]
            if self.use_dmd_loss:
                result_dict["loss_dict"]["gen_dmd"] = self.dmd_loss_scale[K_step] * dmd_loss
            if self.use_adversarial_loss:
                result_dict["loss_dict"]["gen_adv"] = self.adversarial_loss_scale[K_step] * gan_loss[0]

        return result_dict

    def _distill_loss(self, student_output, teacher_output):
        if self.distill_loss_type == "l2":
            return torch.mean(
                ((student_output - teacher_output) ** 2).reshape(
                    student_output.shape[0], -1
                ),
                1,
            ).mean()
        elif self.distill_loss_type == "l1":
            return torch.mean(
                torch.abs(student_output - teacher_output).reshape(
                    student_output.shape[0], -1
                ),
                1,
            ).mean()
        elif self.distill_loss_type == "lpips":
            # center crop patches of size 64x64
            crop_h = (student_output.shape[2] - 64) // 2
            crop_w = (student_output.shape[3] - 64) // 2
            student_output = student_output[
                :, :, crop_h : crop_h + 64, crop_w : crop_w + 64
            ]
            teacher_output = teacher_output[
                :, :, crop_h : crop_h + 64, crop_w : crop_w + 64
            ]

            decoded_student = self.vae.decode(student_output).clamp(-1, 1)
            decoded_teacher = self.vae.decode(teacher_output).clamp(-1, 1)
            # self.lpips = self.lpips.to(student_output.device)
            return self.lpips(decoded_student, decoded_teacher).mean()
        else:
            raise NotImplementedError(f"Loss type {self.loss_type} not implemented")

    def _dmd_loss(
        self,
        student_output,
        student_conditioning,
        conditioning,
        #unconditional_conditioning,
        is_cond_unpack,
        K,
        K_step,
    ):
        """
        Compute the DMD loss
        """

        # Sample noise
        noise = torch.randn_like(student_output)

        timestep = torch.randint(
            0,
            self.teacher_noise_scheduler.config.num_train_timesteps,
            (student_output.shape[0],),
            device=student_output.device,
        )

        # Create noisy sample
        noisy_student = self.teacher_noise_scheduler.add_noise(
            student_output, noise, timestep
        )

        with torch.no_grad():
            cond_fake_noise_pred = self.student_denoiser.apply_model(x=noisy_student,
                                                                     t = timestep,
                                                                     cond=student_conditioning,
                                                                     is_cond_unpack = is_cond_unpack)
            
            if self.student_denoiser.model_output_type == "v_prediction":
                cond_fake_noise_pred = self.student_denoiser.predict_noise_from_v(x_t=noisy_student,
                                                                                  t=timestep,
                                                                                  v=cond_fake_noise_pred)

            guidance_scale = (
                torch.rand(1).to(student_output.device)
                * (self.guidance_scale_max[K_step] - self.guidance_scale_min[K_step])
                + self.guidance_scale_min[K_step]
            )
            
            real_noise_pred = self.teacher_denoiser.apply_model(
                x=noisy_student, 
                t = timestep,
                cond=conditioning,
                is_cond_unpack = is_cond_unpack,
                cfg_scale = guidance_scale
            )
            if self.teacher_denoiser.model_output_type == "v_prediction":
                real_noise_pred = self.teacher_denoiser.predict_noise_from_v(x_t=noisy_student,
                                                                             t=timestep,
                                                                             v=real_noise_pred)

        fake_noise_pred = cond_fake_noise_pred

        score_real = -real_noise_pred
        score_fake = -fake_noise_pred

        alpha_prod_t = self.teacher_noise_scheduler.alphas_cumprod.to(
            device=student_output.device, dtype=student_output.dtype
        )[timestep]
        beta_prod_t = 1.0 - alpha_prod_t

        coeff = (
            (score_fake - score_real)
            * beta_prod_t.view(-1, 1, 1, 1) ** 0.5
            / alpha_prod_t.view(-1, 1, 1, 1) ** 0.5
        )

        pred_x_0_student = self._predicted_x_0(
            real_noise_pred,
            timestep,
            noisy_student,
            "epsilon",
            self.sqrt_alpha_cumprod,
            self.sigmas,
            student_output,
        )

        weight = (
            1.0
            / (
                (student_output - pred_x_0_student).abs().mean([1, 2, 3], keepdim=True)
                + 1e-5
            ).detach()
        )
        return F.mse_loss(
            student_output, (student_output - weight * coeff).detach(), reduction="mean"
        )

    def _gan_loss(
        self,
        z,
        student_output,
        teacher_output,
        conditioning,
        is_cond_unpack,
        down_intrablock_additional_residuals=None,
        train_stage:Literal['generator', 'discriminator'] = 'generator',
    ):

        self.disc_update_counter += 1

        # Sample noise
        noise = torch.randn_like(student_output)

        if self.use_teacher_as_real:
            real = teacher_output

        else:
            real = z

        # Selected timesteps
        selected_timesteps = [10, 250, 500, 750]
        prob = torch.tensor([0.25, 0.25, 0.25, 0.25])

        # Sample the timesteps
        idx = prob.multinomial(student_output.shape[0], replacement=True).to(
            student_output.device
        )
        timesteps = torch.tensor(
            selected_timesteps, device=student_output.device, dtype=torch.long
        )[idx]

        # Create noisy sample
        noisy_fake = self.teacher_noise_scheduler.add_noise(
            student_output, noise, timesteps
        )
        noisy_real = self.teacher_noise_scheduler.add_noise(real, noise, timesteps)

        # Concatenate noisy samples
        noisy_sample = torch.cat([noisy_fake, noisy_real], dim=0)

        # Concatenate conditionings
        if conditioning is not None:
            conditioning = torch.cat([conditioning, conditioning], dim=0)

        # Concatenate timesteps
        timestep = torch.cat([timesteps, timesteps], dim=0)

        # Predict noise level using denoiser
        denoised_sample = self.disc_backbone.apply_model(noisy_sample, timestep, conditioning, is_cond_unpack)

        denoised_sample_fake, denoised_sample_real = denoised_sample.chunk(2, dim=0)

        if self.gan_loss_type == "wgan":
            # Clip weights of discriminator
            for p in self.discriminator.parameters():
                p.data.clamp_(-0.01, 0.01)
            if step % 2 == 0:
                loss_G = -self.discriminator(denoised_sample_fake).mean()
                loss_D = 0
            else:
                loss_D = (
                    -self.discriminator(denoised_sample_real).mean()
                    + self.discriminator(denoised_sample_fake.detach()).mean()
                )
                loss_G = 0

        elif self.gan_loss_type == "lsgan":
            valid = torch.ones(student_output.size(0), 1, device=noise.device)
            fake = torch.zeros(noise.size(0), 1, device=noise.device)
            if train_stage == "generator":
                loss_G = F.mse_loss(
                    torch.sigmoid(self.discriminator(denoised_sample_fake)), valid
                )
                loss_D = 0
            else:
                loss_D = 0.5 * (
                    F.mse_loss(
                        torch.sigmoid(self.discriminator(denoised_sample_real)), valid
                    )
                    + F.mse_loss(
                        torch.sigmoid(
                            self.discriminator(denoised_sample_fake.detach())
                        ),
                        fake,
                    )
                )
                loss_G = 0
        elif self.gan_loss_type == "hinge":
            if train_stage == "generator":
                loss_G = -self.discriminator(denoised_sample_fake).mean()
                loss_D = 0
            else:
                loss_D = (
                    F.relu(1.0 - self.discriminator(denoised_sample_real)).mean()
                    + F.relu(
                        1.0 + self.discriminator(denoised_sample_fake.detach())
                    ).mean()
                )
                loss_G = 0

        elif self.gan_loss_type == "non-saturating":
            if train_stage == "generator":
                loss_G = -torch.mean(
                    torch.log(
                        torch.sigmoid(self.discriminator(denoised_sample_fake)) + 1e-8
                    )
                )
                loss_D = 0

            else:
                loss_D = -torch.mean(
                    torch.log(
                        torch.sigmoid(self.discriminator(denoised_sample_real)) + 1e-8
                    )
                    + torch.log(
                        1
                        - torch.sigmoid(
                            self.discriminator(denoised_sample_fake.detach())
                        )
                        + 1e-8
                    )
                )
                loss_G = 0
        else:
            if train_stage == "generator":
                valid = torch.ones(student_output.size(0), 1, device=noise.device)
                loss_G = F.binary_cross_entropy_with_logits(
                    self.discriminator(denoised_sample_fake), valid
                )
                loss_D = 0

            else:
                valid = torch.ones(student_output.size(0), 1, device=noise.device)
                real = F.binary_cross_entropy_with_logits(
                    self.discriminator(denoised_sample_real), valid
                )
                fake = torch.zeros(noise.size(0), 1, device=noise.device)
                fake = F.binary_cross_entropy_with_logits(
                    self.discriminator(denoised_sample_fake.detach()), fake
                )
                loss_D = real + fake
                loss_G = 0

        return [
            loss_G,
            loss_D,
        ]

    def _timestep_sampling(
        self, n_samples: int = 1, device="cpu", timestep_sampling="uniform"
    ) -> torch.Tensor:
        if timestep_sampling == "uniform":
            idx = self.prob.multinomial(n_samples, replacement=True).to(device)

            return torch.tensor(
                self.selected_timesteps, device=device, dtype=torch.long
            )[idx]

        elif timestep_sampling == "teacher":
            return torch.randint(
                0,
                self.teacher_noise_scheduler.config.num_train_timesteps,
                (n_samples,),
                device=device,
            )

    def _scalings_for_boundary_conditions(self, timestep, sigma_data=0.5):
        """
        Compute the scalings for boundary conditions
        """
        c_skip = sigma_data**2 / ((timestep / 0.1) ** 2 + sigma_data**2)
        c_out = (timestep / 0.1) / ((timestep / 0.1) ** 2 + sigma_data**2) ** 0.5
        return c_skip, c_out

    def _predicted_x_0(
        self,
        model_output,
        timesteps,
        sample,
        prediction_type,
        alphas,
        sigmas,
        input_sample,
    ):
        """
        Predict x_0 using the model output and the timesteps depending on the prediction type
        """
        if prediction_type == "epsilon":
            sigmas = extract_into_tensor(sigmas, timesteps, sample.shape)
            alphas = extract_into_tensor(alphas, timesteps, sample.shape)
            alpha_mask = alphas > 0
            alpha_mask = alpha_mask.reshape(-1)
            alpha_mask_0 = alphas == 0
            alpha_mask_0 = alpha_mask_0.reshape(-1)
            pred_x_0 = torch.zeros_like(sample)
            pred_x_0[alpha_mask] = (
                sample[alpha_mask] - sigmas[alpha_mask] * model_output[alpha_mask]
            ) / alphas[alpha_mask]
            pred_x_0[alpha_mask_0] = input_sample[alpha_mask_0]
        elif prediction_type == "v_prediction":
            sigmas = extract_into_tensor(sigmas, timesteps, sample.shape)
            alphas = extract_into_tensor(alphas, timesteps, sample.shape)
            pred_x_0 = alphas * sample - sigmas * model_output
        else:
            raise ValueError(
                f"Prediction type {prediction_type} currently not supported."
            )

        return pred_x_0
    
    def freeze(self):
        """Freeze the model"""
        self.eval()
        for param in self.parameters():
            param.requires_grad = False