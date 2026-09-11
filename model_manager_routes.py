"""Model-manager HTTP routes: the deliberately triggered setup action (D04).

ComfyUI can reject a workflow whose combo models are missing *before* any node
runs, and an extra wire in the graph does not change that - so establishing the
model inventory is offered as its own explicit action instead of a side effect
of generation:

* ``GET  /minimax_music_toolkit/model_preflight`` - inventory, size and space
  report; it never transfers anything.
* ``POST /minimax_music_toolkit/model_preflight`` - the same report with the
  download explicitly requested (``{"download": true}``).

Both run their blocking work (stat, hash, transfer) in a worker thread, so a
multi-GB download cannot stall ComfyUI's event loop.  Nothing here runs at
import time, and the same functions back the ``MiniMaxModelAutodownload`` node
and the scripts.
"""
from __future__ import annotations

import asyncio

from .model_downloader import (
    format_preflight_report,
    load_models_config,
    normalize_model_entries,
    preflight_models,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("model_manager")

PREFLIGHT_PATH = "/minimax_music_toolkit/model_preflight"
GROUP_FLAGS = ("minimax", "flux2", "flashsr", "llm")
_ROUTES_REGISTERED = False


def selected_entries(flags: dict):
    """Catalog entries for the selected groups (optional artifacts excluded)."""
    return normalize_model_entries(
        load_models_config(),
        minimax=bool(flags.get("minimax", True)),
        flux2=bool(flags.get("flux2", True)),
        flashsr=bool(flags.get("flashsr", True)),
        llm=bool(flags.get("llm", True)),
    )


def build_preflight(flags: dict, auto_download: bool) -> dict:
    """The report the routes and the node both serve."""
    return preflight_models(selected_entries(flags), base_path=None, auto_download=bool(auto_download))


def _parse_flags(source) -> dict:
    flags = {}
    for name in GROUP_FLAGS:
        value = source.get(name, True)
        if isinstance(value, str):
            flags[name] = value.strip().lower() not in ("0", "false", "no", "off", "")
        else:
            flags[name] = bool(value)
    return flags


def register_routes() -> bool:
    """Register the two model-manager routes (idempotent)."""
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return True
    try:
        from aiohttp import web
        from server import PromptServer
    except Exception as exc:
        LOGGER.debug("Model-manager routes not registered outside ComfyUI: %s", exc)
        return False

    routes = PromptServer.instance.routes

    @routes.get(PREFLIGHT_PATH)
    async def _model_preflight_get(request):
        flags = _parse_flags(request.rel_url.query)
        report = await asyncio.to_thread(build_preflight, flags, False)
        return web.json_response(
            {"ok": True, "downloaded": False, "preflight": report, "lines": format_preflight_report(report)}
        )

    @routes.post(PREFLIGHT_PATH)
    async def _model_preflight_post(request):
        body = {}
        try:
            candidate = await request.json()
            if isinstance(candidate, dict):
                body = candidate
        except Exception:
            body = {}
        flags = _parse_flags(body)
        download = bool(body.get("download", True))
        try:
            report = await asyncio.to_thread(build_preflight, flags, download)
        except Exception as exc:
            LOGGER.exception("Model preflight failed")
            return web.json_response(
                {"ok": False, "downloaded": False, "error": f"{type(exc).__name__}: {exc}"}, status=500
            )
        return web.json_response(
            {
                "ok": bool(report["summary"]["ok"]),
                "downloaded": download,
                "preflight": report,
                "lines": format_preflight_report(report),
            }
        )

    _ROUTES_REGISTERED = True
    LOGGER.info("Registered the model-manager preflight routes.")
    return True
