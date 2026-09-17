# MiniMax Music Production Toolkit 3.1.0

A Swiss Army knife for local music production on ComfyUI.

This release adds the **Cover Studio**, an honest **instrumental vocal check**, and
**consolidates the example workflows** into the two that are actually needed.

## Highlights

### Cover Studio: one slider for how far a cover may go

A new **Interpretation Freedom** slider runs from `0` — a faithful cover that keeps
the melody, structure, harmony, tempo and key and only changes the sound — to `100`
— a creative recomposition that keeps only the character of the original.

It is a toolkit idea, not a YuE2 setting, and it is honest about what it does:

- **The style never weakens.** More freedom means that less of the *original audio*
  survives, never that less of the *template you chose* is delivered.
- **At `0` it really is faithful.** A model that rewrites a note, a chord, a bar or
  the tempo is rejected and the untouched score is used.
- **The style you asked for always arrives.** The requested style travels into the
  rework on its own path, so the rework can never quietly replace it.
- **The words never follow the slider.** Keep the source transcription or your own
  lyrics exactly as they are, whatever the slider says.
- **The result is checked before the engine sees it.** The score is validated
  against the native ABC dialect; if the model's answer does not hold up, the
  validated deterministic result is used instead.

### Instrumental covers that stay instrumental

YuE2 can add vocal-like material to an instrumental even though the score contains
no vocal notes at all. Since that can only be heard and not promised, the toolkit
now listens: the optional **instrumental vocal check** transcribes the freshly
generated audio, and a take that still contains words is re-rendered — as often as
you allow, up to ten times.

If no take reaches your tolerance, the take with the **fewest recognised words**
is used, so a long run always ends with the best audio it produced rather than
erroring out. Every take is written to a temporary file while the run is in
progress and the words Whisper heard are logged, so you can see whether it was
humming or a full chorus — and the candidates that lost are removed.

You set how many words are still acceptable, and the check runs on the raw render,
before any EQ, mastering or encoding, so the retries stay as cheap as they can be.

### Two workflows instead of three

- **Music_Production_Toolkit.json** — the main workflow. YuE2, YuE2 Cover and
  MiniMax Music 3, the Cover Studio, and the full mastering and release chain.
- **Music_Production_AudioEnhance.json** — bring a finished recording and enhance
  it. It now carries every restoration and mastering stage of the main workflow,
  including the experimental artifact reduction and the bypass gates.

The AudioEnhance workflow also **copies your original file's tags and cover art**
onto the new export, so an enhanced version still looks like the file it came
from.

## What the toolkit does

One toolkit instead of a shelf of scripts. Everything below is part of the two
shipped workflows, and everything runs on your own machine.

- **Write a song from a description.** Pick a template or write your own brief; a
  local or cloud language model turns it into a complete song request with
  arrangement, synchronized lyrics, a title and an album-cover idea.
- **Cover an existing track.** Read the score from your own audio and render a new
  version in the style you describe - instrumental, with new words, or with the
  words that are already there.
- **Direct how far the cover may go.** One slider, from a faithful rendition to a
  free recomposition, plus an advanced mode that decides element by element what
  stays.
- **Repair and restore a recording.** De-click and de-clip, band-limited
  restoration, high-frequency repair, optional artifact reduction, automatic and
  manual EQ, sample-rate conversion and mastering to a target loudness.
- **Compare honestly.** Every processing stage can be switched off, and the run
  records what ran, what was skipped and with which settings.
- **Render artwork.** A FLUX.2 cover built from the song's own image prompt.
- **Tag and release.** Title, artist, album, track, genre and embedded cover art in
  FLAC and MP3, plus a production record and a prompt report for every run.
- **Bring your own models.** YuE2 and MiniMax Music 3 for songs, SheetSage2 for
  scores, faster-whisper for lyrics, any local or cloud language model for the
  text, and FLUX.2 for the artwork - each downloaded on demand and checked before
  a run.

Nothing leaves your computer unless you deliberately choose a cloud model for the
text.

## One default changed

The standard cover lyrics mode is now **instrumental**. It needs no speech engine
and no transcription, so a fresh install produces a cover straight away. If you
have a saved workflow from an earlier version, set the mode explicitly when you
want new or original words.

## Nothing else was taken away

Existing saved workflows keep loading. The nodes they use keep their inputs, in the
same order, with the same defaults; the new options are appended and switched off
unless you turn them on.

## Assets

- `Music_Production_Toolkit_v3.1.0.json`
- `Music_Production_AudioEnhance_v3.1.0.json`
- `ComfyUI-MiniMax-Music-Production-Toolkit-v3.1.0.zip`
- `SHA256SUMS.txt`

The previous release archives stay where they are.

## Upgrading

Replace the toolkit folder and restart ComfyUI. Load
`Music_Production_Toolkit.json` for new work; it replaces the earlier YuE2 and
MiniMax example workflows. If you have saved copies of those, they still load.
