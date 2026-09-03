#!/usr/bin/env python3
"""Preview the exact output paths a production run would write.

Non-writing collision check for the standard example-workflow layout
(32 kHz FLAC, 44 kHz FLAC, 44 kHz MP3, cover JPG, production JSON).  The
preview mirrors the real naming pipeline: ComfyUI output-directory resolution,
date macros, the shared ``album - title`` basename convention and the
``auto_increment`` / ``overwrite`` / ``error_if_exists`` collision modes.

Usage:
    python scripts/preview_output_paths.py --album "My Album" --title "My Song"
    python scripts/preview_output_paths.py --album "My Album" --title "My Song" --base-output "audio/minimax3/" --collision-mode error_if_exists --fail-on-collision
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Standard example-workflow layout (MiniMaxOutputPaths subdirs).
DEFAULT_SUBDIRS = ("32flac", "44flac", "44mp3", "artwork", "json")
DEFAULT_FORMATS = ("flac", "flac", "mp3", "jpg", "json")
DEFAULT_BASE_OUTPUT = "audio/minimax3/%date:yyyy-MM-dd%/Example Album/"


def _load_saver_module():
    """Load save_audio_smart_prefix as a synthetic package (no ComfyUI import)."""
    import importlib.util
    import types

    pkg_name = "_minimax_preview_paths_pkg"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    for dependency in ("filename_utils", "toolkit_logging"):
        full = f"{pkg_name}.{dependency}"
        if full in sys.modules:
            continue
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{dependency}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
    full = f"{pkg_name}.save_audio_smart_prefix"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, ROOT / "save_audio_smart_prefix.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def preview_all(
    album: str,
    title: str,
    base_output: str = DEFAULT_BASE_OUTPUT,
    collision_mode: str = "auto_increment",
    filename_mode: str = "album - title",
) -> list[dict]:
    """Return one preview entry per planned output file, nothing written."""
    saver = _load_saver_module()
    preview_output_files = saver.preview_output_files

    tags_meta = {"album": album, "title": title}
    base_output = base_output.rstrip("/\\")
    entries = []
    for subdir, ext in zip(DEFAULT_SUBDIRS, DEFAULT_FORMATS):
        prefix = f"{base_output}/{subdir}/" if base_output else f"{subdir}/"
        entry = preview_output_files(
            prefix, ext, collision_mode=collision_mode, filename_mode=filename_mode,
            tags_meta=tags_meta, title=title,
        )
        entry["subdir"] = subdir
        entries.append(entry)
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--album", required=True, help="Album tag used for the 'album - title' basename.")
    parser.add_argument("--title", required=True, help="Song title used for the 'album - title' basename.")
    parser.add_argument("--base-output", default=DEFAULT_BASE_OUTPUT, help="Base output prefix (relative to the ComfyUI output dir, or absolute).")
    parser.add_argument("--collision-mode", default="auto_increment", choices=["auto_increment", "overwrite", "error_if_exists"])
    parser.add_argument("--filename-mode", default="album - title", choices=["album - title", "title only", "prefix as provided"])
    parser.add_argument("--fail-on-collision", action="store_true", help="Exit 1 when any planned path already exists.")
    args = parser.parse_args()

    entries = preview_all(
        args.album, args.title, args.base_output, args.collision_mode, args.filename_mode
    )

    collisions = 0
    print("Planned output files (nothing was written):")
    for entry in entries:
        status = "EXISTS" if entry["exists"] else "OK"
        if entry["would_raise"]:
            status = "WOULD RAISE (error_if_exists)"
        if entry["exists"] or entry["would_raise"]:
            collisions += 1
        print(f"  [{status:24s}] {entry['subdir']:10s} {entry['path'] or '(no path – collision)'}")
    print(f"\nCollisions: {collisions} of {len(entries)} paths.")

    if collisions and args.collision_mode == "error_if_exists":
        print("The run would fail with FileExistsError. Pick another Album/Title or use auto_increment.")
    if args.fail_on_collision and collisions:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
