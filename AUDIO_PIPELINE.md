# Audio processing pipeline

The audio nodes are designed for conservative batch processing. They cannot turn a poor source into a guaranteed professional master, and every restoration stage has limits.

## 1. Declip / overload repair

Hard digital clipping removes waveform information. `Audio Declip / Overload Repair` looks for short near-ceiling flat regions and estimates missing curvature using local boundary slopes and cubic-Hermite interpolation.

Recommended default: **Auto / conservative**.

Use stronger presets only after listening. Very long clipped regions are intentionally skipped because reconstruction becomes increasingly speculative.

## 2. PRE low-pass

A controlled PRE low-pass can remove problematic source high-frequency content before FlashSR reconstructs the upper spectrum. Do not automatically choose the strongest filter: cutting too low discards real transient/cymbal information.

Recommended starting point: **PRE 12 kHz - recommended** for a 32 kHz MiniMax source, then A/B against lighter/bypass settings for acoustic or cymbal-rich material.

## 3. FlashSR hybrid crossover

Pure FlashSR output can sound impressive spectrally while producing artificial/watery high-frequency transients. Hybrid mode keeps a cleanly resampled original and uses FlashSR only as a controlled high-frequency contribution.

Key parameters:

- `crossover_hz`: where FlashSR starts to matter;
- `transition_hz`: how soft the crossover is;
- `flashsr_hf_mix`: reconstructed HF amount.

Lower HF mix values are safer when cymbals or reverbs sound smeared.

## 4. HF cymbal / shimmer repair

This stage works primarily on high-frequency sustained energy and uses separate fast/slow envelopes so attacks can be preserved better than diffuse tails.

Start with **Gentle**. Use `Cymbal clarity` or `Reverb / shimmer control` only on material that actually needs it.

## 5. POST low-pass

The POST filter can remove extreme reconstructed top-end energy after FlashSR/HF repair. It is a cleanup stage, not a replacement for good crossover settings.

## 6. Release preparation

The release-prep node performs HQ sample-rate conversion first, then measures integrated loudness/true peak at the final sample rate.

For loudness modes it computes a **single constant gain for the whole program**. If the requested LUFS increase would exceed the configured true-peak ceiling, the gain is capped instead of invoking dynamic loudness processing.

Consequences:

- no volume pumping from the node;
- no compressor/AGC behavior;
- some quiet masters may finish below the requested LUFS target when the peak ceiling prevents further gain — this is intentional.

`Resample only` is the safest choice when you want to preserve the source level/dynamics exactly.
