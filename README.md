# MiniMax Music Production Toolkit 2.5 for ComfyUI

<p align="center">
  <img src="assets/branding/banner.png" alt="MiniMax Music Production Toolkit" width="100%" />
</p>

**From a song idea to music, mastering and cover artwork — in one connected workflow.**

Describe the music you want to make. Choose a genre, a mood, a voice or a lyrical
theme, and let the toolkit turn your idea into a production brief for MiniMax
Music 3. Generate the song, refine its sound, shape the final master and save
your audio, artwork and production record together.

Already have a song? Open the **Audio Enhancement Lab** to work on an existing
recording without generating it again.

Created by [Johannes Plenio](https://github.com/jplenio).
[Listen to the demo gallery](https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/).

## What's new in 2.5

This release brings the improvements together into a clearer, more capable music
production toolkit:

- **Workflows that are easier to follow.** Numbered stages, labelled controls and
  dedicated areas for song creation, audio processing, mastering, artwork and export.
- **A complete mastering section.** Auto-EQ, an editable manual **8-band
  parametric EQ**, and a stereo-linked compressor with LUFS targeting and a
  true-peak limiter.
- **Independent control.** Use automatic tonal shaping, make your own EQ
  adjustments, combine both, or switch either off. Disable compression while
  keeping loudness and peak control active.
- **More efficient processing.** Improvements to model/resource handling,
  block-based audio processing and bounded working buffers help avoid unnecessary
  work and memory use. The new mastering tools run on the CPU and need no extra VRAM.
- **More reliable everyday operation.** Improvements across model downloads,
  prompt handling, file output, metadata and regression testing.

The redesigned workflows now use the familiar filenames. There is no separate
“optimized” version to choose between.

## Choose your workflow

| Workflow | Start with | What it produces |
|---|---|---|
| [Music Production](example_workflows/MiniMax_Music3_Production_Toolkit.json) | A song idea or prompt template | Music, original and mastered audio, cover artwork, tags and a production record |
| [Audio Enhancement Lab](example_workflows/MiniMax_Music3_Production_Toolkit_AudioEnhance.json) | An existing audio file | Enhanced and mastered FLAC with your tags |

Open the JSON in ComfyUI or drag it onto the canvas. The notes inside each
workflow explain where to start and which controls matter.

### Create a new song

1. Set your output folder, artist and album.
2. Choose a prompt template or describe your own idea. Adjust genre, tempo,
   language, voice and length as needed.
3. Check the model settings for your computer, then queue the workflow.
4. Listen to the result and adjust the restoration or mastering to taste.

The integrated local LLM prepares the caption, lyrics, title and cover idea.
MiniMax Music 3 generates the music. Audio restoration and mastering prepare the
release sound, while the FLUX.2 branch creates matching artwork.

The production workflow saves source FLAC, mastered FLAC and MP3, cover JPG,
standard audio tags, a prompt report and one central production JSON. Files use
the `Album - Title` naming convention.

### Enhance an existing recording

Load a song in Audio Enhancement Lab, set its title and tags, then adjust the
processing. This is useful for comparing settings without generating new music.

The chain includes de-clipping, FlashSR, high-frequency blending and repair,
followed by the new mastering section. Each recording is different: compare
versions at similar listening loudness and keep the processing that helps.

## Mastering, with as much control as you want

**Auto-EQ is enabled by default in both workflows.** The starting preset is a
gentle Warm tilt at 35% strength with a maximum 2 dB correction. Switch
`enabled` off to leave automatic tonal shaping out, or connect a reference
track and choose Reference track mode for a guided tonal comparison.

The **manual 8-band EQ** stays editable whether Auto-EQ is on or off. Shape the
curve visually or enter precise values. Use its own `bypass` control to
disable only your manual EQ.

The **mastering compressor** starts with a gentle 1.5:1 ratio and a
**−14 LUFS / −1 dBTP** target. Switch `compressor_enabled` off to retain
loudness targeting and limiting without compression. Full mastering bypass
disables all dynamics and loudness processing.

The final sample rate defaults to **44.1 kHz**. Choose **48 kHz** in the
Output rate node when needed, and leave the master's rate set to `keep`.
Conversion happens before the final limiter, including when mastering is bypassed.

Peak and gain-reduction limits take priority when the requested loudness cannot
be reached safely. The report explains the result. These presets are useful
starting points; the best master still depends on the source and your listening.

[Mastering controls and workflow guide](WORKFLOW_OPTIMIZED.md) ·
[DSP details and node documentation](AUDIO_MASTERING.md)

## Built for different computers

You do not need the author's PC configuration. Choose models and processing
settings that fit your available RAM and VRAM.

- **Less memory:** select a smaller GGUF language model, reduce its context/output
  budget, and lower artwork resolution. Audio Enhancement Lab avoids the music
  and artwork generation stages entirely.
- **More memory:** use larger compatible language models or higher artwork
  resolutions when they benefit your project.
- **CPU mastering:** EQ, analysis, compression and limiting do not require GPU
  memory. Full audio buffers and generation models still need system memory.

The full example retains a demanding 27B LLM selection and large context settings;
these are configurable examples, not automatic hardware recommendations.
Check them before your first run. Smaller settings can trade speed or capacity
for lower memory use; support also depends on the installed model backend.

See [installation and hardware guidance](INSTALLATION.md).

## Your ideas, your prompts

Use the bundled genre library as a starting point, or choose `custom` for
fields you want to leave unspecified. A free description field holds everything
else: atmosphere, instrumentation, story, arrangement or production style.

Templates can prefill the controls, and you can edit and save your own versions.
Separate system prompts let you guide how the LLM develops the musical brief.
You can also disable the LLM and enter caption, lyrics, title and cover prompt
manually in the parser.

[Explore the prompt library](PROMPT_LIBRARY.md).

## Installation and update

Install this repository in your ComfyUI `custom_nodes` folder, then install
its dependencies using **the Python environment that runs ComfyUI**:

```bash
python -m pip install -r requirements.txt
```

The integrated local LLM additionally requires a suitable `llama-cpp-python`
installation. Backend builds and GPU support vary; follow
[INSTALLATION.md](INSTALLATION.md) rather than assuming a generic package
installation enables GPU acceleration.

Restart ComfyUI and refresh the browser after installation or update.
For 2.5, reopen the bundled workflow to get the new layout, mastering chain and
Auto-EQ defaults. Existing saved personal workflows are not automatically
replaced; keep your own copies when updating.

Model weights are downloaded or supplied separately. The model checker helps
identify missing files, and supported automatic downloads use the configured
catalog. Some models may require accepted license terms or authentication.
See [installation](INSTALLATION.md) and [troubleshooting](TROUBLESHOOTING.md).

## Documentation

- [Release 2.5 notes](RELEASE_NOTES_v2.5.0.md)
- [Installation and dependencies](INSTALLATION.md)
- [Complete workflow guide](WORKFLOW.md)
- [Mastering workflow controls](WORKFLOW_OPTIMIZED.md)
- [Audio processing pipeline](AUDIO_PIPELINE.md)
- [EQ and mastering details](AUDIO_MASTERING.md)
- [Prompt library](PROMPT_LIBRARY.md)
- [Artwork workflow](ARTWORK_WORKFLOW.md)
- [Demo gallery setup](AUDIO_EXAMPLES.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Development](DEVELOPMENT.md) · [Publishing](PUBLISHING.md) · [Changelog](CHANGELOG.md)

## A few practical limits

De-clipping cannot recover information that has been lost completely. FlashSR
can generate high-frequency content that needs further adjustment. EQ and
mastering cannot fix every issue in an arrangement or stereo mix. Listen before
publishing, and check encoded files when their final loudness or peaks matter.

This is an independent community project. MiniMax, FLUX, LLM and FlashSR model
weights are not included, and their licenses apply separately.

## License

MIT for the toolkit. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
