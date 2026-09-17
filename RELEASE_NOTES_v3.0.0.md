# Release Notes – v3.0.0

Release date: 2026-09-16

## YuE2 cover versions: bring your own audio

The major addition in 3.0 is the first **YuE2 Cover** workflow. Open
`Yue2_MM3_Production_Toolkit.json`, choose YuE2 Cover in CHOOSE, upload a track
in SOURCE AUDIO and describe how you want to reinterpret it.

SheetSage2 transcribes the source into **ABC notation**, a readable text score.
That score informs the LLM's cover prompt: its Style arrangement and Lyrics
sections are planned with the source's musical phrases in view. The original
transcription also passes directly to YuE2, without generating a replacement
ABC score. This is the toolkit's first use of an open musical description to
adapt a cover prompt; more ABC-based ideas are in preparation.

## Integrated production controls

- Three choices: **YuE2**, **YuE2 Cover**, **MiniMax Music 3**. Ordinary YuE2
  remains the initial selection. All use the existing production/export chain.
- **Full** source mode conditions on melody and harmony; **melody** gives the
  accompaniment more freedom. The same source mode drives transcription and
  generation. Full is the default, matching new-song YuE2 settings.
- **SheetSage2 BF16 autoload**, enabled for cover mode in the selected-model
  check, downloads missing configured weights to `models/audio_encoders`.
  New-song modes do not load it. `auto_download` remains independently switchable.
- YuE2 cover defaults: **40 steps**, **360-second duration ceiling**,
  **yue2_3b_bf16.safetensors**, Refinement off, Mastering and artwork on.
- A source named `My Song.wav` becomes **My Song-cover**. The parser enforces
  this title across tags, output paths, artwork metadata, JSON and prompt reports.
  Existing album prefixes, filename sanitization and collision rules still apply.
- The generation record retains source identity, encoder, mode and original ABC.
  The artwork switch controls images independently of the audio-cover mode.

SheetSage2 extracts musical notation, not sung lyric words. Supply desired lyrics,
ask for new lyrics, or choose instrumental. Source fidelity, stylistic change
and duration depend on the model and settings; this is an initial cover implementation.
If a cloud LLM is selected, the brief includes source filename and ABC notation.

## Better YuE2 arrangements

Length is now carried through the whole YuE2 path. The structured Length field
adds an approximate target (the midpoint for ranges) to the shared Style/Lyrics
plan. Both ABC planning and final music generation receive the same timed Style,
with explicit instructions to finish phrases, the final cadence and decay naturally.
**Length never becomes a cutoff.** A one-minute request can produce a 68-second
song; `yue2_max_duration` remains the separate maximum (360 seconds by default).
The parser and generation record retain the request, configured maximum and
measured result. YuE2 can still finish early; no silence, repeated audio, time
stretching or target-time cropping is added. Cover ABC remains unchanged.

All twelve YuE2 system prompts now request a developed chronological Style
arrangement, with matching Lyrics section tags in the same order and number.
Motifs, instruments, dynamics and transitions should evolve across the track,
including instrumental songs. Compact and sparse variants retain a complete
structure. Instrumental Lyrics remains tag-only; any explicitly requested
background humming is described in Style.

The previous prompts are preserved unchanged in `prompts/YuE2-old/` for
comparison. Reload the new workflow or reselect a system-prompt file to replace
the prompt text saved in an older node.

## Fixes and compatibility

- Fixed the initial Cover source frontend error that displayed a red node with
  UNKNOWN inputs. Native audio upload now has its required preview widget.
- Added source and score inputs without renaming existing node classes or output
  sockets. The classic MiniMax and Audio Enhancement Lab workflows remain available.
- Existing 2.6 features carry forward: independent stage switches, Windows-readable
  lyric reports, twelve compressor presets plus Custom and selected-model downloads.

Update the complete toolkit, including `web/`, restart ComfyUI, refresh the
browser and load the 3.0 main workflow. Keep personal workflow copies: they are
not overwritten automatically. The host needs native YuE2 generation nodes plus
`AudioEncoderLoader` and `SheetSage2AudioToABC`. No model weights are bundled.
See [setup and usage](docs/YUE2.md) and [installation](INSTALLATION.md).

## Verification

Release preparation validates node registration/contracts, all workflow links,
model/stage switching, source-title propagation, selective model downloads,
prompt structures, frontend behavior and archive privacy. Native ComfyUI CPU
checks exercised transcription output handling and stage bypass with stand-in
models. The audio-upload fix was reproduced and checked using the installed
frontend's actual widget code. These checks are not audio-quality benchmarks.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v3.0.0.zip`
- `Yue2_MM3_Production_Toolkit_v3.0.0.json`
- `MiniMax_Music3_Production_Toolkit_v3.0.0.json`
- `MiniMax_Music3_Production_Toolkit_AudioEnhance_v3.0.0.json`
- `SHA256SUMS.txt`
