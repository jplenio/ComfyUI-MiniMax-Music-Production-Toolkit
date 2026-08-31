# FlashSR Lowpass Lab

Configurable Butterworth low-pass for controlled pre/post FlashSR cleanup, with presets, custom cutoff/order/phase and reproducibility outputs.

**Node ID:** `FlashSRLowpassLab`  
**Category:** `MiniMax Music Production Toolkit/audio restoration`

## Inputs

### Required

- **`audio`** (`AUDIO`) — ComfyUI AUDIO signal to process. The node preserves channel layout unless its processing explicitly states otherwise; check the node's Info/JSON output for sample-rate or level changes.
- **`preset`** (choice: `CUSTOM`, `PRE 14 kHz - light`, `PRE 12 kHz - recommended`, `PRE 10 kHz - strong`, `PRE 8 kHz - aggressive`, `POST 20 kHz - recommended gentle`, `POST 19 kHz - slightly stronger`) — Select a predefined Butterworth low-pass configuration or CUSTOM. PRE presets are intended before FlashSR; POST presets are intended after FlashSR. The visible custom cutoff/order/phase fields update to the selected preset so the effective values are obvious.
- **`custom_cutoff_hz`** (`FLOAT`) — Low-pass cutoff used when preset=CUSTOM. Lower frequencies remove more treble; before FlashSR that forces the model to reconstruct more bandwidth, while after FlashSR it more strongly suppresses artificial air.
- **`custom_order`** (`INT`) — Butterworth filter order used when preset=CUSTOM. Higher order gives a steeper cutoff. In zero_phase mode the filter runs forward and backward, effectively steepening the magnitude response further.
- **`custom_phase_mode`** (choice: `zero_phase`, `causal`) — Filter phase behavior used when preset=CUSTOM. zero_phase uses forward/backward offline filtering to avoid phase rotation; causal is a one-way filter with normal phase shift and is useful for gentle post-processing.
- **`bypass`** (`BOOLEAN`) — When enabled, return the audio unchanged while still providing settings/info outputs. Useful for A/B testing without rewiring the graph.

### Optional

- **`preset_override`** (`STRING`) — Optional connected STRING that overrides the preset widget. Intended for centralized settings nodes; when connected it becomes the effective preset at execution time.
- **`custom_cutoff_override`** (`FLOAT`) — Optional connected FLOAT that overrides custom_cutoff_hz. It matters when the effective preset resolves to CUSTOM.
- **`custom_order_override`** (`INT`) — Optional connected INT that overrides custom_order. It matters when the effective preset resolves to CUSTOM.
- **`custom_phase_override`** (`STRING`) — Optional connected STRING overriding custom_phase_mode. Use 'zero_phase' or 'causal'; it matters when the effective preset is CUSTOM.
- **`bypass_override`** (`BOOLEAN`) — Optional connected BOOLEAN overriding the local bypass widget. This allows one centralized settings node to control whether the filter is active.

## Outputs

- **`audio`** (`AUDIO`)
- **`info`** (`STRING`)
- **`preset`** (`STRING`)
- **`settings_json`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
