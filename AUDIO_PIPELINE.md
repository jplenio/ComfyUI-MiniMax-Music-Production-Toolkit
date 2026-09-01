# Audio processing pipeline

This document describes the restoration/release stages used by the example workflow.

## Signal flow

```text
MiniMax Music 3 source
        ↓
Source Declip / Overload Repair
        ├────────────────────────────→ clean source branch
        ↓
PRE Low-pass
        ↓
FlashSR
        ↓
Hybrid Crossover ←────────────────── clean source branch
        ↓
HF Cymbal / Shimmer Repair
        ↓
POST Low-pass
        ↓
Release Prep (HQ SRC + static LUFS / true peak)
        ↓
44.1 kHz release FLAC + MP3
```

## 1. Source de-clipping

Hard clipping is different from simple level overload. Reducing gain after clipping does not recreate the missing peak shape. The de-clip node looks for near-ceiling flat regions and reconstructs short peaks conservatively.

Recommended unattended mode: `Auto / conservative`.

Long or ambiguous clipped regions may be skipped rather than aggressively invented.

## 2. PRE low-pass

The PRE low-pass controls how much original upper-frequency material FlashSR receives. Lower cutoffs force the SR model to reconstruct more of the upper spectrum, which can be useful for damaged source treble but can also increase hallucinated cymbal/air content.

Use stronger filtering only when the source actually needs it.

## 3. FlashSR

FlashSR performs audio super-resolution/bandwidth extension. Reconstructed high-frequency energy is not guaranteed to equal the original missing waveform, so the workflow does not assume that a full FlashSR replacement is always preferable.

## 4. Hybrid crossover

The hybrid node offers safer combinations of original and SR material.

Recommended starting mode:

`Original + FlashSR air`

This keeps the cleanly resampled original and adds a controlled amount of FlashSR high band. Lower `flashsr_hf_mix` when cymbals, reverb or upper harmonics become watery or artificial.

## 5. HF cymbal / shimmer repair

This stage works mainly in the high band. It distinguishes faster transient energy from sustained HF energy and can attenuate the latter more strongly.

Use it for:

- watery hi-hat sustain;
- smeared cymbal tails;
- synthetic shimmer/reverb haze.

Do not use strong settings automatically on clean material.

## 6. POST low-pass

A gentle POST low-pass can suppress extreme reconstructed top-end energy after hybrid/HF processing. Lower cutoffs are darker but may better hide artificial air.

## 7. Release preparation

The release-prep node resamples first, then measures the audio at the final sample rate.

For LUFS modes it calculates a single requested gain and compares it with the true-peak headroom. The applied gain is the lower of those two values.

Therefore:

- no time-varying gain;
- no compressor;
- no AGC;
- no pumping introduced by this node;
- the target LUFS may not be reached if the true-peak ceiling prevents more gain.

`Resample only` preserves the source level/dynamics when you do not want loudness adjustment.

## 8. File writing and centralized JSON

The three audio savers emit a `save_info_json` output containing the actual saved path, format, sample rate, peak before final file writing, applied save gain, filename mode and embedded-cover size.

The final `Save Production JSON` node consumes these outputs. This both records the final artifact information and ensures the canonical JSON is written after the documented audio files exist.

The legacy `write_json_sidecar` option remains available on individual audio savers but is OFF in the current example workflow (centralized JSON was introduced in v1.0.4).
