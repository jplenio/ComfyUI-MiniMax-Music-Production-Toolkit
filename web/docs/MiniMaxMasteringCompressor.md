# Mastering Compressor – LUFS / True Peak

Separate stereo-linked compressor, oversampled lookahead limiter and measured
LUFS targeting. CPU only; metering requires FFmpeg or imageio-ffmpeg. Supports
mono/stereo and independent batch items. Multichannel layouts are rejected.

Place after EQ/restoration and before saving. Select the final sample rate here;
do not resample or normalize afterward. Keep the existing **Audio Release Prep**
on Bypass, or SRC-only before this node. Its old static-gain behavior is unchanged.

Start with ratio 1.5, knee 6 dB, attack 20 ms and release 150 ms. Adjust threshold
for the source. LUFS is a separate output target, not the threshold. −14 LUFS /
−1 dBTP is a starting option, not a universal delivery rule. Read measured output
and `target_reached`; a gain/limiter budget can intentionally leave audio quieter.

`compressor_enabled=false` keeps normalization/limiting active. `bypass=true`
returns the input unchanged, without metering or SRC. Sidechain HP affects the
detector only. Limiter release specifies time for **12 dB linear recovery**, while
compressor release is an exponential time constant.

Output TP is independently measured and residual overshoots corrected/rechecked.
Future MP3 encoding can create new peaks and is not covered by that measurement.
Outputs: AUDIO, `mastering_json`, `info`. Full workflow/algorithm details and
limits are documented in `AUDIO_MASTERING.md`.

## Presets

The appended `preset` dropdown offers 12 starting points plus **Custom**:
Balanced - gentle glue, Acoustic - gentle, Classical - preserve dynamics,
Jazz - natural, Vocal pop - smooth, Pop - punchy, Rock - bus glue,
Electronic - tight, Club - loud, Hip-hop - low-end punch, Ambient - spacious,
and Limiter only - transparent.

**Balanced - gentle glue** reproduces the previous settings: −14 LUFS, −1 dBTP,
threshold −18 dB, ratio 1.5, knee 6 dB, attack 20 ms, release 150 ms and 80 Hz
sidechain filter. The workflows select this preset. Old/API calls default to
Custom to preserve their explicit settings.

Selecting a preset fills the visible controls. Editing a dynamics control
switches to Custom. Bypass and output sample rate are independent. In headless
runs, a named preset takes precedence over individual dynamics inputs; choose
Custom to use those inputs. The effective preset is recorded in mastering_json.
These are toolkit starting points for common uses, not certified delivery
standards or automatic guarantees of loudness, quality or freedom from distortion.
