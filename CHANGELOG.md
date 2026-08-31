# Changelog

All notable changes to this project will be documented here. The project follows Semantic Versioning.

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
