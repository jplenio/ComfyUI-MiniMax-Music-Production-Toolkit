"""Integrated LLM chat and unload nodes (llama.cpp via llama-cpp-python).

These replace the external ``ComfyUI-LLM-Session`` nodes used by the example
workflow with a small, self-contained implementation:

- ``MiniMaxLLMChat`` loads a GGUF from ``models/llm``, sends one system+user
  turn and returns the assistant text.  Optional session state keyed by
  ``session_id`` supports multi-turn conversations across runs.
- ``MiniMaxLLMUnload`` releases loaded LLM models (and optionally cached
  FlashSR runners) so VRAM/RAM is available for the music generation stage.

No code from the GPL-licensed external node is used; only the public
llama-cpp-python API.  If llama-cpp-python is not installed, the nodes still
register and explain the missing dependency clearly at execution time.

The example GGUF name from the bundled workflow is offered in the model combo
even when the file is not present, so existing workflows keep loading; a
missing model file produces a clear error (or triggers a configured
auto-download from :file:`models_config.json`).
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .model_downloader import check_file_entries, load_models_config, resolve_target
from .toolkit_logging import get_logger

LOGGER = get_logger("llm")

GGUF_SUFFIX = ".gguf"
EXAMPLE_MODEL_NAME = "Qwen3.8-27B-UD-IQ3_XXS.gguf"
PLACEHOLDER_MODEL = "(no GGUF model found in models/llm)"

# The Qwen-style GGUF separates its reasoning into <think>...</think> tags
# when a chat format is applied; the Gemma 4 GGUF works best with its own
# embedded template (chat_format=None).  Verified against both bundled
# example models with llama-cpp-python 0.3.48 (its "qwen3" handler does not
# exist there).
CHAT_FORMAT = "chatml"
_THINK_BLOCK_RE = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)
_SECTION_SCAN_RE = re.compile(
    r"\[(?:Title|Caption|Lyrics|Count|Song[-_\s]?Count|Image[-_\s]?Prompt)\]",
    re.IGNORECASE,
)
_JUNK_PREAMBLE_RE = re.compile(r"<think|</think|<\|channel|\bthought\b", re.IGNORECASE)


def _split_thinking_tags(text: str) -> tuple:
    """Split reasoning away from the assistant text.

    Returns ``(clean_text, thinking)``.  Handles the variants observed with
    real models: well-formed ``<think>...</think>`` blocks, a lone ``</think>``
    without opener, malformed openers like ``<think>/`` that never close, and
    Gemma's ``<|channel>thought ... <|channel|>`` markers.  In every case the
    reasoning ends up in ``thinking`` and the parsed answer stays clean.
    """
    raw = (text or "").strip()

    # 1. Well-formed think blocks.
    matches = list(_THINK_BLOCK_RE.finditer(raw))
    if matches:
        thinking_parts = [m.group(1).strip() for m in matches if m.group(1).strip()]
        clean = _THINK_BLOCK_RE.sub("", raw).strip()
        return clean, "\n\n".join(thinking_parts)

    # 2. Lone closing tag without opener: everything before it is thinking.
    if "</think>" in raw and "<think" not in raw:
        thinking, clean = raw.split("</think>", 1)
        return clean.strip(), thinking.strip()

    # 3. Junk preamble (thinking/channel markers) before the first real
    #    section header - e.g. a malformed "<think>/" that never closes or
    #    Gemma's "<|channel>thought ... <|channel|>" markers.  The scan is
    #    intentionally not line-anchored: Gemma puts "[Caption]" directly
    #    behind its closing marker.
    section = _SECTION_SCAN_RE.search(raw)
    if section and section.start() > 0:
        preamble = raw[: section.start()].strip()
        if _JUNK_PREAMBLE_RE.search(preamble):
            return raw[section.start() :].strip(), preamble

    return raw, ""

# ---------------------------------------------------------------------------
# model discovery / session cache
# ---------------------------------------------------------------------------

_loaded_models: Dict[str, Any] = {}
_loaded_llama_cpp = None
_sessions: Dict[str, bytes] = {}


def _import_llama_cpp():
    global _loaded_llama_cpp
    if _loaded_llama_cpp is not None:
        return _loaded_llama_cpp
    try:
        import llama_cpp  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "The integrated LLM node needs the 'llama-cpp-python' package. "
            "Install it with: python -m pip install llama-cpp-python "
            f"(underlying error: {type(exc).__name__}: {exc})"
        ) from exc
    _loaded_llama_cpp = llama_cpp
    return llama_cpp


def _llm_directories() -> List[Path]:
    """Directories that may contain llama.cpp GGUF models.

    Inside ComfyUI the ``llm`` category is resolved via ``folder_paths`` and
    registered on first use so ``--models-directory "F:\\ComfyUI\\models"``
    (and any extra model paths) are honored.  Outside ComfyUI the
    ``COMFYUI_MODELS_DIRECTORY`` environment variable is used, then the
    working directory's ``models/llm``.
    """
    directories: List[Path] = []
    try:
        import folder_paths  # type: ignore

        paths: List[str] = []
        try:
            paths = list(folder_paths.get_folder_paths("llm"))
        except Exception:
            paths = []
        if not paths:
            models_dir = getattr(folder_paths, "models_dir", None)
            if models_dir:
                llm_dir = os.path.join(models_dir, "llm")
                try:
                    folder_paths.add_model_folder_path("llm", llm_dir)
                    paths = list(folder_paths.get_folder_paths("llm"))
                except Exception:
                    paths = [llm_dir]
        directories = [Path(p) for p in paths]
    except Exception:
        directories = []
    if not directories:
        base = os.environ.get("COMFYUI_MODELS_DIRECTORY")
        if base:
            directories = [Path(base) / "llm"]
        else:
            base_path = os.environ.get("COMFYUI_BASE_PATH")
            directories = [Path(base_path) / "models" / "llm"] if base_path else [Path.cwd() / "models" / "llm"]
    return directories


def list_llm_models() -> List[str]:
    """GGUF files available in the ComfyUI models/llm folders."""
    names: List[str] = []
    seen = set()
    for directory in _llm_directories():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(f"*{GGUF_SUFFIX}")):
            if path.name not in seen:
                seen.add(path.name)
                names.append(path.name)
    return names


_ENVIRONMENT_LOGGED = False


def collect_llm_diagnostics() -> Dict[str, str]:
    """Collect version facts about the local LLM stack without importing models.

    This is the lightweight recovery aid for support requests: it records the
    llama.cpp backend and interpreter versions (when available) so an LLM
    failure can be diagnosed without depending on any specific LLM node.
    """
    details: Dict[str, str] = {}
    try:
        import sys as _sys
        details["python_version"] = _sys.version.split()[0]
    except Exception:  # pragma: no cover - sys is always importable
        pass
    try:
        import llama_cpp  # type: ignore
        details["llama_cpp_version"] = str(getattr(llama_cpp, "__version__", "unknown"))
        details["llama_cpp_module"] = str(getattr(llama_cpp, "__file__", "unknown"))
        details["tensor_parallel_supported"] = str(_accepts_kwarg(llama_cpp.Llama.__init__, "tensor_parallel"))
        details["split_modes_supported"] = str(_accepts_kwarg(llama_cpp.Llama.__init__, "split_mode"))
    except Exception as exc:
        details["llama_cpp_error"] = f"{type(exc).__name__}: {exc}"
    details["cuda_gpu_count"] = str(_gpu_device_count())
    try:
        model_files = list_llm_models()
    except Exception as exc:
        model_files = []
        details["llm_model_list_error"] = f"{type(exc).__name__}: {exc}"
    details["llm_model_count"] = str(len(model_files))
    details["llm_models"] = ", ".join(model_files[:20]) or "(none)"
    details["llm_directories"] = "; ".join(str(p) for p in _llm_directories())
    return details


def log_llm_environment_once() -> None:
    """Log the LLM environment once per process, for failure diagnostics."""
    global _ENVIRONMENT_LOGGED
    if _ENVIRONMENT_LOGGED:
        return
    _ENVIRONMENT_LOGGED = True
    import json as _json
    LOGGER.info("LLM environment: %s", _json.dumps(collect_llm_diagnostics(), ensure_ascii=False))


def _find_model_path(name: str) -> Optional[Path]:
    for directory in _llm_directories():
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _configured_llm_entry(name: str) -> Optional[Dict[str, Any]]:
    config = load_models_config()
    llm = config.get("llm", {})
    for entry in llm.get("files", []):
        if entry.get("name") == name:
            return entry
    example = llm.get("example", {})
    if example.get("name") == name and example.get("url"):
        return example
    return None


def _accepts_kwarg(method, name: str) -> bool:
    """Whether ``method`` declares a parameter with the given name.

    llama-cpp-python varies between releases (min_p, reasoning_budget,
    tensor_parallel, ...); parameters are passed only when supported so the
    node keeps working across versions and across models.
    """
    try:
        import inspect
        return name in inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False


_SPLIT_MODES = {"none": 0, "layer": 1, "row": 2}


def _gpu_device_count() -> int:
    """Number of CUDA GPUs visible to the backend (0 = CPU-only or unknown)."""
    try:
        import torch  # type: ignore
        return int(torch.cuda.device_count())
    except Exception:
        return 0


def _parse_tensor_split(value: str, device_count: int) -> Optional[List[float]]:
    """Resolve the tensor_split widget to VRAM fractions per GPU.

    ``""``        -> None (llama.cpp auto-distributes)
    ``"even"``    -> [1/n, ...] across all GPUs ("Split evenly")
    ``"2,3"``     -> fractions or relative weights, normalized to sum 1

    Invalid or non-positive input never fails the run: it falls back to the
    automatic GPU distribution with a clear warning, because a bad split hint
    must not block generation.
    """
    text = (value or "").strip().lower()
    if not text:
        return None
    if text == "even":
        if device_count < 2:
            LOGGER.warning("tensor_split='even' requested but only %d GPU(s) detected; using auto split.", device_count)
            return None
        return [1.0 / device_count] * device_count
    parts = [part for part in re.split(r"[,\s]+", text) if part]
    if not parts:
        return None
    try:
        weights = [float(part) for part in parts]
    except ValueError:
        LOGGER.warning(
            "tensor_split '%s' is not a list of numbers; falling back to auto GPU distribution.",
            value,
        )
        return None
    positive = [weight for weight in weights if math.isfinite(weight) and weight > 0]
    if len(positive) != len(weights):
        LOGGER.warning("tensor_split '%s' contained non-positive entries; ignoring them.", value)
    if not positive:
        LOGGER.warning(
            "tensor_split '%s' has no positive weights; falling back to auto GPU distribution.",
            value,
        )
        return None
    total = sum(positive)
    if 0.99 <= total <= 1.01:
        return positive
    return [weight / total for weight in positive]


def _thinking_instruction(mode: str) -> str:
    """System-prompt prefix for the thinking toggle.

    Prompt-level thinking suppression proved unreliable (Qwen-style models
    ignore or mangle it); the toggle is instead enforced by the split in
    :func:`_split_thinking_tags` plus a ``reasoning_budget=0`` hint where the
    backend supports it.  This helper is kept for future backends with native
    reasoning control.
    """
    return ""


def _get_model(
    model_name: str,
    auto_download: bool,
    n_gpu_layers: int = -1,
    n_ctx: int = 32768,
    chat_format: str = "auto",
    split_mode: str = "layer",
    tensor_split: str = "",
    main_gpu: int = 0,
    tensor_parallel: bool = False,
):
    """Return a loaded Llama instance for ``model_name``, loading it if needed."""
    global _loaded_models
    llama_cpp = _import_llama_cpp()
    model_path = _find_model_path(model_name)

    if model_path is None:
        entry = _configured_llm_entry(model_name)
        if entry and entry.get("url") and auto_download:
            report = check_file_entries([entry], base_path=None, auto_download=True)
            failed = [item for item in report if item["status"] == "failed"]
            if failed:
                raise RuntimeError("LLM model download failed: " + "; ".join(i["message"] for i in failed))
            model_path = _find_model_path(model_name)
        if model_path is None:
            if entry and entry.get("url") and not auto_download:
                raise RuntimeError(
                    f"LLM model '{model_name}' is missing and auto-download is disabled. "
                    "Enable auto_download or place the GGUF in models/llm."
                )
            raise RuntimeError(
                f"LLM model '{model_name}' was not found in models/llm and no download URL is "
                "configured in models_config.json. Place a llama.cpp-compatible GGUF in "
                "models/llm or select a different model."
            )

    options = {"n_gpu_layers": int(n_gpu_layers), "n_ctx": int(n_ctx)}
    # "auto" = the best verified template for the selected model family:
    # chatml for Qwen-style models (clean <think> tag handling), the model's
    # own embedded template for Gemma (verified clean with Gemma 4), chatml
    # as the generic fallback.  "none" = raw/embedded template; named formats
    # are passed through.
    resolved_format = (chat_format or "auto").strip().lower()
    if resolved_format == "auto":
        name_lower = (model_name or "").lower()
        if "gemma" in name_lower:
            resolved_format = "none"
        else:
            resolved_format = CHAT_FORMAT
    if resolved_format != "none":
        options["chat_format"] = resolved_format

    device_count = _gpu_device_count()
    split = _parse_tensor_split(tensor_split, device_count)
    if split:
        options["tensor_split"] = split
    options["split_mode"] = int(_SPLIT_MODES.get((split_mode or "none").strip().lower(), 0))
    options["main_gpu"] = int(main_gpu)
    if tensor_parallel:
        if _accepts_kwarg(llama_cpp.Llama.__init__, "tensor_parallel"):
            options["tensor_parallel"] = True
            LOGGER.info("LLM tensor parallelism requested (supported by this llama-cpp-python build).")
        else:
            LOGGER.warning(
                "Tensor parallelism is not available in llama-cpp-python %s; "
                "falling back to split modes (layer/row).",
                getattr(llama_cpp, "__version__", "unknown"),
            )

    cache_key = f"{model_path}|" + "|".join(f"{key}={value}" for key, value in sorted(options.items()))
    cached = _loaded_models.get(cache_key)
    if cached is not None:
        return cached

    LOGGER.info(
        "Loading LLM model: %s (n_ctx=%d, n_gpu_layers=%d, chat_format=%s, split_mode=%s, gpus=%d)",
        model_path, options["n_ctx"], options["n_gpu_layers"],
        options.get("chat_format", "none"), options["split_mode"], device_count,
    )
    # verbose=False keeps llama.cpp's per-token debug output out of the log;
    # the chat format makes Qwen-style models emit their reasoning as <think>
    # tags so it can be split off from the real answer.
    model = llama_cpp.Llama(model_path=str(model_path), verbose=False, **options)
    # Keep only the most recently used model loaded to limit memory usage.
    for other_key, other_model in list(_loaded_models.items()):
        if other_key != cache_key:
            LOGGER.info("Unloading previous LLM model: %s", other_key)
            try:
                other_model.close()
            except Exception:
                pass
    _loaded_models = {cache_key: model}
    return model


def _accepts_cache_prompt(model) -> bool:
    """Whether the bound create_chat_completion accepts the cache_prompt kwarg.

    The llama-cpp-python API varies between releases: ``cache_prompt`` exists in
    some versions and is absent in others (e.g. 0.3.48).  Prompt caching is a
    performance optimization only, so it is skipped when unsupported instead of
    breaking generation.
    """
    method = getattr(model, "create_chat_completion", None)
    if method is None:
        return False
    try:
        import inspect
        return "cache_prompt" in inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False


def _run_chat(
    model,
    system_prompt: str,
    user_text: str,
    max_tokens: int = 16384,
    temperature: float = 0.7,
    top_p: float = 0.8,
    top_k: int = 40,
    min_p: float = 0.0,
    repeat_penalty: float = 1.1,
    presence_penalty: float = 0.0,
    frequency_penalty: float = 0.0,
    seed: int = -1,
    thinking: str = "auto",
) -> tuple:
    """Run one chat turn; return ``(clean_text, thinking)``.

    Sampling parameters mirror the LM Studio set (temperature, top_k, top_p,
    min_p, repeat/presence/frequency penalty, seed).  Each one is passed only
    when the installed llama-cpp-python build actually accepts it, so the node
    keeps working across versions.  Qwen-style reasoning (``<think>`` tags) is
    split off; with ``thinking="off"`` a reasoning_budget=0 hint is added where
    supported.
    """
    kwargs = {
        "messages": [
            {"role": "system", "content": system_prompt or ""},
            {"role": "user", "content": user_text or ""},
        ],
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "top_p": float(top_p),
    }
    extra = {
        "top_k": int(top_k),
        "min_p": float(min_p),
        "repeat_penalty": float(repeat_penalty),
        "presence_penalty": float(presence_penalty),
        "frequency_penalty": float(frequency_penalty),
        "seed": int(seed),
    }
    for name, value in extra.items():
        if _accepts_kwarg(model.create_chat_completion, name):
            kwargs[name] = value
    if (thinking or "auto").strip().lower() == "off" and _accepts_kwarg(model.create_chat_completion, "reasoning_budget"):
        kwargs["reasoning_budget"] = 0
    if _accepts_cache_prompt(model):
        kwargs["cache_prompt"] = True
    response = model.create_chat_completion(**kwargs)
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned no completion choices.")
    message = choices[0].get("message") or {}
    reasoning = str(message.get("reasoning_content") or "").strip()
    text = str(message.get("content") or "").strip()
    text, tag_thinking = _split_thinking_tags(text)
    thinking = (reasoning + "\n" + tag_thinking).strip() if reasoning or tag_thinking else ""
    if not text:
        raise RuntimeError("LLM returned empty assistant text. Check the LLM log for generation errors.")
    return text, thinking


def unload_llm_models() -> int:
    """Release all loaded LLM models; returns how many were released."""
    count = len(_loaded_models)
    for path, model in list(_loaded_models.items()):
        try:
            model.close()
        except Exception:
            pass
        LOGGER.info("Unloaded LLM model: %s", path)
    _loaded_models.clear()
    return count


def _clear_llm_sessions() -> None:
    _sessions.clear()


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------

class MiniMaxLLMChat:
    """LLM Chat (llama.cpp) – integrated replacement for the external LLM Session Chat node."""

    @classmethod
    def INPUT_TYPES(cls):
        models = list_llm_models()
        if EXAMPLE_MODEL_NAME not in models:
            models.append(EXAMPLE_MODEL_NAME)
        if not models:
            models = [PLACEHOLDER_MODEL]
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": True}),
                "user_text": ("STRING", {"forceInput": True, "multiline": True}),
                "system_prompt": ("STRING", {"forceInput": True, "multiline": True}),
                "session_id": ("STRING", {"forceInput": True}),
                "model": (models, {"default": EXAMPLE_MODEL_NAME if EXAMPLE_MODEL_NAME in models else models[0]}),
                "max_tokens": ("INT", {"default": 16384, "min": 1, "max": 131072, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.01}),
                "n_gpu_layers": ("INT", {"default": -1, "min": -1, "max": 512, "step": 1}),
                "n_ctx": ("INT", {"default": 32768, "min": 512, "max": 262144, "step": 256}),
                "reset_session": ("BOOLEAN", {"default": True}),
                "auto_download": ("BOOLEAN", {"default": True}),
                "chat_format": (["auto", "chatml", "qwen", "gemma", "llama-3", "none"], {"default": "auto"}),
                "thinking": (["auto", "on", "off"], {"default": "off"}),
                "top_k": ("INT", {"default": 40, "min": 1, "max": 1000, "step": 1}),
                "min_p": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "repeat_penalty": ("FLOAT", {"default": 1.1, "min": 0.0, "max": 3.0, "step": 0.01}),
                "presence_penalty": ("FLOAT", {"default": 0.0, "min": -2.0, "max": 2.0, "step": 0.01}),
                "frequency_penalty": ("FLOAT", {"default": 0.0, "min": -2.0, "max": 2.0, "step": 0.01}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647, "step": 1}),
                "split_mode": (["none", "layer", "row"], {"default": "none"}),
                "tensor_split": ("STRING", {"default": "", "multiline": False}),
                "main_gpu": ("INT", {"default": 0, "min": 0, "max": 16, "step": 1}),
                "tensor_parallel": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "status", "thinking")
    FUNCTION = "chat"
    CATEGORY = "MiniMax Music Production Toolkit/llm"

    def chat(
        self,
        enabled,
        user_text,
        system_prompt,
        session_id,
        model,
        max_tokens=16384,
        temperature=0.7,
        top_p=0.8,
        n_gpu_layers=-1,
        n_ctx=32768,
        reset_session=True,
        auto_download=True,
        chat_format="auto",
        thinking="off",
        top_k=40,
        min_p=0.0,
        repeat_penalty=1.1,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        seed=-1,
        split_mode="none",
        tensor_split="",
        main_gpu=0,
        tensor_parallel=False,
    ):
        if not enabled:
            status = "LLM disabled (enabled=False): returning empty text; the parser can fall back to its manual fields."
            LOGGER.info(status)
            return ("", status, "")
        if not (user_text or "").strip():
            raise ValueError("LLM Chat: user_text is empty (is the upstream prompt node bypassed?).")
        if model == PLACEHOLDER_MODEL:
            raise RuntimeError(
                "LLM Chat: no GGUF model was found in models/llm. "
                "Place a llama.cpp-compatible .gguf there or configure a download URL in models_config.json."
            )

        llama_cpp = _import_llama_cpp()
        log_llm_environment_once()
        device_count = _gpu_device_count()
        if device_count > 1:
            LOGGER.info(
                "LLM: %d CUDA GPUs detected - use split_mode (layer/row) and tensor_split "
                "('even' or explicit fractions) to distribute the model.",
                device_count,
            )
        thinking_mode = (thinking or "auto").strip().lower()
        effective_system = _thinking_instruction(thinking_mode) + (system_prompt or "")
        loaded = _get_model(
            model, bool(auto_download), n_gpu_layers, n_ctx,
            chat_format=chat_format, split_mode=split_mode, tensor_split=tensor_split,
            main_gpu=main_gpu, tensor_parallel=bool(tensor_parallel),
        )

        if reset_session:
            state_key = None
        else:
            state_key = str(session_id or "default")
            saved = _sessions.get(state_key)
            if saved is not None:
                try:
                    loaded.set_state(saved)
                except Exception:
                    LOGGER.debug("Could not restore LLM session state", exc_info=True)

        text, thinking_text = _run_chat(
            loaded, effective_system, user_text,
            max_tokens, temperature, top_p, top_k, min_p, repeat_penalty,
            presence_penalty, frequency_penalty, seed, thinking_mode,
        )
        if thinking_mode == "off" and thinking_text:
            LOGGER.warning(
                "LLM emitted reasoning although thinking=off; it was split off and recorded separately."
            )

        if thinking_text:
            LOGGER.info("LLM thinking (%d chars):\n%s", len(thinking_text), thinking_text)
        LOGGER.info("LLM assistant output (%d chars):\n%s", len(text), text)

        if state_key is not None:
            try:
                _sessions[state_key] = loaded.save_state()
            except Exception:
                LOGGER.debug("Could not save LLM session state", exc_info=True)

        status = (
            f"LLM ok: model={model}, session={state_key or 'reset'}, "
            f"chars={len(text)}, thinking_chars={len(thinking_text)}, "
            f"thinking={thinking_mode}, chat_format={chat_format}, "
            f"max_tokens={max_tokens}, n_ctx={n_ctx}"
        )
        LOGGER.info(status)
        return (text, status, thinking_text)


class MiniMaxLLMUnload:
    """Unload LLM Model – integrated replacement for the external unload node."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "trigger": ("*", {"forceInput": True}),
                "unload_now": ("BOOLEAN", {"default": True}),
                "unload_flashsr": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("*", "INT")
    RETURN_NAMES = ("trigger", "released_count")
    FUNCTION = "unload"
    CATEGORY = "MiniMax Music Production Toolkit/llm"

    def unload(self, trigger=None, unload_now=True, unload_flashsr=False):
        released = 0
        if unload_now:
            released += unload_llm_models()
            _clear_llm_sessions()
            if unload_flashsr:
                from .flashsr_audio import clear_flashsr_cache
                released += clear_flashsr_cache()
        LOGGER.info("LLM unload requested: unload_now=%s, released=%d", unload_now, released)
        return (trigger, released)


NODE_CLASS_MAPPINGS = {
    "MiniMaxLLMChat": MiniMaxLLMChat,
    "MiniMaxLLMUnload": MiniMaxLLMUnload,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxLLMChat": "LLM Chat (llama.cpp, integrated)",
    "MiniMaxLLMUnload": "Unload LLM Model (integrated)",
}
