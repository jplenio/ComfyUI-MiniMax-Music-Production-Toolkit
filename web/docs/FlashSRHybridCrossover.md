# FlashSR Hybrid Crossover – Preserve Original / Blend Air

Combines a cleanly resampled original with FlashSR in a controlled high-frequency crossover, preserving original transients while adding only as much reconstructed 'air' as desired.

**Node ID:** `FlashSRHybridCrossover`  
**Category:** `MiniMax Music Production Toolkit/audio restoration`

## Inputs

### Required

- **`original_audio`** (`AUDIO`) — Original MiniMax/source audio before FlashSR. It is resampled cleanly to the FlashSR sample rate and provides the trustworthy low/mid and original transient information for hybrid modes.
- **`flashsr_audio`** (`AUDIO`) — FlashSR-upscaled audio. Hybrid modes mainly use its reconstructed high-frequency content rather than blindly replacing the complete original signal.
- **`mode`** (choice: `Original + FlashSR air`, `Hybrid replace above crossover`, `Original SRC only`, `FlashSR only`) — Select how original and FlashSR signals are combined. 'Original + FlashSR air' preserves the complete clean-resampled original and adds only a controlled FlashSR high band. 'Hybrid replace above crossover' uses original low frequencies plus FlashSR high frequencies. Original/FlashSR only are useful A/B references.
- **`crossover_hz`** (`FLOAT`) — Center/cutoff of the linear-phase crossover used to isolate FlashSR high-frequency content. Lower values let FlashSR influence more of cymbals/upper harmonics; higher values preserve more original source information. A good starting range is roughly 13–15 kHz for 32 kHz MiniMax sources.
- **`transition_hz`** (`FLOAT`) — Width/softness of the FIR crossover transition. Wider values produce a gentler spectral blend and reduce sharp crossover behavior; narrower values separate bands more decisively but require a longer/more selective filter.
- **`flashsr_hf_mix`** (`FLOAT`) — Amount of reconstructed FlashSR high band used in hybrid modes. 0 removes the FlashSR HF contribution; 1 uses it at full level; values below 1 are safer for watery cymbals/shimmer. Values above 1 intentionally exaggerate reconstructed air and are normally not recommended for mastering.

## Outputs

- **`audio`** (`AUDIO`)
- **`hybrid_crossover_json`** (`STRING`)
- **`info`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
