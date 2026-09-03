# Release Notes – v2.0.1

Release date: 2026-09-03

## Summary

Bugfix release that makes the workflow runnable **repeatedly** in the same
ComfyUI session. The integrated LLM chat node now releases *all* GPU memory
held by the previous run (including ComfyUI's dynamic-VRAM staging, cast
buffers and CUDA-graph workspaces, plus the FlashSR cache) before loading the
LLM, so a second run no longer overflows the GPU and hangs in the LLM load or
fails later in the MiniMax node with `cudaErrorStreamCaptureInvalidated`.
Single-GPU machines are fully supported again; on multi-GPU machines the LLM
is optionally auto-routed to the GPU with the most free VRAM.

## Added

- Automatic LLM GPU routing: with two or more visible GPUs and the default
  settings (`main_gpu=0`, `split_mode=none`, no `tensor_split`), the LLM is
  routed to the non-default GPU with the most free VRAM; ComfyUI models stay
  on their usual device. Explicit `main_gpu`/split settings always win.
- Diagnostic logging around the LLM load: resident models before cleanup,
  aimdo VRAM usage and free VRAM per GPU after cleanup, and – if anything is
  still resident – the owner of every remaining dynamic-VRAM staging block
  (VBAR), which is then force-released.

## Changed

- `MiniMaxLLMUnload` returns GPU memory to the allocator pools more
  aggressively after closing the model (`gc.collect()`,
  `torch.cuda.empty_cache()`, `soft_empty_cache`), so the music stage gets
  unfragmented VRAM.
- The LLM load error message now names `n_ctx`, `n_gpu_layers` and `main_gpu`
  and suggests concrete remedies when a load fails.
- One-time log hint explains single-GPU operation and mentions the optional
  `--cuda-device all` launch flag for machines with a second GPU.

## Fixed

- **Repeated runs hang in the integrated LLM chat / overflow VRAM.** The
  models of the previous run (dynamic-VRAM staging pages, cast buffers,
  CUDA-graph/prefetch workspaces, cached FlashSR runners) were not released
  before the LLM loaded; on a single GPU the GGUF load then spilled into
  system memory (seemingly endless load) and left the CUDA context broken so
  MiniMax later failed during CUDA graph capture
  (`cudaErrorStreamCaptureInvalidated`). The node now frees all of these
  explicitly before every LLM load; models re-stage on demand afterwards.
- FlashSR model cache is released before the LLM load as well, not only by
  the unload node.

## Breaking changes

- None. No node inputs, outputs or workflow changes; the example workflow is
  unchanged.

## Upgrade notes

- Existing workflows keep working; no workflow reload required.
- Restart ComfyUI after updating so the Python changes are loaded.
- If you run on a machine with two GPUs and want the LLM on the second card,
  start ComfyUI with `--cuda-device all` (on Windows ComfyUI otherwise hides
  the extra GPUs); the LLM is then routed automatically.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.1.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.1.json`
- `SHA256SUMS.txt`
