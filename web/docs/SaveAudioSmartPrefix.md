# Save Audio Smart Prefix

Saves FLAC/MP3/WAV using smart output prefixes, safe filesystem naming, standard audio tags and configurable embedded cover artwork.

**Node ID:** `SaveAudioSmartPrefix`  
**Category:** `MiniMax Music Production Toolkit/save`

## Key inputs

- **`audio`** — ComfyUI AUDIO signal to save.
- **`filename_prefix`** — Normally supplied by `MiniMax Output Paths`.
- **`format`** — FLAC, MP3 or WAV.
- **`collision_mode`** — `auto_increment`, `overwrite` or `error_if_exists`.
- **`create_directories`** — Create missing directories automatically.
- **`mp3_quality`** — MP3 encoder quality/bitrate.
- **`flac_bit_depth` / `wav_bit_depth`** — File precision.
- **`peak_handling`** — `normalize_only_if_clipping` applies only one constant safety gain if sample peaks exceed full scale; it is not loudness normalization.
- **`embed_basic_metadata`** — Write standard tags to compatible audio formats.
- **`filename_mode`** — Default `album - title`; affects only the filesystem filename, not the embedded TITLE tag.
- **`embedded_cover_size`** — Target embedded cover resolution.

## Centralized JSON behavior

`write_json_sidecar` remains available for **backward compatibility**. When enabled and `metadata_json` is connected, this saver can still create an individual sidecar beside the audio file.

The bundled current workflow keeps this option **OFF** (the centralized design was introduced in v1.0.4) and leaves `metadata_json` disconnected on the audio savers. Instead, one canonical file is written by `Save Production JSON` into the configurable `json/` directory.

## Outputs

- **`audio`** — passthrough audio.
- **`saved_path`** — final saved audio path.
- **`metadata_path`** — legacy sidecar path, empty when no individual sidecar is written.
- **`save_info_json`** — structured save result containing the actual path, format, sample rate, peak before file writing, applied constant save gain, filename mode, embedded-cover size and any legacy sidecar path.

Connect `save_info_json` to `Save Production JSON`. That dependency also ensures the final JSON writer waits for this audio file to be written.
