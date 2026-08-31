# Example workflow guide

The bundled workflow is a complete production example. Individual toolkit nodes can also be used separately.

## Stage 1 — Prompt preparation

`LLM Prompt Library / Template` resolves the user and system prompts from manual text, the bundled libraries or external directories. The production system prompt asks the LLM to return exactly these conceptual sections:

1. `[Caption]`
2. `[Lyrics]`
3. `[Title]`
4. `[Image_Prompt]`

The title is intentionally created after Caption and Lyrics. The parser remains order-tolerant so a minor LLM formatting deviation does not unnecessarily destroy an otherwise usable result.

`LLM Session ID / Cache Buster` changes the external LLM's `session_id` per queued run when its seed is set to Randomize/Increment. This prevents ComfyUI from reusing a previous LLM output simply because the creative user prompt is unchanged.

## Stage 2 — MiniMax Music 3

The parser passes Caption/Lyrics to the MiniMax Music 3 core generation node and derives a generation seed. Generation settings are centralized for reproducibility.

The original source audio is saved as an archival branch before corrective processing.

## Stage 3 — Source repair

`Audio Declip / Overload Repair` detects short hard-clipping plateaus and can reconstruct plausible peak curvature. The conservative mode is intended as a batch-safe safety net; it does not apply a compressor or limiter.

## Stage 4 — FlashSR and high-frequency control

The repaired source takes two paths:

- clean HQ sample-rate conversion for the trustworthy original branch;
- PRE low-pass → FlashSR for reconstructed high-frequency information.

`FlashSR Hybrid Crossover` recombines them. The default hybrid approach preserves original information and only adds controlled FlashSR air.

`HF Cymbal / Shimmer Repair` can reduce diffuse/smeared HF sustain, followed by the POST low-pass stage.

## Stage 5 — Release preparation

`Audio Release Prep – Static LUFS / True Peak / SRC` converts to the selected final sample rate and optionally applies one constant full-program gain calculated from measured integrated loudness and true peak.

If the LUFS target would violate the true-peak ceiling, the true-peak ceiling wins. The node does not silently switch to dynamic gain riding.

## Stage 6 — Artwork and metadata

The LLM's Image Prompt drives the FLUX.2 Klein cover branch. Artwork size is also connected to the audio savers' embedded-cover size.

`MiniMax Song Metadata` writes reproducibility data. `MiniMax Standard Audio Tags` supplies ordinary release tags. The smart saver defaults to filesystem names of the form:

```text
[Album] - [Title].[extension]
```

The embedded `Title` metadata remains only the song title.
