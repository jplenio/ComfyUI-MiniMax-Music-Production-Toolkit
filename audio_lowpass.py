"""
ComfyUI FlashSR Lowpass Lab

A transparent offline Butterworth low-pass filter for ComfyUI AUDIO data.

Goals:
- Keep the input sample rate unchanged.
- No normalization, no resampling, no hidden gain changes.
- High-quality Butterworth SOS filtering via SciPy.
- Zero-phase mode for controlled pre-FlashSR cleanup.
- Causal mode for a mild post-FlashSR high-frequency roll-off.
- Safe Nyquist validation to avoid invalid filter frequencies.
- Convenient presets for MiniMax Music 3 -> FlashSR experiments.

ComfyUI AUDIO:
    {
        "waveform": torch.Tensor [B, C, T],
        "sample_rate": int
    }
"""

from __future__ import annotations

from .toolkit_logging import get_logger

LOGGER = get_logger("audio_lowpass")

from typing import Dict, Any, Tuple
import json
import numpy as np
import torch

try:
    from scipy import signal
except Exception as exc:
    signal = None
    _SCIPY_IMPORT_ERROR = exc
else:
    _SCIPY_IMPORT_ERROR = None


# Presets intentionally use a low design order.
# In zero-phase mode scipy.signal.sosfiltfilt applies the filter forwards
# and backwards, so the magnitude attenuation is effectively squared.
PRESETS = {
    "CUSTOM": None,
    "PRE 14 kHz - light": {
        "cutoff_hz": 14000.0,
        "order": 2,
        "phase_mode": "zero_phase",
        "description": "Light cleanup before FlashSR; preserves most MiniMax high-frequency content.",
    },
    "PRE 12 kHz - recommended": {
        "cutoff_hz": 12000.0,
        "order": 2,
        "phase_mode": "zero_phase",
        "description": "Recommended first test before FlashSR; strong suppression of 14-16 kHz while preserving the core spectrum.",
    },
    "PRE 10 kHz - strong": {
        "cutoff_hz": 10000.0,
        "order": 2,
        "phase_mode": "zero_phase",
        "description": "Stronger cleanup; asks FlashSR to reconstruct more of the upper spectrum.",
    },
    "PRE 8 kHz - aggressive": {
        "cutoff_hz": 8000.0,
        "order": 2,
        "phase_mode": "zero_phase",
        "description": "Aggressive cleanup; removes much more original high-frequency information.",
    },
    "POST 20 kHz - recommended gentle": {
        "cutoff_hz": 20000.0,
        "order": 2,
        "phase_mode": "causal",
        "description": "Gentle post-FlashSR roll-off at 48 kHz; leaves ~16-18 kHz largely intact and suppresses the extreme top end.",
    },
    "POST 19 kHz - slightly stronger": {
        "cutoff_hz": 19000.0,
        "order": 2,
        "phase_mode": "causal",
        "description": "Slightly stronger post-FlashSR roll-off for harsh or artificial air.",
    },
}


def _resolve_settings(
    preset: str,
    custom_cutoff_hz: float,
    custom_order: int,
    custom_phase_mode: str,
) -> Tuple[float, int, str, str]:
    cfg = PRESETS.get(preset)
    if cfg is None:
        return (
            float(custom_cutoff_hz),
            int(custom_order),
            str(custom_phase_mode),
            "Custom settings",
        )
    return (
        float(cfg["cutoff_hz"]),
        int(cfg["order"]),
        str(cfg["phase_mode"]),
        str(cfg["description"]),
    )


def _validate_audio(audio: Any) -> Tuple[torch.Tensor, int]:
    if not isinstance(audio, dict):
        raise ValueError("FlashSR Lowpass Lab: AUDIO input must be a ComfyUI AUDIO dictionary.")
    if "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError("FlashSR Lowpass Lab: AUDIO input needs 'waveform' and 'sample_rate'.")
    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])
    if not isinstance(waveform, torch.Tensor):
        raise ValueError("FlashSR Lowpass Lab: audio['waveform'] must be a torch.Tensor.")
    if waveform.ndim != 3:
        raise ValueError(
            f"FlashSR Lowpass Lab: expected waveform shape [B,C,T], got {tuple(waveform.shape)}."
        )
    if sample_rate <= 0:
        raise ValueError(f"FlashSR Lowpass Lab: invalid sample rate {sample_rate}.")
    return waveform, sample_rate


def _filter_channel_zero_phase(x: np.ndarray, sos: np.ndarray) -> np.ndarray:
    """
    Zero-phase offline filtering with safe edge padding.
    sosfiltfilt is ideal for this use because it avoids phase rotation,
    but it needs a minimum amount of audio for padding.
    """
    n = int(x.shape[-1])
    if n < 4:
        return x.copy()

    # Conservative pad length. SciPy's default is similar but depends on SOS layout.
    # Keep it below signal length so short clips remain valid.
    suggested = max(12, 6 * len(sos))
    padlen = min(suggested, n - 1)

    return signal.sosfiltfilt(
        sos,
        x,
        axis=-1,
        padtype="odd",
        padlen=padlen,
    ).astype(np.float32, copy=False)


def _filter_channel_causal(x: np.ndarray, sos: np.ndarray) -> np.ndarray:
    """
    Causal SOS filtering. Initialize the filter close to the first sample's
    steady-state value to avoid an unnecessary startup transient.
    """
    if x.shape[-1] == 0:
        return x.copy()

    zi = signal.sosfilt_zi(sos).astype(np.float32)
    zi = zi * np.float32(x[0])
    y, _ = signal.sosfilt(sos, x, zi=zi)
    return y.astype(np.float32, copy=False)


class FlashSRLowpassLab:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "preset": (
                    list(PRESETS.keys()),
                    {"default": "PRE 12 kHz - recommended"},
                ),
                "custom_cutoff_hz": (
                    "FLOAT",
                    {
                        "default": 12000.0,
                        "min": 20.0,
                        "max": 96000.0,
                        "step": 10.0,
                    },
                ),
                "custom_order": (
                    "INT",
                    {
                        "default": 2,
                        "min": 1,
                        "max": 12,
                        "step": 1,
                    },
                ),
                "custom_phase_mode": (
                    ["zero_phase", "causal"],
                    {"default": "zero_phase"},
                ),
                "bypass": (
                    "BOOLEAN",
                    {"default": False},
                ),
            },
            "optional": {
                "preset_override": ("STRING", {"forceInput": True}),
                "custom_cutoff_override": ("FLOAT", {"forceInput": True}),
                "custom_order_override": ("INT", {"forceInput": True}),
                "custom_phase_override": ("STRING", {"forceInput": True}),
                "bypass_override": ("BOOLEAN", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "info", "preset", "settings_json")
    FUNCTION = "run"
    CATEGORY = "MiniMax Music Production Toolkit/audio restoration"
    OUTPUT_NODE = False

    def run(
        self,
        audio=None,
        preset="PRE 12 kHz - recommended",
        custom_cutoff_hz=12000.0,
        custom_order=2,
        custom_phase_mode="zero_phase",
        bypass=False,
        preset_override=None,
        custom_cutoff_override=None,
        custom_order_override=None,
        custom_phase_override=None,
        bypass_override=None,
    ):
        if signal is None:
            raise RuntimeError(
                "FlashSR Lowpass Lab requires SciPy. "
                "Install requirements.txt in the ComfyUI Python environment. "
                f"Original import error: {_SCIPY_IMPORT_ERROR}"
            )

        waveform, sample_rate = _validate_audio(audio)

        if preset_override not in (None, ""):
            preset = str(preset_override)
        if custom_cutoff_override is not None:
            custom_cutoff_hz = float(custom_cutoff_override)
        if custom_order_override is not None:
            custom_order = int(custom_order_override)
        if custom_phase_override not in (None, ""):
            custom_phase_mode = str(custom_phase_override)
        if bypass_override is not None:
            bypass = bool(bypass_override)

        cutoff_hz, order, phase_mode, description = _resolve_settings(
            preset,
            custom_cutoff_hz,
            custom_order,
            custom_phase_mode,
        )

        if bypass:
            info = (
                f"BYPASS | selected preset={preset} | sample_rate={sample_rate} Hz | "
                f"shape={tuple(waveform.shape)} | no processing"
            )
            settings_json = json.dumps({
                "preset": preset,
                "bypass": True,
                "cutoff_hz": cutoff_hz,
                "order": order,
                "phase_mode": phase_mode,
                "sample_rate": sample_rate,
                "description": description,
            }, ensure_ascii=False)
            return (audio, info, preset, settings_json)

        nyquist = sample_rate / 2.0
        if cutoff_hz <= 0:
            raise ValueError("FlashSR Lowpass Lab: cutoff_hz must be > 0.")
        if cutoff_hz >= nyquist:
            hint = ""
            if preset.startswith("POST"):
                hint = (
                    " The POST 19/20 kHz presets require a 48 kHz (or higher) input. "
                    "Place this node AFTER FlashSR with FlashSR output_sr=48000."
                )
            raise ValueError(
                f"FlashSR Lowpass Lab: cutoff {cutoff_hz:.1f} Hz is invalid for "
                f"sample rate {sample_rate} Hz (Nyquist = {nyquist:.1f} Hz). "
                f"Cutoff must be strictly below Nyquist.{hint}"
            )

        if order < 1 or order > 12:
            raise ValueError("FlashSR Lowpass Lab: order must be between 1 and 12.")
        if phase_mode not in ("zero_phase", "causal"):
            raise ValueError(
                "FlashSR Lowpass Lab: phase_mode must be 'zero_phase' or 'causal'."
            )

        # Second-order sections are numerically more stable than high-order
        # direct-form coefficients.
        sos = signal.butter(
            N=order,
            Wn=cutoff_hz,
            btype="lowpass",
            fs=sample_rate,
            output="sos",
        ).astype(np.float32)

        # Work on CPU float32. Audio filtering is inexpensive compared with FlashSR,
        # and keeping this node off CUDA avoids extra GPU state/VRAM pressure.
        x = waveform.detach().to(device="cpu", dtype=torch.float32).numpy()
        y = np.empty_like(x, dtype=np.float32)

        batch, channels, _ = x.shape
        for b in range(batch):
            for c in range(channels):
                channel = np.ascontiguousarray(x[b, c], dtype=np.float32)
                if phase_mode == "zero_phase":
                    y[b, c] = _filter_channel_zero_phase(channel, sos)
                else:
                    y[b, c] = _filter_channel_causal(channel, sos)

        # Deliberately NO normalization and NO resampling.
        out_waveform = torch.from_numpy(np.ascontiguousarray(y)).float()
        output_audio: Dict[str, Any] = {
            "waveform": out_waveform,
            "sample_rate": int(sample_rate),
        }

        in_peak = float(np.max(np.abs(x))) if x.size else 0.0
        out_peak = float(np.max(np.abs(y))) if y.size else 0.0

        effective_note = (
            "zero-phase forward/backward filtering; magnitude attenuation is effectively doubled"
            if phase_mode == "zero_phase"
            else "causal single-pass filtering"
        )

        info = (
            f"{preset} | cutoff={cutoff_hz:.0f} Hz | Butterworth order={order} | "
            f"phase={phase_mode} | sr={sample_rate} Hz unchanged | "
            f"peak {in_peak:.4f}->{out_peak:.4f} | no normalization | "
            f"{effective_note} | {description}"
        )

        if out_peak > 1.0 and in_peak <= 1.0:
            LOGGER.warning(
                "Filtering created a peak above 1.0 (%.4f). The node intentionally does not normalize.",
                out_peak,
            )

        settings_json = json.dumps({
            "preset": preset,
            "bypass": False,
            "cutoff_hz": cutoff_hz,
            "order": order,
            "phase_mode": phase_mode,
            "sample_rate": sample_rate,
            "description": description,
            "input_peak": in_peak,
            "output_peak": out_peak,
        }, ensure_ascii=False)
        LOGGER.info("%s", info)
        return (output_audio, info, preset, settings_json)


NODE_CLASS_MAPPINGS = {
    "FlashSRLowpassLab": FlashSRLowpassLab,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FlashSRLowpassLab": "FlashSR Lowpass Lab",
}
