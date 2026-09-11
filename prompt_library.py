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


def _custom_target(root: Path, safe_stem: str, kind: str) -> Path:
    """Prepare ``<root>/_custom/<safe_stem>.txt`` with resolved containment.

    ``_custom`` (or a file inside it) can be a symlink/junction pointing outside
    the selected library.  Reads are already protected by ``_safe_selected_path``;
    writes must offer the same protection instead of trusting the path join.
    """
    custom_dir = root / "_custom"
    custom_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir = custom_dir.resolve()
    try:
        resolved_dir.relative_to(root.resolve())
    except ValueError as exc:
        raise PromptLibraryError(
            f"Custom {kind} prompt directory resolves outside the selected library root: {resolved_dir}"
        ) from exc

    target = resolved_dir / f"{safe_stem}.txt"
    if target.is_symlink():
        raise PromptLibraryError(
            f"Refusing to write custom {kind} prompt through the symlink '{target.name}'."
        )
    return target


def _exclusive_write_text(target: Path, payload: str, overwrite: bool, kind: str) -> None:
    """Write *payload* to *target* without ever clobbering an unrelated file.

    ``overwrite=False`` uses ``O_CREAT|O_EXCL``, which is atomic: a file created
    between the existence check and the write makes the call fail instead of
    being silently replaced.  ``overwrite=True`` stages a same-directory file
    and publishes it with ``os.replace`` so a failed write cannot leave a
    truncated prompt behind.
    """
    if overwrite:
        staging = target.with_name(f".{target.name}.{os.getpid()}.part")
        try:
            staging.write_text(payload, encoding="utf-8", newline="\n")
            os.replace(staging, target)
        finally:
            try:
                staging.unlink()
            except OSError:
                pass
        return
    try:
        handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    except FileExistsError as exc:
        raise PromptLibraryError(
            f"A custom {kind} prompt '{target.name}' already exists in _custom/. "
            "Choose another name or allow overwrite."
        ) from exc
    except OSError as exc:
        raise PromptLibraryError(f"Could not create custom {kind} prompt '{target.name}': {exc}") from exc
    with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def save_custom_prompt(
    source: str,
    directory: str,
    filename: str,
    fields: dict,
    description: str,
    overwrite: bool = False,
) -> str:
    """Save the current structured-prompt values as a prompt file.

    Writes a metadata block (all canonical structured fields, e.g.
    Genre/Tempo/Time signature/Key/Lyrics/Language/Voice/Theme/Length;
    ``custom`` values are omitted) plus the description into
    ``<prompt-root>/_custom/<name>.txt``.  Returns the display-relative path
    (``_custom/<name>.txt``).  Existing files are only replaced when
    ``overwrite`` is true.
    """
    from .filename_utils import safe_filename_component

    root = resolve_root("user", source, directory)
    name = (filename or "").strip()
    if not name:
        raise PromptLibraryError("Prompt file name is empty.")
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise PromptLibraryError("Prompt file name must be a plain file name without folders.")
    stem = Path(name).stem
    safe = safe_filename_component(stem)
    if not safe or safe == "song":
        raise PromptLibraryError(f"Prompt file name '{name}' is invalid after sanitizing.")
    target = _custom_target(root, safe, "user")
    if target.exists() and not overwrite:
        raise PromptLibraryError(
            f"A custom prompt '{safe}.txt' already exists in _custom/. "
            "Choose another name or allow overwrite."
        )

    # Canonical field order and display labels come from prompt_metadata so
    # the saved file always matches what the structured node understands
    # (including newer fields such as meter / time signature).  Fall back to
    # the historic hardcoded list if the import is unavailable.
    try:
        from .prompt_metadata import FIELD_LABELS, STRUCTURED_FIELDS

        labels = {field: FIELD_LABELS[field] for field in STRUCTURED_FIELDS}
        field_order = tuple(STRUCTURED_FIELDS)
    except Exception:  # pragma: no cover - defensive fallback only
        labels = {
            "genre": "Genre", "tempo": "Tempo", "key": "Key", "lyrics": "Lyrics",
            "language": "Language", "voice": "Voice", "theme": "Theme", "length": "Length",
        }
        field_order = tuple(labels)
    lines = ["---"]
    for field in field_order:
        value = fields.get(field)
        if isinstance(value, str):
            value = value.strip()
        if value and value != "custom":
            lines.append(f"{labels[field]}: {value}")
    lines.append("---")
    lines.append("")
    lines.append((description or "").strip() or "Custom prompt.")
    _exclusive_write_text(target, "\n".join(lines) + "\n", overwrite, "user")
    LOGGER.info("Saved custom user prompt: %s (%d lines)", target, len(lines))
    return f"_custom/{safe}.txt"


def save_custom_system_prompt(
    source: str,
    directory: str,
    filename: str,
    text: str,
    overwrite: bool = False,
) -> str:
    """Save an editable system-prompt text as a plain prompt file.

    System prompts have no metadata block: the full text is used verbatim as
    the LLM system prompt.  The file is written into ``<system-root>/_custom/
    <name>.txt`` and the display-relative path is returned.  Existing files are
    only replaced when ``overwrite`` is true.
    """
    from .filename_utils import safe_filename_component

    root = resolve_root("system", source, directory)
    name = (filename or "").strip()
    if not name:
        raise PromptLibraryError("System prompt file name is empty.")
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise PromptLibraryError("System prompt file name must be a plain file name without folders.")
    stem = Path(name).stem
    safe = safe_filename_component(stem)
    if not safe or safe == "song":
        raise PromptLibraryError(f"System prompt file name '{name}' is invalid after sanitizing.")
    target = _custom_target(root, safe, "system")
    if target.exists() and not overwrite:
        raise PromptLibraryError(
            f"A custom system prompt '{safe}.txt' already exists in _custom/. "
            "Choose another name or allow overwrite."
        )

    payload = (text or "").strip()
    if not payload:
        raise PromptLibraryError("System prompt text is empty.")
    _exclusive_write_text(target, payload + "\n", overwrite, "system")
    LOGGER.info("Saved custom system prompt: %s (%d chars)", target, len(payload))
    return f"_custom/{safe}.txt"


def _body_string(body: dict, key: str, default: str = "") -> str:
    value = body.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise PromptLibraryError(f"Field '{key}' must be a string.")
    return value


def _body_bool(body: dict, key: str, default: bool = False) -> bool:
    value = body.get(key, default)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise PromptLibraryError(f"Field '{key}' must be a boolean.")
    return value


def _body_fields(body: dict) -> dict:
    fields = body.get("fields")
    if fields is None:
        return {}
    if not isinstance(fields, dict):
        raise PromptLibraryError("Field 'fields' must be an object of string values.")
    for name, value in fields.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise PromptLibraryError("Field 'fields' must map string names to string values.")
    return fields


def register_routes() -> bool:
    """Compatibility delegate; the HTTP adapter lives in :mod:`prompt_routes`."""
    from .prompt_routes import register_routes as _register_routes

    return _register_routes()


# --- aggregated structured-field options -----------------------------------

_LIBRARY_OPTIONS_MAX_PER_FIELD = 200
_options_cache: Dict[str, Dict[str, list]] = {}
_options_version = 0


def invalidate_library_options(kind: str = "user") -> None:
    """Drop the cached options after prompt files changed on disk.

    Cache keys are ``kind|source|directory``, so a targeted invalidation drops
    every entry of that kind regardless of source or directory.
    """
    global _options_version
    _options_version += 1
    if kind == "all":
        _options_cache.clear()
        return
    prefix = f"{kind}|"
    for key in [key for key in _options_cache if key.startswith(prefix)]:
        _options_cache.pop(key, None)


def library_option_version() -> int:
    """Monotonic counter bumped on every invalidation (diagnostics/tests)."""
    return _options_version


def library_options(kind: str = "user", source: str = "bundled_library", directory: str = "") -> Dict[str, list]:
    """Curated vocabulary merged with the values found in the prompt library.

    Uses the same safe enumeration as every other library read (extension
    filter, hidden-file skip, symlink containment) and the same per-file byte
    limit as a selected prompt, so aggregation cannot be tricked into reading
    something the library would refuse to load.
    """
    cache_key = f"{kind}|{source}|{directory}"
    cached = _options_cache.get(cache_key)
    if cached is not None:
        return cached

    from .prompt_metadata import (
        LYRICS_CHOICES,
        collect_file_field_values,
        merge_field_options,
    )

    try:
        root = resolve_root(kind, source, directory)
        collected = collect_file_field_values(
            _iter_prompt_paths(root), max_options=_LIBRARY_OPTIONS_MAX_PER_FIELD, max_bytes=MAX_PROMPT_BYTES
        )
    except Exception as exc:  # keep ComfyUI node discovery alive on broken installs
        LOGGER.warning("Could not aggregate %s prompt metadata: %s", kind, exc)
        collected = {}

    options = merge_field_options(collected)
    if not options.get("lyrics"):
        options["lyrics"] = list(LYRICS_CHOICES)
    _options_cache[cache_key] = options
    return options
