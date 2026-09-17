# Changelog

All notable changes to this project will be documented here. The project follows Semantic Versioning.

## [3.1.0] - 2026-09-18

- **Added the instrumental vocal check (opt-in).** YuE2 can add vocal-like material to an
  instrumental even though the score carries no vocal notes, so the toolkit now transcribes its
  own raw output with the Whisper engine it already ships and counts the words. A take that still
  contains words is re-rendered, up to the configured number of retries (0-10); when no take reaches
  the tolerance the take with the fewest recognised words is used, the words Whisper heard are
  logged per take, and the losing candidate files are deleted, so an unattended run always ends with
  the best audio it produced. Three new settings on the music settings node: `instrumental_check`,
  `instrumental_word_tolerance` (words, not letters) and `instrumental_max_retries`. The check runs
  on the freshly decoded song, before refinement, EQ, mastering and encoding, and only for a YuE2
  instrumental cover. The retry loop is built into the generation expansion with lazy inputs, so a
  clean first take costs one generation rather than eleven. The result is stored as
  `instrumental_check_result` in the generation record.
- **Added the source-tag reader.** `MiniMaxAudioTagReader` reads an existing audio file's title,
  artist, album, album artist, year, track, genre, comment and composer, plus its embedded cover
  art, so an enhanced export carries the same metadata as the original. The source file's own tags
  win; the optional override input only fills the fields the source lacks.
- **Consolidated the example workflows into two.** `Music_Production_Toolkit.json` (the former
  Cover Studio workflow) is the main workflow and covers YuE2, YuE2 Cover and MiniMax Music 3.
  `Music_Production_AudioEnhance.json` replaces the audio-enhancement example and now carries every
  enhancement stage of the main workflow: the experimental artifact reduction, the refinement and
  mastering bypass gates, the MP3 release saver and the source-tag reader. The Yue2 and MiniMax-only
  workflows were strict subsets of the main workflow and were removed.
- **Fixed the layout of the consolidated workflows.** Every node sits inside exactly one group and
  no two nodes overlap, so the canvas stays readable; the rebuilt enhancement chain was also
  verified acyclic.

- **Fixed, from the real instrumental logs: the identity text fed the engine the
  model's scheduling text instead of the musical identity.** The Style of a real
  run starts with "Target duration: 270 seconds; requested range ... follow the
  supplied ABC phrase order and tempo ... the source score may end earlier", and
  the 400-character identity budget was spent before the sentence that actually
  names the music. That is echoed instruction, not style, and it occupied the
  most prominent position in the text the engine receives. Scheduling and
  score-supervision sentences are now rejected, so the identity begins with the
  music (verified against the user's own Style text).
- **Fixed, from the same logs: instrumental covers handed the engine a lyrics
  field that said `[Chorus]`.** The bundled instrumentals instruction explicitly
  forbids vocal-oriented section tags and prescribes [Intro], [Instrumental],
  [Bridge], [Solo] and [Outro]; the compiled text did the opposite. Verse,
  Pre-Chorus and Chorus labels now become `[Instrumental]` in the Style arc and
  in the Lyrics field alike, so the two stay one-to-one. The source labels remain
  in `cover_conditioning.section_tag_map` and in the prompt report.
- **Recorded the remaining structural lever.** All 17 instrumental runs in the
  user's log used `full` conditioning, which asks the engine for melody and
  harmony from a score whose vocal part is empty by design. `cover_conditioning`
  now records `cot_mode` and a `mode_note` stating that the upstream cover guide
  prescribes `melody` conditioning for a stylistic cover. The mode is the user's
  choice on the source node, so it is reported, not overridden.
- Verified in the same logs: the score that reached YuE2 carried **zero** vocal
  notes in every case, so a voice that is still audible is model behaviour, not
  unmuted score content.
- **Fixed: more freedom used to reduce how much of the selected template reached the
  result.** Two couplings caused it. (a) The studio applied the chord-free
  `melody_only` reduction at every freedom above 20, including `full` covers -
  which declare "melody and harmony" - so the engine was handed a score without
  harmony and filled the gap with its own priors. `melody_only` now follows the
  decode mode: a `melody` cover gets the chord-free score from the arrangement
  band upward, a `full` cover always keeps its chords, the report explains which
  applies, and an explicit override that would break the mode contract is refused
  with a message. (b) An instrumental cover replaced the whole Style with a
  bounded tag list, so most of the template's character words never reached the
  model. The instrumental text channel now leads with the Style's own identity
  sentence, hazard-filtered so no singer, language, duration instruction or
  narrative can travel, followed by the tag list, the section arc and an explicit
  "instrumental only" rule.
- **Added the style-priority contract.** The freedom permissions are now stated
  as applying to the source material only - in the cover instruction the prompt
  node sends, in the planner brief and its JSON payload, and in the transformer
  role file. A higher freedom value means that less of the source survives, never
  that less of the requested style is delivered. A test runs the whole chain at
  freedom 0/25/50/75/100 and asserts the style and lyrics that reach the engine
  are identical while the score still changes.
- **Fixed: the Cover Studio example could not be loaded in the browser.** The
  added note node had no `properties` object, which the frontend's zod schema
  rejects. A regression test now requires that key on every node in the file.
- **Fixed: "faithful cover" was not faithful.** At the low end of the slider the
  guard only checked the structure and the tempo, so a model score could still
  rewrite every note and chord and be accepted. The comparison now reports each
  element separately and the profile rejects a change to any element it pins: at
  Interpretation Freedom 0 a rewritten note, chord, bar or tempo falls back to
  the unchanged source score.
- **Added a lyrics lock.** The words no longer follow the slider. The plan node
  gains `lyrics_policy` (`auto` / `keep source words` / `keep supplied words`)
  and `supplied_lyrics`; the apply node gains the `locked_lyrics` output. The
  parser gains an appended optional `cover_lyrics_lock` input that uses the
  block verbatim and marks it as an intentional user decision, so the
  "new lyrics copied the source" guard does not fire on a deliberate lock.
  Impossible combinations (a lock on an instrumental cover, supplied words in
  original-lyrics mode, a missing transcription) are refused with a clear
  message. The lyrics/melody fit is still reported, so locked words that no
  longer fit a strongly reworked melody are visible.
- **Fixed: a missing artwork file aborted the audio export.** A finished render
  was lost with `cover image not found` when the image was no longer at the path
  the artwork node reported. The saver now writes the audio without embedded
  artwork and logs a warning; the small `_load_cover_bytes` helper still fails
  closed for direct callers.
- **Clarified `lead_instrument`.** It is implemented: the notes that carried the
  vocals move into the native `Ins` part unchanged, `Vocal` keeps its harmony
  and becomes rests, and the instrument name travels in the `Style` YuE2
  receives. It is deliberately not written into the score header, because the
  official checker requires the native `Vocal`/`Ins` definitions. New tests pin
  both halves.
- Added the **YuE2 Cover Studio** as a separate, additive cover path (three new
  nodes). It is an optional stage, and existing saved workflows keep loading and
  running: the nodes they use keep their inputs, their order and their defaults.
- Added the **Interpretation Freedom** slider (0-100). It is a toolkit
  abstraction, never a YuE2 parameter: it produces a structured profile that
  drives what is preserved, what may be reworked, whether the score becomes a
  chord-free melody line, an exact transposition and an exact tempo rewrite.
  Explicit `auto`/`yes`/`no` (and `none`/`low`/`moderate`/`high`) user settings
  always override the automatic value.
- Added a cover plan stage: the planner lists what it preserves and what it
  changes before any score edit, contradictions with the profile are recorded,
  and the plan is stored with the debug report.
- Added a validation layer for every model-produced score: ABC extraction from
  chatty answers, header and structure checks against the bounded native
  dialect, prose and fence rejection, empty-voice-block detection and an
  invariant comparison with the score the model received. Invalid scores are
  rejected, one optional repair is tried, then the validated deterministic
  result is used. YuE2 never receives unvalidated model output.
- Added an explicit local ABC reference
  (`docs/references/YUE2_ABC_COVER_RULES.md`) that is injected into every
  ABC-related prompt automatically, distilled from the verified upstream
  snapshot already pinned in `docs/references/`.
- Added a deterministic, verified transposition (key and every sounding pitch
  shift together; accidentals are re-spelled against the target key with the
  minimum the dialect allows) and a lyrics/melody fit report per section.
- The parser's additive `cover_lyrics_lock` socket was appended to the workflows
  and the link indexes were re-derived, so the frontend migration stays a no-op and
  no stored slot moves.

- **One install command now covers every documented feature.** `requirements.txt`
  contains the Whisper engine, so a fresh environment has no missing dependency for
  the cover lyrics modes or the instrumental vocal check. The installation guide lists
  the minimal install without Whisper, and the toolkit prints one line per missing
  engine at load time with the exact command that fixes it (a missing *required*
  package is logged as a warning). A verified fresh-environment resolution installs
  31 packages without touching the installed PyTorch stack.
- **Cover instructions now have exactly one owner each**, audited end to end and
  documented in the tooltips, the node descriptions and the cover guide:
  `Song request · template & fields` is the master for the style and the musical
  fields (resolution: explicit value > prompt-file metadata > omitted), the Cover
  Studio owns only how the source material is reworked, and the cover lyrics mode
  owns the words. An inherited **Lyrics theme** is now removed from the brief for
  instrumental and original-lyrics covers - it used to stay in and invited the
  model to write words that must not exist - and the Whisper-detected language is
  written in the same capitalised form as the curated language field.
  `structured_summary_json` reports `cover_mode_removed_fields`, and the studio's
  `target_style` is documented (and worded in both prompts) as a hint for the
  rework rather than a second style source.
- **The standard cover lyrics mode is now `instrumental`.** It needs no Whisper engine
  and no transcription, so a fresh installation produces a cover out of the box; the
  node default, the fallback for payloads without a mode and the bundled workflow all
  agree. A missing or legacy `lyrics_mode` therefore resolves to instrumental now.
- **New node `Style hint · template or text`:** the supported way to give the Cover
  Studio the requested style. The master node consumes the studio's rewritten score,
  so it is downstream of the studio and can never feed it - that link is a dependency
  cycle. This node reads the same prompt template (or typed text) from outside the
  studio's chain and feeds `target_style`; the bundled workflow wires it that way. Its
  cache key covers the resolved text, so an edited hint or a changed template re-runs
  the studio.
- The style hint now **behaves exactly like the structured prompt node**: its three
  selection widgets carry the same names, the grouped/indented dropdown is built by
  the same shared frontend code (moved to `prompt_ui_utils.js` so the two nodes cannot
  drift apart again), and selecting a template copies its text into `style_text` -
  only the body, without the front-matter block. Its output feeds `target_style` on the
  studio, and only that: the master's `description_override` is filled from that node's
  **own** template selection, so the two nodes keep separate dropdowns and a style hint
  can never rewrite the description the LLM receives.
- The "YuE2 Cover Studio" note now uses the same colours as every other note: the
  heading in the colour of the group it sits in, the body on the shared dark
  background.
- **A cyclic workflow now fails the release gate instead of failing at run time.**
  `validate_release.py` followed link endpoints but never dependencies, so a graph
  that ComfyUI rejects with `Dependency cycle detected` could pass every check and
  only break when someone queued it. The gate now reports the cycle with its path
  (`80 -> 127 -> 128 -> 129 -> 130 -> 131 -> 80`), and the studio's `target_style`
  tooltip plus the cover guide warn against the wiring that causes it: the master
  node consumes the studio's rewritten score, so it is downstream of the studio and
  cannot feed it.
- Fixed a stricter-than-useful workflow check: a workflow saved from the ComfyUI
  frontend carries the audio widget's `audioUI`/`upload` helper entries, which are
  now accepted as optional extras instead of counting as a contract drift.
- **Documentation layout:** topic guides live in `docs/` next to the GitHub Pages
  site; only the conventional files (README, CHANGELOG, INSTALLATION, TROUBLESHOOTING,
  DEVELOPMENT, PUBLISHING, contributing/conduct/security/licence, release notes) stay
  at the root. `workflow_schema.py` moved to `scripts/` with the other dev tools.
- **New tests** keep both guarantees mechanical: every relative documentation link and
  anchor resolves, the root/documentation split cannot drift, every third-party import
  is declared or has a documented fallback, and every optional engine is detected and
  named in the installation guide.
- The installation guide gained a "if something is missing, too small or too slow"
  section: what to do when VRAM or RAM is short and which levers actually help speed
  (non-local LLM, smaller model, shorter songs, no artwork, skipped stages, the cost of
  the instrumental vocal check).

- Fixed Whisper receiving display names such as English instead of language
  codes: normalize common names/casing before loading and reject unknown inputs
  early. Input errors no longer retry on CPU.
- Fixed the reported cover runs: VAD defaults off for music; strongly filtered
  sources retry without VAD, and obvious opening-only fragments stop generation.
  Requested/effective settings and attempts are retained. Whisper runs in an
  isolated cancellable worker with progress and time limits, Windows DLL discovery
  and CPU fallback; auto avoids repeatedly using a failed GPU in the same session.
  Instrumental covers compile prose to musical tags and empty lyric sections; exact native inputs are recorded.

- Added YuE2 Cover lyrics modes: new lyrics, original lyrics and instrumental,
  independent of full/melody conditioning, with mode-specific score/prompt rules.
- Corrected instrumental score handling: preserve native Vocal/Ins format,
  mute Vocal notes without losing harmony, transfer its melody into Ins and
  report overlapping instrumental notes replaced. Preserve block boundaries,
  key/meter fields and musical timing. Accompaniment-only keeps the old Ins part.
- Replaced the false one-note/one-syllable constraint with a note/phrase map,
  source words and Whisper word/segment timestamps. Both lyric-bearing cover
  modes use Whisper; new lyrics treats the transcript as a phrasing reference.
- Original lyrics uses deterministic timestamp-to-ABC placement of unchanged source
  words, repairing LLM rewrites, then verifies their complete ordered sequence.
  Native ABC validation supplies measured section boundaries; instrumental headers
  retain native names and melody conditioning explicitly strips harmony. Instrumental strips words and positive vocal
  instructions at parser/generator boundaries. Cover text is never auto-trimmed.
- Raised the parser prompt budget in the shipped main workflow from 1200 to the
  4500 default and pinned it in release validation: 35 real cover productions
  (2026-09-17) measure 610-1707 tokens for Caption+Lyrics, so the old 1200 with
  trimming off would have rejected 24 of them instead of generating a song.
  `trim_long_prompt` stays off, as cover text must never be auto-trimmed.
- Raised the example LLM budgets to `max_tokens = 24576`, `n_ctx = 37376` and
  `remote_max_tokens = 65536` on every LLM node, and replaced the exact-value
  release check with floors so they cannot shrink silently. The two values are
  sized so that even a maximum-length answer fits beside the largest measured
  prompt (36166 of 37376 tokens). The same defaults apply to a freshly added
  LLM Chat node.
- Fixed empty Whisper results and CUDA errors during lazy transcription;
  retry on CPU/int8 and release models. Added the optional engine dependency,
  pinned large-v3 catalog/autoload and production transcript/score reports.
- Corrected workflow report connections so the LLM receives time information,
  not only plain text. Updated docs, review plan and targeted regression tests.

## [3.0.1] - 2026-09-16

- Added 10 Auto-EQ and 24 manual EQ presets, plus Custom, with editable values,
  saved settings and manual Undo. Manual EQ starts Flat; two clearly named
  YuE2 Smooth highs presets soften harsh upper mids and highs.
- Unified Auto-EQ to one visible preset selector with explanations. The legacy
  target_mode stays serialized internally for compatibility. All bundled
  workflows start at Warm - gentle: 35%, maximum 2 dB, four bands, 40–16000 Hz.
- Fixed the production abort when Reference mode has no reference audio:
  warn and return unity settings, record skipped analysis, and continue.
- Added experimental AudioArtifactReduction for brief spectral outliers:
  bounded attenuation, transient protection, linked channel masks, analysis-only
  mode, removed-audio audition and candidate reports. Main workflow places it
  between Refinement and Mastering, with its own CHOOSE switch, default ON and
  Balanced sensitivity. Production JSON stores the report. No additional models
  or downloads; this heuristic cannot reliably identify AI origin or repair all
  generation artifacts.
- Consolidated all twelve 2.x release notes into RELEASE_NOTES_v2.x.md and
  corrected documentation for installation, model-aware prompts/reports,
  approximate duration targets, stage bypass and production metadata.
- Added an App-Mode concept and selectable configuration catalog as planning
  documents. An App-Mode interface is not implemented in this release.

## [3.0.0] - 2026-09-16

- Requested song length now guides a timed arrangement in all active system
  prompts. YuE2 sends the same target and synchronized Style/Lyrics to ABC and
  music generation. Length is approximate, never a cutoff: phrases and natural
  decay may finish beyond it, with the full configured maximum still available.
  Receipts record requested and actual duration without cropping the result.

- Fixed the red/UNKNOWN Cover source node: create the audio preview required by
  ComfyUI's native uploader before the upload widget is constructed. Backend
  registration alone did not detect this frontend error.

- Added **YuE2 Cover** to the main workflow: upload source audio, transcribe its
  score with native SheetSage2, then generate a cover through the existing audio,
  artwork and export pipeline. Same stage/sampler defaults as YuE2.
- Added selective SheetSage2 BF16 checking/autoload, a shared source full/melody
  mode, score-aware LLM instructions and cover provenance. Source filename plus
  `-cover` owns titles throughout tags, filenames, artwork and reports.

- Reworked all twelve YuE2 system prompts around a developed chronological
  arrangement: motif evolution, instrumental roles, harmonic/rhythmic contrast,
  transitions, purposeful returns and an ending. Style and Lyrics must share
  identical section tags, order and occurrence counts, including instrumentals.
- Removed the conflicting short-Style/short-instrumental-map instructions,
  including the structured brief override. Compact and sparse variants retain
  the complete arrangement while economizing wording or instrumentation.
- Archived the previous prompts unchanged in `prompts/YuE2-old/`; refreshed the
  bundled system-prompt text in the dual-model workflow. Reload the workflow or
  reselect the active system-prompt file to replace text saved in existing nodes.

## [2.6.0] - 2026-09-15

- Main feature: choose YuE2 or MiniMax Music 3 in the renamed
  `Yue2_MM3_Production_Toolkit.json`; YuE2 is the default.
- Central Cover (on), Refinement (model default: MiniMax on / YuE2 off) and
  Mastering (on) controls. Lazy audio/report routing skips disabled stages,
  including previews and unneeded FLUX.2 / FlashSR downloads.
- Stricter YuE2 instrumental prompts: no lyric words, vocal syllables or
  unintended voices; only explicitly requested background humming in Style.
- Release assets now include the dual-model workflow as a standalone JSON.

- Yue2 workflow defaults: 40 sampler steps, independent 360-second duration,
  BF16 checkpoint and enabled model check/download for the selected song engine.
- Release-tag comment defaults to "Generated with jplenio Music Production Toolkit".
- Prompt reports preserve lyric line breaks in Markdown and use CRLF on disk.
- Added twelve mastering presets plus Custom; Balanced - gentle glue retains
  the previous processing settings. Manual edits select Custom in the frontend.

- Added a model-selectable Yue2 production workflow with native ABC planning,
  YuE2/MiniMax generation, separate settings and twelve YuE2 prompt templates.
- Model-aware parsing, prompt reports and production records preserve Style,
  lyrics and generated ABC without using MiniMax's tokenizer for YuE2.
- The classic MiniMax workflow remains fixed to MiniMax; legacy node interfaces
  retain their widget order. See `docs/YUE2.md` for setup and validation limits.

## [2.5.2] - 2026-09-13

A bug-fix release. Nothing changes in the node interfaces, the workflow layout or
any stored setting; the generated cover and the finished song stay visible in the
workflow through the `PreviewImage` and `PreviewAudio` nodes.

### Fixed
- `TROUBLESHOOTING.md` documents the non-finite MiniMax DiT latents with the
  measured dtype decision (ComfyUI picks float16 for the fp16 DiT with no flags;
  `--bf16-unet` changes only the DiT and is VRAM-neutral, `--fp32-unet` also
  switches the FLUX.2 cover to fp32) plus the experiment order, so the remaining
  upstream failure class is not re-investigated from scratch.
- `KSamplerWithConfig` no longer repeats an identical non-finite sampling run.
  The noise follows the seed and the conditioning and weights are unchanged, so
  a second pass reproduced the same latents and only doubled the longest stage
  of the prompt (observed: two identical 8:48 sampling runs before the error).
  Non-finite latents now stop immediately with the precise remedy
  (`--fp32-unet`, a MiniMax FP32/BF16 model, or a new seed); the one retry for
  capture/CUDA-graph backend errors, where repeating after clearing the captured
  state can help, is unchanged. This restores the documented behavior
  ("invalid sampler latents stop immediately with a specific error").
- `MINIMAX_MUSIC3_RUNTIME_SAFETY=auto` now works as documented. The policy
  parser folded `auto` into `off`, which made the risky-backend branch
  (Blackwell-class CUDA or ROCm) unreachable, so the automatic mode silently did
  nothing. `off` remains the default and stays inert.
- Audio savers reject empty/non-finite audio across the entire batch before
  peak handling and encoding. NaN audio can trigger a blank SoundFile FLAC
  short-write assertion; remaining encoder assertions now include actionable
  format/library diagnostics and preserve staging-file cleanup.
- The production subgraph uses `MiniMaxSafeAudioDecode` in both normal and
  tiled branches. It checks sampler latents, decoded audio and normalization,
  with one conservative tiled retry for non-finite decoder output. Valid audio
  retains the host gain rule; sampling settings, output rates and export
  interfaces stay unchanged. No invalid samples are silently zeroed.
- Added regression coverage for bounded decoder recovery, input ownership,
  real FLAC/WAV roundtrips, batch validation and failed-export cleanup.
- Made the existing FFmpeg pipe timeout test independent of encoder speed and
  pipe backpressure, using a controlled child process that stays alive after
  consuming its input. Production FFmpeg behavior is unchanged.

## [2.5.1] - 2026-09-13

### Added
- LLM backend selection: integrated GGUF, local API servers, and cloud services.
  Presets include LM Studio, Ollama, llama.cpp, Unsloth Studio, vLLM, OpenAI,
  Claude, Gemini, DeepSeek, Qwen, MiniMax, OpenRouter and Groq, plus custom endpoints.
- Conditional LLM controls, model discovery, session-only API key entry and a
  connection setup dialog. Existing node identifiers, outputs and GGUF defaults
  remain compatible; obsolete session input wires migrate on load.
- FLUX.2 cover switch, enabled by default, wired to image execution and preflight
  downloads. Audio export continues without generated artwork when switched off.
- Provider/transport/UI/cover regression tests and `docs/LLM_PROVIDERS.md` setup guide.

### Changed
- LLM execution now uses ComfyUI's native cache invalidation to generate fresh
  text on every enabled run. Removed the session-ID helper from the example and
  the session input from the LLM; old wires migrate without disturbing other links.
- **The production workflow got a visual pass.** The LLM node is titled
  `LLM · In ComfyUI / Local app / Cloud`, its panel and the prompt-report panel
  are taller so the new controls fit, and node positions and group sizes were
  tidied. The workflow opens on the mastering chain and the artwork lane.
- The full workflow's generic LLM preflight is off: the integrated LLM downloads
  its selected GGUF on demand; external providers manage their models separately.

### Fixed
- The documentation of the FLUX.2 cover switch matches the shipped workflow
  again: it lives in `05 · ILLUSTRATE / Cover artwork` with the cover nodes it
  controls, not at the top of the start group. The layout test pins that
  placement and the two connections it feeds.
- `PreviewImage` and `PreviewAudio` are registered as ComfyUI-core node types in
  the node-ownership test.
- The FFmpeg pipe timeout test no longer races the process start (long workload
  instead of 0.2 s), so the release gate is deterministic.

## [2.5.0] - 2026-09-11

### Added
- Mastering section in both public workflows: independently switchable Auto-EQ,
  manual 8-band EQ, stereo-linked compression, LUFS targeting and true-peak limiting.
- Visual EQ editor, bounded spectral analysis and regression coverage for DSP,
  workflow connections, serialization and resource handling.
- EQ/analysis/mastering reports connected to the production JSON writer.

### Changed
- The redesigned workflows replace the previous examples under the original filenames;
  the temporary `_Optimized` copies are removed. Auto-EQ is enabled by default.
- Resampling occurs before final mastering: 44.1 kHz by default, 48 kHz selectable.
  Release Prep is resample-only in the examples; no duplicate loudness adjustment.
- Numerous improvements to model/resource management, bounded audio processing,
  model downloads, prompts, file handling and metadata, including support for
  configurations with less available memory.
- README rewritten around the two user journeys and independent mastering controls.
- Historical optimizer command now validates the canonical files without rebuilding
  from retired source graphs.

Personal saved workflows retain their settings. Reopen the bundled examples to
use the new chain/defaults; compare audio at matched loudness before publishing.

## [2.1.1] - 2026-09-09

Branding and README refresh: project icon + banner, banner at the top of the README, and an up-to-date description with exact prompt counts (239 user templates, 11 system-prompt variants).

### Added
- Branding assets `assets/branding/icon.png` (400×400) and `assets/branding/banner.png` (1680×720), wired in `pyproject.toml` as `[tool.comfy] Icon` / `Banner`.
- README banner at the very top (centered, full-width).

### Changed
- README: production system-prompt bullet mentions the **11 focus variants**; the genre-library bullet states **239 templates** (was "230+"); description kept current.

## [2.1.0] - 2026-09-09

The structured system-prompt and output-layout release: a visually separated System Prompt section in the Structured Song Prompt with file selection and an editable authoritative field, eleven bundled system-prompt focus variants, clearer output folder defaults, and removal of the dead variant-suffix inputs.

### Added
- **System Prompt section in `MiniMaxStructuredPromptV20`**: `system_prompt_source` (default `bundled_library`), `system_prompt_directory`, `system_prompt_file` (default `minimax-music3-production.txt`) and the editable `system_prompt` field, with `USER PROMPT` / `SYSTEM PROMPT` section headings styled as plain headers. Selecting a system-prompt file copies its text into `system_prompt`, which is authoritative from then on.
- **Buttons**: `Save as custom user prompt`, `Save as custom system prompt` and `Refresh prompt lists` (refreshes both libraries).
- **Backend routes**: `/minimax_music_toolkit/prompt_text` and `/minimax_music_toolkit/save_system_prompt`, plus `save_custom_system_prompt()` in `prompt_library.py`.
- **Eleven bundled system-prompt variants** in `prompts/system/`, each the full production contract plus a `## 0. PRIORITY FOCUS` section: concise, lyrics-first, instrumental-first, fantasy, genre-faithful, cinematic, dance-energy, emotional-story, minimal-sparse and fast-tempo (high BPM).
- `user_prompt_file` default in `MiniMaxStructuredPromptV20` is now `electronic/synth-pop-vocal.txt`.

### Changed
- **`MiniMaxOutputPaths` defaults**: `org-32flac/`, `highres-44flac/`, `highres-44mp3/`, `log/`; workflow, tooltips and docs updated.
- **Removed `append_variant_index` and `variant_padding`** from `MiniMaxOutputPaths` (no visible effect under `filename_mode="album - title"`).
- **`MiniMaxStructuredPromptV20` field order**: `system_prompt` after `source_name_override`; `source_name_override` moved to required.
- System prompt selection is now field-authoritative (the copied text is used); `IS_CHANGED` includes the `system_prompt` text.

### Fixed
- **Pre-2.1.0 workflow load shift**: the system-prompt reorder shifted old widget values; the load-time migration in `web/workflow_migration.js` / `web/migration_utils.js` now repairs by name and reconstructs the historical positional orders (the earlier `meter` repair is folded into the same path).
- Removed the contradictory "Caption maximum ~120 words" guidance from all system prompts.

## [2.0.5] - 2026-09-06

The time-signature and world-library release: a dedicated Time signature field in the Structured Song Prompt, the prompt library expanded from 95 to 239 world-spanning templates with Meter metadata everywhere, and a fully overhauled curated combo vocabulary.

### Added
- **Time signature (`meter`) field** in `MiniMaxStructuredPromptV20` between tempo and key: curated list (`4/4 (common time)`, `3/4 (waltz)`, `6/8`, odd meters, `changing time signatures`, `free time / rubato`) with `custom` first. The assembled prompt gets a `Time signature:` line; `IS_CHANGED`, the provenance summary, the frontend prefill and the option lists all include it. Front-matter aliases: `Meter`, `Taktart`, `Time signature`, `Signature`.
- **Prompt library expanded to 239 templates across 31 categories**: new `blues`, `cinematic`, `country`, `disco`, `gospel`, `kids`, `meditation`, `musical`, `punk`, `seasonal`, `soul`, `world` categories plus dozens of new subgenres in the existing ones (drill, phonk, cloud rap, dubstep, hardstyle, big room, eurodance, future bass, goa trance, acid/french/disco house, Berlin school, vaporwave, chiptune, IDM, EBM, electro swing, bebop, cool jazz, dixieland, swing, gypsy jazz, baroque, sacred choir, string quartet, minimalism, death/black/folk/nu metal, metalcore, djent, britpop, new wave, shoegaze, garage rock, psychedelic/surf/stoney/post rock, merengue, son cubano, norteño, rocksteady, ska, enka, mandopop, gqom, soukous, …). Every template carries the canonical metadata block including Meter.
- **Overhauled curated vocabulary**: genre list spans the full world map; voice list adds character/age/mood variants, ensembles, choirs, rap flows, operatic/baritone/falsetto, screamed/growled vocals, vocoder and spoken word; language list adds ~50 languages plus regional variants and special cases; key list reordered to circle of fifths starting with the minor keys.
- **Consistency tests for meter**: canonical field order including `meter`, curated time-signature values, and the no-duplication rule extended to numeric time signatures in descriptions.

### Changed
- Key combo order: minor keys first (`A minor … D minor`, then `C major … F major`).
- Both example workflows carry `workflow_version: 2.0.5`; the production workflow's Structured Song Prompt includes the new `meter` widget (default `custom`).
- All prompt descriptions cleaned so the free text never repeats a selectable field value; two new ambient templates gained their missing Meter metadata.

### Fixed
- **Pre-2.0.5 workflow load shift**: inserting `meter` between tempo and key shifted every following widget value on load (ComfyUI applies the positional `widgets_values` slot by slot). A load-time migration repair in `web/workflow_migration.js` / `web/migration_utils.js` (unit-tested) now re-aligns pre-2.0.5 serializations: named values are re-applied by name with `meter` = `custom`, positional-only files get `custom` inserted at the meter slot, and the stored serialization is kept in the new shape.
- Prompt-library consistency tests now pass over all 239 templates (field duplication in descriptions removed).

## [2.0.4] - 2026-09-05

The "fields that feel right" release: a curated tempo range list, circle-of-fifths keys, a wordless-vocal lyrics mode, more languages, log progress bars, the MiniMax prompt as an `.md` file, and the unified world-spanning prompt library.

### Added
- **Curated tempo range list** in `MiniMaxStructuredPromptV20`: `custom` first, then sensible BPM ranges (Slow 40-70 / Laid-back 70-100 / Midtempo 100-120 / Dancefloor 120-130 / Uptempo 130-145 / Fast 145-175 / Very fast 175-200 BPM). All 24 prompt files with Tempo metadata use the matching range; consistency tests enforce range-only Tempo values.
- **`only voice - no words` lyrics mode** (yes / sparse / only voice - no words / instrumental) with normalization for `wordless`, `vocalise`, `vocalese`, `scat`, `humming`, `no words`.
- **Circle-of-fifths key list** (C major … F major, then A minor … D minor).
- **More languages**: important languages first, then 25 additional languages in alphabetical order (Arabic … Vietnamese, incl. Hindi in the important set).
- **MiniMax prompt report as Markdown file**: `MiniMaxSaveProductionJSON` gained the optional `minimax_prompt_md` input; wired to `MiniMaxPromptReport` it writes `Album - Title.md` next to the canonical JSON (same basename, atomic) and records it in `outputs.prompt_report`. Bundled workflow wired (link 259).
- **Audio Enhancement Lab workflow**: a second public example workflow (`MiniMax_Music3_Production_Toolkit_AudioEnhance.json`) that skips the production stage — LoadAudio → declip → FlashSR chain → release prep → tagged FLAC save — for experimenting with enhancement settings on finished songs. Generic (no pre-selected audio file), validated and shipped in the release ZIP.
- **Log progress bars**: single ASCII bar (`[##########----------]  8192/16384`, 0 left / max right) in the log for LLM streaming (~every 10% of max_tokens) and FlashSR (every 10% of chunks); replaces the per-64-token heartbeat and per-chunk lines. In-node progress bars unchanged.
- **Unified, consolidated, world-spanning prompt library**: 95 templates, one canonical format, no field duplication in the free text; near-duplicates merged; heavy metal moved to `metal/`; new `african/`, `asian/`, `european/`, `latin/`, `reggae/`, `hiphop/` categories plus modern genres (Punk, Indie, Power Metal, Psytrance, Jungle, Trap, Synth-Pop, R&B, Dub, Dancehall, Opera); curated Genre/Language lists extended.
- **Grouped prompt dropdown**: directory labels first (alphabetical), files indented beneath; labels are display-only.
- New consistency tests (`test_prompt_consistency.py`), progress-bar tests (`test_progress_utils.py`) and tempo-migration tests.

### Changed
- Log heartbeat for LLM streaming / FlashSR chunking replaced by the ASCII progress bar.
- All pre-2.0.0 release notes merged into `RELEASE_NOTES_v1.0.x.md`; the six per-version v1.0.x note files were removed.
- Bundled example workflow carries the user's audio-preset edits and the new `minimax_prompt_md` wiring.

### Fixed
- The smoke-test workflow converter (`scripts/comfyui_smoke_test.py`) now reads widget values from `widgets_values_named`; the positional list interleaves seed `control_after_generate` values and previously broke API validation (`main_gpu`, `tempo`).

## [2.0.3] - 2026-09-05

Full-freedom prompt release: a `custom` choice in the Structured Song Prompt's file dropdown, refined audio presets in the example workflow, and a rewritten, welcoming README.

### Added
- **`custom` free mode in `MiniMaxStructuredPromptV20`**: the `user_prompt_file` dropdown now starts with `custom`, which loads no prompt file and leaves every structured field exactly as the user set it (equivalent to manual mode in the backend; no file named `custom` is ever resolved).

### Changed
- Example workflow audio presets: PRE low-pass `PRE 10 kHz - strong`, FlashSR hybrid `FlashSR only`, HF Cymbal / Shimmer `Cymbal clarity` (7000 Hz start, 2.25 dB sustain reduction, -0.5 dB static HF trim).
- README rewritten in English as an attractive, non-technical introduction that explains the few-fields-in / finished-track-out experience and the new custom mode.

### Fixed
- None (additive, backward-compatible release).

## [2.0.2] - 2026-09-04

Usability and transparency release: exact MiniMax prompt report in the workflow, progress bars for FlashSR and LLM chat, and a rebuilt play-first demo page with 10 new tracks.

### Added
- **`MiniMaxPromptReport`** node: Markdown report of exactly what MiniMax Music 3 received (cleaned caption, normalized lyrics, verbatim final prompt) plus the FLUX.2 image prompt, rendered as formatted Markdown in the node; wired into the example workflow's Save Audio section.
- Progress bar for `MiniMaxFlashSRAudio` (per-chunk) and token-streaming progress for `MiniMaxLLMChat` (per-token progress bar + log heartbeat every 64 tokens, with non-streaming fallback).
- 10 new demo tracks (35 total) with covers and SoundCloud links on the GitHub Pages demo page.

### Changed
- Demo page rebuilt: single-column play-first list, small cover thumbnails, details behind "Generation details"; placeholder tags of the new batch replaced by album names (Unbreakable, System Override, Symphonic Metal, Night Maps).

### Fixed
- CI green: torch imports in the six audio modules are now tolerant (torch lives only in ComfyUI), numpy is an explicit dependency, and the CI installs the requirements before testing.
- Complete link serialization for the new node (no workflow-validation warnings on load).

## [2.0.1] - 2026-09-03

Bugfix release: the workflow can now be run repeatedly in the same ComfyUI session without VRAM exhaustion.

### Added
- Automatic LLM GPU routing on multi-GPU machines: with default settings the LLM goes to the non-default GPU with the most free VRAM; explicit `main_gpu`/split settings always win.
- Diagnostic logging around the LLM load: resident models before cleanup, aimdo VRAM usage and free VRAM per GPU after cleanup, and the owner of any remaining dynamic-VRAM staging block (which is then force-released).

### Changed
- `MiniMaxLLMUnload` returns GPU memory to the allocator pools more aggressively after closing the model (`gc.collect()`, `torch.cuda.empty_cache()`, `soft_empty_cache`).
- Clearer LLM load error message naming `n_ctx`, `n_gpu_layers`, `main_gpu` with concrete remedies.

### Fixed
- **Repeated runs hung in the integrated LLM chat and overflowed the GPU.** The previous run's dynamic-VRAM staging pages, cast buffers, CUDA-graph/prefetch workspaces and cached FlashSR runners were not released before the LLM loaded; the GGUF load then spilled into system memory and left the CUDA context broken (later MiniMax failure: `cudaErrorStreamCaptureInvalidated`). The node now frees all of these explicitly before every LLM load; models re-stage on demand. Single-GPU machines are fully supported again.

## [2.0.0] - 2026-09-02

This major release makes the example workflow self-contained, gives the prompt stage structured control, and adds first-run model auto-download. The never-published v1.0.7 documentation/demo preparation is included in this release.

### Added
- **Integrated FlashSR node** `MiniMaxFlashSRAudio` (display: *Audio Super Resolution (FlashSR, integrated)*): replaces the external `ComfyUI-Egregora-Audio-Super-Resolution` node with an identical processing behavior (48 kHz, 5.12 s chunks, 0.50 s overlap, Hann overlap-add). Missing FlashSR code/weights are auto-downloaded on first use.
- **Integrated LLM nodes** `MiniMaxLLMChat` and `MiniMaxLLMUnload`: self-contained llama-cpp-python chat (GGUF from `models/llm`, optional per-session state) replaces the external `ComfyUI-LLM-Session` nodes. No GPL code is used; failures raise clear errors instead of empty text.
- **Structured prompt control** `MiniMaxStructuredPromptV20`: dedicated Genre / Tempo / Key / Lyrics (yes/sparse/instrumental) / Language / Voice / Lyrics theme / Target length fields plus a further-description area. Prompt library files can carry an optional metadata block that prefills the fields on selection; every field can be overridden and `custom` leaves the part out of the LLM prompt. All 62 bundled prompt files are annotated.
- **Model auto-download** `MiniMaxModelAutodownload` plus declarative `models_config.json`: needed model files are checked on first use, downloaded when a URL is configured (with progress logging), and the run continues. Gated MiniMax / FLUX.2 weights without a public URL are reported with guidance.
- **LLM section can be switched off without errors**: the parser's LLM input is now optional with manual caption/lyrics/title/image-prompt fallbacks, and `LLM Chat → enabled=false` skips model loading entirely.
- **Workflow schema migration** (`workflow_schema.py` + frontend hook `web/workflow_migration.js`): pre-2.0.0 workflows that wired the parser's old input order are repaired by input name.
- Add `scripts/annotate_prompt_metadata.py` to (re-)generate prompt front-matter metadata from file paths and prompt content.
- Add `scripts/upgrade_workflow_to_v2.py` documenting the v1→v2 example workflow transformation.
- Add `DEVELOPMENT.md` with public contributor/maintainer rules for node compatibility, serialized workflow safety, validation and releases.
- Add `scripts/update_demo_catalog.py` to safely extract public GitHub Pages demo metadata from production JSON while preserving existing SoundCloud URLs.
- Add demo-catalog regression tests and release validation for unique track IDs/orders, cover availability and SoundCloud URL shape.
- Local-only `docs/KONTEXT.md` hand-off context is excluded from Git, the Comfy Registry and release ZIPs by validator-guarded rules.

### Changed
- The bundled example workflow uses only toolkit and ComfyUI-core nodes (external LLM Session / Egregora nodes removed).
- **FlashSR inference code is now bundled** in `flashsr_inference/` (vendored from FlashSR_Inference + TorchJaekwon, with attribution in `flashsr_inference/NOTICE.md`). No code is downloaded into the models directory anymore; only the three FlashSR weights are fetched on first use. `models_config.json` no longer contains code-download entries (config version 2).
- **Example workflow simplified**: the shared `FlashSRProcessingSettings` node and the `MiniMaxSongMetadata` node were removed. The PRE/POST low-pass values live directly on the two low-pass nodes, and `metadata_json` became an optional input of `MiniMaxSaveProductionJSON` (old saved workflows are repaired by name via `workflow_schema.migrate_workflow` and the frontend migration hook).
- **Complete generation record in the production JSON** (schema `minimax_music3_production_metadata_v7`, auto-migrated from v6): the canonical JSON now contains the LLM system/user prompt, the raw LLM output and status, the structured-prompt summary, the parsed Caption/Lyrics/Title/Image_Prompt with provenance and seeds, the MiniMax generation settings and every audio-enhancement report (declip, PRE/POST low-pass, FlashSR, hybrid crossover, HF repair, release prep) plus the written files - enough to recreate a song from the JSON alone.
- **Prompt library fully normalized**: every description follows the new structure; song lengths and BPM values no longer appear in the free text (they live in the metadata block), the missing `Length` entries were added, and `scripts/normalize_prompt_descriptions.py` keeps the library consistent (idempotent).
- **Consistent logging**: the integrated LLM node logs model load, environment and the full assistant output while llama.cpp runs with `verbose=False`; FlashSR's vendored import noise and per-chunk tqdm bars are suppressed in favor of the toolkit's own log lines.
- **Cover-prompt fix**: leaked LLM planning text no longer pollutes the FLUX cover prompt - the parser restarts a section on every repeated top-level header (last occurrence wins), the system prompt forbids any output outside the four sections, and the parser appends the standard text-free prohibition whenever the image prompt lacks it.
- **Full LM Studio-style LLM node**: `MiniMaxLLMChat` now exposes temperature, top_k, top_p, min_p, repeat/presence/frequency penalty, seed, a chat-format selector (auto = verified per model family: chatml for Qwen-style, embedded template for Gemma), a thinking toggle (reasoning is split off, logged and recorded separately in `llm.thinking`) and multi-GPU controls (split_mode layer/row, tensor_split including `even`, main_gpu, tensor_parallel when the backend supports it). Verified end-to-end with Qwen3.8-27B and Gemma 4; parameter passing is gated by API introspection so older llama-cpp-python versions keep working.
- **Save as custom prompt**: a button on `MiniMaxStructuredPromptV20` stores the current field values + description into the prompt library's `_custom/` folder (name prompt included); manual mode saves into the bundled library and switches to it. `custom` fields now always mean "no specification" - they no longer fall back to the file's metadata.
- **Workflow documentation**: six MarkdownNote nodes explain every section (Prompt & LLM, FLUX.2, MiniMax, Audio Enhancement, Save & Release) plus a Models & Folders note with the required model files and their directory structure.
- **`MiniMaxMetadataLoader` removed from the example workflow** (it belongs in a future separate song-restore workflow; the node class stays registered and reads the same schema).
- **Song length limited to 5 minutes**: the Length combo offers shorter options (`30 seconds` up to `4-5 minutes`), two prompt files with longer metadata were corrected, and the bundled system prompt now caps every request at 5:00 (the MiniMax generation settings already used `max_duration` 300 s).
- **Artwork size presets** now include `1536x1536`, `2048x2048`, `3072x3072` and `3096x3096` (the FLUX.2 latent stage quantizes to multiples of 16, so 3096 renders as 3088 - prefer 3072).
- `MiniMaxParseExternalLLMOutputV16` now accepts an optional LLM output plus manual fallback fields and an `llm_status` input (wired to the LLM chat node's status output); provenance records whether LLM or manual values were used. A decorated `[Count]` value no longer fails the run - the first integer is extracted, clamped to 1-100 and warned about instead.
- Selecting a prompt file in `MiniMaxStructuredPromptV20` copies the file's body text into `description_override`, which is authoritative from then on; editing it invalidates the cache even in file mode. Combo option lists ship with a curated vocabulary merged with library values.
- Windows filename hardening: reserved device names (`CON`, `NUL`, `COM1`, …) are neutralized, trailing dots/spaces stripped and over-long titles truncated.
- Expand the GitHub Pages demo catalog from 17 to 25 tracks and include the eight new supplied cover images.
- Improve display labels for prompt-slug-based new demo collections/genres.
- Make `scripts/prepare_demo_covers.py` derive its expected cover list dynamically from `docs/demo-tracks.js`.
- Refresh README, audio examples, troubleshooting, development and publishing documentation.
- Remove transient `Refresh prompt lists` UI state from the bundled example workflow metadata.

### Maintainer tooling
- `scripts/toolkit_diagnostics.py` — self-diagnostics report (Python, FFmpeg, packages, LLM stack, model targets, prompt library).
- `scripts/preview_output_paths.py` — non-writing preview of the five output paths a run would produce, including collision resolution.
- `scripts/bump_version.py` — version bump across VERSION / `pyproject.toml` / `project_info.py` / `CITATION.cff` / example workflow metadata, with a release-notes skeleton.
- `scripts/package_release.py --dry-run` — release contents summary without creating assets.
- New regression suites: node schema snapshot for every toolkit node in the bundled workflow, Windows filename edge tests, LLM failure-propagation tests, release-tooling tests (129 unit tests total).
- LLM environment facts (llama-cpp-python version, GGUF inventory, model directories) are logged once per run for failure diagnostics.

### Maintainer notes
- Runtime node behavior of the audio chain (declip, low-pass, hybrid crossover, HF repair, release prep) remains unchanged; only the FlashSR/LLM node wrappers were replaced, with identical processing parameters.
- New demo entries may keep an empty `soundcloudUrl` until their SoundCloud uploads are published.
- v1.0.7 was never published; its prepared changes are released as part of 2.0.0.

## [1.0.6] - 2026-09-01

### Fixed
- Fixed the serialized `Save Image Smart Prefix` input-slot order in the bundled workflow. The v1.0.5 workflow could map widget values to the wrong inputs after `title` and `audio_tags_json` were added, producing validation errors for `collision_mode` and `jpeg_quality`.
- Added release validation and unit coverage for the artwork saver input order and widget types so this class of workflow-serialization regression is caught before packaging.
- Hardened `scripts/build_public_workflow.py` to normalize artwork-saver slots and repair linked target-slot indices automatically.

### Included
- Preserves the expanded bundled prompt library supplied for this release (62 user prompt files across additional rock, metal, EDM, house, electronic and alternative styles).
- Preserves the SoundCloud demo-page configuration and demo links already present in the repository.

## [1.0.5] - 2026-09-01

### Fixed
- Make generated cover JPGs use the same `Album - Title` basename as original FLAC, release FLAC, release MP3 and the canonical production JSON.
- Prevent prompt-library source names such as `nordic-folk-vocal` from leaking into the final artwork filename when `album - title` naming is selected.

### Changed
- Add `title`, `audio_tags_json` and `filename_mode` inputs to `Save Image Smart Prefix`.
- Share one filename-building helper across audio, artwork and centralized JSON output to keep cross-format names consistent.
- Keep the bundled, user-tested local-LLM example values at `max_tokens = 16384` and `n_ctx = 32768`.
- Ship the prepared SoundCloud demo playlist/track URLs in the GitHub Pages configuration.
- Refresh artwork, workflow, installation, demo and publishing documentation.

## [1.0.4] - 2026-09-01

### Added
- Add a dedicated `configuration_subdir` output path (default `json/`).
- Add `Save Production JSON`, which writes one canonical per-song JSON after the original audio, release FLAC, release MP3, and cover artwork have been saved.
- Add machine-readable `save_info_json` output to `Save Audio Smart Prefix` so the final JSON records actual file paths, sample rate, format, save peak/gain, filename mode, and embedded-cover size.
- Add a GitHub Pages SoundCloud demo template under `docs/` with editable track URL placeholders.

### Changed
- Set the example local LLM `max_tokens` to 14000.
- Stop writing duplicated JSON sidecars beside each audio output in the v1.0.4 example workflow; legacy sidecar support remains available for backward compatibility.
- Rewrite and expand README, installation, workflow, audio-pipeline, artwork, audio-example, troubleshooting, and node documentation.

## [1.0.3] - 2026-09-01

### Changed
- Refresh the public example workflow layout using the user-tested ComfyUI arrangement.
- Simplify visible node titles and remove two redundant explanatory note nodes for a cleaner canvas.
- Keep the optional saved-configuration loader bypassed in the example workflow.
- Preserve all MiniMax Music 3, FlashSR, restoration, release-prep, artwork, metadata, and output processing values.
- Keep the repaired MiniMax Music 3 subgraph boundary links introduced in 1.0.1.
- Remove the transient serialized `Refresh prompt lists` button state; the frontend extension recreates the button at runtime.

## [1.0.1] - 2026-08-31

### Fixed
- Preserve MiniMax Music 3 subgraph boundary links while sanitizing the public example workflow.
- Fix ComfyUI `No link found in parent graph ... unet_name` and equivalent missing subgraph-input/output link errors.
- Extend release validation and unit tests to verify subgraph boundary links, child-node links, and parent/definition input alignment.
- Make public-workflow version metadata follow `VERSION` automatically.

## [1.0.0] - 2026-08-31

### Added
- Public release of **MiniMax Music Production Toolkit**.
- File-backed user/system prompt libraries with bundled examples and external-directory support.
- Dynamic prompt-file dropdowns and refresh control in ComfyUI.
- Cache fingerprinting for file-backed prompts so edits are detected without renaming files.
- Structured external-LLM parser for Caption, Lyrics, Title and Image Prompt.
- LLM session-ID/cache-buster helper without extra utility-node dependencies.
- MiniMax generation settings, output paths, standard audio tags and reproducibility JSON.
- Source declipping, FlashSR pre/post filtering, hybrid original/FlashSR crossover, HF shimmer/cymbal repair.
- High-quality 44.1/48 kHz release SRC plus static full-program LUFS/true-peak targeting.
- FLAC/MP3/WAV saving, Album - Title filename mode and configurable embedded cover size.
- FLUX.2 square-cover helpers and smart JPEG saving.
- Input tooltips for every toolkit node and built-in ComfyUI node help pages.
- Sanitized example workflow and bundled genre prompt library.
- CI validation and Comfy Registry publishing workflow.
