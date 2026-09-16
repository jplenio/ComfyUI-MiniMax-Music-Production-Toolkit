# Save Production JSON

Writes **one canonical JSON file per generated song** after the workflow has finished saving the audio encodings and album artwork.

## Why this node exists

Older workflow versions could write a separate JSON sidecar beside every audio file. That duplicated the same production configuration in several folders. Since v1.0.4 the recommended workflow stores one consolidated JSON in a dedicated configuration directory (default: `log/`).

The node receives the save-information outputs from the original FLAC, release FLAC and release MP3 savers plus the saved artwork path. These connections are intentional dependencies: the JSON node cannot execute until those files have been written successfully.

## Recommended settings

- **collision_mode:** `auto_increment`
- **filename_mode:** `album - title`
- **create_directories:** `true`
- Configure the destination folder in **MiniMax Output Paths → configuration_subdir**. Default: `log`.

## What the JSON contains

The node assembles the **complete generation record** from direct inputs (no separate metadata node is needed since 2.0.0):

- the full LLM stage: system prompt, user prompt, raw LLM output and status;
- the structured-prompt summary (origin, resolved fields, overrides);
- the parsed Caption (MiniMax) or Style (YuE2), Lyrics, Title and Image_Prompt with source provenance, seeds and run/variant counters;
- the selected engine's settings: MiniMax's generation parameters, or YuE2's `song_model`, `generation` and `style`, including ABC, approximate duration target, configured ceiling and actual generated seconds;
- for YuE2 Cover, the source record, filename-derived title and original SheetSage2 ABC;
- every audio-enhancement report: de-clipping, PRE/POST low-pass, FlashSR settings, hybrid crossover, HF cymbal/shimmer repair and release preparation;
- the optional `artifact_reduction_json` report, stored under `artifact_reduction`, including effective settings, candidate timestamps and bypass/analysis status;
- (V01) the EQ / auto-EQ / mastering reports under `mastering`, the **effective** resource and LLM runtime under `runtime`, the model identity under `models` and the system-prompt template version under `llm.template_version`;
- the standard audio tags,
- original-audio / release FLAC / release MP3 save information,
- the artwork path, the configuration-file path and (since 2.0.4) the MiniMax prompt-report path.

Audio save information includes format, sample rate, peak before final file writing, any constant safety gain applied by the saver, filename mode and embedded-cover size.

These records support inspection and reconstruction of settings; they are not
a self-contained generation checkpoint. Models, source audio for covers and a
compatible runtime are still required. The legacy `MiniMaxMetadataLoader` extracts
MiniMax fields only; YuE2 Style, ABC and generation settings must be read from the
full JSON. Semantic tokens and latent arrays are not exported.

## Reproducibility and the V01 additions

Seven optional inputs were appended to the node (all `forceInput` sockets, so no
stored widget value moves): `eq_report_json`, `auto_eq_analysis_json`,
`mastering_json`, `resource_profile_json`, `llm_runtime_json`,
`model_identity_json` and `template_version`. Wire them from the corresponding
nodes when you want the record to be reproducible:

- `mastering.eq` / `mastering.auto_eq` / `mastering.chain` store the JSON reports
  the DSP nodes already emit (`minimax_eq_report_v1`,
  `minimax_auto_eq_report_v1`, `minimax_mastering_v1`) verbatim;
- `runtime.resource_profile` must describe what the run **actually used**
  (`effective`), never only what was suggested (`recommended`) - the two live in
  separate keys so they cannot be confused;
- `runtime.llm` records model, device and context; `models` records the model
  revisions/hashes; `llm.template_version` records which system-prompt template
  produced the run.

All seven are optional. Left unwired, they add no keys, so a payload written
without them is identical to what earlier versions produced and every reader of
schema `v7` keeps working - additions do not need a schema bump or a migration.

The canonical JSON beside your rendered files legitimately contains your own
paths. Before a payload is pasted into a bug report or embedded in a public
example, pass it through `production_metadata.public_safe_payload()`: it removes
secret-named keys and replaces absolute paths with `<path>/<file name>`, keeping
the processing parameters intact.

## File naming

With the recommended `album - title` mode, a song with album `Example Album` and title `Northern Light` becomes:

`log/Example Album - Northern Light.json`

Since 2.0.4 the node additionally writes the MiniMax prompt report beside the JSON with the **same basename**:

`log/Example Album - Northern Light.md`

The Markdown report (from `MiniMaxPromptReport`, connected to `minimax_prompt_md`)
contains the selected model's prompt: MiniMax's cleaned/native prompt when
available, or the actual YuE2 Style and Lyrics. Artwork is separate. Literal
Markdown blocks and CRLF file line endings preserve lyric lines on Windows.
When the input is empty, no `.md` file is written.

This affects only the filesystem name. It does not change the song Title metadata.

## Atomic writing

The JSON (and the optional prompt-report Markdown) is first written to a temporary file and then atomically renamed to the final path. This reduces the chance of leaving a partially written configuration file after an interrupted write.
