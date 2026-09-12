# Language models: ComfyUI, local apps and cloud

The **MiniMax LLM Chat** node can prepare your song with a GGUF inside ComfyUI,
a model served by another app, or a cloud API. Select **Run language model**;
the node shows the settings for that mode. Its three outputs and existing
workflow connections remain unchanged.

| Mode | Where the model runs | What you need |
|---|---|---|
| **In ComfyUI (GGUF)** | In the ComfyUI process | A GGUF and a compatible llama-cpp-python installation |
| **Local app / server** | In LM Studio, Ollama, llama.cpp, Unsloth Studio, vLLM or another compatible server | A running API server and a text chat model |
| **Cloud service** | At the selected provider | An API account, key and supported text model |

External modes do not load a GGUF in ComfyUI and need no additional provider
SDK. They send the assembled user prompt and system prompt as a fresh,
single-turn request. Audio and image files are not sent by this LLM node.
The song parser, MiniMax music generation and mastering continue as before.

## Quick setup: another local app

1. Open the app, download/load a **text chat or instruct model**, and start its
   API server. The app's chat window alone is not an API server.
2. Select **Local app / server**, then the app's name in the LLM node.
3. Leave **API address** empty for the default below, or enter the address shown
   by your app. Use the API base, including `/v1`, without `/chat/completions`.
4. If the server requires a key, click **Set API key…** and paste it.
5. Click **Find models / test connection…** and choose a text model. You can
   also paste its exact ID into **Model ID**. Listing models does not generate text.
6. Queue the workflow. **Connection setup / status…** shows the effective address
   and setup steps whenever you need them.

| Local app | Default API base | Setup detail |
|---|---|---|
| LM Studio | `http://127.0.0.1:1234/v1` | Start the server in the Developer area. |
| Ollama | `http://127.0.0.1:11434/v1` | Install/pull the model first; IDs include tags such as `:latest`. |
| llama.cpp | `http://127.0.0.1:8080/v1` | Run `llama-server` with your model; use the ID returned by the server. |
| Unsloth Studio | `http://127.0.0.1:8888/v1` | Enable its API and copy its API key. Some installations use port 8000; use the actual address. |
| vLLM | `http://127.0.0.1:8000/v1` | Start its OpenAI-compatible server; use the served model name. |
| Other OpenAI-compatible server | Enter your API base | Also suitable for tools such as LocalAI when their Chat Completions endpoint is enabled. |

These addresses are relative to **the computer running ComfyUI**, not necessarily
your browser. For Docker, remote ComfyUI or another computer on your network,
enter the reachable server address. Use HTTPS when sending a server key over an
untrusted network.

Local app setup references: [LM Studio](https://lmstudio.ai/docs/developer/openai-compat),
[Ollama](https://docs.ollama.com/api/openai-compatibility),
[llama.cpp](https://github.com/ggml-org/llama.cpp/tree/master/tools/server),
[Unsloth API](https://unsloth.ai/docs/basics/api),
[vLLM](https://docs.vllm.ai/en/latest/serving/openai_compatible_server/).

## Quick setup: cloud

1. Select **Cloud service**, then your provider.
2. Obtain a key in that provider's developer/API console. A chat app subscription
   does not necessarily include API access or API credit.
3. Click **Set API key…**. For Qwen, enter the correct regional workspace API
   address first. For other presets, leave the address blank unless your account
   requires a different endpoint.
4. Use **Find models…**, or enter the exact model ID from the provider's console.
   Select a text model; model lists may also include image, audio or embedding models.
5. Queue the workflow. Your prompts go to the selected provider, whose pricing,
   availability and data policies apply.

| Provider | API base when blank | Optional environment variable |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| Claude (Anthropic) | `https://api.anthropic.com/v1` | `ANTHROPIC_API_KEY` |
| Gemini (Google) | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY` |
| DeepSeek | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |
| Qwen (Alibaba Cloud) | **Enter your workspace/region API base** | Enter `DASHSCOPE_API_KEY` explicitly in Key variable, or use Set API key |
| MiniMax | `https://api.minimax.io/v1` | `MINIMAX_API_KEY` |
| OpenRouter | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| Groq | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| Other OpenAI-compatible cloud | **Enter your HTTPS API base** | Enter the variable name explicitly, or use Set API key |

**Qwen:** Copy the API base from Alibaba Cloud Model Studio for your workspace and
region. For example, Singapore workspace addresses use
`https://YOUR_WORKSPACE_ID.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`.
Replace the workspace ID; the API key must belong to the same region. The node
does not guess a region or silently send your key to a different one.
[Alibaba Cloud setup](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope).

OpenAI uses its native **Responses API** with `store=false`. Claude uses its
native **Messages API**. The remaining presets use **Chat Completions**; custom
endpoints must support that format. Model discovery uses `GET /models`. If an
endpoint does not provide a model list, manual IDs still work. These are text
adapters, not support for every provider feature, deployment type or model.
Azure-specific authentication, Bedrock, Vertex service accounts and tool execution
are not implemented.

API references: [OpenAI](https://developers.openai.com/api/docs/guides/text),
[Claude](https://platform.claude.com/docs/en/api/messages/create),
[Gemini](https://ai.google.dev/gemini-api/docs/openai),
[DeepSeek](https://api-docs.deepseek.com/),
[MiniMax](https://platform.minimax.io/docs/api-reference/text-openai-api),
[OpenRouter](https://openrouter.ai/docs/api-reference/overview),
[Groq](https://console.groq.com/docs/openai).

## Keys, sharing and saved workflows

**Set API key** uses a password field. The provider key is kept in ComfyUI server
memory, bound to the exact API base. It is not written to a file, browser storage,
workflow JSON or production record. A workflow contains only an opaque reference
to that connection. Restarting ComfyUI expires it: enter the key again, or click
**Clear session key** to use an environment variable. Changing an address also
requires a new bound key or clearing the old reference.

Only use this key facility on a trusted ComfyUI server: it is not a separate
multi-user credential vault. Someone with the workflow reference and access to
the same running server can use that connection. Do not expose an unauthenticated
ComfyUI instance to the internet.

For unattended use, set the environment variable **before starting ComfyUI**.
The **Key variable** field accepts the variable's name, never the secret itself.
Blank uses the preset's standard variable. When overriding an API address,
specify the variable explicitly or use Set API key; a different address does
not automatically inherit a provider's standard key.

Provider selection resets external address, model and credential selection to
avoid carrying settings to the wrong provider. Integrated GGUF settings are
retained. Old workflows without a mode continue to use **In ComfyUI (GGUF)**.
The integrated mode's advanced controls are behind **Show / hide advanced GGUF
settings**; hiding them does not change their stored values.

## Output length, performance and memory

- **Output token limit** defaults to 4096 for external models. Increase it if a
  response is truncated, especially with reasoning models. Limits and reasoning
  accounting depend on the provider. No automatic retry or model fallback occurs.
- External sampling, reasoning, context and GPU placement use the server/model
  defaults. The hidden GGUF sliders do not affect an external model. Configure
  local model memory and context in its own app. No chain of tools is requested.
- **Request timeout** defaults to 120 seconds (5–600 selectable). This is a network
  operation timeout, not a guaranteed maximum inference duration. Stopping a
  workflow cannot guarantee cancellation of work at an external provider; a
  blocked network call may take until its timeout to return. Check provider usage
  before retrying a timed-out cloud request.
- Every queued execution with the LLM enabled requests fresh text, even if its
  inputs are unchanged. This also means another cloud API request may be billed.
  No session ID input or helper node is needed: the node uses ComfyUI's native
  `IS_CHANGED` mechanism. External requests are single turns, not persistent chats.
- **Unload LLM** releases only models owned by this toolkit. It cannot reclaim
  another app's VRAM or RAM. Unload that model in its app if music generation
  needs the memory. Cloud mode avoids local LLM model memory, but music generation
  still runs in ComfyUI.

## Optional FLUX.2 cover

The full Music Production workflow includes **FLUX.2 cover · ON / OFF** in the
**05 · ILLUSTRATE / Cover artwork** area, next to the cover nodes it controls.
It defaults to **ON**. In the node search, enter **FLUX.2 Cover**.
Personal workflows are not automatically replaced: reopen the updated bundled
Production workflow, or add the switch and connect the two inputs listed below.

- **ON:** render and save the JPG, then embed it in audio exports as before.
- **OFF:** skip the FLUX download group and the upstream image computation. No
  new cover file is written; the saved artwork path is empty. Audio and the
  production record still export, without newly generated artwork. Existing
  files from earlier runs are not removed or reused as the new cover.

The switch connects to both `MiniMaxModelAutodownload.flux2_models` and
`SaveImageSmartPrefix.enabled`. The saver requests its lazy `image` input only
when enabled. Keep these two wires intact. A separate preview/output node
connected to the same image branch can still request generation independently.

ComfyUI validates model dropdowns before execution in some versions. If missing
FLUX filenames cause validation errors even with the switch off, mute the unused
FLUX loaders/sampler/decode branch in your personal workflow as well. Keep the
cover saver active with `enabled=false` so its empty path reaches the audio
exports. The switch skips computation; it does not rewrite host validation rules.

The bundled model check now leaves `llm_model=false`: integrated GGUF loading
already downloads its selected model on demand. This prevents downloading an
unused GGUF when using a local app or cloud. The Audio Enhancement Lab has no
LLM or FLUX branch and does not need these controls.

The old **Fresh request / Session ID** helper was removed from the example.
Loading an older workflow removes the obsolete LLM session input and its wire;
other links are retained. The legacy helper remains registered for personal
workflows that use its seed output or another LLM node. Direct Python callers
can still pass the old `session_id` argument. The LLM always reruns when enabled;
advanced integrated `reset_session=false` still concerns llama.cpp state reuse,
not ComfyUI's output cache. Without an explicit legacy Python session ID, this
advanced state cache uses the default session; keep reset on for independent songs.

## Troubleshooting

| Message / symptom | What to check |
|---|---|
| Cannot reach server | Start its API server; check the address/port from the ComfyUI host. |
| HTTP 401 / 403 | API key, account access and region. Use the server's API key, not a browser login password. |
| HTTP 404 | API base and model ID. Do not include `/chat/completions`, `/messages` or `/responses` in the base. |
| HTTP 400 | Exact model ID and its maximum output budget. A listed model may not support text generation. |
| HTTP 429 | Provider quota or rate limit; no automatic retry was sent. |
| No models listed | Load a model in the app or enter its ID manually. |
| API key expired | Re-enter it after restarting ComfyUI, or clear the session reference and use an environment variable. |
| Incomplete / reasoning-only answer | Increase output budget, choose a suitable text model or adjust the prompt. |
| Old fields still visible | Restart ComfyUI and hard-refresh the browser to reload the extension. |

## Validation and scope

Automated tests cover request bodies for every preset, native authentication,
response parsing, malformed/refused/truncated responses, exact-address key
binding, redirect rejection, loopback HTTP generation/model discovery, UI
visibility/serialization and the cover switch's graph connections. Live account
access, model availability and output quality must also be checked with your
chosen app/provider; automated tests do not spend cloud credit.
