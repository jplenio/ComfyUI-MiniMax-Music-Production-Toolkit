# Development guide

This repository is a ComfyUI custom-node package **and** a complete reference workflow. Changes must therefore preserve three contracts at the same time:

1. Python node APIs and legacy node class identifiers.
2. Serialized ComfyUI workflow structure, including positional input slots and nested subgraph links.
3. Public release artifacts, documentation, prompt files and GitHub Pages demo data.

The deeper maintainer hand-off context is intentionally kept outside the public repository in `KONTEXT.md` when using a code assistant.

## Compatibility rules

- Do not rename existing keys in `NODE_CLASS_MAPPINGS` unless a migration strategy exists. Legacy class identifiers are intentionally retained for old workflows.
- Prefer adding new inputs as optional inputs and avoid reordering existing serialized inputs. ComfyUI can validate saved node slots positionally.
- Never remove or rewrite MiniMax subgraph boundary links just because their endpoints are not in `subgraph["nodes"]`. Virtual `inputNode` / `outputNode` IDs are valid endpoints.
- Do not silently change audio-processing defaults in the public example workflow when doing documentation, layout or packaging work.
- Keep machine-specific paths, private IPs, personal prompt text and private metadata out of public workflow/repository content. The public author name and GitHub URL are intentional.
- Do not install or replace PyTorch/NumPy as toolkit dependencies. They belong to the ComfyUI runtime.
- Keep external model weights and third-party custom nodes external; document them rather than bundling them.

## Repository architecture

Runtime node modules live at the repository root. `__init__.py` merges their `NODE_CLASS_MAPPINGS`, applies input tooltips, exposes `WEB_DIRECTORY = "./web"`, and registers the prompt-library HTTP route.

Important areas:

- `minimax_prompt_source.py` / `prompt_library.py` — prompt sources, structured LLM parser and safe prompt-file loading.
- `minimax_settings.py`, `ksampler_config.py`, `minimax_batch.py` — generation settings and batching helpers.
- `audio_declip.py`, `audio_lowpass.py`, `audio_hf_repair.py`, `audio_release_prep.py` — restoration and release processing.
- `save_audio_smart_prefix.py`, `save_audio_absolute.py`, `minimax_artwork.py`, `minimax_json_output.py` — persistent artifacts and naming.
- `minimax_audio_tags.py`, `minimax_metadata.py` — tags and reproducibility metadata.
- `session_utils.py` — LLM session/cache-buster helper.
- `web/` — ComfyUI frontend extensions and per-node help.
- `prompts/` — bundled system/user prompt library.
- `example_workflows/` — public workflow.
- `docs/` — GitHub Pages SoundCloud demo.
- `scripts/` — workflow sanitizer, validation, packaging and demo-maintenance utilities.
- `tests/` — regression tests that do not require a full ComfyUI runtime.

## Local checks before every commit

From the repository root:

```bash
python scripts/validate_release.py
python -m unittest discover -s tests -v
python -m compileall -q .
node --check web/prompt_library.js
node --check web/structured_prompt.js
node --check web/workflow_migration.js
node --check web/migration_utils.js
node --check web/preset_sync.js
node --check docs/demo-tracks.js
node tests/test_workflow_migration.mjs
```

The static release validator intentionally avoids importing ComfyUI/Torch, so it can run in lightweight CI. The unit suite includes a node-schema snapshot for every toolkit node in the bundled workflow (`tests/test_node_schema_compat.py`) and Windows filename edge tests (`tests/test_windows_paths.py`).

Useful maintainer helpers:

```bash
python scripts/package_release.py --dry-run        # release contents summary, no assets
python scripts/toolkit_diagnostics.py              # self-diagnostics report
python scripts/preview_output_paths.py --album "My Album" --title "My Song"   # planned output paths
python scripts/bump_version.py 2.0.1               # version bump + release-notes skeleton
```

When runtime nodes or the example workflow changed, also run the headless smoke test against a real ComfyUI checkout:

```bash
python scripts/comfyui_smoke_test.py \
    --comfy-dir D:/ComfyUI \
    --venv-python D:/ComfyUI/.venv/Scripts/python.exe \
    --base-dir %TEMP%/minimax_smoke_v2
```

It registers the toolkit in an isolated base directory (junction, no changes to the real installation), validates the full workflow graph including the MiniMax subgraph, and executes the prompt/LLM section with the LLM disabled and manual parser fallbacks.

## Workflow editing

Treat `example_workflows/MiniMax_Music3_Production_Toolkit.json` as a serialized API surface, not as an arbitrary JSON document.

When changing a toolkit node schema:

1. Compare `INPUT_TYPES()` order with the saved workflow node `inputs` array.
2. Repair target slot numbers of connected links if an input must move.
3. Add a regression test for the exact saved slot order.
4. Load the workflow in a current ComfyUI build and queue a small execution.
5. Re-run recursive subgraph-link validation.

The public-workflow builder contains explicit protection for the two workflow serialization regressions already encountered: nested MiniMax boundary links and the artwork-saver input order.

Since 2.0.0 there is also a schema migration layer: `workflow_schema.migrate_workflow()` repairs pre-2.0.0 workflows that wired the parser's old input order (remapping link slots by input name), and `web/workflow_migration.js` performs the same repair when an old workflow is loaded in the browser. The bundled workflow must never contain external custom-node types (`LLMSessionChatNode`, `UnloadLLMModelNode`, `EgregoraAudioUpscaler`, …); release validation enforces this.

## Demo gallery maintenance

The GitHub Pages page reads `docs/demo-tracks.js`; audio remains on SoundCloud.

For repeated additions prefer:

```bash
python scripts/update_demo_catalog.py "D:/exports/json/*.json" --cover-source "D:/exports/artwork"
```

The helper extracts only public demo fields and preserves existing SoundCloud URLs for matching tracks. It deliberately does **not** copy the full system prompt, raw LLM response or machine-specific output paths from production JSON.

If cover filenames already match the catalog exactly, `scripts/prepare_demo_covers.py` can prepare all referenced covers dynamically. It no longer contains a hard-coded 17-track list.

After adding tracks, paste their normal SoundCloud URLs into `soundcloudUrl` and push the `docs/` changes. GitHub Pages should be configured for `main` + `/docs`.

## Release procedure

1. Choose a new immutable version. Never replace the contents of a version that was already published to the Comfy Registry.
2. Update `VERSION`, `pyproject.toml`, `project_info.py`, `CITATION.cff`, `CHANGELOG.md`, release notes and example-workflow version metadata.
3. Run all validation/tests.
4. Build assets:

```bash
python scripts/package_release.py --output-dir dist
```

5. Review `SHA256SUMS.txt` and the ZIP contents.
6. Commit and push.
7. Create GitHub tag/release `vX.Y.Z`.
8. The GitHub Action publishes package version `X.Y.Z` to the Comfy Registry using `REGISTRY_ACCESS_TOKEN`.
9. Check GitHub Actions and the Registry result before announcing the release.

See `PUBLISHING.md` for the exact maintainer commands.

## High-value regression areas

Whenever code in these areas changes, explicitly test them:

- nested subgraph boundary links (`inputNode` / `outputNode`)
- `SaveImageSmartPrefix` input order and widget types
- shared `Album - Title` filename behavior across audio, JPG and JSON
- centralized JSON execution after audio/artwork savers
- prompt-file path traversal and symlink escape handling
- prompt content fingerprints / ComfyUI cache invalidation
- Windows paths and Unicode filenames
- duplicate demo titles / multiple takes
- SoundCloud URL preservation when refreshing demo metadata
