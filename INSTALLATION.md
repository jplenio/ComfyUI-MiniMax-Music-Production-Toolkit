# Installation

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

`MiniMaxLLMChat` uses the public `llama-cpp-python` API:

```bash
python -m pip install llama-cpp-python
```

When it is missing, the node still registers and explains the dependency at execution time. Provide a llama.cpp-compatible GGUF in `ComfyUI/models/llm/` (or configure a download URL in `models_config.json`).

## 2. Model files and auto-download

`models_config.json` in the toolkit folder lists every model file the example workflow references, its target folder and (where available) its download URL. `MiniMaxModelAutodownload` and the integrated FlashSR/LLM nodes check these files on first use:

- Files with a configured URL are downloaded automatically (progress is logged) and the run continues.
- Gated MiniMax / FLUX.2 weights have no public URL and are reported with guidance; obtain them from the official channels.
- The FlashSR **inference code is bundled** with the toolkit in `flashsr_inference/` (vendored from `jakeoneijk/FlashSR_Inference` and `jakeoneijk/TorchJaekwon`; see `flashsr_inference/NOTICE.md`). Nothing is downloaded into the models directory except the three **weights** from the `jakeoneijk/FlashSR_weights` dataset (`student_ldm.pth`, `sr_vocoder.pth`, `vae.pth` → `models/audio/flashsr/`).
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
original_subdir       = 32flac/
sr_flac_subdir        = 44flac/
sr_mp3_subdir         = 44mp3/
artwork_subdir        = artwork/
configuration_subdir  = json
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
