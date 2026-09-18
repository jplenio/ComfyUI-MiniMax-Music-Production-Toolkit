"""Checked audio VAE decode with one bounded, smaller-tile recovery attempt.

Uses the host VAE's public decode methods; never changes global precision,
devices, model patches or weights. Valid output retains ComfyUI's audio gain
rule. Invalid sampler latents are rejected, not turned into a silent song.
"""
from __future__ import annotations

import torch

from .audio_utils import NonFiniteAudioError, require_finite_tensor
from .toolkit_logging import get_logger

LOGGER = get_logger("audio_decode")


class MiniMaxSafeAudioDecode:
    DESCRIPTION = (
        "Decodes sampler latents with the VAE and validates the result before anything downstream "
        "touches it. Invalid decoder output triggers one retry with smaller tiles instead of writing "
        "broken audio; invalid latents stop immediately."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "samples": ("LATENT",),
                "vae": ("VAE",),
            },
            "optional": {
                "tile_size": ("INT", {"default": 512, "min": 32, "max": 8192, "step": 8,
                    "tooltip": "Latent frames per decode tile. Smaller tiles use less working memory."}),
                "overlap": ("INT", {"default": 64, "min": 0, "max": 1024, "step": 8,
                    "tooltip": "Frames shared between neighbouring decode tiles. Must be smaller than tile_size; more overlap hides seams at a higher cost."}),
                "tiled": ("BOOLEAN", {"default": True,
                    "tooltip": "Use tiled decoding. Invalid decoder output triggers one retry with smaller tiles; invalid sampler latents stop immediately."}),
            },
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("AUDIO",)
    FUNCTION = "decode"
    CATEGORY = "Music Production Toolkit/audio"

    @staticmethod
    def _attempt(vae, latent, tiled, tile_size, overlap, rate):
        with torch.inference_mode():
            decoded = (vae.decode_tiled(latent, tile_x=tile_size, tile_y=tile_size, overlap=overlap)
                       if tiled else vae.decode(latent))
            if not isinstance(decoded, torch.Tensor) or decoded.ndim != 3:
                raise ValueError("MiniMax Safe Audio Decode: expected VAE output [batch, frames, channels].")
            audio = decoded.movedim(-1, 1).float()
            if audio.shape[1] * audio.shape[2] < 2:
                raise NonFiniteAudioError("Audio decoder returned too few samples for normalization.")
            require_finite_tensor(audio, error_label="Audio decoder output")
            # Same std*5, minimum gain divisor 1 rule as ComfyUI's
            # vae_decode_audio; use an owned result instead of editing input.
            divisor = torch.std(audio, dim=[1, 2], keepdim=True) * 5.0
            require_finite_tensor(divisor, error_label="Audio decoder normalization")
            audio = audio / divisor.clamp_min(1.0)
            require_finite_tensor(audio, error_label="Normalized audio decoder output")
        return ({"waveform": audio, "sample_rate": rate},)

    def decode(self, samples, vae, tile_size=512, overlap=64, tiled=True):
        if not isinstance(samples, dict) or not isinstance(samples.get("samples"), torch.Tensor):
            raise ValueError("MiniMax Safe Audio Decode: expected a LATENT dictionary with tensor samples.")
        latent = samples["samples"]
        if latent.is_nested:
            latent = latent.unbind()[-1]
        if latent.ndim != 3:
            raise ValueError("MiniMax Safe Audio Decode: expected audio latents [batch, channels, frames].")
        try:
            require_finite_tensor(latent, error_label="Music sampler latents")
        except NonFiniteAudioError as exc:
            raise NonFiniteAudioError(
                f"{exc} Decoding cannot recover invalid sampler output. Rerun music sampling; "
                "check the diffusion model, sampling settings and precision. No silent repair was applied."
            ) from None
        tile_size, overlap = int(tile_size), int(overlap)
        if tile_size < 32 or overlap < 0 or (tiled and overlap >= tile_size):
            raise ValueError("MiniMax Safe Audio Decode: tile_size must be at least 32 and overlap smaller than tile_size.")
        rate = int(samples.get("sample_rate", getattr(vae, "audio_sample_rate_output", getattr(vae, "audio_sample_rate", 44100))))
        if rate <= 0:
            raise ValueError("MiniMax Safe Audio Decode: sample rate must be positive.")

        try:
            return self._attempt(vae, latent, tiled, tile_size, overlap, rate)
        except NonFiniteAudioError as exc:
            failure = str(exc)
        # Leave the except block before retrying: its traceback can otherwise
        # keep the failed decoded audio buffer alive during the second decode.
        retry_tile = min(512, max(32, tile_size // 2)) if tiled else 512
        retry_overlap = min(32, retry_tile // 4)
        LOGGER.warning("%s Retrying audio decode once with tile_size=%d, overlap=%d. Music sampling is not repeated.",
                       failure, retry_tile, retry_overlap)
        try:
            return self._attempt(vae, latent, True, retry_tile, retry_overlap, rate)
        except NonFiniteAudioError as exc:
            raise NonFiniteAudioError(
                f"MiniMax Safe Audio Decode: smaller-tile retry also failed. {exc} "
                "The incoming latents were finite; check the audio VAE file and ComfyUI decoder/backend. "
                "No invalid audio was passed to export and no samples were replaced with silence."
            ) from None


NODE_CLASS_MAPPINGS = {"MiniMaxSafeAudioDecode": MiniMaxSafeAudioDecode}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxSafeAudioDecode": "MiniMax Safe Audio Decode"}
