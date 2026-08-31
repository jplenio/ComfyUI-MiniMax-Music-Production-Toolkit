# MiniMax Music Production Toolkit 1.0.3

This release refreshes the public example workflow layout while keeping the production pipeline and processing defaults intact.

## Changed

- Updated the example workflow to the newly arranged, more compact ComfyUI canvas layout.
- Simplified several visible node titles and removed redundant explanatory note nodes.
- The optional saved-song-configuration loader is bypassed in the example workflow so it stays clearly optional.
- Preserved the prompt-library workflow, LLM session helper, MiniMax Music 3 generation path, source declipping, FlashSR hybrid chain, HF repair, static LUFS/true-peak release preparation, FLUX.2 artwork, metadata and smart saving.
- Preserved the repaired MiniMax Music 3 subgraph boundary links from v1.0.1.
- Removed a transient serialized frontend button value from the prompt-library node; the button is recreated dynamically by the toolkit frontend extension.

## Compatibility

No toolkit Python API or node type was intentionally removed or renamed. Existing workflows using the v1.0.x nodes remain compatible.
