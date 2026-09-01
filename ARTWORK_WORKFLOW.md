# Artwork workflow

The full example workflow uses FLUX.2 Klein to generate a square album cover from the LLM-created `[Image_Prompt]`.

## Flow

```text
LLM [Image_Prompt]
        ↓
FLUX.2 text encoding → sampling → VAE decode
        ↓
Save Cover JPG
        ├────────────→ embed into original FLAC
        ├────────────→ embed into release FLAC
        ├────────────→ embed into release MP3
        └────────────→ final production JSON dependency/path
```

## Matching `Album - Title` filenames

Since v1.0.5, `Save Image Smart Prefix` receives both the generated song `title` and the same `audio_tags_json` used by the audio savers. Its default `filename_mode` is `album - title`.

The audio saver, artwork saver and centralized JSON writer share the same filename-building helper. This prevents the old mismatch where a prompt source such as `nordic-folk-vocal.txt` could produce:

```text
44mp3/Example Album - Last Wick.mp3
artwork/nordic-folk-vocal.jpg
```

The bundled workflow now produces:

```text
32flac/Example Album - Last Wick.flac
44flac/Example Album - Last Wick.flac
44mp3/Example Album - Last Wick.mp3
artwork/Example Album - Last Wick.jpg
json/Example Album - Last Wick.json
```

This naming changes only filesystem names. The embedded audio `TITLE` tag remains the song title, and the `ALBUM` tag remains the configured album name.

If you deliberately want the old prefix behavior, set the artwork saver's `filename_mode` to `prefix as provided`.

## Square resolution

`MiniMax Square Image Size` provides equal width/height values. In the example workflow the same selected size is connected to the audio savers' `embedded_cover_size`, so the embedded artwork can match the generated JPG resolution.

## Prompt design

The bundled system prompt tells the LLM to create a positive-only visual concept that reflects the completed song rather than literal music-production equipment. It also explicitly asks for no visible text, letters, numbers, logos, labels or signage.

## File location

The JPG directory is controlled by `MiniMax Output Paths → artwork_subdir` (default `artwork/`). The final JPG basename is then rebuilt by `Save Image Smart Prefix` according to its `filename_mode`.

The saved artwork path is recorded in the single canonical JSON created at the end of the workflow.

### v1.0.6 workflow-serialization fix

The first v1.0.5 example workflow had the newly added `title` and `audio_tags_json` sockets serialized ahead of the older widget-backed inputs. ComfyUI validates these slots positionally, which could make `collision_mode` and `jpeg_quality` appear invalid before execution. v1.0.6 keeps the node schema and saved workflow order aligned and validates the contract during release packaging.
