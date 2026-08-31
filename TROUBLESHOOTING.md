# Troubleshooting

## Toolkit nodes do not appear

Check the ComfyUI console for `IMPORT FAILED`. Install this package's `requirements.txt` into the same Python environment that runs ComfyUI, then restart completely.

## Prompt-file dropdown is empty

- For `bundled_library`, verify the repository still contains `prompts/user/` and `prompts/system/`.
- For `external_directory`, enter a directory on the **ComfyUI server machine**, not a path that exists only on another browser/client computer.
- Supported files are `.txt`, `.md`, `.prompt`.
- Click **Refresh prompt lists**.
- Hard-refresh the browser after upgrading the toolkit.

## I edited a prompt file but the old output was reused

The toolkit fingerprints selected prompt-file contents, so the template node should invalidate automatically. If the *external LLM node* itself is cached, use `LLM Session ID / Cache Buster` with control-after-generate set to Randomize or Increment.

## External LLM model is missing

The example GGUF filename is not a bundled dependency. Install/select a compatible model supported by your LLM node.

## FlashSR node is missing

Install `ComfyUI-Egregora-Audio-Super-Resolution` and follow its own FlashSR weight instructions. The weights are not distributed by this toolkit.

## FFmpeg/loudness error

The package first looks for a system `ffmpeg`, then falls back to the executable provided by `imageio-ffmpeg`. Reinstall requirements if neither is available.

## Long batch fails with CUDA graph / allocator errors

This is normally a ComfyUI/PyTorch/CUDA/model interaction rather than the prompt toolkit itself. Restart ComfyUI after a CUDA capture failure. If the error specifically mentions `CUDAMallocAsyncAllocator` / stream capture invalidation, testing ComfyUI with `--disable-cuda-malloc` can help isolate allocator/capture instability. Expect a possible performance trade-off.

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
