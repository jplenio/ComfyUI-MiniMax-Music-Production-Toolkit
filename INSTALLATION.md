# Installation

## 1. Requirements

Use a current ComfyUI installation. The full example workflow needs three groups of components: this toolkit, external custom nodes, and model files.

### This toolkit

Clone into `ComfyUI/custom_nodes/` and install its Python dependencies using **the Python environment used by ComfyUI**.

Typical virtual-environment installation:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit.git
cd ComfyUI-MiniMax-Music-Production-Toolkit
../../.venv/Scripts/python.exe -m pip install -r requirements.txt
```

For a Windows portable installation, use its embedded Python instead. The included `install_requirements.bat` attempts to find a nearby ComfyUI `.venv` or portable embedded Python automatically.

The toolkit requirements are deliberately small:

- SciPy — filtering and high-quality polyphase resampling.
- SoundFile — lossless audio I/O.
- imageio-ffmpeg — FFmpeg fallback for MP3 and loudness/true-peak measurement.
- Mutagen — MP3/FLAC/WAV tags and cover artwork.
- Pillow — cover resizing/encoding.

PyTorch/NumPy are expected from ComfyUI and are intentionally not installed or replaced by this package.

## 2. External custom nodes used by the full example workflow

### ComfyUI-Egregora-Audio-Super-Resolution

Required only for the example workflow's FlashSR stage:

https://github.com/lucasgattas/ComfyUI-Egregora-Audio-Super-Resolution

Follow that project's installation and model-weight instructions. FlashSR weights are not bundled here.

### ComfyUI-LLM-Session

Required only for the example workflow's local GGUF LLM stage:

https://github.com/kantan-kanto/ComfyUI-LLM-Session

The toolkit's prompt-library/template and parser nodes are LLM-runtime agnostic: another ComfyUI node can be used if it accepts system/user text and returns the assistant text in the required format.

## 3. MiniMax Music 3 model files

The example workflow uses ComfyUI's MiniMax Music 3 support and these filenames:

```text
ComfyUI/models/
├── diffusion_models/
│   └── minimax_music3_dit_fp16.safetensors
├── text_encoders/
│   └── minimax_music3_text_encoder_pruned_int8_convrot.safetensors
└── vae/
    └── minimax_music3_dav.safetensors
```

ComfyUI also provides an INT8 diffusion option for lower VRAM. Use official ComfyUI model links/workflows for current downloads and licensing information.

## 4. FLUX.2 Klein cover models

The example artwork branch uses:

```text
ComfyUI/models/
├── diffusion_models/
│   └── flux-2-klein-4b.safetensors
├── text_encoders/
│   └── qwen_3_4b.safetensors
└── vae/
    └── flux2-vae.safetensors
```

If you use a different official FLUX.2 Klein quantization/base variant, select the matching model in the workflow.

## 5. Local LLM model

Install any GGUF model supported by your LLM custom node and select it there. The example workflow may remember one example filename; it is not a required model. A 16k context is a practical starting point because the bundled system prompt is intentionally detailed.

## 6. Restart and verify

1. Completely restart ComfyUI.
2. Hard-refresh the browser (`Ctrl+F5`) once so the prompt-library and preset-sync JavaScript is refreshed.
3. Confirm there are no `IMPORT FAILED` messages for this toolkit.
4. Open **Workflow → Browse Templates** or load `example_workflows/MiniMax_Music3_Production_Toolkit.json` manually.
5. Select your installed MiniMax, FLUX.2 and LLM model files.

## 7. ComfyUI Manager / Registry

After the project is published to the Comfy Registry, normal users should install it through ComfyUI Manager. Manager installs dependencies from `requirements.txt` automatically. External custom nodes and model weights remain separate dependencies of the full example workflow.
