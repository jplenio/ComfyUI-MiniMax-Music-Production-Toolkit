# Instrumental check · words heard

Transcribes one generated candidate with Whisper and counts the words it hears.
An instrumental passes when it hears none, or no more than the configured
tolerance.

This node is created inside the generation expansion; you do not place it
yourself. It runs on the **raw** generated audio, before refinement,
equalisation, mastering and release encoding, because those change the sound but
not whether someone is singing.

The score of an instrumental cover contains no vocal notes at all - the vocal
part is muted and its melody moves into the instrumental part. A voice that is
still audible was added by the audio model, so listening is the only honest test,
and this node is the listening.

`word_tolerance` counts spoken or sung **words**, not letters. `0` requires a
render with no recognisable words at all.

## What the log shows

Every word Whisper heard is logged per take, so humming without words and a
returning chorus can be told apart:

```text
Instrumental vocal check take-2: Whisper heard 4 words: hold on to me now
Instrumental vocal check take-2: 4 words (tolerance 0) -> voice detected
```

A very long transcript is shortened to 500 characters in the log with the total
character count appended; the full text stays in `check_report_json` and in the
generation record. A take Whisper hears nothing in is reported as
`Whisper heard no words` rather than logged silently.

`candidate_label` names the take in the log, the report and its temporary WAV
file. The generation expansion sets it to `take-1`, `take-2`, and so on.

The audio is passed through untouched. See
[the YuE2 guide](../../docs/YUE2.md#when-a-voice-still-appears-in-an-instrumental)
and [Instrumental check · keep least vocal take](MiniMaxInstrumentalPick.md).
