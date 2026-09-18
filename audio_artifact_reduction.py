"""Conservative, reference-free spectral outlier attenuation (not an AI detector).

Original DSP implementation: joint frequency/time contrast, smoothed bounded
attenuation and one mask shared by all channels. See docs/ARTIFACT_REDUCTION.md.
"""
from __future__ import annotations

import math

from .audio_dsp_utils import audio_numpy, as_audio, check_cancelled, number, report_json

SENSITIVITY = {"Gentle": (12.0, 10.0), "Balanced": (9.0, 8.0), "Strong": (6.0, 6.0)}


def _segment(x, sr, nfft, hop, low, high, threshold, limit, protect):
    import numpy as np
    from scipy.ndimage import gaussian_filter, maximum_filter1d, median_filter
    from scipy.signal import stft, istft

    frequencies, times, spectrum = stft(x, fs=sr, window="hann", nperseg=nfft,
                                      noverlap=nfft-hop, boundary="zeros", padded=True)
    # Power aggregation preserves anti-phase stereo evidence. Shared mask preserves image.
    magnitude = np.sqrt(np.mean(np.abs(spectrum).astype(np.float64)**2, axis=0))
    level = 20*np.log10(np.maximum(magnitude, 1e-12))
    frequency_width = max(5, int(round(350/(sr/nfft))) | 1)
    frequency_baseline = median_filter(level, size=(frequency_width, 1), mode="nearest")
    time_width = max(5, int(round(.30*sr/hop)) | 1)
    temporal_baseline = median_filter(level, size=(1, time_width), mode="nearest")
    prominence = level - frequency_baseline - threshold[0]
    novelty = level - temporal_baseline - threshold[1]
    evidence = np.clip(np.minimum(prominence, novelty)/6.0, 0, 1)
    # Do not chase very quiet FFT bins or try to reconstruct missing information.
    evidence *= level > max(-65.0, float(level.max())-55.0)
    band = np.clip((frequencies-low)/400, 0, 1)*np.clip((high-frequencies)/400, 0, 1)
    reduction = gaussian_filter(evidence, sigma=(1.0, 1.2), mode="nearest", truncate=3)*limit
    if protect:
        rise = level-np.concatenate((level[:, :1], level[:, :-1]), axis=1)
        broadband_onset = np.mean((rise > 8) & (level > -65), axis=0) > .20
        protected = maximum_filter1d(broadband_onset.astype(float), size=9, mode="nearest")
        # Smooth the protection too, avoiding hard gain-mask edges.
        protected = gaussian_filter(protected, sigma=1, mode="nearest", truncate=3)
        reduction *= (1-protected)[None, :]
    reduction *= band[:, None]
    gain = 10**(-reduction/20)
    # Reconstruct ONLY the removed component. Unity is exact, not an STFT roundtrip.
    _, removed = istft(spectrum*(1-gain)[None, :, :], fs=sr, window="hann",
                       nperseg=nfft, noverlap=nfft-hop, boundary=True)
    return removed[..., :x.shape[-1]].astype(np.float32), times, frequencies, reduction


class AudioArtifactReduction:
    DESCRIPTION = (
        "Experimental spectral outlier reduction for brief whistles/metallic spikes. "
        "Heuristics cannot prove a sound is an AI artifact. Compare removed_audio and bypass; "
        "legitimate high notes can also trigger detection. No model or GPU needed."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "audio": ("AUDIO",),
            "enabled": ("BOOLEAN", {"default": True}),
            "mode": (["Reduce", "Analyze only"], {"default": "Reduce"}),
            "sensitivity": (list(SENSITIVITY), {"default": "Balanced"}),
            "min_frequency_hz": ("FLOAT", {"default": 3000.0, "min": 1000.0, "max": 16000.0, "step": 100.0}),
            "max_frequency_hz": ("FLOAT", {"default": 18000.0, "min": 2000.0, "max": 20000.0, "step": 100.0}),
            "max_reduction_db": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 8.0, "step": .25}),
            "protect_transients": ("BOOLEAN", {"default": True}),
            "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": .05}),
        }}

    RETURN_TYPES = ("AUDIO", "AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "removed_audio", "artifact_reduction_json", "info")
    FUNCTION = "process"
    CATEGORY = "Music Production Toolkit/audio restoration"

    def process(self, audio, enabled=True, mode="Reduce", sensitivity="Balanced",
                min_frequency_hz=3000.0, max_frequency_hz=18000.0, max_reduction_db=3.0,
                protect_transients=True, mix=1.0):
        import numpy as np

        x, sr = audio_numpy(audio, "Artifact reduction")
        low = number(min_frequency_hz, "min_frequency_hz", 1000, 16000)
        requested_high = number(max_frequency_hz, "max_frequency_hz", 2000, 20000)
        if requested_high <= low:
            raise ValueError("max_frequency_hz must exceed min_frequency_hz")
        limit = number(max_reduction_db, "max_reduction_db", 0, 8)
        mix = number(mix, "mix", 0, 1)
        if mode not in ("Reduce", "Analyze only") or sensitivity not in SENSITIVITY:
            raise ValueError("Unknown artifact reduction mode or sensitivity")
        high = min(requested_high, sr*.45)
        report = {
            "schema": "music_artifact_reduction_v1", "enabled": bool(enabled), "mode": mode,
            "detector": "time_frequency_outliers_v1", "ai_origin_detection": False,
            "sample_rate": sr, "sensitivity": sensitivity,
            "frequency_prominence_db": SENSITIVITY[sensitivity][0],
            "temporal_novelty_db": SENSITIVITY[sensitivity][1],
            "min_frequency_hz": low, "requested_max_frequency_hz": requested_high,
            "effective_max_frequency_hz": high, "max_reduction_db": limit,
            "protect_transients": bool(protect_transients), "mix": mix,
            "stereo_linked": True, "hidden_normalization": False,
            "candidate_meaning": "spectral outliers, not confirmed artifacts or AI-origin evidence",
            "batch_reports": [],
        }
        removed = np.zeros_like(x)
        status = "bypassed" if not enabled else "no_processing"
        if enabled and high > low and (mode == "Analyze only" or (limit > 0 and mix > 0)):
            # Fixed global hop alignment plus generous context prevents chunk seams.
            nfft = 2**int(round(math.log2(sr*.043)))
            nfft = max(128, min(16384, nfft))
            hop = nfft//4
            core_size = 256*hop
            context = max(64, math.ceil(.5*sr/hop))*hop
            report.update(fft_size=nfft, hop_samples=hop, context_samples=context)
            for b, source in enumerate(x):
                candidates = total_frames = 0
                maximum = 0.0
                windows = []
                window_count = 0
                for start in range(0, source.shape[-1], core_size):
                    check_cancelled()
                    stop = min(start+core_size, source.shape[-1])
                    left, right = start-context, stop+context
                    segment = np.pad(source[:, max(0, left):min(right, source.shape[-1])],
                                     ((0, 0), (max(0, -left), max(0, right-source.shape[-1]))))
                    delta, times, frequencies, reduction = _segment(
                        segment, sr, nfft, hop, low, high, SENSITIVITY[sensitivity], limit,
                        bool(protect_transients))
                    if mode == "Reduce":
                        removed[b, :, start:stop] = delta[:, context:context+stop-start]*mix
                    sample_positions = np.rint(times*sr).astype(np.int64)+left
                    core = (sample_positions >= start) & (sample_positions < stop)
                    strength = reduction[:, core].max(axis=0)
                    total_frames += int(core.sum())
                    candidates += int(np.count_nonzero(strength >= .25))
                    maximum = max(maximum, float(strength.max(initial=0)))
                    # Bounded diagnostic windows, independent of the sample data in reports.
                    core_times = sample_positions[core]/sr
                    for offset in range(0, len(strength), 10):
                        values = strength[offset:offset+10]
                        if values.max(initial=0) < .25:
                            continue
                        window_count += 1
                        if len(windows) < 64:
                            frame = offset+int(values.argmax())
                            column = reduction[:, core][:, frame]
                            windows.append({"time_seconds": round(float(core_times[frame]), 4),
                                            "frequency_hz": round(float(frequencies[column.argmax()]), 1),
                                            "proposed_reduction_db": round(float(values.max()), 3)})
                report["batch_reports"].append({
                    "item": b, "analyzed_frames": total_frames, "candidate_frames": candidates,
                    "candidate_frame_fraction": candidates/max(1, total_frames),
                    "max_proposed_reduction_db": maximum, "candidate_windows": windows,
                    "candidate_window_count": window_count, "windows_truncated": window_count > len(windows),
                })
            status = "analyzed" if mode == "Analyze only" else "processed"
        elif enabled and high <= low:
            status = "frequency_range_unavailable"
        # Difference output is exactly input - delivered audio (within float precision).
        changed = bool(np.any(removed))
        output = as_audio(x-removed, sr) if changed else audio
        if changed:
            np.subtract(x, output["waveform"].numpy(), out=removed)
        report["status"] = status
        report["audio_changed"] = changed
        energy = sum(float(np.sum(removed[..., i:i+65536].astype(np.float64)**2))
                     for i in range(0, removed.shape[-1], 65536))
        report["removed_rms"] = math.sqrt(energy/removed.size)
        count = sum(r["candidate_frames"] for r in report["batch_reports"])
        info = f"Artifact reduction: {status} | {count} candidate frames (not confirmed artifacts) | {sr} Hz"
        return output, as_audio(removed, sr), report_json(report), info


NODE_CLASS_MAPPINGS = {"AudioArtifactReduction": AudioArtifactReduction}
NODE_DISPLAY_NAME_MAPPINGS = {"AudioArtifactReduction": "AI Audio Artifact Reduction (experimental)"}
