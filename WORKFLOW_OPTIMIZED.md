# Production and mastering workflows — Release 2.5

Open either complete workflow in ComfyUI:

- [Production](example_workflows/MiniMax_Music3_Production_Toolkit.json)
- [AudioEnhance](example_workflows/MiniMax_Music3_Production_Toolkit_AudioEnhance.json)

The redesigned examples are now the canonical workflows. Both use
the same independently controlled mastering chain:

`Restoration → POST → Auto-EQ application → Manual EQ → Output rate → Mastering → Export`

Auto-EQ analyzes the same post-restoration audio that its application EQ receives.
Its settings feed a dedicated EQ, leaving the second, manual EQ freely editable.
Numbered nodes and a separate green mastering area show the processing order.
In production, artwork occupies the lower lane; output records stay beside the
savers. Color supplements text labels. The production workflow opens on the
mastering chain and that artwork lane; the Audio Enhancement Lab opens on its
source setup.

## Independent controls

The production LLM offers **In ComfyUI / Local app / Cloud** modes and generates
fresh text on each queued execution; the old session-ID helper has been removed.
The **FLUX.2 cover · ON / OFF** control in **05 · ILLUSTRATE / Cover artwork**
defaults to ON. OFF skips
FLUX preflight downloads and image computation and exports audio without a new
cover. See [LLM_PROVIDERS.md](LLM_PROVIDERS.md) for setup and compatibility details.

| Control | Effect | Starting setting |
|---|---|---|
| Auto-EQ `enabled` | Off skips analysis and emits neutral settings | On |
| Manual EQ `bypass` | Disable only manual EQ | False, but empty bands / unity |
| Output rate `target_sample_rate` | Final rate, also with mastering bypassed | 44100; 48000 selectable |
| Master `compressor_enabled` | Compression only; LUFS and limiter stay active | True; ratio 1.5:1 |
| Master `bypass` | Disable all dynamics and loudness processing | False |

The manual EQ can be enabled or bypassed with Auto-EQ either on or off.
No rewiring is required. The linked Auto-EQ application panel shows the automatic
curve; add your own bands in the separate manual EQ panel.

Auto-EQ has Warm tilt, strength 35%, maximum correction 2 dB preconfigured, and is enabled by default. This is a creative option, not a universal spectral
ideal. For reference matching, add a core LoadAudio, connect reference_audio and
select Reference track. Use musically comparable source/reference material.
Personal workflows lacking the optional enabled input retain the analyzer's original
behavior: enabled=True. Disabling analysis does not require a reference.

## Final sample rate and loudness

The former G / Release Prep node is retained solely as **Resample only**. Set
44100 or 48000 there. Keep the final master's target_sample_rate at **keep**.
The dedicated rate stage remains useful because complete mastering bypass also
bypasses the master's own resampling. Thus the workflow still exports the selected
rate with EQ and dynamics switched off. There is no second loudness stage and no
resampling after the limiter.

Starting mastering settings are -14 LUFS / -1 dBTP, ratio 1.5:1, soft knee,
20 ms attack and 150 ms release. Makeup and limiter reduction are bounded.
When these limits prevent the loudness target, the report explains the shortfall.
Turning compressor_enabled off retains loudness targeting and peak protection.
Turning master bypass on disables both. EQ alone provides no peak protection.

These settings are a conservative starting point. Listen at matched loudness,
adjust compression to the source and check the final report. Mastering cannot
repair every balance, arrangement or distortion problem in a stereo mix.
The true-peak measurement describes the PCM sent to export, not a subsequently
decoded MP3 or other downstream processing. See [AUDIO_MASTERING.md](AUDIO_MASTERING.md).

## Production records and behavior changes

The production release branch now uses dynamic mastering in place of its old
static-gain release stage, so its audio intentionally differs from the original.
All music generation, LLM, restoration and artwork settings are retained.
The original audio saver still archives the branch before restoration, with its
existing peak-handling policy (not a guaranteed bit-exact archive).

Production JSON receives the manual EQ report, Auto-EQ analysis and final
mastering report through the existing optional metadata inputs. The analyzer's
applied=false describes analysis itself; the following EQ applies its settings.
The separate automatic application EQ report is not additionally persisted.
The resample-only report still records input/output rates. AudioEnhance exports
FLAC without a central production JSON, as before.

The starting production restoration settings remain PRE 10 kHz, crossover
FlashSR only, POST 19 kHz. Select Original + FlashSR air explicitly if preferred.
Cover render size is 1536 px and embedded cover size is 1024 px. The saved
27B LLM / 32768 context is demanding; select a smaller catalog model/context
for limited memory. These settings do not automatically adapt to hardware.

## Remaining architectural considerations

- Production audio savers wait for cover artwork because they embed its path.
  Hiding the cover group does not remove that dependency.
- Visual layout does not serialize GPU branches. Changing execution scheduling
  requires explicit tested dependencies.
- Provenance links remain visible and use existing nodes. No third-party routing
  extension is introduced.
- Export folder names inherited from the source may contain 44; changing the rate
  changes audio, not path names. Update folders if you want names to reflect 48 kHz.

## Rebuild and validation

Edit the two canonical JSON files directly. The former optimizer script now
validates without rewriting files; its historical input graphs have been retired.
Keep personal workflow copies separate when updating the toolkit.

Automated checks cover generation/artwork settings, graph cycles, bidirectional
link indexes, schema compatibility, exact generated content, independent EQ
controls, default output rate, final master-to-saver routing, group containment
and node overlaps. DSP tests cover neutral Auto-EQ output without analysis and
independent manual bypass, alongside the existing loudness, peak and SRC tests.

Manual acceptance in ComfyUI: open each workflow, inspect the mastering group,
try Auto-EQ on/off with manual EQ on/off, then compression off and full bypass.
Render short mono/stereo sources at both 44100 and 48000; inspect the actual saved
rate, final meter report and listen at matched loudness. No missing reference
should be requested while Auto-EQ is disabled. Widget heights may vary with
frontend versions. Automated layout checks do not replace this live check.
