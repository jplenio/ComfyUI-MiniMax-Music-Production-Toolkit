"""Small boundaries for the additive EQ/mastering tools; no host import at discovery."""
from __future__ import annotations

import json
import math


def number(value, name, minimum, maximum):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, not a boolean")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result


def check_cancelled():
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
    except ImportError:
        return
    throw_exception_if_processing_interrupted()


def audio_numpy(audio, label, *, stereo_only=False):
    import numpy as np
    import torch
    from .audio_utils import validate_audio

    waveform, sr = validate_audio(audio, error_label=label, require_positive_rate=True)
    number(audio["sample_rate"], "sample_rate", 1000, 384000)
    if float(audio["sample_rate"]) != sr:
        raise ValueError(f"{label}: sample rate must be an integer")
    if any(size == 0 for size in waveform.shape):
        raise ValueError(f"{label}: empty AUDIO is not supported")
    if stereo_only and waveform.shape[1] not in (1, 2):
        raise ValueError(f"{label}: supports mono/stereo only; channel layout is ambiguous")
    x = waveform.detach().to(device="cpu", dtype=torch.float32).numpy()
    validate_samples(x)
    return x, sr


def validate_samples(x):
    import numpy as np
    if x.ndim not in (2, 3) or any(s == 0 for s in x.shape):
        raise ValueError("Expected nonempty channels x samples or batch x channels x samples")
    for start in range(0, x.shape[-1], 65536):
        check_cancelled()
        if not np.isfinite(x[..., start:start + 65536]).all():
            raise ValueError("Audio contains NaN or Infinity")


def as_audio(samples, sr):
    import numpy as np
    import torch
    validate_samples(samples)
    return {"waveform": torch.from_numpy(np.ascontiguousarray(samples, dtype=np.float32)),
            "sample_rate": int(sr)}


def report_json(report):
    return json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def peak_linear(samples):
    import numpy as np
    return max(float(np.max(np.abs(samples[..., i:i + 65536])))
               for i in range(0, samples.shape[-1], 65536))


def db(value):
    return 20.0 * math.log10(value) if value > 0 else None

