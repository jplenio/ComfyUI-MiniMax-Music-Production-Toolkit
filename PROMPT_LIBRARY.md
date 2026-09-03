# Prompt library

## Purpose

Prompt files separate reusable prompts from the workflow JSON. The `LLM Prompt Library / Template` node (legacy) and the new `Structured Song Prompt` node both read the same library; the structured node additionally understands the optional metadata block described below.

User and system prompts can use different source modes at the same time.

## Source modes

### `manual`

Use the multiline field stored directly in the workflow.

### `bundled_library`

Reads from this repository:

```text
prompts/user/
prompts/system/
```

The file dropdown contains relative paths, including category folders.

### `external_directory`

Enter an absolute or environment-variable-based path on the machine running ComfyUI. The node recursively discovers supported prompt files below that root and displays them as relative paths in the dropdown.

Supported file types:

- `.txt`
- `.md`
- `.prompt`

Text must be UTF-8. UTF-8 with BOM is accepted.

## Structured metadata block (optional)

Prompt files may start with a metadata block. `MiniMaxStructuredPromptV20` uses it to prefill the structured fields when the file is selected:

```text
---
Genre: Melodic Techno
Tempo: 128 BPM
Key: A minor
Lyrics: sparse
Language: English
Voice: female vocal, airy
Theme: escape into the night
Length: 4-5 minutes
---
Free text describing the track in more detail.
```

- The block must be the very first thing in the file, delimited by lines containing only `---`.
- Keys are case-insensitive; aliases such as `BPM`, `Tonart`, `Sprache`, `Stimme`, `Lyrics theme` and `Song length` are accepted. Unknown keys are ignored.
- Lyrics values are normalized to `yes` / `sparse` / `instrumental` where recognizable (`ja`, `no`, `wenig`, …).
- Everything after the closing `---` (or the whole file, if there is no block) is the **further description**.
- Files without a metadata block are fully supported: all fields default to `custom` and the whole file is used as the description.
- Every prefilled field can be overridden in the node; `custom` leaves that part out of the LLM prompt entirely.

The bundled library ships with metadata for all 62 user prompts; regenerate it with:

```bash
python scripts/annotate_prompt_metadata.py --dry-run
python scripts/annotate_prompt_metadata.py
```

## Refreshing the dropdown

The browser extension refreshes when source/directory values change and also adds a **Refresh prompt lists** button. Use it after creating, renaming or deleting files while ComfyUI is already open. Selecting a prompt file prefills the structured fields of `MiniMaxStructuredPromptV20` via the `/minimax_music_toolkit/prompt_metadata` route.

## Cache behavior

File content is fingerprinted. If a selected file is edited but keeps the same filename, ComfyUI sees the changed fingerprint and recomputes the prompt node.

This is separate from an LLM runtime's own KV/prompt cache.

## Safety and validation

The loader:

- rejects missing/empty directories;
- rejects unsupported extensions;
- rejects files larger than 2 MiB;
- rejects invalid UTF-8;
- rejects absolute selections and `..` traversal outside the configured root;
- ignores symlinks that resolve outside the configured library root;
- returns clear user-facing errors instead of silently substituting another prompt.

## Adding bundled user prompts

Create a descriptive UTF-8 file under a category, for example:

```text
prompts/user/house/my-house-prompt.txt
```

After restarting or refreshing the prompt list, it appears as:

```text
house/my-house-prompt.txt
```

## Adding system prompts

Place alternate system prompts in:

```text
prompts/system/
```

A system prompt should document the output contract expected by your downstream parser. The bundled production prompt currently expects Caption → Lyrics → Title → Image Prompt.

## Current bundled library

The v1.0.7 repository contains **62 user prompt files** across:

`alternative`, `ambient`, `classical`, `comedy`, `edm`, `electronic`, `folk`, `funk`, `house`, `jazz`, `metal`, `pop`, and `rock`.

The production system prompt is stored only in `prompts/system/minimax-music3-production.txt`; avoid duplicating that long prompt in Python source.

## Implementation notes for developers

The dropdown is populated through the toolkit's `/minimax_music_toolkit/prompt_files` route and `web/prompt_library.js`. Because the choices are dynamic, the node performs authoritative path/file validation at execution time rather than assuming a saved combo value is permanently valid.

`IS_CHANGED` includes a content fingerprint for file-backed prompts, so an edit to a selected file invalidates ComfyUI caching even when its filename is unchanged.

The selected external path refers to the filesystem of the machine running ComfyUI. A generic browser-side server filesystem explorer is intentionally not exposed by default; typed/configured server paths are the safer baseline for local and remote ComfyUI deployments.
