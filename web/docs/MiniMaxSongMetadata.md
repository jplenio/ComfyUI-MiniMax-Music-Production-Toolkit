# MiniMax Song Metadata

Builds the in-memory reproducibility metadata for one generated song.

**Node ID:** `MiniMaxSongMetadata`  
**Category:** `MiniMax Music Production Toolkit/metadata`

The metadata includes:

- generated Title, Caption, Lyrics and Image Prompt;
- source/provenance information;
- generation seed;
- MiniMax text and sampler settings;
- PRE/POST low-pass settings;
- de-clipping report;
- FlashSR hybrid-crossover report;
- HF cymbal/shimmer repair report;
- release-prep report;
- optional complete LLM system prompt;
- workflow/version label.

## Centralized storage model

This node **does not itself write a file**. It returns `metadata_json` as a STRING.

In the bundled current workflow that string is connected only to `Save Production JSON`, which writes one final canonical JSON after all audio and artwork files have been saved.

This replaces the previous example-workflow pattern of feeding the same metadata to several audio savers and creating duplicated sidecars.

## Outputs

- **`metadata_json`** — complete in-memory reproducibility object.
- **`summary`** — compact human-readable settings summary.

For the persistent file, see the `Save Production JSON` node documentation.
