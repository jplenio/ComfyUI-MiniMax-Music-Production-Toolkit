# MiniMax Model Auto-Download / Check

For **YuE2 Cover**, `sheetsage2_models` (on by default) adds the SheetSage2 BF16
audio encoder to the selected song check. It requires the YuE2 engine switch
as well. Other song selections do not check/download it. `auto_download` controls
whether missing files are fetched; the default target is `models/audio_encoders`.

Checks the model files referenced by the bundled workflow and downloads missing ones on first use when a URL is configured in `models_config.json`.

**Node ID:** `MiniMaxModelAutodownload`  
**Category:** `MiniMax Music Production Toolkit/utilities`

## Inputs

- **`minimax_models`** (`BOOLEAN`) — check MiniMax Music 3 files (dit / text encoder / VAE).
- **`flux2_models`** (`BOOLEAN`) — check the FLUX.2 Klein artwork branch files.
- **`flashsr_models`** (`BOOLEAN`) — check the FlashSR weight files used by `MiniMaxFlashSRAudio`.
- **`llm_model`** (`BOOLEAN`) — check the example LLM GGUF referenced by the workflow.
- **`auto_download`** (`BOOLEAN`) — download every missing file that has a configured URL.
- **`yue2_models`** (`BOOLEAN`) — check/download the YuE2 BF16 checkpoint; enabled
  on new nodes and the Yue2 workflow. Older workflows keep it off on restore.
- **`model_profile_json`** — optional song-model connection. With it, only the
  selected music engine is checked; artwork and FlashSR switches remain independent.

## Behavior

- Missing files with a configured URL are downloaded (progress is logged) and the run continues.
- Missing files without a URL (gated MiniMax / FLUX.2 weights) are reported with guidance from `models_config.json` instead of failing.
- Only download failures raise an error.
- The report is logged line by line and returned as text.

## Outputs

- **`report`** (`STRING`) — multi-line status report (`OK` present / `DL` downloaded / `--` missing / `ERR` failed).

## Notes

The node is placed early in the example workflow and its report feeds the parser node, so the checks run before generation. The selected YuE2 or MiniMax song model is chosen through `model_profile_json`; artwork, FlashSR and LLM checks remain independently switchable. The integrated FlashSR and LLM chat nodes additionally perform their own lazy first-use checks.
