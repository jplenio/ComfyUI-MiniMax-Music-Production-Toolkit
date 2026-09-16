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

**Version 3.0:** Open [Yue2_MM3_Production_Toolkit.json](example_workflows/Yue2_MM3_Production_Toolkit.json) for YuE2, YuE2 Cover or MiniMax. CHOOSE controls the song mode, artwork, refinement and mastering; SOURCE AUDIO supplies a cover track. See [the song and cover guide](YUE2.md). The classic MiniMax workflow below retains its existing processing chain.

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

- **SciPy** — filtering and high-quality polyphase resampling.
- **SoundFile** — FLAC/WAV audio I/O.
- **imageio-ffmpeg** — FFmpeg fallback for MP3 encoding and loudness/true-peak measurement.
- **Mutagen** — FLAC/MP3/WAV metadata and cover embedding.
- **Pillow** — cover-art resizing and JPEG encoding.

PyTorch and NumPy are expected from ComfyUI and are deliberately not replaced by this package.

### Optional: integrated LLM chat

The LLM node also supports **Local app / server** and **Cloud service** modes.
Those modes do not require llama-cpp-python or a GGUF in ComfyUI. Start your local
app's API server or configure a cloud API key, then select a model on the node.
See [LLM_PROVIDERS.md](LLM_PROVIDERS.md) for supported apps, addresses and setup.
The GGUF requirements below apply only to **In ComfyUI (GGUF)**.

`MiniMaxLLMChat` uses the public `llama-cpp-python` API:

```bash
python -m pip install llama-cpp-python
```

When it is missing, the node still registers and explains the dependency at execution time. Provide a llama.cpp-compatible GGUF in `ComfyUI/models/llm/` (or configure a download URL in `models_config.json`).

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
- The FlashSR **inference code is bundled** with the toolkit in `flashsr_inference/` (vendored from `jakeoneijk/FlashSR_Inference` and `jakeoneijk/TorchJaekwon`; see `flashsr_inference/NOTICE.md`). Nothing is downloaded into the models directory except the three **weights** from the `jakeoneijk/FlashSR_weights` dataset (`student_ldm.pth`, `sr_vocoder.pth`, `vae.pth` → `models/audio/flashsr/`) and the MiniMax/FLUX files listed above.
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

The v1.0.7 example LLM settings use:

```text
max_tokens = 16384
n_ctx      = 32768
```

The detailed bundled system prompt consumes a meaningful part of the context, so very small context windows are not recommended. If your chosen LLM needs more context, increase `n_ctx` only if your hardware/runtime can support it.

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
4. Load `example_workflows/MiniMax_Music3_Production_Toolkit.json`.
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

## 9. ComfyUI Manager / Registry

After publication in the Comfy Registry, users can install the toolkit through ComfyUI Manager. Manager can install this package's `requirements.txt`, but it does **not** automatically provide the external FlashSR custom node or large model weights used by the full example workflow.

## 10. Updating

For a Git checkout:

```bash
git pull
python -m pip install -r requirements.txt
```

Then restart ComfyUI and hard-refresh the browser.

## YuE2 and model selection

The new `example_workflows/Yue2_MM3_Production_Toolkit.json` supports both MiniMax and YuE2 through its first Song model control. It includes matched templates, native ABC planning and generation records. See [YUE2.md](YUE2.md) for setup, prompt examples and verification scope. The classic MiniMax workflow remains fixed to MiniMax.
