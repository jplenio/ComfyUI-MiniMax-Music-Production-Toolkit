"""Text-only LLM server adapters. No model loading, SDKs or import-time I/O.

Provider defaults are intentionally conservative: sampling/reasoning remain
server-owned. A failed generation is never retried (it may already be billed).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import socket
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MODES = ["In ComfyUI (GGUF)", "Local app / server", "Cloud service"]
# label: (API base URL, wire protocol, default credential environment variable)
LOCAL = {
    "LM Studio": ("http://127.0.0.1:1234/v1", "chat", ""),
    "Ollama": ("http://127.0.0.1:11434/v1", "chat", ""),
    "llama.cpp": ("http://127.0.0.1:8080/v1", "chat", ""),
    "Unsloth Studio": ("http://127.0.0.1:8888/v1", "chat", "UNSLOTH_API_KEY"),
    "vLLM": ("http://127.0.0.1:8000/v1", "chat", ""),
    "Other OpenAI-compatible server": ("", "chat", ""),
}
CLOUD = {
    "OpenAI": ("https://api.openai.com/v1", "responses", "OPENAI_API_KEY"),
    "Claude (Anthropic)": ("https://api.anthropic.com/v1", "anthropic", "ANTHROPIC_API_KEY"),
    "Gemini (Google)": ("https://generativelanguage.googleapis.com/v1beta/openai", "chat", "GEMINI_API_KEY"),
    "DeepSeek": ("https://api.deepseek.com/v1", "chat", "DEEPSEEK_API_KEY"),
    "Qwen (Alibaba Cloud)": ("", "chat", "DASHSCOPE_API_KEY"),
    "MiniMax": ("https://api.minimax.io/v1", "chat", "MINIMAX_API_KEY"),
    "OpenRouter": ("https://openrouter.ai/api/v1", "chat", "OPENROUTER_API_KEY"),
    "Groq": ("https://api.groq.com/openai/v1", "chat", "GROQ_API_KEY"),
    "Other OpenAI-compatible cloud": ("", "chat", ""),
}
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_KEYS = {}  # opaque handle -> (API base, secret); never written to disk
_KEY_LOCK = threading.Lock()


def connection(backend, local_provider="LM Studio", cloud_provider="OpenAI", server_url=""):
    if backend not in MODES[1:]:
        raise ValueError("Choose Local app / server or Cloud service.")
    catalog = LOCAL if backend == MODES[1] else CLOUD
    provider = local_provider if backend == MODES[1] else cloud_provider
    if provider not in catalog:
        raise ValueError("Unknown LLM provider. Select a provider from the list.")
    default, protocol, env = catalog[provider]
    base = (server_url or default).strip().rstrip("/")
    try:
        parsed = urlsplit(base)
        _ = parsed.port  # validate the port even when it is not otherwise used
    except ValueError:
        raise ValueError("Invalid server address or port.") from None
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or any(c.isspace() for c in base) or "{" in base or "}" in base):
        raise ValueError("Enter the API base address (including /v1), without keys, query parameters or placeholders.")
    if backend == MODES[2] and parsed.scheme != "https":
        raise ValueError("Cloud services require an https:// API address.")
    # An overridden URL must not silently inherit a known provider's secret.
    # Users can explicitly select an environment variable or enter a bound key.
    if server_url.strip() and base != default:
        env = ""
    return provider, base, protocol, env


def _validate_key(key):
    if not isinstance(key, str):
        raise ValueError("Enter a valid API key.")
    key = key.strip()
    if not key or len(key) > 8192 or any(not 33 <= ord(c) <= 126 for c in key):
        raise ValueError("API key must contain only printable ASCII characters without spaces or line breaks.")
    return key


def remember_key(base, key, previous=""):
    """Bind a browser-entered key to an exact API base, not a provider label."""
    key = _validate_key(key)
    with _KEY_LOCK:
        if previous in _KEYS and _KEYS[previous][0] == base:
            del _KEYS[previous]
        if len(_KEYS) >= 128:
            raise ValueError("Too many stored connections. Restart ComfyUI to clear session keys.")
        handle = secrets.token_urlsafe(32)
        _KEYS[handle] = (base, key)
    return handle


def forget_key(handle):
    with _KEY_LOCK:
        _KEYS.pop(handle, None)


def credential(base, default_env, api_key_env="", credential_id="", required=False):
    if credential_id:
        with _KEY_LOCK:
            stored = _KEYS.get(credential_id)
        if not stored or stored[0] != base:
            raise ValueError("API key expired or server address changed. Use Set API key again, or Clear session key to use an environment variable.")
        return stored[1]
    env = (api_key_env or default_env).strip()
    if env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env):
        raise ValueError("API key environment variable must be a variable NAME, not the key itself.")
    key = os.environ.get(env, "").strip() if env else ""
    if required and not key:
        raise ValueError("API key missing. Click Set API key on the LLM node, or configure its API key environment variable before starting ComfyUI.")
    return _validate_key(key) if key else ""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # never forward a credential to a redirect destination


def request_json(url, key, protocol, payload=None, timeout=120):
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "ComfyUI-LLM-Adapter/1.0"}
    if protocol == "anthropic":
        headers["anthropic-version"] = "2023-06-01"
        if key:
            headers["x-api-key"] = key
    elif key:
        headers["Authorization"] = "Bearer " + key
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=max(5, min(600, int(timeout)))) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("LLM server response is too large.")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("LLM server returned an unexpected response format.")
        return result
    except HTTPError as exc:
        code = exc.code
        exc.close()
        advice = {
            400: "Check the model ID and output token limit.",
            401: "Set a valid API key for this server.",
            403: "Check account permissions and the key's region.",
            404: "Check the API base address and model ID.",
            429: "Check quota/rate limits and try again later.",
        }.get(code, "Check the provider status and server address.")
        # Do not expose provider response bodies, request headers or URLs.
        raise RuntimeError(f"LLM server returned HTTP {code}. {advice} No automatic retry was made.") from None
    except (TimeoutError, socket.timeout):
        raise RuntimeError("LLM request timed out. Check the server or increase Request timeout. The server may still be processing; no retry was made.") from None
    except (URLError, OSError):
        raise RuntimeError("Cannot reach the LLM server. Start its API server and check the address, port, network and TLS certificate.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("LLM server did not return valid JSON. Use its API base address, not its web interface address.") from None


def _texts(blocks, kind="text", field="text"):
    return "\n".join(b[field] for b in (blocks or []) if isinstance(b, dict)
                     and b.get("type") == kind and isinstance(b.get(field), str))


def parse_response(result, protocol):
    """Return final text, separately supplied reasoning and usage; reject partials."""
    if result.get("error"):
        raise RuntimeError("LLM provider reported an error. Check the model and account in the provider's console.")
    thinking = ""
    try:
        if protocol == "responses":
            if result.get("status") != "completed":
                raise RuntimeError("LLM response was incomplete. Increase Output token limit or check provider status.")
            text = "\n".join(_texts(item.get("content"), "output_text") for item in result.get("output", []) if item.get("type") == "message")
            thinking = "\n".join(_texts(item.get("summary"), "summary_text") for item in result.get("output", []) if item.get("type") == "reasoning")
        elif protocol == "anthropic":
            if result.get("stop_reason") not in ("end_turn", "stop_sequence"):
                raise RuntimeError("Claude did not finish a text answer. Increase Output token limit if the answer was truncated.")
            text = _texts(result.get("content"))
            thinking = _texts(result.get("content"), "thinking", "thinking")
        else:
            choice = result["choices"][0]
            if choice.get("finish_reason") not in ("stop", None):
                raise RuntimeError("LLM did not finish a text answer (token limit, refusal or tool call). Check the model and Output token limit.")
            message = choice["message"]
            if message.get("tool_calls") or message.get("refusal"):
                raise RuntimeError("LLM returned a tool call or refusal instead of song text. Choose a text chat model or revise the prompt.")
            content = message.get("content")
            text = content if isinstance(content, str) else _texts(content)
            thinking = message.get("reasoning_content") or message.get("reasoning") or ""
            if not isinstance(thinking, str):
                thinking = ""
        if not text.strip():
            raise RuntimeError("LLM returned no final text. Choose a text chat model, revise the prompt, or increase Output token limit.")
        return text.strip(), thinking.strip(), result.get("usage") or {}
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ValueError("Unexpected LLM response format. Check that this server supports the selected API.") from None


def remote_chat(*, backend, user_text, system_prompt, local_provider="LM Studio",
                cloud_provider="OpenAI", server_url="", remote_model="", api_key_env="",
                credential_id="", remote_max_tokens=4096, request_timeout=120):
    provider, base, protocol, env = connection(backend, local_provider, cloud_provider, server_url)
    model = remote_model.strip()
    if not model or len(model) > 512:
        raise ValueError("Choose a model with Find models, or enter its exact model ID.")
    limit = int(remote_max_tokens)
    if not 1 <= limit <= 131072:
        raise ValueError("Output token limit must be between 1 and 131072.")
    key = credential(base, env, api_key_env, credential_id, backend == MODES[2])
    payload = {"model": model}
    if protocol == "responses":
        endpoint = "/responses"
        payload.update(input=user_text, instructions=system_prompt or "", max_output_tokens=limit, store=False)
    elif protocol == "anthropic":
        endpoint = "/messages"
        payload.update(messages=[{"role": "user", "content": user_text}], max_tokens=limit)
        if system_prompt:
            payload["system"] = system_prompt
    else:
        endpoint = "/chat/completions"
        messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
        messages.append({"role": "user", "content": user_text})
        payload.update(messages=messages, max_tokens=limit, stream=False)
    start = time.monotonic()
    result = request_json(base + endpoint, key, protocol, payload, request_timeout)
    text, thinking, usage = parse_response(result, protocol)
    status = f"LLM ok: provider={provider}, model={model}, session=single-turn, chars={len(text)}, elapsed={time.monotonic()-start:.1f}s, sampling=provider defaults"
    return text, status, thinking


def list_remote_models(**options):
    provider, base, protocol, env = connection(options["backend"], options.get("local_provider", "LM Studio"), options.get("cloud_provider", "OpenAI"), options.get("server_url", ""))
    key = credential(base, env, options.get("api_key_env", ""), options.get("credential_id", ""), options["backend"] == MODES[2])
    result = request_json(base + "/models", key, protocol, timeout=15)
    items = result.get("data")
    if not isinstance(items, list):
        raise ValueError("This server did not return a compatible model list. Enter the model ID manually.")
    models = sorted({item["id"] for item in items if isinstance(item, dict)
                     and isinstance(item.get("id"), str) and 0 < len(item["id"]) <= 512})
    if not models:
        raise ValueError("No models listed. Load a model in the local app, or enter its model ID manually.")
    return models[:1000]
