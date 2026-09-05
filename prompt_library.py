"""Safe prompt-library discovery and loading.

The prompt library is used by the LLM Prompt Library / Template node and by its
small frontend helper.  It supports bundled prompt libraries and user-supplied
external directories while keeping file selection inside the chosen root.
"""
from __future__ import annotations

import os
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .toolkit_logging import get_logger

LOGGER = get_logger("prompt_library")
PACKAGE_ROOT = Path(__file__).resolve().parent
BUNDLED_USER_DIR = PACKAGE_ROOT / "prompts" / "user"
BUNDLED_SYSTEM_DIR = PACKAGE_ROOT / "prompts" / "system"
ALLOWED_EXTENSIONS = frozenset({".txt", ".md", ".prompt"})
MAX_PROMPT_BYTES = 2 * 1024 * 1024
PLACEHOLDER = "<select a prompt>"
_ROUTES_REGISTERED = False


class PromptLibraryError(ValueError):
    """User-facing error raised for invalid prompt-library configuration."""


@dataclass(frozen=True)
class PromptFile:
    relative_path: str
    absolute_path: Path


def bundled_root(kind: str) -> Path:
    kind = (kind or "").strip().lower()
    if kind == "user":
        return BUNDLED_USER_DIR
    if kind == "system":
        return BUNDLED_SYSTEM_DIR
    raise PromptLibraryError(f"Unknown prompt kind '{kind}'. Expected 'user' or 'system'.")


def normalize_external_directory(value: str) -> Path:
    raw = os.path.expandvars(os.path.expanduser((value or "").strip()))
    if not raw:
        raise PromptLibraryError("External prompt directory is empty.")
    root = Path(raw).resolve()
    if not root.exists():
        raise PromptLibraryError(f"Prompt directory does not exist: {root}")
    if not root.is_dir():
        raise PromptLibraryError(f"Prompt path is not a directory: {root}")
    return root


def resolve_root(kind: str, source: str, directory: str = "") -> Path:
    source = (source or "manual").strip().lower()
    if source == "bundled_library":
        root = bundled_root(kind).resolve()
        if not root.is_dir():
            raise PromptLibraryError(f"Bundled {kind} prompt directory is missing: {root}")
        return root
    if source == "external_directory":
        return normalize_external_directory(directory)
    raise PromptLibraryError(
        f"Prompt source '{source}' does not use a file library. Choose bundled_library or external_directory."
    )


def _iter_prompt_paths(root: Path) -> Iterable[Path]:
    """Yield prompt files that resolve inside *root*.

    Symlinks that escape the selected library are intentionally ignored so a
    library listing cannot expose files outside its configured root.
    """
    root = root.resolve()
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith(".") or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            path.resolve().relative_to(root)
        except (OSError, ValueError):
            LOGGER.warning("Ignoring prompt file outside library root: %s", path)
            continue
        yield path


def list_prompt_files(kind: str, source: str, directory: str = "") -> list[str]:
    root = resolve_root(kind, source, directory)
    result: list[str] = []
    for path in _iter_prompt_paths(root):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        result.append(relative)
    result.sort(key=str.casefold)
    return result


def _safe_selected_path(root: Path, selected: str) -> Path:
    selected = (selected or "").strip().replace("\\", "/")
    if not selected or selected == PLACEHOLDER:
        raise PromptLibraryError("No prompt file selected.")
    if Path(selected).is_absolute():
        raise PromptLibraryError("Prompt selection must be relative to the selected library directory.")

    candidate = (root / selected).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PromptLibraryError("Prompt selection escapes the selected library directory.") from exc

    if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise PromptLibraryError(
            f"Unsupported prompt extension '{candidate.suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
    if not candidate.exists() or not candidate.is_file():
        raise PromptLibraryError(f"Selected prompt file does not exist: {candidate}")
    return candidate


def load_prompt_file(kind: str, source: str, directory: str, selected: str) -> tuple[str, str]:
    """Return (text, display-relative-path) for a selected prompt file."""
    root = resolve_root(kind, source, directory)
    path = _safe_selected_path(root, selected)
    size = path.stat().st_size
    if size > MAX_PROMPT_BYTES:
        raise PromptLibraryError(
            f"Prompt file is too large ({size:,} bytes). Maximum supported size is {MAX_PROMPT_BYTES:,} bytes."
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PromptLibraryError(f"Prompt file is not valid UTF-8: {path.name}") from exc
    except OSError as exc:
        raise PromptLibraryError(f"Could not read prompt file '{path}': {exc}") from exc

    text = text.strip()
    if not text:
        raise PromptLibraryError(f"Prompt file is empty: {path.name}")

    relative = path.relative_to(root).as_posix()
    LOGGER.info("Loaded %s prompt '%s' (%d chars)", kind, relative, len(text))
    return text, relative


def resolve_prompt(kind: str, source: str, directory: str, selected_file: str, manual_text: str = "") -> tuple[str, str]:
    """Resolve one prompt (user or system) to its final text.

    Returns ``(text, origin)`` where origin is ``<manual>`` or the display
    relative path of the selected file.  Raises :class:`PromptLibraryError` or
    :class:`ValueError` with a user-facing message when the configuration is
    incomplete.
    """
    source = (source or "manual").strip().lower()
    if source == "manual":
        text = (manual_text or "").strip()
        if not text:
            raise ValueError(f"Manual {kind} prompt is empty.")
        return text, "<manual>"
    return load_prompt_file(kind, source, directory, selected_file)


def prompt_selection_fingerprint(kind: str, source: str, directory: str, selected: str, manual_text: str = "") -> str:
    """Stable fingerprint used by ComfyUI caching.

    File-backed prompts are hashed by content, so editing a selected prompt file
    causes the template node to re-execute even when the filename stays the same.
    """
    source = (source or "manual").strip().lower()
    if source == "manual":
        payload = (manual_text or "").encode("utf-8", errors="replace")
        return "manual:" + hashlib.sha256(payload).hexdigest()
    try:
        text, relative = load_prompt_file(kind, source, directory, selected)
        payload = (source + "\0" + relative + "\0" + text).encode("utf-8", errors="replace")
        return source + ":" + hashlib.sha256(payload).hexdigest()
    except Exception as exc:
        # Keep node validation/error reporting in build(); still return a deterministic
        # fingerprint so ComfyUI can construct the graph without crashing here.
        return f"error:{source}:{selected}:{type(exc).__name__}:{exc}"


def default_combo_values(kind: str) -> list[str]:
    """Initial COMBO options shown before the frontend performs a refresh."""
    try:
        values = list_prompt_files(kind, "bundled_library")
    except Exception as exc:  # keep ComfyUI node discovery alive if installation is incomplete
        LOGGER.warning("Could not enumerate bundled %s prompts: %s", kind, exc)
        values = []
    return [PLACEHOLDER, *values]


def save_custom_prompt(
    source: str,
    directory: str,
    filename: str,
    fields: dict,
    description: str,
    overwrite: bool = False,
) -> str:
    """Save the current structured-prompt values as a prompt file.

    Writes a metadata block (Genre/Tempo/Key/Lyrics/Language/Voice/Theme/
    Length; ``custom`` values are omitted) plus the description into
    ``<prompt-root>/_custom/<name>.txt``.  Returns the display-relative path
    (``_custom/<name>.txt``).  Existing files are only replaced when
    ``overwrite`` is true.
    """
    from .filename_utils import safe_filename_component

    root = resolve_root("user", source, directory)
    custom_dir = root / "_custom"
    name = (filename or "").strip()
    if not name:
        raise PromptLibraryError("Prompt file name is empty.")
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise PromptLibraryError("Prompt file name must be a plain file name without folders.")
    stem = Path(name).stem
    safe = safe_filename_component(stem)
    if not safe or safe == "song":
        raise PromptLibraryError(f"Prompt file name '{name}' is invalid after sanitizing.")
    target = custom_dir / f"{safe}.txt"
    if target.exists() and not overwrite:
        raise PromptLibraryError(
            f"A custom prompt '{safe}.txt' already exists in _custom/. "
            "Choose another name or allow overwrite."
        )

    labels = {
        "genre": "Genre", "tempo": "Tempo", "key": "Key", "lyrics": "Lyrics",
        "language": "Language", "voice": "Voice", "theme": "Theme", "length": "Length",
    }
    lines = ["---"]
    for field in ("genre", "tempo", "key", "lyrics", "language", "voice", "theme", "length"):
        value = fields.get(field)
        if isinstance(value, str):
            value = value.strip()
        if value and value != "custom":
            lines.append(f"{labels[field]}: {value}")
    lines.append("---")
    lines.append("")
    lines.append((description or "").strip() or "Custom prompt.")
    custom_dir.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    LOGGER.info("Saved custom user prompt: %s (%d lines)", target, len(lines))
    return f"_custom/{safe}.txt"


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
            files = list_prompt_files(kind, source, directory)
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
        aggregated unique field values used to refresh the combo options."""
        source = request.rel_url.query.get("source", "bundled_library")
        directory = request.rel_url.query.get("directory", "")
        selected = request.rel_url.query.get("file", "")
        try:
            from .prompt_metadata import (
                collect_file_field_values,
                merge_field_options,
                parse_prompt_front_matter,
            )

            text, _relative = load_prompt_file("user", source, directory, selected)
            fields, description = parse_prompt_front_matter(text)
            root = resolve_root("user", source, directory)
            unique_values = merge_field_options(
                collect_file_field_values(p for p in _iter_prompt_paths(root))
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
        source = str(body.get("source") or "bundled_library")
        directory = str(body.get("directory") or "")
        filename = str(body.get("file") or "")
        fields = body.get("fields") or {}
        description = str(body.get("description") or "")
        overwrite = bool(body.get("overwrite", False))
        try:
            relative = save_custom_prompt(source, directory, filename, fields, description, overwrite)
        except (PromptLibraryError, ValueError) as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - defensive server boundary
            LOGGER.exception("Unexpected save_prompt failure")
            return web.json_response(
                {"ok": False, "error": f"Unexpected save_prompt error: {type(exc).__name__}"},
                status=500,
            )
        try:
            from .minimax_structured_prompt import invalidate_library_options_cache
            invalidate_library_options_cache()
        except Exception:  # pragma: no cover - option cache refresh is best-effort
            pass
        return web.json_response({"ok": True, "file": relative})

    _ROUTES_REGISTERED = True
    LOGGER.debug("Registered prompt-library route")
    return True
