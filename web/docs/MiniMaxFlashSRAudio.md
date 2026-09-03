# MiniMax FlashSR Audio (integrated)

Integrated Audio Super Resolution (FlashSR) node. It replaces the external `ComfyUI-Egregora-Audio-Super-Resolution` custom node so the example workflow has no dependency on it anymore.

**Node ID:** `MiniMaxFlashSRAudio`  
**Category:** `MiniMax Music Production Toolkit/audio`

## Processing

The behavior matches the previously used external node so existing chains sound the same:

- input is normalized to `[channels, samples]` and resampled to 48 kHz (soxr → scipy `resample_poly` → linear fallback)
- fixed chunking: 5.12 s chunks, 0.50 s overlap, Hann windowed overlap-add stitching
- inference at 48 kHz (FlashSR's design target), optional post-resample to the selected output rate
- `lowpass_input` is forwarded to FlashSR's internal low-pass flag (OFF in the example workflow; the PRE low-pass node controls input bandwidth instead)

## First use / models

The **inference code is bundled** with the toolkit in `flashsr_inference/` (vendored from the upstream FlashSR_Inference and TorchJaekwon repositories; see `flashsr_inference/NOTICE.md`). No code is downloaded into the models directory, and no external custom node is involved.

Only the model **weights** are downloaded on first use, per `models_config.json`:

```text
models/audio/flashsr/student_ldm.pth
models/audio/flashsr/sr_vocoder.pth
models/audio/flashsr/vae.pth
```

Downloads are logged with progress and the run continues afterwards. Set `auto_download` to OFF to fail fast instead. Weight source: Hugging Face dataset `jakeoneijk/FlashSR_weights`.

## Inputs

- **`audio`** (`AUDIO`) — signal to super-resolve.
- **`lowpass_input`** (`BOOLEAN`) — FlashSR internal low-pass flag.
- **`output_sr`** (`48000` / `44100` / `96000`) — delivery sample rate.
- **`auto_download`** (`BOOLEAN`) — enable first-use downloads.

## Outputs

- **`audio`** (`AUDIO`) — super-resolved signal at the selected rate.
- **`settings_json`** (`STRING`) — settings report (inference rate, chunk/overlap sizes, low-pass flag, output rate, device); wired into the production JSON for reproducibility.

## Notes

- FlashSR is generative: reconstructed high frequencies may be invented. The example workflow's hybrid crossover and HF repair stages exist to control exactly that.
- Loaded FlashSR models are cached per process; `MiniMaxLLMUnload` can release them with `unload_flashsr`.
