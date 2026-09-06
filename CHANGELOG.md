# Changelog

All notable changes to this project will be documented here. The project follows Semantic Versioning.

## [2.0.5] - 2026-09-06

The time-signature and world-library release: a dedicated Time signature field in the Structured Song Prompt, the prompt library expanded from 95 to 239 world-spanning templates with Meter metadata everywhere, and a fully overhauled curated combo vocabulary.

### Added
- **Time signature (`meter`) field** in `MiniMaxStructuredPromptV20` between tempo and key: curated list (`4/4 (common time)`, `3/4 (waltz)`, `6/8`, odd meters, `changing time signatures`, `free time / rubato`) with `custom` first. The assembled prompt gets a `Time signature:` line; `IS_CHANGED`, the provenance summary, the frontend prefill and the option lists all include it. Front-matter aliases: `Meter`, `Taktart`, `Time signature`, `Signature`.
- **Prompt library expanded to 239 templates across 31 categories**: new `blues`, `cinematic`, `country`, `disco`, `gospel`, `kids`, `meditation`, `musical`, `punk`, `seasonal`, `soul`, `world` categories plus dozens of new subgenres in the existing ones (drill, phonk, cloud rap, dubstep, hardstyle, big room, eurodance, future bass, goa trance, acid/french/disco house, Berlin school, vaporwave, chiptune, IDM, EBM, electro swing, bebop, cool jazz, dixieland, swing, gypsy jazz, baroque, sacred choir, string quartet, minimalism, death/black/folk/nu metal, metalcore, djent, britpop, new wave, shoegaze, garage rock, psychedelic/surf/stoney/post rock, merengue, son cubano, norteño, rocksteady, ska, enka, mandopop, gqom, soukous, …). Every template carries the canonical metadata block including Meter.
- **Overhauled curated vocabulary**: genre list spans the full world map; voice list adds character/age/mood variants, ensembles, choirs, rap flows, operatic/baritone/falsetto, screamed/growled vocals, vocoder and spoken word; language list adds ~50 languages plus regional variants and special cases; key list reordered to circle of fifths starting with the minor keys.
- **Consistency tests for meter**: canonical field order including `meter`, curated time-signature values, and the no-duplication rule extended to numeric time signatures in descriptions.

### Changed
- Key combo order: minor keys first (`A minor … D minor`, then `C major … F major`).
- Both example workflows carry `workflow_version: 2.0.5`; the production workflow's Structured Song Prompt includes the new `meter` widget (default `custom`).
- All prompt descriptions cleaned so the free text never repeats a selectable field value; two new ambient templates gained their missing Meter metadata.

### Fixed
- **Pre-2.0.5 workflow load shift**: inserting `meter` between tempo and key shifted every following widget value on load (ComfyUI applies the positional `widgets_values` slot by slot). A load-time migration repair in `web/workflow_migration.js` / `web/migration_utils.js` (unit-tested) now re-aligns pre-2.0.5 serializations: named values are re-applied by name with `meter` = `custom`, positional-only files get `custom` inserted at the meter slot, and the stored serialization is kept in the new shape.
- Prompt-library consistency tests now pass over all 239 templates (field duplication in descriptions removed).

## [2.0.4] - 2026-09-05

The "fields that feel right" release: a curated tempo range list, circle-of-fifths keys, a wordless-vocal lyrics mode, more languages, log progress bars, the MiniMax prompt as an `.md` file, and the unified world-spanning prompt library.

### Added
- **Curated tempo range list** in `MiniMaxStructuredPromptV20`: `custom` first, then sensible BPM ranges (Slow 40-70 / Laid-back 70-100 / Midtempo 100-120 / Dancefloor 120-130 / Uptempo 130-145 / Fast 145-175 / Very fast 175-200 BPM). All 24 prompt files with Tempo metadata use the matching range; consistency tests enforce range-only Tempo values.
- **`only voice - no words` lyrics mode** (yes / sparse / only voice - no words / instrumental) with normalization for `wordless`, `vocalise`, `vocalese`, `scat`, `humming`, `no words`.
- **Circle-of-fifths key list** (C major … F major, then A minor … D minor).
- **More languages**: important languages first, then 25 additional languages in alphabetical order (Arabic … Vietnamese, incl. Hindi in the important set).
- **MiniMax prompt report as Markdown file**: `MiniMaxSaveProductionJSON` gained the optional `minimax_prompt_md` input; wired to `MiniMaxPromptReport` it writes `Album - Title.md` next to the canonical JSON (same basename, atomic) and records it in `outputs.prompt_report`. Bundled workflow wired (link 259).
- **Audio Enhancement Lab workflow**: a second public example workflow (`MiniMax_Music3_Production_Toolkit_AudioEnhance.json`) that skips the production stage — LoadAudio → declip → FlashSR chain → release prep → tagged FLAC save — for experimenting with enhancement settings on finished songs. Generic (no pre-selected audio file), validated and shipped in the release ZIP.
- **Log progress bars**: single ASCII bar (`[##########----------]  8192/16384`, 0 left / max right) in the log for LLM streaming (~every 10% of max_tokens) and FlashSR (every 10% of chunks); replaces the per-64-token heartbeat and per-chunk lines. In-node progress bars unchanged.
- **Unified, consolidated, world-spanning prompt library**: 95 templates, one canonical format, no field duplication in the free text; near-duplicates merged; heavy metal moved to `metal/`; new `african/`, `asian/`, `european/`, `latin/`, `reggae/`, `hiphop/` categories plus modern genres (Punk, Indie, Power Metal, Psytrance, Jungle, Trap, Synth-Pop, R&B, Dub, Dancehall, Opera); curated Genre/Language lists extended.
- **Grouped prompt dropdown**: directory labels first (alphabetical), files indented beneath; labels are display-only.
- New consistency tests (`test_prompt_consistency.py`), progress-bar tests (`test_progress_utils.py`) and tempo-migration tests.

### Changed
- Log heartbeat for LLM streaming / FlashSR chunking replaced by the ASCII progress bar.
- All pre-2.0.0 release notes merged into `RELEASE_NOTES_v1.0.x.md`; the six per-version v1.0.x note files were removed.
- Bundled example workflow carries the user's audio-preset edits and the new `minimax_prompt_md` wiring.

### Fixed
- The smoke-test workflow converter (`scripts/comfyui_smoke_test.py`) now reads widget values from `widgets_values_named`; the positional list interleaves seed `control_after_generate` values and previously broke API validation (`main_gpu`, `tempo`).

## [2.0.3] - 2026-09-05

Full-freedom prompt release: a `custom` choice in the Structured Song Prompt's file dropdown, refined audio presets in the example workflow, and a rewritten, welcoming README.

### Added
- **`custom` free mode in `MiniMaxStructuredPromptV20`**: the `user_prompt_file` dropdown now starts with `custom`, which loads no prompt file and leaves every structured field exactly as the user set it (equivalent to manual mode in the backend; no file named `custom` is ever resolved).

### Changed
- Example workflow audio presets: PRE low-pass `PRE 10 kHz - strong`, FlashSR hybrid `FlashSR only`, HF Cymbal / Shimmer `Cymbal clarity` (7000 Hz start, 2.25 dB sustain reduction, -0.5 dB static HF trim).
- README rewritten in English as an attractive, non-technical introduction that explains the few-fields-in / finished-track-out experience and the new custom mode.

### Fixed
- None (additive, backward-compatible release).

## [2.0.2] - 2026-09-04

Usability and transparency release: exact MiniMax prompt report in the workflow, progress bars for FlashSR and LLM chat, and a rebuilt play-first demo page with 10 new tracks.

### Added
- **`MiniMaxPromptReport`** node: Markdown report of exactly what MiniMax Music 3 received (cleaned caption, normalized lyrics, verbatim final prompt) plus the FLUX.2 image prompt, rendered as formatted Markdown in the node; wired into the example workflow's Save Audio section.
- Progress bar for `MiniMaxFlashSRAudio` (per-chunk) and token-streaming progress for `MiniMaxLLMChat` (per-token progress bar + log heartbeat every 64 tokens, with non-streaming fallback).
- 10 new demo tracks (35 total) with covers and SoundCloud links on the GitHub Pages demo page.

### Changed
- Demo page rebuilt: single-column play-first list, small cover thumbnails, details behind "Generation details"; placeholder tags of the new batch replaced by album names (Unbreakable, System Override, Symphonic Metal, Night Maps).

### Fixed
- CI green: torch imports in the six audio modules are now tolerant (torch lives only in ComfyUI), numpy is an explicit dependency, and the CI installs the requirements before testing.
- Complete link serialization for the new node (no workflow-validation warnings on load).

## [2.0.1] - 2026-09-03

Bugfix release: the workflow can now be run repeatedly in the same ComfyUI session without VRAM exhaustion.

### Added
- Automatic LLM GPU routing on multi-GPU machines: with default settings the LLM goes to the non-default GPU with the most free VRAM; explicit `main_gpu`/split settings always win.
- Diagnostic logging around the LLM load: resident models before cleanup, aimdo VRAM usage and free VRAM per GPU after cleanup, and the owner of any remaining dynamic-VRAM staging block (which is then force-released).

### Changed
- `MiniMaxLLMUnload` returns GPU memory to the allocator pools more aggressively after closing the model (`gc.collect()`, `torch.cuda.empty_cache()`, `soft_empty_cache`).
- Clearer LLM load error message naming `n_ctx`, `n_gpu_layers`, `main_gpu` with concrete remedies.

### Fixed
- **Repeated runs hung in the integrated LLM chat and overflowed the GPU.** The previous run's dynamic-VRAM staging pages, cast buffers, CUDA-graph/prefetch workspaces and cached FlashSR runners were not released before the LLM loaded; the GGUF load then spilled into system memory and left the CUDA context broken (later MiniMax failure: `cudaErrorStreamCaptureInvalidated`). The node now frees all of these explicitly before every LLM load; models re-stage on demand. Single-GPU machines are fully supported again.

## [2.0.0] - 2026-09-02

This major release makes the example workflow self-contained, gives the prompt stage structured control, and adds first-run model auto-download. The never-published v1.0.7 documentation/demo preparation is included in this release.

### Added
- **Integrated FlashSR node** `MiniMaxFlashSRAudio` (display: *Audio Super Resolution (FlashSR, integrated)*): replaces the external `ComfyUI-Egregora-Audio-Super-Resolution` node with an identical processing behavior (48 kHz, 5.12 s chunks, 0.50 s overlap, Hann overlap-add). Missing FlashSR code/weights are auto-downloaded on first use.
- **Integrated LLM nodes** `MiniMaxLLMChat` and `MiniMaxLLMUnload`: self-contained llama-cpp-python chat (GGUF from `models/llm`, optional per-session state) replaces the external `ComfyUI-LLM-Session` nodes. No GPL code is used; failures raise clear errors instead of empty text.
- **Structured prompt control** `MiniMaxStructuredPromptV20`: dedicated Genre / Tempo / Key / Lyrics (yes/sparse/instrumental) / Language / Voice / Lyrics theme / Target length fields plus a further-description area. Prompt library files can carry an optional metadata block that prefills the fields on selection; every field can be overridden and `custom` leaves the part out of the LLM prompt. All 62 bundled prompt files are annotated.
- **Model auto-download** `MiniMaxModelAutodownload` plus declarative `models_config.json`: needed model files are checked on first use, downloaded when a URL is configured (with progress logging), and the run continues. Gated MiniMax / FLUX.2 weights without a public URL are reported with guidance.
- **LLM section can be switched off without errors**: the parser's LLM input is now optional with manual caption/lyrics/title/image-prompt fallbacks, and `LLM Chat → enabled=false` skips model loading entirely.
- **Workflow schema migration** (`workflow_schema.py` + frontend hook `web/workflow_migration.js`): pre-2.0.0 workflows that wired the parser's old input order are repaired by input name.
- Add `scripts/annotate_prompt_metadata.py` to (re-)generate prompt front-matter metadata from file paths and prompt content.
- Add `scripts/upgrade_workflow_to_v2.py` documenting the v1→v2 example workflow transformation.
- Add `DEVELOPMENT.md` with public contributor/maintainer rules for node compatibility, serialized workflow safety, validation and releases.
- Add `scripts/update_demo_catalog.py` to safely extract public GitHub Pages demo metadata from production JSON while preserving existing SoundCloud URLs.
- Add demo-catalog regression tests and release validation for unique track IDs/orders, cover availability and SoundCloud URL shape.
- Local-only `KONTEXT.md` hand-off context is excluded from Git, the Comfy Registry and release ZIPs by validator-guarded rules.

### Changed
- The bundled example workflow uses only toolkit and ComfyUI-core nodes (external LLM Session / Egregora nodes removed).
- **FlashSR inference code is now bundled** in `flashsr_inference/` (vendored from FlashSR_Inference + TorchJaekwon, with attribution in `flashsr_inference/NOTICE.md`). No code is downloaded into the models directory anymore; only the three FlashSR weights are fetched on first use. `models_config.json` no longer contains code-download entries (config version 2).
- **Example workflow simplified**: the shared `FlashSRProcessingSettings` node and the `MiniMaxSongMetadata` node were removed. The PRE/POST low-pass values live directly on the two low-pass nodes, and `metadata_json` became an optional input of `MiniMaxSaveProductionJSON` (old saved workflows are repaired by name via `workflow_schema.migrate_workflow` and the frontend migration hook).
- **Complete generation record in the production JSON** (schema `minimax_music3_production_metadata_v7`, auto-migrated from v6): the canonical JSON now contains the LLM system/user prompt, the raw LLM output and status, the structured-prompt summary, the parsed Caption/Lyrics/Title/Image_Prompt with provenance and seeds, the MiniMax generation settings and every audio-enhancement report (declip, PRE/POST low-pass, FlashSR, hybrid crossover, HF repair, release prep) plus the written files - enough to recreate a song from the JSON alone.
- **Prompt library fully normalized**: every description follows the new structure; song lengths and BPM values no longer appear in the free text (they live in the metadata block), the missing `Length` entries were added, and `scripts/normalize_prompt_descriptions.py` keeps the library consistent (idempotent).
- **Consistent logging**: the integrated LLM node logs model load, environment and the full assistant output while llama.cpp runs with `verbose=False`; FlashSR's vendored import noise and per-chunk tqdm bars are suppressed in favor of the toolkit's own log lines.
- **Cover-prompt fix**: leaked LLM planning text no longer pollutes the FLUX cover prompt - the parser restarts a section on every repeated top-level header (last occurrence wins), the system prompt forbids any output outside the four sections, and the parser appends the standard text-free prohibition whenever the image prompt lacks it.
- **Full LM Studio-style LLM node**: `MiniMaxLLMChat` now exposes temperature, top_k, top_p, min_p, repeat/presence/frequency penalty, seed, a chat-format selector (auto = verified per model family: chatml for Qwen-style, embedded template for Gemma), a thinking toggle (reasoning is split off, logged and recorded separately in `llm.thinking`) and multi-GPU controls (split_mode layer/row, tensor_split including `even`, main_gpu, tensor_parallel when the backend supports it). Verified end-to-end with Qwen3.8-27B and Gemma 4; parameter passing is gated by API introspection so older llama-cpp-python versions keep working.
- **Save as custom prompt**: a button on `MiniMaxStructuredPromptV20` stores the current field values + description into the prompt library's `_custom/` folder (name prompt included); manual mode saves into the bundled library and switches to it. `custom` fields now always mean "no specification" - they no longer fall back to the file's metadata.
- **Workflow documentation**: six MarkdownNote nodes explain every section (Prompt & LLM, FLUX.2, MiniMax, Audio Enhancement, Save & Release) plus a Models & Folders note with the required model files and their directory structure.
- **`MiniMaxMetadataLoader` removed from the example workflow** (it belongs in a future separate song-restore workflow; the node class stays registered and reads the same schema).
- **Song length limited to 5 minutes**: the Length combo offers shorter options (`30 seconds` up to `4-5 minutes`), two prompt files with longer metadata were corrected, and the bundled system prompt now caps every request at 5:00 (the MiniMax generation settings already used `max_duration` 300 s).
- **Artwork size presets** now include `1536x1536`, `2048x2048`, `3072x3072` and `3096x3096` (the FLUX.2 latent stage quantizes to multiples of 16, so 3096 renders as 3088 - prefer 3072).
- `MiniMaxParseExternalLLMOutputV16` now accepts an optional LLM output plus manual fallback fields and an `llm_status` input (wired to the LLM chat node's status output); provenance records whether LLM or manual values were used. A decorated `[Count]` value no longer fails the run - the first integer is extracted, clamped to 1-100 and warned about instead.
- Selecting a prompt file in `MiniMaxStructuredPromptV20` copies the file's body text into `description_override`, which is authoritative from then on; editing it invalidates the cache even in file mode. Combo option lists ship with a curated vocabulary merged with library values.
- Windows filename hardening: reserved device names (`CON`, `NUL`, `COM1`, …) are neutralized, trailing dots/spaces stripped and over-long titles truncated.
- Expand the GitHub Pages demo catalog from 17 to 25 tracks and include the eight new supplied cover images.
- Improve display labels for prompt-slug-based new demo collections/genres.
- Make `scripts/prepare_demo_covers.py` derive its expected cover list dynamically from `docs/demo-tracks.js`.
- Refresh README, audio examples, troubleshooting, development and publishing documentation.
- Remove transient `Refresh prompt lists` UI state from the bundled example workflow metadata.

### Maintainer tooling
- `scripts/toolkit_diagnostics.py` — self-diagnostics report (Python, FFmpeg, packages, LLM stack, model targets, prompt library).
- `scripts/preview_output_paths.py` — non-writing preview of the five output paths a run would produce, including collision resolution.
- `scripts/bump_version.py` — version bump across VERSION / `pyproject.toml` / `project_info.py` / `CITATION.cff` / example workflow metadata, with a release-notes skeleton.
- `scripts/package_release.py --dry-run` — release contents summary without creating assets.
- New regression suites: node schema snapshot for every toolkit node in the bundled workflow, Windows filename edge tests, LLM failure-propagation tests, release-tooling tests (129 unit tests total).
- LLM environment facts (llama-cpp-python version, GGUF inventory, model directories) are logged once per run for failure diagnostics.

### Maintainer notes
- Runtime node behavior of the audio chain (declip, low-pass, hybrid crossover, HF repair, release prep) remains unchanged; only the FlashSR/LLM node wrappers were replaced, with identical processing parameters.
- New demo entries may keep an empty `soundcloudUrl` until their SoundCloud uploads are published.
- v1.0.7 was never published; its prepared changes are released as part of 2.0.0.

## [1.0.6] - 2026-09-01

### Fixed
- Fixed the serialized `Save Image Smart Prefix` input-slot order in the bundled workflow. The v1.0.5 workflow could map widget values to the wrong inputs after `title` and `audio_tags_json` were added, producing validation errors for `collision_mode` and `jpeg_quality`.
- Added release validation and unit coverage for the artwork saver input order and widget types so this class of workflow-serialization regression is caught before packaging.
- Hardened `scripts/build_public_workflow.py` to normalize artwork-saver slots and repair linked target-slot indices automatically.

### Included
- Preserves the expanded bundled prompt library supplied for this release (62 user prompt files across additional rock, metal, EDM, house, electronic and alternative styles).
- Preserves the SoundCloud demo-page configuration and demo links already present in the repository.

## [1.0.5] - 2026-09-01

### Fixed
- Make generated cover JPGs use the same `Album - Title` basename as original FLAC, release FLAC, release MP3 and the canonical production JSON.
- Prevent prompt-library source names such as `nordic-folk-vocal` from leaking into the final artwork filename when `album - title` naming is selected.

### Changed
- Add `title`, `audio_tags_json` and `filename_mode` inputs to `Save Image Smart Prefix`.
- Share one filename-building helper across audio, artwork and centralized JSON output to keep cross-format names consistent.
- Keep the bundled, user-tested local-LLM example values at `max_tokens = 16384` and `n_ctx = 32768`.
- Ship the prepared SoundCloud demo playlist/track URLs in the GitHub Pages configuration.
- Refresh artwork, workflow, installation, demo and publishing documentation.

## [1.0.4] - 2026-09-01

### Added
- Add a dedicated `configuration_subdir` output path (default `json/`).
- Add `Save Production JSON`, which writes one canonical per-song JSON after the original audio, release FLAC, release MP3, and cover artwork have been saved.
- Add machine-readable `save_info_json` output to `Save Audio Smart Prefix` so the final JSON records actual file paths, sample rate, format, save peak/gain, filename mode, and embedded-cover size.
- Add a GitHub Pages SoundCloud demo template under `docs/` with editable track URL placeholders.

### Changed
- Set the example local LLM `max_tokens` to 14000.
- Stop writing duplicated JSON sidecars beside each audio output in the v1.0.4 example workflow; legacy sidecar support remains available for backward compatibility.
- Rewrite and expand README, installation, workflow, audio-pipeline, artwork, audio-example, troubleshooting, and node documentation.

## [1.0.3] - 2026-09-01

### Changed
- Refresh the public example workflow layout using the user-tested ComfyUI arrangement.
- Simplify visible node titles and remove two redundant explanatory note nodes for a cleaner canvas.
- Keep the optional saved-configuration loader bypassed in the example workflow.
- Preserve all MiniMax Music 3, FlashSR, restoration, release-prep, artwork, metadata, and output processing values.
- Keep the repaired MiniMax Music 3 subgraph boundary links introduced in 1.0.1.
- Remove the transient serialized `Refresh prompt lists` button state; the frontend extension recreates the button at runtime.

## [1.0.1] - 2026-08-31

### Fixed
- Preserve MiniMax Music 3 subgraph boundary links while sanitizing the public example workflow.
- Fix ComfyUI `No link found in parent graph ... unet_name` and equivalent missing subgraph-input/output link errors.
- Extend release validation and unit tests to verify subgraph boundary links, child-node links, and parent/definition input alignment.
- Make public-workflow version metadata follow `VERSION` automatically.

## [1.0.0] - 2026-08-31

### Added
- Public release of **MiniMax Music Production Toolkit**.
- File-backed user/system prompt libraries with bundled examples and external-directory support.
- Dynamic prompt-file dropdowns and refresh control in ComfyUI.
- Cache fingerprinting for file-backed prompts so edits are detected without renaming files.
- Structured external-LLM parser for Caption, Lyrics, Title and Image Prompt.
- LLM session-ID/cache-buster helper without extra utility-node dependencies.
- MiniMax generation settings, output paths, standard audio tags and reproducibility JSON.
- Source declipping, FlashSR pre/post filtering, hybrid original/FlashSR crossover, HF shimmer/cymbal repair.
- High-quality 44.1/48 kHz release SRC plus static full-program LUFS/true-peak targeting.
- FLAC/MP3/WAV saving, Album - Title filename mode and configurable embedded cover size.
- FLUX.2 square-cover helpers and smart JPEG saving.
- Input tooltips for every toolkit node and built-in ComfyUI node help pages.
- Sanitized example workflow and bundled genre prompt library.
- CI validation and Comfy Registry publishing workflow.
