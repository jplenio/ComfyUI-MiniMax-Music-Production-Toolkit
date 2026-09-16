# Parametric EQ, Auto-EQ and mastering

The main dual-model workflow offers an independent, default-on
[artifact reduction stage](ARTIFACT_REDUCTION.md) after optional Refinement and
before this mastering chain. Its output also feeds the Mastering bypass, so
turning Mastering off does not disable artifact reduction. Detector candidates
and effective settings are saved separately from mastering reports.

These are **additional** CPU audio tools. They need no AI weights, GPU, Numba,
model downloads or changes to ComfyUI's memory settings. Existing nodes and
saved workflows, including the static `AudioReleasePrep`, retain their behavior.
Restart ComfyUI and refresh the frontend after installing the files.

## Nodes and connections

Find the three nodes in **MiniMax Music Production Toolkit / mastering**:

1. **Auto-EQ – Analyze / Propose** (`MiniMaxAutoEQAnalyze`, optional).
2. **Parametric EQ – 8 Bands** (`MiniMaxParametricEQ`).
3. **Mastering Compressor – LUFS / True Peak** (`MiniMaxMasteringCompressor`).

Typical signal flow:

```text
Load Audio / restoration output ──┬──> Auto-EQ Analyze <── Reference Audio
                                 │           │ eq_settings_json
                                 └──> Parametric EQ
                                             │ AUDIO
                                    Mastering Compressor
                                             │ AUDIO
                                    FLAC / WAV / MP3 saver
```

Auto-EQ does not output processed audio. Feed the **same source** to its analysis
input and the EQ's audio input. Connect its settings output to the EQ's settings
input. For manual correction, leave that connection absent and use the editor.
Run EQ and mastering directly without Auto-EQ when a reference is not needed.

In an existing enhancement workflow, insert EQ after restoration/HF processing,
and put the new master last before the saver. Set the old Release Prep to
**Bypass**, or use it only for SRC **before** mastering. Do not resample or
normalize the master again afterward. Select the desired final rate in the
new mastering node. Keep a separate lossless original branch.

Each node exposes JSON reports plus a short status string. Use a text preview
for reports/status. These reports are not automatically wired into existing
`Save Production JSON` workflows: its optional legacy `metadata_json` can carry
an additive `audio_tools` object after merging the reports with existing
metadata. The unrelated production-JSON work remains with the main improvement
integration; none of its sockets was changed by this implementation.

## Parametric EQ

The editor offers **24 presets plus Custom**, starting at **Flat**, including
two YuE2 curves for gentler upper mids/highs. Selecting a preset writes the
existing settings JSON; Undo restores the previous curve. Connected settings
remain read-only. See [EQ presets](EQ_PRESETS.md) for every recipe and sources.

The graph editor adds a frequency-response canvas, band enable switches,
frequency/gain/Q or shelf-slope inputs, Add/Remove, Reset and Undo. All operations
are available through normal keyboard-accessible controls. Drag a band on the
canvas to adjust frequency and gain; select Q or slope numerically.

The cyan curve is the current preview, thin curves are individual bands, and
gold is the last rendered backend response. Values beyond ±20 dB are visually
clipped by the graph, not by the DSP. The displayed response assumes 48 kHz
until a render supplies the actual rate. This is an **offline** editor, not a
realtime audio plugin. Execute the graph to hear a change.

When settings are connected from another node, the editor becomes read-only.
After execution it displays batch item 1's effective settings. To edit an
Auto-EQ proposal manually, copy its settings JSON into the unconnected widget.
Batch proposals must first be reduced to the desired single item for manual
editing, or kept connected to process the matching batch.

Supported band types:

| Type | Controls | Notes |
|---|---|---|
| `peak` | Frequency, gain, Q | ±12 dB, Q 0.2–10 |
| `low_shelf`, `high_shelf` | Frequency, gain, slope | Slope 0.25–1; Q is ignored |
| `highpass`, `lowpass` | Frequency, Q | One biquad, 12 dB/octave asymptotically; gain is ignored |
| `notch` | Frequency, Q | Narrow rejection; gain is ignored |

Frequency range is 20 Hz to the lower of 20 kHz and 45% of the sample rate.
Active bands outside that range cause an explanatory error rather than silently
changing frequency. Disabled bands may retain frequencies for other rates.
Preamp is explicit and allows ±24 dB. EQ does not normalize or limit peaks.
The suggested headroom in the report is based on the frequency-response maximum,
not a guaranteed true-peak margin.

Canonical settings, also usable in headless/API execution:

```json
{
  "schema": "minimax_eq_v1",
  "preamp_db": -2.0,
  "bands": [
    {"id": "body", "enabled": true, "type": "peak",
     "frequency_hz": 250, "gain_db": -1.5, "q": 0.8},
    {"id": "air", "enabled": true, "type": "high_shelf",
     "frequency_hz": 9000, "gain_db": 1.0, "slope": 1.0}
  ]
}
```

There are at most eight bands. JSON is validated, including duplicate IDs,
unknown fields, invalid booleans and non-finite numbers. Bypass, or zero preamp
with no effective filters, returns the original AUDIO object. Active processing
never mutates input tensors, preserves length/rate and uses separate states
for every channel and batch item. Empty/non-finite audio is rejected.

## Auto-EQ

The **Auto-EQ preset** selector offers 10 starting points plus Custom. It sets
the six existing analysis controls without changing `enabled` or the reference
connection. All bundled workflows use **Warm - gentle (workflow default)**
(Warm tilt, 35%, 2 dB, four bands, 40–16000 Hz), requiring no reference audio. A newly added standalone node retains its
Reference/50%/3 dB/six-band defaults, named **Reference - balanced**. Reference
presets need reference audio. See [EQ presets](EQ_PRESETS.md).

This is the single visible preset selection. The separate target_mode dropdown
is hidden; the preset sets the target and Custom shows it in the explanation.
Numerical controls remain editable, and old saved workflows retain their values.

Missing reference audio in Reference mode now produces a visible/logged warning
and unity EQ, not an exception after generation. The analysis report records
`status: skipped_missing_reference` and `analysis_performed: false`; no implicit
Warm/Bright target is substituted. Remaining manual EQ/mastering can continue.

Reference mode compares broad tonal balance after removing the global level
difference. It does not normalize loudness, reconstruct missing frequencies,
remove recording-room resonances or make unrelated arrangements equivalent.
Start with 50% strength, ±3 dB and no more than six bands. Audition the proposal;
fewer bands and a lower strength can be better than a mathematically closer fit.

Warm/Bright tilt are deliberate creative targets relative to the source
(−/+0.75 dB per octave before strength/clipping). They are not standards or an
automatically correct mastering curve. The source/reference may have different
rates or durations. Comparison uses their shared frequency range; original
audio is not resampled by the analysis node.

The reference batch must contain either one item or as many items as the source.
Mono and stereo references can be compared because channel **powers**, not
channel sums, are aggregated. Anti-phase stereo therefore does not cancel.
At least four active analysis frames and enough reliable frequency bins are
required. Silence, very short clips or narrow-band material return a unity
proposal and an explanatory report. Lack of evidence never triggers a treble
boost to fill in a missing spectrum.

The current fitter uses broad **peak bands** (Q 0.3–2). Shelf filters remain
available manually; automated shelf selection is intentionally not required
for the first reliable fitter. A candidate must reduce weighted spectral error
and satisfy the maximum **combined** response, not just individual gains.

For batch size >1 the settings envelope is:

```json
{"schema":"minimax_eq_batch_v1","items":[
  {"schema":"minimax_eq_v1","preamp_db":0,"bands":[]},
  {"schema":"minimax_eq_v1","preamp_db":0,"bands":[]}
]}
```

The EQ rejects a mismatched batch length. Reports include spectral confidence,
source/target curves, predicted response, fitted bands and before/after fit
error. Confidence measures available spectral evidence, not artistic merit.

## Compressor, limiter and LUFS

Mastering supports mono/stereo, including batches. Ambiguous multichannel layouts
are rejected. Integrated measurement needs FFmpeg on PATH or `imageio-ffmpeg`,
already supported by the toolkit. It is discovered at execution, not at import.
Full bypass needs no FFmpeg, does no SRC and returns the original AUDIO.

### Suggested starting procedure

1. Select the final output rate (`keep`, 44.1 or 48 kHz).
2. Start with ratio 1.5, knee 6 dB, attack 20 ms, release 150 ms and detector HP
   80 Hz. Adjust threshold to the actual input level and listen to transients.
3. Select a loudness target, e.g. −14 LUFS and −1 dBTP as a starting choice,
   not a universal delivery standard.
4. Keep maximum limiter reduction around 6 dB initially. The result may be
   quieter than requested if the target requires excessive limiting.
5. Read the **measured output** and reason in the status/JSON. Loudness targeting
   is complete only when `target_reached` is true; silence never counts as a
   successful loudness match.

`compressor_enabled=false` disables compression only: explicit input gain,
LUFS targeting and limiting remain active. `bypass=true` skips the entire node.
RMS detects mean energy across channels; Peak detects the maximum sample across
channels. Both produce one stereo-linked gain curve. Sidechain HP filters only
the detector, not the audible source.

The LUFS target is distinct from threshold. The implementation measures the
compressor output, adds bounded gain and renders the limiter, then measures
again. At most three loudness iterations run from the **unlimited compressor
output**, avoiding repeated compression of an already limited result. A limiter
budget correction may require a second candidate render within an iteration.
True-peak safety corrections are remeasured independently. Tolerance for
integrated target achievement is ±0.3 LU.

Possible status reasons: `target_reached`, `makeup_budget`,
`limiter_reduction_budget`, `iteration_limit`, or
`silence_or_unmeasurable_loudness`. Reported undefined values are JSON `null`,
never NaN/Infinity. A failed meter or unverifiable peak ceiling raises an error
rather than publishing a successful result.

Compressed formats can introduce new peaks: remeasure a decoded MP3 if its
delivery ceiling matters. This node verifies the AUDIO before encoding, not a
future MP3 file. Saver gain handling is reported separately by existing savers.

## Engineering details and resource use

* `eq_config.py` owns validation and RBJ coefficient design. `audio_eq.py` uses
  float64 coefficients/states, float32 output, zero track-start state and
  bounded SOS blocks. No `sosfiltfilt` doubling of the EQ response.
* `audio_analysis.py` computes Welch power with up to 8192-sample frames,
  50% overlap and logarithmic 1/6-octave smoothing. It keeps running moments,
  not a whole-track spectrogram. LF bins below two analysis bins are excluded
  from automatic fitting because evidence is inadequate.
* `audio_compressor.py` uses a soft-knee feed-forward curve and approximately
  1 ms control cells. Detection includes every audio sample; gain is smoothed
  at the control rate and interpolated. This avoids a slow Python loop over
  millions of audio samples and a mandatory JIT dependency. The minimum attack
  is 1 ms. The exact control period is recorded in the report.
* `audio_limiter.py` uses 4× polyphase oversampling, linked lookahead maxima,
  a smoothed anticipation curve and O(N) prefix maxima for release. Limiter
  release means a linear recovery of **12 dB per selected release time**,
  unlike the compressor's exponential time constant. Overlap tiles preserve
  length without block-edge discontinuities.
* The limiter's candidate is not a certified TP measurement. Reconstruction
  kernels differ especially at track boundaries. `audio_mastering.py` performs
  FFmpeg BS.1770 input-metric measurement and applies/rechecks a constant safety
  attenuation when needed. `loudnorm` is used as a meter, not as a hidden
  dynamic processor.
* Measurement writes one temporary float WAV and removes it in `finally`.
  Chunked writing and cancellation checks keep scratch RAM bounded; this
  version deliberately reuses the toolkit's file-based interchange approach.
  Cancellation kills and waits for the meter subprocess before cleanup.
* ComfyUI AUDIO itself and each node output are full tensors, so this is not a
  streaming graph. A five-minute stereo 48 kHz float32 buffer is about 110 MiB.
  Batch items are processed sequentially; the final batch output still resides
  in RAM. No per-device/global model cache is created by these audio tools.

Formula/API references: [RBJ cookbook](https://www.w3.org/TR/audio-eq-cookbook/),
[SciPy SOS](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfilt.html),
[FFmpeg loudnorm](https://ffmpeg.org/ffmpeg-filters.html#loudnorm).

## Tests and remaining manual acceptance

Run from the toolkit root:

```text
python -B -m unittest discover -s tests -p test_audio_mastering_tools.py -v
python -B -m unittest discover -s tests -p test_node_contracts.py -v
node tests/test_audio_eq_frontend.mjs
node tests/test_audio_eq_browser.mjs
```

The last test optionally requires Playwright and Chromium/Edge in the development
environment; it is not a runtime dependency. The Python suite uses real FFmpeg
when installed and explicitly skips meter checks otherwise. It checks analytical
responses, actual sine gain, inverse filters, coefficient stability, batch
behavior, ownership, cancellation, silence, stereo linkage, limiter block parity,
actual LUFS targeting and intersample-peak correction. The frontend parity test
compares JavaScript coefficients with Python across rates/types/gains.

These are engineering acceptance tests, not a claim of subjective sonic
superiority. Final listening in a real ComfyUI workflow remains appropriate:
compare drums, sustained cymbals, vocals, bass, sparse acoustic and dense music
at matched playback loudness. Check fresh creation, workflow restore, connected
Auto-EQ settings, output saving and user cancellation in the installed host.
Do not replace the legacy node contracts to accommodate a failure.
