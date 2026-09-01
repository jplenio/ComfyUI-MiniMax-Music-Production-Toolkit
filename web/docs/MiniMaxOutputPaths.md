# MiniMax Output Paths

Creates consistent relative output prefixes for original audio, release FLAC/MP3, artwork and the centralized production JSON.

**Node ID:** `MiniMaxOutputPaths`  
**Category:** `MiniMax Music Production Toolkit/batch`

## Inputs

- **`source_name`** — Stable source identifier used to derive preliminary path prefixes and provenance. In the bundled workflow, the audio/artwork/JSON savers subsequently rebuild the public basename from Album + generated Title, so a library prompt filename does not become the final cover filename.
- **`base_output`** — Base path relative to ComfyUI's output directory. Date macros such as `%date:yyyy-MM-dd%` are supported by the saver/path logic.
- **`original_subdir`** — Folder for untouched/original MiniMax audio. Example default: `32flac/`.
- **`sr_flac_subdir`** — Folder for final lossless release FLAC. Example default: `44flac/`.
- **`sr_mp3_subdir`** — Folder for final MP3. Example default: `44mp3/`.
- **`artwork_subdir`** — Folder for generated cover JPGs. Default: `artwork/`.
- **`configuration_subdir`** — Folder for the single canonical JSON configuration. **Default: `json`**. This is the recommended v1.0.4 replacement for duplicated JSON sidecars beside individual audio files.
- **`append_variant_index`** — Append a variant number when several songs are generated from one source.
- **`variant_padding`** — Number of digits used for the variant suffix.
- **`run_index` / `variant_count`** — Optional connected batch information.

## Outputs

- **`original_prefix`**
- **`sr_flac_prefix`**
- **`sr_mp3_prefix`**
- **`artwork_prefix`**
- **`configuration_prefix`** — Connect this to `Save Production JSON`.

## Recommended layout

```text
base_output/
├── 32flac/
├── 44flac/
├── 44mp3/
├── artwork/
└── json/
```

All subfolder names remain configurable.
