# Save Production JSON

Writes **one canonical JSON file per generated song** after the workflow has finished saving the audio encodings and album artwork.

## Why this node exists

Older workflow versions could write a separate JSON sidecar beside every audio file. That duplicated the same production configuration in several folders. Since v1.0.4 the recommended workflow stores one consolidated JSON in a dedicated configuration directory (default: `json/`).

The node receives the save-information outputs from the original FLAC, release FLAC and release MP3 savers plus the saved artwork path. These connections are intentional dependencies: the JSON node cannot execute until those files have been written successfully.

## Recommended settings

- **collision_mode:** `auto_increment`
- **filename_mode:** `album - title`
- **create_directories:** `true`
- Configure the destination folder in **MiniMax Output Paths → configuration_subdir**. Default: `json`.

## What the JSON contains

The node assembles the **complete generation record** from direct inputs (no separate metadata node is needed since 2.0.0):

- the full LLM stage: system prompt, user prompt, raw LLM output and status;
- the structured-prompt summary (origin, resolved fields, overrides);
- the parsed Caption / Lyrics / Title / Image_Prompt with source provenance, seeds, run/variant counters;
- the MiniMax Music 3 generation settings (max duration, text seed/CFG/top-k, sampler seed/steps/CFG/denoise);
- every audio-enhancement report: de-clipping, PRE/POST low-pass, FlashSR settings, hybrid crossover, HF cymbal/shimmer repair and release preparation;
- the standard audio tags,
- original-audio / release FLAC / release MP3 save information,
- the artwork path, the configuration-file path and (since 2.0.4) the MiniMax prompt-report path.

Audio save information includes format, sample rate, peak before final file writing, any constant safety gain applied by the saver, filename mode and embedded-cover size.

Together with the `outputs` section this is enough to recreate a song (with modified settings) from the JSON file alone - the optional `MiniMaxMetadataLoader` node (used in a separate restore workflow) reads the same schema.

## File naming

With the recommended `album - title` mode, a song with album `Example Album` and title `Northern Light` becomes:

`json/Example Album - Northern Light.json`

Since 2.0.4 the node additionally writes the MiniMax prompt report beside the JSON with the **same basename**:

`json/Example Album - Northern Light.md`

The Markdown report (from the `MiniMaxPromptReport` node, wired to the new `minimax_prompt_md` input) contains the cleaned caption, the normalized lyrics, the verbatim final prompt sent to MiniMax and the FLUX.2 image prompt. When the input is empty (not wired), no `.md` file is written.

This affects only the filesystem name. It does not change the song Title metadata.

## Atomic writing

The JSON (and the optional prompt-report Markdown) is first written to a temporary file and then atomically renamed to the final path. This reduces the chance of leaving a partially written configuration file after an interrupted write.
