# AI Audio Artifact Reduction (experimental)

Detects brief time/frequency outliers and applies a smoothed, bounded reduction.
Useful to audition on whistles and metallic/chirpy spikes; cannot establish
whether a sound is an AI error. Legitimate high notes can also trigger it.

In the main workflow use `artifact_reduction_enabled` in CHOOSE. Default **on**,
independent of Refinement and Mastering. Placement: after optional Refinement,
before Auto-EQ. Original exports remain unchanged.

Default sensitivity is **Balanced**, maximum **3 dB**, **3000–18000 Hz**, transient protection
on. **Analyze only** reports candidates without modifying audio. **Reduce**
applies attenuation; `removed_audio` is the actual removed signal for audition
with PreviewAudio. If wanted notes are audible there, reduce Mix/reduction or
disable. Disabled and Analyze-only modes output silence on removed_audio.

The report contains approximate candidate timestamps/frequencies, sensitivity,
effective frequency range and processing status. Up to 64 windows per batch item
are retained; totals/truncation are explicit. The main workflow saves it under
`artifact_reduction` in Production JSON. Candidates are not confirmed defects.

CPU only; no weights/download. Preserves duration, sample rate, channels/batches
and linked stereo behavior. No normalization or replacement synthesis. Does not
repair wrong notes/lyrics, gaps, clipping or all watery artifacts. See
`docs/ARTIFACT_REDUCTION.md` for research, thresholds, limitations and validation.
