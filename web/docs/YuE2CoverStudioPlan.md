# YuE2 Cover Studio · 1 plan

Turns the **Interpretation Freedom** slider into a structured cover profile and
builds the planning prompt for an LLM Chat node. It never changes the score.

`Interpretation Freedom` is a toolkit abstraction, **not a YuE2 parameter**: YuE2
has no such setting. The value selects what the cover keeps and what it may
rework, and the transformation stage then realises that in ways YuE2 does
understand - a chord-free melody line, a rewritten `Q:` tempo, a transposed key,
and explicit instructions.

Bands: `0-20` faithful cover, `21-40` arrangement, `41-60` reinterpretation,
`61-80` creative reinterpretation, `81-95` loose adaptation, `96-100` inspired
recomposition. The individual weights interpolate between the band boundaries,
so every integer yields a different profile.

Outputs `system_prompt` and `user_prompt` go into an LLM Chat node.
`studio_json` carries the profile, the measured score analysis, the overrides and
the original ABC to the next studio node.

## What this node owns, and what it does not

The studio and *Song request · template & fields* describe different things. Both
the tooltips and the prompts say so, and the code enforces it:

- **This node owns the rework of the source material:** the slider, the
  preserve/variation knobs, key and tempo changes, and the score validation that
  follows in steps 2 and 3.
- **Song request · template & fields owns what the track sounds like.** Its
  template, fields and description are the master, and its STYLE PRIORITY rule is
  forwarded to the model unchanged.
- **`target_style` is a hint for the rework, not a second style source.** Empty
  means "no extra hint" - not "follow the source's character". Filling it guides
  how the material is reworked toward the requested style and must never
  contradict it.
- **Do not wire the song request node into this field.** That node consumes the
  studio's rewritten score, so it is downstream of the studio; a link from it back
  into the studio is a dependency cycle and ComfyUI rejects the prompt with
  `Dependency cycle detected`.
- **Connect [Style hint · template or text](MiniMaxStyleHint.md) here instead** if
  you want the studio to see the requested style. That node reads the same prompt
  template (or typed text) from outside the studio's chain, so the link is legal. In
  the bundled workflow this is its only consumer: the master's `description_override`
  is filled from the master's own template selection, so the value stays a hint for
  the rework while the master remains the style of record.
- **The cover lyrics mode owns the words** (selected in *Cover song · source
  audio*): `instrumental` removes Voice, Language and Lyrics theme from the brief,
  `original lyrics` removes the theme and takes its language from the Whisper
  transcript, and `new lyrics` keeps them because the new words are written from
  them. See [the cover guide](../../docs/YUE2.md#where-each-instruction-comes-from).
- **`lyrics_policy` / `supplied_lyrics` are the one deliberate exception:** they
  lock words verbatim, and the studio refuses combinations that cannot work (an
  instrumental cover has no words to keep; `original lyrics` owns its words).

Every `preserve_*` / `melody_only` widget is tri-state: `auto` uses the slider,
`yes` pins the element, `no` releases it. An explicit setting always wins over
the automatic value. The degree widgets (`melody_variation`, `rhythm_variation`,
`harmony_freedom`, `structure_freedom`) accept `auto`, `none`, `low`, `moderate`
or `high`.

Advanced knockouts: `key_change` transposes deterministically by semitones and
`tempo_change` rewrites the tempo by percent; both are validated before they are
applied. `vocal_range` is a request to the model, not an enforced constraint.
`advanced_mode` only widens the debug report - it never changes which values
apply.

## What the slider does not change

The freedom permissions apply to the **source material** only. The requested
style - the selected template, the genre, the instrumentation, the production and
the character - always governs the result, at every freedom value. A higher value
means that less of the source survives, never that less of the requested style is
delivered. This is stated in the cover instruction the prompt node sends and in
both studio prompts.

`melody_only` follows the decode mode, not the slider. The chord-free reduction
is what a `melody` cover expects, so it is applied there from the arrangement
band upward. A `full` cover promises melody **and** harmony, so it keeps its
chords whatever the freedom value; removing them would hand the engine a
"melody and harmony" score with no harmony. The report says which of the two
applies and why, and an explicit `melody_only = yes` on a `full` cover is refused
with an explanation instead of silently breaking the mode contract.

## Lyrics policy

The words never follow the slider. `lyrics_policy` decides them separately:

- **auto (mode decides)** - the cover lyrics mode owns the words, exactly as
  before this node existed.
- **keep source words** - the Whisper transcription is placed verbatim into the
  final score's sections with the existing lossless, order-verified placer. The
  result leaves on `locked_lyrics`.
- **keep supplied words** - the text in `supplied_lyrics` is used exactly as
  written, with no rewriting and no syllable alignment.

A locked block is a user decision, so the parser treats it as intentional
instead of mistaking it for a model that lazily copied the source. Combinations
that cannot work are refused with a clear message: an instrumental cover has no
words to keep, and `original lyrics` mode already owns the words from the
transcription. The report records the lyrics/melody fit, so a locked text that
no longer fits a strongly reworked melody is visible rather than silent.

When the node is switched off, or the source is not a YuE2 Cover source, the
score passes through untouched and the studio report says so.
See [the YuE2 guide](../../docs/YUE2.md#yue2-cover-studio).
