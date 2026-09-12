# MiniMax LLM Chat — ComfyUI / local app / cloud

Integrated LLM chat node based on the public `llama-cpp-python` API. It replaces the external `ComfyUI-LLM-Session` chat node in the example workflow. No GPL code from the external node is used.

Choose **Run language model**: **In ComfyUI (GGUF)**, **Local app / server** or
**Cloud service**. Existing workflows default to the integrated mode. Its basic
controls stay visible; **Show / hide advanced GGUF settings** exposes the rest
without changing stored values.

External modes show the app/provider, API base, model ID, optional key variable,
output limit and timeout. **Set API key** stores a key in server RAM until restart,
not in the workflow. **Find models** lists the server's model IDs. **Connection
setup / status** explains the selected connection. Only text chat is supported.

Local presets: LM Studio, Ollama, llama.cpp, Unsloth Studio and vLLM. Cloud:
OpenAI, Claude, Gemini, DeepSeek, Qwen, MiniMax, OpenRouter and Groq. Both modes
also accept a custom OpenAI-compatible Chat Completions API base. For Qwen, copy
the regional workspace base from Alibaba Cloud; its key must match that region.

External modes use fresh single turns and provider sampling/reasoning defaults.
The GGUF settings below apply only inside ComfyUI. External requests do not load
local model weights; another app's model memory remains owned by that app.
Cloud sends both prompts to the provider and may incur charges. Generation is
not automatically retried after failure. Stopping ComfyUI may not cancel remote
work immediately; a blocking call can take until its network timeout to return.

For addresses, keys, memory advice and troubleshooting, see **LLM_PROVIDERS.md**
in the repository.

**Node ID:** `MiniMaxLLMChat`  
**Category:** `MiniMax Music Production Toolkit/llm`

## Inputs

- **`user_text`** (`STRING`, forceInput) — assembled user prompt (normally from `MiniMaxStructuredPromptV20`).
- **`system_prompt`** (`STRING`, forceInput) — resolved system prompt.
- **Fresh execution:** no session-ID input is needed. ComfyUI's `IS_CHANGED` hook
  makes an enabled LLM execute on every queued run, including unchanged prompts.
  Each cloud run may incur another API charge. Old session input wires are removed
  on workflow load; the helper remains registered for other legacy uses.
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
- **`reset_session`** — ON = fresh single-turn chat every run (recommended). OFF = advanced reuse of the default llama.cpp state cache. This does not control ComfyUI's output cache; the node executes on every enabled queued run.
- **`auto_download`** — fetch a missing GGUF when a download URL is configured in `models_config.json`.

## Verified models

- **Qwen3.8-27B-UD-IQ3_XXS.gguf** (Unsloth) — chat_format `auto` (chatml); reasoning comes as `<think>` blocks and is split off automatically.
- **Gemma 4** (`gemma-4-12B-it-QAT-Q4_0.gguf`) — chat_format `auto` (embedded template); clean structured output without channel markers.

The generic chatml fallback plus the thinking split keep the node working with most llama.cpp-compatible instruction models.

## Outputs

- **`text`** (`STRING`) — assistant response, parsed downstream by `MiniMaxParseExternalLLMOutputV16`.
- **`status`** (`STRING`) — one-line status (model, session mode, character count).
- **`thinking`** (`STRING`) — separately supplied reasoning or reasoning split from the answer.

## Requirements

The integrated mode needs the `llama-cpp-python` package in the ComfyUI Python environment;
external modes need no provider SDK or llama-cpp-python:

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

While streaming, the log shows a single ASCII progress bar that mirrors the node's bar: `[##########----------]  8192/16384` (0 on the left, `max_tokens` on the right), updated roughly every 10% instead of one line per token.

## Memory

Only the most recently used model stays loaded. Wire `MiniMaxLLMUnload` after this node to release it before music generation.

## Templates and thinking per family

The node picks a versioned family adapter (`llm_sampling.py`, adapter version 1) from the model file name:

- **Qwen 3.8 / 3.5 / Qwen (generic):** ChatML template; `thinking=off` is enforced with `reasoning_budget=0` where the build accepts it. The Qwen 3.8 non-thinking sampler values (temperature 0.7, top_p 0.8, top_k 20, repeat_penalty 1.0) are documented but **not applied automatically** - they belong to an explicitly chosen profile, never to a saved workflow.
- **Gemma 4 / Llama 3 / generic:** the model's own embedded template is used (`chat_format=none`) or the documented named format. These families have **no** thinking switch in the bindings.

The log states per run whether thinking control is `supported` or `NOT supported`. Where it is not supported, the toggle only separates reasoning from the answer afterwards and is **not a speedup** - the node says so instead of implying one, and an empty answer that consisted only of reasoning is reported with that explanation.

## Token statistics

`llm_chat` reports the backend's own usage when the build provides it (`source: backend`, with prompt/completion/total tokens). A streaming response without usage is reported as a **chunk count** (`source: chunks`): a stream chunk is not a token, so it is never presented as an exact token count. The status string carries the number together with its source, and unknown values stay unknown.

## Runtime options (opt-in, no widget change)

`n_batch`, `n_ubatch`, `flash_attn`, `type_k`, `type_v` and `n_threads` are passed only when the installed `llama-cpp-python` build declares the parameter. Anything unsupported - or invalid, or a typo in the name - is reported in the log instead of being dropped silently. They are configured in `models_config.json` under `llm.runtime_options`, so the node's widget list and every saved workflow stay untouched. Accepted options become part of the model cache identity: a different runtime configuration is a different model instance. `n_ubatch` 128/256/512 are the documented starting points for a benchmark.

## Hardware profile (which model class fits this machine)

The node logs a profile recommendation once per process, based on the detected device (`llm_profiles.py`, IMPROVE-TODO L01). It is advisory: it never changes a setting and never downloads anything.

| Device | Suggested class | Suggested context |
|---|---|---|
| CPU only | small 2-4B model, no automatic CPU offload of a large one | 4k |
| up to 8 GiB | small 4B class; 9B Q4_K_M only after a real budget check | 4-8k |
| 10-12 GiB | Qwen 3.5 9B Q5_K_M or Gemma 4 12B QAT Q4_0 | 8k start |
| 16 GiB | Gemma 4 12B QAT / Qwen 3.5 9B Q6_K; 27B UD-IQ3_XXS as comparison | 8-16k |
| 24 GiB | 27B UD-IQ4_XS or more | by need |
| 32 GiB+ | larger quantizations as an explicit quality profile | by need |

Anchored **file sizes** (not VRAM promises, read from the repositories on 2026-09-11): Qwen 3.5 9B Q4_K_M 6.17 GB, Q5_K_M 7.11 GB, Q6_K 7.96 GB; Gemma 4 12B QAT Q4_0 6.98 GB; Qwen 3.8 27B UD-IQ3_XXS 10.93 GB, UD-IQ4_XS 14.25 GB, UD-Q4_K_M 16.46 GB. Context/KV state, compute buffers and backend overhead are extra, and the active parameters of an MoE model do not describe its resident size.

An installed GGUF is matched by **name**; its provenance is only called verified when its size matches the anchored artifact, because a file name alone proves nothing. Already-installed candidates are offered before anything new is suggested.
