# Complete workflow guide

The included workflow is designed as an end-to-end MiniMax Music 3 production example. You can remove stages you do not need, but this document describes the complete graph.

## 1. Prompt preparation

`Structured Song Prompt` provides two independent prompt sources:

- the **user prompt** assembled from structured fields (Genre, Tempo, Key, Lyrics, Language, Voice, Lyrics theme, Target length) plus a further-description area;
- the **system prompt** describing how the LLM must transform that request for MiniMax Music 3.

Each can come from:

- manual text;
- the bundled prompt library;
- an external directory.

Prompt files can start with an optional metadata block that prefills the structured fields when the file is selected (see [PROMPT_LIBRARY.md](PROMPT_LIBRARY.md)). Every field can be overridden; `custom` leaves that part out of the LLM prompt.

The bundled production system prompt requires the LLM to return:

```text
[Caption]
[Lyrics]
[Title]
[Image_Prompt]
```

The parser is intentionally order-tolerant for resilience, but the system prompt asks for this exact order.

## 2. Integrated LLM (llama.cpp)

The example uses the integrated `LLM Chat (llama.cpp)` node with a local GGUF model — no external LLM custom node is required.

The bundled example uses the user-tested local-LLM settings:

```text
max_tokens = 16384
n_ctx      = 32768
```

This is intentionally generous because the model may need to produce a detailed Caption, long instrumental section structure, lyrics, title and cover prompt in one response. If your selected GGUF model or hardware needs less context, reduce these values together rather than assuming the example settings are universal.

`LLM Session ID / Cache Buster` can randomize/increment the session ID so identical high-level genre prompts still trigger a fresh creative LLM pass in batch generation. `Unload LLM (integrated)` runs after the chat and frees the model memory before music generation.

### Switching the LLM section off

- Set `LLM Chat (llama.cpp) → enabled` to false (or bypass the LLM nodes).
- Fill `manual_caption` and `manual_lyrics` (optionally `manual_title`, `manual_image_prompt`) on the parser node.
- The parser falls back to these manual values; the rest of the workflow keeps running.

## 3. Structured output parser

`Parse Structured LLM Output` extracts:

- Caption
- Lyrics / instrumental section map
- Title
- Image Prompt

Its LLM input is optional; without it, the manual fallback fields are used. It also generates/provides per-song source/provenance information and the primary generation seed used downstream.

## 4. MiniMax generation settings

`MiniMax Music 3 Generation Settings` derives the text/sampler values used by the MiniMax Music 3 subgraph. The public example keeps the established defaults unless you deliberately change them.

The generated Caption and Lyrics are sent into the MiniMax Music 3 node/subgraph.

## 5. Original source archive

The raw MiniMax output can be saved as the original FLAC before restoration/upscaling. This is useful because it preserves the untouched model output for later comparison or re-processing.

The bundled workflow does **not** write its own JSON sidecar at this stage.

## 6. Source de-clipping

`Audio Declip / Overload Repair` runs before FlashSR. It looks for hard-clipped flat-top peaks and can reconstruct plausible curvature conservatively.

This is not a limiter and cannot restore information that clipping destroyed exactly.

## 7. PRE low-pass + FlashSR (integrated)

`Audio Super Resolution (FlashSR, integrated)` replaces the previously used external Egregora node with the same processing behavior (48 kHz inference, 5.12 s chunks, 0.50 s overlap, Hann overlap-add). Its inference code is bundled with the toolkit (`flashsr_inference/`); only the FlashSR weights are checked/downloaded automatically on first use (see [INSTALLATION.md](INSTALLATION.md)).

The explicit PRE low-pass can remove problematic source treble before FlashSR. FlashSR then reconstructs bandwidth at a higher sample rate. Since 2.0.0 the PRE/POST low-pass values live directly on the two low-pass nodes (the former shared "FlashSR / Lowpass Settings" node was removed from the example workflow).

The full workflow intentionally preserves an original branch as well so you are not forced to replace the whole source with generated high-frequency content.

## 8. Hybrid crossover

`FlashSR Hybrid Crossover` combines the clean resampled original with controlled FlashSR high-frequency content.

The default `Original + FlashSR air` mode prioritizes original source/transient information and adds only a selected amount of reconstructed high band.

## 9. HF cymbal / shimmer repair

This stage targets sustained high-frequency smear while preserving attacks. Use conservative presets for unattended batches.

## 10. POST low-pass

The POST filter can remove excessive extreme reconstructed treble. Treat it as cleanup, not as a substitute for good hybrid settings.

## 11. Release preparation

`Audio Release Prep` performs high-quality sample-rate conversion, integrated loudness/true-peak measurement and optional static gain.

Important: it applies **one constant gain to the entire program** and caps that gain when the true-peak target would be exceeded. There is no compressor, AGC or time-varying loudness normalization in this node.

The example produces 44.1 kHz release audio.

## 12. FLUX.2 album artwork

The LLM-generated `[Image_Prompt]` drives the FLUX.2 Klein branch. The square-size node controls both generated JPG dimensions and the embedded cover size used by the audio savers.

In v1.0.5 the cover saver also receives the generated `title` and the same `audio_tags_json` used by the audio savers. With the default `filename_mode = album - title`, the JPG therefore receives the exact same basename as the FLAC, MP3 and production JSON. The prompt-source filename is still useful internally for provenance/output-prefix routing, but it no longer becomes the public cover filename in the bundled workflow.

See [ARTWORK_WORKFLOW.md](ARTWORK_WORKFLOW.md).

## 13. Standard audio metadata

`Standard MP3 / FLAC Metadata` provides:

- Title (generated and connected)
- Artist
- Album
- Year
- Track
- Genre
- Comment
- Album Artist
- Composer

The default filesystem naming mode is:

```text
Album - Title.ext
```

The embedded `TITLE` tag itself remains only the song title.

## 14. Central output paths

`MiniMax Output Paths` controls all output subdirectories from one place:

```text
base_output
original_subdir
sr_flac_subdir
sr_mp3_subdir
artwork_subdir
configuration_subdir
```

v1.0.4 adds:

```text
configuration_subdir = json
```

The node emits a dedicated `configuration_prefix` for the final JSON writer.

## 15. One final production JSON

v1.0.4 changes the reproducibility-file strategy.

Older workflow versions could produce repeated JSON sidecars beside multiple audio encodings. The current workflow instead uses:

`Save Production JSON`

It depends on:

- the original FLAC saver's `save_info_json`;
- the release FLAC saver's `save_info_json`;
- the release MP3 saver's `save_info_json`;
- the saved cover JPG path;
- standard audio tags;
- the centralized `configuration_prefix`.

Since 2.0.0 the separate "Reproducible Song Metadata" node is no longer part of the example workflow: `metadata_json` is an optional input, and the canonical JSON still records the standard tags, the title and the complete `outputs` section without it.

Because those save-info/path inputs only become available after each file is saved, the final configuration writer naturally executes after the output artifacts it documents.

Default output:

```text
json/Example Album - Song Title.json
```

The canonical JSON contains both **generation configuration** and an `outputs` section describing the files that were actually written.

## 16. Legacy per-audio sidecars

`Save Audio Smart Prefix` still supports its historical `write_json_sidecar` option for backward compatibility. In the current example workflow it is OFF and the `metadata_json` input is intentionally not connected to the audio savers.

For new workflows, the centralized JSON design is recommended.

## 17. Batch generation

For batches, use a changing generation/session seed and prompt-library entries. Each run can independently vary:

- composition;
- arrangement;
- title;
- lyrics;
- artwork concept;
- generation seed.

The output-path and JSON structure keeps the resulting assets associated without duplicating configuration records.
