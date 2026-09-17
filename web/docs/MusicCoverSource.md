# Cover song · source audio

For **YuE2 Cover**, upload or select an audio file. Other song models ignore this
node, including an empty selection. The filename without its last extension
plus `-cover` becomes the final title, independent of LLM or manual title fields.

`full` (default) retains melody and harmony; `melody` allows a new accompaniment.
This single choice controls both transcription and generation, overriding the
new-song `yue2_mode` setting. The default encoder is
`sheetsage2_bf16.safetensors` in `models/audio_encoders`.

## Cover lyrics mode

`lyrics_mode` decides what happens to the vocals. It is carried to the score
node, the Whisper node, the Structured Song Prompt so the LLM receives the
matching instructions, and the production JSON.

- **new lyrics** - the LLM writes new words that fit the transcribed
  melody: same section order and count, guided by timed source phrases and the score. Whisper is used for this mode too.
- **original lyrics** - *Cover song · original lyrics (Whisper)* transcribes the
  original sung words, and the LLM only distributes that verbatim text across
  the score's sections. Requires the optional `faster-whisper` engine and the
  `whisper-large-v3` checkpoint (see [MusicCoverLyrics](MusicCoverLyrics.md)).
- **instrumental** - the score is rewritten so the melodic line that carried the
  vocals is played by an instrument; report Lyrics carries section tags, while
  the native generator receives empty lyric sections and a musical-tag Style. See
  [MusicCoverScore](MusicCoverScore.md).

`lead_instrument` selects that instrument for the instrumental mode, or
`Remove vocal line (accompaniment only)` to keep the accompaniment alone. It is
ignored by the two lyric-writing modes.

The instrument really takes over the melody: the notes that carried the vocals
move into the native `Ins` part unchanged, the `Vocal` part keeps its harmony
and becomes rests, and the instrument name is carried in the `Style` that YuE2
receives. It is deliberately **not** written into the score header - the native
voice definitions `Vocal` and `Ins` must stay exactly as they are, because the
official ABC checker requires them. The instrument therefore reaches the model
through the style text, not through the notation.

Nothing here guarantees a voice-free render: the score contains no more vocal
notes, but the audio model can still produce vocal-like material. Listen to the
result.

The instrumental text channel starts with the Style's own identity sentence, so
the selected template keeps its genre, instrumentation and production character.
The sentence is hazard-filtered: a clause that mentions a voice, a language, a
duration, a prompt instruction or a spoken phrase is dropped, and so is every
scheduling sentence about the score, the target or the arrangement plan - a real
Style opens with those before it names the music, and they are not style. The
explicit "instrumental only, no human voices" rule is appended after the tag list
and the section arc.

Section labels follow the bundled instrumentals instruction. A source section
labelled Verse, Pre-Chorus or Chorus becomes `[Instrumental]` in the text the
engine receives, in the Style arc and in the Lyrics field alike, so the two stay
one-to-one. Intro, Bridge, Interlude, Solo and Outro keep their names. The
original labels stay in `cover_conditioning.section_tag_map` and in the prompt
report, so the mapping is auditable.

The score never contains vocal notes: the vocal part is muted and its melody
moves into the instrumental part. That is verified in every run and is not the
source of a voice you may still hear - the audio model can add one on its own.
`cover_conditioning.mode_note` records when an instrumental cover was generated
with full conditioning, which asks the engine for melody and harmony from a score
whose vocal part is empty by design; the upstream cover guide prescribes melody
conditioning for a stylistic cover.

The mode also pins the Structured Song Prompt's Lyrics field: `instrumental` for
an instrumental cover (no words may be sung) and `yes` for original lyrics (the
transcribed words must be sung). New lyrics preserves yes/sparse and overrides wordless values.

Connect the source JSON to transcription, the score node, the Whisper node, the
model check, Structured Song Prompt, parser, Music settings and Generate song, as
in the bundled workflow. The optional title output is a preview/convenience
output; the parser enforces the same rule.
