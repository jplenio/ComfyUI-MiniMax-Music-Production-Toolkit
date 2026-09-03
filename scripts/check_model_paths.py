#!/usr/bin/env python3
"""Verify that the toolkit resolves model paths like the running ComfyUI does.

Reproduces the resolution used by a ComfyUI started with
``--models-directory "F:\\ComfyUI\\models"`` and prints where the toolkit would
look for FlashSR weights/code and llama.cpp GGUFs.  Exits non-zero when the
resolved paths do not live below ``folder_paths.models_dir``.

Usage (from any shell, pointing at a ComfyUI checkout and its venv Python):

    <venv-python> scripts/check_model_paths.py --comfy-dir D:/ComfyUI --models-directory F:/ComfyUI/models
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load_toolkit_modules() -> dict:
    pkg = types.ModuleType("_toolkit_paths_check")
    pkg.__path__ = [str(REPO)]
    sys.modules["_toolkit_paths_check"] = pkg
    modules = {}
    for module_name in ("toolkit_logging", "model_downloader", "llm_chat"):
        full = f"_toolkit_paths_check.{module_name}"
        spec = importlib.util.spec_from_file_location(full, REPO / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        modules[module_name] = module
    return modules


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-dir", required=True, help="path to the ComfyUI checkout")
    parser.add_argument("--models-directory", required=True, help="models directory passed to --models-directory")
    args = parser.parse_args()

    sys.argv = ["main.py", "--models-directory", args.models_directory]
    sys.path.insert(0, args.comfy_dir)
    os.chdir(args.comfy_dir)

    try:
        import comfy.options  # type: ignore
        comfy.options.args_parsing = True
        import comfy.cli_args  # type: ignore
        import folder_paths  # type: ignore
    except Exception as exc:
        print(f"Could not import ComfyUI from {args.comfy_dir}: {type(exc).__name__}: {exc}")
        return 1

    models_dir = Path(folder_paths.models_dir)
    print(f"folder_paths.models_dir = {models_dir}")
    print(f"folder_paths.base_path   = {folder_paths.base_path}")

    modules = load_toolkit_modules()
    downloader = modules["model_downloader"]
    llm_chat = modules["llm_chat"]

    flashsr_target = downloader.resolve_target("models/audio/flashsr")
    llm_directories = llm_chat._llm_directories()
    ggufs = llm_chat.list_llm_models()

    print(f"FlashSR weights/code   -> {flashsr_target}")
    print(f"LLM search directories -> {[str(p) for p in llm_directories]}")
    print(f"GGUF models found      -> {ggufs or 'none'}")

    ok = True
    try:
        flashsr_target.relative_to(models_dir)
    except ValueError:
        print(f"ERROR: FlashSR target {flashsr_target} is outside models_dir {models_dir}")
        ok = False
    if not any(str(models_dir / "llm") in str(directory) for directory in llm_directories):
        print(f"ERROR: no LLM directory below models_dir {models_dir}: {llm_directories}")
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
