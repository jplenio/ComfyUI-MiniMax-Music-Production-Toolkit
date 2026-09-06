# MiniMax Music Production Toolkit for ComfyUI

**Fill in a few fields — get a finished song.**

Just describe what you want to hear. A genre, a mood, a few words about the
theme. The workflow does the rest: it turns your input into a polished
production plan, generates the song with **MiniMax Music 3**, repairs and
refines the audio, creates a matching cover, and saves everything — cleanly
named, tagged, and release-ready — into your output folder.

You don't need to be an audio engineer or understand a chain of twenty nodes.
This toolkit bundles that knowledge into **one** workflow, so the result you
get at the end is something you can publish right away.

Author: [Johannes Plenio](https://github.com/jplenio)

> Independent community project. No MiniMax, FLUX, LLM or FlashSR model weights
> are included — they are downloaded or provided separately (see
> [Installation](INSTALLATION.md)).

## 🎧 Listen first, then try it

The music on this page was generated entirely with this workflow:

👉 [Open the demo gallery](https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/)

If you like what you hear — that is exactly what this project is for.

## Why it feels so easy

The workflow is built so that **you stay creative and it handles the
technology**:

- **Just a few fields.** Genre, tempo, time signature, key, voice, language,
  mood, length — that's all it takes. Every field also has a `custom` option
  when you want to leave something open.
- **One text field for everything else.** Whatever doesn't fit into the fields,
  you simply write as a description — as freely as you like.
- **The model thinks along.** A local language model shapes your input into the
  precise plan MiniMax Music 3 needs, including a fitting song title and cover
  idea.
- **The audio gets cleaned up.** Clipping is repaired, the high frequencies are
  extended (FlashSR), harsh cymbal/shimmer tails are tamed, and the loudness is
  made streaming-safe.
- **Everything is named and tagged at the end.** `Album - Title`, FLAC + MP3,
  cover JPG, and one central production JSON — one song, one tidy folder.

## How a song travels through the workflow

```text
You fill in a few fields
        ↓
Local LLM writes Caption, Lyrics, Title & cover idea
        ↓
MiniMax Music 3 generates the song
        ↓
Audio is repaired & refined (Declip → FlashSR → HF Repair → Release Prep)
        ↓
FLUX.2 creates the cover
        ↓
FLAC + MP3 + Cover + Production JSON are saved
```

The exact technical pipeline is documented in
[AUDIO_PIPELINE.md](AUDIO_PIPELINE.md) and [WORKFLOW.md](WORKFLOW.md).

## The best part: the Custom Mode

At the very top of the prompt you can choose **`custom`**. The workflow then
loads no template at all — it leaves your fields exactly as you filled them in
and uses only what you wrote yourself.

Why is that so great?

- **Full freedom, zero surprises.** No prompt that silently overwrites your
  fields. What you type is exactly what goes in.
- **Still not a blank page.** The option lists for genre, tempo, time
  signature, key and the rest stay available — you can take inspiration from
  them without having to use them.
- **The fastest way to start.** No library to search. Just pick `custom`, fill
  a few fields, write a description — done.
- **The best of both worlds.** You can switch back to a template at any time,
  which prefills the fields for you — and you can still edit everything
  afterwards.

That turns a "pre-made tool" into a real instrument: your taste decides the
song, the machine takes care of the craft.

## What the toolkit does

- **Structured Song Prompt** — dedicated fields for Genre, Tempo (curated BPM ranges, `custom` first), Time signature (curated list from common time to free time / rubato, `custom` first), Key (circle of fifths, minor keys first), Lyrics (yes / sparse / only voice - no words / instrumental), Language (important languages first, then alphabetical), Voice, Theme and Length plus a free description. Prompt files can prefill the fields; every combo field can be overridden and `custom` leaves it out.
- **Integrated LLM Chat (llama.cpp)** — self-contained GGUF chat node; no
  external LLM custom node required. The LLM stage can also be switched off
  completely.
- **Structured LLM parsing** — extracts `[Caption]`, `[Lyrics]`, `[Title]` and
  `[Image_Prompt]` from the response, with manual fallbacks.
- **Production system prompt** — tuned for MiniMax Music 3: long instrumental
  structures, imaginative lyrics, and avoidance of smeared high frequencies.
- **Bundled genre prompt library** — 230+ curated, unified genre templates with metadata: every template carries its Genre / Tempo / Time signature / Key / Lyrics / Language / Voice / Theme / Length as fields, so the free text never repeats them. Coverage spans Western pop/rock/electronic, plus Asian (K-Pop, City Pop, Bollywood, Chinese & Indian traditional, J-RPG / anime), European (Flamenco, Fado, Chanson, Schlager, Klezmer, Balkan), African (Afrobeats, Amapiano, Ethio-Jazz, Highlife, Desert Blues), Latin American (Bossa Nova, Samba, Salsa, Cumbia, Tango, Reggaeton, Bachata) and many more world styles. The dropdown lists the categories alphabetically with their files indented beneath.
- **Reproducible generation controls** — consistent seeds and sampling values.
- **Integrated Audio Super Resolution (FlashSR)** — the inference code is
  bundled; only the weights are fetched on first use.
- **Model auto-download / check** — `models_config.json` plus a check node with
  progress logging.
- **Audio Declip / Overload Repair** — reconstructs short hard-clipped peaks.
- **FlashSR processing tools** — pre/post filtering and controlled
  high-frequency blending.
- **HF Cymbal / Shimmer Repair** — reduces watery upper-frequency sustain
  without destroying transients.
- **Static LUFS / True-Peak Release Prep** — constant loudness with no AGC,
  compressor, or time-varying loudness riding.
- **Release file handling** — FLAC/MP3/WAV, `Album - Title` naming, standard
  tags, configurable cover resolution.
- **Centralized production JSON** — one canonical JSON per song after all
  outputs.
- **FLUX.2 cover branch** — square artwork generation and JPEG saving.
- **Complete UI help** — tooltips for every input and Markdown help for every
  node.

## Installation

Install the package into the `custom_nodes` directory of your ComfyUI
installation and install the dependencies with the Python interpreter that
belongs to your ComfyUI installation. Then restart ComfyUI and hard-refresh the
browser once (`Ctrl+F5`).

For the integrated LLM chat node, additionally install in the same environment:

```bash
python -m pip install llama-cpp-python
```

and place a llama.cpp-compatible GGUF in `models/llm` (or configure a download
URL in `models_config.json`).

Full instructions: [INSTALLATION.md](INSTALLATION.md).

## Example workflows

### Full production workflow

Load:

`example_workflows/MiniMax_Music3_Production_Toolkit.json`

The public workflow contains only generic metadata and no machine-specific
paths. It is intended as a complete reference workflow; each individual node can
also be used independently.

### Audio Enhancement Lab

Load:

`example_workflows/MiniMax_Music3_Production_Toolkit_AudioEnhance.json`

A compact second workflow that **skips the production stage** entirely. It
takes an already-finished song (a 32 kHz MiniMax source file, or any imperfect
recording), runs it through declipping, FlashSR, the hybrid crossover, HF
repair and release preparation, and saves the enhanced result with full tags.
Perfect for experimenting with the enhancement settings without generating a
new song each time: drop in a file, tweak the presets, compare the results.

## Demo & SoundCloud

The included **35-track** GitHub Pages demo is driven by the generated
production data and shows covers, a SoundCloud player, search/filter, musical
summaries, and expandable generation details.

- Listening page: `docs/index.html`
- Track/SoundCloud configuration: `docs/demo-tracks.js`
- Covers: `docs/assets/demo-covers/`
- Setup instructions: [AUDIO_EXAMPLES.md](AUDIO_EXAMPLES.md)
- Public page: `https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/`

## Documentation

- [Installation & dependencies](INSTALLATION.md)
- [Complete workflow guide](WORKFLOW.md)
- [Prompt library](PROMPT_LIBRARY.md)
- [Audio processing pipeline](AUDIO_PIPELINE.md)
- [Artwork workflow](ARTWORK_WORKFLOW.md)
- [Audio examples / SoundCloud](AUDIO_EXAMPLES.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Publishing / maintainer guide](PUBLISHING.md)
- [Development guide](DEVELOPMENT.md)
- [Changelog](CHANGELOG.md)

## Limitations

- De-clipping can reconstruct plausible peak curvature, but it cannot recover
  information that was destroyed by clipping.
- FlashSR can "invent" high-frequency content. Hybrid crossover and HF repair
  are safeguards, not guarantees.
- Static LUFS normalization preserves dynamics and may intentionally finish
  below a requested target when the true-peak ceiling prevents more gain.
- LLM output quality depends on the selected local model.
- GitHub README pages cannot reliably host a native SoundCloud player; the
  included GitHub Pages template is the intended embedded-player solution.

## License

MIT. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
