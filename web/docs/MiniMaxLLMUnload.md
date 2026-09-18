# MiniMax LLM Unload (integrated)

Releases the loaded LLM model(s) and session state so VRAM/RAM is free for the following music and artwork stages.

Only models loaded inside this toolkit are released. Models in LM Studio,
Ollama, llama.cpp, Unsloth Studio or other servers remain under that app's
control; this node does not send external unload/shutdown requests.

**Node ID:** `MiniMaxLLMUnload`  
**Category:** `Music Production Toolkit/llm`

## Inputs

- **`trigger`** (`*`, forceInput) — any value. In the example workflow the LLM chat `text` output is connected here so unloading happens strictly after the LLM finished.
- **`unload_now`** (`BOOLEAN`) — release the loaded LLM model(s) and session state.
- **`unload_flashsr`** (`BOOLEAN`) — additionally release cached FlashSR model instances (useful when the audio stage already finished).

## Outputs

- **`trigger`** (`*`) — the trigger value passed through.
- **`released_count`** (`INT`) — how many cached model instances were released.
