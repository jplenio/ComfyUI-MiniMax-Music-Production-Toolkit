# Experimental audio artifact reduction

**AI Audio Artifact Reduction** (`AudioArtifactReduction`) looks for brief,
narrow spectral outliers and attenuates them. It is useful to audition on short
whistles, metallic spikes and some chirpy sounds in generated music. It does
**not** detect whether audio was AI-generated, identify all audible defects or
guarantee their removal. A wanted high note can look like an unwanted whistle.

## Research and implementation decision

Research checked on 2026-09-16:

| Approach | Evidence and scope | Toolkit decision |
| --- | --- | --- |
| Local spectral attenuation | [iZotope Spectral Repair](https://downloads.izotope.com/docs/rx6/35-spectral-repair/index.html) compares a selected region with its surroundings. Human selection provides knowledge of what should be removed. | Implement an original, conservative automatic outlier heuristic with explicit limits and audition output. This is not an implementation of RX. |
| Time/frequency smoothing | [iZotope Spectral De-noise](https://downloads.izotope.com/docs/rx6/34-spectral-de-noise/index.html) explains that heavy denoising can itself create chirpy/watery musical noise, and describes temporal and frequency smoothing. | Smooth a bounded attenuation mask; do not gate bins to silence or reconstruct missing audio. |
| Dynamic resonance control | [iZotope dynamic EQ guide](https://www.izotope.com/community/blog/when-to-use-dynamic-eq-in-a-mix) describes reducing momentary resonances while preserving the rest of a track. | Attenuate only detected time/frequency regions. The existing manual EQ remains appropriate for persistent tonal harshness. |
| Learned music restoration | [Apollo's official repository](https://github.com/JusperLee/Apollo) describes restoration trained with simulated MP3 degradation and mixed music. It does not establish reliable removal of arbitrary YuE2 generation errors. | A future candidate for a separately evaluated model-based node; no Apollo model, code or dependency is included here. |
| Learned speech enhancement | [Resemble Enhance](https://github.com/resemble-ai/resemble-enhance) targets speech and is trained on speech data. | Do not apply a speech denoiser indiscriminately to full music mixes. |

The inference from these sources is that **targeted attenuation is feasible,
but reliable automatic identification of every AI defect is not established**.
No reference recording or clean target is available to this node. Detector
thresholds are engineering starting points, not trained probabilities or a
YuE2-specific validated optimum.

## Workflow placement and switch

The updated `Yue2_MM3_Production_Toolkit.json` contains a **CLEAN** group:

```text
Generated/decoded audio → optional Refinement → Artifact reduction
    → optional Mastering (Auto-EQ → Manual EQ → Rate → Dynamics) → exports
```

In **CHOOSE / Song model**, `artifact_reduction_enabled` turns the node on/off.
It defaults to **on**, with **Balanced** sensitivity, for all three models. It is independent of Refinement
and Mastering: enabling it still works when either or both of those are off.
When Mastering is bypassed, its input is the artifact node's output. Original
generation exports remain original. The detector report always reaches the
Production JSON, including the explicit bypass state.

This placement can address an outlier already in the generated song or one
introduced during optional restoration, before EQ/loudness processing. It is
not inserted twice. The classic MiniMax and Audio Enhancement Lab examples keep
their existing audio wiring; the node can be added manually after restoration
and before Auto-EQ in either graph.

Install the updated toolkit and load the updated main workflow. Old personal
graphs keep their behavior and do not acquire a new processing branch
automatically. The appended central control defaults on. No model download,
GPU, external service or extra package is required.

## Audition procedure

1. `artifact_reduction_enabled` in CHOOSE defaults to on, with **Balanced**, **3 dB**
   maximum reduction, **3000–18000 Hz**, transient protection on and Mix 1.
2. Choose **Analyze only** to inspect candidates without changing any samples.
   Candidate times/frequencies appear in `artifact_reduction_json`, also saved
   under `artifact_reduction` in the canonical Production JSON.
3. Choose **Reduce** and connect **removed_audio** to a native PreviewAudio node
   to hear the difference. This is the actual input minus delivered output,
   including Mix. Analyze-only and disabled modes output silence here.
4. Compare enabled/bypassed versions. If wanted notes or percussion are being
   removed, lower Mix/maximum reduction, increase the lower frequency boundary,
   return to Gentle or turn the node off. Balanced/Strong increase detection
   sensitivity and false-positive risk; they do not change the visible dB limit.

Reports call detections **candidates**, never confirmed AI artifacts. Times
refer to the input audio timeline and are approximate analysis-frame centers;
each batch item has its own report. Up to 64 representative candidate windows
are retained per item, with total counts and a truncation flag. These are
diagnostics, not a calibrated audibility or quality score.

## Algorithm and preservation rules

- CPU short-time Fourier analysis with a Hann window, approximately 43 ms,
  rounded to a power-of-two FFT, 75% overlap. Existing NumPy/SciPy dependencies.
- Channel-power aggregation produces one shared gain mask for all channels;
  anti-phase stereo does not cancel the detector. Batches remain independent.
- A candidate must exceed **both** a local frequency median (approximately
  350 Hz) and a temporal median (approximately 300 ms). Stable sustained tones
  tend to fail the temporal novelty test. Very quiet bins are excluded.
- Gentle requires 12 dB frequency prominence and 10 dB temporal novelty;
  Balanced uses 9/8 dB and Strong 6/6 dB. These thresholds precede smoothing.
- A smoothed, soft-edged frequency mask limits attenuation to the requested
  band and at most `max_reduction_db` per spectral bin. The top edge is capped
  at 45% of the actual sample rate. An unavailable band passes through.
- Optional broadband-onset protection backs off around attacks. It cannot
  guarantee that every legitimate transient or ornament survives unchanged.
- Reconstruct only the removed component and subtract it from the source.
  There is no hard gate, new synthesis, normalization, resampling, duration
  change, tail truncation or change of channel count. Unity returns the original
  AUDIO object. This is not a peak limiter; final peak control stays downstream.
- Fixed-size frame blocks with surrounding context bound spectral scratch
  memory. Only central samples are retained, preserving global hop alignment
  and avoiding independent block-edge fades. Cancellation is checked per block.

## What this version cannot fix

It does not repair wrong lyrics/notes, broken musical structure, missing audio,
clipping, an entire distorted instrument, persistent hiss or all broadband,
watery and phase-related artifacts. Very brief clicks require a different
detector; clipped peaks already have a dedicated toolkit restoration node.
For a consistently sharp tonal balance, try the [YuE2 EQ presets](EQ_PRESETS.md).
Manual spectral editing or regenerating the affected passage can be more
appropriate when a defect overlaps wanted music.

Automated checks cover synthetic outlier attenuation, sustained-tone
preservation, silence, short signals, bypass, analysis-only mode, cancellation,
batch/stereo behavior, chunk seams, metadata and routing. They do **not** prove
perceptual improvement on real YuE2/MiniMax songs. A listening evaluation with
representative source tracks is still needed to judge the effect on a song.
