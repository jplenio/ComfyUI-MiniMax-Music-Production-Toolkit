# Bundled prompt library

- `user/` contains short creative requests grouped by musical family.
- `system/` contains reusable LLM system prompts.

Supported extensions are `.txt`, `.md` and `.prompt`; bundled files are UTF-8.

Personal data, machine-specific paths and private production metadata should never be committed to this library.

## YuE2 prompt family

YuE2 Cover uses the same templates plus a runtime cover instruction: the LLM
receives the source ABC score and fixed filename title. It adapts Style and Lyrics
to the source music; no separate cover-template copies need to be maintained.

`system/yue2/` contains the twelve YuE2 counterparts of the MiniMax templates.
They emit `[Style]`, `[Lyrics]`, `[Title]`, `[Image_Prompt]`. The song-model
selector switches bundled template families; manual and external prompts are
preserved. Style contains a developed chronological arrangement; Lyrics carries
the same ordered section tags, including repeated occurrences. Instrumental
Lyrics stays tag-only while musical development is described in Style.
All active system prompts plan the requested duration across those sections,
including a natural ending. Section timings are approximate musical guidance;
phrases and decay may run beyond the target. YuE2's configured maximum remains
available in full, so Length never causes a target-time cut. The parser carries
the numeric target into the final Style sent to ABC and music generation.
See [the YuE2 guide](../YUE2.md) and the
[full instrumental example](examples/yue2-instrumental-arrangement.txt).

`YuE2-old/` preserves the previous twelve prompts outside the active system
library. Use them as manual/external prompts for comparison. Saved nodes retain
their editable text; reselect the system-prompt file or load the updated workflow
to adopt the revised instructions.
