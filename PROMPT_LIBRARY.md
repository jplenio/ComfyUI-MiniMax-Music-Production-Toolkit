# Prompt library

## Purpose

The `LLM Prompt Library / Template` node separates reusable prompt files from the workflow JSON. This makes genre prompts and system prompts versionable, shareable and easier to maintain.

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

## Refreshing the dropdown

The browser extension refreshes when source/directory values change and also adds a **Refresh prompt lists** button. Use it after creating, renaming or deleting files while ComfyUI is already open.

## Cache behavior

File content is fingerprinted. If a selected file is edited but keeps the same filename, ComfyUI sees the changed fingerprint and recomputes the template node.

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
