# Troubleshooting

## Cover source is red and shows UNKNOWN inputs

The first cover integration omitted the preview widget required by ComfyUI's
native audio uploader. Version 3.0 includes the frontend fix. Update the full
toolkit including `web/song_model.js` and `web/song_model_utils.js`, then reload
the browser and reopen the workflow. A successful node registration in the
backend alone does not establish that the browser can construct the node.

## YuE2 Cover cannot transcribe the source

Select an audio file in SOURCE AUDIO and confirm the host has native
`AudioEncoderLoader` and `SheetSage2AudioToABC`. Enable `yue2_models`,
`sheetsage2_models` and `auto_download` to obtain the default encoder if missing,
or install it in `models/audio_encoders`. Custom filenames require matching
installed files. An empty ABC transcript stops the run; try a different source
or inspect the native SheetSage2 error. SheetSage2 extracts music, not lyric words.
Use the **Cover lyrics** modes to decide what should happen to the vocals; see
[docs/YUE2.md](docs/YUE2.md#cover-lyrics-modes).

The source mode controls both transcription and generation. Editing `yue2_mode`
in Music settings affects new songs; use SOURCE AUDIO for cover full/melody mode.

## Cover lyrics transcription fails or produces no words

**`'English' is not a valid language code`.** Update the toolkit and restart
ComfyUI. The Whisper wrapper now converts common language names (English → en,
German/Deutsch → de) and normalizes code casing before loading or decoding.
Unknown names fail immediately with guidance; invalid input is not retried on
CPU. In older installations, select **en** directly. This field describes the
source recording's language, not the language requested for new cover lyrics.

**VAD removes nearly the entire song.** **vad_filter=false** is now the song
default. Older saved workflows with VAD enabled automatically retry the complete
audio without VAD if less than half survives or no segments are found. The log
and report record the retry and effective settings. The reported 207-second
source previously retained only 7.3 seconds and produced 40 characters; such an
obvious opening-only fragment now stops before generation if the retry cannot
recover it. Review the words for recognition errors and hallucinations.

**New lyrics seems stuck before the LLM.** That stage includes Whisper too.
Inference now runs in an isolated, cancellable process, with progress every 15 s.
A GPU stall times out after 180 s without progress and retries on CPU; CPU gets
600 s without progress. The total limit is at least 20 minutes, scaled for long
sources. No partial transcript is accepted. See the [Whisper node](web/docs/MusicCoverLyrics.md).

**`faster-whisper` is not installed.** The error names
`requirements-whisper.txt`. Install it into the same Python environment as
ComfyUI, restart, and run the model check again. Choose **instrumental** to cover without Whisper; both lyric-bearing modes
use it in the bundled workflow.

**The checkpoint folder is missing.** Enable `whisper_models` in the model check
node and run it once with **Cover lyrics = new lyrics or original lyrics**; it downloads the
pinned `whisper-large-v3` files into
`models/audio_encoders/whisper-large-v3`. The node's **Whisper model** field must
match that folder name. Additional CTranslate2 checkpoints need a matching catalog entry for the model dropdown.

**The transcription is wrong-language, repeated or empty.** Set **language** to
the language actually sung instead of `auto`, try **vad_filter=false** if singing was omitted (speech detection may miss it), keep **condition_on_previous_text** off (carrying text
between chunks can repeat a line), and prefer the full `whisper-large-v3`
checkpoint over any smaller one. Whisper was not trained on singing and
accompaniment reduces accuracy; hallucination over instrumental sections is a
documented failure mode. For a cleaner read, separate the vocals first (for
example with Demucs `--two-stems=vocals`) and use that stem as the cover source
for a separate lyrics transcription. Keep the full mix as the musical
cover source; otherwise SheetSage2 loses the accompaniment.

**The GPU path fails.** `device = auto` falls back to CPU with int8 precision
when CUDA cannot run the checkpoint; the report records which device actually
ran. On Windows, CTranslate2 needs cuBLAS and cuDNN 9. `device = cpu` forces the
working path. The worker exposes installed Torch/NVIDIA DLL directories on
Windows; if those libraries are still missing/incompatible it falls back to CPU.
After a CUDA runtime failure, further `auto` runs stay on CPU until ComfyUI
restarts. Explicit `cuda` requests can retry a repaired GPU installation.

**Instrumental covers still contain voice-like sounds.** The score's Vocal notes
are muted and its lead transferred to Ins. The native YuE2 Lyrics input is now
limited to empty section tags. Native Style uses musical tags, excluding the
narrative production plan that was audible in the reported run. Native ABC
headers are preserved. This strengthens conditioning but cannot guarantee voice-free audio.
Listen to a new render; previously generated audio is unchanged.

**The final lyrics barely contain the transcribed words.** The parser records a
`lyrics_word_coverage` ratio in the production JSON. A low value means the LLM
replaced the transcription instead of distributing it; check the prompt report
and the system prompt in use.

## Toolkit nodes do not appear

Check the ComfyUI console for `IMPORT FAILED`. Install this package's `requirements.txt` into the same Python environment that runs ComfyUI, then restart completely.

## The console reports a missing engine or dependency

The toolkit prints one line per missing engine as soon as it loads, with the exact command, for example:

```text
Optional engine not installed: faster-whisper (Whisper engine). Without it, cover lyrics
mode 'original lyrics' and the instrumental vocal check is unavailable ...
Install with: python -m pip install -r requirements.txt
```

It also warns when a *required* package is missing, because the toolkit cannot run
correctly without it. Install into the environment that runs ComfyUI (not a system Python),
then restart ComfyUI. `install_requirements.bat` finds a nearby venv or a portable Python
for you. See [dependencies](INSTALLATION.md#toolkit-python-dependencies).

## Not enough VRAM or RAM, or it is too slow

Every supported lever is listed together - a non-local LLM, a smaller model, shorter
songs, no artwork, skipping the restoration chain, fewer steps and the cost of the
instrumental vocal check. See
[if something is missing, too small or too slow](INSTALLATION.md#if-something-is-missing-too-small-or-too-slow).

## Prompt-file dropdown is empty

- For `bundled_library`, verify the repository still contains `prompts/user/` and `prompts/system/`.
- For `external_directory`, enter a directory on the **ComfyUI server machine**, not a path that exists only on another browser/client computer.
- Supported files are `.txt`, `.md`, `.prompt`.
- Click **Refresh prompt lists**.
- Hard-refresh the browser after upgrading the toolkit.

## I edited a prompt file but the old output was reused

The toolkit fingerprints selected prompt-file contents, so the template node should invalidate automatically. If the *external LLM node* itself is cached, use `LLM Session ID / Cache Buster` with control-after-generate set to Randomize or Increment.

## External LLM model is missing

The example GGUF filename is not a bundled dependency. Install/select a compatible llama.cpp GGUF in `models/llm` (or configure a download URL in `models_config.json`). The integrated LLM node needs `llama-cpp-python` installed in the ComfyUI Python environment.

## `LLM prompt exceeds the ... token budget`

The parser node stops instead of cutting the prompt, because with `trim_long_prompt` off an oversized Caption+Lyrics is an error. The message names the measured count and the budget. Real cover productions measure 610-1707 tokens for Caption+Lyrics, so keep `max_prompt_tokens` at its 4500 default (4800 maximum) and shorten redundant Style wording rather than enabling trimming - trimming drops cover lyrics or ABC sections. Measured demand and the recommended LLM budgets are listed in `INSTALLATION.md` section 5.

## The LLM answer stops mid-sentence

Two independent caps can end it: `max_tokens` (the node's response cap) and `n_ctx` (the context window that prompt, response and thinking share). A response cap larger than `n_ctx` minus the prompt is cut by the runtime, not by the node, so the pair has to fit: the bundled values are `max_tokens = 24576` and `n_ctx = 37376`, which hold the largest measured prompt (~11.6k tokens) plus a maximum-length answer (36166 tokens in total). If you raise `max_tokens`, raise `n_ctx` by at least the same amount - in multiples of the widget step of 256.

## FlashSR code or weights are missing

Since v2.0.0 FlashSR is integrated (`MiniMaxFlashSRAudio`). Missing code/weights are downloaded automatically on first use when `auto_download` is enabled; see `models_config.json`. With auto-download disabled, place the files under `models/audio/flashsr/` manually.

## FFmpeg/loudness error

The package first looks for a system `ffmpeg`, then falls back to the executable provided by `imageio-ffmpeg`. Reinstall requirements if neither is available.

## Audio export fails with a blank `AssertionError`

A traceback ending in `SaveAudioSmartPrefix.save`, `sf.write(...)`, and
`soundfile.py: assert written == len(data)` means the audio encoder returned a
short write. It does not by itself identify an LLM failure. In the reported
run, LLM generation, cover generation and the music sampler had completed;
the failure occurred during the source FLAC export after audio VAE decoding.

This exact empty assertion was reproduced with NaN audio using SoundFile 0.13.0
and libsndfile 1.2.2, for both 16-bit and 24-bit FLAC. NaN also defeats a normal
peak comparison; Infinity can become NaN when peak normalization multiplies it
by zero. The original run's waveform/latents were not captured, so the traceback
alone cannot prove where invalid values originated or exclude a separate codec
or disk problem. Switching formats is not a repair for invalid audio.

The toolkit now provides two protections:

1. **MiniMax Safe Audio Decode**, included in both decoder branches of the
   production subgraph, validates sampler latents and decoded audio. When only
   decoding fails numerically, it retries once with conservative tiles using
   the same latents. It never replaces bad samples with silence.
2. **Both Save Audio nodes** check all samples in the entire batch before
   normalization or file writing. A remaining SoundFile short-write assertion
   becomes a message containing the encoder format, sample rate and library
   versions, while the incomplete staging file is removed.

Apply the update to the toolkit folder that **your running ComfyUI actually
loads** (`ComfyUI/custom_nodes/ComfyUI-MiniMax-Music-Production-Toolkit`), then
fully restart ComfyUI and open the updated production example. A separate Git
working copy does not update that installed folder automatically. The update
includes new `audio_decode.py` and `audio_file_io.py` modules, package
registration, shared audio validation and both audio savers; copying only a
single saver file is insufficient. Models do not need to be downloaded again.

For personal workflows, replace `VAEDecodeAudio` and `VAEDecodeAudioTiled`
inside the music subgraph with **MiniMax Safe Audio Decode**, keeping LATENT,
VAE and AUDIO connections. Use `tiled = false` for the former normal decoder;
use `tiled = true` and retain your tile size/overlap for the tiled decoder.
An already open/saved workflow is not rewritten automatically by a code update.

If the new error says:

- **Music sampler latents**: the invalid values already came from music
  sampling. Rerun that stage and check the diffusion model, settings and
  precision; decoding cannot recover these latents.
- **Retry also failed / incoming latents were finite**: check the audio VAE
  file and the ComfyUI decoder/backend. The automatic retry is deliberately
  limited and cannot repair invalid weights or every numerical failure.
- **Save Audio ... NaN or Infinity**: invalid audio reached the saver. Verify
  that the checked decoder is in the graph, then inspect subsequent processing
  if decoding succeeded.
- **Encoder wrote fewer samples than requested**, with valid audio: check
  destination free space and the SoundFile/libsndfile installation used by
  ComfyUI. Include the new diagnostic and full traceback in a bug report.

## Long batch fails with CUDA graph / allocator errors

This is normally a ComfyUI/PyTorch/CUDA/model interaction rather than the prompt toolkit itself. Restart ComfyUI after a CUDA capture failure. If the error specifically mentions `CUDAMallocAsyncAllocator` / stream capture invalidation, testing ComfyUI with `--disable-cuda-malloc` can help isolate allocator/capture instability. Expect a possible performance trade-off.

## MiniMax Music 3 sounds distorted, or the next run returns NaN/Infinity

There are two different failure classes here; they need different remedies.

**Incoherent audio with finite values.** ComfyUI 0.35 enables its
compiler/CUDA allocation graphs by default. MiniMax Music 3 combines those
graphs with dynamic layer loading, and the AR text encoder's graph replay can
then emit corrupted conditioning even though every number is technically
finite (`graph breaks: 0, rogues: 0` looks clean; upstream report:
Comfy-Org/ComfyUI#16222). The toolkit keeps the normal performance profile by
default. Set `MINIMAX_MUSIC3_RUNTIME_SAFETY=auto` to disable CUDA graph capture
automatically only on a backend marked risky (Blackwell-class CUDA or ROCm),
`=on` to force it on any backend, or `=strict` to disable the allocation
compiler as well. Disabling graph capture keeps the faster allocation compiler
active and is the cheapest fix for this class.

**Non-finite latents reported by the sampler.** The MiniMax Music 3 diffusion
model runs in fp16 with the official fp16 checkpoint. For some
seed/prompt/length combinations the fp16 DiT path then writes non-finite
latents for the whole track at once; that is reproducible for the same seed and
is *not* fixed by disabling CUDA graphs or the compiler (upstream report:
Comfy-Org/ComfyUI#16249). The sampler therefore fails immediately instead of
repeating the identical sampling, which could only reproduce the same values.
No node can change this afterwards: ComfyUI picks the dtype while the
checkpoint loads (`unet_dtype` / `unet_manual_cast`), so only launch flags or a
new seed change the outcome. Measured with ComfyUI's own logic on an RTX 5060 Ti
(16 GiB), with the official fp16 DiT and the FLUX.2 Klein cover:

| Launch flags | MiniMax DiT (fp16 checkpoint) | FLUX.2 cover (bf16 checkpoint) |
| --- | --- | --- |
| none | float16 - the path that fails | bfloat16, unchanged |
| `--bf16-unet` | bfloat16 | bfloat16, unchanged |
| `--fp32-unet` | float32 | float32, about twice the VRAM |

Experiments, cheapest first:

1. **`--bf16-unet`** - the only flag that changes the DiT without touching the
   cover model, and it is VRAM-neutral (bf16 keeps fp32's exponent range, so the
   fp16 overflow/underflow class disappears). Not verified by upstream, but the
   cheapest real chance.
2. **`--fp32-unet`** - upstream-verified for this class. It also switches the
   FLUX.2 cover to fp32, so on a 16 GiB card switch the cover off
   (`FLUX.2 cover - ON / OFF`) for that test. Expect it to be much slower.
3. **Queue the prompt again** - a new seed often succeeds, because the defect
   depends on the seed/prompt/length combination.
4. If neither flag helps, separate the remaining classes:
   `MINIMAX_MUSIC3_RUNTIME_SAFETY=on` (rules out the graph-replay class of
   Comfy-Org/ComfyUI#16222) and `PYTORCH_NO_CUDA_MEMORY_CACHING=1` (the
   allocator/unwritten-memory observation in #16249; expect it to be slower).

`KSamplerWithConfig` retries once for backend/capture *errors* (a `RuntimeError`
mentioning capture, CUDA graphs, NaN or Infinity): that class is a state
problem, so clearing the captured state and repeating the sampling can help.
It never replaces bad audio with silence and never passes non-finite latents to
the decoder.

If a clean run is still not possible, start ComfyUI with:

```text
--disable-comfy-compiler --disable-cuda-graphs --fp32-unet
```

The first two flags are the strict compatibility test and are expected to be
slower. `--fp32-unet` addresses the fp16 diffusion path (overflow or reads of
unwritten memory) and costs more VRAM/time. If the machine cannot hold the FP32
diffusion model, use the official MiniMax INT8 diffusion model or a BF16-capable
model instead. The default toolkit mode is `MINIMAX_MUSIC3_RUNTIME_SAFETY=off`,
which preserves the original ComfyUI performance.

## Cymbals/hi-hats sound watery after FlashSR

A/B these changes one at a time:

1. lighter PRE filter or PRE bypass;
2. `Original SRC only` versus FlashSR;
3. lower `flashsr_hf_mix` in Hybrid Crossover;
4. `HF Cymbal / Shimmer Repair = Gentle`;
5. stronger HF repair only if necessary.

Do not assume that more reconstructed bandwidth sounds more natural.

## Quiet tracks change level unexpectedly

`Audio Release Prep` uses static full-program gain only. If you hear time-varying pumping, verify you are running the current toolkit version and that no additional compressor/limiter/loudness node exists elsewhere in the graph.


## `No link found in parent graph ...`

If ComfyUI reports a message such as `No link found in parent graph for id [37:6] slot [0] unet_name`, the workflow contains a broken serialized subgraph boundary link. Version 1.0.1 fixes the affected v1.0.0 example workflow. Use the v1.0.1 example workflow or later. This is a workflow-serialization issue, not a missing MiniMax model file.

## No JSON appears beside the FLAC/MP3 files

That is expected in the current workflow. Since v1.0.4, the example no longer writes duplicated per-audio sidecars. Look in the directory configured by **MiniMax Output Paths → configuration_subdir** (default `log/`).

The final `Save Production JSON` node must be connected to the three audio savers' `save_info_json` outputs and the saved artwork path.

## Final production JSON is not created

Check the ComfyUI error log for the first failed upstream save. The central JSON intentionally runs only after the original audio, release FLAC, release MP3 and artwork save dependencies complete. If one of those files fails to save, the final JSON is not written, preventing a misleading configuration record that claims missing artifacts exist.

Also verify that `configuration_subdir` is writable and that `create_directories` is enabled on `Save Production JSON`.

## SoundCloud players do not show on the GitHub README

Use the supplied GitHub Pages template instead of trying to embed an iframe directly in README Markdown. Add normal SoundCloud URLs to `docs/demo-tracks.js`, then enable Pages from the repository's **Settings → Pages** using the `main` branch and `/docs` folder.


## External LLM returns empty text after a native access violation

If the LLM runtime (the legacy `ComfyUI-LLM-Session` node or any other backend) logs a native `access violation` and the downstream parser then reports missing `[Caption]` / `[Lyrics]`, the parser error is secondary: it received an empty assistant response. First fully restart ComfyUI; if the native backend remains in a bad state, a full machine restart can clear stale CUDA/llama.cpp state. Only investigate the parser if the LLM node actually returns non-empty text. The integrated `MiniMaxLLMChat` raises its own clear error on empty generation output, so an empty-string parser error cannot mask the upstream failure.

## Save Cover JPG reports invalid `collision_mode` or wrong `jpeg_quality` type

This was a workflow-serialization issue in the first v1.0.5 example workflow, not an image-quality or Pillow problem. The `title` and `audio_tags_json` sockets had been inserted ahead of the existing widget-backed inputs in the saved JSON, while the Python node schema still expected `collision_mode`, `create_directories`, and `jpeg_quality` first. ComfyUI therefore associated saved widget values with the wrong slots.

Use the v1.0.6-or-newer example workflow or recreate the `Save Image Smart Prefix` node and reconnect `image`, `filename_prefix`, `title`, and `audio_tags_json`. In the corrected workflow the visible values are `collision_mode = auto_increment`, `jpeg_quality = 95`, and `filename_mode = album - title`.
## I committed new demo tracks but GitHub Pages still shows the old page

A local `git commit` does not update GitHub. Run `git push`, then check **GitHub → Actions** for the Pages deployment. If the deployment is green but the browser still shows the old catalog, hard-refresh (`Ctrl+F5`) or test in a private window because `demo-tracks.js` may still be cached. LF→CRLF warnings from Git on Windows are harmless.

## I accidentally deleted the local `.git` folder

If the project files are still intact and the remote repository contains the history, recreate only the local Git metadata:

```powershell
git init -b main
git remote add origin https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit.git
git fetch origin
git reset --mixed origin/main
```

Use `--mixed`, not `--hard`, so current working files are preserved. Then inspect `git status`, commit the intended local differences and push normally.
