# Reddit announcement draft — v3.1.1

Post in r/comfyui after the GitHub release is published.

The three image placeholders below are marked so you can find them with a search for
`IMAGE`. Reddit takes uploaded images (inline in the text editor) or an image/gallery
post — raw `<img>` HTML and Markdown image paths to a local file do not survive there,
so the file names are given as a reminder of which picture goes where.

- `IMAGE 1` — `assets/branding/banner.png` (1680×720)
- `IMAGE 2` — `assets/branding/screenshot-main-workflow.png`
- `IMAGE 3` — `assets/branding/screenshot-audio-enhancement.png`

## Title (pick one)

1. You can now dial exactly how far a cover may go from the original: 0–100 [Music Production Toolkit 3.1]
2. I gave my ComfyUI music toolkit a cover slider that really holds at 0 — and a fix so it stops inventing vocals [3.1]
3. YuE2 covers, now with a "how faithful should this be" slider from 0 to 100 [Music Production Toolkit 3.1]

## Post

> 🖼️ **IMAGE 1 — banner.** Insert `assets/branding/banner.png` (1680×720) here.

**3.1 is out, and it is the release I have been wanting to make since I added YuE2.**

The cover feature has grown from "load a file and hope" into something you can actually
steer, so that is what this post is mostly about. Everything runs locally in ComfyUI:
no cloud service in the middle, no account, MIT licensed.

**What the cover path does now.** SheetSage2 reads the actual musical score out of your
audio — melody, chords, phrases, sections — and everything after that works on real
notes: the toolkit plans what it will preserve and what it will change, rewrites the
score, validates the result, and only then hands it to YuE2.

**One slider, 0 to 100.** Interpretation Freedom runs from a faithful re-recording of the
same song to a free recomposition that keeps only its character. At `0` it is enforced
rather than promised: a model answer that rewrites a note, a chord, a bar or the tempo is
rejected, and a `full` cover keeps its harmony at every freedom level. And the two things
you would expect to drift do not: **more freedom never means less of the style template
you chose**, and **the words never follow the slider**.

**If you want to go deep, the advanced mode is element by element:** main melody, chorus
hook, structure, harmony, tempo and key — plus how far melody, rhythm, harmony and
structure may vary, a key shift in semitones, a tempo change, and the vocal range of the
new version.

**The words are a first-class choice now.** Keep the source transcription, supply your
own and lock them, or go fully instrumental. Instrumental is the default mode: the vocal
notes become rests, the line moves into the instrumental part and is played by the lead
instrument you pick. Because YuE2 sometimes adds vocal-like material even to a score
with no vocal notes, there is an optional check that *listens*: it transcribes the
render, counts the words, re-renders within a limit you set, and keeps the least vocal
take when none comes out clean.

**Nothing unchecked reaches the engine.** Every model answer is validated against the
native ABC dialect and the plan first; an answer that breaks the contract is replaced by
the validated deterministic score.

> 🖼️ **IMAGE 2 — main workflow.** Insert `assets/branding/screenshot-main-workflow.png`
> here. Caption idea: *the main workflow, grouped from CHOOSE to DELIVER.*

**Two workflows instead of three.** `Music_Production_Toolkit.json` is the main one —
YuE2, YuE2 Cover and MiniMax Music 3, the Cover Studio, artwork, restoration, mastering
and the release chain. `Music_Production_AudioEnhance.json` brings your own finished
recording through the same restoration and mastering, and copies your file's own tags and
embedded cover art onto both exports.

> 🖼️ **IMAGE 3 — enhancement workflow.** Insert
> `assets/branding/screenshot-audio-enhancement.png` here.

**Also in this release:** every log line now carries the date and time so a long run
reads as a timeline, a cover run names the audio file it was made from, and a bug that
stopped `original lyrics` covers before the first note is fixed. The toolkit is also
called **Music Production Toolkit** now instead of "MiniMax …" — MiniMax is one of the
models it drives, not the whole story.

**One honest caveat, because it will save you time:** the prompts are long and tightly
structured, and the cover path is the most demanding part of the toolkit. A
few-billion-parameter or heavily quantised local model can lose the thread there — a
truncated answer, invented notation, an ignored constraint. It degrades rather than
breaks (bad answers are rejected), but expect to experiment: a bigger model, a cloud
provider just for the text, or the advanced settings that make the rework simpler.

**What would you try first — a genre swap, an instrumental reinterpretation of a track
you love, or a faithful re-recording of your own song with a different sound?**

**Toolkit, setup and workflow:** [Music Production Toolkit on GitHub](https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit#readme)
**Demo songs (35 tracks, instrumental and vocal):** [Demo Songs](https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/)
**Release notes:** [3.1.1](https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit/releases/tag/v3.1.1)

Happy to answer questions about the implementation — the ABC validation, the cover
profiles and the Whisper gate are all in the repository.
