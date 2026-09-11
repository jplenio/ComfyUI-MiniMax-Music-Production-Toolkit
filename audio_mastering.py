"""Additive mastering node: own compressor/limiter plus measured LUFS targeting."""
from __future__ import annotations

from .audio_dsp_utils import audio_numpy, as_audio, check_cancelled, number, report_json
from .audio_analysis import measure_loudness
from .audio_compressor import compress
from .audio_limiter import limit_peaks


def master_track(x_ct, sr, *, target_lufs=-14, ceiling_dbtp=-1,
                 max_limiter_reduction_db=6, max_makeup_db=18, lookahead_ms=3,
                 limiter_release_ms=100, **compressor_options):
    import numpy as np
    target_lufs = number(target_lufs, "target_lufs", -30, -5)
    ceiling_dbtp = number(ceiling_dbtp, "ceiling_dbtp", -12, -0.1)
    budget = number(max_limiter_reduction_db, "max_limiter_reduction_db", 1, 18)
    max_makeup_db = number(max_makeup_db, "max_makeup_db", 0, 24)
    before = measure_loudness(x_ct, sr)
    compressed, compression = compress(x_ct, sr, **compressor_options)
    measured = measure_loudness(compressed, sr)
    gain = float(np.clip(target_lufs-measured["integrated_lufs"], -48, max_makeup_db)) if measured["valid"] else 0.0
    attempts, final, after, limiter = [], None, None, None
    reason = "iteration_limit"
    for iteration in range(1, 4):
        check_cancelled()
        final, limiter = limit_peaks(compressed, sr, ceiling_dbtp=ceiling_dbtp, drive_db=gain,
                                    lookahead_ms=lookahead_ms, release_ms=limiter_release_ms)
        if limiter["max_reduction_db"] > budget + 0.05:
            # Render again from the un-limited compressor output, not the previous master.
            gain = max(-48, gain-(limiter["max_reduction_db"]-budget)-0.05)
            final, limiter = limit_peaks(compressed, sr, ceiling_dbtp=ceiling_dbtp, drive_db=gain,
                                        lookahead_ms=lookahead_ms, release_ms=limiter_release_ms)
            reason = "limiter_reduction_budget"
        after = measure_loudness(final, sr)
        correction = 0.0
        if after["true_peak_dbtp"] is not None and after["true_peak_dbtp"] > ceiling_dbtp:
            correction = ceiling_dbtp-after["true_peak_dbtp"]-0.1
            final *= np.float32(10**(correction/20))
            after = measure_loudness(final, sr)
        if after["true_peak_dbtp"] is not None and after["true_peak_dbtp"] > ceiling_dbtp+0.05:
            raise RuntimeError("Mastering could not verify the true-peak ceiling")
        attempts.append({"iteration": iteration, "makeup_db": gain, "safety_gain_db": correction,
                         "output": after, "limiter": limiter})
        if not after["valid"]:
            reason = "silence_or_unmeasurable_loudness"
            break
        error = target_lufs-after["integrated_lufs"]
        if abs(error) <= 0.3:
            reason = "target_reached"
            break
        if error > 0 and (reason == "limiter_reduction_budget" or gain >= max_makeup_db):
            reason = "limiter_reduction_budget" if reason == "limiter_reduction_budget" else "makeup_budget"
            break
        new_gain = float(np.clip(gain+np.clip(error, -6, 6), -48, max_makeup_db))
        if abs(new_gain-gain) < 0.01:
            reason = "makeup_budget"
            break
        gain = new_gain
    return final, {"input": before, "after_compressor": measured, "output": after,
                   "compressor": compression, "attempts": attempts, "target_lufs": target_lufs,
                   "ceiling_dbtp": ceiling_dbtp, "target_reached": reason == "target_reached",
                   "reason": reason, "max_limiter_reduction_db": budget}


class MiniMaxMasteringCompressor:
    DESCRIPTION = "CPU stereo-linked compressor and lookahead limiter with measured LUFS/true peak. FFmpeg required. Existing static Release Prep is unchanged."
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "audio": ("AUDIO",), "bypass": ("BOOLEAN", {"default": False}),
            "target_lufs": ("FLOAT", {"default": -14, "min": -30, "max": -5, "step": 0.1}),
            "ceiling_dbtp": ("FLOAT", {"default": -1, "min": -12, "max": -0.1, "step": 0.1}),
            "target_sample_rate": (["keep", "44100", "48000"], {"default": "keep"}),
            "compressor_enabled": ("BOOLEAN", {"default": True}),
            "threshold_db": ("FLOAT", {"default": -18, "min": -60, "max": 0, "step": 0.1}),
            "ratio": ("FLOAT", {"default": 1.5, "min": 1, "max": 10, "step": 0.1}),
            "knee_db": ("FLOAT", {"default": 6, "min": 0, "max": 24, "step": 0.5}),
            "attack_ms": ("FLOAT", {"default": 20, "min": 1, "max": 200}),
            "release_ms": ("FLOAT", {"default": 150, "min": 10, "max": 2000}),
            "sidechain_hz": ("FLOAT", {"default": 80, "min": 0, "max": 500}),
            "detector": (["RMS", "Peak"], {"default": "RMS"}),
            "input_gain_db": ("FLOAT", {"default": 0, "min": -24, "max": 24, "step": 0.1}),
            "max_makeup_db": ("FLOAT", {"default": 18, "min": 0, "max": 24}),
            "max_limiter_reduction_db": ("FLOAT", {"default": 6, "min": 1, "max": 18}),
            "lookahead_ms": ("FLOAT", {"default": 3, "min": 1, "max": 5, "step": 0.1}),
            "limiter_release_ms": ("FLOAT", {"default": 100, "min": 10, "max": 1000}),
        }}
    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "mastering_json", "info")
    FUNCTION = "process"
    CATEGORY = "MiniMax Music Production Toolkit/mastering"

    def process(self, audio, bypass=False, target_lufs=-14, ceiling_dbtp=-1, target_sample_rate="keep",
                compressor_enabled=True, threshold_db=-18, ratio=1.5, knee_db=6, attack_ms=20,
                release_ms=150, sidechain_hz=80, detector="RMS", input_gain_db=0,
                max_makeup_db=18, max_limiter_reduction_db=6, lookahead_ms=3, limiter_release_ms=100):
        import numpy as np
        from .audio_utils import resample_kaiser_polyphase
        x, sr = audio_numpy(audio, "Mastering", stereo_only=True)
        if bypass:
            return {"ui": {"text": ["Mastering bypass"]}, "result": (audio, report_json({"schema": "minimax_mastering_v1", "bypass": True}), "Bypass")}
        if target_sample_rate not in ("keep", "44100", "48000"):
            raise ValueError("Unknown target sample rate")
        target_sr = sr if target_sample_rate == "keep" else int(target_sample_rate)
        if not 8000 <= target_sr <= 192000:
            raise ValueError("Mastering supports 8–192 kHz")
        # SRC before dynamics: the limiter/meter always see the final sample rate.
        n = (x.shape[-1]*target_sr + sr-1)//sr
        y = np.empty((len(x), x.shape[1], n), dtype=np.float32)
        reports = []
        for b, track in enumerate(x):
            track = resample_kaiser_polyphase(track, sr, target_sr)
            y[b], report = master_track(track, target_sr, target_lufs=target_lufs, ceiling_dbtp=ceiling_dbtp,
                                       max_limiter_reduction_db=max_limiter_reduction_db, max_makeup_db=max_makeup_db,
                                       lookahead_ms=lookahead_ms, limiter_release_ms=limiter_release_ms,
                                       threshold_db=threshold_db, ratio=ratio, knee_db=knee_db, attack_ms=attack_ms,
                                       release_ms=release_ms, sidechain_hz=sidechain_hz, detector=detector,
                                       input_gain_db=input_gain_db, enabled=compressor_enabled)
            reports.append(report)
        summaries = []
        for i, r in enumerate(reports):
            m = r["output"]
            value = f"{m['integrated_lufs']:.1f} LUFS / {m['true_peak_dbtp']:.1f} dBTP" if m["valid"] else "unmeasurable loudness"
            summaries.append(f"Item {i+1}: {value} ({r['reason']})")
        info = " | ".join(summaries)
        encoded = report_json({"schema": "minimax_mastering_v1", "bypass": False,
                               "input_sample_rate": sr, "output_sample_rate": target_sr, "batch_reports": reports})
        return {"ui": {"text": [info]}, "result": (as_audio(y, target_sr), encoded, info)}


NODE_CLASS_MAPPINGS = {"MiniMaxMasteringCompressor": MiniMaxMasteringCompressor}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxMasteringCompressor": "Mastering Compressor – LUFS / True Peak"}
