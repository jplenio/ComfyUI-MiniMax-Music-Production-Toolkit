# MiniMax Music Production Toolkit for ComfyUI

Production-focused ComfyUI custom nodes plus a complete example workflow for **MiniMax Music 3**. The toolkit combines LLM-assisted prompt preparation, reproducible generation settings, audio repair, FlashSR-assisted bandwidth extension, release preparation, album-cover generation, metadata/tagging and organized output handling.

Author: [Johannes Plenio](https://github.com/jplenio)

> Independent community project. No MiniMax, FLUX, LLM or FlashSR model weights are included.

## 🎧 Listen to Demo Tracks

Hear music generated entirely with this ComfyUI workflow:

👉 [Open the MiniMax Music Production Toolkit Demo Gallery](https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/)

## What the toolkit does

- **LLM Prompt Library / Template** — use manual prompts, bundled prompt files or external prompt directories for both user prompts and system prompts.
- **Structured LLM parsing** — extracts `[Caption]`, `[Lyrics]`, `[Title]` and `[Image_Prompt]` from an external LLM response.
- **Production system prompt** — optimized for MiniMax Music 3, including long instrumental structure, imaginative lyrics and avoidance of smear-prone metallic/high-frequency textures.
- **Bundled genre prompt library** — reusable examples covering house, EDM, electronic, ambient, jazz, folk, classical, funk, pop and more.
- **Reproducible generation controls** — consistent MiniMax text/sampler seeds and generation settings.
- **Audio Declip / Overload Repair** — conservative reconstruction of short hard-clipped flat tops before further enhancement.
- **FlashSR processing tools** — pre/post filtering, hybrid original/FlashSR crossover and controlled reconstructed high-frequency blending.
- **HF Cymbal / Shimmer Repair** — reduces watery or smeared upper-frequency sustain while preserving attacks.
- **Static LUFS / True-Peak Release Prep** — high-quality resampling plus constant full-program gain; no AGC, compressor or time-varying loudness riding.
- **Release file handling** — FLAC/MP3/WAV, `[Album] - [Title]` naming, standard tags and configurable embedded-cover resolution.
- **Centralized production JSON** — one canonical JSON per song is written into a configurable directory (default `json`) after all audio and artwork outputs are saved.
- **FLUX.2 cover branch** — square artwork generation and JPEG saving; cover size also controls the embedded artwork size.
- **Complete UI help** — every toolkit input has a tooltip and every toolkit node has Markdown help inside `web/docs/`.

## v1.0.6 highlights

- Fixes the bundled workflow validation error in **Save Cover JPG – same song name** caused by a serialized input-slot order mismatch (`collision_mode` / `jpeg_quality`).
- Adds a packaging guard so artwork-saver input order and widget types are validated before release.
- Includes the expanded **62-file user prompt library** and the existing SoundCloud-powered demo gallery.
- Keeps unified release naming: audio, artwork and centralized JSON use the same `Album - Title` basename in the bundled workflow.

## v1.0.5 highlights

1. **Artwork filename parity:** cover JPGs now use the exact same `Album - Title` basename as the FLAC, MP3 and canonical JSON outputs.
2. `Save Image Smart Prefix` now accepts the generated title and standard audio-tag JSON and uses the same shared filename rules as the audio/JSON savers.
3. The bundled example workflow keeps the tested local-LLM settings `max_tokens = 16384` and `n_ctx = 32768`.
4. The GitHub Pages demo configuration includes the prepared SoundCloud playlist/track URLs and remains easy to extend with more demos later.
5. Documentation and validation tests were updated to verify matching artwork naming.

## Example production chain

```text
User prompt / prompt library
        ↓
External local LLM
(max_tokens = 16384, n_ctx = 32768 in example)
        ↓
Caption / Lyrics / Title / Image Prompt
        ↓
MiniMax Music 3
        ↓
Source Declip Repair
        ├──────────────────→ clean original branch ─┐
        ↓                                           │
PRE low-pass → FlashSR ─────────────────────────────┤
                                                    ↓
                                           Hybrid crossover
                                                    ↓
                                        HF shimmer repair
                                                    ↓
                                            POST low-pass
                                                    ↓
                                   Static LUFS / TP + HQ SRC
                                                    ↓
                            Release FLAC + Release MP3

FLUX.2 cover branch ────────────────────────────────→ JPG cover

Original FLAC + Release FLAC + Release MP3 + Cover
                         ↓
                Save Production JSON
                         ↓
                  json/Album - Title.json
```

The original MiniMax source is archived separately from the processed release files.

## Output structure

The example workflow defaults to a structure like:

```text
ComfyUI/output/
└── audio/minimax3/2026-09-01/Example Album/
    ├── 32flac/
    │   └── Example Album - Song Title.flac
    ├── 44flac/
    │   └── Example Album - Song Title.flac
    ├── 44mp3/
    │   └── Example Album - Song Title.mp3
    ├── artwork/
    │   └── Example Album - Song Title.jpg
    └── json/
        └── Example Album - Song Title.json
```

`json/` is configurable in **MiniMax Output Paths → configuration_subdir**.

The canonical JSON contains prompts, seeds, MiniMax settings, restoration settings, release-prep data, standard audio tags and the final saved artifact paths.

## Installation

See [INSTALLATION.md](INSTALLATION.md) for the complete dependency/model list.

Quick manual install:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit.git
cd ComfyUI-MiniMax-Music-Production-Toolkit
python -m pip install -r requirements.txt
```

Use the Python interpreter that belongs to your ComfyUI installation. Restart ComfyUI afterward and hard-refresh the browser once (`Ctrl+F5`).

## Prompt library

Bundled prompts live under:

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

For user and system prompts independently choose:

- `manual`
- `bundled_library`
- `external_directory`

See [PROMPT_LIBRARY.md](PROMPT_LIBRARY.md).

## Example workflow

Load:

`example_workflows/MiniMax_Music3_Production_Toolkit.json`

The public workflow contains generic metadata and no machine-specific paths. It is intended as a complete reference workflow; individual toolkit nodes can also be used independently.

## Audio demos / SoundCloud

A curated **17-track** GitHub Pages demo is included. It is driven by the supplied production metadata and supports cover art, SoundCloud playback, search/filtering, musical summaries and expandable generation details.

- Listening page source: `docs/index.html`
- Track/SoundCloud configuration: `docs/demo-tracks.js`
- Cover images: `docs/assets/demo-covers/`
- Setup instructions: [AUDIO_EXAMPLES.md](AUDIO_EXAMPLES.md)
- Intended public page: `https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/`

The current demo configuration already contains the prepared SoundCloud playlist/track URLs. For future additions, paste a normal public SoundCloud URL into the matching `soundcloudUrl` field in `docs/demo-tracks.js`; the page builds the embedded player automatically. Local cover JPGs can be copied directly or prepared with `scripts/prepare_demo_covers.py`. If no local JPG is present, the page can fall back to SoundCloud's visual player so the SoundCloud artwork remains visible.

## Documentation

- [Installation and dependencies](INSTALLATION.md)
- [Complete workflow guide](WORKFLOW.md)
- [Prompt library](PROMPT_LIBRARY.md)
- [Audio processing pipeline](AUDIO_PIPELINE.md)
- [Artwork workflow](ARTWORK_WORKFLOW.md)
- [Audio examples / SoundCloud](AUDIO_EXAMPLES.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Publishing / maintainer guide](PUBLISHING.md)
- [Changelog](CHANGELOG.md)

## Logging

Logging uses the namespace `minimax_music_toolkit`. Default level: `INFO`.

For detailed diagnostics set before starting ComfyUI:

```text
MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL=DEBUG
```

Prompt contents are not dumped at normal log levels.

## Limitations

- De-clipping can reconstruct plausible peak curvature but cannot recover information destroyed by clipping exactly.
- FlashSR can invent high-frequency content. Hybrid crossover and HF repair are safeguards, not guarantees.
- Static LUFS normalization preserves dynamics and may intentionally finish below a requested LUFS target when the true-peak ceiling prevents more gain.
- LLM output quality depends on the selected local model and its instruction-following ability.
- GitHub README pages cannot host a native SoundCloud iframe player reliably; the included GitHub Pages template is the intended embedded-player solution.

## License

MIT. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
