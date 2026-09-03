# MiniMax Music Production Toolkit for ComfyUI

Production-focused ComfyUI custom nodes plus a complete example workflow for **MiniMax Music 3**. The toolkit combines structured LLM prompt preparation, reproducible generation settings, audio repair, integrated FlashSR bandwidth extension, release preparation, album-cover generation, metadata/tagging and organized output handling.

Author: [Johannes Plenio](https://github.com/jplenio)

> Independent community project. No MiniMax, FLUX, LLM or FlashSR model weights are included (they are downloaded or provided separately, see [Installation](INSTALLATION.md)).

## 🎧 Listen to Demo Tracks

Hear music generated entirely with this ComfyUI workflow:

👉 [Open the MiniMax Music Production Toolkit Demo Gallery](https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/)

## What the toolkit does

- **Structured Song Prompt control** — dedicated fields for Genre, Tempo, Key, Lyrics (yes/sparse/instrumental), Language, Voice, Lyrics theme and Target length plus a further-description area. Prompt files can prefill these fields via an optional metadata block; every field can be overridden and `custom` leaves the part out.
- **Integrated LLM Chat (llama.cpp)** — self-contained GGUF chat node with optional session state; no external LLM custom node required. The LLM section can be switched off (`enabled = false` + manual parser fallbacks) without workflow errors.
- **Structured LLM parsing** — extracts `[Caption]`, `[Lyrics]`, `[Title]` and `[Image_Prompt]` from the LLM response, with manual fallback fields for LLM-less runs.
- **Production system prompt** — optimized for MiniMax Music 3, including long instrumental structure, imaginative lyrics and avoidance of smear-prone metallic/high-frequency textures.
- **Bundled genre prompt library** — reusable examples covering house, EDM, electronic, ambient, jazz, folk, classical, funk, pop and more, all with structured metadata.
- **Reproducible generation controls** — consistent MiniMax text/sampler seeds and generation settings.
- **Integrated Audio Super Resolution (FlashSR)** — self-contained FlashSR node replacing the external Egregora node, with identical processing behavior. The inference code is bundled with the toolkit (`flashsr_inference/`); only the weights are auto-downloaded on first use.
- **Model auto-download / check** — declarative `models_config.json` plus a check node; needed files with a configured URL are downloaded with progress logging and the run continues.
- **Audio Declip / Overload Repair** — conservative reconstruction of short hard-clipped flat tops before further enhancement.
- **FlashSR processing tools** — pre/post filtering, hybrid original/FlashSR crossover and controlled reconstructed high-frequency blending.
- **HF Cymbal / Shimmer Repair** — reduces watery or smeared upper-frequency sustain while preserving attacks.
- **Static LUFS / True-Peak Release Prep** — high-quality resampling plus constant full-program gain; no AGC, compressor or time-varying loudness riding.
- **Release file handling** — FLAC/MP3/WAV, `[Album] - [Title]` naming, standard tags and configurable embedded-cover resolution.
- **Centralized production JSON** — one canonical JSON per song is written into a configurable directory (default `json`) after all audio and artwork outputs are saved.
- **FLUX.2 cover branch** — square artwork generation and JPEG saving; cover size also controls the embedded artwork size.
- **Complete UI help** — every toolkit input has a tooltip and every toolkit node has Markdown help inside `web/docs/`.

## v2.0.0 highlights

- **Self-contained workflow**: the integrated `MiniMaxFlashSRAudio`, `MiniMaxLLMChat` and `MiniMaxLLMUnload` nodes replace the external Egregora FlashSR and ComfyUI-LLM-Session nodes. The example workflow uses only toolkit and ComfyUI core nodes.
- **Structured prompt control**: `MiniMaxStructuredPromptV20` with metadata-prefilled fields and `custom` semantics; all 62 bundled prompt files carry metadata.
- **Model auto-download**: `models_config.json` + `MiniMaxModelAutodownload` download the FlashSR weights (and any URL-configured model) on first use with logging, then the run continues. The FlashSR inference code is bundled with the toolkit.
- **Switchable LLM section**: disable the LLM chat node and fill the parser's manual fallback fields — the rest of the workflow keeps running without errors.
- **Workflow schema migration**: pre-2.0.0 saved workflows are repaired by input name (`workflow_schema.py` + a frontend hook).
- The never-published v1.0.7 demo/documentation preparation is included (25-track demo catalog, development guide, demo-catalog maintenance script).

## v1.0.7 highlights (included in 2.0.0)

- Expands the GitHub Pages demo catalog to **25 tracks** while preserving existing SoundCloud URLs and cover artwork.
- Adds `scripts/update_demo_catalog.py` so production JSON can be converted into safe public demo metadata without copying the full system prompt, raw LLM response or machine-specific paths.
- Makes `scripts/prepare_demo_covers.py` read expected cover filenames dynamically from the demo catalog instead of a hard-coded list.
- Adds a public `DEVELOPMENT.md` with workflow-schema, testing and release-maintenance rules.
- Strengthens release validation around the demo catalog and refreshes maintainer/troubleshooting documentation.

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
Structured Song Prompt (Genre / Tempo / Key / Lyrics ...) + prompt library
        ↓
Integrated LLM Chat (llama.cpp)
(max_tokens = 16384, n_ctx = 32768 in example)
        ↓
Caption / Lyrics / Title / Image Prompt
        ↓
MiniMax Music 3
        ↓
Source Declip Repair
        ├──────────────────→ clean original branch ─┐
        ↓                                           │
PRE low-pass → Integrated FlashSR ─────────────────┤
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

## Switching the LLM section off

- Set `LLM Chat (llama.cpp) → enabled` to false, or bypass the LLM nodes (the parser's LLM input is optional).
- Fill `manual_caption` and `manual_lyrics` (optionally `manual_title`, `manual_image_prompt`) on the parser node.
- The rest of the workflow keeps running without the LLM.

## Model auto-download

`models_config.json` lists every model file the example workflow references together with its target folder and, where available, its download URL. On first use, `MiniMaxModelAutodownload` (and the integrated FlashSR/LLM nodes) check these files, download missing ones with progress logging, and the run continues. Gated MiniMax / FLUX.2 weights have no public URL and are reported with guidance instead.

## Output structure

The example workflow defaults to a structure like:

```text
ComfyUI/output/
└── audio/minimax3/<YYYY-MM-DD>/Example Album/
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

For the integrated LLM chat node, additionally install `llama-cpp-python` in the same environment:

```bash
python -m pip install llama-cpp-python
```

and place a llama.cpp-compatible GGUF in `models/llm` (or configure a download URL in `models_config.json`).

## Prompt library

Bundled prompts live under:

```text
prompts/
├── system/
│   └── minimax-music3-production.txt
└── user/
    ├── alternative/
    ├── ambient/
    ├── classical/
    ├── comedy/
    ├── edm/
    ├── electronic/
    ├── folk/
    ├── funk/
    ├── house/
    ├── jazz/
    ├── metal/
    ├── pop/
    └── rock/
```

For user and system prompts independently choose:

- `manual`
- `bundled_library`
- `external_directory`

Prompt files can start with an optional metadata block that prefills the structured fields (Genre, Tempo, Key, Lyrics, Language, Voice, Theme, Length) when the file is selected:

```text
---
Genre: Melodic Techno
Tempo: 128 BPM
Lyrics: sparse
---
Free text describing the track in more detail.
```

See [PROMPT_LIBRARY.md](PROMPT_LIBRARY.md).

## Example workflow

Load:

`example_workflows/MiniMax_Music3_Production_Toolkit.json`

The public workflow contains generic metadata and no machine-specific paths. It is intended as a complete reference workflow; individual toolkit nodes can also be used independently.

## Audio demos / SoundCloud

A curated **25-track** GitHub Pages demo is included. It is driven by the supplied production metadata and supports cover art, SoundCloud playback, search/filtering, musical summaries and expandable generation details.

- Listening page source: `docs/index.html`
- Track/SoundCloud configuration: `docs/demo-tracks.js`
- Cover images: `docs/assets/demo-covers/`
- Setup instructions: [AUDIO_EXAMPLES.md](AUDIO_EXAMPLES.md)
- Intended public page: `https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/`

The demo configuration preserves existing SoundCloud playlist/track URLs; newly prepared tracks may intentionally keep an empty `soundcloudUrl` until they are uploaded. For future additions, prefer `scripts/update_demo_catalog.py` to extract safe public metadata from production JSON, then paste the normal public SoundCloud URL into the matching `soundcloudUrl` field. Local cover JPGs can be copied directly or prepared with `scripts/prepare_demo_covers.py`. If no local JPG is present, the page can fall back to SoundCloud's visual player so the SoundCloud artwork remains visible.

## Documentation

- [Installation and dependencies](INSTALLATION.md)
- [Complete workflow guide](WORKFLOW.md)
- [Prompt library](PROMPT_LIBRARY.md)
- [Audio processing pipeline](AUDIO_PIPELINE.md)
- [Artwork workflow](ARTWORK_WORKFLOW.md)
- [Audio examples / SoundCloud](AUDIO_EXAMPLES.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Publishing / maintainer guide](PUBLISHING.md)
- [Development guide](DEVELOPMENT.md)
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
