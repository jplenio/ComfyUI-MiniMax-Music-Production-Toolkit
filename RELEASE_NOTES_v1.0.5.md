# MiniMax Music Production Toolkit 1.0.5

## Artwork filename parity

This release fixes a mismatch between audio and artwork filenames in prompt-library workflows. Previously, audio files could correctly be saved as `Album - Title` while the cover JPG kept the source prompt filename, for example `nordic-folk-vocal.jpg`.

The bundled workflow now connects the generated song title and the standard audio-tag JSON to `Save Image Smart Prefix`. With the default `filename_mode = album - title`, all principal per-song artifacts share the same basename:

```text
32flac/Example Album - Last Wick.flac
44flac/Example Album - Last Wick.flac
44mp3/Example Album - Last Wick.mp3
artwork/Example Album - Last Wick.jpg
json/Example Album - Last Wick.json
```

Audio, artwork and centralized JSON naming now use one shared filename helper so sanitization and Album/Title construction cannot drift between formats. The old source-prefix behavior remains available explicitly through `filename_mode = prefix as provided`.

## Demo page

The GitHub Pages demo configuration includes the prepared SoundCloud playlist and track URLs. The page can use local demo covers when present and otherwise fall back to SoundCloud's visual player.

## Example workflow

The release preserves the packaged/tested local-LLM settings:

```text
max_tokens = 16384
n_ctx      = 32768
```

No MiniMax Music 3 generation, audio restoration, FlashSR, release-prep or metadata-processing defaults were intentionally changed for this fix.

## Validation

Release tests now explicitly verify the artwork title/tag connections, shared `album - title` naming contract, centralized JSON contract and workflow link integrity including MiniMax subgraph boundaries.
