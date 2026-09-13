# Release 2.5 workflow update

The canonical examples now include Auto-EQ (enabled by default), a separate manual
8-band EQ, resample-only Release Prep, and final compressor/LUFS/true-peak mastering.
Output defaults to 44.1 kHz, with 48 kHz selectable before the limiter. Historical
static-gain Release Prep behavior remains available for personal workflows.
See [the current workflow controls](WORKFLOW_OPTIMIZED.md).

# Audio processing pipeline

This document describes the restoration/release stages used by the example workflow.

## Signal flow

```text
MiniMax Music 3 sampler
        ↓
MiniMax Safe Audio Decode → source archive
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
Auto-EQ (on by default) → separate manual 8-band EQ
    ↓
Release Prep (HQ SRC only, 44.1 / 48 kHz)
    ↓
Mastering compressor → LUFS / true-peak limiter
        ↓
44.1 kHz release FLAC + MP3
```

## Source decoding and export safety

Both decoding alternatives inside the production subgraph use
`MiniMaxSafeAudioDecode`. Valid output follows ComfyUI's `std * 5` gain rule,
channel layout and sample-rate precedence. The existing `tiled_decode` control
and the normal tiled size remain in effect.

Sampler latents are checked before decoding. Invalid latents stop immediately.
If decoded audio or its normalization becomes non-finite (NaN/Infinity), the
node retries decoding once with a conservative tile size of at most 512 and
overlap of at most 32. It reuses the latents, releases failed audio before the
retry and leaves model precision and device management to ComfyUI. The retry
can help with tile-dependent failures; it does not repair invalid sampler
output or model weights.

Both audio savers check every batch element before peak handling or encoding
FLAC, WAV or MP3. Empty/non-finite audio is rejected; it is never silently
replaced with zeroes. Finite audio retains the selected export format, bit
depth, gain policy and metadata. Encoder failures discard the staged file.
See [the decoder reference](web/docs/MiniMaxSafeAudioDecode.md) and
[troubleshooting](TROUBLESHOOTING.md#audio-export-fails-with-a-blank-assertionerror).

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

## Declip findings: what the report tells you (Q01)

The declip node no longer reports only "N candidates repaired". Every channel
report carries:

- `confidence` (`high` / `medium` / `low` / `none`) with `confidence_reason`:
  *short flat-topped crests with context on both sides* is the case the node is
  built for; *most candidates are long plateaus or sit at the signal edge* means
  the material is probably **limiter-processed or intentionally distorted**, and
  that is not safely repairable clipping;
- `regions_for_review`: per candidate the start/end sample, length, plateau
  length, start time in milliseconds and a `classification`
  (`flat_top` / `long_plateau` / `edge_of_signal`), capped at 64 entries with
  `regions_truncated` saying so - audition these spots against the original;
- `caveats`: always that the Hermite reconstruction **interpolates the
  surrounding waveform and does not restore the original samples**, plus the
  limiter/distortion note for low and no confidence. `Analyze only` reports the
  same findings without touching the audio.

For limiter-processed or deliberately distorted material, prefer `Analyze only`
and listen before repairing; a universal "better" preset is not the goal.

### Not implemented yet from Q01

- Band-separated HF repair (presence/sibilance and upper cymbal/air) beside the
  existing broad stereo-linked envelope, which stays the legacy mode; new gain
  curves would need time smoothing, transient protection and a measured-reduction
  readout.
- Hybrid level/time alignment with a *measured* SR delay and delay compensation
  only when the correlation in the shared band is certain enough - never an
  automatic global phase correction from reconstructed high frequencies.
- A guard against stacking the same high-frequency reduction in PRE, HF repair,
  Auto-EQ and POST without noticing.
- The acceptance itself: dry hi-hats, long cymbals, voice/sibilants, ambient,
  bass, distorted guitars, percussive transients and clean sources, compared
  loudness-matched and as a difference signal.
