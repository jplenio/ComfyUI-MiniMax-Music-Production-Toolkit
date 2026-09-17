# Read tags from source audio

Reads the metadata and the embedded cover art of an existing audio file so an
enhanced export looks like the file it came from.

Outputs:

- `audio_tags_json` - title, artist, album, album artist, year, track, genre,
  comment and composer, in the shape Save Audio Smart Prefix already accepts.
  Connect it to that node's `audio_tags_json` input.
- `cover_image_path` - the embedded picture, written to a temporary file, so the
  new export carries the same artwork. Connect it to `cover_image_path`. Empty
  when the source has no embedded picture.
- `tag_report_json` - which file and container were read and which fields were
  found, missing or overridden.

The source file's own tags win. The optional `overrides_json` input only fills
the fields the source does not carry, so it is a fallback rather than a way to
replace the original metadata.

FLAC, MP3, WAV and MP4 containers are read through mutagen. A field the source
does not carry stays empty; nothing is invented.

In the audio-enhancement workflow, select the same file here that Load Audio
loads. See [the audio pipeline](../../docs/AUDIO_PIPELINE.md).
