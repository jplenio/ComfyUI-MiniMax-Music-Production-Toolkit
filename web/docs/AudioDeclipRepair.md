# Audio Declip / Overload Repair

Detects near-ceiling hard-clipping plateaus and reconstructs plausible missing peak curvature before FlashSR. Uses local cubic-Hermite interpolation and only a single optional whole-track safety gain; it cannot recover exact information destroyed by clipping.

**Node ID:** `AudioDeclipRepair`  
**Category:** `MiniMax Music Production Toolkit/audio restoration`

## Inputs

### Required

- **`audio`** (`AUDIO`) — Original MiniMax/source audio before FlashSR processing. The node searches this signal for near-ceiling flat-topped regions and reconstructs plausible peak curvature before later enhancement stages can exaggerate clipping distortion.
- **`mode`** (choice: `Auto / conservative`, `Standard`, `Strong`, `Custom`, `Analyze only`, `Bypass`) — De-clipping preset. Auto / conservative repairs only strong near-peak plateau evidence and is recommended for unattended batches. Standard widens detection and allows longer repairs. Strong is intentionally aggressive and may alter merely limited peaks. Custom uses the visible values exactly. Analyze only reports clipping without changing audio. Bypass performs no analysis or repair.
- **`detection_threshold_percent`** (`FLOAT`) — Lower edge of the region considered for peak reconstruction, expressed as a percentage of each channel's own maximum absolute sample peak. Lower values replace a wider portion around each clipped crest and can smooth harsher clipping, but values that are too low may reshape legitimate loud transients. Used exactly in Custom/Analyze only; presets show their effective value.
- **`plateau_tolerance_percent`** (`FLOAT`) — Maximum allowed sample-to-sample change inside a supposed flat top, expressed as a percentage of the channel peak. Very small values detect genuinely flat hard-clipping plateaus and avoid mistaking naturally rounded sine/bass peaks for clipping. Larger values also catch slightly processed/rounded clipping but raise false-positive risk.
- **`min_flat_samples`** (`INT`) — Minimum length of a sufficiently flat near-ceiling plateau before the region is treated as clipping. Auto uses 3 samples to avoid reshaping ordinary smooth peaks; Standard can detect shorter two-sample flat tops. A value of 1 is extremely aggressive because any above-threshold peak can qualify.
- **`slope_context_samples`** (`INT`) — Number of clean samples outside each clipped region used to estimate entry and exit slopes for the cubic-Hermite reconstruction. More context smooths the estimate and helps low-frequency peaks; too much context can ignore a very fast transient's local shape.
- **`max_repair_ms`** (`FLOAT`) — Maximum duration of one clipped region that the node is willing to reconstruct. Very long flat tops contain too much missing information for reliable interpolation; those regions are left unchanged and counted as skipped. Increase only when the source has clearly audible long hard-clipped crests.
- **`max_peak_extension_db`** (`FLOAT`) — Safety cap on how far a reconstructed peak may rise above the detected clipping ceiling before final whole-track safety scaling. Higher values allow more natural recovery of strongly chopped peaks but also permit larger speculative overshoot. This is not a loudness boost; the output is subsequently capped with one constant gain when required.
- **`output_ceiling_dbfs`** (`FLOAT`) — Sample-peak safety ceiling applied only when actual repairs create peaks above this level. The node then applies ONE constant gain to the entire track, never a limiter or time-varying gain. -1 dBFS is a safe default before FlashSR and later release processing.
- **`mix`** (`FLOAT`) — Wet/dry blend between the original clipped waveform and reconstructed waveform. 1.0 uses the full repair, 0.0 leaves the original unchanged. Intermediate values can soften a repair that sounds too reconstructed, but also blend some clipping distortion back in.

## Outputs

- **`audio`** (`AUDIO`)
- **`declip_json`** (`STRING`)
- **`info`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
