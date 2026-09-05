# MiniMax Music Production Toolkit 1.0.x – Combined Release Notes

All pre-2.0.0 releases in one file (kept for reference; the 2.x notes are
versioned separately).

---

## 1.0.6

This release fixes the bundled workflow validation error in **Save Cover JPG – same song name** and includes the repository's expanded prompt library and SoundCloud demo-page updates.

### Fixed

- Corrected the serialized input order of `Save Image Smart Prefix`.
- `collision_mode` now maps to its choice widget again (`auto_increment` by default).
- `jpeg_quality` now maps to its integer widget again (`95` by default).
- The connected `title` and `audio_tags_json` sockets remain intact, so artwork still uses the same `Album - Title` basename as FLAC, MP3 and the centralized production JSON.
- `scripts/build_public_workflow.py` now normalizes this node automatically and repairs target-slot indices after reordering.
- Release validation and unit tests now assert the exact artwork-saver slot order and widget types.

### Included in this release

- 62 bundled user prompt files, including the additional alternative, EDM, electronic, house, rock and metal prompts supplied with the release package.
- SoundCloud demo-gallery configuration and public demo links already present in the repository.
- Existing v1.0.5 output naming, centralized JSON, metadata, artwork, audio processing and LLM settings are otherwise retained.

### Upgrade note

If an older v1.0.5 workflow already shows the `collision_mode` / `jpeg_quality` validation error, load the bundled v1.0.6 example workflow. Recreating only the `Save Image Smart Prefix` node and reconnecting its inputs also resolves the stale serialized slot order.

---

## 1.0.5

### Artwork filename parity

This release fixes a mismatch between audio and artwork filenames in prompt-library workflows. Previously, audio files could correctly be saved as `Album - Title` while the cover JPG kept the source prompt filename, for example `nordic-folk-vocal.jpg`.

The bundled workflow now connects the generated song title and the standard audio-tag JSON to `Save Image Smart Prefix`. With the default `filename_mode = album - title`, all principal per-song artifacts share the same basename:

```text
32flac/Example Album - Last Wick.flac
44flac/Example Album - Last Wick.flac
44mp3/Example Album - Last Wick.mp3
artwork/Example Album - Last Wick.jpg
json/Example Album - Last Wick.json
```

Audio, artwork and centralized JSON naming now use one shared filename helper so sanitization and Album/Title construction cannot drift between formats. The old source-prefix behavior remains available explicitly through `filename_mode = prefix as provided`.

### Demo page

The GitHub Pages demo configuration includes the prepared SoundCloud playlist and track URLs. The page can use local demo covers when present and otherwise fall back to SoundCloud's visual player.

### Example workflow

The release preserves the packaged/tested local-LLM settings:

```text
max_tokens = 16384
n_ctx      = 32768
```

No MiniMax Music 3 generation, audio restoration, FlashSR, release-prep or metadata-processing defaults were intentionally changed for this fix.

### Validation

Release tests now explicitly verify the artwork title/tag connections, shared `album - title` naming contract, centralized JSON contract and workflow link integrity including MiniMax subgraph boundaries.

---

## 1.0.4

v1.0.4 improves output organization, LLM headroom and public demo/documentation support.

### Changes

- Example local LLM `max_tokens` increased to **14000**.
- Added `configuration_subdir` to **MiniMax Output Paths** with default `json`.
- Added **Save Production JSON** for one canonical per-song configuration file.
- The final JSON is written only after original FLAC, release FLAC, release MP3 and artwork saves have completed.
- Audio savers now emit `save_info_json` so the canonical JSON records the actual saved paths and file-writing details.
- The v1.0.4 example workflow disables duplicated per-audio JSON sidecars. Legacy sidecar support is retained for existing workflows.
- Added a ready-to-edit GitHub Pages SoundCloud demo page under `docs/index.html`.
- Thoroughly revised the public documentation and node help for the new output model.

### Default output organization

```text
32flac/
44flac/
44mp3/
artwork/
json/
```

The `json/` directory is configurable.

### Upgrade note

After replacing the custom-node folder, restart ComfyUI completely and hard-refresh the browser (`Ctrl+F5`). Load the v1.0.4 example workflow to use the new centralized JSON design.

---

## 1.0.3

This release refreshes the public example workflow layout while keeping the production pipeline and processing defaults intact.

### Changed

- Updated the example workflow to the newly arranged, more compact ComfyUI canvas layout.
- Simplified several visible node titles and removed redundant explanatory note nodes.
- The optional saved-song-configuration loader is bypassed in the example workflow so it stays clearly optional.
- Preserved the prompt-library workflow, LLM session helper, MiniMax Music 3 generation path, source declipping, FlashSR hybrid chain, HF repair, static LUFS/true-peak release preparation, FLUX.2 artwork, metadata and smart saving.
- Preserved the repaired MiniMax Music 3 subgraph boundary links from v1.0.1.
- Removed a transient serialized frontend button value from the prompt-library node; the button is recreated dynamically by the toolkit frontend extension.

### Compatibility

No toolkit Python API or node type was intentionally removed or renamed. Existing workflows using the v1.0.x nodes remain compatible.

---

## 1.0.1

This hotfix repairs the public example workflow's embedded MiniMax Music 3 subgraph.

### Fixed

- Restored all subgraph boundary links between the parent MiniMax node and its internal model, text encoder, sampler and VAE nodes.
- Fixes ComfyUI errors such as `No link found in parent graph for id [37:6] slot [0] unet_name`.
- Release validation now recursively checks subgraph link integrity so this class of packaging regression is caught before a release is built.
- Public workflow version metadata is now generated from the repository `VERSION` file.

No audio-processing defaults or generation defaults were changed.

---

## 1.0.0

Initial public release.

### Highlights

- Prompt-library/template node with manual, bundled-library and external-directory sources for both user and system prompts.
- Bundled MiniMax Music 3 production system prompt and 38 sanitized genre prompt examples.
- Structured Caption / Lyrics / Title / Image Prompt parsing for an external ComfyUI LLM.
- Reproducible MiniMax settings, metadata JSON, standard release tags and Album - Title filenames.
- Audio declipping, FlashSR pre/post filtering, hybrid original/FlashSR crossover and HF cymbal/shimmer repair.
- High-quality release sample-rate conversion plus static full-program LUFS / true-peak targeting without gain riding.
- FLUX.2 cover workflow helpers and configurable embedded-cover resolution.
- Complete tooltips, node help pages, release validation, tests and GitHub/Comfy Registry publishing workflows.

See `INSTALLATION.md` before loading the full example workflow because FlashSR, the local LLM stage and model files are external dependencies.
