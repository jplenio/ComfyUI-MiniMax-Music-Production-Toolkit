# Cover song · source lyrics / phrasing (Whisper)

Runs only for **YuE2 Cover** with **new lyrics** or **original lyrics**.
The first uses original words/timestamps as a phrasing reference for new words;
the second preserves the transcribed words. Instrumental and other models skip it.

Install `requirements-whisper.txt` into ComfyUI's Python environment. The model
check's `whisper_models` / `auto_download` switches obtain the pinned large-v3
CTranslate2 files under `models/audio_encoders/whisper-large-v3` when needed.
Additional model choices come from the catalog. No comparative singing-quality
benchmark is claimed for this checkpoint.

Controls: source language (auto or explicit), device/precision, beam size,
VAD and previous-text conditioning. Both are off by default for songs. If you
enable VAD and it retains less than half the audio or returns no segments, the
node retries the complete audio without VAD. The report records both attempts
and requested/effective settings. Review the words: unfiltered music can also
cause hallucinations. Empty text or an obvious opening-only fragment (audio
>=60 s, fewer than 12 words, last segment before 20% of the song) stops generation
with guidance; this is a heuristic, not a completeness certificate.

Inference runs in a separate local process with progress messages every 15 s.
Cancel terminates that process and discards partial text. A stalled GPU worker
times out after 180 s without progress; CPU after 600 s. The total limit is the
larger of 20 minutes or 20 times the source duration. CUDA runtime failures or
timeouts retry once on CPU/int8; input errors and cancellation do not. Subsequent
`auto` runs use CPU for that ComfyUI session after a CUDA failure. Restart or
explicitly select `cuda` after repairing the GPU libraries. Installed Torch/NVIDIA
DLL directories are exposed inside the Windows worker; no libraries are installed.
The child exits and releases its weights before the music stage.

The source language accepts codes such as `en`/`de` and common names such as
`English`, `German` or `Deutsch`, normalized before model loading. The field offers
`auto` or a concrete language and has no placeholder choice: a cover that never
chooses one auto-detects. A legacy saved workflow can still carry the toolkit's
`custom` placeholder here; that counts as auto-detect and is logged as such, while a
real value Whisper does not know is refused. Invalid input does not cause a pointless
CPU retry. The report preserves both the requested language and the effective code.
VAD retained duration/fraction describes the initial filtered attempt; `vad_filter`
describes the accepted attempt.

Outputs: `cover_lyrics` is plain text; `lyrics_report_json` includes that text,
segment/word timestamps and engine settings. **Connect the report output to the
Structured Song Prompt and parser** to retain timing evidence, as the bundled
workflow does. Production JSON stores it under `cover.lyrics_source`.

Original mode restores source words at measured section times after the LLM,
then verifies the complete ordered word sequence. Correct a bad source
transcription by connecting reviewed text to the prompt/parser's `cover_lyrics`
inputs in a custom graph. New mode writes different words, using source phrase
lengths and rests as guidance. Neither Whisper nor the score guarantees exact
audio synchronization. See [cover guide](../../docs/YUE2.md#cover-lyrics-modes).
