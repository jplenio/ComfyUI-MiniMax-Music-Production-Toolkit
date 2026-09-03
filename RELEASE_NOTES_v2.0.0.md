# MiniMax Music Production Toolkit 2.0.0

**Major release: self-contained workflow, structured prompt control, model auto-download.**

This release removes the example workflow's dependency on external custom nodes, gives the prompt stage structured control over Genre / Tempo / Key / Lyrics / Language / Voice / Theme / Length, and downloads missing models automatically on first use. The never-published v1.0.7 documentation/demo preparation is included.

## Highlights

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

## Migration notes

- Workflows saved with v1.x load unchanged; the parser-node link slots are migrated automatically.
- The old external nodes (`LLMSessionChatNode`, `UnloadLLMModelNode`, `EgregoraAudioUpscaler`) are no longer used by the bundled workflow. They still work if you keep the external packages installed, but the integrated replacements are recommended.
- Install `llama-cpp-python` in the ComfyUI Python environment for the integrated LLM node (`python -m pip install llama-cpp-python`).
- Provide a GGUF in `models/llm` (or configure a download URL in `models_config.json`).

## What stayed the same

- All audio processing defaults (declip, PRE/POST low-pass, hybrid crossover, HF shimmer repair, static LUFS/true-peak release prep) are unchanged.
- The `Album - Title` naming contract across FLAC/MP3/JPG/JSON, the centralized production JSON and the metadata schema remain unchanged.
- Legacy node class IDs (`MiniMaxLLMTemplateV16`, `MiniMaxParseExternalLLMOutputV16`, …) remain backwards-compatible.

## Validation

`python scripts/validate_release.py`, the full unit suite (154 tests), Python compile checks and JS syntax checks pass for this tree. The bundled workflow references only toolkit and ComfyUI core nodes, and every toolkit node's serialized input order is pinned against its `INPUT_TYPES`.

## Maintainer tooling

- `scripts/toolkit_diagnostics.py` — self-diagnostics report: Python, FFmpeg, required packages, the LLM stack, `models_config.json` targets and the prompt library.
- `scripts/preview_output_paths.py` — non-writing preview of the exact five output paths (32flac/44flac/44mp3/cover/JPG/JSON) a run would produce, including `auto_increment` collision resolution.
- `scripts/bump_version.py` — updates VERSION, `pyproject.toml`, `project_info.py`, `CITATION.cff` and the example workflow metadata together and creates a release-notes skeleton.
- `scripts/package_release.py --dry-run` — release contents summary (nodes, prompts, demo tracks, workflow stats, privacy scan) without creating assets.
- Windows filename hardening: reserved device names (`CON`, `NUL`, `COM1`, …) are neutralized, trailing dots/spaces stripped and over-long titles truncated; covered by dedicated edge tests.

## Files

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.0.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.0.json`
- `SHA256SUMS.txt`
