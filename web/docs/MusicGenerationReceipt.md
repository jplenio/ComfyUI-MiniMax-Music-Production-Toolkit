# Music generation record

YuE2 Cover records the original SheetSage2 ABC, source filename, fixed cover
title, transcription mode and audio encoder. `abc_source` identifies audio
transcription; new-score sampling settings are omitted because no ABC is generated.

Internal companion to Generate song, created during graph expansion. Stores
the actual generated duration and ABC together with the effective settings and
selected model filenames. Does not download, generate or save audio itself.

When a duration plan is present, `duration_request` stores the requested Length
and target; `max_duration` remains the separate configured ceiling.
`duration_result` records the actual deviation and whether it falls inside the
requested range. This is informational: finishing beyond the target is allowed,
and the record never crops or fades the audio.
