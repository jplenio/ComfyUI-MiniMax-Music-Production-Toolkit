"""Explicit audio-branch selection with real lazy inputs (A04).

The bundled example hard-wires "strong PRE low-pass + full FlashSR replacement".
That is a deliberate choice for *damaged* sources, but running an unrestored
source through the same graph anyway would silently change its rate and length
(the old ``Original SRC only`` mode takes both from the replacement branch).
This node makes the branch an explicit, named decision instead:

* **Keep original** - the input is passed through untouched; no replacement
  branch is requested at all.
* **Careful restore** - a restored branch is blended into the original with an
  explicit mix.
* **Reconstruct bandwidth** - a bandwidth-reconstruction branch is blended in.

Only the branches a profile actually needs are executed: ComfyUI's lazy
evaluation asks :meth:`MiniMaxAudioBranchSelect.check_lazy_status` which inputs
still have to be computed, so an unconnected or unneeded branch is never run.
Lazy evaluation does not stop the *chosen* branch from running - it stops the
other ones, and the preview below saves the downstream stages only.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .audio_utils import resample_kaiser_polyphase
from .toolkit_logging import get_logger

LOGGER = get_logger("audio_branch")

PROFILE_ORIGINAL = "Keep original"
PROFILE_CAREFUL = "Careful restore"
PROFILE_RECONSTRUCT = "Reconstruct bandwidth"
PROFILES: Tuple[str, ...] = (PROFILE_ORIGINAL, PROFILE_CAREFUL, PROFILE_RECONSTRUCT)

# Which upstream inputs each profile needs.  The selector asks only for these.
PROFILE_INPUTS: Dict[str, Tuple[str, ...]] = {
    PROFILE_ORIGINAL: ("original_audio",),
    PROFILE_CAREFUL: ("original_audio", "restored_audio"),
    PROFILE_RECONSTRUCT: ("original_audio", "bandwidth_audio"),
}

# A preview is a parameter-checking aid; the task names 15-30 s.
PREVIEW_MIN_SECONDS = 15.0
PREVIEW_MAX_SECONDS = 30.0


def _split_audio(audio: Any, label: str) -> Tuple[Any, int]:
    """``(waveform[B, C, T], sample_rate)`` for an AUDIO dict."""
    if not isinstance(audio, dict) or "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError(f"MiniMax Audio Branch Select: {label} is not a valid AUDIO value.")
    waveform = audio["waveform"]
    if waveform.dim() == 2:
        waveform = waveform.unsqueeze(0)
    if waveform.dim() != 3:
        raise ValueError(
            f"MiniMax Audio Branch Select: {label} has shape {tuple(waveform.shape)}; expected [B, C, T]."
        )
    return waveform, int(audio["sample_rate"])


def _conform(waveform, rate: int, target_rate: int, target_batch: int, target_channels: int, target_length: int, label: str):
    """Conform a replacement branch to the selector's own output contract.

    The contract belongs to this node - the output rate and length come from the
    *original* input, never from the replacement branch (that was the trap of the
    old ``Original SRC only`` mode).  Returns ``(waveform, notes)``.
    """
    import torch

    notes: List[str] = []
    if rate != target_rate:
        # ``resample_kaiser_polyphase`` works on [C, T] float32 numpy arrays.
        import numpy as np

        moved = []
        for batch_index in range(waveform.shape[0]):
            array = waveform[batch_index].detach().cpu().float().numpy()
            moved.append(torch.from_numpy(resample_kaiser_polyphase(array, rate, target_rate).astype("float32")))
        waveform = torch.stack(moved, dim=0)
        notes.append(f"{label}: resampled {rate} Hz -> {target_rate} Hz to match the original contract")
    if waveform.shape[0] != target_batch:
        if waveform.shape[0] < target_batch:
            waveform = waveform.repeat(target_batch, 1, 1)[:target_batch]
        else:
            waveform = waveform[:target_batch]
        notes.append(f"{label}: batch conformed to {target_batch}")
    if waveform.shape[1] != target_channels:
        if waveform.shape[1] == 1:
            waveform = waveform.repeat(1, target_channels, 1)
        elif target_channels == 1:
            waveform = waveform.mean(dim=1, keepdim=True)
        else:
            waveform = waveform[:, :target_channels]
        notes.append(f"{label}: channels conformed to {target_channels}")
    current = waveform.shape[2]
    if current < target_length:
        import torch as _torch

        waveform = _torch.nn.functional.pad(waveform, (0, target_length - current))
        notes.append(f"{label}: padded {target_length - current} samples to match the original length")
    elif current > target_length:
        waveform = waveform[:, :, :target_length]
        notes.append(f"{label}: trimmed {current - target_length} samples to match the original length")
    return waveform, notes


class MiniMaxAudioBranchSelect:
    """Choose which audio branch is used, explicitly and lazily."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "profile": (list(PROFILES), {"default": PROFILE_CAREFUL}),
                "mix": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "preview_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 60.0, "step": 1.0}),
                "original_audio": ("AUDIO",),
            },
            "optional": {
                # Lazy branches: requested only when the chosen profile needs them.
                "restored_audio": ("AUDIO",),
                "bandwidth_audio": ("AUDIO",),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "branch_report_json", "info")
    FUNCTION = "select"
    CATEGORY = "Music Production Toolkit/audio"
    DESCRIPTION = (
        "Picks one audio branch explicitly (keep original / careful restore / reconstruct bandwidth) and uses "
        "ComfyUI's lazy evaluation so only the needed branch is executed. The output rate and length always follow "
        "the original input, so a replacement branch can never silently change them."
    )

    def check_lazy_status(
        self,
        profile,
        mix=0.35,
        preview_seconds=0.0,
        original_audio=None,
        restored_audio=None,
        bandwidth_audio=None,
    ):
        """Names of the inputs ComfyUI still has to compute for this profile."""
        needed = PROFILE_INPUTS.get(str(profile), ("original_audio",))
        available = {
            "original_audio": original_audio,
            "restored_audio": restored_audio,
            "bandwidth_audio": bandwidth_audio,
        }
        pending = [name for name in needed if available.get(name) is None]
        if pending:
            LOGGER.info("Audio branch '%s' needs: %s", profile, ", ".join(pending))
        return pending

    def select(
        self,
        profile,
        mix=0.35,
        preview_seconds=0.0,
        original_audio=None,
        restored_audio=None,
        bandwidth_audio=None,
    ):
        import torch

        profile = str(profile)
        if profile not in PROFILE_INPUTS:
            raise ValueError(
                f"MiniMax Audio Branch Select: unknown profile '{profile}'. Choose one of: {', '.join(PROFILES)}."
            )
        original, rate = _split_audio(original_audio, "original_audio")
        batch, channels, length = original.shape
        sources = {"original_audio": original}
        notes: List[str] = []

        replacement = None
        replacement_label = None
        if profile == PROFILE_CAREFUL:
            if restored_audio is None:
                raise ValueError(
                    "MiniMax Audio Branch Select: the 'Careful restore' profile needs the restored_audio input "
                    "(a restoration or enhancement branch). Connect it, or choose 'Keep original'."
                )
            replacement, replacement_rate = _split_audio(restored_audio, "restored_audio")
            replacement_label = "restored_audio"
        elif profile == PROFILE_RECONSTRUCT:
            if bandwidth_audio is None:
                raise ValueError(
                    "MiniMax Audio Branch Select: the 'Reconstruct bandwidth' profile needs the bandwidth_audio "
                    "input (a reconstruction branch). Connect it, or choose another profile."
                )
            replacement, replacement_rate = _split_audio(bandwidth_audio, "bandwidth_audio")
            replacement_label = "bandwidth_audio"
        else:
            replacement_rate = 0

        if replacement is not None:
            replacement, conform_notes = _conform(
                replacement, replacement_rate, rate, batch, channels, length, replacement_label
            )
            notes.extend(conform_notes)
            weight = float(max(0.0, min(1.0, mix)))
            if weight <= 0.0:
                notes.append("mix=0: the replacement branch is blended with zero weight (original kept)")
            out = original * (1.0 - weight) + replacement * weight
        else:
            out = original.clone()
            if profile == PROFILE_ORIGINAL:
                notes.append("'Keep original': the input is passed through unchanged; no branch was requested")

        # Preview: bounded to the documented 15-30 s window.  It trims the
        # *result*, so it saves the save/encode stages, not the chosen branch's
        # own inference (that already ran upstream).
        preview = float(preview_seconds or 0.0)
        preview_info = {"requested_seconds": preview, "applied_seconds": 0.0}
        if preview > 0.0:
            applied = max(PREVIEW_MIN_SECONDS, min(PREVIEW_MAX_SECONDS, preview))
            frames = int(applied * rate)
            if frames < out.shape[2]:
                out = out[:, :, :frames]
                notes.append(
                    f"preview: rendered the first {applied:g} s ({frames} samples); the chosen branch already ran "
                    "in full upstream"
                )
            else:
                notes.append(
                    f"preview: {applied:g} s requested but the selection is only "
                    f"{out.shape[2] / rate:g} s long; nothing was trimmed"
                )
            preview_info = {"requested_seconds": preview, "applied_seconds": applied}

        report = {
            "schema": "minimax_audio_branch_v1",
            "profile": profile,
            "sources": {
                "original_audio": {"sample_rate": rate, "channels": channels, "batch": batch, "samples": length},
            },
            "replacement_source": replacement_label,
            "mix": float(max(0.0, min(1.0, mix))) if replacement is not None else None,
            "output": {"sample_rate": rate, "channels": out.shape[1], "batch": out.shape[0], "samples": out.shape[2]},
            "preview": preview_info,
            "notes": notes,
        }
        info = f"Audio branch: {profile} | {rate} Hz, {out.shape[1]} ch, {out.shape[2] / rate:.2f} s"
        for line in notes:
            LOGGER.info("Audio branch %s: %s", profile, line)
        return (
            {"waveform": out.contiguous(), "sample_rate": rate},
            json.dumps(report, ensure_ascii=False, indent=2),
            info,
        )


NODE_CLASS_MAPPINGS = {
    "MiniMaxAudioBranchSelect": MiniMaxAudioBranchSelect,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxAudioBranchSelect": "Audio Branch Select (lazy)",
}
