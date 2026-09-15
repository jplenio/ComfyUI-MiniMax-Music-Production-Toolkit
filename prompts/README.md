# Bundled prompt library

- `user/` contains short creative requests grouped by musical family.
- `system/` contains reusable LLM system prompts.

Supported extensions are `.txt`, `.md` and `.prompt`; bundled files are UTF-8.

Personal data, machine-specific paths and private production metadata should never be committed to this library.

## YuE2 prompt family

`system/yue2/` contains the twelve YuE2 counterparts of the MiniMax templates.
They emit `[Style]`, `[Lyrics]`, `[Title]`, `[Image_Prompt]`. The song-model
selector switches bundled template families; manual and external prompts are
preserved. See [the YuE2 guide](../YUE2.md) for examples and limits.
