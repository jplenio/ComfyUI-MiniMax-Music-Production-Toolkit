# MiniMax LLM Unload (integrated)

Releases the loaded LLM model(s) and session state so VRAM/RAM is free for the following music and artwork stages.

**Node ID:** `MiniMaxLLMUnload`  
**Category:** `MiniMax Music Production Toolkit/llm`

## Inputs

- **`trigger`** (`*`, forceInput) — any value. In the example workflow the LLM chat `text` output is connected here so unloading happens strictly after the LLM finished.
- **`unload_now`** (`BOOLEAN`) — release the loaded LLM model(s) and session state.
- **`unload_flashsr`** (`BOOLEAN`) — additionally release cached FlashSR model instances (useful when the audio stage already finished).

## Outputs

- **`trigger`** (`*`) — the trigger value passed through.
- **`released_count`** (`INT`) — how many cached model instances were released.
