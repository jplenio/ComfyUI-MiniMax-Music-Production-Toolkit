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


## `No link found in parent graph ...`

If ComfyUI reports a message such as `No link found in parent graph for id [37:6] slot [0] unet_name`, the workflow contains a broken serialized subgraph boundary link. Version 1.0.1 fixes the affected v1.0.0 example workflow. Use the v1.0.1 example workflow or later. This is a workflow-serialization issue, not a missing MiniMax model file.

## No JSON appears beside the FLAC/MP3 files

That is expected in the current workflow. Since v1.0.4, the example no longer writes duplicated per-audio sidecars. Look in the directory configured by **MiniMax Output Paths → configuration_subdir** (default `json/`).

The final `Save Production JSON` node must be connected to the three audio savers' `save_info_json` outputs and the saved artwork path.

## Final production JSON is not created

Check the ComfyUI error log for the first failed upstream save. The central JSON intentionally runs only after the original audio, release FLAC, release MP3 and artwork save dependencies complete. If one of those files fails to save, the final JSON is not written, preventing a misleading configuration record that claims missing artifacts exist.

Also verify that `configuration_subdir` is writable and that `create_directories` is enabled on `Save Production JSON`.

## SoundCloud players do not show on the GitHub README

Use the supplied GitHub Pages template instead of trying to embed an iframe directly in README Markdown. Add normal SoundCloud URLs to `docs/index.html`, then enable Pages from the repository's **Settings → Pages** using the `main` branch and `/docs` folder.


## External LLM returns empty text after a native access violation

If `ComfyUI-LLM-Session` logs a native `access violation` and the downstream parser then reports missing `[Caption]` / `[Lyrics]`, the parser error is secondary: it received an empty assistant response. First fully restart ComfyUI; if the native backend remains in a bad state, a full machine restart can clear stale CUDA/llama.cpp state. Only investigate the parser if the LLM node actually returns non-empty text.

## Save Cover JPG reports invalid `collision_mode` or wrong `jpeg_quality` type

This was a workflow-serialization issue in the first v1.0.5 example workflow, not an image-quality or Pillow problem. The `title` and `audio_tags_json` sockets had been inserted ahead of the existing widget-backed inputs in the saved JSON, while the Python node schema still expected `collision_mode`, `create_directories`, and `jpeg_quality` first. ComfyUI therefore associated saved widget values with the wrong slots.

Use the v1.0.6 example workflow or recreate the `Save Image Smart Prefix` node and reconnect `image`, `filename_prefix`, `title`, and `audio_tags_json`. In the corrected workflow the visible values are `collision_mode = auto_increment`, `jpeg_quality = 95`, and `filename_mode = album - title`.
