"""Stereo-linked oversampled lookahead limiter, bounded overlap tiles.

Zero-phase SRC latency is compensated by overlap/cropping. Release is a linear
dB ramp (12 dB per release time), computed with a prefix maximum in O(N).
Final independent true-peak measurement remains the mastering node's authority.
"""
from __future__ import annotations

from .audio_dsp_utils import check_cancelled, number, validate_samples


def limit_peaks(x_ct, sr, *, ceiling_dbtp=-1, drive_db=0, lookahead_ms=3,
                release_ms=100, block_frames=32768):
    """Return a candidate master; call the independent meter before publishing.

    Resampling kernels disagree at track edges. ``master_track`` measures and
    corrects residual overshoots, then measures again. This helper by itself
    does not certify a BS.1770 true-peak ceiling.
    """
    import numpy as np
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    from scipy.signal import resample_poly
    validate_samples(x_ct)
    ceiling_dbtp = number(ceiling_dbtp, "ceiling_dbtp", -12, -0.1)
    drive_db = number(drive_db, "drive_db", -48, 24)
    lookahead_ms = number(lookahead_ms, "lookahead_ms", 1, 5)
    release_ms = number(release_ms, "release_ms", 10, 1000)
    if x_ct.ndim != 2 or len(x_ct) not in (1, 2) or block_frames < 256:
        raise ValueError("Limiter expects mono/stereo CT audio and blocks >= 256 frames")
    factor = 4
    look = max(1, round(sr*factor*lookahead_ms/1000))
    width = look+1
    guard = 64  # source frames, exceeds the resample_poly kernel support
    halo = 2*((look+factor-1)//factor) + 2*guard
    step = 12/(sr*factor*release_ms/1000)
    threshold = 10**((ceiling_dbtp-0.2)/20)  # reserve for SRC / meter rounding
    drive = 10**(drive_db/20)
    n = x_ct.shape[-1]
    out = np.empty_like(x_ct, dtype=np.float32)
    history = np.zeros((len(x_ct), guard*factor))
    previous = 0.0
    max_reduction, sum_reduction = 0.0, 0.0
    for start in range(0, n, block_frames):
        check_cancelled()
        stop = min(start+block_frames, n)
        lo, hi = max(0, start-halo), min(n, stop+halo)
        tile = np.asarray(x_ct[:, lo:hi], dtype=np.float64)*drive
        tile = np.pad(tile, ((0, 0), (max(0, halo-start), max(0, stop+halo-n))))
        up = resample_poly(tile, factor, 1, axis=-1, window=("kaiser", 10.0))
        demand = np.maximum(0, 20*np.log10(np.maximum(np.max(np.abs(up), axis=0), 1e-20)/threshold))
        future = maximum_filter1d(demand, size=width, origin=-(width//2), mode="nearest")
        # Every trailing window's future maximum includes the current demand:
        # this smooth attack cannot reduce protection at the current sample.
        smooth = uniform_filter1d(future, size=width, origin=(width-1)//2, mode="nearest")
        core_start = halo*factor
        core_size = (stop-start)*factor
        count = core_size+guard*factor
        required = np.maximum(demand, smooth)[core_start:core_start+count]
        offsets = np.arange(1, count+1)*step
        reduction = np.maximum.accumulate(np.maximum(required+offsets, previous))-offsets
        reduction = np.maximum(reduction, 0)
        processed = up[:, core_start:core_start+count]*10**(-reduction[None, :]/20)
        extended = np.concatenate((history, processed), axis=-1)
        down = resample_poly(extended, 1, factor, axis=-1, window=("kaiser", 10.0))
        out[:, start:stop] = down[:, guard:guard+stop-start]
        history = processed[:, max(0, core_size-guard*factor):core_size].copy()
        if history.shape[-1] < guard*factor:
            history = np.pad(history, ((0, 0), (guard*factor-history.shape[-1], 0)))
        previous = float(reduction[core_size-1])
        max_reduction = max(max_reduction, float(np.max(reduction[:core_size])))
        sum_reduction += float(np.sum(reduction[:core_size]))
    return out, {"algorithm": "lookahead_4x_linear_db_release_v1", "oversampling": factor,
                 "lookahead_ms": lookahead_ms, "release_ms_per_12db": release_ms,
                 "max_reduction_db": max_reduction, "mean_reduction_db": sum_reduction/(n*factor),
                 "drive_db": drive_db, "ceiling_dbtp": ceiling_dbtp, "internal_margin_db": 0.2}
