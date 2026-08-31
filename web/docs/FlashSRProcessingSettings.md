# FlashSR Processing Settings

Centralizes PRE/POST low-pass settings and FlashSR lowpass_input so one configuration can drive the processing nodes and metadata consistently.

**Node ID:** `FlashSRProcessingSettings`  
**Category:** `MiniMax Music Production Toolkit/config`

## Inputs

### Required

- **`pre_preset`** (choice: `CUSTOM`, `PRE 14 kHz - light`, `PRE 12 kHz - recommended`, `PRE 10 kHz - strong`, `PRE 8 kHz - aggressive`, `POST 20 kHz - recommended gentle`, `POST 19 kHz - slightly stronger`) — Preset for the low-pass stage before FlashSR. Lower cutoffs remove more original high-frequency content and force FlashSR to reconstruct more; use stronger presets only when the source top end is already problematic.
- **`pre_custom_cutoff_hz`** (`FLOAT`) — Custom PRE low-pass cutoff used when pre_preset=CUSTOM. Lower values discard more source treble before FlashSR; do not lower it unnecessarily on cymbal-rich material.
- **`pre_custom_order`** (`INT`) — Butterworth order for the custom PRE filter. Higher orders make the cutoff steeper; zero-phase processing effectively doubles magnitude attenuation.
- **`pre_custom_phase`** (choice: `zero_phase`, `causal`) — Phase mode for the custom PRE filter. zero_phase is normally preferred before FlashSR because it avoids phase rotation; causal applies a one-way filter.
- **`pre_bypass`** (`BOOLEAN`) — Disable the explicit PRE low-pass while leaving the rest of the FlashSR chain connected. Useful for testing whether original source highs are already cleaner without filtering.
- **`post_preset`** (choice: `CUSTOM`, `PRE 14 kHz - light`, `PRE 12 kHz - recommended`, `PRE 10 kHz - strong`, `PRE 8 kHz - aggressive`, `POST 20 kHz - recommended gentle`, `POST 19 kHz - slightly stronger`) — Preset for the low-pass stage after FlashSR. It gently removes extreme reconstructed high-frequency energy; lower cutoffs sound darker but can better hide artificial 'air' or shimmer.
- **`post_custom_cutoff_hz`** (`FLOAT`) — Custom POST low-pass cutoff used when post_preset=CUSTOM. Lower values hide more reconstructed extreme treble but can make the release darker.
- **`post_custom_order`** (`INT`) — Butterworth order for the custom POST filter. Higher values produce a steeper roll-off near the selected cutoff.
- **`post_custom_phase`** (choice: `zero_phase`, `causal`) — Phase mode for the custom POST filter. causal is intentionally available for a natural one-way roll-off; zero_phase avoids phase rotation but changes the effective magnitude slope because filtering is applied twice.
- **`post_bypass`** (`BOOLEAN`) — Disable the explicit POST low-pass for A/B comparison while preserving the rest of the chain.
- **`flashsr_lowpass_input`** (`BOOLEAN`) — Passes the lowpass_input switch to the FlashSR node. Keep OFF when you already perform the explicit PRE low-pass in this workflow; enabling both can apply unintended extra filtering.

## Outputs

- **`pre_preset`** (`STRING`)
- **`pre_cutoff_hz`** (`FLOAT`)
- **`pre_order`** (`INT`)
- **`pre_phase`** (`STRING`)
- **`pre_bypass`** (`BOOLEAN`)
- **`pre_settings_json`** (`STRING`)
- **`post_preset`** (`STRING`)
- **`post_cutoff_hz`** (`FLOAT`)
- **`post_order`** (`INT`)
- **`post_phase`** (`STRING`)
- **`post_bypass`** (`BOOLEAN`)
- **`post_settings_json`** (`STRING`)
- **`flashsr_lowpass_input`** (`BOOLEAN`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
