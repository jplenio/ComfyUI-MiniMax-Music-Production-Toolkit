# MiniMax and YuE2 song production

Open `example_workflows/Yue2_MM3_Production_Toolkit.json`. Its first control,
**00 · CHOOSE / Song model**, selects **YuE2** (the example default), **YuE2 Cover** or **MiniMax Music 3**.
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
   MiniMax `max_duration`. A selected Length becomes an approximate timed
   Style/Lyrics plan, with a natural ending near the target. It never reduces
   the configured generation ceiling or crops audio at the target. For example,
   **Length = 1 minute** with **yue2_max_duration = 360** still allows a 68-second
   song to finish. The model can still finish early; audio is never padded or stretched.
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

The initial audio-cover integration could show a red Cover source node with
`UNKNOWN` inputs even when backend registration succeeded. Its frontend lacked
the preview widget required by ComfyUI's audio uploader. Update the toolkit's
frontend files, reload the browser and reopen the workflow to apply the fix.

## Cover an audio file

1. Select **YuE2 Cover** in CHOOSE, then upload/select your audio in the new
   **YuE2 Cover / SOURCE AUDIO** group above WRITE.
2. Select the source mode: **full** retains melody and harmony and matches the
   normal YuE2 default; **melody** allows a different harmonic accompaniment.
   The official cover guide recommends melody conditioning for stylistic covers.
   This source setting controls both SheetSage2 and YuE2; the separate
   `yue2_mode` field applies only to new-song generation.
3. Describe the desired instrumentation, genre and development in WRITE.
   SheetSage2 transcribes the musical score before the LLM runs. The cover
   instructions ask for a detailed Style arrangement matched to that score,
   with synchronized Lyrics sections. They are added to any selected YuE2
   system template. The score itself passes unchanged to YuE2; there is no
   new Generate ABC step.
4. Leave `sheetsage2_models`, `yue2_models` and `auto_download` enabled in
   **Selected song / artwork / FlashSR model check** to download missing
   configured weights. SheetSage2 BF16 is about 1.39 GB and belongs in
   `models/audio_encoders/sheetsage2_bf16.safetensors`. It is checked only in
   YuE2 Cover mode. Custom encoder names require an installed file or a matching
   catalog entry.
5. Queue as usual. The sampler remains at 40 steps in the example, the YuE2
   duration ceiling at 360 seconds, refinement off by model default, mastering
   and cover artwork on. The artwork switch is independent of audio covers.

`My Song.wav` becomes **My Song-cover**. The parser enforces this title even if
the LLM or manual fields suggest another name. Audio tags, artwork metadata,
output-path source names, production JSON and prompt reports all use it. Existing
album prefixes, filename sanitization and collision rules still apply.

SheetSage2 does **not** transcribe sung lyrics. Supply the words you want in the
brief, use manual lyrics when bypassing the LLM, or request new lyrics. For an
instrumental cover, select instrumental; Lyrics contains section tags only.
The source audio is conditioning material, not a waveform that is mixed into the
output. Duration remains a ceiling, so long sources may need a higher limit.

Normal YuE2 and MiniMax ignore an empty source node and do not load SheetSage2.
The host also needs native `AudioEncoderLoader` and `SheetSage2AudioToABC`.
The supplied cover workflow was used as the wiring reference; no sample audio
or private source filename is included in the public example.

[Official cover guide](https://github.com/multimodal-art-projection/YuE/blob/main/docs/covers.md),
[Comfy-Org model files](https://huggingface.co/Comfy-Org/YuE2/tree/main/audio_encoders).

## Style and Lyrics

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

### One arrangement, two synchronized fields

The active templates now require an identity paragraph **and a chronological
arrangement in Style**. Each numbered entry describes the section's musical
role, motif/harmonic development, instrumental entrances/exits, groove,
energy and transition. Repeated sections must develop rather than restart the
same loop. Minimal/sparse music uses subtler changes instead of compulsory
builds, new instruments or solos.

Style uses entries such as `01 [Intro]: ...`, `02 [Instrumental]: ...`.
Lyrics uses those **same bracketed tags in the same order and with the same
number of occurrences**, without the numbers or arrangement descriptions.
The LLM is instructed to compare both lists and repair mismatches before returning
the answer. Vocal songs use the same rule, with sung words only under the
sections identified as vocal in Style.

For an ordinary 3-6 minute track, the writing target is about 250-450 words of
Style and 6-10 meaningful sections. Short cues and deliberately simple forms
need less. Compact variants shorten wording while retaining the complete map.
These are our composition guidelines, not a YuE2 word limit or a formula for
audio duration. The combined text budget and shared native context still apply.

The official [generation guide](https://github.com/multimodal-art-projection/YuE/blob/main/docs/generation.md)
places musical attributes in Style and sectioned sung words in Lyrics; it does
not prescribe a one-line Style description. The official
[editing guide](https://github.com/multimodal-art-projection/YuE/blob/main/docs/editing.md)
also requires corresponding score and lyric sections to be updated together
when structure changes. Our numbered Style map extends these principles to
the upstream LLM brief. It is not a documented native section-alignment API
and does not guarantee exact realization in the audio. Older YuE-v1 advice
about fixed segment lengths is not treated as YuE2 guidance.

### Requested duration and a natural ending

All active system prompts allocate the requested duration across the arrangement,
including the ending. Timings and plausible bar/phrase counts belong in Style;
Lyrics repeats the same section occurrences without timestamps or timing prose.
For `3-4 minutes`, the planning target is approximately 210 seconds. Neither
240 seconds nor the midpoint becomes a runtime cutoff. A single `1 minute`
likewise means roughly 60 seconds, allowing the last phrase and decay to finish.

The updated main workflow connects the structured summary to the parser and the
parser's provenance to Music settings. The parser places the authoritative
target at the start of final Style, so ABC planning and music generation see
the same request. A free-form/manual Style may instead state
`Target duration: 90 seconds.` when Length is unspecified. A target above the
configured ceiling raises a clear error; increase `yue2_max_duration` or choose
a feasible Length. The technical maximum and available native context still
limit generation, so leave headroom for the ending.

In Cover mode the original ABC remains unchanged. Its phrases take precedence
over forcing an exact duration; the requested length cannot automatically
rewrite or extend the source score. The generation record stores the target,
configured limit, actual duration and difference. A duration outside the requested
range is informational, not a reason to cut, fade or reject the audio.

### Instrumental tracks

For **Lyrics = instrumental**, all twelve templates require explicit instrumental
exclusions in Style and a Lyrics section containing only tags. The structured
brief reinforces this even when an old vocal/language selection remains set.
No lyric words, syllables, scat, spoken text or vocal hooks are permitted.
Human voices are excluded by default. Only explicitly requested background
closed-mouth humming may be described in Style, never transcribed into Lyrics.

The full [instrumental arrangement example](prompts/examples/yue2-instrumental-arrangement.txt)
shows eight synchronized sections: motif introduction, groove establishment,
variation, contrasting bridge, rebuild, fullest statement, release and outro.
All musical descriptions stay in Style; Lyrics contains only the corresponding
eight tags. It is a hand-written format example, not a generated audio benchmark.

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

The previous twelve system prompts are preserved unchanged in
[`prompts/YuE2-old/`](prompts/YuE2-old/README.md), outside the active library.
To use the revision in an existing saved node, reselect the active system-prompt
file (select another file and then switch back), or load the updated example
workflow. Saved editable prompt text remains authoritative; updating files
alone does not overwrite it. For an A/B comparison, use the archive as an
external system-prompt directory and keep the song brief and seeds fixed.

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
sources. Cover tests also check selective SheetSage2 loading, source-title
enforcement, unchanged ABC conditioning and transcription mode consistency.
The native frontend's audio-upload widget code was used to reproduce and verify
the Cover source preview fix. Full GPU generation,
audible quality and actual browser interaction require a host acceptance run.
No audio-quality or VRAM benchmark is claimed by these software checks.
