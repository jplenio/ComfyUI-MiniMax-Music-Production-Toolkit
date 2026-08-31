# Audio Release Prep – Static LUFS / True Peak / SRC

High-quality sample-rate conversion plus optional BS.1770 loudness/true-peak measurement and constant full-program gain. It never uses compressor/AGC/time-varying loudness riding.

**Node ID:** `AudioReleasePrep`  
**Category:** `MiniMax Music Production Toolkit/mastering`

## Inputs

### Required

- **`audio`** (`AUDIO`) — Final processed audio to prepare for release, normally after HF repair and POST low-pass. Sample-rate conversion happens before loudness/true-peak measurement so the reported values represent the actual output rate.
- **`target_sample_rate`** (choice: `44100`, `48000`, `keep`) — Final sample rate. 44100 gives standard 44.1 kHz release files, 48000 keeps a 48 kHz production master, and keep leaves the incoming sample rate unchanged. Conversion uses high-quality polyphase FIR resampling.
- **`processing`** (choice: `Resample only`, `Streaming Safe -14 LUFS / -1 dBTP`, `Modern Music -12 LUFS / -2 dBTP`, `Loud Electronic -10 LUFS / -2 dBTP`, `Custom`, `Bypass`) — Release-prep mode. Resample only changes sample rate without loudness gain. The LUFS presets measure ITU-R BS.1770 loudness/true peak and apply ONE constant gain to the whole track, capped by the true-peak target—no compressor, AGC or time-varying gain. Custom uses the two custom target fields; Bypass changes nothing.
- **`custom_target_lufs`** (`FLOAT`) — Integrated loudness target used only when processing=Custom. The node applies a single constant full-program gain; if reaching this target would violate the true-peak ceiling, it stops lower instead of compressing or riding the level.
- **`custom_true_peak_dbtp`** (`FLOAT`) — Maximum true-peak target used only when processing=Custom. More negative values leave more codec/playback headroom. This limit can prevent the requested LUFS target from being reached, by design, to preserve internal dynamics.

## Outputs

- **`audio`** (`AUDIO`)
- **`release_prep_json`** (`STRING`)
- **`info`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
