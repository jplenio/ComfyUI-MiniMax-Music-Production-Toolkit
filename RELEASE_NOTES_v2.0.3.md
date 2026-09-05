# Release Notes – v2.0.3

Release date: 2026-09-05

## Summary

A "full freedom" release for the prompt stage: the prompt-file dropdown of the **Structured Song Prompt** node now starts with a **`custom`** choice that loads no file and leaves every field exactly as you set it, so you can compose a prompt entirely by hand. The bundled example workflow also ships refined audio-enhancement presets, and the README was rewritten as a welcoming, non-technical introduction to the project.

## Added

- **`custom` free mode in the Structured Song Prompt**: the `user_prompt_file` dropdown now offers `custom` as the first real choice. Selecting it loads no prompt file, prefills nothing and clears nothing — the Genre / Tempo / Key / Lyrics / Language / Voice / Theme / Length fields and the further-description area are used exactly as you filled them in. In the backend this is equivalent to manual mode, so no file named `custom` is ever resolved.

## Changed

- **Refined audio presets in the example workflow**: the PRE low-pass preset moved from `PRE 12 kHz - recommended` to `PRE 10 kHz - strong`, the FlashSR hybrid crossover now uses the `FlashSR only` mode, and the HF Cymbal / Shimmer Repair stage switched from `Gentle` to `Cymbal clarity` (start frequency 7000 Hz, sustain reduction 2.25 dB, static HF trim -0.5 dB).
- **README rewritten**: a concise, appealing overview for newcomers that leads with the "fill a few fields, get a finished track" experience and explains at the end how the pipeline and the new custom mode actually work.

## Fixed

- None — this is an additive, backward-compatible release.

## Breaking changes

- None. Existing workflows keep working; `custom` only adds a choice to the prompt-file dropdown.

## Upgrade notes

- Restart ComfyUI after updating and hard-refresh the browser (`Ctrl+F5`) so the prompt-file dropdown gains the `custom` entry.
- The bundled example workflow keeps its previous prompt selection; open the **Structured Song Prompt** node and choose `custom` to try the free mode.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.3.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.3.json`
- `SHA256SUMS.txt`
