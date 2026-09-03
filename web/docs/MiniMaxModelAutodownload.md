# MiniMax Model Auto-Download / Check

Checks the model files referenced by the bundled workflow and downloads missing ones on first use when a URL is configured in `models_config.json`.

**Node ID:** `MiniMaxModelAutodownload`  
**Category:** `MiniMax Music Production Toolkit/utilities`

## Inputs

- **`minimax_models`** (`BOOLEAN`) — check MiniMax Music 3 files (dit / text encoder / VAE).
- **`flux2_models`** (`BOOLEAN`) — check the FLUX.2 Klein artwork branch files.
- **`flashsr_models`** (`BOOLEAN`) — check the FlashSR weight files used by `MiniMaxFlashSRAudio`.
- **`llm_model`** (`BOOLEAN`) — check the example LLM GGUF referenced by the workflow.
- **`auto_download`** (`BOOLEAN`) — download every missing file that has a configured URL.

## Behavior

- Missing files with a configured URL are downloaded (progress is logged) and the run continues.
- Missing files without a URL (gated MiniMax / FLUX.2 weights) are reported with guidance from `models_config.json` instead of failing.
- Only download failures raise an error.
- The report is logged line by line and returned as text.

## Outputs

- **`report`** (`STRING`) — multi-line status report (`OK` present / `DL` downloaded / `--` missing / `ERR` failed).

## Notes

The node is placed early in the example workflow and its report feeds the parser node, so the checks run before the MiniMax generation subgraph. The integrated FlashSR and LLM chat nodes additionally perform their own lazy first-use checks, so those two models are covered even when this node is removed.
