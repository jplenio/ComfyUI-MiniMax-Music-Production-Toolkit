"""ComfyUI host-resource cleanup (F10 / T19).

Moved verbatim out of ``llm_chat`` so the LLM runtime is not also the owner of
ComfyUI's private memory APIs, and so the cleanup can be reasoned about and
tested on its own.  Only the logger name changed (``comfy_resources`` instead of
``llm``); the call order, the capability guards, the diagnostics and the
force-release fallback are unchanged.

Ordering is a contract, not an implementation detail:

1. release the FlashSR runner cache (torch models outside ComfyUI management),
2. collect dynamic (staged) models *before* they are detached,
3. release the CUDA-graph/prefetch workspaces (they reference staged pages),
4. reset the aimdo/torch cast buffers,
5. ``unload_all_models()``,
6. ``partially_unload()`` on the collected dynamic models (the only path that
   reaches ``vbar.free_memory()``),
7. ``torch.cuda.empty_cache()`` + ``soft_empty_cache(force=True)``,
8. diagnostics, then the guarded ``ModelVBAR`` force-release fallback.
"""
from __future__ import annotations

from .toolkit_logging import get_logger

LOGGER = get_logger("comfy_resources")


def free_comfyui_model_cache() -> None:
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
