# Cover song · SheetSage2 transcription

Expands native LoadAudio, AudioEncoderLoader and SheetSage2AudioToABC only when
**YuE2 Cover** is selected. The model-check report input ensures configured
downloads finish before the encoder is loaded. Other models return an empty
string without loading source audio or SheetSage2.

Connect `cover_abc` to *Cover song · instrumental score / phrase map*. That node adapts the
score to the selected cover lyrics mode - an instrumental cover rewrites the
vocal melody line into an instrument part - and the LLM and the native generator
both receive that adapted score. For the two lyric-writing modes the score is
handed through unchanged, and no new ABC is generated in this mode.

SheetSage2 extracts music, not the original sung words: the score carries two
melodic voices (`Vocal` and `Ins`), structure labels and chord symbols, but no
lyric text. Use the *original lyrics* cover mode (Whisper) to transcribe the
original words, or supply words in the brief. An empty transcription stops the
cover run with an error.

## Inputs

- **model_profile_json** - decides whether anything is transcribed at all: only a YuE2 Cover
  profile loads the source audio.
- **cover_source_json** - the selected file and the shared transcription/generation mode.
- **model_check_report** - SheetSage2 preflight result, so a missing model is reported before
  the load is attempted.

Other song models load nothing, which keeps a new-song run independent of the source audio.
