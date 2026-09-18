# Music Production Toolkit 3.1.1

A Swiss Army knife for local music production on ComfyUI.

A patch on top of 3.1.0: one cover stopper fixed, every run now logged with its date,
time and source file, and fresh branding for a toolkit that is no longer MiniMax only.

## The cover feature is the highlight

**Turn an existing track into your own version of it — with as much or as little
control as you want.** SheetSage2 reads the actual musical score out of your
recording, and everything after that works on real notes.

- **One slider, 0 to 100.** From a faithful re-recording to a free recomposition that
  keeps only the character. At `0` the source score is *enforced*: a model answer that
  rewrites a note, a chord, a bar or the tempo is rejected, and a `full` cover keeps
  its harmony at every freedom level.
- **Advanced mode, if you want it.** Element by element: main melody, chorus hook,
  structure, harmony, tempo and key, plus how far melody, rhythm, harmony and
  structure may vary, a key shift in semitones, a tempo change and the vocal range of
  the new version.
- **The words never follow the slider.** Lock the source transcription or your own
  lyrics and they stay exactly as they are.
- **Instrumental that stays instrumental.** The notes that carried the vocals move
  into the native instrumental part and are played by the **lead instrument** you
  name, while the vocal line becomes rests. If you want proof, the optional vocal
  check transcribes the render, counts the words and re-renders within your limit —
  keeping the least vocal take when none is clean.
- **The style you chose always wins.** More freedom means that less of the *original
  audio* survives, never that less of *your* template is delivered.
- **Nothing unchecked reaches the engine.** Every model answer is validated against
  the native ABC dialect and the plan first; an answer that breaks the contract is
  replaced by the validated deterministic result.

The minimum is a file, a style and a queue. Everything else is optional and off the
critical path.

## Fixed in 3.1.1

**`original lyrics` covers stopped before the first note.** The bundled workflow
carried the toolkit's own "field not set" placeholder in the Whisper node's language
field — a value that node never offers — and the run aborted with

```text
YuE2 Cover: unsupported Whisper source language 'custom'
```

before a single frame was decoded. The shipped workflow now stores `auto`, and a
workflow test refuses any stored value the node does not offer. A misspelled language
is still rejected — transcribing in the wrong language silently would be worse — but a
saved workflow from an earlier version that still carries the old placeholder now
auto-detects instead of stopping.

## Your runs are easier to follow now

- **Every log line carries the date and time** (`2026-09-18 14:22:31 Saved artwork: …`),
  so a ComfyUI log reads as a timeline: when a run started, how long a stage took,
  which result belongs to which attempt.
- **A cover run names the audio file it was made from** — the file, its full path, its
  size and the three cover choices, once when the file is selected and again for every
  generated song. The exports only carry the derived `<name>-cover` title, so the log
  is what tells you what a run was built on later.
- **Documented, not mysterious:** the `_ProactorBasePipeTransport` error a long Windows
  run can print is CPython reporting a dropped client connection — usually the browser
  tab that queued the prompt. The run and its files are unaffected. See
  [troubleshooting](TROUBLESHOOTING.md).

## Branding for more than MiniMax

The toolkit has grown past its name: YuE2, YuE2 Cover and MiniMax Music 3 live side by
side, and the new banner and icon say so. The README now pictures both workflows where
they are described — the main workflow end to end, and the audio-enhancement workflow
that carries every restoration and mastering stage of the main one.

## Assets

- `Music_Production_Toolkit_v3.1.1.json`
- `Music_Production_AudioEnhance_v3.1.1.json`
- `ComfyUI-MiniMax-Music-Production-Toolkit-v3.1.1.zip`
- `SHA256SUMS.txt`

The previous release archives stay where they are.

## Upgrading

Replace the toolkit folder, restart ComfyUI and refresh the browser. Re-import the two
bundled workflows if you keep your own copies: 3.1.1 corrects one value in the main
workflow (the Whisper node's language field now reads `auto`). Everything else loads
unchanged — no node input was renamed, reordered or removed.
