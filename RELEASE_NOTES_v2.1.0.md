# Release Notes – v2.1.0

Release date: 2026-09-09

## Summary

The **structured system-prompt and output-layout release**. The Structured Song Prompt is now clearly split into a **User Prompt** and a **System Prompt** section with visible headings, a file-backed system-prompt selector that copies the chosen prompt into an editable field, and dedicated save/refresh buttons. The bundled system-prompt library grew from one production prompt to **eleven focus variants** (brevity, lyrics, instrumentation, fantasy, genre fidelity, cinematic, dance energy, emotional storytelling, minimalism and fast tempo), each built on the full production contract. `MiniMaxOutputPaths` now uses clearer, self-describing folder names (`org-32flac/`, `highres-44flac/`, `highres-44mp3/`, `log/`), and its dead variant-suffix inputs were removed.

## Added

- **System Prompt section in `MiniMaxStructuredPromptV20`**: `system_prompt_source` (default `bundled_library`), `system_prompt_directory`, `system_prompt_file` (default `minimax-music3-production.txt`) and the editable `system_prompt` field now sit in their own visually separated section below the user-prompt fields. Selecting a system-prompt file copies its text into `system_prompt`, which is authoritative from then on (exactly like `description_override` for user prompts), so a selection can still be tweaked by hand.
- **Section headings**: `USER PROMPT` and `SYSTEM PROMPT` render as plain, transparent section headers (styled via an injected CSS rule) instead of dark input/button boxes.
- **New buttons**: `Save as custom user prompt` (after the description), `Save as custom system prompt` (below the system prompt) and `Refresh prompt lists` (bottom, refreshes both user and system libraries).
- **New backend routes**: `/minimax_music_toolkit/prompt_text` (returns a prompt file's raw text so the frontend can copy it into `system_prompt`) and `/minimax_music_toolkit/save_system_prompt` (saves the current system prompt into the library's `_custom/` folder), plus `save_custom_system_prompt` in `prompt_library.py`.
- **Eleven bundled system-prompt variants** in `prompts/system/`, each a complete production prompt (all ten default sections) plus a `## 0. PRIORITY FOCUS` section: `concise`, `lyrics-first`, `instrumental-first`, `fantasy`, `genre-faithful`, `cinematic`, `dance-energy`, `emotional-story`, `minimal-sparse`, and `fast-tempo` (high-BPM, to counter MiniMax playing fast requests too slowly). The dropdown discovers them automatically.
- **`user_prompt_file` default**: the Structured Song Prompt now starts with `electronic/synth-pop-vocal.txt` instead of the placeholder.

## Changed

- **`MiniMaxOutputPaths` defaults**: `original_subdir` → `org-32flac/`, `sr_flac_subdir` → `highres-44flac/`, `sr_mp3_subdir` → `highres-44mp3/`, `configuration_subdir` → `log/`. The example workflow, tooltips and documentation now reflect these names.
- **Removed `append_variant_index` and `variant_padding`** from `MiniMaxOutputPaths`: the suffix had no visible effect because the downstream audio/artwork/JSON savers rebuild the basename from `Album - Title` via `filename_mode`. The connected `run_index`/`variant_count` inputs remain for compatibility.
- **`MiniMaxStructuredPromptV20` field order**: `system_prompt` now appears after `source_name_override`, and `source_name_override` moved from optional to required so it can sit before the system prompt.
- **System prompt selection semantics**: the `system_prompt` field is authoritative in every mode (the frontend copies the selected file into it); headless/API runs without the prefill fall back to loading the selected file directly. `IS_CHANGED` now includes the `system_prompt` text.
- The system-prompt `custom` free-mode entry was removed from the system dropdown (it is only meaningful for user prompts).

## Fixed

- **Pre-2.1.0 saved workflows load with shifted system-prompt fields**: because `system_prompt` moved after `source_name_override`, older serializations had those fields one slot off. The load-time migration in `web/workflow_migration.js` / `web/migration_utils.js` now repairs by widget name for named serializations and reconstructs both historical positional orders; the stored serialization is rebuilt in the current order. The earlier `meter` repair is folded into the same name-based path.
- The contradictory "Caption maximum ~120 words" guidance (conflicting with the `[Caption]` quality target) was removed from every system prompt.

## Breaking changes

- None for execution. Saved workflows are repaired on load (see Fixed). The `MiniMaxOutputPaths` inputs `append_variant_index` and `variant_padding` no longer exist, so very old workflows carrying those two widget values are migrated by dropping the trailing values; the node ignores them at runtime.

## Upgrade notes

- Restart ComfyUI after updating and hard-refresh the browser (`Ctrl+F5`) so the new headings, buttons, system-prompt selector and repaired widget order load.
- Opening a workflow saved before 2.1.0 repairs the Structured Song Prompt widget values automatically (a console line logs the repair).
- Press `Refresh prompt lists` after adding or editing prompt files, and after updating to see the new bundled system-prompt variants.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.1.0.zip`
- `MiniMax_Music3_Production_Toolkit_v2.1.0.json`
- `SHA256SUMS.txt`
