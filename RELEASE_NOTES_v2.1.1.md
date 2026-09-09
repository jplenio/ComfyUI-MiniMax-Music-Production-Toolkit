# Release Notes – v2.1.1

Release date: 2026-09-09

## Summary

The **branding and README refresh**. This patch adds the project icon and banner to the Comfy Registry metadata and the README, and brings the README description up to date with the current prompt counts (239 user templates, 11 system-prompt variants). No runtime behavior changed. The main feature work shipped in v2.1.0 (see `RELEASE_NOTES_v2.1.0.md`) — the structured system prompt, the reworked `MiniMaxOutputPaths` layout and the eleven bundled system-prompt variants.

## Added

- **Branding assets**: `assets/branding/icon.png` (400×400) and `assets/branding/banner.png` (1680×720), referenced from `pyproject.toml` as `[tool.comfy] Icon` / `Banner` (raw GitHub URLs on `main`).
- **README banner**: the banner is now shown at the very top of `README.md` (centered, full-width).

## Changed

- **README refreshed**: the production system-prompt bullet now mentions the **11 bundled focus variants**, and the bundled genre prompt library bullet states the exact **239 templates** (was the rounded "230+"). The rest of the description was kept current with the released feature set.

## Fixed

- None.

## Breaking changes

- None.

## Upgrade notes

- None beyond a normal restart + browser hard-refresh (`Ctrl+F5`). If v2.1.0 was not published separately, this v2.1.1 release is the one to publish and includes all v2.1.0 changes as well.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.1.1.zip`
- `MiniMax_Music3_Production_Toolkit_v2.1.1.json`
- `SHA256SUMS.txt`
