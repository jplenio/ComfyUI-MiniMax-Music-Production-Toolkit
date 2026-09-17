# Cover song · instrumental score / phrase map

New/original lyrics pass the score through unchanged. The phrase map counts
vocal note onsets, preserves phrase notation and does not claim to measure
sung syllables. Missing Vocal material never falls back to instrumental notes.

Instrumental mode replaces Vocal notes with equal-duration rests, preserving
its harmony, and transfers the lead into native Ins blocks. Where melodies
overlap in a block, the former vocal melody wins and replaced Ins notes are
reported. Blocks without sung notes retain the original instrumental theme.
Accompaniment-only mutes Vocal but keeps Ins unchanged. Native fields, structure
and block boundaries remain. No unsupported extra voice is invented.

The rewrite is idempotent; both the prompt and generator receive the same ABC.
Report output records changes, note counts and phrase grids in `cover.score`.
The legacy `total_syllables` key means note-onset count, not measured syllables.
This notation transformation does not guarantee voice-free rendered audio.
See [cover guide](../../docs/YUE2.md#cover-lyrics-modes).

## Inputs

- **cover_source_json** - the selected file, its `full`/`melody` mode and its lyrics mode. This
  is what decides the rewrite: new and original lyrics pass the score through unchanged,
  instrumental rewrites it.
- **cover_abc** - the ABC score from the transcription node.

Only an instrumental cover changes the score. Everything else is reported for validation.
