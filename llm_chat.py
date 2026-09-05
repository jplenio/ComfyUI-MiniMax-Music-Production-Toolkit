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


def _free_comfyui_model_cache() -> None:
    """Free ALL ComfyUI-managed GPU memory before allocating a llama.cpp model.

    llama.cpp allocates CUDA memory outside PyTorch, so ComfyUI's memory
    manager does not see those allocations and will not evict its own cached
    models when the GGUF is loaded.  On a repeated run the MiniMax / FLUX
    models of the previous run are still resident in VRAM; loading the LLM
    on top overflows the GPU, which makes llama.cpp spill to CPU (generation
    takes \"forever\") and leaves the CUDA context broken so the later
    MiniMax CUDA graph capture fails with ``cudaErrorStreamCaptureInvalidated``.

    ``unload_all_models()`` alone is NOT enough on dynamic-VRAM builds
    (aimdo): their staged weight pages live in a VBAR and are only released
    through ``ModelPatcher.partially_unload()`` -> ``vbar.free_memory()``,
    the cast buffers (``VRAMBuffer`` / torch cast tensors) that grow
    while weights stream are only destroyed by ``reset_cast_buffers()``,
    and the MiniMax CUDA-graph/prefetch workspaces only by
    ``cleanup_prefetch_queues()`` (ComfyUI itself never calls the last
    two).  All of these are invisible to the torch allocator and survive
    ``free_memory()``.  They are released explicitly here; the models
    re-stage on demand later in the pipeline (dynamic VRAM loading), so
    nothing is lost - this keeps a SINGLE-GPU machine working run after run.
    A short diagnostic (aimdo usage + free VRAM per GPU) is logged at the
    end so any remaining residency is visible instead of a mysterious hang.

    Outside ComfyUI (unit tests) this is a no-op.
    """
    try:
        import comfy.model_management as model_management  # type: ignore
    except Exception:
        return

    # FlashSR runners cache torch models on the GPU outside ComfyUI's
    # management; release them too so a previous run cannot squeeze the LLM.
    try:
        from .flashsr_audio import clear_flashsr_cache as _clear_flashsr
        _clear_flashsr()
    except Exception:
        pass

    # Collect dynamic (staged) models BEFORE unload_all_models(): unload
    # detaches them and drops them from current_loaded_models, but their
    # VBAR staging pages stay resident - we must release them afterwards.
    dynamic_models = []
    try:
        for entry in list(getattr(model_management, "current_loaded_models", None) or []):
            model = getattr(entry, "model", None)
            if model is None:  # weakref already dead
                continue
            try:
                if callable(getattr(model, "is_dynamic", None)) and model.is_dynamic():
                    dynamic_models.append(model)
            except Exception as exc:
                LOGGER.debug("Could not inspect model dynamism before freeing cache: %s", exc)
    except Exception as exc:
        LOGGER.debug("Could not collect dynamic models before freeing cache: %s", exc)

    # Diagnostic: list what is actually resident, so a leftover residency
    # can be attributed to its model instead of guessed at.
    try:
        for entry in list(getattr(model_management, "current_loaded_models", None) or []):
            model = getattr(entry, "model", None)
            if model is None:
                continue
            try:
                LOGGER.info(
                    "Model resident before LLM cleanup: %s (dynamic=%s, loaded=%.2f GB)",
                    type(getattr(model, "model", model)).__name__,
                    bool(model.is_dynamic()),
                    float(getattr(model, "loaded_size", lambda: 0.0)() or 0) / (2**30),
                )
            except Exception as exc:
                LOGGER.debug("Could not describe resident model: %s", exc)
    except Exception as exc:
        LOGGER.debug("Could not list resident models: %s", exc)

    # CUDA-graph / prefetch pools of the music models (model_prefetch.py)
    # hold their workspace in VRAM after a run; ComfyUI never calls
    # cleanup_prefetch_queues() itself, so the graphs stay resident.
    # Release them first: the graphs reference the staged pages below.
    try:
        from comfy import model_prefetch as _model_prefetch  # type: ignore
        cleanup_prefetch = getattr(_model_prefetch, "cleanup_prefetch_queues", None)
        if cleanup_prefetch is None:
            LOGGER.debug("comfy.model_prefetch has no cleanup_prefetch_queues(); skipping prefetch free.")
        else:
            cleanup_prefetch()
            LOGGER.info("Released ComfyUI prefetch queues / CUDA graphs before LLM load.")
    except Exception as exc:
        LOGGER.debug("Could not clean ComfyUI prefetch queues: %s", exc)

    # Cast buffers (aimdo VRAMBuffer + torch cast tensors) grow while the
    # music models stream weights and are NEVER released by
    # unload_all_models() or partially_unload() - they stay resident for the
    # whole process (observed: ~5 GB left on the GPU after a run, which then
    # overflows the card when the GGUF loads).  reset_cast_buffers() is the
    # only path that destroys them; it also clears cross-step state and
    # dirty mmaps.  Called BEFORE unload_all_models() so it can still reset
    # the pin state of the loaded dynamic models.
    try:
        reset = getattr(model_management, "reset_cast_buffers", None)
        if reset is None:
            LOGGER.debug("comfy.model_management has no reset_cast_buffers(); skipping cast buffer free.")
        else:
            reset()
            LOGGER.info("Released ComfyUI cast buffers before LLM load.")
    except Exception as exc:
        LOGGER.debug("Could not reset ComfyUI cast buffers: %s", exc)

    try:
        unload = getattr(model_management, "unload_all_models", None)
        if unload is None:
            unload = getattr(model_management, "unload_all", None)
        if unload is None:
            LOGGER.debug("comfy.model_management has no unload_all_models(); skipping cache free.")
        else:
            unload()
            LOGGER.info("Freed ComfyUI model cache before LLM load.")
    except Exception as exc:
        LOGGER.debug("Could not free ComfyUI model cache before LLM load: %s", exc)

    released_staging = 0
    for model in dynamic_models:
        try:
            offload = getattr(model, "offload_device", None)
            if offload is None:
                import torch as _torch  # type: ignore
                offload = _torch.device("cpu")
            freed = model.partially_unload(offload, 1e32)
            released_staging += int(freed or 0)
            name = type(getattr(model, "model", model)).__name__
            if freed:
                LOGGER.info(
                    "Released dynamic VRAM staging for %s: %.2f GB",
                    name,
                    freed / (2**30),
                )
            else:
                LOGGER.warning(
                    "partially_unload freed nothing for %s (loaded_size=%.2f GB).",
                    name,
                    float(getattr(model, "loaded_size", lambda: 0.0)() or 0) / (2**30),
                )
        except Exception as exc:
            LOGGER.warning("Could not release dynamic VRAM staging: %s", exc)
    if released_staging:
        LOGGER.info("Total dynamic VRAM staging released before LLM load: %.2f GB", released_staging / (2**30))
    elif dynamic_models:
        LOGGER.warning("No dynamic VRAM staging could be released before LLM load.")

    try:
        import torch  # type: ignore
        torch.cuda.empty_cache()
        soft_empty = getattr(model_management, "soft_empty_cache", None)
        if soft_empty is not None:
            try:
                soft_empty(force=True)
            except TypeError:
                soft_empty()
    except Exception:
        pass

    # Diagnostic: report what still holds GPU memory after the cleanup, so a
    # remaining residency is visible in the log instead of a mysterious hang.
    aimdo_usage = 0
    try:
        import comfy_aimdo.control as _aimdo  # type: ignore
        aimdo_usage = _aimdo.get_total_vram_usage()
        if aimdo_usage:
            LOGGER.info("Aimdo VRAM usage after cleanup: %.2f GB", aimdo_usage / (2**30))
    except Exception:
        pass
    try:
        import torch as _torch  # type: ignore
        for index in range(_torch.cuda.device_count()):
            free_bytes, total_bytes = _torch.cuda.mem_get_info(index)
            LOGGER.info(
                "GPU %d after cleanup: %.2f GB free of %.2f GB",
                index,
                free_bytes / (2**30),
                total_bytes / (2**30),
            )
    except Exception:
        pass
    # If aimdo still holds a meaningful amount, find the live VBARs, name
    # their owner models, and force-release their pages directly.  The pages
    # re-fault on demand the next time the model runs, so this is safe.
    if aimdo_usage > 200 * (2**20):
        try:
            import gc as _gc
            import torch as _torch_mod  # type: ignore
            for vbar in [obj for obj in _gc.get_objects() if type(obj).__name__ == "ModelVBAR"]:
                owner = None
                try:
                    for ref in _gc.get_referrers(vbar):
                        if isinstance(ref, dict):
                            for holder in _gc.get_referrers(ref):
                                if isinstance(holder, _torch_mod.nn.Module):
                                    owner = type(holder).__name__
                                    break
                        if owner:
                            break
                except Exception:
                    pass
                try:
                    deprioritize = getattr(vbar, "deprioritize", None)
                    if deprioritize is not None:
                        deprioritize()
                    freed = vbar.free_memory(1e32)
                except Exception as exc:
                    freed = 0
                    LOGGER.warning("Could not force-release orphan VBAR: %s", exc)
                LOGGER.warning(
                    "Live aimdo VBAR after cleanup: owner=%s device=%s loaded=%.2f GB watermark=%.2f GB force_freed=%.2f GB",
                    owner or "unknown",
                    getattr(vbar, "device", "?"),
                    float(getattr(vbar, "loaded_size", lambda: 0)() or 0) / (2**30),
                    float(getattr(vbar, "get_watermark", lambda: 0)() or 0) / (2**30),
                    freed / (2**30),
                )
        except Exception:
            pass
        try:
            import comfy_aimdo.control as _aimdo2  # type: ignore
            LOGGER.info("Aimdo VRAM usage after force release: %.2f GB", _aimdo2.get_total_vram_usage() / (2**30))
        except Exception:
            pass


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
    if _gpu_device_count() <= 1:
        LOGGER.info(
            "Single-GPU mode: ComfyUI models and the LLM share one GPU. "
            "Before the LLM loads, all ComfyUI model VRAM (incl. dynamic staging) "
            "is released and re-staged afterwards - repeated runs are supported. "
            "If this machine has a second GPU, start ComfyUI with '--cuda-device all' "
            "(Windows hides extra GPUs otherwise); the LLM is then auto-routed to its own GPU."
        )


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

    cache_key = f"{model_path}|" + "|".join(f"{key}={value}" for key, value in sorted(options.items()))
    cached = _loaded_models.get(cache_key)
    if cached is not None:
        return cached

    LOGGER.info(
        "Loading LLM model: %s (n_ctx=%d, n_gpu_layers=%d, chat_format=%s, split_mode=%s, main_gpu=%d, gpus=%d)",
        model_path, options["n_ctx"], options["n_gpu_layers"],
        options.get("chat_format", "none"), options["split_mode"], options["main_gpu"], device_count,
    )
    # verbose=False keeps llama.cpp's per-token debug output out of the log;
    # the chat format makes Qwen-style models emit their reasoning as <think>
    # tags so it can be split off from the real answer.
    _free_comfyui_model_cache()
    try:
        model = llama_cpp.Llama(model_path=str(model_path), verbose=False, **options)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load LLM model '{model_path.name}' into llama.cpp "
            f"(n_gpu_layers={options['n_gpu_layers']}, n_ctx={options['n_ctx']}, main_gpu={options['main_gpu']}). "
            "If this happens on a repeated run, VRAM was likely exhausted by models "
            "cached from the previous run; restart ComfyUI or free the cache first. "
            "Otherwise reduce n_ctx or set n_gpu_layers to a positive number to keep "
            "part of the model on CPU. Underlying error: {type(exc).__name__}: {exc}"
        ) from exc
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
        raise RuntimeError("LLM returned empty assistant text. Check the LLM log for generation errors.")
    return text, thinking


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
    log_every = max(64, max_tokens // 10)
    pbar = make_progress_bar(max_tokens)
    for chunk in stream:
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
    LOGGER.info("LLM progress %s", format_progress_bar(total_tokens, max_tokens))
    LOGGER.info("LLM streaming finished: %d tokens.", total_tokens)
    reasoning = "".join(reasoning_parts).strip()
    text = "".join(text_parts).strip()
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
