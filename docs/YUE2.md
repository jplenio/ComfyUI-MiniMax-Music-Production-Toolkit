# MiniMax and YuE2 song production

Open `example_workflows/Music_Production_Toolkit.json`. Its first control,
**00 · CHOOSE / Song model**, selects **YuE2** (the example default), **YuE2 Cover** or **MiniMax Music 3**.
This switches the actual generator as well as prompt templates and settings.
The classic `Music_Production_Toolkit.json` remains a fixed MiniMax
workflow for existing users.

## Start a song

1. Choose the song model and the production stages in **CHOOSE**:

   | Choice | Default | Behavior |
   | --- | --- | --- |
   | Model | YuE2 | Switches generator, prompt family and active sampler settings. |
   | Cover | On | Controls rendering, preview, cover file and FLUX.2 model checks/downloads. |
   | Refinement | Model default | MiniMax: on. YuE2: off. Choose On or Off for a fixed override. |
   | Mastering | On | Controls Auto-EQ, manual EQ, release sample rate and compressor. |
   | Artifact reduction | On (Balanced) | Experimental spectral outlier attenuation after Refinement, before Mastering; independent of both. |

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
and HF repair, and sends generation through Balanced artifact reduction to mastering. This saves the time
and model loading required for restoration. Refinement remains available for
tracks that benefit from it. When Mastering is off, release files receive the
incoming audio at its existing sample rate. Original generation is always saved;
the saver's configured peak handling still applies. Keeping artifact reduction
off and disabling Refinement and Mastering
passes generation straight to the release savers.

Enable `artifact_reduction_enabled` to audition the new **CLEAN** stage for
brief metallic/whistling outliers. Analyze-only mode, candidate reports and
removed-audio audition help assess it; wanted high notes can also trigger it.
See [artifact reduction](ARTIFACT_REDUCTION.md) for research and limitations.

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
2. Choose what happens to the vocals. **Cover lyrics** has three settings:

   | Setting | What it does |
   | --- | --- |
   | `new lyrics` | The LLM writes new words that fit the transcribed melody: same sections, using timed original phrases and the score as approximate guidance. Needs the Whisper engine. |
   | `original lyrics` | Whisper transcribes the original sung words and the LLM only distributes that text across the score. Needs the optional Whisper engine. |
   | `instrumental` | The score is rewritten so the vocal melody line is played by an instrument; Lyrics carries section tags only. Default: needs no Whisper engine. |

   For `instrumental`, **Lead instrument** picks which instrument takes over the
   former vocal line (or `Remove vocal line (accompaniment only)`). See
   [Cover lyrics modes](#cover-lyrics-modes) below.
3. Select the source mode: **full** retains melody and harmony and matches the
   normal YuE2 default; **melody** allows a different harmonic accompaniment.
   The official cover guide recommends melody conditioning for stylistic covers.
   This source setting controls both SheetSage2 and YuE2; the separate
   `yue2_mode` field applies only to new-song generation.
4. Describe the desired instrumentation, genre and development in WRITE.
   SheetSage2 transcribes the musical score before the LLM runs. The cover
   instructions ask for a detailed Style arrangement matched to that score,
   with synchronized Lyrics sections. They are added to any selected YuE2
   system template. The score passes to YuE2 through the score node; there is
   no new Generate ABC step.
5. Leave `sheetsage2_models`, `yue2_models` and `auto_download` enabled in
   **Selected song / artwork / FlashSR model check** to download missing
   configured weights. SheetSage2 BF16 is about 1.39 GB and belongs in
   `models/audio_encoders/sheetsage2_bf16.safetensors`. It is checked only in
   YuE2 Cover mode. Custom encoder names require an installed file or a matching
   catalog entry.
6. Queue as usual. The sampler remains at 40 steps in the example, the YuE2
   duration ceiling at 360 seconds, refinement off by model default, mastering
   and cover artwork on. The artwork switch is independent of audio covers.

`My Song.wav` becomes **My Song-cover**. The parser enforces this title even if
the LLM or manual fields suggest another name. Audio tags, artwork metadata,
output-path source names, production JSON and prompt reports all use it. Existing
album prefixes, filename sanitization and collision rules still apply.

SheetSage2 does **not** transcribe sung lyrics. Supply the words you want in the
brief, use manual lyrics when bypassing the LLM, choose `original lyrics` to have
Whisper read them from the source, or choose `instrumental`. The source audio is
conditioning material, not a waveform that is mixed into the output. Duration
remains a ceiling, so long sources may need a higher limit.

### Cover lyrics modes

The source node owns two independent choices: `full` / `melody` for score
conditioning, and `new lyrics` / `original lyrics` / `instrumental` for vocals.
Only **YuE2 Cover** uses these choices. Source filename plus `-cover` still owns
the title. The central refinement, mastering and artwork switches remain independent.

**New lyrics.** The LLM writes completely new words for your selected template,
theme and language. Whisper supplies the source words with segment/word time
estimates as a phrasing reference. The LLM uses these to approximate the original
phrase lengths, syllable density, stress and breathing points. The score's
section order, note durations and rests provide additional guidance. Notes are
not syllables: a sung vowel can span several notes. The phrase map explicitly
allows these melismas. Words belong under matching section tags in `[Lyrics]`,
never in Style. A stale wordless Lyrics field is overridden; `yes`/`sparse` remain.
Legacy/custom graphs without a transcript use score-only approximate guidance
and explicitly state that the original syllable counts are unknown.

**Original lyrics.** Whisper transcribes the words. The LLM receives the measured section layout; Python
places the original words using Whisper timestamps and restores them if the LLM
rewrites, translates or drops text. The final word-order check retains repetitions
and short words. Missing timestamps use an explicitly reported source-order fallback. Empty transcription also
stops instead of inventing lyrics. Review transcription errors before relying on
the text: automatic speech recognition is not verified lyric ground truth.

**Instrumental.** This choice overrides the template, voice fields and all
conflicting vocal requests, including humming. Python converts the native
`Vocal` notes to equal-duration rests, retaining chord symbols and the two-voice
format, including the fixed native voice headers. The former sung melody moves
to `Ins`; **Lead instrument** is conveyed through Style, not renamed ABC headers.
Where both melodies overlap within a native one-to-four-bar block, the former
vocal melody replaces that block's Ins melody; the report counts those replaced
notes. Instrumental-only blocks retain their original Ins theme. Choosing
**Remove vocal line (accompaniment only)** mutes Vocal without replacing Ins.
Structure labels, bar boundaries, meter/key fields and tempo remain intact.
The LLM and generator receive the same rewritten score. The prompt report keeps
section tags for arrangement review. Native YuE2 receives a compiled musical-tag
Style and empty lyric sections, excluding narrative planning prose.
`generation.cover_conditioning` records exact native Style, Lyrics and ABC. Parser and
generator remove singable text and conflicting vocal Style clauses even if the
LLM ignored the request. This does not guarantee that YuE2's
audio realization contains no voice: listen to the result.

Install the optional engine once in ComfyUI's Python environment:

```bash
python -m pip install -r requirements-whisper.txt
```

Whisper is used for **both new and original lyrics** in the bundled cover
workflow, never for instrumental covers, ordinary YuE2 or MiniMax. Keep
`whisper_models` and `auto_download` enabled to obtain the pinned
`whisper-large-v3` CTranslate2 files (about 2.9 GB) in
`models/audio_encoders/whisper-large-v3`. Switch autoload off for manually
installed models. This remains a separate dependency from normal song generation.

The workflow passes **lyrics_report_json**, including word/segment times, to
both the Structured Song Prompt and parser. The text-only output is available
for other graphs. A reviewed plain-text transcript can also be connected to
their `cover_lyrics` inputs instead; it carries no automatic timing information.
The Production JSON stores the source transcript, phrase/score report and parser
verification. No cover mode silently trims the lyrics to satisfy a text budget.

VAD is off by default for singing. When enabled, retention below 50% or no
segments triggers a full-audio retry without VAD, recorded in the report.
An obvious opening-only fragment stops before the LLM/music generation. Set the
source language and review/correct recognition errors. Whisper now runs in a
separate cancellable process with progress and stall limits; CUDA runtime errors
retry on CPU/int8. Later `auto` runs stay on CPU after a GPU failure until restart.
Accuracy on sung material is not established by unit tests. Timing is approximate;
YuE2 exposes no forced phoneme-to-note alignment. The [faster-whisper documentation](https://github.com/SYSTRAN/faster-whisper)
describes the speech-oriented VAD and separate CTranslate2 CUDA dependencies.

See [review and implementation plan](YUE2_COVER_REVIEW.md),
[Whisper node](../web/docs/MusicCoverLyrics.md), [score node](../web/docs/MusicCoverScore.md)
and the [official cover guide](https://github.com/multimodal-art-projection/YuE/blob/main/docs/covers.md).

The [follow-up diagnostics](YUE2_COVER_DIAGNOSTICS.md) include the real reported
failures and a native-model test. Downloaded [ABC documentation](references/YUE2_ABC_REFERENCE.md)
and the [pinned ABC implementation as Markdown](references/YUE2_ABC_IMPLEMENTATION.md)
explain the native dialect. Native validation now checks sounding pitches, ties,
bar grids and compressed rests. Measured section times replace guessed numbered
Style headings; no duration target stretches or cuts the source score.

## YuE2 Cover Studio

The [example workflow](../example_workflows/Music_Production_Toolkit.json) adds an optional,
separate path in front of the cover chain. The existing MiniMax-only, YuE2-only
and combined workflows are untouched and keep working exactly as before; the
studio only ever replaces the score that already travels through the
`cover_abc` socket.

```text
Source audio
  -> SheetSage2 transcription (unchanged)
  -> Cover Studio 1 plan        -> LLM: what to keep, what to change
  -> Cover Studio 2 transform   -> LLM: the actual score edit
  -> Cover Studio 3 validate    -> structure, invariants, fallback
  -> Structured prompt + YuE2 generation (unchanged)
```

### Interpretation Freedom

```text
0 = faithful cover        50 = reinterpretation        100 = creative recomposition
```

The slider is a **toolkit abstraction and not a native YuE2 parameter**. YuE2 has
no such setting; nothing is forwarded to the engine as a number. Instead the
value produces a structured profile that decides what stays recognisable and what
may be reworked, and the stages then realise that with operations YuE2 does
understand:

| Freedom | Band | Keeps | May change |
| --- | --- | --- | --- |
| 0-20 | Faithful cover | melody, structure, harmony, tempo, key, hooks | instruments, sound design, vocal timbre |
| 21-40 | Arrangement cover | melody, chorus hook, structure, basic tempo | harmony, arrangement, instrumentation, intro/outro |
| 41-60 | Reinterpretation | central melodies, hooks, rough structure | harmony, tempo, key, rhythm, transitions |
| 61-80 | Creative reinterpretation | chorus hook, key motifs, characteristic phrases | melody shape, rhythm, section length, harmony |
| 81-95 | Loose adaptation | selected motifs, basic dramaturgy | almost everything else |
| 96-100 | Inspired recomposition | key, tempo, structure, character | compose rather than reproduce |

Two things make the slider honest rather than decorative:

- **Explicit settings always win.** Every `preserve_*` choice and `melody_only`
is tri-state (`auto` / `yes` / `no`). `auto` uses the slider; an explicit
setting overrides it. The report lists which overrides were active.
- **Only real parameters move.** The exact knobs act on the score: `key_change`
transposes, `tempo_change` rewrites `Q:`, and `melody_only` removes the chord
symbols (the chord-free melody line a `melody` cover expects). The decode mode
`cot=full` / `melody` is **not** driven by the slider - it belongs to the source
mode, because the same setting also drives the SheetSage2 transcription and the
two must not disagree.

### The slider never touches the lyrics

The words are not a musical parameter, so they do not follow the slider. At
the faithful end this is enforced, not promised: with no melody variation
allowed, a model score that rewrites a note, a chord, a bar or the tempo is
rejected and the unchanged source score is used.

For an explicit guarantee, **Lyrics policy** on the plan node locks the words:
`keep source words` places the Whisper transcription verbatim into the final
score's sections, `keep supplied words` uses your own text exactly as written,
and `auto` leaves the decision to the cover lyrics mode. The locked block
leaves the studio on the `locked_lyrics` output and reaches the parser, which
treats it as an intentional decision instead of a model that copied the source.
The report then measures the lyrics/melody fit, so it is visible when locked
words no longer sit comfortably on a strongly reworked melody.

### The slider never touches the style either

More freedom means that less of the **source material** survives. It never means
that less of the **requested style** is delivered. The slider's permissions apply
to the source only, and that is stated explicitly in the cover instruction the
prompt node sends and in both studio prompts, so a model cannot read "everything
else may be redesigned" as licence to redesign the genre.

The score and the decode mode also stay in agreement. The chord-free
melody-only reduction belongs to the `melody` decode mode, which is the mode that
expects it; a `full` cover always keeps its harmony, whatever the freedom value.
Before this, the slider removed the chords from `full` covers above 20, so the
engine was handed a "melody and harmony" score with no harmony and filled the gap
with its own priors - which is where the requested style used to get lost. The
report now says which of the two applies and why.

Instrumental covers keep the requested style too. The text YuE2 receives starts
with the Style's own identity sentence - hazard-filtered, so no singer, language
or duration instruction can travel - instead of being reduced to a bare tag list.
Its section labels follow the bundled instrumentals rule: Verse, Pre-Chorus and
Chorus become `[Instrumental]` in the Style arc and in the Lyrics field alike,
so an instrumental never hands the engine a lyrics field that says `[Chorus]`.

### Where each instruction comes from

Two nodes can describe a cover, and they do different jobs. This is the whole
precedence, and it is the same in the code, in the tooltips and in the prompts:

- **Song request · template & fields is the master for what the track sounds
  like.** Its prompt file, its fields (genre, tempo, time signature, key, lyrics,
  language, voice, lyrics theme, length) and its further description are what the
  LLM is told to produce, and the style rules it forwards - including STYLE
  PRIORITY - are what the model must follow. Each field resolves as *your explicit
  value > the prompt file's metadata block > left out*, and an explicit `custom`
  means "no specification", not "take the file's value".
- **Cover Studio owns how the source material is reworked.** The Interpretation
  Freedom slider, the preserve/variation knobs and the key/tempo changes decide
  which notes, chords, phrases and sections survive. Its `target_style` is a
  *hint for that rework*, not a second style source: leaving it empty means "no
  extra hint", and filling it must not contradict the song request.
- **The master is downstream of the studio, so the studio cannot receive its
  brief.** `Song request · template & fields` consumes the studio's rewritten
  score (it has to: the rewritten key, tempo and structure are what the final
  prompt must describe), so a link from it back into the studio is a dependency
  cycle and ComfyUI rejects the whole prompt with `Dependency cycle detected`.
  The supported way to give the studio the style anyway is the optional
  **Style hint · template or text** node: it reads the same prompt template the
  master uses (or takes typed text) from *outside* the studio's own chain. Its one
  output feeds the studio's `target_style` and nothing else - the master's
  `description_override` is filled from that node's own template selection, so the
  two keep separate dropdowns and the hint can never rewrite the description the
  LLM receives. Select the same template there that you use in *Song request* if
  you want both to work from one style definition; the master's own selection still
  decides the genre, tempo and other prefilled fields. The value remains a hint for
  the rework, the master remains the style of record, and both studio prompts say so.
- **The cover lyrics mode owns the words.** It is selected in *Cover song ·
  source audio* and it wins over every vocal field in the master node:
  - `instrumental` forces the Lyrics field to instrumental and removes Voice,
    Language and Lyrics theme from the brief. Nothing sings, hums or speaks; the
    parser strips words from the Lyrics block even if a lock arrives by wire, and
    vocal clauses are removed from the running text the engine receives.
  - `original lyrics` removes the Lyrics theme (the words are the transcription,
    not a topic) and takes the language from the Whisper transcript. The
    transcript is authoritative: word order, repetitions and omissions are
    verified, and a mismatch stops instead of generating.
  - `new lyrics` keeps theme, language and voice, because those are what the new
    words are written from. The transcript is a phrasing reference only.
- **The studio's lyrics lock is the one exception, and it is deliberate.** With
  *Lyrics policy* set to `keep source words` or `keep supplied words`, those words
  replace the LLM's words verbatim in the parser. Impossible combinations are
  refused rather than guessed: an instrumental cover has no words to keep, and
  `original lyrics` owns its words from the transcription.

The cover instruction the model receives repeats the same order, and every report
records it: `forced_lyrics_field` names a forced Lyrics value,
`cover_mode_removed_fields` lists the fields a mode took out of the brief, and
`mode_note` explains the conditioning that was used.

### When a voice still appears in an instrumental

The score is never the cause: the vocal part is muted and its melody moves into
the instrumental part, which is verified for every run. A voice that is still
audible was added by the audio model. What the toolkit can do is remove the
invitations, and `cover_conditioning` records what is left:

- the Style leads with the musical identity, not with scheduling text;
- the Lyrics field carries no vocal-oriented section tag;
- `mode_note` reports when the cover used `full` conditioning. Full mode asks the
  engine for melody **and** harmony from a score whose vocal part is empty by
  design - the one remaining structural invitation. The verified upstream cover
  guide prescribes `melody` conditioning for a stylistic cover, so if a voice
  keeps appearing, set the source mode to `melody` and compare.

### Let the toolkit listen to its own render

Because the cause is the model, the honest test is to listen - which is what the
optional **instrumental vocal check** does. It transcribes each freshly decoded
take, logs every word it heard, and compares the count with your **word
tolerance**. A take at or below the tolerance is used immediately; when no take
reaches it, the take with the **fewest recognised words** continues into the rest
of the chain and the other candidate files are deleted. Equal counts keep the
earliest take, so a stored seed stays reproducible. Up to ten retries are
allowed; a clean first take costs a single generation, because the later takes are
rendered only when the check asks for them.

Use the logged words to judge the result: a few soft syllables are a different
case from a returning chorus. Every take is written to a temporary WAV
(`<system temp>/mmt-instrumental-check/...`), the kept one stays for listening,
and the audio that continues downstream is the winner's original data. See
[the node documentation](../web/docs/MiniMaxInstrumentalPick.md).

### The three cover modes

All three lyrics modes of the ordinary cover chain are available unchanged. The
studio adds interpretation on top:

- **Instrumental.** The score is already rewritten so an instrument carries the
melodic line. The studio keeps that line recognisable and never promises
voice-free audio: if YuE2 produces vocal-like material, that is a model
limitation, not a validated property of this pipeline.
- **Original lyrics.** The transcription still owns the words. The studio only
changes the musical side, and the existing lossless word-order check keeps
applying afterwards.
- **New lyrics.** The studio reports a per-section lyrics/melody fit - note
onsets, phrase lengths, rests and the syllable density the words need - before a
render is spent. The advice prefers adjusting the words, and only allows a
stronger melody change when the freedom value actually permits it.

### The score is never trusted to the model alone

The architecture is

```text
ABC reference + structured rules + source ABC + interpretation profile
        -> LLM
        -> ABC validator
        -> YuE2
```

and not "hand the model a score and hope". Concretely:

- Every ABC-related prompt automatically carries the compact local reference
[`docs/references/YUE2_ABC_COVER_RULES.md`](references/YUE2_ABC_COVER_RULES.md),
a condensation of the verified upstream snapshot.
- The two role prompts are files too - `resources/yue2/cover-planner.txt` and
`resources/yue2/abc-transformer.txt`. Edit them and re-queue; no Python change is
needed. They deliberately do **not** live in `prompts/system/`, because that
directory is the user-facing template library offered in the prompt nodes'
dropdowns.
- The model answers with one JSON object (`abc`, `changes`, `warnings`). The
score is extracted, structurally validated against the bounded native dialect,
and compared with the score the model received.
- A score that breaks a pinned invariant (structure or tempo), fails the
structure check, or is not ABC at all is **rejected**. One optional repair
answer is tried, then the validated deterministic result is used. A bad model
answer costs reinterpretation, not the run.

At most two model calls are made (one plan, one transform, plus an optional
repair). Bypass nodes 1-2 (`Ctrl+B`) to work with the untouched score again, and
switch the studio off entirely to guarantee a byte-for-byte pass-through.

See the [plan node](../web/docs/YuE2CoverStudioPlan.md),
[transform node](../web/docs/YuE2CoverStudioTransform.md) and
[validate node](../web/docs/YuE2CoverStudioApply.md).

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

In Cover mode the source phrases take precedence over forcing an exact duration;
the requested length cannot automatically rewrite or extend the source score.
Instrumental mode mutes the vocal part and moves its melody into the instrumental
part, preserving the timeline; overlapping Ins material may be replaced as described above. The generation
record stores the target, configured limit, actual duration and difference. A
duration outside the requested range is informational, not a reason to cut, fade
or reject the audio.

### Instrumental tracks

For **Lyrics = instrumental**, all twelve templates require explicit instrumental
exclusions in Style and a Lyrics section containing only tags. The structured
brief reinforces this even when an old vocal/language selection remains set.
No lyric words, syllables, scat, spoken text or vocal hooks are permitted.
Human voices are excluded by default. Only explicitly requested background
closed-mouth humming may be described in Style, never transcribed into Lyrics.

The full [instrumental arrangement example](../prompts/examples/yue2-instrumental-arrangement.txt)
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
[`prompts/YuE2-old/`](../prompts/YuE2-old/README.md), outside the active library.
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
enforcement, transcription mode consistency, the lyrics-mode routing, the score
rewrite and its idempotence, the note/phrase map, exact original-word order, and that the Whisper
node stays inactive outside new/original-lyrics covers. The Whisper engine itself is
stubbed in those tests: no checkpoint is downloaded and no transcription quality
is claimed.
The native frontend's audio-upload widget code was used to reproduce and verify
the Cover source preview fix. Full GPU generation,
audible quality and actual browser interaction require a host acceptance run.
No audio-quality or VRAM benchmark is claimed by these software checks.
