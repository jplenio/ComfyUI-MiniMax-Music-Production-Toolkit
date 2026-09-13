# Release Notes – v2.5.2

Release date: 2026-09-13

## Summary

2.5.2 is a bug-fix release. It hardens the audio export path and the music
sampler against invalid numerical output, and it makes the documented
runtime-safety mode work as described. Nothing else changes: node interfaces,
workflow layout, stored settings and the LLM defaults stay as they are.

**Preview of image and song.** The generated cover and the finished song stay
visible right in the workflow: `PreviewImage` shows the artwork as soon as the
cover saver has written it, and `PreviewAudio` plays the exported track. Both are
part of the production example and need no setup.

## Fixed

- **Audio export never writes invalid samples.** Both audio savers validate the
  entire batch before peak handling and encoding. NaN/Infinity audio used to end
  in a blank SoundFile assertion while writing FLAC; the remaining encoder
  assertions now carry format, sample-rate and library diagnostics, and the
  incomplete staging file is removed.
- **Both decoder branches check their input and their output.** The production
  subgraph uses `MiniMaxSafeAudioDecode` for the normal and the tiled decoder.
  It validates sampler latents, decoded audio and the normalization step,
  retries decoding once with conservative tiles when only the decoding failed
  numerically, and never replaces bad samples with silence.
- **The music sampler no longer repeats an identical non-finite run.**
  `KSamplerWithConfig` failed twice on the same seed in the reporting run: the
  noise follows the seed and the conditioning and weights are unchanged, so the
  second pass reproduced the same latents and only doubled the longest stage of
  the prompt. Non-finite latents now stop immediately with the concrete remedy
  (`--bf16-unet`, `--fp32-unet`, or a new seed). The one retry for
  capture/CUDA-graph backend *errors* — where clearing the captured state can
  help — is unchanged.
- **`MINIMAX_MUSIC3_RUNTIME_SAFETY=auto` works as documented.** The policy
  parser folded `auto` into `off`, so the risky-backend branch (Blackwell-class
  CUDA or ROCm) could never run and the automatic mode silently did nothing.
  `off` is still the default and stays inert.
- **`TROUBLESHOOTING.md` documents the remaining non-finite DiT class** with the
  dtype decision measured on the reporting machine (float16 without flags;
  `--bf16-unet` changes only the DiT and is VRAM-neutral; `--fp32-unet` also
  switches the FLUX.2 cover to fp32) and the experiment order, so the upstream
  issue is not re-diagnosed from scratch.
- **Release-gate hygiene.** The FFmpeg pipe timeout test no longer races the
  process start (it could fail a release build at random), and the regression
  coverage now includes decoder recovery, input ownership, real FLAC/WAV
  roundtrips, batch validation, failed-export cleanup and the sampler guard.

## Breaking changes

None. Node identifiers, inputs, outputs, return orders, widget names and stored
values are unchanged; the example workflows keep their layout and settings.

## Upgrade notes

- Restart ComfyUI and hard-refresh the browser after updating.
- Reopen the bundled example workflows; saved personal workflows are not
  rewritten automatically.
- The non-finite latents of the fp16 diffusion model are a ComfyUI/MiniMax issue
  that this release detects early and explains. `TROUBLESHOOTING.md` lists the
  measured `--bf16-unet` / `--fp32-unet` experiments.

## Validation

- Full test suite: **866 tests, OK** (1 skipped: `mutagen` is not installed in
  the development environment).
- `scripts/validate_release.py`: **Release validation OK**, privacy scan clean.
- `scripts/dump_node_contracts.py --check`: contract snapshot up to date.
- `python -m compileall -q .`: clean.
- `scripts/package_release.py --dry-run`: 34 registered nodes, 850 files,
  privacy scan CLEAN.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.5.2.zip`
- `MiniMax_Music3_Production_Toolkit_v2.5.2.json`
- `MiniMax_Music3_Production_Toolkit_AudioEnhance_v2.5.2.json`
- `SHA256SUMS.txt`
