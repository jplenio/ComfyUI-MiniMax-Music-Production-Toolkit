# MiniMax Music Production Toolkit v1.0.4

v1.0.4 improves output organization, LLM headroom and public demo/documentation support.

## Changes

- Example local LLM `max_tokens` increased to **14000**.
- Added `configuration_subdir` to **MiniMax Output Paths** with default `json`.
- Added **Save Production JSON** for one canonical per-song configuration file.
- The final JSON is written only after original FLAC, release FLAC, release MP3 and artwork saves have completed.
- Audio savers now emit `save_info_json` so the canonical JSON records the actual saved paths and file-writing details.
- The v1.0.4 example workflow disables duplicated per-audio JSON sidecars. Legacy sidecar support is retained for existing workflows.
- Added a ready-to-edit GitHub Pages SoundCloud demo page under `docs/index.html`.
- Thoroughly revised the public documentation and node help for the new output model.

## Default output organization

```text
32flac/
44flac/
44mp3/
artwork/
json/
```

The `json/` directory is configurable.

## Upgrade note

After replacing the custom-node folder, restart ComfyUI completely and hard-refresh the browser (`Ctrl+F5`). Load the v1.0.4 example workflow to use the new centralized JSON design.
