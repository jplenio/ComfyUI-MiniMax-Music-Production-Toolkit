# MiniMax and YuE2 song production

Open `example_workflows/Yue2_MM3_Production_Toolkit.json`. Its first control,
**00 · CHOOSE / Song model**, selects **YuE2** (the example default) or **MiniMax Music 3**.
This switches the actual generator as well as prompt templates and settings.
The classic `MiniMax_Music3_Production_Toolkit.json` remains a fixed MiniMax
workflow for existing users.

## Start a song

1. Choose the song model and the production stages in **CHOOSE**:

   | Choice | Default | Behavior |
   | --- | --- | --- |
   | Model | YuE2 | Switches generator, prompt family and active sampler settings. |
   | Cover | On | Controls rendering, preview, cover file and FLUX.2 model checks/downloads. |
   | Refinement | Model default | MiniMax: on. YuE2: off. Choose On or Off for a fixed override. |
   | Mastering | On | Controls Auto-EQ, manual EQ, release sample rate and compressor. |

2. On **Generate song**, enter the installed model filenames. The YuE2 example
   uses `yue2_3b_bf16.safetensors`.
   This is a local filename, not a download URL or a required quantization.
3. Choose your song template, genre, tempo, meter, vocals, language and description.
   Select the LLM provider as before.
4. Review **Music settings**. MiniMax and YuE2 have separate editable sampler
   groups. The selected group is used automatically; the other group's values
   are retained for switching back. `max_duration` is a ceiling, not an exact
   runtime. `yue2_max_duration` defaults to 360 seconds independently of the
   MiniMax `max_duration`. The description's target length remains a compositional request.
5. Set output folder and artist/album, then queue.

The YuE2 default path skips declipping, PRE/POST filtering, FlashSR, crossover
and HF repair, and sends generation directly to mastering. This saves the time
and model loading required for restoration. Refinement remains available for
tracks that benefit from it. When Mastering is off, release files receive the
incoming audio at its existing sample rate. Original generation is always saved;
the saver's configured peak handling still applies. Disabling both audio stages
passes generation straight to the release savers.

Skipped stages do not execute to produce reports: their JSON sections say
`status: bypassed`. Effective central choices are recorded under
`generation.production_stages`. Avoid connecting extra output/preview nodes
directly inside a stage if you want the whole stage to remain skippable.

Only the selected song engine is expanded and loaded. The model-check node also
checks the selected song engine. `yue2_models` and `auto_download` are enabled
in this example, so missing BF16 weights are downloaded before generation.
Disable auto_download for checks without transfers. The verified download is
pinned to a Comfy-Org revision and checked against the expected byte size.
[Comfy-Org checkpoint source](https://huggingface.co/Comfy-Org/YuE2).
Custom checkpoint filenames still need their own installed files/catalog entry.
YuE2 checkpoints go
in ComfyUI's `checkpoints` model category; MiniMax uses `diffusion_models`,
`text_encoders` and `vae`. ComfyUI's configured model directory applies.

YuE2 needs a ComfyUI build exposing `YuE2GenerateABC`, `YuE2GenerateMusic` and
`EmptyYuE2LatentAudio`. The integration was checked against the native source
and the supplied `yue2_full.json` on 2026-09-14. Third-party Yue node packs with
different node names are not drop-in replacements. Restart ComfyUI and reload
the browser after installing the updated toolkit.

## Why the prompts differ

YuE2 accepts a musical **style** description and separate **lyrics** with section
tags. Its planner creates a symbolic composition before audio synthesis.
[Official generation guide](https://github.com/multimodal-art-projection/YuE/blob/main/docs/generation.md)

Our LLM output contract is `[Style]`, `[Lyrics]`, `[Title]`, `[Image_Prompt]`.
Title and image prompt are toolkit additions; only Style and Lyrics enter the
music nodes. The existing parser output socket is still named `caption` for
compatibility. For YuE2 it carries Style without MiniMax text normalization.

For example, a toolkit request can use:

```text
[Style]
English, intimate folk-pop, warm female voice, fingerpicked guitar,
piano, restrained brushed drums, hopeful, 92 BPM, 4/4

[Lyrics]
[Verse]
I left a lantern by the door
Its little sun across the floor

[Chorus]
When the road runs out of light
Let it bring you home tonight
```

The twelve files under `prompts/system/yue2/` correspond to the twelve MiniMax
templates: production, compact-core, concise, cinematic, dance-energy,
emotional-story, fantasy, fast-tempo, genre-faithful, instrumental-first,
lyrics-first and minimal-sparse. Their writing priorities are retained, while
the MiniMax caption format is replaced with the YuE2 contract.

Concise comma-separated descriptors are our writing preference, not a mandatory
model grammar. Section tag capitalization, a 300-character limit and fixed
instrumental-to-vocal section ratios are not asserted as model requirements.
For **Lyrics = instrumental**, all twelve templates require explicit instrumental
exclusions in Style and a Lyrics section containing only tags. The structured
brief reinforces this even when an old vocal/language selection remains set.
No lyric words, syllables, scat, spoken text or vocal hooks are permitted.
Human voices are excluded by default. Only explicitly requested background
closed-mouth humming may be described in Style, never transcribed into Lyrics.

```text
[Style]
Instrumental, piano and warm strings, reflective, 80 BPM, 4/4,
no sung or spoken words, no lead vocals, no backing vocals, no choir

[Lyrics]
[Intro]
[Instrumental]
[Outro]
```

This is a toolkit prompting convention; YuE2 has no documented hard switch
guaranteeing voice-free audio. Review the generated Style/Lyrics in the prompt
report and listen to the result. No exact runtime is guaranteed.
Language choices remain available for experimentation;
the toolkit does not certify equivalent quality across languages.

On a model change, a bundled template changes to its corresponding family.
The backend also performs this mapping for API/headless runs. Same-family edits,
manual prompts and external templates remain authoritative. Unsaved per-family
edits are retained while switching in the current browser session; save a custom
template to keep them permanently. Custom/external prompts must use the right
contract for the selected engine.

## Generation and records

The reference's new-song path is implemented as:

```text
Checkpoint → Generate ABC → Generate Music → actual seconds → Empty latent
                            ↓                               ↓
                         conditioning ──────────────────→ sampler → decode
```

`full` generates melody and chords; `melody` generates a melody plan. In this
native ComfyUI implementation an empty ABC input silently selects `off`, so the
toolkit explicitly connects the ABC generator. The separate SheetSage2
audio-to-score cover branch of the reference is not needed for new songs.
[YuE2 modes and covers](https://github.com/multimodal-art-projection/YuE#quick-start)

The reference acoustic settings use 32 steps; this workflow now uses **40 steps**
as requested, with CFG 1 and `dpm_2` / `sgm_uniform`.
ABC sampling uses the inspected native defaults: 8192 maximum tokens,
temperature 0.7, top-p 0.9, top-k 30, repetition penalty 1.005 and window 100.
Music-token generation has its own editable settings. Model management and
execution stay with ComfyUI through dynamic graph expansion.

The text-budget estimate is explicitly not a measurement with YuE2's tokenizer.
The native implementation's 24576-token context also holds instructions, ABC
and music. The 4500-token toolkit text budget does not guarantee a particular
remaining duration. Automatic lyric trimming is off in the new example; an
oversized request stops with a message rather than silently losing its ending.

The production JSON records `song_model`, `generation` (effective settings,
filenames, generated seconds and ABC) and `style`. YuE2 runs do not receive
mislabelled MiniMax settings. The Markdown report shows the actual input
strings without claiming to reconstruct YuE2's internal tokenizer prompt.
These records are traceability data, not a complete native resumable checkpoint;
semantic tokens and latent arrays are not exported by this workflow.

Original YuE2 audio is 48 kHz. Existing restoration, EQ, mastering and cover
stages remain in place; release conversion is independently set to 44.1 kHz
in this example. Original files use `original-flac/` to avoid a misleading rate
in the directory name.

## Verification scope

Automated checks cover both expanded engines, ABC/music connections, actual
duration wiring, model-specific sampler settings, parser/tokenizer isolation,
template mapping, production records and workflow links. All model/stage
combinations are checked for accidental output/report dependencies. Native ComfyUI
CPU execution confirms audio-stage bypass and cache transitions with synthetic
sources. Full GPU generation,
audible quality and actual browser interaction require a host acceptance run.
No audio-quality or VRAM benchmark is claimed by these software checks.
