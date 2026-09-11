"""Bounded spectral analysis and FFmpeg BS.1770 metering for the new tools."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

from .audio_dsp_utils import check_cancelled, db, peak_linear, validate_samples


def measure_loudness(x_ct, sr):
    """Meter only: no loudnorm-processed audio is returned. Mono/stereo layouts."""
    import numpy as np
    import soundfile as sf
    from .ffmpeg_utils import find_ffmpeg

    validate_samples(x_ct)
    if x_ct.ndim != 2 or x_ct.shape[0] not in (1, 2):
        raise ValueError("Loudness measurement requires mono or stereo CT audio")
    peak = peak_linear(x_ct)
    base = {"sample_peak_dbfs": db(peak), "integrated_lufs": None,
            "true_peak_dbtp": None, "lra_lu": None, "plr_db": None,
            "meter": "FFmpeg loudnorm input metrics / BS.1770", "valid": False}
    if peak < 1e-12:
        return dict(base, reason="silence")
    ffmpeg = find_ffmpeg("Mastering loudness measurement needs FFmpeg (or imageio-ffmpeg).")
    with tempfile.TemporaryDirectory(prefix="minimax-meter-") as directory:
        source = Path(directory) / "input.wav"
        log = Path(directory) / "meter.log"
        with sf.SoundFile(str(source), "w", samplerate=sr, channels=len(x_ct), format="WAV", subtype="FLOAT") as wav:
            for start in range(0, x_ct.shape[-1], 65536):
                check_cancelled()
                wav.write(np.ascontiguousarray(x_ct[:, start:start+65536].T))
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-i", str(source),
               "-af", "loudnorm=I=-23:TP=-1:LRA=11:print_format=json", "-f", "null", "-"]
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        with log.open("wb") as stderr:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=stderr, **flags)
            try:
                deadline = time.monotonic() + max(60, 4*x_ct.shape[-1]/sr)
                while proc.poll() is None:
                    check_cancelled()
                    if time.monotonic() > deadline:
                        raise RuntimeError("FFmpeg loudness measurement timed out")
                    try:
                        proc.wait(timeout=0.1)
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
        with log.open("rb") as handle:
            handle.seek(max(0, log.stat().st_size-16384))
            text = handle.read().decode("utf-8", errors="replace")
        if proc.returncode:
            raise RuntimeError(f"FFmpeg loudness measurement failed: {text[-2000:]}")
        start = text.rfind("{")
        try:
            values = json.JSONDecoder().raw_decode(text[start:])[0]
            for key, source_key in (("integrated_lufs", "input_i"), ("true_peak_dbtp", "input_tp"), ("lra_lu", "input_lra")):
                value = float(values[source_key])
                base[key] = value if math.isfinite(value) else None
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Invalid loudness response from FFmpeg") from exc
    base["valid"] = base["integrated_lufs"] is not None and base["true_peak_dbtp"] is not None
    if base["valid"]:
        base["plr_db"] = base["true_peak_dbtp"]-base["integrated_lufs"]
    else:
        base["reason"] = "Below loudness gate or too short to measure"
    return base


def spectral_profile(x_ct, sr, *, grid=None):
    """Welch mean power with per-frame silence gate; channel power, not mono sum.

    Only one 8192-sample frame/channel and running moments are held in scratch.
    Confidence describes spectral evidence, not artistic quality.
    """
    import numpy as np
    from scipy.ndimage import gaussian_filter1d
    validate_samples(x_ct)
    if x_ct.ndim != 2:
        raise ValueError("Spectral analysis expects CT audio")
    grid = np.geomspace(20, min(20000, sr*0.45), 256) if grid is None else np.asarray(grid, dtype=float)
    size = min(8192, x_ct.shape[-1])
    hop = max(1, size//2)
    window = np.hanning(size)
    power = np.zeros(size//2+1)
    sum_db = np.zeros_like(power)
    sum_db2 = np.zeros_like(power)
    count, total = 0, 0
    norm = sr * max(float(np.dot(window, window)), 1e-20)
    for start in range(0, x_ct.shape[-1]-size+1, hop):
        check_cancelled()
        frame = np.asarray(x_ct[:, start:start+size], dtype=np.float64)
        total += 1
        if np.mean(frame*frame) < 1e-10:  # -100 dBFS RMS, not a genre loudness gate
            continue
        spectrum = np.fft.rfft(frame * window, axis=-1)
        psd = np.mean(np.abs(spectrum)**2, axis=0) / norm
        psd[1:-1] *= 2
        power += psd
        d = 10*np.log10(np.maximum(psd, 1e-20))
        sum_db += d
        sum_db2 += d*d
        count += 1
    freqs = np.fft.rfftfreq(size, 1/sr)
    mean = power / max(count, 1)
    level = np.interp(grid, freqs, 10*np.log10(np.maximum(mean, 1e-20)))
    sigma = max(0.5, (math.log(2)/6) / math.log(grid[1]/grid[0]) / 2.355)
    level = gaussian_filter1d(level, sigma=sigma, mode="nearest")
    variance = np.maximum(0, sum_db2/max(count, 1)-(sum_db/max(count, 1))**2)
    std = np.interp(grid, freqs, np.sqrt(variance))
    evidence = (level > max(-130, float(np.max(level))-50)) & (grid >= 2*sr/size)
    confidence = np.where(evidence, 1/(1+std/20), 0.0) if count >= 4 else np.zeros_like(grid)
    return {"frequency_hz": grid.tolist(), "power_db": level.tolist(),
            "confidence": confidence.tolist(), "active_frames": count, "total_frames": total,
            "valid": bool(count >= 4 and np.count_nonzero(confidence) >= 12),
            "sample_rate": sr, "duration_seconds": x_ct.shape[-1]/sr,
            "algorithm": "welch8192_power_log_smooth_1_6_octave_v1"}

