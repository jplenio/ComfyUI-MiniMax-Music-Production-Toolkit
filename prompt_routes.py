"""HTTP adapter for the prompt library (F17 / T15).

Extracted from ``prompt_library`` so the filesystem service has no HTTP
dependency and no node imports.  The five routes, their payloads and their
status codes are unchanged; ``prompt_library.register_routes`` remains as a
lazy compatibility delegate.

Validation lives on the service boundary (``prompt_library._body_string`` and
friends); this module only adapts aiohttp requests to those calls.
"""
from __future__ import annotations

import asyncio

from .prompt_library import (
    PLACEHOLDER,
    PromptLibraryError,
    _body_bool,
    _body_fields,
    _body_string,
    _iter_prompt_paths,
    invalidate_library_options,
    list_prompt_files,
    load_prompt_file,
    resolve_root,
    save_custom_prompt,
    save_custom_system_prompt,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("prompt_routes")

_ROUTES_REGISTERED = False


def register_routes() -> bool:
    """Register the read-only prompt-file listing route used by the frontend."""
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return True
    try:
        from aiohttp import web
        from server import PromptServer
    except Exception as exc:
        LOGGER.debug("Prompt-library HTTP route not registered outside ComfyUI: %s", exc)
        return False

    routes = PromptServer.instance.routes

    @routes.get("/minimax_music_toolkit/prompt_files")
    async def _prompt_files(request):
        kind = request.rel_url.query.get("kind", "user")
        source = request.rel_url.query.get("source", "bundled_library")
        directory = request.rel_url.query.get("directory", "")
        try:
            # U02: directory scans and file reads are blocking work; they run in a
            # worker thread so a few thousand prompt files cannot stall the event
            # loop while the UI waits for the route.
            files = await asyncio.to_thread(list_prompt_files, kind, source, directory)
            return web.json_response({"ok": True, "files": files})
        except PromptLibraryError as exc:
            return web.json_response({"ok": False, "error": str(exc), "files": []}, status=400)
        except Exception as exc:  # pragma: no cover - defensive server boundary
            LOGGER.exception("Unexpected prompt-library listing failure")
            return web.json_response(
                {"ok": False, "error": f"Unexpected prompt-library error: {type(exc).__name__}", "files": []},
                status=500,
            )

    @routes.get("/minimax_music_toolkit/prompt_metadata")
    async def _prompt_metadata(request):
        """Return the structured metadata of one user prompt file plus the
        aggregated unique field values used to refresh the combo options.

        The selected file is optional: an absent/empty ``file`` parameter
        returns the aggregated options only (used by the option refresh), with
        the same response envelope as a successful file lookup.
        """
        source = request.rel_url.query.get("source", "bundled_library")
        directory = request.rel_url.query.get("directory", "")
        selected = (request.rel_url.query.get("file", "") or "").strip()
        try:
            from .prompt_metadata import (
                collect_file_field_values,
                merge_field_options,
                parse_prompt_front_matter,
            )

            root = resolve_root("user", source, directory)
            fields: dict = {}
            description = ""
            if selected and selected != PLACEHOLDER:
                text, _relative = await asyncio.to_thread(
                    load_prompt_file, "user", source, directory, selected
                )
                fields, description = parse_prompt_front_matter(text)
            # The option aggregation reads every prompt file in the library; that
            # is exactly the work that must not sit in the event loop thread.
            unique_values = await asyncio.to_thread(
                lambda: merge_field_options(
                    collect_file_field_values(p for p in _iter_prompt_paths(root))
                )
            )
            return web.json_response({
                "ok": True,
                "fields": fields,
                "description": description,
                "unique_values": unique_values,
            })
        except (PromptLibraryError, ValueError) as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - defensive server boundary
            LOGGER.exception("Unexpected prompt-metadata failure")
            return web.json_response(
                {"ok": False, "error": f"Unexpected prompt-metadata error: {type(exc).__name__}"},
                status=500,
            )

    @routes.post("/minimax_music_toolkit/save_prompt")
    async def _save_prompt(request):
        """Save the current structured-prompt widget values as a custom prompt
        file inside the selected prompt library's _custom/ folder."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body."}, status=400)
        try:
            if not isinstance(body, dict):
                raise PromptLibraryError("Request body must be a JSON object.")
            source = _body_string(body, "source", "bundled_library")
            directory = _body_string(body, "directory", "")
            filename = _body_string(body, "file", "")
            fields = _body_fields(body)
            description = _body_string(body, "description", "")
            overwrite = _body_bool(body, "overwrite", False)
            relative = save_custom_prompt(source, directory, filename, fields, description, overwrite)
        except (PromptLibraryError, ValueError) as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - defensive server boundary
            LOGGER.exception("Unexpected save_prompt failure")
            return web.json_response(
                {"ok": False, "error": f"Unexpected save_prompt error: {type(exc).__name__}"},
                status=500,
            )
        invalidate_library_options()
        return web.json_response({"ok": True, "file": relative})

    @routes.get("/minimax_music_toolkit/prompt_text")
    async def _prompt_text(request):
        """Return the raw text of one prompt file (user or system)."""
        kind = request.rel_url.query.get("kind", "user")
        source = request.rel_url.query.get("source", "bundled_library")
        directory = request.rel_url.query.get("directory", "")
        selected = request.rel_url.query.get("file", "")
        try:
            text, _relative = await asyncio.to_thread(load_prompt_file, kind, source, directory, selected)
            return web.json_response({"ok": True, "text": text})
        except (PromptLibraryError, ValueError) as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - defensive server boundary
            LOGGER.exception("Unexpected prompt-text failure")
            return web.json_response(
                {"ok": False, "error": f"Unexpected prompt-text error: {type(exc).__name__}"},
                status=500,
            )

    @routes.post("/minimax_music_toolkit/save_system_prompt")
    async def _save_system_prompt(request):
        """Save the current system_prompt text as a plain system prompt file."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body."}, status=400)
        try:
            if not isinstance(body, dict):
                raise PromptLibraryError("Request body must be a JSON object.")
            source = _body_string(body, "source", "bundled_library")
            directory = _body_string(body, "directory", "")
            filename = _body_string(body, "file", "")
            text = _body_string(body, "text", "")
            overwrite = _body_bool(body, "overwrite", False)
            relative = save_custom_system_prompt(source, directory, filename, text, overwrite)
        except (PromptLibraryError, ValueError) as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - defensive server boundary
            LOGGER.exception("Unexpected save_system_prompt failure")
            return web.json_response(
                {"ok": False, "error": f"Unexpected save_system_prompt error: {type(exc).__name__}"},
                status=500,
            )
        return web.json_response({"ok": True, "file": relative})

    _ROUTES_REGISTERED = True
    LOGGER.debug("Registered prompt-library route")
    return True
