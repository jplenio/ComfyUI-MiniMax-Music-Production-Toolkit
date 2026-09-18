# Installation

For the **YuE2 Cover** option, use a ComfyUI build that also exposes
`AudioEncoderLoader` and `SheetSage2AudioToABC`. The Selected song model check
can download `sheetsage2_bf16.safetensors` into `models/audio_encoders` when
YuE2 Cover is selected and `sheetsage2_models` / `auto_download` are on.
Restart ComfyUI and reload the workflow after updating the toolkit.

For a red Cover source node with `UNKNOWN` inputs, install the audio-preview
frontend fix (`web/song_model.js` and `web/song_model_utils.js`), then reload
the browser and reopen the workflow. The initial cover integration enabled
native audio upload without creating its required preview widget. Clearing the
cache alone cannot fix that version. A successful backend registration does
not exclude an error while the browser constructs the node.

**Version 3.0:** Open [Music_Production_Toolkit.json](example_workflows/Music_Production_Toolkit.json) for YuE2, YuE2 Cover or MiniMax. CHOOSE controls the song mode, artwork, refinement and mastering; SOURCE AUDIO supplies a cover track. See [the song and cover guide](docs/YUE2.md). The classic MiniMax workflow below retains its existing processing chain.

This document separates **toolkit requirements** from the model files used by the full example workflow. Since v2.0.0 the example workflow no longer needs any external custom nodes: FlashSR and the LLM chat are integrated into this toolkit.

## 1. Install the toolkit

Clone into `ComfyUI/custom_nodes/`:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit.git
cd ComfyUI-MiniMax-Music-Production-Toolkit
```

Install dependencies with the **same Python interpreter that runs ComfyUI**.

Typical venv installation on Windows:

```powershell
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you use ComfyUI Portable, use its embedded Python. `install_requirements.bat` attempts to locate a nearby ComfyUI venv or portable Python automatically.

### Toolkit Python dependencies

One command installs everything the toolkit can use:

```bash
python -m pip install -r requirements.txt
```

- **NumPy** (`>=1.26`) - array and DSP math.
- **SciPy** - filtering and high-quality polyphase resampling.
- **SoundFile** - FLAC/WAV audio I/O.
- **imageio-ffmpeg** - FFmpeg fallback for MP3 encoding and loudness/true-peak measurement.
- **Mutagen** - FLAC/MP3/WAV metadata and cover embedding.
- **Pillow** - cover-art resizing and JPEG encoding.
- **faster-whisper** - the Whisper engine for cover lyrics and the instrumental vocal
  check. It pulls CTranslate2, PyAV, ONNX Runtime and Tokenizers.

PyTorch is expected from ComfyUI and is deliberately never replaced by this package.
A fresh environment resolves this list into 31 packages without a conflict and without
touching the installed PyTorch stack (verified with `pip install --dry-run --ignore-installed`).

**Optional extras that each improve one thing** (safe to omit, both are reported at startup
when missing):

```bash
python -m pip install psutil soxr
```

- **psutil** - real free-RAM figures in the resource report; without it the toolkit falls
  back to a Windows-only RAM query and reports no VRAM figures.
- **soxr** - high-quality resampling inside the FlashSR chain; without it SciPy's
  polyphase resampling is used instead.

**Minimal install, without the Whisper engine.** If you never use the `original lyrics`
cover mode and never use the instrumental vocal check, install only the core:

```bash
python -m pip install numpy scipy soundfile imageio-ffmpeg mutagen Pillow
```

Nothing else changes: the toolkit logs which engine is missing and how to add it later
(`python -m pip install -r requirements-whisper.txt`).

**Check the installation before the first run.** When the toolkit loads, the ComfyUI
console gets one line per missing engine:

```text
Optional engine not installed: faster-whisper (Whisper engine). Without it, cover lyrics
mode 'original lyrics' and the instrumental vocal check is unavailable (the other cover
modes and every non-cover path still work). Install with: python -m pip install -r requirements.txt
```

A complete installation logs `All optional engines are installed; every feature is available.`
A missing *required* package is logged as a warning naming `requirements.txt`, because the
toolkit cannot run correctly without it. If you see that, install with the same Python
that runs ComfyUI - `install_requirements.bat` finds a nearby venv or portable Python for you.

### Cover lyrics transcription (Whisper)

Bundled with `requirements.txt`. The YuE2 Cover workflow uses Whisper for **new lyrics**
(source phrasing), **original lyrics** (source words) and the optional **instrumental
vocal check**. Instrumental-only and other song models do not need it.

```bash
python -m pip install -r requirements-whisper.txt   # only needed on an older install
```

Enable `whisper_models` and `auto_download` in the model check for a text-bearing
cover to obtain the pinned large-v3 files in `models/audio_encoders/whisper-large-v3`
(about 2.9 GB). For custom graphs, a reviewed transcript can instead be wired to
the prompt/parser's `cover_lyrics` inputs; see [cover modes](docs/YUE2.md#cover-lyrics-modes).

### Integrated LLM chat

The LLM node also supports **Local app / server** and **Cloud service** modes.
Those modes do not require llama-cpp-python or a GGUF in ComfyUI. Start your local
app's API server or configure a cloud API key, then select a model on the node.
See [docs/LLM_PROVIDERS.md](docs/LLM_PROVIDERS.md) for supported apps, addresses and setup.
The GGUF requirements below apply only to **In ComfyUI (GGUF)**.

`MiniMaxLLMChat` uses the public `llama-cpp-python` API:

```bash
python -m pip install llama-cpp-python
```

It is not in `requirements.txt` on purpose: there is no single wheel that fits every
CUDA/ROCm/CPU setup, and the two other LLM modes need no local runtime at all. When it is
missing, the node still registers, the startup report names it, and the execution error
repeats the command. Provide a llama.cpp-compatible GGUF in `ComfyUI/models/llm/` (or
configure a download URL in `models_config.json`).

### If something is missing, too small or too slow

The bundled example is deliberately demanding. Every item below is a supported change,
not a workaround.

**A dependency is missing**

- The startup line names the engine and the command. Install into the environment that
  runs ComfyUI (**not** a system Python) and restart ComfyUI.
- `python -m pip list` in that environment shows what is actually installed.
- Nothing is downloaded by `pip` for the models; those go to `ComfyUI/models/…` and are
  handled by the model check (section 2).

**Not enough VRAM**

- **Use a non-local LLM.** `Local app / server` or `Cloud service` needs no local LLM
  VRAM at all, and the text stage is where a big model sits idle most of the time.
- **Smaller LLM.** Section 5 lists candidates per card size. Keep the context at
  `n_ctx = 37376` or at least above ~16000: the production system prompt alone is about
  11.6k tokens, so a smaller window truncates the request instead of saving memory.
  A smaller *model* or a lower quantization is the lever, not the context.

  Expect to experiment here. The text side is the hard part, and the cover path feels it
  first: it hands the model the source score, the arrangement plan and the style template
  together and asks for a complete rewritten score back, so a few-billion-parameter or
  heavily quantised model can lose the thread - a truncated answer, invented notation, an
  ignored constraint. A plain song request is easier, and the audio-enhancement workflow
  needs no language model at all. Keep `max_tokens` at `24576` for the same reason: a
  budget that is generous for a caption can be too small for a rewritten score. What the
  toolkit does about it: an answer that breaks the notation contract is rejected and the
  validated score is used instead, so a weak model degrades the result rather than
  corrupting it - it cannot, however, rescue a cover it never managed to write. If a small
  model keeps failing on that path, try a more capable one, a cloud provider for the text,
  or the advanced settings that make the rework simpler. See
  [Built for different computers](README.md#built-for-different-computers).
- **YuE2 instead of MiniMax Music 3.** YuE2 3B bf16 is far lighter than the MiniMax
  DiT + text encoder pair.
- **Shorter songs.** `Length` in the prompt and `max_duration` / `yue2_max_duration` in
  Music settings shrink the latent the model has to hold.
- **No artwork.** Turn cover artwork off: FLUX.2 at 1536 px is one of the heaviest steps,
  and the audio export continues without it.
- **Skip the restoration chain.** The PRE low-pass, FlashSR, crossover and HF repair
  stages are optional; de-clip and mastering work without them.
- **Tiled VAE decode is already on.** It keeps the decode step's peak memory low; a
  smaller `tile_size` lowers it further.

**Not enough system RAM**

- Audio buffers scale with song length and sample rate: shorter songs, and the
  enhancement workflow instead of a full generation.
- The resource report logs the free RAM it measured; close other applications that hold
  several GB before a long run.
- Mastering, EQ and analysis run on the CPU and need RAM, not VRAM - with little memory,
  skip the manual EQ editor and the artifact reduction, which both hold extra buffers.

**It runs, but too slowly**

- **The instrumental vocal check is the most expensive optional stage**: one Whisper pass
  per take, and every retry is a full re-render. `instrumental_max_retries = 0` keeps a
  single check, switching `instrumental_check` off removes it entirely.
- **Fewer steps.** `yue2_steps` (32) and `minimax_steps` (40) trade time for detail.
- **Shorter songs** help more than any sampling tweak.
- **Skip stages you do not need:** FlashSR and HF repair, refinement, Artifact Reduction,
  Auto-EQ analysis, the artwork branch.
- **A smaller Whisper model** for the check or the lyrics, when the pinned large-v3 is the
  bottleneck: set `whisper_model` on the check, or the matching field on the transcription
  node. Quality of the word check drops with the model size.
- **Cloud LLM for the text**, local models for audio: the LLM stage is a large part of the
  wall time on a single GPU and does not need the GPU at all in the other two modes.

**A model file is missing** (not a Python package): section 2 covers the preflight, the
commit-pinned catalog and manual placement.

## 2. Model files and auto-download

`models_config.json` in the toolkit folder lists every model file the example workflow references, its target folder and its source. Each artifact is pinned to a verified repository **commit** and an exact byte size:

- **Preflight first (recommended).** `MiniMaxModelAutodownload` reports what is present, what is missing, how many bytes that is and whether the volume can hold it — and downloads only when its `auto_download` toggle is on. The same action is available outside the graph:

  ```bash
  # report only (never transfers):
  curl http://127.0.0.1:8188/minimax_music_toolkit/model_preflight
  # report + download (the explicit setup action):
  curl -X POST http://127.0.0.1:8188/minimax_music_toolkit/model_preflight -d '{"download": true}'
  ```

  Neither the nodes nor their `INPUT_TYPES` ever touch the network at load time; the transfer only starts when you ask for it.
- **Downloads are resumable and verified.** An interrupted transfer keeps a partial that a later run continues (HTTP range/ETag), retries transient failures, and publishes the file only after its size (and hash, where one is recorded) checks out. `Retry-After` is honoured; a 401/403/404 fails immediately instead of retrying.
- The **MiniMax Music 3** files and the **FLUX.2 Klein** files are publicly readable in the Comfy-Org mirrors; no token is needed for those. A gated source would be reported separately, with its permission problem named.
- The FlashSR **inference code is bundled** in `flashsr_inference/` (see [attribution](flashsr_inference/NOTICE.md)); only its three weights (`student_ldm.pth`, `sr_vocoder.pth`, `vae.pth`) download to `models/audio/flashsr/`. Other enabled checks may download the selected MiniMax, YuE2, SheetSage2, FLUX or GGUF artifacts from the configured catalog. The main workflow skips checks for inactive song models and disabled artwork/refinement stages.
- Alternative quantizations (e.g. the int8 DiT) are marked `"optional": true` in the catalog and are **never** downloaded automatically — a family is not pulled in as a whole.
- Set the per-node `auto_download` toggle to OFF to fail fast instead of downloading.

**All model paths follow ComfyUI's own configuration.** The toolkit resolves targets through `folder_paths.models_dir`, so a ComfyUI started with `--models-directory "F:\ComfyUI\models"` looks for FlashSR under `F:\ComfyUI\models\audio\flashsr` and for GGUFs under `F:\ComfyUI\models\llm` — never under the default base directory. Verify the resolution on any machine with:

```bash
<comfyui-venv-python> scripts/check_model_paths.py --comfy-dir D:/ComfyUI --models-directory F:/ComfyUI/models
```

## 3. MiniMax Music 3 model files

The bundled example references:

```text
ComfyUI/models/
├── diffusion_models/
│   └── minimax_music3_dit_fp16.safetensors
├── text_encoders/
│   └── minimax_music3_text_encoder_pruned_int8_convrot.safetensors
└── vae/
    └── minimax_music3_dav.safetensors
```

Use official ComfyUI/MiniMax model sources for current downloads and licensing terms. Other compatible quantizations can be selected in the workflow.

## 4. FLUX.2 Klein cover models

The example artwork branch references:

```text
ComfyUI/models/
├── diffusion_models/
│   └── flux-2-klein-4b.safetensors
├── text_encoders/
│   └── qwen_3_4b.safetensors
└── vae/
    └── flux2-vae.safetensors
```

Choose matching official model variants if your installation uses different filenames/quantizations.

## 5. Local LLM

Install a GGUF model supported by your LLM node. The workflow includes one example filename only; that model is not bundled.

The bundled production workflows' integrated GGUF settings use:

```text
max_tokens        = 24576   # response cap, not a reservation
n_ctx             = 37376   # prompt + response + thinking
remote_max_tokens = 65536   # cap for "Local app / server" and "Cloud service"
max_prompt_tokens = 4500    # parser guard, Caption+Lyrics (widget default)
```

The detailed bundled system prompt consumes a meaningful part of the context, so very small context windows are not recommended. If your chosen LLM needs more context, increase `n_ctx` only if your hardware/runtime can support it.

Measured demand on real productions (YuE2 Cover, 35 runs, 2026-09-17): parser prompt (Caption+Lyrics) 610-1707 tokens, LLM prompt (system+user) up to ~11.6k tokens, LLM response up to ~2k tokens. `max_tokens` stays a cap: it does not reserve context and cannot shorten a finished answer.

`n_ctx` and `max_tokens` belong together. The context holds the prompt, the response and any thinking, so a response cap larger than `n_ctx` minus the prompt is ended by the runtime rather than by the node - and that would be silent. These two values are therefore chosen so that even the worst case fits: the largest measured prompt (~11.6k tokens) plus a maximum-length answer (24576) is 36166 tokens, still inside `n_ctx = 37376`. A normal answer (up to ~2k tokens) leaves more than 23k tokens unused. If you raise `max_tokens`, raise `n_ctx` by at least the same amount (multiples of the widget step of 256).

Keep `trim_long_prompt` off for covers. With trimming off an oversized prompt is reported as an error naming the budget instead of being cut; with `max_prompt_tokens` too low (below ~1700 for covers) that error fires on normal production prompts.

### Which model for which machine

The toolkit ships a small hardware-profile table (`llm_profiles.py`) and logs the recommendation for the detected device once per run. It is a **starting point, not a measurement**: every size below is the **file size** read from the repository (2026-09-11), not a VRAM promise - context/KV state, compute buffers and backend overhead come on top.

- **CPU only:** small 2-4B class, short context, compact prompt. A large model is not pushed onto the CPU by default. No verified small-model artifact is shipped yet, so check a concrete GGUF (file size, backend support) before committing to one.
- **Up to 8 GiB VRAM:** prefer the small 4B class; the 9B Q4_K_M (6.17 GB file) is an option **only after** the free VRAM was actually checked against it. 4-8k context.
- **10-12 GiB:** Qwen 3.5 9B Q5_K_M (7.11 GB) or Gemma 4 12B QAT Q4_0 (6.98 GB); start at 8k.
- **16 GiB:** Gemma 4 12B QAT or Qwen 3.5 9B Q6_K (7.96 GB) as everyday candidates, Qwen 3.8 27B UD-IQ3_XXS (10.93 GB) as a quality comparison; 8-16k by actual input length.
- **24 GiB:** 27B at UD-IQ4_XS (14.25 GB) or higher; a large context only when the input needs it.
- **32 GiB or more:** larger quantizations (UD-Q4_K_M, 16.46 GB) as an explicit quality profile; on several GPUs measure a split against a single card instead of assuming a gain.

Two cautions the profiles state explicitly: the **active parameters of an MoE model are not its resident weight memory**, and bigger is not automatically better or faster for this task. Model quality for this workflow is not measured yet - see the baseline harness in `DEVELOPMENT.md`.

Optional runtime tuning lives in `models_config.json` under `llm.runtime_options` (for example `{"n_ubatch": 256}`). A parameter is only passed when the installed `llama-cpp-python` build declares it; unsupported or misspelled options are reported in the log instead of being ignored silently, and an accepted option becomes part of the model's cache identity. The node's widgets are unchanged, so existing workflows keep their saved values.

## 6. FFmpeg

For MP3 and loudness/true-peak measurement, the toolkit first searches for system `ffmpeg`. If none is available it tries the executable supplied by `imageio-ffmpeg`.

If MP3 saving or loudness measurement fails, verify:

```bash
ffmpeg -version
```

or reinstall the toolkit requirements.

## 7. Restart and verify

1. Completely stop and restart ComfyUI.
2. Hard-refresh the browser once (`Ctrl+F5`) so frontend JavaScript is reloaded.
3. Check the console for `IMPORT FAILED` messages.
4. Load `example_workflows/Music_Production_Toolkit.json` for YuE2, YuE2 Cover or MiniMax. The classic `Music_Production_Toolkit.json` is also available for fixed MiniMax generation.
5. Select the model files that exist on your system.
6. Run a short test generation before starting a large batch.

## 8. Expected output folders

`MiniMax Output Paths` defines a common base plus these subdirectories:

```text
original_subdir       = org-32flac/
sr_flac_subdir        = highres-44flac/
sr_mp3_subdir         = highres-44mp3/
artwork_subdir        = artwork/
configuration_subdir  = log/
```

All are configurable. The current example workflow writes one final JSON to `configuration_subdir` rather than one sidecar beside every audio file.

The table above describes the classic MiniMax workflow. The main YuE2/MM3
workflow uses `original-flac/` for originals because the source sample rate
depends on the selected model. Both workflows write the prompt report beside
the JSON in `log/`.

## 9. ComfyUI Manager / Registry

Users can install published versions through ComfyUI Manager. Manager can install
this package's `requirements.txt`; FlashSR inference is included and requires no
external custom node. Model weights are separate and are checked/downloaded by
the toolkit when the relevant checks and `auto_download` are enabled.

## 10. Updating

For a Git checkout:

```bash
git pull
python -m pip install -r requirements.txt
```

Then restart ComfyUI and hard-refresh the browser.

## YuE2 and model selection

The main `example_workflows/Music_Production_Toolkit.json` offers YuE2,
YuE2 Cover and MiniMax Music 3 in CHOOSE. New YuE2 songs use native ABC planning;
cover songs use the source's SheetSage2 ABC. See [docs/YUE2.md](docs/YUE2.md) for required
native nodes, checkpoint/encoder folders, prompts and verification scope.
