# Notices and third-party components

MiniMax Music Production Toolkit is an independent open-source project by Johannes Plenio and is not affiliated with or endorsed by MiniMax, ComfyUI/Comfy Org, Black Forest Labs, FlashSR, or the authors of third-party custom nodes used by the example workflow.

The repository does **not** redistribute third-party model weights. Users must obtain models and weights from their respective official sources and comply with the applicable licenses and terms.

The included example workflow can reference these external components:

- ComfyUI core MiniMax Music 3 nodes and model files.
- FLUX.2 Klein model files.
- FlashSR inference code, **bundled** in `flashsr_inference/` (vendored from `jakeoneijk/FlashSR_Inference` and `jakeoneijk/TorchJaekwon`; attribution and per-component licenses are recorded in `flashsr_inference/NOTICE.md`). The FlashSR model **weights** are fetched on first use from the `jakeoneijk/FlashSR_weights` dataset (not redistributed).
- A llama.cpp-compatible GGUF for the integrated `MiniMaxLLMChat` node (not redistributed).

Since v2.0.0 the example workflow no longer uses the external `ComfyUI-Egregora-Audio-Super-Resolution` or `ComfyUI-LLM-Session` custom nodes; they remain optional third-party alternatives.

Each third-party project remains governed by its own license. The upstream FlashSR_Inference and TorchJaekwon repositories do not declare a root license (see `flashsr_inference/NOTICE.md` for the per-component license situation).
