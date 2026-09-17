# Music generation record

YuE2 Cover records the original SheetSage2 ABC, source filename, fixed cover
title, transcription mode and audio encoder. `abc_source` identifies audio
transcription; new-score sampling settings are omitted because no ABC is generated.

Internal companion to Generate song, created during graph expansion. Stores
the actual generated duration and ABC together with the effective settings and
selected model filenames. Does not download, generate or save audio itself.
For a cover, the recorded ABC is the score the engine actually received, and
`cover_source` names the lyrics mode and lead instrument used.

When a duration plan is present, `duration_request` stores the requested Length
and target; `max_duration` remains the separate configured ceiling.
`duration_result` records the actual deviation and whether it falls inside the
requested range. This is informational: finishing beyond the target is allowed,
and the record never crops or fades the audio.

## Inputs

- **settings_json** - the resolved settings the song was generated with.
- **abc** - the score handed to the model. Empty for models that do not read notation.
- **seconds** - the duration the model was asked for; the saved file can differ.
- **model_files_json** - which weights produced this song.
- **cover_source_json** / **instrumental_check_json** (optional) - the cover's identity and the
  result of the vocal check, when the run had them.
