# YuE2 cover ABC reference (compact, injected into the transformation prompt)

This is the explicit local reference the Cover Studio loads before any
ABC-related model call. It is a curated condensation of the verified upstream
snapshot in [YUE2_ABC_REFERENCE.md](YUE2_ABC_REFERENCE.md) (YuE commit
`ef1936f2`, Apache-2.0) and of the bounded checker vendored as
`third_party/yue2_abc.py`. Where this sheet and the upstream document disagree,
the upstream document wins.

## 1. Native format

YuE2 and SheetSage2 speak a **bounded** two-voice ABC dialect, not the full ABC
standard. A score looks exactly like this:

```abc
X:1
T:
M:4/4
L:1/32
Q:1/4=88
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:G
% verse
V: Vocal
"Gmaj7"B8d8"Am7"c8A8|"D7"F16"G"G16|
V: Ins
Z2|
```

- **Header order is fixed.** `X:1`, a blank `T:`, `M:`, `L:`, `Q:`, the two `V:`
  definitions, then `K:`. `K:` ends the header block.
- **`L:`** is the default note length. The exporter picks the denominator it
  needs, usually `1/32`; any `1/<power of two>` up to `1/1024` is accepted.
  Preserve the exported value.
- **`Q:`** is an integer quarter-note tempo: `Q:1/4=120`.
- **Pitches** are relative to the active key. `C`/`c`/`c'`/`C,` are C4/C5/C6/C3.
  An unmarked `F` in `K:D` sounds F-sharp.
- **Durations** are multipliers of `L:`. Only `1, 2, 3, 4, 6, 8, 12, 16, 24, 32,
  48` are supported. Ten units must be written `C8-C2`, never `C10`.
- **Rests** are `z<duration>`. A whole resting measure is `Z`, or `Z2`/`Z3`/`Z4`
  for two to four measures. `Z` counts measures, not `L:` units.
- **Accidentals** are `^` sharp, `_` flat, `=` natural, `^^` double sharp,
  `__` double flat. They stay active through the bar and **propagate by letter
  across octaves**; after `^F`, both later `F` and `f` are sharp in that bar.
  The state resets at a barline and at a key change.
- **Ties** are `-`. A tie joins two equal sounding pitches into one note and must
  not be left unresolved at the end of the score. A rest cannot be tied.
- **Chords** are quoted symbols and belong in **Vocal**, including while it
  rests: `"Am7"`, `"F#m7/C#"`, `"Gm6/Bb"`. Only the root and an optional slash
  bass use note names; double accidentals are allowed where the spelling needs
  them.
- **Within a measure**, each bar is separated by a plain `|` and the music line
  ends with `|`. Supported chord qualities are exactly: *(none)*, `m`, `dim`,
  `aug`, `7`, `maj7`, `m7`, `dim7`, `m7b5`, `sus4`, `sus2`, `6`, `m6`, `7sus4`,
  `m(maj7)`.

## 2. Structure

- The body is grouped in **one to four measures** per group.
- A group is a `% <label>` comment, then `V: Vocal` plus its music line, then
  `V: Ins` plus its music line. Both voices must carry the **same number of
  measures**, the same meter and the same key-change timeline.
- Both parts are **monophonic**. `Ins` may carry an instrumental theme or solo;
  it is not a piano chord staff.
- A meter or key change **starts a new group** and needs matching `M:` or `K:`
  fields in both voice blocks. An inline `[K:...]` may occur inside a measure,
  but both voices must change key at the same musical time.
- Section comments delimit structure. Preserve them.

## 3. What YuE2 does and does not take

- YuE2's request accepts `style`, `lyrics`, `cot`, `seed`, `abc`, `cfg_scale`
  and `id`. There is no `reference_audio`, `phonemes`, `bpm`, `negative_prompt`
  or edit-interval field.
- `cot` has exactly two usable values for covers:
  - `cot="full"` - the supplied score keeps melody **and** harmony.
  - `cot="melody"` - the score is a **melody-only** line and the model is free
    to write a new accompaniment.
- **`cot="melody"` does not remove chords for you.** A melody-only score must be
  produced first, by removing the quoted chord symbols from the music lines
  while leaving every sounding note, onset, duration and meter unchanged.
- An external ABC bypasses the symbolic planner. There is no second planner that
  repairs a bad score, so a malformed score is a failed run.
- Keep pronunciation, note alignment and syllable plans in sidecar records. Do
  **not** add `w:` lyric fields, phoneme annotations, extra voices or custom
  directives to the model's ABC.

## 4. Transformation rules

```
NEVER output prose around the score.
NEVER wrap the score in a markdown code fence.
NEVER invent constructs this sheet does not list.
NEVER change the fixed header order or drop a required header.
NEVER silently change the meter or the key.
NEVER create an invalid bar: the durations plus rests in a bar must equal the
  meter exactly.
NEVER leave an unresolved tie, a tie over a rest, or a rest with an accidental.
NEVER add a second note to a voice: both parts stay monophonic.
NEVER write chord symbols into Ins.
NEVER claim that generated audio will match the score; the score is a condition,
  not a guarantee.

ALWAYS preserve the one-to-four-measure grouping and the section comments unless
  the profile explicitly allows a structural change.
ALWAYS keep both voices on the same measure and key-change grid.
ALWAYS re-check every changed bar for exact duration.
ALWAYS keep the melody inside the requested vocal range when one is given.
```

When `melody_only` is true:

```
- remove the quoted chord symbols from every music line,
- keep every sounding note, its onset, its duration and every tie,
- keep the bar structure, the meter and the full-measure rests,
- keep both voice definitions and the header unchanged.
```

When the melody may vary:

```
- keep phrase boundaries recognisable unless the profile allows structure change,
- prefer stepwise motion and keep the range singable,
- do not turn one syllable-carrying note into a run of very short notes.
```

## 5. Examples

**A - full ABC** (two groups, chords in Vocal, `Ins` doubling the lead):

```abc
X:1
T:
M:4/4
L:1/8
Q:1/4=100
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% intro
V: Vocal
z2 "Cmaj7"C2 E2 G2-|G2 c2 z4|
V: Ins
C,2 G,2 C2 E2|G2 c2 z4|
% verse
V: Vocal
"Cmaj7"C2 D2 E2 F2|"Fmaj7"G4- G2 z2|
V: Ins
C,2 G,2 C2 E2|F,2 C2 F2 A2|
```

**B - melody-only ABC** (the same score with the chord symbols removed; nothing
else changed - this is the shape `cot="melody"` expects):

```abc
X:1
T:
M:4/4
L:1/8
Q:1/4=100
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% intro
V: Vocal
z2 C2 E2 G2-|G2 c2 z4|
V: Ins
C,2 G,2 C2 E2|G2 c2 z4|
% verse
V: Vocal
C2 D2 E2 F2|G4- G2 z2|
V: Ins
C,2 G,2 C2 E2|F,2 C2 F2 A2|
```

**C - faithful transformation.** Only the instrumentation, the sound design and
the production prose change. The score above is returned byte for byte, with an
empty `changes` list.

**D - moderate reinterpretation.** Chords may be reharmonised while the melody
stays: replace `"Fmaj7"` with a chord that supports the sustained melody tone,
for example `"Am7"` in front of an `A`, and keep the measure lengths identical:

```abc
"Cmaj7"C2 D2 E2 F2|"Am7"G4- G2 z2|
```

**E - strong reinterpretation.** The melody may be simplified or ornamented, but
every bar must still add up and the phrase ends stay recognisable:

```abc
"Cmaj7"C2 D2 E4|"Am7"G4 z4|
```

**F - transposition.** The key field and every sounding pitch move together, and
the accidentals are re-spelled against the new key. `K:C` moved up two semitones
is `K:D`:

```abc
K:D
% verse
V: Vocal
D2 E2 F2 G2|A4- A2 z2|
```

**G - vocal range adjustment.** If a phrase sits above the requested range, move
it down an octave with `,` rather than rewriting the rhythm; keep the bar
durations untouched:

```abc
V: Vocal
C,2 D,2 E,2 F,2|G,4- G,2 z2|
```
