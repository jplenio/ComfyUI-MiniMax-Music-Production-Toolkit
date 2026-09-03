# MiniMax LLM Chat (integrated)

Integrated LLM chat node based on the public `llama-cpp-python` API. It replaces the external `ComfyUI-LLM-Session` chat node in the example workflow. No GPL code from the external node is used.

**Node ID:** `MiniMaxLLMChat`  
**Category:** `MiniMax Music Production Toolkit/llm`

## Inputs

- **`user_text`** (`STRING`, forceInput) — assembled user prompt (normally from `MiniMaxStructuredPromptV20`).
- **`system_prompt`** (`STRING`, forceInput) — resolved system prompt.
- **`session_id`** (`STRING`, forceInput) — session/cache-buster from `MiniMaxLLMSessionId`; a new value re-runs generation instead of reusing ComfyUI's output cache.
- **`model`** — llama.cpp-compatible GGUF from `models/llm`. The bundled workflow's example model name is always offered so existing workflows keep loading.
- **`max_tokens`** — response token budget (example: `16384`).
- **`temperature`** / **`top_p`** / **`top_k`** / **`min_p`** — sampling controls (LM Studio defaults: `0.7` / `0.8` / `40` / `0.0`).
- **`repeat_penalty`** / **`presence_penalty`** / **`frequency_penalty`** — repetition controls (defaults `1.1` / `0.0` / `0.0`).
- **`seed`** — sampling seed (`-1` = random per run).
- **`n_gpu_layers`** — GPU offload (`-1` = as many as possible).
- **`n_ctx`** — context window (example: `32768`).
- **`chat_format`** — chat template: `auto` picks the verified template for the model family (chatml for Qwen-style models, the model's own embedded template for Gemma), `none` uses the GGUF's own template, or choose `chatml` / `qwen` / `gemma` / `llama-3` explicitly.
- **`thinking`** — `off` asks the backend to disable reasoning and always splits any remaining thinking blocks off the answer; `on` / `auto` keep them. Reasoning is logged and recorded separately either way.
- **`split_mode`** — multi-GPU distribution: `layer` (sequential layer split) or `row` (split parallel); `none` disables it.
- **`tensor_split`** — VRAM distribution: empty = auto, `even` = evenly across all GPUs, or comma-separated fractions/weights.
- **`main_gpu`** — GPU index for intermediate results (normally `0`).
- **`tensor_parallel`** — true tensor parallelism when the installed llama-cpp-python build supports it (0.3.48 does not; falls back to split modes with a warning).
- **`reset_session`** — ON = fresh single-turn chat every run (recommended). OFF = llama.cpp session state per `session_id`.
- **`auto_download`** — fetch a missing GGUF when a download URL is configured in `models_config.json`.

## Verified models

- **Qwen3.8-27B-UD-IQ3_XXS.gguf** (Unsloth) — chat_format `auto` (chatml); reasoning comes as `<think>` blocks and is split off automatically.
- **Gemma 4** (`gemma-4-12B-it-QAT-Q4_0.gguf`) — chat_format `auto` (embedded template); clean structured output without channel markers.

The generic chatml fallback plus the thinking split keep the node working with most llama.cpp-compatible instruction models.

## Outputs

- **`text`** (`STRING`) — assistant response, parsed downstream by `MiniMaxParseExternalLLMOutputV16`.
- **`status`** (`STRING`) — one-line status (model, session mode, character count).

## Requirements

The node needs the `llama-cpp-python` package in the ComfyUI Python environment:

```bash
python -m pip install llama-cpp-python
```

When it is missing, the node still registers and produces a clear error at execution time instead of breaking ComfyUI startup.

## Failure behavior

- Empty `user_text` → clear error (typically the upstream prompt node was bypassed; the parser node supports manual fallback fields for exactly this case).
- Model file missing and no download URL configured → clear error naming the expected location.
- Empty assistant response → error pointing at the LLM log, so a downstream parser error cannot mask an upstream generation failure.

## Logging

The node logs the model load, the LLM environment (llama.cpp version, GGUF inventory) once per process, and the **full assistant output**. llama.cpp is constructed with `verbose=False`, so its per-token debug output does not flood the log - one consistent INFO line per run instead.

## Memory

Only the most recently used model stays loaded. Wire `MiniMaxLLMUnload` after this node to release it before music generation.
