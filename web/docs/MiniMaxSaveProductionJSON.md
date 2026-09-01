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

The base reproducibility metadata is produced by **MiniMax Song Metadata** and includes the LLM/system prompt, generated Caption/Lyrics/Title/Image Prompt, source provenance, seeds, MiniMax generation settings, FlashSR/filter settings, de-clipping, HF repair and release preparation settings.

The final writer adds:

- standard audio tags,
- original-audio save information,
- release FLAC save information,
- release MP3 save information,
- artwork path,
- configuration-file path.

Audio save information includes format, sample rate, peak before final file writing, any constant safety gain applied by the saver, filename mode and embedded-cover size.

## File naming

With the recommended `album - title` mode, a song with album `Example Album` and title `Northern Light` becomes:

`json/Example Album - Northern Light.json`

This affects only the filesystem name. It does not change the song Title metadata.

## Atomic writing

The JSON is first written to a temporary file and then atomically renamed to the final `.json` path. This reduces the chance of leaving a partially written configuration file after an interrupted write.
