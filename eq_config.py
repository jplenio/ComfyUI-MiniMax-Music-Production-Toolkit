"""Versioned EQ parameters and RBJ biquads. Frequencies are always in Hz.

Formula reference: https://www.w3.org/TR/audio-eq-cookbook/
Implementation is independent of the ComfyUI frontend.
"""
from __future__ import annotations

import json
import math
from .audio_dsp_utils import number

SCHEMA = "minimax_eq_v1"
BATCH_SCHEMA = "minimax_eq_batch_v1"
FILTER_TYPES = ("peak", "low_shelf", "high_shelf", "highpass", "lowpass", "notch")
DEFAULT_SETTINGS = '{"schema":"minimax_eq_v1","preamp_db":0,"bands":[]}'


def parse_settings(value, sample_rate=None):
    if isinstance(value, str):
        if len(value) > 65536:
            raise ValueError("EQ settings exceed 64 KiB")
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("EQ settings must be valid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError(f"Expected EQ schema {SCHEMA}")
    if set(value) - {"schema", "preamp_db", "bands"}:
        raise ValueError("Unknown EQ settings field")
    bands = value.get("bands", [])
    if not isinstance(bands, list) or len(bands) > 8:
        raise ValueError("EQ requires a list of at most eight bands")
    result = {"schema": SCHEMA, "preamp_db": number(value.get("preamp_db", 0), "preamp_db", -24, 24), "bands": []}
    ids = set()
    for i, band in enumerate(bands):
        if not isinstance(band, dict) or set(band) - {"id", "enabled", "type", "frequency_hz", "gain_db", "q", "slope"}:
            raise ValueError("Invalid EQ band fields")
        ident = band.get("id", f"band-{i+1}")
        if not isinstance(ident, str) or not ident or len(ident) > 64 or ident in ids:
            raise ValueError("EQ band IDs must be unique nonempty strings (max 64 characters)")
        ids.add(ident)
        kind = band.get("type", "peak")
        enabled = band.get("enabled", True)
        if kind not in FILTER_TYPES or not isinstance(enabled, bool):
            raise ValueError("Invalid EQ type or enabled flag")
        upper = min(20000, 0.45 * sample_rate) if sample_rate and enabled else 20000
        clean = {"id": ident, "enabled": enabled, "type": kind,
                 "frequency_hz": number(band.get("frequency_hz", 1000), "frequency_hz", 20, upper),
                 "gain_db": number(band.get("gain_db", 0), "gain_db", -12, 12),
                 "q": number(band.get("q", 1 / math.sqrt(2)), "q", 0.2, 10),
                 "slope": number(band.get("slope", 1), "slope", 0.25, 1)}
        result["bands"].append(clean)
    return result


def settings_for_batch(value, batch_size, sr):
    if isinstance(value, str):
        if len(value) > 1048576:
            raise ValueError("Batch EQ settings exceed 1 MiB")
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise ValueError("EQ settings must be valid JSON") from exc
    if isinstance(value, dict) and value.get("schema") == BATCH_SCHEMA:
        if set(value) != {"schema", "items"} or not isinstance(value["items"], list) or len(value["items"]) != batch_size:
            raise ValueError("Batch EQ settings must contain exactly one item per AUDIO batch item")
        return [parse_settings(item, sr) for item in value["items"]]
    return [parse_settings(value, sr) for _ in range(batch_size)]


def band_sos(band, sr):
    """Return one normalized float64 SOS; caller has validated parameters."""
    import numpy as np
    w = 2 * math.pi * band["frequency_hz"] / sr
    c, s = math.cos(w), math.sin(w)
    a = 10 ** (band["gain_db"] / 40)
    alpha = s / (2 * band["q"])
    kind = band["type"]
    den = [1 + alpha, -2*c, 1-alpha]
    if kind == "peak":
        num = [1+alpha*a, -2*c, 1-alpha*a]
        den = [1+alpha/a, -2*c, 1-alpha/a]
    elif kind == "lowpass":
        num = [(1-c)/2, 1-c, (1-c)/2]
    elif kind == "highpass":
        num = [(1+c)/2, -(1+c), (1+c)/2]
    elif kind == "notch":
        num = [1, -2*c, 1]
    elif kind in ("low_shelf", "high_shelf"):
        alpha = s/2 * math.sqrt((a+1/a)*(1/band["slope"]-1)+2)
        v = 2*math.sqrt(a)*alpha
        if kind == "low_shelf":
            num = [a*((a+1)-(a-1)*c+v), 2*a*((a-1)-(a+1)*c), a*((a+1)-(a-1)*c-v)]
            den = [(a+1)+(a-1)*c+v, -2*((a-1)+(a+1)*c), (a+1)+(a-1)*c-v]
        else:
            num = [a*((a+1)+(a-1)*c+v), -2*a*((a-1)+(a+1)*c), a*((a+1)+(a-1)*c-v)]
            den = [(a+1)-(a-1)*c+v, 2*((a-1)-(a+1)*c), (a+1)-(a-1)*c-v]
    else:
        raise ValueError(f"Unknown EQ type: {kind}")
    row = np.asarray(num + den, dtype=np.float64) / den[0]
    if not np.isfinite(row).all() or np.max(np.abs(np.roots(row[3:]))) >= 1:
        raise ValueError("Unstable EQ coefficients")
    return row


def design_sos(settings, sr):
    import numpy as np
    settings = parse_settings(settings, sr)
    rows = [band_sos(b, sr) for b in settings["bands"] if b["enabled"] and
            (b["type"] not in ("peak", "low_shelf", "high_shelf") or b["gain_db"] != 0)]
    return np.asarray(rows, dtype=np.float64).reshape(-1, 6)


def response_db(settings, sr, frequencies):
    import numpy as np
    from scipy.signal import sosfreqz
    sos = design_sos(settings, sr)
    h = sosfreqz(sos, worN=frequencies, fs=sr)[1] if len(sos) else np.ones_like(frequencies)
    return 20*np.log10(np.maximum(np.abs(h), 1e-15)) + settings.get("preamp_db", 0)

