# MiniMax Music Production Toolkit 1.0.0

Initial public release.

## Highlights

- Prompt-library/template node with manual, bundled-library and external-directory sources for both user and system prompts.
- Bundled MiniMax Music 3 production system prompt and 38 sanitized genre prompt examples.
- Structured Caption / Lyrics / Title / Image Prompt parsing for an external ComfyUI LLM.
- Reproducible MiniMax settings, metadata JSON, standard release tags and Album - Title filenames.
- Audio declipping, FlashSR pre/post filtering, hybrid original/FlashSR crossover and HF cymbal/shimmer repair.
- High-quality release sample-rate conversion plus static full-program LUFS / true-peak targeting without gain riding.
- FLUX.2 cover workflow helpers and configurable embedded-cover resolution.
- Complete tooltips, node help pages, release validation, tests and GitHub/Comfy Registry publishing workflows.

See `INSTALLATION.md` before loading the full example workflow because FlashSR, the local LLM stage and model files are external dependencies.
