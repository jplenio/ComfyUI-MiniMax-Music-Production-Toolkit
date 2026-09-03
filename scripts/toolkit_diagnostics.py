#!/usr/bin/env python3
"""Toolkit self-diagnostics report.

Checks the local environment and model inventory without generating anything:
Python interpreter, FFmpeg, required Python packages, the LLM stack
(llama.cpp / GGUF models), the models_config.json targets (resolved against
the ComfyUI models directory, honoring --models-directory) and the bundled
prompt library.  Prints a readable report and exits non-zero when hard
requirements are missing.

Usage:
    python scripts/toolkit_diagnostics.py [--comfy-dir D:/path/to/ComfyUI] [--models-directory F:/ComfyUI/models] [--quiet]

This script does not import ComfyUI itself; when a --comfy-dir is given the
checks that need folder_paths run inside that checkout's Python via subprocess.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PACKAGES = ("numpy", "scipy", "soundfile", "mutagen", "PIL", "torch", "safetensors", "tokenizers", "llama_cpp")

PROMPT_LIBRARY_HINT = "Loads prompts from prompts/user and prompts/system."


def _load_module(module_name: str):
    """Load one toolkit module under a synthetic package (no ComfyUI import)."""
    import importlib.util
    import types

    pkg_name = "_minimax_diagnostics_pkg"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    full = f"{pkg_name}.{module_name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _check_packages() -> list[tuple[str, bool, str]]:
    results = []
    for name in PACKAGES:
        try:
            module = __import__(name)
            version = getattr(module, "__version__", "") or getattr(module, "VERSION", "") or ""
            results.append((name, True, str(version)))
        except Exception as exc:  # pragma: no cover - defensive diagnostics
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
    return results


def _check_ffmpeg() -> tuple[bool, str]:
    exe = shutil.which("ffmpeg")
    if exe:
        try:
            proc = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=20)
            first_line = proc.stdout.splitlines()[0] if proc.stdout else "?"
            return True, f"{exe} ({first_line})"
        except Exception as exc:  # pragma: no cover - defensive diagnostics
            return False, f"found {exe} but could not run it: {exc}"
    return False, "ffmpeg not found on PATH (MP3 saving needs it; run install_requirements.bat)"


def _check_models(auto_download: bool = False) -> list[dict]:
    try:
        model_downloader = _load_module("model_downloader")
        config = model_downloader.load_models_config()
        entries = []
        for group in ("minimax", "flux2"):
            entries.extend(config.get(group, {}).get("files", []))
        entries.extend(config.get("flashsr", {}).get("weights", {}).get("files", []))
        llm_example = config.get("llm", {}).get("example")
        if isinstance(llm_example, dict):
            entries.append(llm_example)
        return model_downloader.check_file_entries(entries, auto_download=auto_download)
    except Exception as exc:  # pragma: no cover - defensive diagnostics
        return [{"name": "<config error>", "target": "", "status": "failed", "message": f"{type(exc).__name__}: {exc}"}]


def _check_llm() -> dict:
    try:
        llm_chat = _load_module("llm_chat")
        return llm_chat.collect_llm_diagnostics()
    except Exception as exc:  # pragma: no cover - defensive diagnostics
        return {"llm_diagnostics_error": f"{type(exc).__name__}: {exc}"}


def _check_prompt_library() -> dict:
    try:
        prompt_library = _load_module("prompt_library")
        user = prompt_library.list_prompt_files("user", "bundled_library")
        system = prompt_library.list_prompt_files("system", "bundled_library")
        return {"user_prompts": len(user), "system_prompts": len(system)}
    except Exception as exc:  # pragma: no cover - defensive diagnostics
        return {"prompt_library_error": f"{type(exc).__name__}: {exc}"}


def run_diagnostics(comfy_dir: str | None = None, models_directory: str | None = None) -> dict:
    """Collect all diagnostics into one report dict."""
    report: dict = {}
    report["python"] = sys.version.split()[0]
    report["python_executable"] = sys.executable
    if "folder_paths" in sys.modules:
        report["comfy_dir"] = "(running inside ComfyUI)"
    else:
        report["comfy_dir"] = comfy_dir or "(not detected)"
    report["ffmpeg"] = _check_ffmpeg()
    report["packages"] = {name: {"ok": ok, "version": version} for name, ok, version in _check_packages()}

    # Model/LLM checks resolve targets against folder_paths.models_dir when
    # running inside ComfyUI; outside ComfyUI, --models-directory is honored
    # via the COMFYUI_MODELS_DIRECTORY environment variable.
    if models_directory:
        os.environ["COMFYUI_MODELS_DIRECTORY"] = models_directory
    report["llm"] = _check_llm()
    report["models"] = _check_models(auto_download=False)
    report["prompt_library"] = _check_prompt_library()
    report["ok"] = (
        report["ffmpeg"][0]
        and all(item["ok"] for item in report["packages"].values())
        and not any(item["status"] == "failed" for item in report["models"])
    )
    return report


def format_report(report: dict) -> str:
    lines = ["MiniMax Music Production Toolkit – diagnostics"]
    lines.append(f"Python:  {report['python']} ({report['python_executable']})")
    lines.append(f"ComfyUI: {report['comfy_dir']}")
    ok, detail = report["ffmpeg"]
    lines.append(f"FFmpeg:  {'OK  ' if ok else 'MISS'} {detail}")
    lines.append("Python packages:")
    for name, info in sorted(report["packages"].items()):
        marker = "OK  " if info["ok"] else "MISS"
        lines.append(f"  {marker} {name} {info['version'] or ''}".rstrip())
    lines.append("LLM stack:")
    for key in sorted(report["llm"]):
        lines.append(f"  {key}: {report['llm'][key]}")
    lines.append("Models (models_config.json, resolved against the ComfyUI models directory):")
    for item in report["models"]:
        marker = {"present": "OK  ", "downloaded": "DL  ", "missing": "--  ", "failed": "ERR "}.get(item["status"], "?   ")
        line = f"  {marker} {item['name']}: {item['status']}"
        if item.get("message"):
            line += f" ({item['message']})"
        if item.get("target"):
            line += f" -> {item['target']}"
        lines.append(line)
    lines.append("Prompt library:")
    for key in sorted(report["prompt_library"]):
        lines.append(f"  {key}: {report['prompt_library'][key]}")
    lines.append("")
    lines.append("Overall: " + ("OK - all hard requirements present." if report["ok"] else "PROBLEMS FOUND (see above)."))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-dir", type=str, default=None, help="ComfyUI checkout directory (informational).")
    parser.add_argument("--models-directory", type=str, default=None, help="Override the ComfyUI models directory (e.g. F:/ComfyUI/models).")
    parser.add_argument("--quiet", action="store_true", help="Print only the overall verdict.")
    args = parser.parse_args()

    report = run_diagnostics(args.comfy_dir, args.models_directory)
    if args.quiet:
        print("OK" if report["ok"] else "PROBLEMS FOUND")
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
