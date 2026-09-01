# Save Image Smart Prefix

Saves generated artwork as JPEG using smart output paths, collision handling and the same filename convention as the audio/JSON savers.

**Node ID:** `SaveImageSmartPrefix`  
**Category:** `MiniMax Music Production Toolkit/artwork`

## Inputs

### Required

- **`image`** (`IMAGE`) — ComfyUI IMAGE tensor to save as the cover JPG.
- **`filename_prefix`** (`STRING`) — Output path/prefix, normally produced by `MiniMax Output Paths`. Its directory is preserved; the basename can be rebuilt by `filename_mode`.
- **`collision_mode`** — `auto_increment`, `overwrite`, or `error_if_exists`.
- **`create_directories`** (`BOOLEAN`) — Create missing output folders automatically.
- **`jpeg_quality`** (`INT`) — JPEG quality from 50 to 100; 90–95 is normally visually transparent for album artwork.

### Optional / connected in the bundled workflow

- **`title`** (`STRING`) — Generated song title.
- **`audio_tags_json`** (`STRING`) — Standard tag object containing at least the configured album and generated title. The bundled workflow connects the same tag JSON that is sent to FLAC/MP3 saving.
- **`filename_mode`** — `album - title` (default), `title only`, or `prefix as provided`.

## Filename behavior

With the recommended `album - title` mode:

```text
Album = Example Album
Title = Last Wick
→ artwork/Example Album - Last Wick.jpg
```

The audio saver, artwork saver and centralized JSON writer use the same shared filename helper, so their basenames stay aligned. This fixes the pre-v1.0.5 behavior where the artwork could retain the selected prompt filename (for example `nordic-folk-vocal.jpg`).

## Output

- **`saved_path`** (`STRING`) — Actual JPG path after collision handling. This path is used for cover embedding and stored in the canonical production JSON.

### Workflow compatibility

v1.0.6 corrects the saved input-slot order used by the bundled example workflow. If an older v1.0.5 workflow reports that `collision_mode` is unavailable or that `jpeg_quality` has the wrong type, load the v1.0.6 workflow or recreate this node and reconnect its inputs.
