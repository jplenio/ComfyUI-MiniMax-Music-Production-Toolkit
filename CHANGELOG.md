# Changelog

All notable changes to this project will be documented here. The project follows Semantic Versioning.

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
