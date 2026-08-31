# HF Cymbal / Shimmer Repair

Reduces smeared cymbal/hi-hat sustain and artificial high-frequency shimmer while protecting attacks and leaving low/mid-band level untouched.

**Node ID:** `HFCymbalShimmerRepair`  
**Category:** `MiniMax Music Production Toolkit/audio restoration`

## Inputs

### Required

- **`audio`** (`AUDIO`) — Audio entering the high-frequency repair stage, normally the output of FlashSR Hybrid Crossover. Only the high-frequency band is dynamically shaped; low/mid frequencies keep constant gain.
- **`mode`** (choice: `Gentle`, `Cymbal clarity`, `Reverb / shimmer control`, `Custom`, `Bypass`) — Processing preset. Gentle is conservative batch-safe cleanup; Cymbal clarity suppresses smeared sustain more strongly while preserving attacks; Reverb / shimmer control is stronger for diffuse artificial HF tails; Custom uses the visible parameters exactly; Bypass returns the signal unchanged. The visible controls automatically update when a preset is selected.
- **`start_frequency_hz`** (`FLOAT`) — Frequency above which the repair detector/process works. Lower values affect more presence/upper harmonics; higher values restrict treatment to air/cymbal frequencies. Too low can dull instruments/vocals, while too high may miss problematic hi-hat smear. Used exactly in Custom; presets overwrite it with their displayed value.
- **`sustain_reduction_db`** (`FLOAT`) — Maximum dynamic attenuation applied to sustained/non-transient high-frequency energy. Larger values reduce watery cymbal tails and artificial shimmer more strongly but can make cymbals unnaturally short or dark. Used exactly in Custom; presets set their own displayed value.
- **`fast_envelope_ms`** (`FLOAT`) — Time constant of the fast HF envelope used to recognize attacks/transients. Smaller values react more quickly to hi-hat/cymbal attacks; values that are too small can follow fine waveform fluctuations rather than musical transients.
- **`slow_envelope_ms`** (`FLOAT`) — Time constant of the slow HF envelope representing sustained energy. Larger values classify longer tails/reverb as sustain; too large can make the detector slow to adapt when the arrangement changes.
- **`transient_sensitivity`** (`FLOAT`) — Controls how different the fast and slow envelopes must be before HF energy is treated as a transient and protected from reduction. Lower values protect transients more readily; higher values classify more energy as sustain and therefore apply more reduction.
- **`side_hf_reduction_db`** (`FLOAT`) — Static reduction of high-frequency stereo Side information (M/S processing). Useful when artificial reverb/shimmer is excessively wide. Higher values narrow only the HF region; 0 leaves HF stereo width untouched.
- **`static_hf_trim_db`** (`FLOAT`) — Constant gain applied to the processed high-frequency band in addition to dynamic sustain reduction. Negative values gently darken the top end; positive values add brightness and can re-expose artifacts.
- **`min_hf_level_dbfs`** (`FLOAT`) — Detector floor. HF energy below this level is considered too quiet to process dynamically, preventing the node from riding very low-level noise/reverb tails. A more negative value makes the detector active deeper into quiet material.
- **`mix`** (`FLOAT`) — Wet/dry blend for the complete HF repair result. 1.0 is fully processed; 0.0 is original audio; intermediate values parallel-blend the repair and are useful when a preset is slightly too strong.

## Outputs

- **`audio`** (`AUDIO`)
- **`hf_repair_json`** (`STRING`)
- **`info`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
