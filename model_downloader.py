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
import json
import os
import threading
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.request import Request, urlopen

from .toolkit_logging import get_logger

LOGGER = get_logger("model_downloader")

CONFIG_PATH = Path(__file__).resolve().parent / "models_config.json"
_DOWNLOAD_LOCK = threading.Lock()
_TMP_SUFFIX = ".part"


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


def _verify_sha256(path: Path, expected: Optional[str]) -> bool:
    if not expected:
        return True
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower() == expected.strip().lower()


def _file_is_ready(path: Path, expected_sha256: Optional[str] = None, min_bytes: int = 1) -> bool:
    if not path.is_file() or path.stat().st_size < min_bytes:
        return False
    return _verify_sha256(path, expected_sha256)


def download_file(
    url: str,
    destination: Path,
    headers: Optional[Dict[str, str]] = None,
    sha256: Optional[str] = None,
    timeout: int = 300,
) -> Path:
    """Stream a URL to ``destination`` atomically, logging progress.

    Returns the destination path.  Raises on HTTP or checksum failure.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _file_is_ready(destination, sha256):
        LOGGER.info("Model file already present: %s", destination)
        return destination

    with _DOWNLOAD_LOCK:
        if _file_is_ready(destination, sha256):
            return destination
        tmp = destination.with_name(destination.name + _TMP_SUFFIX)
        LOGGER.info("Model download: %s -> %s", url, destination)
        request = Request(url, headers=headers or {"User-Agent": "ComfyUI-MiniMax-Music-Production-Toolkit"})
        last_log = 0.0
        downloaded = 0
        with urlopen(request, timeout=timeout) as response:
            total = int(response.headers.get("Content-Length") or 0)
            with tmp.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    import time
                    now = time.monotonic()
                    if total and (now - last_log >= 10.0 or downloaded == total):
                        LOGGER.info(
                            "Model download progress: %s %.1f%% (%.1f / %.1f MB)",
                            destination.name,
                            100.0 * downloaded / total,
                            downloaded / 1e6,
                            total / 1e6,
                        )
                        last_log = now
        if sha256 and not _verify_sha256(tmp, sha256):
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"SHA256 mismatch after download: {destination.name}")
        os.replace(tmp, destination)
        LOGGER.info("Model download finished: %s (%.1f MB)", destination, destination.stat().st_size / 1e6)
        return destination


def download_and_extract_zip(
    url: str,
    destination_dir: Path,
    strip_top_dir: bool = True,
    sha256: Optional[str] = None,
) -> Path:
    """Download a GitHub-style source ZIP and extract it into ``destination_dir``."""
    destination_dir = Path(destination_dir)
    marker = destination_dir / ".minimax_download_ok"
    if destination_dir.is_dir() and marker.is_file():
        return destination_dir

    with _DOWNLOAD_LOCK:
        if destination_dir.is_dir() and marker.is_file():
            return destination_dir
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        tmp_zip = destination_dir.with_name(destination_dir.name + ".zip.part")
        LOGGER.info("Model code download: %s -> %s", url, destination_dir)
        request = Request(url, headers={"User-Agent": "ComfyUI-MiniMax-Music-Production-Toolkit"})
        with urlopen(request, timeout=300) as response:
            tmp_zip.write_bytes(response.read())
        if sha256 and not _verify_sha256(tmp_zip, sha256):
            tmp_zip.unlink(missing_ok=True)
            raise RuntimeError(f"SHA256 mismatch after zip download: {destination_dir.name}")
        destination_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp_zip) as zf:
            for member in zf.namelist():
                parts = Path(member).parts
                if strip_top_dir and len(parts) > 1:
                    parts = parts[1:]
                if not parts or any(p in {"..", ""} for p in parts):
                    continue
                target = destination_dir.joinpath(*parts)
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
        tmp_zip.unlink(missing_ok=True)
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
        url = entry.get("url", "")
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
            if _file_is_ready(destination, entry.get("sha256")):
                status = "present"
            elif url and auto_download:
                download_file(
                    url,
                    destination,
                    headers=_hf_headers(entry),
                    sha256=entry.get("sha256"),
                    timeout=int(entry.get("timeout", 1800)),
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
