"""CPU parametric EQ, independent batch/channel states and bounded scratch space."""
from __future__ import annotations

from .eq_config import DEFAULT_SETTINGS, design_sos, response_db, settings_for_batch
from .audio_dsp_utils import audio_numpy, as_audio, check_cancelled, peak_linear, report_json


def apply_eq(x_ct, sr, settings, block_frames=65536):
    import numpy as np
    from scipy.signal import sosfilt
    if block_frames <= 0:
        raise ValueError("block_frames must be positive")
    sos = design_sos(settings, sr)
    gain = 10 ** (settings["preamp_db"]/20)
    if not len(sos) and gain == 1:
        return x_ct
    out = np.empty(x_ct.shape, dtype=np.float32)
    state = np.zeros((len(sos), x_ct.shape[0], 2), dtype=np.float64)
    for start in range(0, x_ct.shape[-1], block_frames):
        check_cancelled()
        stop = min(start+block_frames, x_ct.shape[-1])
        block = np.asarray(x_ct[:, start:stop], dtype=np.float64) * gain
        if len(sos):
            block, state = sosfilt(sos, block, axis=-1, zi=state)
        out[:, start:stop] = block
    return out


class MiniMaxParametricEQ:
    DESCRIPTION = "Eight-band CPU EQ. Edit the curve or JSON; connect Auto-EQ settings to apply its proposal. No automatic normalization."
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "audio": ("AUDIO",),
            "eq_settings_json": ("STRING", {"default": DEFAULT_SETTINGS, "multiline": True}),
            "bypass": ("BOOLEAN", {"default": False}),
        }}
    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "eq_report_json", "info")
    FUNCTION = "process"
    CATEGORY = "Music Production Toolkit/mastering"

    def process(self, audio, eq_settings_json=DEFAULT_SETTINGS, bypass=False):
        import numpy as np
        x, sr = audio_numpy(audio, "Parametric EQ")
        settings = settings_for_batch(eq_settings_json, len(x), sr)
        reports = []
        unity = bypass or all(not len(design_sos(s, sr)) and s["preamp_db"] == 0 for s in settings)
        out = audio
        if not unity:
            y = np.empty_like(x)
            for b, config in enumerate(settings):
                y[b] = apply_eq(x[b], sr, config)
            out = as_audio(y, sr)
        grid = np.geomspace(20, min(20000, sr*0.45), 256)
        for b, config in enumerate(settings):
            curve = np.zeros_like(grid) if bypass else response_db(config, sr, grid)
            reports.append({"settings": config, "frequency_hz": grid.tolist(), "response_db": curve.tolist(),
                            "suggested_headroom_db": max(0.0, float(np.max(curve)))})
        info = f"{'Bypass / unity' if unity else 'Parametric EQ'} | {sr} Hz | {len(x)} item(s)"
        report = {"schema": "minimax_eq_report_v1", "bypass": bool(bypass), "sample_rate": sr,
                  "batch_reports": reports, "input_peak": peak_linear(x),
                  "output_peak": peak_linear(x if unity else y), "hidden_normalization": False}
        encoded = report_json(report)
        return {"ui": {"eq_report": [encoded]}, "result": (out, encoded, info)}


NODE_CLASS_MAPPINGS = {"MiniMaxParametricEQ": MiniMaxParametricEQ}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxParametricEQ": "Parametric EQ – 8 Bands"}
