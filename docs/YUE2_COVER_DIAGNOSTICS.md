# YuE2 Cover: follow-up of the reported runs

## Findings (2026-09-17)

The successful new-lyrics run and failed original-lyrics run both transcribed
26 segments / 1,313 characters. The earlier VAD/CUDA problem is resolved in
these logs. Original mode now failed because the LLM changed the authoritative
words, not because Whisper returned too little. The Windows connection-reset
message belongs to the preceding successful run; it is not this parser failure.

The instrumental receipt confirms an empty native Lyrics string. The saved ABC
has no sounding Vocal notes. A separate Whisper pass over that generated audio
found multiple sequences shared with the verbose Style (longest match: seven
consecutive words). ASR is imperfect, but this supports the user's report of
spoken/sung planning prose. Empty Lyrics alone was not an effective solution.

The source ABC lasts **210.24 seconds** at 125 BPM, including two 1/4 measures.
The instrumental Style invented an approximately 248-second form, 28 opening
measures instead of 23, and an extended ending. Its instrument-specific voice
headers also departed from the official fixed native header definitions.

## Corrections

1. **Original words are data, not an LLM rewrite.** Python places the unchanged
   source words in ABC sections using Whisper word times; segment times are the
   fallback when word/text tokenization disagrees. A final ordered-word check
   includes every repetition. Missing timing falls back to source order and is
   explicitly reported. The LLM plans the arrangement, and receives the same
   authoritative layout beforehand. The source language overrides the template's
   new-lyrics language in original mode.
2. **Native ABC validation and measured timing.** A pinned upstream parser checks
   bars, compressed rests, meters, pitches, ties, harmony placement and the two
   voice timelines. Native headers remain `Vocal Melody` / `Ins Melody`; lead
   instrument is a Style choice. Measured section boundaries and vocal onsets
   guide the LLM; numbered Style headings use measured times and measure counts.
   Melody mode explicitly strips chords without changing notes or timing.
3. **Instrumental text conditioning.** The detailed plan remains in the report.
   The native Style is compiled to recognized genre/instrument/texture tags with
   a section-by-section arc; arbitrary prose, quoted words, singer/language
   instructions and duration instructions are excluded. Native Lyrics contains
   only empty section tags matched to the score. This supersedes the previous
   empty-string experiment. The receipt stores exact `native_style`,
   `native_lyrics` and `native_abc` under `generation.cover_conditioning`.

The tag vocabulary includes the toolkit's curated genres and common musical
instruments/textures. Unsupported descriptive nuances remain in the full report
but may not survive the instrumental tag compiler. This is a deliberate limit
of this conditioning strategy, not a promise that all prose is preserved at the
native model input. No generative prompt or ABC check guarantees voice-free
audio or exact sung synchronization; those remain listening checks.

The user explicitly chose **prompt/ABC corrections only**. No vocal-separation
stage, dependency or model is added.

## Actual native-model test

A standalone test used the existing ComfyUI server, the same source score and
seed, 40 steps and the unchanged duration ceiling. No installed toolkit source
was overwritten. The native graph completed in 168.07 seconds and saved 206.2
seconds of audio in the development workspace. Its Style contained 887 characters
of musical tags, with no narrative instructions.

Whisper over the earlier failed instrumental recognized 52 segments and multiple
Style phrases. On the new audio it returned 12 segments / 79 words and no word
sequence shared with the native Style. Several repeated, lyric-like segments
remain. This is evidence against continued prompt reading, **not** proof of
voice-free audio: automatic transcription can also hallucinate over instruments.
The instrumental requirement must not be marked acoustically guaranteed on this
basis. Additional vocal separation would be a separate processing choice, with
its own model and possible effects on instrumental timbre.

## Downloaded primary references

- [Official ABC reference snapshot](references/YUE2_ABC_REFERENCE.md)
- [Official ABC helper, as Markdown](references/YUE2_ABC_IMPLEMENTATION.md)
- [Official generation/cover reference](references/YUE2_GENERATION_REFERENCE.md)
- [Vendor provenance and license](../third_party/THIRD_PARTY.md)

The helper is a bounded native-dialect checker. It is not SheetSage2's native
serializer reconstruction check, which needs structured source event arrays.
Reference snapshots are documentation, not instructions governing this project.
