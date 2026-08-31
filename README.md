# MiniMax Music Production Toolkit for ComfyUI

Production-focused ComfyUI custom nodes and an example workflow for **MiniMax Music 3**. The toolkit covers prompt orchestration, reproducible generation settings, audio repair, FlashSR-assisted bandwidth extension, release preparation, cover artwork and metadata.

Author: [Johannes Plenio](https://github.com/jplenio)

> Independent community project. No third-party model weights are included.

## Highlights

- **LLM Prompt Library / Template** — use an editable prompt directly, bundled prompt files, or your own external prompt directory. User prompts and system prompts are independent libraries with dynamically refreshed file dropdowns.
- **Structured LLM parsing** — robustly extracts `[Caption]`, `[Lyrics]`, `[Title]`, `[Image_Prompt]` from an external LLM response.
- **Bundled production system prompt** — designed around MiniMax Music 3 structure, longer instrumental section maps, imaginative lyrics and artifact-resistant sound choices.
- **38 bundled user prompts** — EDM, house, electronic, ambient, jazz, folk, classical, funk, pop and comedy examples.
- **Reproducible generation metadata** — prompts, seeds, MiniMax settings, filters, restoration stages and release preparation can be written to JSON sidecars.
- **Audio Declip / Overload Repair** — conservative reconstruction of short hard-clipped flat tops before further processing.
- **FlashSR workflow tools** — pre/post filtering plus hybrid crossover that can preserve original transients while blending only controlled reconstructed high-frequency content.
- **HF Cymbal / Shimmer Repair** — reduces smeared high-frequency sustain while protecting attacks.
- **Static LUFS / True Peak Release Prep** — HQ sample-rate conversion and constant full-program gain. No automatic gain riding, compressor or dynamic `loudnorm` fallback.
- **Release file handling** — FLAC/MP3/WAV, standard tags, JSON sidecars, `[Album] - [Title]` filenames and configurable embedded-cover size.
- **Artwork helpers** — square image sizing and smart JPEG saving for a FLUX.2 cover branch.
- **Complete UI help** — every toolkit input has a tooltip and every registered node has an embedded Markdown help page.

## Example production chain

```text
External LLM
    ↓
Caption / Lyrics / Title / Image Prompt
    ↓
MiniMax Music 3 (source audio)
    ↓
Declip repair
    ├──────────────→ clean-resampled original ─┐
    ↓                                          │
PRE low-pass → FlashSR ────────────────────────┤
                                               ↓
                                  Hybrid crossover
                                               ↓
                                  HF shimmer repair
                                               ↓
                                      POST low-pass
                                               ↓
                              Static LUFS / TP + HQ SRC
                                               ↓
                                 Release FLAC + MP3
```

The untouched MiniMax source can also be archived separately.

## Installation

See [INSTALLATION.md](INSTALLATION.md). The toolkit itself is one custom-node package, but the **included full example workflow** additionally uses ComfyUI core MiniMax Music 3 / FLUX.2 nodes plus optional third-party FlashSR and local-LLM nodes.

Quick manual install:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit.git
cd ComfyUI-MiniMax-Music-Production-Toolkit
python -m pip install -r requirements.txt
```

Use the Python interpreter belonging to your ComfyUI installation. Then restart ComfyUI and hard-refresh the browser once.

## Prompt library

The repository ships with:

```text
prompts/
├── system/
│   └── minimax-music3-production.txt
└── user/
    ├── ambient/
    ├── classical/
    ├── comedy/
    ├── edm/
    ├── electronic/
    ├── folk/
    ├── funk/
    ├── house/
    ├── jazz/
    └── pop/
```

In **LLM Prompt Library / Template** choose independently for user and system prompts:

- `manual`
- `bundled_library`
- `external_directory`

For an external library, enter the directory path on the **machine running ComfyUI**. The file dropdown is populated from `.txt`, `.md` and `.prompt` files below that directory. Use **Refresh prompt lists** after adding/removing files. File contents are fingerprinted, so editing a selected file invalidates ComfyUI's cached template output without requiring a rename.

See [PROMPT_LIBRARY.md](PROMPT_LIBRARY.md).

## Example workflow

`example_workflows/MiniMax_Music3_Production_Toolkit.json` is sanitized and contains generic release metadata. ComfyUI can expose JSON files in `example_workflows/` through its Workflow Template browser.

The workflow is an example, not a requirement to use every toolkit node. You can use the prompt, metadata, repair, mastering and saver nodes independently.

## Documentation

- [Installation and dependencies](INSTALLATION.md)
- [Workflow guide](WORKFLOW.md)
- [Prompt library](PROMPT_LIBRARY.md)
- [Audio processing](AUDIO_PIPELINE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Publishing / maintainer guide](PUBLISHING.md)
- [Audio examples strategy](AUDIO_EXAMPLES.md)
- [Changelog](CHANGELOG.md)

## Logging

The package logs through Python logging under the namespace `minimax_music_toolkit`. Default level is `INFO`.

For detailed diagnostics:

```text
MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL=DEBUG
```

Set the environment variable before starting ComfyUI. Prompt contents are not dumped at normal log levels.

## Limitations

- De-clipping reconstructs plausible curvature; information destroyed by hard clipping cannot be recovered exactly.
- FlashSR/bandwidth extension can invent high-frequency content. The hybrid and HF-repair nodes are intended to reduce, not eliminate, model artifacts.
- LUFS normalization does not make a mix professionally mastered by itself. The supplied release-prep stage intentionally preserves dynamics rather than forcing every track to a target through compression.
- The example LLM stage depends on the quality and instruction-following ability of the GGUF model you choose.

## License

MIT. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
