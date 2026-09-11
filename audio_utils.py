"""Minimal shared AUDIO helpers (F06/F07 / T24).

Deliberately small.  The restoration nodes and the savers process ``[B,C,T]``
CPU float32 tensors; ``flashsr_audio`` uses a different ``[C,T]`` adapter and is
**not** routed through these helpers (its tuple/frame-first heuristics and its
batch-zero selection are separate contracts).

Two things were duplicated verbatim and are owned here:

* the BCT validation rules - six copies with three different message shapes and
  two different sample-rate policies.  :func:`validate_audio` owns the *rules*;
  each caller keeps its historic message and its historic policy.
* the Kaiser-windowed polyphase resampler (beta 14.769656459379492), whose two
  copies must never drift apart - that would silently change the audio.

Ownership contract (A03, applies to every audio module of this toolkit):

* an **incoming** tensor/array - a node input, or a cached output of an upstream
  node - is never modified in place, not even when ``.numpy()`` happens to share
  memory with the caller's tensor;
* a node that must write allocates **one deliberate owned output** array
  (``np.empty``/``np.empty_like``/``copy``) and writes the result there.  One
  incoming reference plus one owned output is the per-stage budget;
* **own scratch buffers** may be reused across channels, chunks and batch items -
  that is what a scratch buffer is for - but a returned array must never alias
  one unless the callee documents it and the caller consumes it immediately;
* a stage that removes a copy must say which copy it kept and why.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Callable, Optional, Tuple

import numpy as np

try:
    import torch  # type: ignore
except ImportError:  # torch ships with ComfyUI; absent only in bare CI/test environments
    torch = None  # type: ignore[assignment]

try:
    from scipy.signal import resample_poly as _scipy_resample_poly
except Exception:  # pragma: no cover - dependency probe
    _scipy_resample_poly = None

# Kaiser beta of the shared high-quality SRC kernel.
KAISER_BETA = 14.769656459379492

# Problems reported by :func:`validate_audio`, most specific first.
AUDIO_PROBLEMS = ("not_mapping", "missing_fields", "torch_missing", "not_tensor", "wrong_ndim", "invalid_rate")


def validate_audio(
    audio: Any,
    *,
    error_label: str,
    template: str = "compact",
    require_positive_rate: bool = False,
) -> Tuple[Any, int]:
    """Validate a ComfyUI AUDIO value and return ``(waveform, sample_rate)``.

    ``template`` selects the message shape the caller has always used:

    * ``"compact"`` - ``"<label>: expected ComfyUI AUDIO with waveform and
      sample_rate."`` and ``"<label>: waveform must be torch.Tensor [B,C,T]."``
    * ``"separate"`` - one message per problem, including the offending shape
      and sample rate.

    ``require_positive_rate`` keeps the historic split: some nodes reject a
    non-positive rate explicitly, others never checked it.
    """
    problem = audio_problem(audio, require_positive_rate=require_positive_rate)
    if problem is None:
        return audio["waveform"], int(audio["sample_rate"])

    waveform = audio.get("waveform") if isinstance(audio, dict) else None
    sample_rate = audio.get("sample_rate") if isinstance(audio, dict) else None
    if template == "separate":
        if problem == "not_mapping":
            raise ValueError(f"{error_label}: AUDIO input must be a ComfyUI AUDIO dictionary.")
        if problem == "missing_fields":
            raise ValueError(f"{error_label}: AUDIO input needs 'waveform' and 'sample_rate'.")
        if problem == "torch_missing":
            raise ValueError(f"{error_label}: AUDIO input needs torch, which is not available.")
        if problem == "not_tensor":
            raise ValueError(f"{error_label}: audio['waveform'] must be a torch.Tensor.")
        if problem == "wrong_ndim":
            shape = tuple(waveform.shape) if hasattr(waveform, "shape") else "?"
            raise ValueError(f"{error_label}: expected waveform [B,C,T], got {shape}.")
        raise ValueError(f"{error_label}: invalid sample rate {sample_rate}.")

    if problem in {"not_mapping", "missing_fields"}:
        raise ValueError(f"{error_label}: expected ComfyUI AUDIO with waveform and sample_rate.")
    if problem == "torch_missing":
        raise ValueError(f"{error_label}: waveform must be torch.Tensor [B,C,T] (torch is not available).")
    if problem == "invalid_rate":
        raise ValueError(f"{error_label}: invalid sample rate.")
    raise ValueError(f"{error_label}: waveform must be torch.Tensor [B,C,T].")


def audio_problem(audio: Any, *, require_positive_rate: bool = False) -> Optional[str]:
    """Return the first problem of a BCT AUDIO value, or ``None`` when valid."""
    if not isinstance(audio, dict):
        return "not_mapping"
    if "waveform" not in audio or "sample_rate" not in audio:
        return "missing_fields"
    if torch is None:
        return "torch_missing"
    waveform = audio["waveform"]
    if not isinstance(waveform, torch.Tensor):
        return "not_tensor"
    if waveform.ndim != 3:
        return "wrong_ndim"
    if require_positive_rate:
        try:
            sample_rate = int(audio["sample_rate"])
        except (TypeError, ValueError):
            return "invalid_rate"
        if sample_rate <= 0:
            return "invalid_rate"
    return None


def resample_kaiser_polyphase(
    x_bct: np.ndarray,
    sr_in: int,
    sr_out: int,
    *,
    resample_poly: Optional[Callable[..., np.ndarray]] = None,
    missing_message: str = "scipy is required for HQ resampling.",
) -> np.ndarray:
    """Kaiser-windowed polyphase resampling along the last axis.

    Identical input/output rates return a float32 view of the input (no copy,
    no dependency needed, matching both historic callers).  Missing SciPy is
    reported with the caller's own message so the dependency error keeps its
    historic wording and timing.
    """
    if int(sr_in) == int(sr_out):
        return np.asarray(x_bct, dtype=np.float32)
    polyphase = resample_poly if resample_poly is not None else _scipy_resample_poly
    if polyphase is None:
        raise RuntimeError(missing_message)
    frac = Fraction(int(sr_out), int(sr_in)).limit_denominator(10000)
    y = polyphase(
        x_bct, frac.numerator, frac.denominator, axis=-1, window=("kaiser", KAISER_BETA)
    )
    return np.asarray(y, dtype=np.float32)
