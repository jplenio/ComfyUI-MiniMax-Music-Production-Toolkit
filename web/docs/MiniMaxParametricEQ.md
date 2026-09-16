# Parametric EQ – 8 Bands

CPU parametric EQ with a curve editor, numeric controls, per-band bypass and Undo.
Supports peak, shelves, high/low-pass and notch. JSON is the canonical saved state;
no GPU, model or download is required.

**Manual EQ preset** offers 24 presets plus Custom; the default is **Flat**.
Try **YuE2 - Smooth highs** for harsh highs, or **YuE2 - Smooth highs (strong)**
for more reduction including a 14 kHz low-pass. These are static tonal starting
points, not artifact removal. Presets set the editable curve and preamp, save
in the existing JSON and support Undo. Edits show Custom. See `EQ_PRESETS.md`.

Connect AUDIO and edit the bands, or connect `MiniMaxAutoEQAnalyze.eq_settings_json`.
Connected settings are read-only in the editor; the rendered first batch item is
shown after execution. The graph preview is not realtime audio. Execute to hear
changes. Unconnected preview assumes 48 kHz until the node has run.

Gain ±12 dB; Q 0.2–10; shelf slope 0.25–1. Frequency must fit the audio sample
rate. Preamp is explicit; there is **no hidden normalization**. Leave headroom
or place Mastering Compressor afterward. Bypass/unity preserves the original
AUDIO; active processing preserves its sample count, rate, batches and channels.

Outputs: processed AUDIO, `eq_report_json`, `info`. Cyan is the current curve;
gold is the last actual response. See `AUDIO_MASTERING.md` for JSON examples,
batch settings, technical details and workflow instructions.
