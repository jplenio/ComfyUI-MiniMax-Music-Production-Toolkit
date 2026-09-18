# Music Production Toolkit 3.1.1 for ComfyUI

<p align="center">
  <img src="assets/branding/banner.png" alt="Music Production Toolkit for ComfyUI — YuE2, YuE2 Cover and MiniMax Music 3" width="100%" />
</p>

**A Swiss Army knife for local music production on ComfyUI.** Generate a song from
a description, turn an existing track into a cover, repair and master a finished
recording, and tag and export the result — one toolkit, one place, no cloud
service in the middle.

Everything runs on your own machine. You choose the language model, the song
model and the artwork model, and the workflow keeps a record of what was used.

## Listen to the demo gallery

**🎧 [Open the demo gallery](https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/)** —
35 generated tracks with search, filters and the settings behind each one —
instrumental and vocal, YuE2, YuE2 Cover and MiniMax Music 3. Hear what comes out
before you install anything.

## New highlight: the cover feature

**Turn an existing track into your own version of it — with as much or as little
control as you want.** Point *Cover song · source audio* at a file, describe the
style you want, and queue. That is the whole minimum. Everything else is
**optional** and off the critical path: leave it on auto and one slider decides
how far the cover departs from the original.

This is not a remix that keeps a loop and hopes for the best. SheetSage2 reads the
**actual musical score out of your recording** — melody, chords, phrases, sections —
and everything after that works on real notes:

1. **Listen.** SheetSage2 transcribes your file into a score with measured section
   boundaries, inside ComfyUI.
2. **Plan.** The Cover Studio states what it will preserve and what it will change
   *before* touching a note, from the freedom slider and, if you want, from the
   advanced settings.
3. **Rewrite.** The score is rewritten in ABC — transposed, re-temped, thinned to a
   melody line, restructured — exactly as far as your freedom setting allows.
4. **Verify.** Every model answer is validated against the native ABC dialect and
   the plan. An answer that breaks the contract is rejected and the validated
   deterministic result is used instead; the engine never receives unchecked model
   output.
5. **Render.** YuE2 performs the new version. For an instrumental, the notes that
   carried the vocals move into the native instrumental part and are played by the
   **lead instrument** you named, while the vocal line becomes rests.
6. **Check, if you want it.** The optional vocal check listens to the render,
   counts the words it hears, and re-renders within the limit you set.

If you do want to steer it, almost every part of the arrangement is a knob:

- **Interpretation Freedom (0–100)** — from a faithful re-recording of the same
  song to a free recomposition that keeps only its character. At `0` the source
  score is *enforced*: a model that rewrites a note, a chord, a bar or the tempo is
  rejected, and a `full` cover keeps its harmony at every freedom level.
- **Advanced mode** — decide element by element what stays: main melody, chorus
  hook, structure, harmony, tempo and key; plus how much melody, rhythm, harmony
  and structure may vary, a key shift in semitones, a tempo change and the vocal
  range of the new version.
- **Lyrics policy** — let the mode decide, lock the source words, or supply your
  own and keep them exactly. The words never follow the slider.
- **Cover mode and lyrics mode** — condition on melody and harmony, or on melody
  alone; then choose new lyrics, the original words, or a pure instrumental.
- **Lead instrument** — which instrument carries the former vocal line when no
  one sings.
- **Instrumental vocal check** — re-render a take that still contains words, with
  a word tolerance and a retry cap; every take is transcribed, logged and kept
  until the best one is chosen.
- **The rest of the chain** — length target, steps and sampler, artwork, refinement
  and mastering, each with its own on/off switch.

Nothing here is required, and nothing overrides you: **the style you chose and the
lyrics keep priority at every freedom level.** More freedom means that less of the
*original audio* survives — never that less of *your* template is delivered.

Hear what it produces: the [demo gallery](https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/)
holds instrumental and vocal covers across the freedom range. See
[Cover Studio](docs/YUE2.md#yue2-cover-studio) and
[cover lyrics modes](docs/YUE2.md#cover-lyrics-modes).

**Also new: an honest answer to "is it really instrumental?"**, **two workflows
instead of three**, and **every run logged with its date, time and source file** —
the main workflow handles YuE2, YuE2 Cover and MiniMax Music 3, and the
audio-enhancement workflow carries every restoration and mastering stage of the
main one plus your original file's own tags and cover art.

[What's new in 3.1.1](RELEASE_NOTES_v3.1.1.md) · [Complete workflow guide](docs/WORKFLOW.md) ·
[Installation](INSTALLATION.md)

## What the toolkit does

- **Write a song from a description.** Pick a template or write your own brief,
  choose a language model, and get a complete song request: developed arrangement,
  synchronized lyrics, title and a matching album cover.
- **Cover an existing track.** SheetSage2 reads a musical score from your audio,
  and YuE2 renders a new version in the style you describe — instrumental, with
  new lyrics, or with the original words.
- **Direct how far the cover may go.** One slider from a faithful rendition to a
  free recomposition, with the style and the lyrics held constant.
- **Keep the words you want.** Lock the source transcription or your own lyrics so
  neither the slider nor the model can rewrite them.
- **Check that an instrumental is instrumental.** Optional, and the only honest
  test there is: transcribe the render, count the words, retry within a limit you
  set, and keep the take with the fewest words when none is clean.
- **Repair and restore a recording.** Declick and declip, band-limited
  restoration, high-frequency repair, optional artifact reduction, Auto-EQ and
  manual EQ, rate conversion and mastering to a target loudness.
- **Compare honestly.** Every processing stage can be bypassed, and the workflow
  records what ran, what was skipped and with which settings.
- **Render artwork.** A FLUX.2 cover from the song's own image prompt, at the
  resolution your GPU can take.
- **Tag and release.** Title, artist, album, track, genre and embedded cover art,
  in FLAC and MP3, with a production JSON and a prompt report for every run.
- **Bring your own models.** YuE2 and MiniMax Music 3 for songs, SheetSage2 for
  scores, faster-whisper for lyrics, any local or cloud LLM for the text, and
  FLUX.2 for the artwork. Each is downloaded on demand and checked before a run.

**From a song idea to music, mastering and cover artwork — in one connected workflow.**

Describe the music you want to make. Choose a genre, a mood, a voice or a lyrical
theme, and let the toolkit turn your idea into a production brief for YuE2 or MiniMax
Music 3. Generate the song, refine its sound, shape the final master and save
your audio, artwork and production record together.

Already have a song? Select **YuE2 Cover** to create a new arrangement, or open
[Music_Production_AudioEnhance.json](example_workflows/Music_Production_AudioEnhance.json)
to enhance and master the recording you already have.

Created by [Johannes Plenio](https://github.com/jplenio).

## What's new in 3.1.1

A patch that makes long runs easier to follow, fixes one cover stopper and refreshes
the look:

- **Every log line now carries the date and time** (`2026-09-18 14:22:31 Saved
  artwork: …`), so a ComfyUI log reads as a timeline: when a run started, how long a
  stage took, which result belongs to which attempt.
- **A cover run names the audio file it was made from** — the file, its full path,
  its size and the three cover choices, once when the file is selected and again for
  every generated song.
- **Fixed: `original lyrics` covers stopped before the first note.** The bundled
  workflow carried the toolkit's "field not set" placeholder in the Whisper node's
  language field. It now stores `auto`, and a workflow test refuses any stored value
  the node does not offer.
- **New banner, icon and workflow screenshots.** The toolkit is no longer MiniMax
  only — YuE2, YuE2 Cover and MiniMax Music 3 live side by side, and the branding now
  says so. Both workflows are pictured above.
- **Documented:** the `_ProactorBasePipeTransport` message a long Windows run can
  print is a dropped client connection, not a toolkit failure — see
  [troubleshooting](TROUBLESHOOTING.md#exception-in-callback-_proactorbasepipetransport_call_connection_lost-during-a-run).

**The cover feature in detail.** *Cover song · source audio* has a
**Cover lyrics** setting with three modes, and the choice reaches the score node,
the Whisper node, the LLM prompt, the parser provenance and the production JSON.
See [cover lyrics modes](docs/YUE2.md#cover-lyrics-modes).

- **Instrumental.** Vocal notes become rests; the melody moves into the native
  instrumental part. Lead instrument selects its sound. Overlapping instrumental
  material in those blocks is replaced and reported. The choice overrides all
  template vocal requests. Reports keep section tags; native YuE2 receives a
  musical-tag Style and empty lyric sections; arbitrary planning prose stays out of the native input.
- **New lyrics.** Whisper supplies timed source phrases; the LLM writes new
  words for the chosen template, matching approximate syllable density, stress
  and breathing points. Note counts are guidance, not exact sung-syllable counts.
- **Original lyrics.** Whisper transcribes; Python restores the unchanged source words into measured ABC sections using Whisper timestamps.
  The parser checks every word in order, including repetitions, and stops if the
  source text failed the final lossless-word check; LLM rewrites are repaired automatically.
- **Whisper is gated to text-bearing covers.** Both new and original lyrics use
  it in the bundled workflow. Instrumental and other song models do not. Install
  the engine with `pip install -r requirements-whisper.txt`; the model check can
  download the pinned `whisper-large-v3` checkpoint (about 2.9 GB).

Whisper uses song-friendly VAD-off defaults, retries strongly filtered audio,
and runs in a cancellable process with progress and timeout handling. Obvious
opening-only fragments stop before generating an almost wordless cover.
Whisper can mishear or hallucinate lyrics, and the score cannot force an exact
audio performance. Inspect the transcript and listen to the result. See the
[cover review and correction plan](docs/YUE2_COVER_REVIEW.md).

**Instrumental vocal check: it listens, then keeps the least vocal take.** YuE2 can
add voice-like material to an instrumental even when the score contains no vocal
notes at all. The check transcribes the freshly decoded song, logs the words it
heard and compares them with the tolerance you set. Every take is written to a
temporary WAV while the run is in progress, and when no take reaches the tolerance
the one with the **fewest recognised words** continues into the rest of the chain
instead of whichever take happened to be last; the other candidate files are
deleted. A clean first take still costs one generation, because the next take is
only rendered when it is actually needed. It is opt-in, since transcription costs
time.

**YuE2 Cover Studio: one Interpretation Freedom slider.** The optional Studio path
inside the [main workflow](example_workflows/Music_Production_Toolkit.json) adds an
optional stage in front of the cover chain. From `0` (a faithful cover - same
melody, structure, harmony, tempo and key, new sound) to `100` (a creative
recomposition that keeps only key, tempo, structure and character), the slider
decides what stays recognisable and what may be reworked.

It is a **toolkit abstraction, not a YuE2 parameter**: nothing is forwarded to
the engine as a number. The slider produces a structured profile, explicit user
settings always override it, and only real operations move - a transposed key, a
rewritten tempo, a chord-free melody line, and a concrete plan the model must
follow. The score is never trusted to the model alone: every answer is validated
against the native ABC dialect and the profile, and the validated deterministic
result is used when it does not hold up. At `0` that is enforced rather than
promised: a model score that rewrites a note, a chord, a bar or the tempo is
rejected, so a faithful cover really is the source score.

**The words never follow the slider.** *Lyrics policy* keeps the source words or
your own words exactly as they are, and its output is wired to the parser's
locked-lyrics input. **Neither does the style**: more freedom means that less of
the source audio is retained, never that less of the requested template is
delivered. A `full` cover also keeps its harmony at every freedom level, so the
score and the decode mode never disagree. Up to two model calls, one optional
repair. See [YuE2 Cover Studio](docs/YUE2.md#yue2-cover-studio).

## Choose your workflow

Two workflows, and that is the whole set:

- **[Music_Production_Toolkit.json](example_workflows/Music_Production_Toolkit.json)
  — the main workflow.** New songs with YuE2 or MiniMax Music 3, cover versions
  with YuE2 Cover, the optional Cover Studio in front of it, artwork, restoration,
  refinement and mastering, tags and the production record. Start here.
- **[Music_Production_AudioEnhance.json](example_workflows/Music_Production_AudioEnhance.json)
  — enhancement and mastering only.** Load an existing recording; it runs every
  restoration and mastering stage of the main workflow and copies your file's own
  tags and embedded cover art onto both exports.

Open the JSON in ComfyUI or drag it onto the canvas. The grouped notes inside each
workflow explain where to start and which controls matter.

<p align="center">
  <img src="assets/branding/screenshot-main-workflow.png" alt="The main workflow in ComfyUI, grouped and labelled: CHOOSE, START, WRITE, GENERATE, REFINE, ILLUSTRATE, MASTERING and DELIVER" width="100%" />
</p>

*The main workflow in ComfyUI: labelled groups from the first choice to the finished
release — CHOOSE → START → WRITE → GENERATE → REFINE → ILLUSTRATE → MASTERING → DELIVER.*

### Create a new song

1. Choose YuE2 or MiniMax Music 3 in CHOOSE. Set your output folder, artist and album.
2. Choose a prompt template or describe your own idea. Adjust genre, tempo,
   language, voice and length as needed.
3. Check the model settings for your computer, then queue the workflow.
4. Listen to the result and adjust the restoration or mastering to taste.

Your chosen LLM prepares the caption, lyrics, title and cover idea: use a GGUF
inside ComfyUI, a model in another local app, or a cloud provider.
The selected YuE2 or MiniMax Music 3 model generates the music. Audio restoration and mastering prepare the
release sound, while the optional FLUX.2 branch creates matching artwork.

The production workflow saves source FLAC, mastered FLAC and MP3, cover JPG,
standard audio tags, a prompt report and one central production JSON. Files use
the `Album - Title` naming convention.

Audio decoding checks for invalid model output and can retry once with smaller
tiles without generating the music again. Audio savers reject invalid samples
instead of writing a broken file. See [audio error help](TROUBLESHOOTING.md#audio-export-fails-with-a-blank-assertionerror).

### Create a cover version

1. Select **YuE2 Cover** in CHOOSE.
2. Upload or select a track in **SOURCE AUDIO**. Use `full` for melody and
   harmony, or `melody` for greater freedom in the accompaniment.
3. Describe the new arrangement in WRITE. The workflow supplies the source ABC
   to your LLM automatically; you do not need to write notation yourself.
4. Queue the workflow. For example, `My Song.wav` becomes **My Song-cover**,
   with the same title used throughout the export pipeline.

**Want more control over how far the cover departs from the original?** Set
**Interpretation Freedom**. `0` keeps the song as faithful as possible and `100`
uses it only as a compositional reference. The slider is a toolkit abstraction,
not a YuE2 parameter - see [YuE2 Cover Studio](docs/YUE2.md#yue2-cover-studio), and
[new highlight: the cover feature](#new-highlight-the-cover-feature) for the
optional settings around it.

The model check can download SheetSage2 when this mode is selected. The normal
YuE2 and MiniMax paths ignore the source audio input. See [requirements and
cover controls](docs/YUE2.md#cover-an-audio-file).

### Choose your language model and artwork

The LLM node has three clear modes: **In ComfyUI (GGUF)**, **Local app / server**,
and **Cloud service**. Choose LM Studio, Ollama, llama.cpp, Unsloth Studio or
vLLM locally; or OpenAI, Claude, Gemini, DeepSeek, Qwen, MiniMax, OpenRouter or
Groq in the cloud. Other OpenAI-compatible endpoints can be entered manually.
Only the relevant settings are shown. **Set API key** keeps the secret out of
your workflow; **Find models** helps select a model from your server.
The LLM generates fresh text on each queued execution, without a separate
session-ID node. In cloud mode, each new request may incur API charges.

In the main workflow, **Cover** in **CHOOSE** controls artwork and defaults to
**ON**. It is independent of the **YuE2 Cover** song mode. Turn it off to skip
artwork generation and FLUX downloads.

Cloud mode sends your prompts to the selected provider and may incur API charges.
For YuE2 Cover, the prompt also contains the source filename and ABC transcription.
Local apps manage their own model memory; ComfyUI's LLM unload node cannot unload
another app's model. See the [step-by-step connection and cover guide](docs/LLM_PROVIDERS.md).

### Enhance an existing recording

Load a song in **Music_Production_AudioEnhance.json**, set its title and tags,
then adjust the processing. This is useful for comparing settings without
generating new music. The source file's own tags and embedded cover art are
copied onto both exports.

The chain includes de-clipping, FlashSR, high-frequency blending and repair,
followed by the new mastering section. Each recording is different: compare
versions at similar listening loudness and keep the processing that helps.

<p align="center">
  <img src="assets/branding/screenshot-audio-enhancement.png" alt="The audio-enhancement workflow in ComfyUI: load a file, run the restoration chain, master it and export" width="100%" />
</p>

*The audio-enhancement workflow: bring your own file, run the same restoration and
mastering chain, and receive both exports carrying your original tags and cover art.*

## Mastering, with as much control as you want

**Auto-EQ is enabled by default when Mastering runs.** The main workflow starts with
**Warm - gentle (workflow default)**: Warm tilt, 35% strength, maximum 2 dB,
four bands, 40–16000 Hz. No reference audio is needed. Switch `enabled` off to
leave automatic tonal shaping out, or connect a reference track and choose a
Reference preset for a guided tonal comparison. Missing reference audio in
Reference mode produces a warning and skips correction.

The **manual 8-band EQ** stays editable whether Auto-EQ is on or off. Shape the
curve visually or enter precise values. Use its own `bypass` control to
disable only your manual EQ.

Choose from **10 Auto-EQ presets** and **24 manual EQ presets**, plus Custom.
The Auto-EQ workflow preset is **Warm - gentle**; manual EQ starts **Flat**.
For harsh YuE2 highs, try **YuE2 - Smooth highs** or its stronger variant.
Presets remain fully editable and save with the workflow. See the
[preset guide and YuE2 recommendations](docs/EQ_PRESETS.md).

The main workflow also includes **experimental AI Audio Artifact Reduction**
for brief whistles and metallic spectral spikes. Control `artifact_reduction_enabled`
in **CHOOSE**; it starts **on**, uses **Balanced** sensitivity and runs independently between Refinement and
Mastering. An analysis-only mode and a removed-audio output help you judge what
it detects. It cannot distinguish every unwanted artifact from wanted music.
See [research, usage and limitations](docs/ARTIFACT_REDUCTION.md).

The **mastering compressor** starts with a gentle 1.5:1 ratio and a
**−14 LUFS / −1 dBTP** target. Switch `compressor_enabled` off to retain
loudness targeting and limiting without compression. Full mastering bypass
disables all dynamics and loudness processing.

The final sample rate defaults to **44.1 kHz**. Choose **48 kHz** in the
Output rate node when needed, and leave the master's rate set to `keep`.
Conversion happens before the final limiter, including when mastering is bypassed.

In the main workflow, switching **Mastering** off centrally skips the whole
mastering area, including sample-rate conversion. The compressor's own bypass
is a separate control inside that area.

Peak and gain-reduction limits take priority when the requested loudness cannot
be reached safely. The report explains the result. These presets are useful
starting points; the best master still depends on the source and your listening.

[Mastering controls and workflow guide](docs/WORKFLOW_OPTIMIZED.md) ·
[DSP details and node documentation](docs/AUDIO_MASTERING.md)

## Built for different computers

You do not need the author's PC configuration. Choose models and processing
settings that fit your available RAM and VRAM.

- **Less memory:** select a smaller GGUF language model, reduce its context/output
  budget, lower artwork resolution or switch the cover off. A cloud LLM avoids
  local LLM model memory. The audio-enhancement workflow avoids the music
  and artwork generation stages entirely.
- **More memory:** use larger compatible language models or higher artwork
  resolutions when they benefit your project.
- **CPU mastering:** EQ, analysis, compression and limiting do not require GPU
  memory. Full audio buffers and generation models still need system memory.

**A smaller local model is a memory saving, not a free one — the text side is the hard
part.** The toolkit's prompts are long and tightly structured: the cover path hands the
model the source score, the arrangement plan and the style template together and asks
for a complete rewritten score back. Small local models — a few billion parameters, or
heavily quantised — can lose the thread: a truncated answer, invented notation, an
ignored constraint. **The cover feature is by far the most demanding part of the
toolkit in this respect**; a plain song request is easier, and the audio-enhancement
workflow needs no language model at all. Expect to experiment here.

Two things make that worse, and both are easy to avoid. Lowering the context or output
budget to save memory also removes the room the rewritten cover score needs — a budget
that is generous for a caption can be too small for a score. And a vague style
description gives a weak model more room to invent; a short, concrete one helps.

What the toolkit does about it: an answer that breaks the notation contract is
rejected, and the validated deterministic score is used instead. A weak model therefore
degrades the result rather than producing a broken file — but it cannot rescue a cover
the model never managed to write. If a small model keeps failing on the cover path,
try a larger one, a cloud provider for the text, or the advanced settings that make the
rework simpler before you conclude the cover itself cannot work.

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
manually in the parser. For YuE2 Cover, the title always comes from the source
filename; manual and LLM title suggestions do not replace it.

[Explore the prompt library](docs/PROMPT_LIBRARY.md).

## Installation and update

Install this repository in your ComfyUI `custom_nodes` folder, then install
its dependencies using **the Python environment that runs ComfyUI**:

```bash
python -m pip install -r requirements.txt
```

The integrated local LLM additionally requires a suitable `llama-cpp-python`
installation; local-server and cloud modes do not. Backend builds and GPU support vary; follow
[INSTALLATION.md](INSTALLATION.md) rather than assuming a generic package
installation enables GPU acceleration.

Restart ComfyUI and refresh the browser after installation or update.
Reopen the bundled workflows after updating: 3.1 consolidated them into
`Music_Production_Toolkit.json` and `Music_Production_AudioEnhance.json`.
Existing saved personal workflows are not automatically replaced, so replace their
absolute-path and node wiring by re-importing the bundled files; keep your own copies
when updating. The higher example LLM budgets need a machine that can hold them -
[INSTALLATION.md](INSTALLATION.md) says what to reduce first.

Model weights are downloaded or supplied separately. The model checker helps
identify missing files, and supported automatic downloads use the configured
catalog. Some models may require accepted license terms or authentication.
See [installation](INSTALLATION.md) and [troubleshooting](TROUBLESHOOTING.md).

## Documentation

- [Release 3.1.1 notes](RELEASE_NOTES_v3.1.1.md)
- [Release 3.1.0 notes](RELEASE_NOTES_v3.1.0.md)
- [Release 3.0.1 notes](RELEASE_NOTES_v3.0.1.md)
- [Release 3.0.0 notes](RELEASE_NOTES_v3.0.0.md)
- [YuE2 new songs and audio cover guide](docs/YUE2.md)
- [Combined 2.x release notes](RELEASE_NOTES_v2.x.md)
- [Combined 1.0.x release notes](RELEASE_NOTES_v1.0.x.md)
- [Installation and dependencies](INSTALLATION.md)
- [Complete workflow guide](docs/WORKFLOW.md)
- [Mastering workflow controls](docs/WORKFLOW_OPTIMIZED.md)
- [Audio processing pipeline](docs/AUDIO_PIPELINE.md)
- [EQ and mastering details](docs/AUDIO_MASTERING.md)
- [Prompt library](docs/PROMPT_LIBRARY.md)
- [Artwork workflow](docs/ARTWORK_WORKFLOW.md)
- [Demo gallery setup](docs/AUDIO_EXAMPLES.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Development](DEVELOPMENT.md) · [Publishing](PUBLISHING.md) · [Changelog](CHANGELOG.md)

## A few practical limits

De-clipping cannot recover information that has been lost completely. FlashSR
can generate high-frequency content that needs further adjustment. EQ and
mastering cannot fix every issue in an arrangement or stereo mix. Listen before
publishing, and check encoded files when their final loudness or peaks matter.

This is an independent community project. YuE2, SheetSage2, MiniMax, FLUX, LLM and FlashSR model
weights are not included, and their licenses apply separately.

## License

MIT for the toolkit. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
