"""Explicit UI actions for LLM configuration; secrets live only in server RAM."""
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from .llm_providers import LOCAL, CLOUD, connection, remember_key, forget_key, list_remote_models

_REGISTERED = False
PATH = "/minimax_music_toolkit/llm"


def register_routes():
    global _REGISTERED
    if _REGISTERED:
        return
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.get(PATH + "/providers")
    async def providers(request):
        return web.json_response({"local": LOCAL, "cloud": CLOUD})

    @PromptServer.instance.routes.post(PATH + "/configure")
    async def configure(request):
        # Configuration is a same-origin UI operation, never a cross-site form.
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            return web.json_response({"error": "Cross-origin configuration is not allowed."}, status=403)
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON."}, status=415)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Expected a configuration object.")
            action = body.get("action")
            options = {name: str(body.get(name, "")) for name in (
                "backend", "local_provider", "cloud_provider", "server_url", "api_key_env", "credential_id")}
            if action == "clear_key":
                forget_key(options["credential_id"])
                return web.json_response({"ok": True})
            if action == "set_key":
                _, base, _, _ = connection(options["backend"], options["local_provider"], options["cloud_provider"], options["server_url"])
                handle = remember_key(base, body.get("key", ""), options["credential_id"])
                return web.json_response({"credential_id": handle})
            if action == "models":
                models = await asyncio.to_thread(list_remote_models, **options)
                return web.json_response({"models": models})
            raise ValueError("Unknown configuration action.")
        except (ValueError, RuntimeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)

    _REGISTERED = True
