# Release Notes – v2.0.2

Release date: 2026-09-04

## Summary

Usability and transparency release: the workflow now shows **exactly which prompt MiniMax Music 3 received** (readable Markdown report right in the node), long-running stages got **ComfyUI progress bars** (FlashSR chunks, and token-streaming progress for the LLM chat), and the GitHub Pages demo page was rebuilt as a compact, play-first single-column player with 10 new tracks (35 total).

## Added

- **`MiniMaxPromptReport` node** ("MiniMax Prompt Report (Markdown)"): shows the cleaned musical caption, the normalized lyrics, the character-exact final prompt sent to the MiniMax tokenizer (verbatim, including token markers) and — clearly separated — the FLUX.2 image prompt. The report is rendered as **formatted Markdown inside the node** (ComfyUI's built-in text-preview widget, Markdown mode by default, with a Plain-text toggle) and remains available as a STRING output. Wired into the example workflow's Save Audio section.
- **Progress bars in the integrated LLM chat**: generation now runs as a token stream (when the installed llama-cpp-python supports `stream`) — the node's progress bar advances per generated token (reasoning included) up to `max_tokens`, a log heartbeat appears every 64 tokens, and start/finish lines make the stage observable. Non-streaming backends fall back to the previous behaviour.
- **Progress bar in `MiniMaxFlashSRAudio`**: the blue ComfyUI progress bar now advances per 5.12 s chunk, with a per-10 % log update.
- **10 new demo tracks** on the GitHub Pages demo page (hard rock, industrial metal, symphonic metal, and four multilingual tracks — Italian, Korean, Japanese) with covers, mixed into a curated showcase order.

## Changed

- **Demo page rebuilt**: tracks are listed in a single column (no more side-by-side grid); the SoundCloud player is the first thing on every card; cover images are small thumbnails; descriptions are clipped and full generation details stay behind "Generation details". Search/filter/sort and the stats header are unchanged.
- Demo catalog count raised to 35; placeholder tags of the new batch were replaced with real album names (Unbreakable, System Override, Symphonic Metal, Night Maps).
- `progress_utils.py` provides the ComfyUI progress bar with a silent no-op fallback outside ComfyUI, so unit tests keep running everywhere.

## Fixed

- **CI for this repository is green again**: the six audio modules import `torch` tolerantly (only present inside ComfyUI), and `numpy` is now an explicit dependency in `requirements.txt`/`pyproject.toml`; the CI workflow installs the requirements before running the tests.
- Example-workflow link serialization for the new node is complete on both sides (`outputs[].links` and `inputs[].link`), so no workflow-validation warnings appear on load.

## Breaking changes

- None. Existing workflows keep working; the new report node is additive and optional.

## Upgrade notes

- Restart ComfyUI after updating and hard-refresh the browser (Ctrl+F5) to load the new node and its Markdown-preview extension.
- The bundled example workflow now contains the `MiniMaxPromptReport` node; older saved workflows simply don't have it.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.2.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.2.json`
- `SHA256SUMS.txt`
