# MiniMax Music Production Toolkit 2.x – Combined Release Notes

All twelve 2.x release notes (2.0.0–2.6.0) are collected here, newest first.
These are historical descriptions: model choices, defaults, limits and verification
results describe their respective releases. For current behavior, see
[the README](README.md), [the YuE2 guide](docs/YUE2.md) and [3.0.0 notes](RELEASE_NOTES_v3.0.0.md).

## Releases

- [2.6.0](#v260)
- [2.5.2](#v252)
- [2.5.1](#v251)
- [2.5.0](#v250)
- [2.1.1](#v211)
- [2.1.0](#v210)
- [2.0.5](#v205)
- [2.0.4](#v204)
- [2.0.3](#v203)
- [2.0.2](#v202)
- [2.0.1](#v201)
- [2.0.0](#v200)

---

## v2.6.0

Release date: 2026-09-15

### YuE2 joins MiniMax Music 3

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

### Central production choices

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

### Prompt and production improvements

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

### Upgrade

Update the toolkit, restart ComfyUI and reload the browser. Load the new dual-model
workflow to receive the stage switches and connections. Existing MiniMax and
Audio Enhancement Lab workflows remain available, and legacy nodes stay registered.

YuE2 requires ComfyUI's native `YuE2GenerateABC`, `YuE2GenerateMusic` and
`EmptyYuE2LatentAudio` nodes. The default BF16 checkpoint is checked/downloaded
into ComfyUI's configured checkpoints directory. See [setup and usage](docs/YUE2.md).

### Validation scope

Automated tests cover model selection, native graph wiring, sampler defaults,
instrumental prompt rules, Markdown line breaks, presets, and the complete
workflow dependency paths for every model/stage combination. Release checks
cover node contracts, workflow links, metadata consistency and archive privacy.
The audio gates were also executed in native ComfyUI on CPU using synthetic
sources, including cache transitions between enabled and bypassed stages.
No new GPU song generation, listening comparison or interactive browser run was
performed as part of this release preparation.

### Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.6.0.zip`
- `Yue2_MM3_Production_Toolkit_v2.6.0.json`
- `MiniMax_Music3_Production_Toolkit_v2.6.0.json`
- `MiniMax_Music3_Production_Toolkit_AudioEnhance_v2.6.0.json`
- `SHA256SUMS.txt`

---

## v2.5.2

Release date: 2026-09-13

### Summary

2.5.2 is a bug-fix release. It hardens the audio export path and the music
sampler against invalid numerical output, and it makes the documented
runtime-safety mode work as described. Nothing else changes: node interfaces,
workflow layout, stored settings and the LLM defaults stay as they are.

**Preview of image and song.** The generated cover and the finished song stay
visible right in the workflow: `PreviewImage` shows the artwork as soon as the
cover saver has written it, and `PreviewAudio` plays the exported track. Both are
part of the production example and need no setup.

### Fixed

- **Audio export never writes invalid samples.** Both audio savers validate the
  entire batch before peak handling and encoding. NaN/Infinity audio used to end
  in a blank SoundFile assertion while writing FLAC; the remaining encoder
  assertions now carry format, sample-rate and library diagnostics, and the
  incomplete staging file is removed.
- **Both decoder branches check their input and their output.** The production
  subgraph uses `MiniMaxSafeAudioDecode` for the normal and the tiled decoder.
  It validates sampler latents, decoded audio and the normalization step,
  retries decoding once with conservative tiles when only the decoding failed
  numerically, and never replaces bad samples with silence.
- **The music sampler no longer repeats an identical non-finite run.**
  `KSamplerWithConfig` failed twice on the same seed in the reporting run: the
  noise follows the seed and the conditioning and weights are unchanged, so the
  second pass reproduced the same latents and only doubled the longest stage of
  the prompt. Non-finite latents now stop immediately with the concrete remedy
  (`--bf16-unet`, `--fp32-unet`, or a new seed). The one retry for
  capture/CUDA-graph backend *errors* — where clearing the captured state can
  help — is unchanged.
- **`MINIMAX_MUSIC3_RUNTIME_SAFETY=auto` works as documented.** The policy
  parser folded `auto` into `off`, so the risky-backend branch (Blackwell-class
  CUDA or ROCm) could never run and the automatic mode silently did nothing.
  `off` is still the default and stays inert.
- **`TROUBLESHOOTING.md` documents the remaining non-finite DiT class** with the
  dtype decision measured on the reporting machine (float16 without flags;
  `--bf16-unet` changes only the DiT and is VRAM-neutral; `--fp32-unet` also
  switches the FLUX.2 cover to fp32) and the experiment order, so the upstream
  issue is not re-diagnosed from scratch.
- **Release-gate hygiene.** The FFmpeg pipe timeout test no longer races the
  process start (it could fail a release build at random), and the regression
  coverage now includes decoder recovery, input ownership, real FLAC/WAV
  roundtrips, batch validation, failed-export cleanup and the sampler guard.

### Breaking changes

None. Node identifiers, inputs, outputs, return orders, widget names and stored
values are unchanged; the example workflows keep their layout and settings.

### Upgrade notes

- Restart ComfyUI and hard-refresh the browser after updating.
- Reopen the bundled example workflows; saved personal workflows are not
  rewritten automatically.
- The non-finite latents of the fp16 diffusion model are a ComfyUI/MiniMax issue
  that this release detects early and explains. `TROUBLESHOOTING.md` lists the
  measured `--bf16-unet` / `--fp32-unet` experiments.

### Validation

- Full test suite: **866 tests, OK** (1 skipped: `mutagen` is not installed in
  the development environment).
- `scripts/validate_release.py`: **Release validation OK**, privacy scan clean.
- `scripts/dump_node_contracts.py --check`: contract snapshot up to date.
- `python -m compileall -q .`: clean.
- `scripts/package_release.py --dry-run`: 34 registered nodes, 850 files,
  privacy scan CLEAN.

### Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.5.2.zip`
- `MiniMax_Music3_Production_Toolkit_v2.5.2.json`
- `MiniMax_Music3_Production_Toolkit_AudioEnhance_v2.5.2.json`
- `SHA256SUMS.txt`

---

## v2.5.1

Release date: 2026-09-13

### Summary

2.5.1 makes the language-model stage a first-class choice. The LLM node now runs
either the bundled GGUF inside ComfyUI, a model served by a local app, or a cloud
service — selected in the node, with the same outputs as before. A new switch
turns FLUX.2 cover generation off completely (rendering, saving and preflight
downloads), and the example workflow's layout, node ownership and release gates
were brought back in line with the documentation.

Everything in 2.5.0 still applies: the redesigned workflows, the mastering
section with auto-EQ, parametric EQ, compressor and true-peak limiter, and the
Audio Enhancement Lab.

### Added

- **LLM backend selection.** The `MiniMaxLLMChat` node offers three modes:
  `In ComfyUI (GGUF)` (unchanged default), `Local app / server`, and
  `Cloud service`. The node shows only the controls the selected mode needs.
- **Local app / server presets:** LM Studio (`127.0.0.1:1234`), Ollama
  (`11434`), llama.cpp (`8080`), Unsloth Studio (`8888`), vLLM (`8000`), and any
  other OpenAI-compatible server.
- **Cloud service presets:** OpenAI (Responses API), Claude (Anthropic), Gemini
  (Google), DeepSeek, Qwen (Alibaba Cloud), MiniMax, OpenRouter and Groq, plus
  any other OpenAI-compatible cloud endpoint. Each provider has its documented
  credential environment variable (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`, `MINIMAX_API_KEY`,
  `OPENROUTER_API_KEY`, `GROQ_API_KEY`).
- **Model discovery and a setup dialog.** Available models can be listed from the
  selected endpoint, or entered by hand. The connection setup (backend, provider,
  address, model, key) is reachable from the node.
- **Session-only API keys.** A key entered in the browser is held in memory for
  the session and is never written into the workflow or to disk.
- **FLUX.2 cover switch (`MiniMaxCoverControl`).** One boolean, enabled by
  default, wired to both `SaveImageSmartPrefix.enabled` and
  `MiniMaxModelAutodownload.flux2_models`. Switched off, no cover is rendered or
  saved, the FLUX preflight download is skipped, and the audio export continues
  with an empty artwork path. Previously written JPGs are not deleted.
- **Documentation and tests.** New `docs/LLM_PROVIDERS.md` setup guide (local apps,
  cloud, keys, output length, optional cover, troubleshooting), updated node
  pages for the three LLM nodes and the cover switch, plus provider, transport,
  UI and cover regression tests including two frontend suites.

### Changed

- **LLM execution uses ComfyUI's cache invalidation.** An enabled run generates
  fresh text instead of replaying the previous completion.
- **The session helper is gone.** `MiniMaxLLMSessionId` was removed from the
  example workflow and the LLM node no longer takes a session input; stored
  workflows with those wires migrate on load without disturbing other links.
- **The production workflow got a visual pass.** The LLM node is titled
  `LLM · In ComfyUI / Local app / Cloud`, its panel and the prompt-report panel
  are taller so the new controls fit without scrolling, and node positions and
  group sizes were tidied. The saved view opens on the mastering chain and the
  artwork lane, where the cover switch and the master controls live.
- **The workflow's generic LLM preflight is off.** The integrated LLM downloads
  its selected GGUF on demand; external providers manage their own models.
- The production workflow grew from 48 to 50 nodes (cover switch, preview nodes).

### Fixed

- **The cover-switch documentation matches the shipped layout.** The switch
  lives in `05 · ILLUSTRATE / Cover artwork` with the cover nodes it controls —
  its `cover_enabled` output feeds the image saver and the FLUX.2 preflight
  download next to it. The node page, the README, `docs/WORKFLOW_OPTIMIZED.md` and
  `docs/LLM_PROVIDERS.md` now all describe that placement, and the layout test pins
  it together with both connections.
- **`PreviewImage` and `PreviewAudio` are registered** as ComfyUI-core node types
  in the node-ownership test, so the preview nodes in the example workflow are
  covered instead of reported as unknown owners.
- **The FFmpeg pipe timeout test no longer races the process start.** It used
  0.2 s of audio with a 1 ms deadline, so FFmpeg occasionally finished in time
  and the expected timeout never occurred — a flaky test that could fail a
  release build at random. The workload is now long enough that the deadline is
  always reached while FFmpeg is still working.

### Breaking changes

None. Node identifiers, input and output names, return orders and the GGUF
defaults are unchanged. Existing workflows load as before; the removed session
wires migrate automatically.

### Upgrade notes

- Open the updated bundled workflow to get the cover switch and the new LLM
  menus. An update never inserts nodes into personal workflows — search for
  **FLUX.2 Cover** to add the switch to your own, and connect `cover_enabled` to
  `SaveImageSmartPrefix.enabled` and `MiniMaxModelAutodownload.flux2_models`.
- For cloud or local-app use, set the provider's environment variable (or type
  the key into the node for the current session). Unattended and API runs should
  use the environment variable.
- Keep the cover saver active even when the switch is off; some ComfyUI versions
  validate missing model dropdowns before execution. See `docs/LLM_PROVIDERS.md`.

### Validation

- Full test suite: **837 tests, OK** (1 skipped: `mutagen` is not installed in
  the development environment).
- `scripts/validate_release.py`: **Release validation OK**, privacy scan clean.
- `scripts/dump_node_contracts.py --check`: contract snapshot up to date.
- Both example workflows re-validated: graph integrity, group containment, no
  overlapping nodes, canonical node ownership.

### Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.5.1.zip`
- `MiniMax_Music3_Production_Toolkit_v2.5.1.json`
- `SHA256SUMS.txt`

---

## v2.5.0

Release 2.5 brings a clearer workflow, more efficient everyday operation and a
complete mastering section to music generation and existing-audio enhancement.

### Highlights

- Redesigned, numbered working areas make both workflows easier to navigate.
- Auto-EQ is on by default, with a gentle Warm tilt preset (35%, maximum 2 dB).
- A separate manual 8-band EQ stays editable with Auto-EQ on or off.
- Stereo-linked compression, LUFS targeting and true-peak limiting finish the
  release signal. Compression can be disabled independently of the limiter.
- Final output defaults to 44.1 kHz; 48 kHz is selectable before mastering.
- Improvements throughout memory/resource handling, audio processing, downloads,
  prompts, metadata and file output support a wider range of computers.

### Updating

Update the toolkit and dependencies in the ComfyUI environment, restart ComfyUI
and refresh the browser. Open the bundled production or AudioEnhance JSON again.
The redesigned examples now have the original filenames; the temporary optimized
copies and the older example contents are retired. Keep personal workflows under
separate filenames. Existing saved workflows are not silently replaced.

The production release chain now uses dynamic mastering in place of static gain;
the resulting audio can differ. Auto-EQ can be switched off. Manual EQ starts
neutral. Check the master at matched loudness; target loudness may remain below
the requested value when peak/gain-reduction limits take priority.

Mastering runs on CPU. Generation models still require adequate memory; the
bundled large LLM settings should be reduced for smaller machines. This release
does not promise that every model fits every GPU.

### Distribution

The release package contains the toolkit and both canonical workflows. Standalone
versioned workflow JSON files and SHA-256 checksums accompany the ZIP. Model
weights are not included. See INSTALLATION.md for dependencies and model setup.

Prepared locally for tag `v2.5.0`. Building these assets does not publish a GitHub
release or submit the package to Comfy Registry.

### Local validation

The Python suite completed 809 tests with no failures and one skipped test
(optional metadata dependency unavailable in the validation interpreter).
The EQ coefficient parity, prompt UI, workflow migration and headless EQ browser
tests passed. Release structure/version/privacy validation passed as well.
This does not constitute a fresh full-model GPU generation or listening test;
the workflows were previously tested interactively by the maintainer.

---

## v2.1.1

Release date: 2026-09-09

### Summary

The **branding and README refresh**. This patch adds the project icon and banner to the Comfy Registry metadata and the README, and brings the README description up to date with the current prompt counts (239 user templates, 11 system-prompt variants). No runtime behavior changed. The main feature work shipped in v2.1.0 (see [v2.1.0](#v210)) — the structured system prompt, the reworked `MiniMaxOutputPaths` layout and the eleven bundled system-prompt variants.

### Added

- **Branding assets**: `assets/branding/icon.png` (400×400) and `assets/branding/banner.png` (1680×720), referenced from `pyproject.toml` as `[tool.comfy] Icon` / `Banner` (raw GitHub URLs on `main`).
- **README banner**: the banner is now shown at the very top of `README.md` (centered, full-width).

### Changed

- **README refreshed**: the production system-prompt bullet now mentions the **11 bundled focus variants**, and the bundled genre prompt library bullet states the exact **239 templates** (was the rounded "230+"). The rest of the description was kept current with the released feature set.

### Fixed

- None.

### Breaking changes

- None.

### Upgrade notes

- None beyond a normal restart + browser hard-refresh (`Ctrl+F5`). If v2.1.0 was not published separately, this v2.1.1 release is the one to publish and includes all v2.1.0 changes as well.

### Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.1.1.zip`
- `MiniMax_Music3_Production_Toolkit_v2.1.1.json`
- `SHA256SUMS.txt`

---

## v2.1.0

Release date: 2026-09-09

### Summary

The **structured system-prompt and output-layout release**. The Structured Song Prompt is now clearly split into a **User Prompt** and a **System Prompt** section with visible headings, a file-backed system-prompt selector that copies the chosen prompt into an editable field, and dedicated save/refresh buttons. The bundled system-prompt library grew from one production prompt to **eleven focus variants** (brevity, lyrics, instrumentation, fantasy, genre fidelity, cinematic, dance energy, emotional storytelling, minimalism and fast tempo), each built on the full production contract. `MiniMaxOutputPaths` now uses clearer, self-describing folder names (`org-32flac/`, `highres-44flac/`, `highres-44mp3/`, `log/`), and its dead variant-suffix inputs were removed.

### Added

- **System Prompt section in `MiniMaxStructuredPromptV20`**: `system_prompt_source` (default `bundled_library`), `system_prompt_directory`, `system_prompt_file` (default `minimax-music3-production.txt`) and the editable `system_prompt` field now sit in their own visually separated section below the user-prompt fields. Selecting a system-prompt file copies its text into `system_prompt`, which is authoritative from then on (exactly like `description_override` for user prompts), so a selection can still be tweaked by hand.
- **Section headings**: `USER PROMPT` and `SYSTEM PROMPT` render as plain, transparent section headers (styled via an injected CSS rule) instead of dark input/button boxes.
- **New buttons**: `Save as custom user prompt` (after the description), `Save as custom system prompt` (below the system prompt) and `Refresh prompt lists` (bottom, refreshes both user and system libraries).
- **New backend routes**: `/minimax_music_toolkit/prompt_text` (returns a prompt file's raw text so the frontend can copy it into `system_prompt`) and `/minimax_music_toolkit/save_system_prompt` (saves the current system prompt into the library's `_custom/` folder), plus `save_custom_system_prompt` in `prompt_library.py`.
- **Eleven bundled system-prompt variants** in `prompts/system/`, each a complete production prompt (all ten default sections) plus a `## 0. PRIORITY FOCUS` section: `concise`, `lyrics-first`, `instrumental-first`, `fantasy`, `genre-faithful`, `cinematic`, `dance-energy`, `emotional-story`, `minimal-sparse`, and `fast-tempo` (high-BPM, to counter MiniMax playing fast requests too slowly). The dropdown discovers them automatically.
- **`user_prompt_file` default**: the Structured Song Prompt now starts with `electronic/synth-pop-vocal.txt` instead of the placeholder.

### Changed

- **`MiniMaxOutputPaths` defaults**: `original_subdir` → `org-32flac/`, `sr_flac_subdir` → `highres-44flac/`, `sr_mp3_subdir` → `highres-44mp3/`, `configuration_subdir` → `log/`. The example workflow, tooltips and documentation now reflect these names.
- **Removed `append_variant_index` and `variant_padding`** from `MiniMaxOutputPaths`: the suffix had no visible effect because the downstream audio/artwork/JSON savers rebuild the basename from `Album - Title` via `filename_mode`. The connected `run_index`/`variant_count` inputs remain for compatibility.
- **`MiniMaxStructuredPromptV20` field order**: `system_prompt` now appears after `source_name_override`, and `source_name_override` moved from optional to required so it can sit before the system prompt.
- **System prompt selection semantics**: the `system_prompt` field is authoritative in every mode (the frontend copies the selected file into it); headless/API runs without the prefill fall back to loading the selected file directly. `IS_CHANGED` now includes the `system_prompt` text.
- The system-prompt `custom` free-mode entry was removed from the system dropdown (it is only meaningful for user prompts).

### Fixed

- **Pre-2.1.0 saved workflows load with shifted system-prompt fields**: because `system_prompt` moved after `source_name_override`, older serializations had those fields one slot off. The load-time migration in `web/workflow_migration.js` / `web/migration_utils.js` now repairs by widget name for named serializations and reconstructs both historical positional orders; the stored serialization is rebuilt in the current order. The earlier `meter` repair is folded into the same name-based path.
- The contradictory "Caption maximum ~120 words" guidance (conflicting with the `[Caption]` quality target) was removed from every system prompt.

### Breaking changes

- None for execution. Saved workflows are repaired on load (see Fixed). The `MiniMaxOutputPaths` inputs `append_variant_index` and `variant_padding` no longer exist, so very old workflows carrying those two widget values are migrated by dropping the trailing values; the node ignores them at runtime.

### Upgrade notes

- Restart ComfyUI after updating and hard-refresh the browser (`Ctrl+F5`) so the new headings, buttons, system-prompt selector and repaired widget order load.
- Opening a workflow saved before 2.1.0 repairs the Structured Song Prompt widget values automatically (a console line logs the repair).
- Press `Refresh prompt lists` after adding or editing prompt files, and after updating to see the new bundled system-prompt variants.

### Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.1.0.zip`
- `MiniMax_Music3_Production_Toolkit_v2.1.0.json`
- `SHA256SUMS.txt`

---

## v2.0.5

Release date: 2026-09-06

### Summary

The **time signature and world-library release**. The Structured Song Prompt gains a dedicated **Time signature** field (curated list from `4/4 (common time)` through odd meters and `free time / rubato`, with `custom` first like every other field), and the bundled prompt library grows from 95 to **239 world-spanning templates** across 31 categories. Every template now carries the canonical **Meter** metadata, and the free description text was cleaned everywhere so it never repeats anything a structured field can select. The curated combo vocabulary was overhauled to match the expanded library: the genre list now spans the full world map, the voice list covers character, mood, ensemble and special vocal types, the language list adds ~50 more languages plus regional variants, and the key list is reordered along the circle of fifths starting with the minor keys.

### Added

- **Time signature (`meter`) field** in `MiniMaxStructuredPromptV20`, positioned between tempo and key like the canonical field order. The combo offers a curated list (`4/4 (common time)`, `3/4 (waltz)`, `6/8`, `2/4 (march / polka)`, `12/8 (shuffle / slow blues)`, `2/2 (cut time)`, `6/4`, `5/4`, `7/8`, `7/4`, `9/8`, `5/8`, `11/8`, `changing time signatures`, `free time / rubato`) with `custom` first. The assembled LLM prompt gets a `Time signature:` line; `IS_CHANGED`, the provenance summary and the frontend prefill/refresh all include the new field.
- **Front-matter aliases for the new category**: `Meter`, `Taktart`, `Time signature`, `Time_signature` and `Signature` are recognized and normalized to the canonical `meter` field (alongside the existing German aliases `Tonart`, `Sprache`, `Stimme`).
- **Expanded prompt library**: 239 templates (was 95) across 31 categories. New categories: `blues`, `cinematic`, `country`, `disco`, `gospel`, `kids`, `meditation`, `musical`, `punk`, `seasonal`, `soul`, `world`. The existing categories gained dozens of subgenres — UK drill, phonk, cloud rap, old-school hip-hop, dubstep, hardstyle, big room, eurodance, future bass, goa/uplifting/progressive trance, acid/french/disco house, Berlin school, vaporwave, chiptune, IDM, EBM, electro swing, bebop, cool jazz, dixieland, swing, gypsy jazz, vocal jazz, baroque, sacred choir, string quartet, minimalism, symphonic orchestra, death/black/folk/nu metal, metalcore, djent, britpop, new wave, shoegaze, garage rock, psychedelic rock, surf rock, rockabilly, post-rock, stoner rock, merengue, son cubano, norteño, rocksteady, ska, enka, mandopop, gqom, soukous, mbalax, and many more. Every template carries the canonical metadata block including **Meter**, and the free text never repeats anything a field can select.
- **Overhauled curated combo vocabulary**: the genre list now covers the full world map (including African, Asian, Latin American and European traditional styles plus functional music); the voice list adds character/age/mood variants, ensembles, gospel/mixed choirs, rap flows, operatic/baritone/falsetto types, screamed/growled vocals, vocoder and spoken word; the language list adds ~50 more languages (from Afrikaans to Quechua, including regional German variants and `Multilingual / mixed` and `Invented / gibberish language` special cases). All curated values are verified against the bundled library by tests.
- **Consistency tests for the new category**: `tests/test_prompt_consistency.py` now enforces the canonical field order including `meter`, that every Meter value is a curated time signature, and that no description mentions a numeric time signature (the no-field-duplication rule extended to meter).

### Changed

- The key combo now follows the circle of fifths **starting with the minor keys** (`A minor … D minor`, then `C major … F major`); the node documentation and the bundled example workflow were updated to match.
- Both public example workflows carry `workflow_version: 2.0.5`; the production workflow's Structured Song Prompt node includes the new `meter` widget (default `custom`, so existing behavior is unchanged).
- Two new ambient templates gained the missing Meter metadata (`free time / rubato`), and every description that still repeated a selectable value (lyrics mode, voice gender, duration, time signature) was cleaned across the library.
- `docs/PROMPT_LIBRARY.md`, the node documentation and the UI help texts describe the new field and the expanded library.

### Fixed

- **Pre-2.0.5 saved workflows load with shifted widget values** in `MiniMaxStructuredPromptV20`: because ComfyUI applies the serialized positional `widgets_values` slot by slot, inserting the new `meter` widget between tempo and key made every field from meter onwards show the next field's old value (meter=key, key=lyrics, … , description=system_prompt). A load-time migration repair (`web/workflow_migration.js` + `web/migration_utils.js`, unit-tested in `tests/test_workflow_migration.mjs`) now detects the old serialization shape on graph load and re-aligns all widget values: named values are re-applied by name and `meter` defaults to `custom`; positional-only files get `custom` inserted at the meter slot. The repair runs before the structured-prompt extension's description prefill, so selecting a prompt file still fills the description correctly.
- The prompt library's free-text descriptions no longer repeat values covered by the structured fields (lyrics mode such as "sparse"/"instrumental", voice gender, durations, time signatures) — the consistency tests now pass over all 239 templates.
- `scripts/upgrade_workflow_to_v2.py` and the documentation examples were brought in line with the new canonical field order (the migration script itself was not re-run; the example workflow is user-owned).

### Breaking changes

- None. The new `meter` widget defaults to `custom`, so saved workflows and headless/API runs behave exactly as before. Prompt files that were merely renamed in v2.0.3 remain consolidated as documented in `docs/PROMPT_LIBRARY.md`.

### Upgrade notes

- Restart ComfyUI after updating and hard-refresh the browser (`Ctrl+F5`) so the new Time signature combo, the expanded option lists and the meter-migration repair load.
- Opening a workflow saved before 2.0.5 repairs its Structured Song Prompt widget values automatically (a console line logs the repair).
- Selecting an older saved workflow that references a prompt file by name keeps working; if you want the new Meter prefills, select the file again (or press `Refresh prompt lists`).

### Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.5.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.5.json`
- `SHA256SUMS.txt`

---

## v2.0.4

Release date: 2026-09-05

### Summary

The "fields that feel right" release. The Structured Song Prompt gets a **curated tempo range list** (Slow 40-70 through Very fast 175-200 BPM, `custom` first), the key list now follows the **circle of fifths**, the lyrics choices gain **"only voice - no words"** (wordless vocalization), and the language list offers the important languages first and then **25 more languages alphabetically**. The log shows a single **ASCII progress bar** for the LLM chat and FlashSR stages instead of one line per step, and the **MiniMax prompt is now saved as an `.md` file** in the JSON folder with the same `Album - Title` basename as everything else. The prompt library was unified, consolidated and expanded to **95 world-spanning templates** with a grouped dropdown, and all pre-2.0.0 release notes were merged into one file.

### Added

- **Curated tempo range list**: the `tempo` combo now offers sensible BPM ranges (`Slow (40-70 BPM)`, `Laid-back (70-100 BPM)`, `Midtempo (100-120 BPM)`, `Dancefloor (120-130 BPM)`, `Uptempo (130-145 BPM)`, `Fast (145-175 BPM)`, `Very fast (175-200 BPM)`) with `custom` as the first entry like every other field — a selection always leaves the LLM a comfortable musical window instead of a single fixed value. All 24 prompt files with Tempo metadata were converted to the matching range, and the consistency tests enforce that Tempo values stay curated ranges.
- **"only voice - no words" lyrics mode**: the lyrics choices are now `yes`, `sparse`, `only voice - no words`, `instrumental`. Front-matter values like `wordless`, `vocalise`, `vocalese`, `scat`, `humming` and `no words` are normalized to the new choice.
- **Circle-of-fifths key list**: the key combo is ordered `C major … F major` then `A minor … D minor`, so related keys sit next to each other.
- **More languages**: after the existing important languages, 25 additional languages (Arabic, Bengali, Bulgarian, Czech, Danish, Dutch, Finnish, Greek, Hebrew, Hungarian, Indonesian, Malay, Norwegian, Persian, Polish, Romanian, Serbian, Swahili, Swedish, Tagalog, Thai, Turkish, Ukrainian, Urdu, Vietnamese) follow in alphabetical order.
- **MiniMax prompt report as Markdown file**: `MiniMaxSaveProductionJSON` gained the optional `minimax_prompt_md` input. When wired to the `MiniMaxPromptReport` node, the report is written next to the canonical JSON as `Album - Title.md` (same basename, atomic write) and recorded in the JSON's `outputs.prompt_report`. The bundled example workflow is wired accordingly (link 259).
- **Audio Enhancement Lab workflow**: a second public example workflow (`example_workflows/MiniMax_Music3_Production_Toolkit_AudioEnhance.json`, 15 nodes / 16 links) that skips the production stage — it enhances an already-finished song (LoadAudio → declip → PRE lowpass → FlashSR → hybrid crossover → HF repair → POST lowpass → release prep → tagged FLAC save) so you can experiment with the enhancement settings without generating a new song. Generic by design (no pre-selected audio file); validated by `validate_release.py` and new tests, and included in the release ZIP.
- **Log progress bars**: `progress_utils.format_progress_bar()` renders a single ASCII bar spanning 0 (left) to the maximum (right), e.g. `[##########----------]  8192/16384`. `MiniMaxLLMChat` logs it roughly every 10% of `max_tokens` (final 100% included) instead of a line per 64 tokens; `MiniMaxFlashSRAudio` logs it every 10% of the chunks instead of one line per chunk. The in-node blue progress bars are unchanged.
- **Unified, consolidated, world-spanning prompt library**: all 95 bundled user prompts follow one format — a canonical metadata block (Genre / Tempo / Key / Lyrics / Language / Voice / Theme / Length) plus a description that never repeats what a field can express. Near-duplicates were merged (EDM dance anthem, minimal electronic German vocals, absurd German novelty, chillout guitar) and heavy metal moved from `rock/` to `metal/`. New categories cover Africa (Afrobeats, Amapiano, Ethio-Jazz, Highlife, Desert Blues), Asia (K-Pop, J-Pop / City Pop, Anime, Chinese & Indian traditional, Bollywood), Latin America (Bossa Nova, Samba, Salsa, Cumbia, Tango, Reggaeton, Bachata) and Europe (Flamenco, Fado, Chanson, Schlager, Klezmer, Balkan Folk), plus Reggae/Dub/Dancehall, Hip-Hop/Trap/R&B and missing modern genres (Punk, Indie, Power Metal, Psytrance, Jungle, Synth-Pop, Opera). The curated Genre and Language lists were extended to match (including Hindi).
- **Grouped prompt dropdown**: both prompt-file dropdowns list the categories alphabetically as directory labels first, with each directory's files indented beneath them; directory labels are display-only.
- **Consistency tests**: `tests/test_prompt_consistency.py` guards the unified format, canonical field order, canonical lyrics values, the no-field-duplication rule and the alphabetical directory grouping; `tests/test_progress_utils.py` covers the log progress bar; workflow-migration tests cover the tempo conversion.

### Changed

- The log heartbeat for LLM streaming and FlashSR chunking was replaced by the ASCII progress bar described above.
- All pre-2.0.0 release notes were merged into a single `RELEASE_NOTES_v1.0.x.md`; the six per-version v1.0.x note files were removed.
- The bundled example workflow carries the user's audio-preset edits (PRE lowpass `PRE 10 kHz - strong`, FlashSR hybrid `FlashSR only`, HF repair `Cymbal clarity`) and the new `minimax_prompt_md` wiring.

### Fixed

- The smoke-test workflow converter (`scripts/comfyui_smoke_test.py`) now reads widget values from `widgets_values_named`; the positional list interleaves seed `control_after_generate` values and previously broke API validation (`main_gpu`, `tempo`).

### Breaking changes

- Eight bundled prompt files were consolidated into their successors (merged, renamed or moved); saved workflows that referenced one of them should select the successor file (see `docs/PROMPT_LIBRARY.md`). The node reports a clear error for a missing file instead of failing silently.

### Upgrade notes

- Restart ComfyUI after updating and hard-refresh the browser (`Ctrl+F5`) to load the new tempo range list, the new dropdown grouping and the migration repairs.

### Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.4.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.4.json`
- `SHA256SUMS.txt`

---

## v2.0.3

Release date: 2026-09-05

### Summary

A "full freedom" release for the prompt stage: the prompt-file dropdown of the **Structured Song Prompt** node now starts with a **`custom`** choice that loads no file and leaves every field exactly as you set it, so you can compose a prompt entirely by hand. The bundled example workflow also ships refined audio-enhancement presets, and the README was rewritten as a welcoming, non-technical introduction to the project.

### Added

- **`custom` free mode in the Structured Song Prompt**: the `user_prompt_file` dropdown now offers `custom` as the first real choice. Selecting it loads no prompt file, prefills nothing and clears nothing — the Genre / Tempo / Key / Lyrics / Language / Voice / Theme / Length fields and the further-description area are used exactly as you filled them in. In the backend this is equivalent to manual mode, so no file named `custom` is ever resolved.

### Changed

- **Refined audio presets in the example workflow**: the PRE low-pass preset moved from `PRE 12 kHz - recommended` to `PRE 10 kHz - strong`, the FlashSR hybrid crossover now uses the `FlashSR only` mode, and the HF Cymbal / Shimmer Repair stage switched from `Gentle` to `Cymbal clarity` (start frequency 7000 Hz, sustain reduction 2.25 dB, static HF trim -0.5 dB).
- **README rewritten in English**: a concise, appealing overview for newcomers that leads with the "fill a few fields, get a finished track" experience and explains at the end how the pipeline and the new custom mode actually work.

### Fixed

- None — this is an additive, backward-compatible release.

### Breaking changes

- None. Existing workflows keep working; `custom` only adds a choice to the prompt-file dropdown.

### Upgrade notes

- Restart ComfyUI after updating and hard-refresh the browser (`Ctrl+F5`) so the prompt-file dropdown gains the `custom` entry.
- The bundled example workflow keeps its previous prompt selection; open the **Structured Song Prompt** node and choose `custom` to try the free mode.

### Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.3.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.3.json`
- `SHA256SUMS.txt`

---

## v2.0.2

Release date: 2026-09-04

### Summary

Usability and transparency release: the workflow now shows **exactly which prompt MiniMax Music 3 received** (readable Markdown report right in the node), long-running stages got **ComfyUI progress bars** (FlashSR chunks, and token-streaming progress for the LLM chat), and the GitHub Pages demo page was rebuilt as a compact, play-first single-column player with 10 new tracks (35 total).

### Added

- **`MiniMaxPromptReport` node** ("MiniMax Prompt Report (Markdown)"): shows the cleaned musical caption, the normalized lyrics, the character-exact final prompt sent to the MiniMax tokenizer (verbatim, including token markers) and — clearly separated — the FLUX.2 image prompt. The report is rendered as **formatted Markdown inside the node** (ComfyUI's built-in text-preview widget, Markdown mode by default, with a Plain-text toggle) and remains available as a STRING output. Wired into the example workflow's Save Audio section.
- **Progress bars in the integrated LLM chat**: generation now runs as a token stream (when the installed llama-cpp-python supports `stream`) — the node's progress bar advances per generated token (reasoning included) up to `max_tokens`, a log heartbeat appears every 64 tokens, and start/finish lines make the stage observable. Non-streaming backends fall back to the previous behaviour.
- **Progress bar in `MiniMaxFlashSRAudio`**: the blue ComfyUI progress bar now advances per 5.12 s chunk, with a per-10 % log update.
- **10 new demo tracks** on the GitHub Pages demo page (hard rock, industrial metal, symphonic metal, and four multilingual tracks — Italian, Korean, Japanese) with covers, mixed into a curated showcase order.

### Changed

- **Demo page rebuilt**: tracks are listed in a single column (no more side-by-side grid); the SoundCloud player is the first thing on every card; cover images are small thumbnails; descriptions are clipped and full generation details stay behind "Generation details". Search/filter/sort and the stats header are unchanged.
- Demo catalog count raised to 35; placeholder tags of the new batch were replaced with real album names (Unbreakable, System Override, Symphonic Metal, Night Maps).
- `progress_utils.py` provides the ComfyUI progress bar with a silent no-op fallback outside ComfyUI, so unit tests keep running everywhere.

### Fixed

- **CI for this repository is green again**: the six audio modules import `torch` tolerantly (only present inside ComfyUI), and `numpy` is now an explicit dependency in `requirements.txt`/`pyproject.toml`; the CI workflow installs the requirements before running the tests.
- Example-workflow link serialization for the new node is complete on both sides (`outputs[].links` and `inputs[].link`), so no workflow-validation warnings appear on load.

### Breaking changes

- None. Existing workflows keep working; the new report node is additive and optional.

### Upgrade notes

- Restart ComfyUI after updating and hard-refresh the browser (Ctrl+F5) to load the new node and its Markdown-preview extension.
- The bundled example workflow now contains the `MiniMaxPromptReport` node; older saved workflows simply don't have it.

### Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.2.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.2.json`
- `SHA256SUMS.txt`

---

## v2.0.1

Release date: 2026-09-03

### Summary

Bugfix release that makes the workflow runnable **repeatedly** in the same
ComfyUI session. The integrated LLM chat node now releases *all* GPU memory
held by the previous run (including ComfyUI's dynamic-VRAM staging, cast
buffers and CUDA-graph workspaces, plus the FlashSR cache) before loading the
LLM, so a second run no longer overflows the GPU and hangs in the LLM load or
fails later in the MiniMax node with `cudaErrorStreamCaptureInvalidated`.
Single-GPU machines are fully supported again; on multi-GPU machines the LLM
is optionally auto-routed to the GPU with the most free VRAM.

### Added

- Automatic LLM GPU routing: with two or more visible GPUs and the default
  settings (`main_gpu=0`, `split_mode=none`, no `tensor_split`), the LLM is
  routed to the non-default GPU with the most free VRAM; ComfyUI models stay
  on their usual device. Explicit `main_gpu`/split settings always win.
- Diagnostic logging around the LLM load: resident models before cleanup,
  aimdo VRAM usage and free VRAM per GPU after cleanup, and – if anything is
  still resident – the owner of every remaining dynamic-VRAM staging block
  (VBAR), which is then force-released.

### Changed

- `MiniMaxLLMUnload` returns GPU memory to the allocator pools more
  aggressively after closing the model (`gc.collect()`,
  `torch.cuda.empty_cache()`, `soft_empty_cache`), so the music stage gets
  unfragmented VRAM.
- The LLM load error message now names `n_ctx`, `n_gpu_layers` and `main_gpu`
  and suggests concrete remedies when a load fails.
- One-time log hint explains single-GPU operation and mentions the optional
  `--cuda-device all` launch flag for machines with a second GPU.

### Fixed

- **Repeated runs hang in the integrated LLM chat / overflow VRAM.** The
  models of the previous run (dynamic-VRAM staging pages, cast buffers,
  CUDA-graph/prefetch workspaces, cached FlashSR runners) were not released
  before the LLM loaded; on a single GPU the GGUF load then spilled into
  system memory (seemingly endless load) and left the CUDA context broken so
  MiniMax later failed during CUDA graph capture
  (`cudaErrorStreamCaptureInvalidated`). The node now frees all of these
  explicitly before every LLM load; models re-stage on demand afterwards.
- FlashSR model cache is released before the LLM load as well, not only by
  the unload node.

### Breaking changes

- None. No node inputs, outputs or workflow changes; the example workflow is
  unchanged.

### Upgrade notes

- Existing workflows keep working; no workflow reload required.
- Restart ComfyUI after updating so the Python changes are loaded.
- If you run on a machine with two GPUs and want the LLM on the second card,
  start ComfyUI with `--cuda-device all` (on Windows ComfyUI otherwise hides
  the extra GPUs); the LLM is then routed automatically.

### Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.1.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.1.json`
- `SHA256SUMS.txt`

---

## v2.0.0

**Major release: self-contained workflow, structured prompt control, model auto-download.**

This release removes the example workflow's dependency on external custom nodes, gives the prompt stage structured control over Genre / Tempo / Key / Lyrics / Language / Voice / Theme / Length, and downloads missing models automatically on first use. The never-published v1.0.7 documentation/demo preparation is included.

### Highlights

- **Integrated FlashSR** — `MiniMaxFlashSRAudio` replaces the external Egregora node with identical processing behavior (48 kHz, 5.12 s chunks, 0.50 s overlap, Hann overlap-add). The inference code is **bundled** in `flashsr_inference/` (no code downloads into the models directory, no external-node dependency); only the three weights are downloaded on first use.
- **Integrated LLM** — `MiniMaxLLMChat` (llama-cpp-python, GGUF from `models/llm`, optional session state per `session_id`) and `MiniMaxLLMUnload` replace the external ComfyUI-LLM-Session nodes. Empty/failed LLM generation raises a clear error instead of leaking empty text into the parser.
- **Structured prompt control** — `MiniMaxStructuredPromptV20` with dedicated fields for Genre, Tempo, Key, Lyrics (yes/sparse/instrumental), Language, Voice, Lyrics theme and Target length plus a further-description area. Prompt files can carry an optional metadata block that prefills the fields when the file is selected; every field can be overridden, `custom` leaves the part out. Selecting a prompt copies the file's body text into `description_override`, which is authoritative from then on. All combo lists ship with a curated vocabulary merged with the library's values. All 62 bundled prompt files ship with metadata.
- **Robust LLM output parsing** — a decorated `[Count]` value (e.g. `1 +8? Let's number:`) extracts the first integer instead of failing the run, values outside 1-100 are clamped with a warning, and a `[Count]` without any number is ignored. The LLM chat node's `status` output is wired into the parser, so an empty or failed LLM generation is reported as such instead of looking like a prompt-format error.
- **Simpler example workflow** — the shared `FlashSR / Lowpass Settings` node and the `Reproducible Song Metadata` node are gone: PRE/POST low-pass values live directly on the low-pass nodes, and `metadata_json` is an optional input of the production-JSON writer. Both node classes stay registered so old saved workflows keep loading, and pre-2.0.0 workflows are migrated by input name.
- **Complete generation record** — the canonical production JSON (schema v7) now contains everything relevant for generation: the LLM system/user prompt, the raw LLM output and status, the structured-prompt summary, the parsed Caption/Lyrics/Title/Image_Prompt with provenance and seeds, the MiniMax generation settings and all audio-enhancement reports plus the written files. The optional `MiniMaxMetadataLoader` was removed from the example workflow; it reads the same schema in a future separate restore workflow.
- **Normalized prompt library** — every description follows the new structure: durations and BPM values live only in the metadata block, missing Length entries were added, and `scripts/normalize_prompt_descriptions.py` keeps the library consistent.
- **Consistent logging** — the LLM chat node logs the full assistant output while llama.cpp stays quiet (`verbose=False`); FlashSR import noise and per-chunk progress bars are suppressed in favor of one toolkit log line per chunk.
- **Cover-prompt fix** — LLMs sometimes leak planning/self-check text behind an early `[Image_Prompt]` header, which polluted the FLUX cover prompt and produced covers full of text. The parser now restarts a section on every repeated top-level header (the last occurrence wins), the system prompt forbids any output outside the four sections, and the parser appends the standard `No text, no letters, ...` prohibition whenever the image prompt lacks it - restoring the clean v1.0.7-style cover prompts.
- **Full LM Studio-style LLM node** — `MiniMaxLLMChat` exposes temperature, top_k, top_p, min_p, repeat/presence/frequency penalty, seed, chat-format selection (auto verified for Qwen3.8 and Gemma 4), a thinking toggle (reasoning split off, logged, recorded in `llm.thinking`) and multi-GPU controls (split_mode layer/row, tensor_split `even`, main_gpu, tensor_parallel when available).
- **Save as custom prompt** — a button on the structured prompt node saves the current values + description into the library's `_custom/` folder; `custom` fields now always mean "no specification".
- **Documented workflow** — six MarkdownNote nodes explain every section plus a Models & Folders note with the required model files and their directory structure.
- **Song length capped at 5 minutes** — the Length combo offers shorter options (`30 seconds` … `4-5 minutes`), bundled prompts with longer metadata were corrected, and the system prompt enforces 5:00 as the hard maximum.
- **Artwork size presets** — `1536x1536`, `2048x2048`, `3072x3072` and `3096x3096` are selectable (FLUX.2 quantizes to multiples of 16; 3096 renders as 3088, so 3072 is recommended for exact sizes).
- **Model auto-download** — declarative `models_config.json` plus the `MiniMaxModelAutodownload` node. Files with a configured URL are fetched automatically; gated MiniMax / FLUX.2 weights without a public URL are reported with guidance.
- **LLM section can be switched off without errors** — set `LLM Chat → enabled=false` and fill the parser's manual fallback fields, or simply bypass the LLM nodes; the parser's LLM input is optional now.
- **Workflow schema migration** — pre-2.0.0 workflows using the parser's old input order are repaired by input name (Python helper + frontend hook).

### Migration notes

- Workflows saved with v1.x load unchanged; the parser-node link slots are migrated automatically.
- The old external nodes (`LLMSessionChatNode`, `UnloadLLMModelNode`, `EgregoraAudioUpscaler`) are no longer used by the bundled workflow. They still work if you keep the external packages installed, but the integrated replacements are recommended.
- Install `llama-cpp-python` in the ComfyUI Python environment for the integrated LLM node (`python -m pip install llama-cpp-python`).
- Provide a GGUF in `models/llm` (or configure a download URL in `models_config.json`).

### What stayed the same

- All audio processing defaults (declip, PRE/POST low-pass, hybrid crossover, HF shimmer repair, static LUFS/true-peak release prep) are unchanged.
- The `Album - Title` naming contract across FLAC/MP3/JPG/JSON, the centralized production JSON and the metadata schema remain unchanged.
- Legacy node class IDs (`MiniMaxLLMTemplateV16`, `MiniMaxParseExternalLLMOutputV16`, …) remain backwards-compatible.

### Validation

`python scripts/validate_release.py`, the full unit suite (154 tests), Python compile checks and JS syntax checks pass for this tree. The bundled workflow references only toolkit and ComfyUI core nodes, and every toolkit node's serialized input order is pinned against its `INPUT_TYPES`.

### Maintainer tooling

- `scripts/toolkit_diagnostics.py` — self-diagnostics report: Python, FFmpeg, required packages, the LLM stack, `models_config.json` targets and the prompt library.
- `scripts/preview_output_paths.py` — non-writing preview of the exact five output paths (32flac/44flac/44mp3/cover/JPG/JSON) a run would produce, including `auto_increment` collision resolution.
- `scripts/bump_version.py` — updates VERSION, `pyproject.toml`, `project_info.py`, `CITATION.cff` and the example workflow metadata together and creates a release-notes skeleton.
- `scripts/package_release.py --dry-run` — release contents summary (nodes, prompts, demo tracks, workflow stats, privacy scan) without creating assets.
- Windows filename hardening: reserved device names (`CON`, `NUL`, `COM1`, …) are neutralized, trailing dots/spaces stripped and over-long titles truncated; covered by dedicated edge tests.

### Files

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.0.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.0.json`
- `SHA256SUMS.txt`
