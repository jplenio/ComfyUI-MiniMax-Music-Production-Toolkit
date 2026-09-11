"""Conservative tone matching. Proposals use exactly the manual EQ's schema/DSP."""
from __future__ import annotations

from .audio_dsp_utils import audio_numpy, check_cancelled, number, report_json
from .audio_analysis import spectral_profile
from .eq_config import SCHEMA, BATCH_SCHEMA, parse_settings, response_db


def fit_eq(source, target, sr, *, strength=0.5, max_gain=3.0, max_bands=6,
           min_hz=40, max_hz=16000):
    import numpy as np
    from scipy.optimize import least_squares
    grid = np.asarray(source["frequency_hz"])
    src = np.asarray(source["power_db"])
    weights = np.minimum(source["confidence"], target["confidence"])
    weights = np.where((grid >= min_hz) & (grid <= min(max_hz, sr*0.45)), weights, 0)
    empty = {"schema": SCHEMA, "preamp_db": 0, "bands": []}
    if not source["valid"] or not target["valid"] or np.count_nonzero(weights) < 12:
        return empty, {"accepted": False, "reason": "Insufficient reliable spectrum (silence, short audio or narrow bandwidth)"}
    delta = np.asarray(target["power_db"])-src
    mask = weights > 0
    delta -= np.median(delta[mask])  # remove loudness, preserve only tonal difference
    delta = np.clip(delta * strength, -max_gain, max_gain)
    # Outside supported bands the desired correction is unity, not missing treble.
    desired = np.where(mask, delta, 0)
    objective_weights = np.where(mask, weights, 0.25)
    initial_error = float(np.average(desired**2, weights=objective_weights))
    if initial_error < 0.0025 or strength == 0:
        return empty, {"accepted": True, "reason": "Already matched", "before_error_db": initial_error**0.5, "after_error_db": initial_error**0.5}

    def config(params):
        bands = [{"id": f"auto-{i//3+1}", "type": "peak", "enabled": True,
                  "frequency_hz": float(np.exp(params[i])), "gain_db": float(params[i+1]),
                  "q": float(np.exp(params[i+2]))} for i in range(0, len(params), 3)]
        return parse_settings({"schema": SCHEMA, "preamp_db": 0, "bands": bands}, sr)

    params = []
    best = empty
    best_error = initial_error
    valid_grid = grid[mask]
    lower_f, upper_f = max(20, float(valid_grid[0])), min(float(valid_grid[-1]), 0.45*sr)
    for _ in range(max_bands):
        check_cancelled()
        remaining = desired-response_db(best, sr, grid)
        index = int(np.argmax(np.abs(remaining)*weights))
        if abs(remaining[index]) < 0.15:
            break
        params.extend([np.log(np.clip(grid[index], lower_f, upper_f)), float(np.clip(remaining[index], -max_gain, max_gain)), 0.0])
        count = len(params)//3

        def residual(p):
            check_cancelled()
            curve = response_db(config(p), sr, grid)
            return np.r_[np.sqrt(objective_weights)*(curve-desired), 0.05*np.asarray(p)[1::3]]

        result = least_squares(residual, params,
                               bounds=(np.tile([np.log(lower_f), -max_gain, np.log(0.3)], count),
                                       np.tile([np.log(upper_f), max_gain, np.log(2)], count)), max_nfev=100)
        params = result.x.tolist()
        candidate = config(params)
        # Verify total response on a denser grid; summed bands can exceed limits.
        dense = np.geomspace(20, min(20000, sr*0.45), 2048)
        for _ in range(8):
            extent = float(np.max(np.abs(response_db(candidate, sr, dense))))
            if extent <= max_gain + 1e-6:
                break
            for band in candidate["bands"]:
                band["gain_db"] *= max_gain/extent * 0.99
        # The last shrink can make the candidate valid even when the loop
        # reaches its iteration limit; always validate the final response.
        extent = float(np.max(np.abs(response_db(candidate, sr, dense))))
        curve = response_db(candidate, sr, grid)
        error = float(np.average((curve-desired)**2, weights=objective_weights))
        if error >= best_error or extent > max_gain+1e-5:
            break
        best, best_error = candidate, error
        params = [v for b in best["bands"] for v in (np.log(b["frequency_hz"]), b["gain_db"], np.log(b["q"]))]
    return best, {"accepted": best_error < initial_error, "before_error_db": initial_error**0.5,
                  "after_error_db": best_error**0.5, "frequency_hz": grid.tolist(),
                  "target_delta_db": desired.tolist(), "predicted_response_db": response_db(best, sr, grid).tolist(),
                  "confidence": weights.tolist(), "reason": "Proposal only; audition and apply through Parametric EQ"}


class MiniMaxAutoEQAnalyze:
    DESCRIPTION = "Analyze tone against a reference or explicit tilt; outputs editable EQ settings. Does not change audio or correct a room."
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "audio": ("AUDIO",),
            "target_mode": (["Reference track", "Warm tilt", "Bright tilt"], {"default": "Reference track"}),
            "strength_percent": ("FLOAT", {"default": 50, "min": 0, "max": 100, "step": 1}),
            "max_gain_db": ("FLOAT", {"default": 3, "min": 0.1, "max": 6, "step": 0.1}),
            "max_bands": ("INT", {"default": 6, "min": 1, "max": 6}),
            "min_frequency_hz": ("FLOAT", {"default": 40, "min": 20, "max": 1000}),
            "max_frequency_hz": ("FLOAT", {"default": 16000, "min": 1000, "max": 20000}),
        }, "optional": {"reference_audio": ("AUDIO",),
                         "enabled": ("BOOLEAN", {"default": True,
                             "tooltip": "Off returns unity EQ settings without spectrum analysis or reference requirements."})}}
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("eq_settings_json", "analysis_json", "info")
    FUNCTION = "analyze"
    CATEGORY = "MiniMax Music Production Toolkit/mastering"

    def analyze(self, audio, target_mode="Reference track", strength_percent=50,
                max_gain_db=3, max_bands=6, min_frequency_hz=40, max_frequency_hz=16000, reference_audio=None,
                enabled=True):
        if not enabled:
            settings = {"schema": "minimax_eq_v1", "preamp_db": 0, "bands": []}
            info = "Auto-EQ off | unity settings | analysis skipped"
            return {"ui": {"text": [info]}, "result": (
                report_json(settings), report_json({"schema": "minimax_auto_eq_report_v1",
                    "enabled": False, "applied": False, "batch_reports": []}), info)}
        import numpy as np
        x, sr = audio_numpy(audio, "Auto-EQ")
        strength = number(strength_percent, "strength_percent", 0, 100)/100
        limit = number(max_gain_db, "max_gain_db", 0.1, 6)
        band_count = number(max_bands, "max_bands", 1, 6)
        if int(band_count) != band_count:
            raise ValueError("max_bands must be an integer")
        lo = number(min_frequency_hz, "min_frequency_hz", 20, 1000)
        hi = number(max_frequency_hz, "max_frequency_hz", 1000, 20000)
        if hi <= lo or lo >= sr*0.45:
            raise ValueError("Auto-EQ frequency range is empty for this sample rate")
        ref = None
        if target_mode == "Reference track":
            if reference_audio is None:
                raise ValueError("Connect reference_audio or choose an explicit tilt target")
            ref, ref_sr = audio_numpy(reference_audio, "Auto-EQ reference")
            if len(ref) not in (1, len(x)):
                raise ValueError("Reference batch must contain one item or match the source batch")
        elif target_mode not in ("Warm tilt", "Bright tilt"):
            raise ValueError("Unknown Auto-EQ target mode")
        items, reports = [], []
        for b, track in enumerate(x):
            grid = np.geomspace(20, min(20000, sr*0.45, ref_sr*0.45 if ref is not None else 20000), 256)
            source = spectral_profile(track, sr, grid=grid)
            if ref is not None:
                target = spectral_profile(ref[0 if len(ref)==1 else b], ref_sr, grid=grid)
            else:
                tilt = (-0.75 if target_mode == "Warm tilt" else 0.75)*np.log2(grid/1000)
                target = dict(source, power_db=(np.asarray(source["power_db"])+tilt).tolist())
            config, report = fit_eq(source, target, sr, strength=strength, max_gain=limit,
                                    max_bands=int(band_count), min_hz=lo, max_hz=hi)
            items.append(config)
            reports.append(dict(report, source=source, target=target))
        settings = items[0] if len(items)==1 else {"schema": BATCH_SCHEMA, "items": items}
        info = f"Auto-EQ proposal | {target_mode} | {sum(len(s['bands']) for s in items)} band(s) | audio unchanged"
        encoded = report_json({"schema": "minimax_auto_eq_report_v1", "target_mode": target_mode,
                               "batch_reports": reports, "applied": False})
        return {"ui": {"text": [info]}, "result": (report_json(settings), encoded, info)}


NODE_CLASS_MAPPINGS = {"MiniMaxAutoEQAnalyze": MiniMaxAutoEQAnalyze}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxAutoEQAnalyze": "Auto-EQ – Analyze / Propose"}
