# Release Notes – v2.6.0

Release date: 2026-09-15

## YuE2 joins MiniMax Music 3

The main addition in 2.6 is **YuE2 selection in the production workflow**.
Open **Yue2_MM3_Production_Toolkit.json** and choose YuE2 or MiniMax Music 3
before writing your song brief. The generator, system prompts, parser and active
generation settings follow your choice.

The brand-new YuE2 model offers excellent musical quality, with competitive
results reported by its developers against leading song generators.
[Official YuE2 evaluation](https://github.com/multimodal-art-projection/YuE#benchmarks).
It also enables a faster production path here: the default skips the complete
Restore/FlashSR section and goes straight to mastering. This saves that processing
and model-loading time; it is not a measured generator-speed comparison with MiniMax.

## Central production choices

Everything is set in **00 · CHOOSE / Song model**:

| Control | Default |
| --- | --- |
| Song model | YuE2 |
| Cover creation | On |
| Refinement / Restore | Model default: MiniMax on, YuE2 off |
| Mastering | On |

Refinement also has explicit On and Off overrides. Disabled stages skip their
audio processing and report dependencies. Cover off skips rendering, preview
and FLUX.2 downloads; Refinement off skips FlashSR downloads. Mastering operates
independently on the generated or refined audio. Production records identify
bypassed sections and retain the effective choices.

## Prompt and production improvements

- Twelve model-specific system prompts in `prompts/system/yue2/`, adapted from
  the MiniMax templates. YuE2 uses separate Style and Lyrics and native ABC
  planning; its generated plan and actual duration are retained in the record.
- Stronger instrumental instructions across every YuE2 template: no sung or
  spoken text, no vocal syllables and tag-only Lyrics. At most, explicitly
  requested closed-mouth background humming may appear in Style. Prompting
  reduces unintended vocals but cannot guarantee their absence in generated audio.
- YuE2 workflow defaults: **40 steps**, independent **360-second maximum duration**,
  **yue2_3b_bf16.safetensors**. Model check and automatic download are enabled.
- Prompt-report Markdown preserves lyric line breaks for both engines, including
  Windows CRLF files and literal text blocks for Markdown viewers.
- Twelve mastering-compressor presets plus **Custom**. **Balanced - gentle glue**
  names the previous settings and preserves their processing behavior.
- Default release-tag comment: **Generated with jplenio Music Production Toolkit**.
- The renamed workflow retains the maintainer's cosmetic/layout edits, with added
  central switches and stage routing.

## Upgrade

Update the toolkit, restart ComfyUI and reload the browser. Load the new dual-model
workflow to receive the stage switches and connections. Existing MiniMax and
Audio Enhancement Lab workflows remain available, and legacy nodes stay registered.

YuE2 requires ComfyUI's native `YuE2GenerateABC`, `YuE2GenerateMusic` and
`EmptyYuE2LatentAudio` nodes. The default BF16 checkpoint is checked/downloaded
into ComfyUI's configured checkpoints directory. See [setup and usage](YUE2.md).

## Validation scope

Automated tests cover model selection, native graph wiring, sampler defaults,
instrumental prompt rules, Markdown line breaks, presets, and the complete
workflow dependency paths for every model/stage combination. Release checks
cover node contracts, workflow links, metadata consistency and archive privacy.
The audio gates were also executed in native ComfyUI on CPU using synthetic
sources, including cache transitions between enabled and bypassed stages.
No new GPU song generation, listening comparison or interactive browser run was
performed as part of this release preparation.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.6.0.zip`
- `Yue2_MM3_Production_Toolkit_v2.6.0.json`
- `MiniMax_Music3_Production_Toolkit_v2.6.0.json`
- `MiniMax_Music3_Production_Toolkit_AudioEnhance_v2.6.0.json`
- `SHA256SUMS.txt`
