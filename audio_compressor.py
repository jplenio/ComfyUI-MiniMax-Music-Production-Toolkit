"""Own feed-forward, stereo-linked compressor. 1 kHz control rate, CPU only.

Detection uses every sample; only the smoothed gain control is reduced to
1 ms cells, then interpolated. No Python loop per audio sample or mandatory JIT.
"""
from __future__ import annotations

import math
from .audio_dsp_utils import check_cancelled, number, validate_samples


def soft_knee_reduction_db(level, threshold, ratio, knee):
    over = level-threshold
    slope = 1/ratio-1
    if knee == 0:
        return slope*max(over, 0)
    if over <= -knee/2:
        return 0.0
    if over >= knee/2:
        return slope*over
    return slope*(over+knee/2)**2/(2*knee)


def compress(x_ct, sr, *, threshold_db=-18, ratio=1.5, knee_db=6, attack_ms=20,
             release_ms=150, sidechain_hz=80, detector="RMS", input_gain_db=0, enabled=True):
    import numpy as np
    from scipy.signal import butter, sosfilt
    validate_samples(x_ct)
    if x_ct.ndim != 2 or len(x_ct) not in (1, 2):
        raise ValueError("Compressor expects mono/stereo CT audio")
    threshold_db = number(threshold_db, "threshold_db", -60, 0)
    ratio = number(ratio, "ratio", 1, 10)
    knee_db = number(knee_db, "knee_db", 0, 24)
    attack_ms = number(attack_ms, "attack_ms", 1, 200)
    release_ms = number(release_ms, "release_ms", 10, 2000)
    sidechain_hz = number(sidechain_hz, "sidechain_hz", 0, min(500, sr*0.4))
    input_gain_db = number(input_gain_db, "input_gain_db", -24, 24)
    if detector not in ("RMS", "Peak"):
        raise ValueError("Unknown compressor detector")
    gain = 10**(input_gain_db/20)
    n = x_ct.shape[-1]
    cell = max(1, round(sr/1000))
    frames = (n+cell-1)//cell
    levels = np.zeros(frames, dtype=np.float64)
    hp = butter(2, sidechain_hz, btype="highpass", fs=sr, output="sos") if sidechain_hz else None
    state = np.zeros((len(hp), len(x_ct), 2)) if hp is not None else None
    for f in range(0, frames, 1024):
        check_cancelled()
        stop = min(frames, f+1024)
        block = np.asarray(x_ct[:, f*cell:min(n, stop*cell)], dtype=np.float64)*gain
        if hp is not None:
            block, state = sosfilt(hp, block, axis=-1, zi=state)
        missing = (stop-f)*cell-block.shape[-1]
        if missing:
            block = np.pad(block, ((0, 0), (0, missing)))
        shaped = block.reshape(len(x_ct), stop-f, cell)
        if detector == "Peak":
            levels[f:stop] = np.max(np.abs(shaped), axis=(0, 2))
        else:
            power = np.sum(shaped*shaped, axis=(0, 2))
            divisor = np.full(stop-f, cell*len(x_ct), dtype=float)
            if missing:
                divisor[-1] = (cell-missing)*len(x_ct)
            levels[f:stop] = np.sqrt(power/divisor)
    level_db = 20*np.log10(np.maximum(levels, 1e-15))
    attack = math.exp(-cell/(sr*attack_ms/1000))
    release = math.exp(-cell/(sr*release_ms/1000))
    reductions = np.zeros(frames)
    previous = 0.0
    if enabled:
        for i, level in enumerate(level_db):
            if i % 4096 == 0:
                check_cancelled()
            target = soft_knee_reduction_db(float(level), threshold_db, ratio, knee_db)
            coefficient = attack if target < previous else release
            previous = coefficient*previous + (1-coefficient)*target
            reductions[i] = previous
    # Gains are located at cell ends, with unity at the beginning of the track.
    positions = np.r_[0, np.minimum((np.arange(frames)+1)*cell, n)]
    values = np.r_[0, reductions]
    out = np.empty_like(x_ct, dtype=np.float32)
    for start in range(0, n, 65536):
        check_cancelled()
        stop = min(start+65536, n)
        env = np.interp(np.arange(start, stop), positions, values)
        out[:, start:stop] = x_ct[:, start:stop] * (gain*10**(env/20))
    return out, {"algorithm": "linked_feedforward_control_1ms_v1", "enabled": bool(enabled),
                 "control_period_ms": 1000*cell/sr, "detector": detector,
                 "max_reduction_db": float(-reductions.min()), "mean_reduction_db": float(-reductions.mean()),
                 "fraction_over_3db": float(np.mean(reductions < -3)), "input_gain_db": input_gain_db,
                 "threshold_db": threshold_db, "ratio": ratio, "knee_db": knee_db,
                 "attack_ms": attack_ms, "release_ms": release_ms, "sidechain_hz": sidechain_hz}

