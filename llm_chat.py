"""LLM chat (integrated GGUF or external API) and integrated model unloading.

These replace the external ``ComfyUI-LLM-Session`` nodes used by the example
workflow with a small, self-contained implementation:

- ``MiniMaxLLMChat`` loads a GGUF from ``models/llm`` or delegates to a local
  server/cloud adapter. It returns final text, status and separate reasoning.
  IS_CHANGED makes every enabled queued execution fresh; no session node is
  needed. The old Python session_id argument remains for direct callers.
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

import json
import math
import os
import re
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .comfy_resources import free_comfyui_model_cache
from .llm_providers import MODES, LOCAL, CLOUD, remote_chat
from .llm_sampling import (
    adapter_report,
    build_runtime_options,
    format_adapter_lines,
)
from .model_downloader import (
    check_file_entries,
    config_version_problem,
    load_models_config,
    normalize_model_entries,
    resolve_target,
)
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
# Session snapshots are keyed by session id **plus** the model/context/template
# identity, so a snapshot is never restored into a different model or context.
# Bounded by entry count and by total bytes (see ``_remember_session``); the
# node default (``reset_session=True``) stores no snapshots at all.
_sessions: "OrderedDict[str, bytes]" = OrderedDict()
SESSION_SNAPSHOT_MAX_ENTRIES = 4
SESSION_SNAPSHOT_MAX_BYTES = 512 * 1024 * 1024

# Lock order (documented, never inverted): _MODEL_LOCK -> _SESSIONS_LOCK.
# _MODEL_LOCK serialises loading, state restore, generation, state save, close
# and unload, so no second request can close a model while native inference is
# running.  _SESSIONS_LOCK only guards the snapshot mapping and is never held
# while a model is loading or generating, so the two cannot deadlock.
_MODEL_LOCK = threading.RLock()
_SESSIONS_LOCK = threading.RLock()


def _model_signature(model_path: Path) -> str:
    """File signature used in cache/session keys (name + size + mtime)."""
    try:
        stat = model_path.stat()
        return f"{model_path.name}:{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:  # pragma: no cover - race with a deleted file
        return f"{model_path.name}:missing"


def _close_model(cache_key: str) -> None:
    """Close and forget one cached model; failures are logged, never hidden."""
    model = _loaded_models.pop(cache_key, None)
    if model is None:
        return
    try:
        model.close()
    except Exception as exc:
        LOGGER.warning("Could not close LLM model %s: %s", cache_key, exc)
    LOGGER.info("Unloaded LLM model: %s", cache_key)


def _session_key(session_id: str, model_name: str, n_ctx: int, chat_format: str, signature: str) -> str:
    """Session identity: session id + model signature + context + template."""
    return f"{session_id or 'default'}::{signature}::ctx={int(n_ctx)}::fmt={chat_format or 'auto'}"


def _snapshot_bytes() -> int:
    return sum(len(state) for state in _sessions.values())


def _remember_session(key: str, state: Any) -> None:
    """Store one snapshot inside the count/byte budget, evicting oldest first."""
    if state is None:
        return
    try:
        payload = bytes(state)
    except Exception:
        LOGGER.debug("Session snapshot is not bytes; not cached", exc_info=True)
        return
    with _SESSIONS_LOCK:
        _sessions[key] = payload
        _sessions.move_to_end(key)
        while _sessions and (
            len(_sessions) > SESSION_SNAPSHOT_MAX_ENTRIES or _snapshot_bytes() > SESSION_SNAPSHOT_MAX_BYTES
        ):
            evicted, _ = _sessions.popitem(last=False)
            if evicted == key:
                LOGGER.info("Session snapshot exceeds the snapshot byte budget; not cached.")
                return
            LOGGER.info("Evicted oldest LLM session snapshot: %s", evicted)


def _restore_state(model, state: Any) -> bool:
    """Restore a snapshot through whichever API this build actually provides.

    ``load_state`` is the documented restore call; older builds only expose
    ``set_state``.  Neither is assumed to exist.
    """
    for name in ("load_state", "set_state"):
        method = getattr(model, name, None)
        if callable(method):
            method(state)
            return True
    LOGGER.warning(
        "This llama-cpp-python build exposes neither load_state nor set_state; "
        "session snapshots cannot be restored (generation continues without the history)."
    )
    return False


def _save_state(model) -> Optional[bytes]:
    method = getattr(model, "save_state", None)
    if not callable(method):
        LOGGER.debug("This llama-cpp-python build has no save_state; no snapshot is stored.")
        return None
    return method()


def _processing_interrupted() -> bool:
    """ComfyUI's interrupt flag, when running inside ComfyUI."""
    try:
        import comfy.model_management as model_management  # type: ignore

        checker = getattr(model_management, "processing_interrupted", None)
        return bool(checker()) if callable(checker) else False
    except Exception:
        return False


def _interrupt_exception() -> BaseException:
    """ComfyUI's own interrupt exception when available."""
    try:
        import comfy.model_management as model_management  # type: ignore

        return model_management.InterruptProcessingException()
    except Exception:
        return RuntimeError("LLM generation cancelled by the user.")


def _close_stream(stream) -> None:
    """Close a streaming iterator so the native generator is not left open."""
    close = getattr(stream, "close", None)
    if callable(close):
        try:
            close()
        except Exception as exc:  # pragma: no cover - generator dependent
            LOGGER.debug("Closing the LLM stream failed: %s", exc)



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


def _free_comfyui_model_cache() -> None:
    """Compatibility wrapper around :func:`comfy_resources.free_comfyui_model_cache`."""
    return free_comfyui_model_cache()


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


# ---------------------------------------------------------------------------
# GGUF discovery classification (D01)
#
# A models/llm folder usually also holds projector files (vision/mmproj) and
# multi-part ("split") models.  Offering those as standalone chat models makes
# the combo box lie; a split model belongs in the list exactly once, under its
# first shard, and a missing part must be visible.
# ---------------------------------------------------------------------------
GGUF_PROJECTOR_MARKERS = ("mmproj", "projector", "vision-encoder", "vision_encoder")
GGUF_MTP_MARKERS = ("mtp",)
_GGUF_SHARD_RE = re.compile(r"^(?P<stem>.+?)-(?P<index>\d{5})-of-(?P<total>\d{5})\.gguf$", re.IGNORECASE)
GGUF_STAT_CACHE_MAX = 32
# (size, mtime) cache for the shard scan - metadata only, never weights.
_GGUF_STAT_CACHE: "OrderedDict[str, tuple]" = OrderedDict()


def classify_gguf(name: str) -> str:
    """Classify one file name: ``model``, ``projector``, ``mtp`` or ``shard``."""
    lowered = (name or "").lower()
    if not lowered.endswith(GGUF_SUFFIX):
        return "mtp"
    if any(marker in lowered for marker in GGUF_PROJECTOR_MARKERS):
        return "projector"
    if _GGUF_SHARD_RE.match(name or ""):
        return "shard"
    if any(marker in lowered for marker in GGUF_MTP_MARKERS):
        return "mtp"
    return "model"


def cached_gguf_size(path: Path) -> Optional[int]:
    """File size cached by path + size + mtime.

    The shard scan only stats files; it never opens them, so no weights are
    read and no model is loaded.
    """
    key = str(path)
    try:
        stat = path.stat()
    except OSError:
        return None
    signature = (stat.st_size, stat.st_mtime_ns)
    cached = _GGUF_STAT_CACHE.get(key)
    if cached is not None and cached[0] == signature:
        _GGUF_STAT_CACHE.move_to_end(key)
        return cached[1]
    _GGUF_STAT_CACHE[key] = (signature, stat.st_size)
    _GGUF_STAT_CACHE.move_to_end(key)
    while len(_GGUF_STAT_CACHE) > GGUF_STAT_CACHE_MAX:
        _GGUF_STAT_CACHE.popitem(last=False)
    return stat.st_size


def group_gguf_files(names: List[str]) -> Dict[str, Any]:
    """Group a flat GGUF file list into usable models, projectors and shard sets.

    Returns ``{"models", "projectors", "mtp", "split_models", "incomplete"}``.
    Each ``split_models`` entry names the first shard plus how many parts are
    present of how many are expected, so an incomplete download is visible
    instead of looking like a complete model.
    """
    models: List[str] = []
    projectors: List[str] = []
    mtp: List[str] = []
    shards: Dict[str, List[tuple]] = {}
    for name in names:
        kind = classify_gguf(name)
        if kind == "projector":
            projectors.append(name)
        elif kind == "mtp":
            mtp.append(name)
        elif kind == "shard":
            match = _GGUF_SHARD_RE.match(name)
            assert match is not None
            shards.setdefault(match.group("stem"), []).append(
                (int(match.group("index")), int(match.group("total")), name)
            )
        else:
            models.append(name)

    split_models: List[Dict[str, Any]] = []
    incomplete: List[Dict[str, Any]] = []
    for _stem, parts in shards.items():
        parts.sort(key=lambda item: item[0])
        expected = parts[0][1]
        present = {item[0] for item in parts}
        entry = {
            "name": parts[0][2],
            "files": [item[2] for item in parts],
            "parts_present": len(present),
            "parts_expected": expected,
        }
        missing = [index for index in range(1, expected + 1) if index not in present]
        if missing:
            entry["missing_parts"] = missing
            incomplete.append(entry)
        split_models.append(entry)

    split_models.sort(key=lambda entry: entry["name"].lower())
    return {
        "models": sorted(models, key=str.lower),
        "projectors": sorted(projectors, key=str.lower),
        "mtp": sorted(mtp, key=str.lower),
        "split_models": split_models,
        "incomplete": incomplete,
    }


def list_llm_models() -> List[str]:
    """Chat models available in the ComfyUI models/llm folders.

    Projectors, MTP heads and the trailing parts of split models are not offered
    as standalone chat models; a split model appears once, under its first
    shard.  Manually installed files are kept - they are only classified, never
    renamed or moved.
    """
    names: List[str] = []
    seen = set()
    for directory in _llm_search_directories():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(f"*{GGUF_SUFFIX}")):
            if path.name not in seen:
                seen.add(path.name)
                names.append(path.name)
    grouped = group_gguf_files(names)
    offered = set(grouped["models"]) | {entry["name"] for entry in grouped["split_models"]}
    return [name for name in names if name in offered]


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
    for line in describe_llm_profile():
        LOGGER.info("%s", line)
    if _gpu_device_count() <= 1:
        LOGGER.info(
            "Single-GPU mode: ComfyUI models and the LLM share one GPU. "
            "Before the LLM loads, all ComfyUI model VRAM (incl. dynamic staging) "
            "is released and re-staged afterwards - repeated runs are supported. "
            "If this machine has a second GPU, start ComfyUI with '--cuda-device all' "
            "(Windows hides extra GPUs otherwise); the LLM is then auto-routed to its own GPU."
        )


def _catalog_llm_directories() -> List[Path]:
    """Directories the model catalog points at for LLM artifacts.

    The check node, the downloader and the loader must agree on where an LLM
    file lives, so the catalog's resolved targets are part of the search path
    instead of being a second, separate truth.  A broken catalog config is
    reported and then ignored - the folder scan still works.
    """
    try:
        config = load_models_config()
        problem = config_version_problem(config)
        if problem:
            LOGGER.warning("%s", problem)
            return []
        entries = normalize_model_entries(config, minimax=False, flux2=False, flashsr=False)
    except Exception as exc:
        LOGGER.debug("Model catalog could not be read for the LLM search path: %s", exc)
        return []
    directories: List[Path] = []
    for entry in entries:
        target = entry.get("target")
        if not target:
            continue
        try:
            path = resolve_target(str(target))
        except Exception:  # pragma: no cover - defensive
            continue
        if path not in directories:
            directories.append(path)
    return directories


def _llm_search_directories() -> List[Path]:
    """Folder scan plus the catalog targets, in that order (deduplicated)."""
    directories = list(_llm_directories())
    for directory in _catalog_llm_directories():
        if directory not in directories:
            directories.append(directory)
    return directories


def describe_llm_profile() -> List[str]:
    """Recommended model class for this machine (L01) - advisory and read-only.

    Logged once with the LLM environment and available for the UI; it never
    changes a generation setting and never downloads anything.  A missing or
    unreadable resource reading is reported as such instead of raising.
    """
    try:
        from . import llm_profiles

        names, sizes = llm_profiles.installed_llm_files()
        recommendation = llm_profiles.recommend_llm_setup(installed=names, sizes_by_name=sizes)
        return llm_profiles.format_llm_profile_lines(recommendation)
    except Exception as exc:  # pragma: no cover - advisory path must never break a run
        LOGGER.debug("LLM profile recommendation unavailable: %s: %s", type(exc).__name__, exc)
        return ["LLM profile: not available (" + f"{type(exc).__name__})"]


def _find_model_path(name: str) -> Optional[Path]:
    for directory in _llm_search_directories():
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


def _pick_llm_main_gpu(
    main_gpu: int,
    model_path: Path,
    n_ctx: int,
    device_count: int,
    split_mode: int,
    split: Optional[List[float]],
) -> int:
    """Choose the GPU that should hold the LLM.

    The user's explicit choice always wins (``main_gpu != 0`` or any split
    configuration).  With the default ``main_gpu=0``, ``split_mode=none`` and
    no ``tensor_split``, a multi-GPU machine routes the model to the
    non-default GPU with the most free VRAM.

    Rationale: ComfyUI keeps its own models (MiniMax, FLUX, ...) on the
    default CUDA device and its dynamic-VRAM staging buffers may not be
    released by ``unload_all_models()``.  Loading the GGUF onto the same card
    overflows a 16GB GPU on repeated runs (observed: hang in the llama.cpp
    load and a later ``cudaErrorStreamCaptureInvalidated`` during the MiniMax
    CUDA graph capture).  A second GPU solves this cleanly; ComfyUI models
    never touch it.
    """
    if main_gpu != 0 or split_mode != 0 or split:
        return int(main_gpu)
    if device_count < 2:
        return 0
    try:
        import torch  # type: ignore

        current = int(torch.cuda.current_device()) if torch.cuda.is_available() else 0
        free: Dict[int, int] = {}
        for index in range(device_count):
            try:
                free_bytes, _total = torch.cuda.mem_get_info(index)
                free[index] = int(free_bytes)
            except Exception:
                free[index] = -1
        others = [index for index in range(device_count) if index != current]
        if not others:
            return 0
        best = max(others, key=lambda index: free.get(index, -1))
        try:
            model_bytes = model_path.stat().st_size
        except OSError:
            model_bytes = 0
        if model_bytes and free.get(best, -1) >= 0 and free[best] < model_bytes * 1.2 + (2 << 30):
            LOGGER.warning(
                "Auto-routed the LLM to GPU %d but it may not have enough VRAM "
                "(%.1f GiB free, model file %.1f GiB). Set main_gpu explicitly if the load fails.",
                best,
                free[best] / (2**30),
                model_bytes / (2**30),
            )
        LOGGER.info(
            "Routing LLM to GPU %d (ComfyUI models stay on GPU %d; set main_gpu to override).",
            best,
            current,
        )
        return best
    except Exception:
        return 0


def _configured_runtime_options() -> Dict[str, Any]:
    """Optional runtime parameters from the model catalog (opt-in, no widget).

    Reading them from ``models_config.json`` keeps the node's widget list - and
    therefore every saved workflow - untouched while still letting a user ask
    for ``n_ubatch``, ``flash_attn`` or a KV type explicitly.
    """
    try:
        llm_section = load_models_config().get("llm", {}) or {}
        options = llm_section.get("runtime_options")
        return dict(options) if isinstance(options, dict) else {}
    except Exception:  # pragma: no cover - defensive
        return {}


def _get_model(
    model_name: str,
    auto_download: bool,
    n_gpu_layers: int = -1,
    n_ctx: int = 37376,
    chat_format: str = "auto",
    split_mode: str = "layer",
    tensor_split: str = "",
    main_gpu: int = 0,
    tensor_parallel: bool = False,
    runtime_options: Optional[Dict[str, Any]] = None,
):
    """Return a loaded Llama instance for ``model_name``, loading it if needed.

    Model lifetimes are serialised by :data:`_MODEL_LOCK`.  A model switch
    closes the no-longer-active model *before* the new one is constructed, so
    the two never hold VRAM at the same time and a failed load cannot leave a
    stale entry behind.  The cache key carries the checkpoint's file signature,
    so replacing a GGUF on disk invalidates the cached instance instead of
    silently reusing the old one.
    """
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
    options["main_gpu"] = _pick_llm_main_gpu(
        int(main_gpu), model_path, options["n_ctx"], device_count, options["split_mode"], split
    )
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

    # Optional runtime parameters are only passed when this build declares them,
    # and they are part of ``options`` - so they are part of the cache key below:
    # two runtime configurations are two different model instances.
    requested_runtime = runtime_options if runtime_options is not None else _configured_runtime_options()
    runtime = build_runtime_options(
        requested_runtime, lambda name: _accepts_kwarg(llama_cpp.Llama.__init__, name)
    )
    if runtime["options"]:
        LOGGER.info(
            "LLM runtime options: %s", ", ".join(f"{k}={v}" for k, v in sorted(runtime["options"].items()))
        )
    for name, problem in sorted(runtime["unsupported"].items()):
        LOGGER.warning("Ignoring LLM runtime option %s: %s", name, problem)
    options.update(runtime["options"])

    cache_key = f"{model_path}|{_model_signature(model_path)}|" + "|".join(
        f"{key}={value}" for key, value in sorted(options.items())
    )
    with _MODEL_LOCK:
        cached = _loaded_models.get(cache_key)
        if cached is not None:
            return cached

        LOGGER.info(
            "Loading LLM model: %s (n_ctx=%d, n_gpu_layers=%d, chat_format=%s, split_mode=%s, main_gpu=%d, gpus=%d)",
            model_path, options["n_ctx"], options["n_gpu_layers"],
            options.get("chat_format", "none"), options["split_mode"], options["main_gpu"], device_count,
        )
        # Close the previous model first: keeping it as a "rollback" would mean two
        # models resident at once, which is exactly the peak this loop must avoid.
        for other_key in [key for key in _loaded_models if key != cache_key]:
            _close_model(other_key)
        # verbose=False keeps llama.cpp's per-token debug output out of the log;
        # the chat format makes Qwen-style models emit their reasoning as <think>
        # tags so it can be split off from the real answer.
        _free_comfyui_model_cache()
        try:
            model = llama_cpp.Llama(model_path=str(model_path), verbose=False, **options)
        except Exception as exc:
            # Do not declare one cause ("VRAM") for every failure: report the
            # settings, the likely causes and the real error instead.
            raise RuntimeError(
                f"Failed to load LLM model '{model_path.name}' into llama.cpp "
                f"(n_gpu_layers={options['n_gpu_layers']}, n_ctx={options['n_ctx']}, "
                f"main_gpu={options['main_gpu']}, split_mode={options['split_mode']}). "
                "Possible causes: not enough free memory for these settings (reduce n_ctx, "
                "set n_gpu_layers to a positive number to keep part of the model on CPU, "
                "pick another main_gpu), an incompatible or damaged GGUF file, or a "
                "llama-cpp-python build that does not support this backend. "
                f"The previous model was already released. Underlying error: {type(exc).__name__}: {exc}"
            ) from exc
        _loaded_models[cache_key] = model
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


def _usage_from_response(response: Any, chunks: Optional[int] = None) -> Dict[str, Any]:
    """Token statistics from the backend's own usage report, when it has one.

    A streaming chunk is not a token, so a chunk count is reported *as* a chunk
    count (``source='chunks'``) instead of being presented as an exact token
    count.  Missing values stay ``None`` rather than becoming 0.
    """
    usage = (response or {}).get("usage") or {}
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    if prompt is not None or completion is not None:
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "source": "backend",
            "chunks": chunks,
        }
    return {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "source": "chunks" if chunks is not None else "unknown",
        "chunks": chunks,
    }


def _empty_answer_message(thinking: str) -> str:
    """Explain an empty answer, and say so when it was all reasoning."""
    base = "LLM returned empty assistant text. Check the LLM log for generation errors."
    if not thinking:
        return base
    return (
        base + " The model produced reasoning but no answer text - raise max_tokens, or use a build/family "
        "that can really switch thinking off (see the family line in the log)."
    )


def _run_chat(
    model,
    system_prompt: str,
    user_text: str,
    max_tokens: int = 24576,
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
    if _accepts_kwarg(model.create_chat_completion, "stream"):
        return _run_chat_streamed(model, kwargs, int(max_tokens))
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
        raise RuntimeError(_empty_answer_message(thinking))
    return text, thinking, _usage_from_response(response)


def _run_chat_streamed(model, kwargs: dict, max_tokens: int) -> tuple:
    """Run one chat turn with token streaming (progress bar in node and log).

    Streaming makes the generation visible: the node's progress bar advances
    with every generated token (content + reasoning) up to ``max_tokens``,
    and the log shows a single ASCII progress bar (0 on the left, max_tokens
    on the right) that updates every ~10% instead of one log line per step.
    The collected text is split exactly like the non-streaming path, so
    behaviour is identical otherwise.
    """
    from .progress_utils import format_progress_bar, make_progress_bar

    kwargs = dict(kwargs)
    kwargs.pop("cache_prompt", None)  # prompt caching and streaming are not combined
    kwargs["stream"] = True
    LOGGER.info("LLM streaming generation started (max_tokens=%d) ...", max_tokens)
    stream = model.create_chat_completion(**kwargs)
    text_parts: List[str] = []
    reasoning_parts: List[str] = []
    total_tokens = 0
    usage_payload = None
    log_every = max(64, max_tokens // 10)
    pbar = make_progress_bar(max_tokens)
    try:
        for chunk in stream:
            if _processing_interrupted():
                # ComfyUI's cancel button must stop generation between chunks
                # instead of running to max_tokens first.
                LOGGER.info("LLM generation cancelled by the user after %d chunk(s).", total_tokens)
                raise _interrupt_exception()
            if chunk.get("usage"):
                # Some builds report the authoritative usage on the last chunk.
                usage_payload = chunk
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = str(delta.get("content") or "")
            reasoning = str(delta.get("reasoning_content") or "")
            if content:
                text_parts.append(content)
            if reasoning:
                reasoning_parts.append(reasoning)
            total_tokens += 1
            pbar.update_absolute(min(total_tokens, max_tokens))
            if total_tokens % log_every == 0 or total_tokens >= max_tokens:
                LOGGER.info("LLM progress %s", format_progress_bar(total_tokens, max_tokens))
    finally:
        # The native generator is closed on every path - completion, error and
        # cancellation - so a request is never left open in llama.cpp.
        _close_stream(stream)
    LOGGER.info("LLM progress %s", format_progress_bar(total_tokens, max_tokens))
    # A streaming chunk is not guaranteed to be one token, so report the chunk
    # count together with the token budget instead of claiming exact tokens.
    LOGGER.info(
        "LLM streaming finished: %d stream chunk(s) (token budget %d).", total_tokens, max_tokens
    )
    reasoning = "".join(reasoning_parts).strip()
    text = "".join(text_parts).strip()
    text, tag_thinking = _split_thinking_tags(text)
    thinking = (reasoning + "\n" + tag_thinking).strip() if reasoning or tag_thinking else ""
    if not text:
        raise RuntimeError(_empty_answer_message(thinking))
    return text, thinking, _usage_from_response(usage_payload, chunks=total_tokens)


def unload_llm_models() -> int:
    """Release all loaded LLM models; returns how many were released.

    Serialised by :data:`_MODEL_LOCK`, so it can never close a model while
    another request is generating with it (``close()`` during native inference
    is the failure mode this lock exists to prevent).
    """
    with _MODEL_LOCK:
        return _unload_llm_models_locked()


def _unload_llm_models_locked() -> int:
    """Release all loaded LLM models. The caller must hold :data:`_MODEL_LOCK`."""
    count = len(_loaded_models)
    for path in list(_loaded_models):
        _close_model(path)
    if count:
        # Return the freed GPU memory to the allocator pools so the music
        # stage (MiniMax TE, DAV, FLUX) can claim it without fragmentation.
        try:
            import gc
            gc.collect()
        except Exception:
            pass
        try:
            import torch  # type: ignore
            torch.cuda.empty_cache()
        except Exception:
            pass
        try:
            import comfy.model_management as model_management  # type: ignore
            soft_empty = getattr(model_management, "soft_empty_cache", None)
            if soft_empty is not None:
                soft_empty()
        except Exception:
            pass
    return count


def _clear_llm_sessions() -> None:
    with _SESSIONS_LOCK:
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
                "model": (models, {"default": EXAMPLE_MODEL_NAME if EXAMPLE_MODEL_NAME in models else models[0]}),
                "max_tokens": ("INT", {"default": 24576, "min": 1, "max": 131072, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.01}),
                "n_gpu_layers": ("INT", {"default": -1, "min": -1, "max": 512, "step": 1}),
                "n_ctx": ("INT", {"default": 37376, "min": 512, "max": 262144, "step": 256}),
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
            },
            "optional": {
                "backend": (MODES, {"default": MODES[0], "tooltip": "Where the language model runs: inside ComfyUI, in another local app, or at a cloud provider."}),
                "local_provider": (list(LOCAL), {"default": "LM Studio", "tooltip": "Start the app's API server and load a text chat model there."}),
                "cloud_provider": (list(CLOUD), {"default": "OpenAI", "tooltip": "Cloud sends your user and system prompts to this provider and may incur API charges."}),
                "server_url": ("STRING", {"default": "", "tooltip": "API base address including /v1. Leave empty for the selected provider's default. Qwen: paste your regional workspace API base."}),
                "remote_model": ("STRING", {"default": "", "tooltip": "Exact server model ID. Use Find models to select one, or copy it from the provider/app."}),
                "api_key_env": ("STRING", {"default": "", "tooltip": "Optional environment variable NAME containing the key. Leave empty to use the provider's standard variable or Set API key."}),
                "credential_id": ("STRING", {"default": "", "tooltip": "Internal reference to a session key entered via Set API key. Contains no provider secret. Expires when ComfyUI restarts."}),
                "remote_max_tokens": ("INT", {"default": 4096, "min": 1, "max": 131072, "tooltip": "Output token budget, including reasoning where the provider counts it. Increase if output is truncated; model-specific limits apply."}),
                "request_timeout": ("INT", {"default": 120, "min": 5, "max": 600, "tooltip": "Network timeout in seconds. Slow local models may need more time. Failed requests are never retried automatically."}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "status", "thinking")
    FUNCTION = "chat"
    CATEGORY = "Music Production Toolkit/llm"

    @classmethod
    def IS_CHANGED(cls, enabled=True, **kwargs):
        # Comfy compares successive values; NaN != NaN forces a fresh response
        # on every queued execution without an auxiliary seed/session node.
        return float("nan") if enabled else "disabled"

    @classmethod
    def VALIDATE_INPUTS(cls, model=None, backend=MODES[0], enabled=True):
        # A remembered GGUF filename may not exist on a machine using a server.
        # Validate only these named fields; Comfy keeps validating the others.
        if backend not in MODES:
            return "Select a supported LLM backend."
        if not isinstance(enabled, bool):
            return "LLM enabled must be a BOOLEAN."
        if not enabled or backend != MODES[0] or model is None:
            return True
        if model not in cls.INPUT_TYPES()["required"]["model"][0]:
            return "Select an available GGUF model, or choose Local app / server or Cloud service."
        return True

    def chat(
        self,
        enabled,
        user_text,
        system_prompt,
        session_id="",  # retained for direct Python callers of the old signature
        model=EXAMPLE_MODEL_NAME,
        max_tokens=24576,
        temperature=0.7,
        top_p=0.8,
        n_gpu_layers=-1,
        n_ctx=37376,
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
        backend=MODES[0],
        local_provider="LM Studio",
        cloud_provider="OpenAI",
        server_url="",
        remote_model="",
        api_key_env="",
        credential_id="",
        remote_max_tokens=4096,
        request_timeout=120,
    ):
        if not enabled:
            status = "LLM disabled (enabled=False): returning empty text; the parser can fall back to its manual fields."
            LOGGER.info(status)
            return ("", status, "")
        if not (user_text or "").strip():
            raise ValueError("LLM Chat: user_text is empty (is the upstream prompt node bypassed?).")
        if backend not in MODES:
            raise ValueError("LLM Chat: select a supported backend.")
        if backend != MODES[0]:
            if _processing_interrupted():
                raise _interrupt_exception()
            text, status, remote_thinking = remote_chat(
                backend=backend, user_text=user_text, system_prompt=system_prompt,
                local_provider=local_provider, cloud_provider=cloud_provider,
                server_url=server_url, remote_model=remote_model, api_key_env=api_key_env,
                credential_id=credential_id, remote_max_tokens=remote_max_tokens,
                request_timeout=request_timeout,
            )
            if _processing_interrupted():
                raise _interrupt_exception()
            text, tag_thinking = _split_thinking_tags(text)
            if not text.strip():
                raise RuntimeError("LLM returned reasoning only. Increase Output token limit or choose another model.")
            return text, status, "\n\n".join(p for p in (remote_thinking, tag_thinking) if p)
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

        # Which family is this, and can this build actually switch its thinking
        # off?  Reported, not assumed: removing reasoning afterwards is not a
        # speedup, and the log must not imply one.
        family = adapter_report(model, lambda name: _accepts_kwarg(loaded.create_chat_completion, name))
        for line in format_adapter_lines(family):
            LOGGER.info("%s", line)

        if reset_session:
            state_key = None
        else:
            # The snapshot key carries the model signature, context and template
            # identity, so a snapshot is never restored into a different model or
            # context (which would silently reuse an incompatible KV state).
            resolved = getattr(loaded, "model_path", None)
            signature = _model_signature(Path(resolved)) if resolved else "unknown"
            state_key = _session_key(str(session_id or "default"), model, n_ctx, chat_format, signature)

        # One lock acquisition covers restore, generation and state save: a
        # concurrent request may neither switch the model nor unload it while
        # this turn is running.
        with _MODEL_LOCK:
            if state_key is not None:
                with _SESSIONS_LOCK:
                    saved = _sessions.get(state_key)
                if saved is not None:
                    try:
                        _restore_state(loaded, saved)
                    except Exception:
                        LOGGER.debug("Could not restore LLM session state", exc_info=True)

            text, thinking_text, usage = _run_chat(
                loaded, effective_system, user_text,
                max_tokens, temperature, top_p, top_k, min_p, repeat_penalty,
                presence_penalty, frequency_penalty, seed, thinking_mode,
            )
            if thinking_mode == "off" and thinking_text:
                LOGGER.warning(
                    "LLM emitted reasoning although thinking=off; it was split off and recorded separately%s.",
                    ""
                    if (family.get("thinking") or {}).get("supported")
                    else " - note that this build cannot switch thinking off",
                )
            LOGGER.info(
                "LLM token statistics: %s",
                json.dumps(usage, ensure_ascii=False),
            )

            if thinking_text:
                LOGGER.info("LLM thinking (%d chars):\n%s", len(thinking_text), thinking_text)
            LOGGER.info("LLM assistant output (%d chars):\n%s", len(text), text)

            if state_key is not None:
                try:
                    _remember_session(state_key, _save_state(loaded))
                except Exception:
                    LOGGER.debug("Could not save LLM session state", exc_info=True)

        status = (
            f"LLM ok: model={model}, session={state_key or 'reset'}, "
            f"chars={len(text)}, thinking_chars={len(thinking_text)}, "
            f"thinking={thinking_mode} "
            f"({'generation-controlled' if (family.get('thinking') or {}).get('supported') else 'output-split-only'}), "
            f"tokens={usage.get('completion_tokens') if usage.get('completion_tokens') is not None else usage.get('chunks')} "
            f"({usage.get('source')}), chat_format={chat_format}, "
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
    CATEGORY = "Music Production Toolkit/llm"

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
    "MiniMaxLLMChat": "LLM Chat – ComfyUI / Local / Cloud",
    "MiniMaxLLMUnload": "Unload LLM Model (integrated)",
}
