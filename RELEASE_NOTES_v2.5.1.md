# Release Notes – v2.5.1

Release date: 2026-09-13

## Summary

2.5.1 makes the language-model stage a first-class choice. The LLM node now runs
either the bundled GGUF inside ComfyUI, a model served by a local app, or a cloud
service — selected in the node, with the same outputs as before. A new switch
turns FLUX.2 cover generation off completely (rendering, saving and preflight
downloads), and the example workflow's layout, node ownership and release gates
were brought back in line with the documentation.

Everything in 2.5.0 still applies: the redesigned workflows, the mastering
section with auto-EQ, parametric EQ, compressor and true-peak limiter, and the
Audio Enhancement Lab.

## Added

- **LLM backend selection.** The `MiniMaxLLMChat` node offers three modes:
  `In ComfyUI (GGUF)` (unchanged default), `Local app / server`, and
  `Cloud service`. The node shows only the controls the selected mode needs.
- **Local app / server presets:** LM Studio (`127.0.0.1:1234`), Ollama
  (`11434`), llama.cpp (`8080`), Unsloth Studio (`8888`), vLLM (`8000`), and any
  other OpenAI-compatible server.
- **Cloud service presets:** OpenAI (Responses API), Claude (Anthropic), Gemini
  (Google), DeepSeek, Qwen (Alibaba Cloud), MiniMax, OpenRouter and Groq, plus
  any other OpenAI-compatible cloud endpoint. Each provider has its documented
  credential environment variable (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`, `MINIMAX_API_KEY`,
  `OPENROUTER_API_KEY`, `GROQ_API_KEY`).
- **Model discovery and a setup dialog.** Available models can be listed from the
  selected endpoint, or entered by hand. The connection setup (backend, provider,
  address, model, key) is reachable from the node.
- **Session-only API keys.** A key entered in the browser is held in memory for
  the session and is never written into the workflow or to disk.
- **FLUX.2 cover switch (`MiniMaxCoverControl`).** One boolean, enabled by
  default, wired to both `SaveImageSmartPrefix.enabled` and
  `MiniMaxModelAutodownload.flux2_models`. Switched off, no cover is rendered or
  saved, the FLUX preflight download is skipped, and the audio export continues
  with an empty artwork path. Previously written JPGs are not deleted.
- **Documentation and tests.** New `LLM_PROVIDERS.md` setup guide (local apps,
  cloud, keys, output length, optional cover, troubleshooting), updated node
  pages for the three LLM nodes and the cover switch, plus provider, transport,
  UI and cover regression tests including two frontend suites.

## Changed

- **LLM execution uses ComfyUI's cache invalidation.** An enabled run generates
  fresh text instead of replaying the previous completion.
- **The session helper is gone.** `MiniMaxLLMSessionId` was removed from the
  example workflow and the LLM node no longer takes a session input; stored
  workflows with those wires migrate on load without disturbing other links.
- **The production workflow got a visual pass.** The LLM node is titled
  `LLM · In ComfyUI / Local app / Cloud`, its panel and the prompt-report panel
  are taller so the new controls fit without scrolling, and node positions and
  group sizes were tidied. The saved view opens on the mastering chain and the
  artwork lane, where the cover switch and the master controls live.
- **The workflow's generic LLM preflight is off.** The integrated LLM downloads
  its selected GGUF on demand; external providers manage their own models.
- The production workflow grew from 48 to 50 nodes (cover switch, preview nodes).

## Fixed

- **The cover-switch documentation matches the shipped layout.** The switch
  lives in `05 · ILLUSTRATE / Cover artwork` with the cover nodes it controls —
  its `cover_enabled` output feeds the image saver and the FLUX.2 preflight
  download next to it. The node page, the README, `WORKFLOW_OPTIMIZED.md` and
  `LLM_PROVIDERS.md` now all describe that placement, and the layout test pins
  it together with both connections.
- **`PreviewImage` and `PreviewAudio` are registered** as ComfyUI-core node types
  in the node-ownership test, so the preview nodes in the example workflow are
  covered instead of reported as unknown owners.
- **The FFmpeg pipe timeout test no longer races the process start.** It used
  0.2 s of audio with a 1 ms deadline, so FFmpeg occasionally finished in time
  and the expected timeout never occurred — a flaky test that could fail a
  release build at random. The workload is now long enough that the deadline is
  always reached while FFmpeg is still working.

## Breaking changes

None. Node identifiers, input and output names, return orders and the GGUF
defaults are unchanged. Existing workflows load as before; the removed session
wires migrate automatically.

## Upgrade notes

- Open the updated bundled workflow to get the cover switch and the new LLM
  menus. An update never inserts nodes into personal workflows — search for
  **FLUX.2 Cover** to add the switch to your own, and connect `cover_enabled` to
  `SaveImageSmartPrefix.enabled` and `MiniMaxModelAutodownload.flux2_models`.
- For cloud or local-app use, set the provider's environment variable (or type
  the key into the node for the current session). Unattended and API runs should
  use the environment variable.
- Keep the cover saver active even when the switch is off; some ComfyUI versions
  validate missing model dropdowns before execution. See `LLM_PROVIDERS.md`.

## Validation

- Full test suite: **837 tests, OK** (1 skipped: `mutagen` is not installed in
  the development environment).
- `scripts/validate_release.py`: **Release validation OK**, privacy scan clean.
- `scripts/dump_node_contracts.py --check`: contract snapshot up to date.
- Both example workflows re-validated: graph integrity, group containment, no
  overlapping nodes, canonical node ownership.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.5.1.zip`
- `MiniMax_Music3_Production_Toolkit_v2.5.1.json`
- `SHA256SUMS.txt`
