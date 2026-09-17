"""Model auto-download and presence checking.

The toolkit ships a declarative :file:`models_config.json` that maps every
model file the example workflow needs to its target folder inside the ComfyUI
``models`` directory.  Entries with a ``url`` can be downloaded automatically
on first use; entries without a URL (for example gated MiniMax / FLUX.2 model
files) are only checked and reported with guidance.

Download behavior follows the user-facing contract:

- a needed file is only downloaded when it is missing or empty
- every download is logged with progress and the final target path
- the run continues afterwards; a missing file only fails the run when
  ``auto_download`` is enabled and the download itself fails
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import random
import re
import threading
import time
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .toolkit_logging import get_logger

LOGGER = get_logger("model_downloader")

CONFIG_PATH = Path(__file__).resolve().parent / "models_config.json"
# Config schema versions this module can read.  Every field added after v2 is
# optional, so an existing user config keeps working untouched; an unknown
# version is reported instead of guessed.
SUPPORTED_CONFIG_VERSIONS = (1, 2, 3)
# Documented Hugging Face resolve rule.  The rule is generic; the repository and
# file names it is applied to must still be verified per artifact (see D02).
HF_RESOLVE_TEMPLATE = "https://huggingface.co/{prefix}{repo_id}/resolve/{revision}/{filename}"
_DOWNLOAD_LOCK = threading.Lock()
_STAGING_COUNTER = itertools.count()

# ---------------------------------------------------------------------------
# Transfer policy (D03)
# ---------------------------------------------------------------------------
# Retryable: transient server/network conditions.  429 honours Retry-After.
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
# Not retryable: permission/configuration problems cannot be fixed by waiting.
FATAL_STATUSES = frozenset({400, 401, 403, 404, 410, 451})
DOWNLOAD_ATTEMPTS_DEFAULT = 4
RETRY_BASE_SECONDS = 0.5
RETRY_MAX_SECONDS = 30.0
# Verification results are cached by path+size+mtime, so a large existing file is
# not hashed again on every check - only when its signature actually changed.
VERIFIED_CACHE_MAX = 32
VERIFIED_CACHE: "OrderedDict[tuple, bool]" = OrderedDict()
# One lock per destination file (process/thread level): two callers must not
# write the same staging file, while different files still transfer in parallel.
DESTINATION_LOCKS: Dict[str, threading.Lock] = {}
_DESTINATION_LOCKS_GUARD = threading.Lock()


class DownloadError(RuntimeError):
    """A transfer that cannot succeed as configured (retrying would not help)."""


class IncompleteTransfer(RuntimeError):
    """The body ended early; the partial file is kept and can be resumed."""


def redact_url(url: str) -> str:
    """URL without query/fragment: signed parameters and tokens must not be logged."""
    try:
        parts = urlsplit(url)
    except ValueError:  # pragma: no cover - defensive
        return "<unparsable url>"
    if not parts.query and not parts.fragment:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def destination_lock(destination: Path) -> threading.Lock:
    """The lock for one destination file, created on first use."""
    key = str(destination.absolute())
    with _DESTINATION_LOCKS_GUARD:
        lock = DESTINATION_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            DESTINATION_LOCKS[key] = lock
        return lock


def _retry_delay(attempt: int, retry_after: Optional[str]) -> float:
    """Backoff with jitter; a server-provided Retry-After wins."""
    if retry_after:
        try:
            return max(0.0, min(float(str(retry_after).strip()), RETRY_MAX_SECONDS))
        except (TypeError, ValueError):
            pass
    base = min(RETRY_BASE_SECONDS * (2 ** attempt), RETRY_MAX_SECONDS)
    return base * (0.5 + random.random() * 0.5)


def open_with_retries(request: Request, timeout: int, attempts: int, label: str):
    """Open ``request`` with a bounded number of retries.

    Network errors, 429 and selected 5xx are retried with backoff and jitter
    (honouring ``Retry-After``); 401/403/404 fail immediately instead of looping.
    """
    attempts = max(1, int(attempts))
    last_error: Optional[BaseException] = None
    retry_after: Optional[str] = None
    for attempt in range(attempts):
        retry_after = None
        try:
            return urlopen(request, timeout=timeout)
        except HTTPError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            if status in FATAL_STATUSES:
                raise DownloadError(
                    f"{label}: HTTP {status} ({redact_url(request.full_url)}) - not retrying"
                ) from exc
            if status not in RETRYABLE_STATUSES:
                raise
            last_error = exc
            retry_after = (exc.headers or {}).get("Retry-After")
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt + 1 >= attempts:
            break
        delay = _retry_delay(attempt, retry_after)
        LOGGER.info(
            "Retrying %s in %.1fs (attempt %d/%d): %s",
            label,
            delay,
            attempt + 2,
            attempts,
            type(last_error).__name__,
        )
        time.sleep(delay)
    raise DownloadError(
        f"{label}: gave up after {attempts} attempt(s): "
        f"{type(last_error).__name__}: {last_error}"
    ) from last_error


def check_disk_space(destination: Path, needed_bytes: Optional[int], label: str) -> None:
    """Refuse to start when the volume cannot hold the transfer.

    Only checked when the expected size is known; an unknown size is not guessed.
    The partial file and the final file may coexist briefly, so the requirement
    is twice the payload plus a small margin.
    """
    if not needed_bytes or needed_bytes <= 0:
        return
    try:
        import shutil

        free = shutil.disk_usage(destination.parent).free
    except Exception:  # pragma: no cover - platform dependent
        return
    required = needed_bytes * 2 + (64 << 20)
    if free < required:
        raise DownloadError(
            f"{label}: not enough free disk space for the download: "
            f"{free / 1e9:.2f} GB free, {required / 1e9:.2f} GB required "
            "(payload, staging copy and margin)"
        )


def _parse_content_range(value: Optional[str]):
    """``(start, total)`` from a 206 ``Content-Range`` header, else ``(None, None)``."""
    if not value:
        return None, None
    match = re.match(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", value.strip())
    if not match:
        return None, None
    start = int(match.group(1))
    total = None if match.group(3) == "*" else int(match.group(3))
    return start, total


def _verify_sha256(path: Path, expected: Optional[str]) -> bool:
    if not expected:
        return True
    digest = hashlib.sha256()
    # Block-wise: a multi-GB checkpoint is never read into RAM whole.
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower() == expected.strip().lower()


def _file_is_ready(path: Path, expected_sha256: Optional[str] = None, min_bytes: int = 1) -> bool:
    """Whether a usable file is already in place.

    A hash is only recomputed when the file's signature (size + mtime) changed,
    so repeated checks of a multi-GB checkpoint stay cheap; the cache is not a
    security boundary - it is a local operational check.
    """
    if not path.is_file():
        return False
    try:
        stat = path.stat()
    except OSError:  # pragma: no cover - race with a delete
        return False
    if stat.st_size < max(1, int(min_bytes or 1)):
        return False
    if not expected_sha256:
        return True
    key = (str(path), stat.st_size, stat.st_mtime_ns, expected_sha256.strip().lower())
    cached = VERIFIED_CACHE.get(key)
    if cached is not None:
        VERIFIED_CACHE.move_to_end(key)
        return cached
    result = _verify_sha256(path, expected_sha256)
    VERIFIED_CACHE[key] = result
    VERIFIED_CACHE.move_to_end(key)
    while len(VERIFIED_CACHE) > VERIFIED_CACHE_MAX:
        VERIFIED_CACHE.popitem(last=False)
    return result


def _staging_path(destination: Path) -> Path:
    """Staging file for ``destination``.

    Deliberately a stable name (not a per-call unique one): a resume needs a
    partial file it can find again, and the sidecar records which URL/validator
    produced it.  Concurrency is handled by :func:`destination_lock` plus the
    sidecar check, not by the file name.
    """
    return destination.with_name(f"{destination.name}.part")


def _sidecar_path(destination: Path) -> Path:
    return destination.with_name(f"{destination.name}.part.json")


def _load_sidecar(destination: Path) -> Dict[str, Any]:
    try:
        data = json.loads(_sidecar_path(destination).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_sidecar(destination: Path, payload: Dict[str, Any]) -> None:
    try:
        _sidecar_path(destination).write_text(json.dumps(payload), encoding="utf-8")
    except OSError:  # pragma: no cover - defensive
        LOGGER.debug("Could not write the download sidecar for %s", destination.name)


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def load_models_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the declarative model configuration."""
    config_path = Path(path) if path else CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid models config: {config_path}")
    return data


def comfy_base_path() -> Path:
    """Resolve the ComfyUI base directory without importing it when unavailable."""
    try:
        import folder_paths  # type: ignore
        base = getattr(folder_paths, "base_path", None)
        if base:
            return Path(base)
    except Exception:
        pass
    env = os.environ.get("COMFYUI_BASE_PATH")
    if env:
        return Path(env)
    return Path.cwd()


def comfy_models_dir() -> Path:
    """Resolve the ComfyUI *models* directory.

    This intentionally follows ``folder_paths.models_dir`` (not ``base_path``),
    so ComfyUI started with ``--models-directory "F:\\ComfyUI\\models"`` resolves
    model targets on the F: drive.  Falls outside ComfyUI:

    - the ``COMFYUI_MODELS_DIRECTORY`` environment variable, then
    - ``<base>/models`` (ComfyUI's default layout), then
    - ``<cwd>/models``.
    """
    try:
        import folder_paths  # type: ignore
        models_dir = getattr(folder_paths, "models_dir", None)
        if models_dir:
            return Path(models_dir)
    except Exception:
        pass
    env = os.environ.get("COMFYUI_MODELS_DIRECTORY")
    if env:
        return Path(env)
    return comfy_base_path() / "models"


def config_schema_version(config: Any) -> Optional[int]:
    """The declared schema version, or ``None`` when it is absent/invalid."""
    if not isinstance(config, dict):
        return None
    version = config.get("version")
    return int(version) if isinstance(version, (int, float)) and not isinstance(version, bool) else None


def config_version_problem(config: Any) -> Optional[str]:
    """Describe an unusable schema version, else ``None``.

    A *newer* config is reported rather than silently half-read: guessing at
    fields this build does not know would be worse than saying so.
    """
    version = config_schema_version(config)
    if version is None:
        return None  # pre-versioning configs are still readable
    if version not in SUPPORTED_CONFIG_VERSIONS:
        return (
            f"models_config.json declares version {version}, which this build does not know "
            f"(supported: {', '.join(str(v) for v in SUPPORTED_CONFIG_VERSIONS)}). "
            "Update the toolkit or restore a matching config - the config was not modified."
        )
    return None


def resolve_entry_url(entry: Dict[str, Any]) -> str:
    """The effective download URL for one entry.

    An explicit ``url`` always wins.  Otherwise a Hugging Face artifact
    (``repo_id`` + ``filename``, optional ``repo_type``/``revision``) is
    resolved with the documented rule.  An entry without those fields stays
    URL-less instead of inventing one.
    """
    url = str(entry.get("url") or "")
    if url:
        return url
    repo_id = entry.get("repo_id")
    # ``filename`` is the *remote* path, ``name`` the local file name - they are
    # not interchangeable (the MiniMax artifacts live under ``diffusion_models/``
    # remotely and sit flat in the local folder).  Without an explicit
    # ``filename`` there is no URL to derive, and guessing one would download
    # the wrong file.
    filename = entry.get("filename")
    if not repo_id or not filename:
        return ""
    revision = entry.get("revision") or "main"
    repo_type = str(entry.get("repo_type") or "model").strip().lower()
    prefix = "datasets/" if repo_type == "dataset" else ""
    return HF_RESOLVE_TEMPLATE.format(
        prefix=prefix, repo_id=str(repo_id).strip("/"), revision=revision, filename=filename
    )


def resolve_target(relative_target: str, base_path: Optional[Path] = None) -> Path:
    """Resolve a config target path against the ComfyUI models directory.

    Config targets use the ComfyUI convention (``models/audio/flashsr``).  When
    ``base_path`` is given explicitly (unit tests), the target is resolved
    directly below it.  Otherwise the path is resolved below the real models
    directory, honoring ``--models-directory`` via ``folder_paths.models_dir``.
    """
    target = Path(relative_target)
    if target.is_absolute():
        return target
    if base_path is not None:
        return base_path / target
    models_dir = comfy_models_dir()
    parts = target.parts
    if parts and parts[0] == "models":
        return models_dir.joinpath(*parts[1:])
    return models_dir / target


def _hf_headers(entry: Dict[str, Any]) -> Dict[str, str]:
    headers: Dict[str, str] = {"User-Agent": "ComfyUI-MiniMax-Music-Production-Toolkit"}
    token_env = entry.get("hf_token_env") or entry.get("token_env")
    token = os.environ.get(token_env) if token_env else None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# _verify_sha256 / _file_is_ready / _staging_path live with the transfer policy
# above (D03) - they are part of the same contract.


def validate_model_entry(entry: Any) -> Optional[str]:
    """Return a problem description for a malformed entry, else ``None``.

    Config validation used to cover only the top-level dictionary, so a
    malformed ``files`` value crashed the consumer while it expanded the group.
    This reports the shape without turning any dormant config key into an
    authoritative one.
    """
    if not isinstance(entry, dict):
        return f"entry is {type(entry).__name__}, expected an object"
    name = entry.get("name")
    if name is not None and not isinstance(name, str):
        return "entry 'name' must be a string"
    target = entry.get("target")
    if target is not None and not isinstance(target, str):
        return "entry 'target' must be a string"
    url = entry.get("url")
    if url is not None and not isinstance(url, str):
        return "entry 'url' must be a string"
    for field in ("repo_id", "repo_type", "revision", "filename", "sha256"):
        value = entry.get(field)
        if value is not None and not isinstance(value, str):
            return f"entry '{field}' must be a string"
    size = entry.get("bytes")
    if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size <= 0):
        return "entry 'bytes' must be a positive integer"
    sha256 = entry.get("sha256")
    if isinstance(sha256, str) and sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        return "entry 'sha256' must be 64 hex characters"
    revision = entry.get("revision")
    if isinstance(revision, str) and revision and " " in revision:
        return "entry 'revision' must not contain spaces (use a commit sha or a tag)"
    return None


def normalize_model_entries(
    config: Dict[str, Any],
    *,
    minimax: bool = True,
    flux2: bool = True,
    flashsr: bool = True,
    llm: bool = True,
    include_optional: bool = False,
    yue2: bool = False,
    sheetsage2: bool = False,
    whisper: bool = False,
) -> List[Dict[str, Any]]:
    """Expand the configured model groups into flat check entries.

    Group-level notes and the FlashSR default target are applied here, once, so
    the check node, the FlashSR runtime and the diagnostics script all resolve
    the same entries.  Malformed entries are skipped with a warning instead of
    raising while the group is expanded.

    Entries marked ``"optional": true`` (alternative quantizations of a family)
    are excluded unless ``include_optional`` asks for them, so a download never
    pulls in a whole family by accident.
    """
    config = config if isinstance(config, dict) else {}
    entries: List[Dict[str, Any]] = []

    def add(entry: Any, *, note: str = "", default_target: str = "") -> None:
        problem = validate_model_entry(entry)
        if problem:
            LOGGER.warning("Ignoring malformed model config entry: %s", problem)
            return
        if entry.get("optional") and not include_optional:
            LOGGER.debug("Skipping optional model artifact: %s", entry.get("name"))
            return
        expanded = dict(entry)
        if note:
            expanded["note"] = expanded.get("note") or note
        if default_target:
            expanded["target"] = expanded.get("target") or default_target
        entries.append(expanded)

    if sheetsage2:
        group = config.get("sheetsage2", {}) or {}
        for entry in group.get("files", []) or []:
            add(entry, note=group.get("note", ""), default_target="models/audio_encoders")
    if whisper:
        # The whole group installs one checkpoint folder, so the group target is
        # also the loader's directory; a per-file target would split it.
        group = config.get("whisper", {}) or {}
        default_target = str(group.get("target") or "models/audio_encoders/whisper-large-v3")
        for entry in group.get("files", []) or []:
            add(entry, note=group.get("note", ""), default_target=default_target)
    if yue2:
        group = config.get("yue2", {}) or {}
        for entry in group.get("files", []) or []:
            add(entry, note=group.get("note", ""), default_target="models/checkpoints")
    if minimax:
        group = config.get("minimax", {}) or {}
        for entry in group.get("files", []) or []:
            add(entry, note=group.get("note", ""))
    if flux2:
        group = config.get("flux2", {}) or {}
        for entry in group.get("files", []) or []:
            add(entry, note=group.get("note", ""))
    if flashsr:
        weights = (config.get("flashsr", {}) or {}).get("weights", {}) or {}
        default_target = weights.get("target", "models/audio/flashsr")
        for entry in weights.get("files", []) or []:
            # The runtime only ever opens the standard file names in the group
            # target folder, so a diverging per-file target would download a
            # file that is then never found.  The group target wins; the
            # divergence is reported instead of being honoured silently.
            if isinstance(entry, dict) and entry.get("target") and default_target \
                    and str(entry["target"]).replace("\\", "/") != str(default_target).replace("\\", "/"):
                LOGGER.warning(
                    "FlashSR file '%s' declares target '%s' but the group target is '%s'; "
                    "using the group target.",
                    entry.get("name"),
                    entry.get("target"),
                    default_target,
                )
                entry = {**entry, "target": default_target}
            add(entry, default_target=default_target)
    if llm:
        group = config.get("llm", {}) or {}
        note = group.get("note", "")
        directory = group.get("directory", "") or ""
        seen = set()
        # Every configured LLM artifact, not only the example: the check node and
        # the loader must resolve the same set of files.
        for entry in list(group.get("files", []) or []) + ([group.get("example")] if group.get("example") else []):
            if isinstance(entry, dict):
                key = (entry.get("name"), entry.get("target") or directory)
                if key in seen:
                    continue
                seen.add(key)
            add(entry, note=note, default_target=directory)

    return entries


def download_file(
    url: str,
    destination: Path,
    headers: Optional[Dict[str, str]] = None,
    sha256: Optional[str] = None,
    timeout: int = 300,
    expected_bytes: Optional[int] = None,
    attempts: int = DOWNLOAD_ATTEMPTS_DEFAULT,
) -> Path:
    """Stream a URL to ``destination``; resumable, retried and verified.

    Guarantees (D03):

    * the final file appears only after the body is complete and verified - no
      empty or half-written model ever looks installed;
    * transient failures are retried with backoff and jitter (``Retry-After``
      wins), while 401/403/404 fail immediately instead of looping;
    * an interrupted transfer leaves a resumable partial plus a sidecar naming
      the URL and validator it came from.  Bytes are only appended after a
      validated ``206 Content-Range``; a ``200`` answer to a Range request
      restarts the file instead of concatenating two bodies;
    * one lock per destination keeps concurrent calls single-flight (other files
      still transfer in parallel) and free disk space is checked up front.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    min_bytes = int(expected_bytes or 1)
    if _file_is_ready(destination, sha256, min_bytes):
        LOGGER.info("Model file already present: %s", destination)
        return destination

    label = destination.name
    with destination_lock(destination):
        # Re-check after acquiring the lock: another caller may have finished it.
        if _file_is_ready(destination, sha256, min_bytes):
            return destination

        tmp = _staging_path(destination)
        sidecar = _load_sidecar(destination)
        request_headers = dict(headers or {"User-Agent": "ComfyUI-MiniMax-Music-Production-Toolkit"})
        resume_from = 0
        if tmp.is_file() and sidecar.get("url") == url:
            size = tmp.stat().st_size
            known_total = sidecar.get("total") or expected_bytes
            validator = sidecar.get("etag") or sidecar.get("last_modified")
            if validator and size > 0 and (not known_total or size < int(known_total)):
                resume_from = size
            else:
                LOGGER.info("Discarding the partial download of %s (no usable validator).", label)
                _remove_quietly(tmp)
                _remove_quietly(_sidecar_path(destination))
        elif tmp.is_file():
            # A partial produced by a different URL must never be continued.
            _remove_quietly(tmp)
            _remove_quietly(_sidecar_path(destination))

        if resume_from:
            request_headers["Range"] = f"bytes={resume_from}-"
            request_headers["If-Range"] = sidecar.get("etag") or sidecar.get("last_modified")
            LOGGER.info("Resuming %s at %d bytes.", label, resume_from)

        check_disk_space(destination, expected_bytes or sidecar.get("total"), label)
        LOGGER.info("Model download: %s -> %s", redact_url(url), destination)
        request = Request(url, headers=request_headers)
        downloaded = resume_from
        total = int(sidecar.get("total") or 0) if resume_from else 0
        keep_partial = False
        try:
            with open_with_retries(request, timeout, attempts, label) as response:
                status = int(getattr(response, "status", 200) or 200)
                if status == 206:
                    start, range_total = _parse_content_range(response.headers.get("Content-Range"))
                    if start != resume_from:
                        raise DownloadError(
                            f"{label}: server resumed at byte {start}, expected {resume_from}"
                        )
                    total = range_total or (int(response.headers.get("Content-Length") or 0) + resume_from)
                    mode = "ab"
                else:
                    if resume_from:
                        LOGGER.info(
                            "Server answered 200 to the Range request for %s; starting over.", label
                        )
                        resume_from = 0
                        downloaded = 0
                    total = int(response.headers.get("Content-Length") or 0)
                    mode = "wb"
                _write_sidecar(
                    destination,
                    {
                        "url": url,
                        "etag": response.headers.get("ETag"),
                        "last_modified": response.headers.get("Last-Modified"),
                        "total": total or None,
                    },
                )
                last_log = 0.0
                started = time.monotonic()
                try:
                    with tmp.open(mode) as out:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            out.write(chunk)
                            downloaded += len(chunk)
                            now = time.monotonic()
                            if total and (now - last_log >= 10.0 or downloaded >= total):
                                elapsed = max(1e-6, now - started)
                                speed = (downloaded - resume_from) / elapsed / 1e6
                                LOGGER.info(
                                    "Model download progress: %s %.1f%% (%.1f / %.1f MB, %.1f MB/s)",
                                    label,
                                    100.0 * downloaded / total,
                                    downloaded / 1e6,
                                    total / 1e6,
                                    speed,
                                )
                                last_log = now
                except Exception as exc:
                    if total and 0 < downloaded < total:
                        keep_partial = True
                    raise IncompleteTransfer(
                        f"{label}: transfer interrupted after {downloaded} bytes "
                        f"({type(exc).__name__})"
                    ) from exc
            if downloaded == 0:
                raise DownloadError(f"{label}: empty download (0 bytes)")
            if total and downloaded != total:
                keep_partial = downloaded > 0
                raise IncompleteTransfer(
                    f"{label}: incomplete download ({downloaded} of {total} bytes)"
                )
            if expected_bytes and downloaded != expected_bytes:
                raise DownloadError(
                    f"{label}: wrong size after download ({downloaded} bytes, expected {expected_bytes})"
                )
            if sha256 and not _verify_sha256(tmp, sha256):
                # Wrong bytes: keeping them for a resume would be misleading.
                raise DownloadError(f"{label}: SHA256 mismatch after download")
            os.replace(tmp, destination)
            _remove_quietly(_sidecar_path(destination))
        except BaseException as exc:
            resumable = keep_partial or isinstance(exc, IncompleteTransfer)
            if isinstance(exc, DownloadError) and "SHA256" in str(exc):
                resumable = False
            if isinstance(exc, KeyboardInterrupt) and tmp.is_file():
                size = tmp.stat().st_size
                resumable = bool(total and 0 < size < total)
            if resumable and tmp.is_file() and tmp.stat().st_size > 0:
                LOGGER.warning("Keeping the partial download of %s for a later resume.", label)
            else:
                _remove_quietly(tmp)
                _remove_quietly(_sidecar_path(destination))
            raise
        LOGGER.info("Model download finished: %s (%.1f MB)", destination, destination.stat().st_size / 1e6)
        return destination


def download_and_extract_zip(
    url: str,
    destination_dir: Path,
    strip_top_dir: bool = True,
    sha256: Optional[str] = None,
) -> Path:
    """Download a GitHub-style source ZIP and extract it into ``destination_dir``.

    **There is deliberately no runtime call site**: model code is vendored in
    the repository, and this public helper exists for tooling.  It is not a
    reason to re-enable downloading executable code at run time.

    Hardened against archive path escapes: every member is resolved and must
    stay inside ``destination_dir``, and absolute or drive-letter members are
    skipped.  The staging ZIP has a unique name and is always removed.
    """
    destination_dir = Path(destination_dir)
    marker = destination_dir / ".minimax_download_ok"
    if destination_dir.is_dir() and marker.is_file():
        return destination_dir

    with _DOWNLOAD_LOCK:
        if destination_dir.is_dir() and marker.is_file():
            return destination_dir
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        tmp_zip = _staging_path(destination_dir.with_suffix(destination_dir.suffix + ".zip"))
        LOGGER.info("Model code download: %s -> %s", url, destination_dir)
        request = Request(url, headers={"User-Agent": "ComfyUI-MiniMax-Music-Production-Toolkit"})
        try:
            with urlopen(request, timeout=300) as response:
                tmp_zip.write_bytes(response.read())
            if tmp_zip.stat().st_size == 0:
                raise RuntimeError(f"empty zip download for {destination_dir.name}")
            if sha256 and not _verify_sha256(tmp_zip, sha256):
                raise RuntimeError(f"SHA256 mismatch after zip download: {destination_dir.name}")
            destination_dir.mkdir(parents=True, exist_ok=True)
            root = destination_dir.resolve()
            with zipfile.ZipFile(tmp_zip) as zf:
                for member in zf.namelist():
                    raw = Path(member)
                    if raw.is_absolute() or (raw.drive and raw.drive[0].isalpha()):
                        LOGGER.warning("Skipping absolute archive member: %s", member)
                        continue
                    parts = raw.parts
                    if strip_top_dir and len(parts) > 1:
                        parts = parts[1:]
                    if not parts or any(p in {"..", ""} for p in parts):
                        continue
                    target = destination_dir.joinpath(*parts).resolve()
                    try:
                        target.relative_to(root)
                    except ValueError:
                        LOGGER.warning("Skipping archive member outside the target: %s", member)
                        continue
                    if member.endswith("/"):
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, target.open("wb") as dst:
                        while True:
                            block = src.read(1024 * 1024)
                            if not block:
                                break
                            dst.write(block)
            marker.write_text("ok\n", encoding="utf-8")
        except BaseException:
            _remove_quietly(tmp_zip)
            raise
        _remove_quietly(tmp_zip)
        LOGGER.info("Model code extracted: %s", destination_dir)
        return destination_dir


def check_file_entries(
    entries: Iterable[Dict[str, Any]],
    base_path: Optional[Path] = None,
    auto_download: bool = True,
) -> List[Dict[str, Any]]:
    """Check (and optionally download) a list of file entries.

    Each entry looks like::

        {"name": "x.pth", "target": "models/audio/flashsr", "url": "https://..."}

    Returns a report list with one dict per entry:
    ``{"name", "target", "status" (present|downloaded|missing|failed), "message"}``.
    """
    report: List[Dict[str, Any]] = []
    for entry in entries:
        name = entry.get("name", "")
        target_rel = entry.get("target", "")
        url = resolve_entry_url(entry)
        if not name:
            report.append({"name": "<unnamed>", "target": "", "status": "failed", "message": "entry has no name"})
            continue
        if not target_rel:
            # Guard against silently writing into the ComfyUI base directory root.
            report.append({"name": name, "target": "", "status": "failed", "message": "entry has no target directory"})
            continue
        destination = resolve_target(target_rel, base_path) / name
        status = "missing"
        message = ""
        try:
            if _file_is_ready(destination, entry.get("sha256"), entry.get("bytes") or 1):
                status = "present"
            elif url and auto_download:
                download_file(
                    url,
                    destination,
                    headers=_hf_headers(entry),
                    sha256=entry.get("sha256"),
                    timeout=int(entry.get("timeout", 1800)),
                    expected_bytes=int(entry["bytes"]) if entry.get("bytes") else None,
                )
                status = "downloaded"
            elif url:
                message = "missing and auto_download is disabled"
            else:
                message = (entry.get("note") or "no download URL configured").strip()
        except Exception as exc:
            status = "failed"
            message = f"{type(exc).__name__}: {exc}"
        report.append({
            "name": name,
            "target": str(destination),
            "status": status,
            "message": message,
        })
    return report


def preflight_models(
    entries: Iterable[Dict[str, Any]],
    base_path: Optional[Path] = None,
    auto_download: bool = False,
) -> Dict[str, Any]:
    """Inventory, size and space check for the selected model artifacts.

    This is the deliberately triggered setup action (D04): it answers "what is
    here, what is missing, how big is that, and does the volume hold it".
    Downloading only happens when the caller explicitly passes
    ``auto_download=True``; nothing here runs at import time or inside
    ``INPUT_TYPES()``.

    Returns a JSON-serializable dict with ``entries`` (per artifact: status,
    expected/present bytes, optional flag), a ``summary`` (counts, missing
    bytes, free space, ``required_missing``, ``ok``) and ``checked_at``.
    """
    entry_list = [dict(entry) for entry in entries]
    report = check_file_entries(entry_list, base_path=base_path, auto_download=bool(auto_download))
    expected_bytes_by_name = {entry.get("name"): entry.get("bytes") for entry in entry_list}
    optional_by_name = {entry.get("name"): bool(entry.get("optional")) for entry in entry_list}

    enriched: List[Dict[str, Any]] = []
    missing_bytes = 0
    for item in report:
        name = item["name"]
        target = item.get("target") or ""
        present_bytes: Optional[int] = None
        if target:
            candidate = Path(target)
            if candidate.is_file():
                try:
                    present_bytes = candidate.stat().st_size
                except OSError:  # pragma: no cover - race with a delete
                    present_bytes = None
        expected = expected_bytes_by_name.get(name)
        if item["status"] in ("missing", "failed") and expected:
            missing_bytes += int(expected)
        enriched.append(
            {
                **item,
                "bytes_expected": expected,
                "bytes_present": present_bytes,
                "optional": optional_by_name.get(name, False),
            }
        )

    free_bytes: Optional[int] = None
    space_ok: Optional[bool] = None
    free_candidates = []
    for directory in sorted({str(Path(item["target"]).parent) for item in enriched if item.get("target")}):
        try:
            import shutil

            free_candidates.append(shutil.disk_usage(directory).free)
        except Exception:  # pragma: no cover - platform dependent
            continue
    if free_candidates:
        free_bytes = min(free_candidates)
        # Same rule as check_disk_space: payload + staging copy + margin.
        space_ok = free_bytes >= missing_bytes * 2 + (64 << 20) if missing_bytes else True

    failed = [item["name"] for item in enriched if item["status"] == "failed"]
    required_missing = [
        item["name"] for item in enriched if item["status"] in ("missing", "failed") and not item["optional"]
    ]
    summary = {
        "total": len(enriched),
        "present": sum(1 for item in enriched if item["status"] == "present"),
        "downloaded": sum(1 for item in enriched if item["status"] == "downloaded"),
        "missing": sum(1 for item in enriched if item["status"] == "missing"),
        "failed": len(failed),
        "required_missing": required_missing,
        "optional_missing": [
            item["name"] for item in enriched if item["status"] == "missing" and item["optional"]
        ],
        "missing_bytes": missing_bytes,
        "free_bytes": free_bytes,
        "space_ok": space_ok,
        "auto_download": bool(auto_download),
        "ok": not failed and not required_missing,
    }
    return {
        "entries": enriched,
        "summary": summary,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def format_preflight_report(preflight: Dict[str, Any]) -> List[str]:
    """Human-readable lines for the node's text panel and the HTTP route."""
    summary = preflight.get("summary") or {}
    lines = [
        "MiniMax Music Production Toolkit - model preflight:",
        f"  artifacts: {summary.get('total', 0)} "
        f"(present {summary.get('present', 0)}, downloaded {summary.get('downloaded', 0)}, "
        f"missing {summary.get('missing', 0)}, failed {summary.get('failed', 0)})",
        f"  missing bytes: {summary.get('missing_bytes', 0)}",
        f"  free space: {summary.get('free_bytes') if summary.get('free_bytes') is not None else 'unknown'}",
    ]
    if summary.get("space_ok") is False:
        lines.append("  WARNING: not enough free space for the missing artifacts.")
    for name in summary.get("required_missing") or []:
        lines.append(f"  required and missing: {name}")
    for name in summary.get("optional_missing") or []:
        lines.append(f"  optional and missing (not downloaded automatically): {name}")
    return lines


def format_check_report(report: List[Dict[str, Any]]) -> str:
    """Render a human-readable multi-line report."""
    lines = ["MiniMax Music Production Toolkit – model check:"]
    for item in report:
        status = item["status"]
        marker = {"present": "OK ", "downloaded": "DL ", "missing": "-- ", "failed": "ERR"}[status]
        line = f"{marker} {item['name']}: {status}"
        if item["message"]:
            line += f" ({item['message']})"
        lines.append(line)
    return "\n".join(lines)
