# MiniMax Output Paths

Creates consistent relative output prefixes for original audio, release FLAC/MP3 and artwork.

**Node ID:** `MiniMaxOutputPaths`  
**Category:** `MiniMax Music Production Toolkit/batch`

## Inputs

### Required

- **`source_name`** (`STRING`) — Stable source identifier used to derive output paths and provenance. It normally comes from the prompt filename or manual/LLM source name.
- **`base_output`** (`STRING`) — Base path relative to ComfyUI's output directory. Date placeholders such as %date:yyyy-MM-dd% are expanded by the saver/path logic; all subdirectories below are appended to this base.
- **`original_subdir`** (`STRING`) — Subfolder for untouched/original MiniMax audio, typically the 32 kHz FLAC archive.
- **`sr_flac_subdir`** (`STRING`) — Subfolder for the final/upscaled lossless FLAC output. The name is only a folder label; actual sample rate comes from the audio signal entering the saver.
- **`sr_mp3_subdir`** (`STRING`) — Subfolder for final/preview MP3 output. The name is only a folder label; encoder quality is controlled in the saver node.
- **`artwork_subdir`** (`STRING`) — Subfolder for generated cover JPG files. The same base filename is used so cover embedding can be matched to the song.
- **`append_variant_index`** (`BOOLEAN`) — Append the run/variant number to filenames when multiple variants are generated. Recommended to avoid collisions and keep variants easy to associate with metadata.
- **`variant_padding`** (`INT`) — Number of digits used for the variant suffix, for example 2 produces _01 and 3 produces _001.

### Optional

- **`run_index`** (`INT`) — 1-based variant index for the current song run. It is used for reproducible metadata and optional filename suffixes.
- **`variant_count`** (`INT`) — Total number of variants produced from the current source. Used for metadata and to decide whether a variant index should be appended.

## Outputs

- **`original_prefix`** (`STRING`)
- **`sr_flac_prefix`** (`STRING`)
- **`sr_mp3_prefix`** (`STRING`)
- **`artwork_prefix`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
