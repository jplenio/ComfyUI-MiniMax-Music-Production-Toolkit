#!/usr/bin/env python3
"""Create deterministic GitHub release assets for this repository.

The archive intentionally excludes VCS state, Python caches, generated media,
and already-built release archives. It also copies the sanitized public example
workflow as a standalone versioned release asset and writes SHA-256 checksums.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIRNAME = "ComfyUI-MiniMax-Music-Production-Toolkit"
WORKFLOW_SOURCE = ROOT / "example_workflows" / "MiniMax_Music3_Production_Toolkit.json"

EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
# Local-only files that must never reach GitHub, the Comfy Registry or a release ZIP.
EXCLUDED_NAMES = {"KONTEXT.md", "PROJECT_STATE.md"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def should_include(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name in {"SHA256SUMS.txt"} or path.name in EXCLUDED_NAMES:
        return False
    if path.suffix.lower() in {".zip"}:
        return False
    return True


def run_validation() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_release.py")], cwd=ROOT, check=True)
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        check=True,
    )


def count_registered_nodes() -> int:
    """Count toolkit node classes by AST, without importing ComfyUI."""
    import ast
    names = set()
    for path in sorted(ROOT.glob("*.py")):
        if path.name == "__init__.py":
            continue  # __init__ only re-exports the module mappings
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=path.name)
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name) or target.id != "NODE_CLASS_MAPPINGS":
                    continue
                if isinstance(node.value, ast.Dict):
                    for key in node.value.keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            names.add(key.value)
            # Some modules extend the mapping: NODE_CLASS_MAPPINGS["X"] = X
            if isinstance(node.targets[0], ast.Subscript):
                target = node.targets[0]
                if isinstance(target.value, ast.Name) and target.value.id == "NODE_CLASS_MAPPINGS":
                    if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                        names.add(target.slice.value)
    return len(names)


def count_prompts() -> tuple[int, int]:
    user = len([p for p in (ROOT / "prompts" / "user").rglob("*") if p.is_file()])
    system = len([p for p in (ROOT / "prompts" / "system").rglob("*") if p.is_file()])
    return user, system


def count_demo_tracks() -> int:
    import json as _json
    import re as _re
    path = ROOT / "docs" / "demo-tracks.js"
    if not path.exists():
        return 0
    match = _re.search(r"window\.MINIMAX_DEMO_TRACKS\s*=\s*(\[.*\]);\s*$", path.read_text(encoding="utf-8"), _re.S)
    if not match:
        return -1
    try:
        return len(_json.loads(match.group(1)))
    except Exception:
        return -1


def privacy_scan_summary() -> list[str]:
    """Light privacy scan mirroring validate_release; returns offending files."""
    import re as _re
    patterns = [
        _re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"']+", _re.I),
        _re.compile(r"[A-Za-z]:/Users/[^/\s\"']+", _re.I),
        _re.compile(r"(?:192\.168\.|10\.\d+\.\d+\.|172\.(?:1[6-9]|2\d|3[01])\.)\d+\.\d+"),
        _re.compile("YOUR_" + "GITHUB_USERNAME|YOUR_" + "COMFY_PUBLISHER_ID"),
    ]
    text_extensions = {".py", ".js", ".md", ".txt", ".toml", ".json", ".yml", ".yaml", ".bat"}
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_extensions:
            continue
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in patterns:
            if pattern.search(text):
                hits.append(str(path.relative_to(ROOT)))
                break
    return hits


def print_dry_run_summary(version: str) -> None:
    """Print release contents summary without creating any assets."""
    import json as _json

    workflow_data = _json.loads(WORKFLOW_SOURCE.read_text(encoding="utf-8"))
    user_prompts, system_prompts = count_prompts()
    local_only = [name for name in EXCLUDED_NAMES if (ROOT / name).exists()]
    privacy_hits = privacy_scan_summary()
    included_files = [p for p in ROOT.rglob("*") if p.is_file() and should_include(p)]

    print("Release dry-run summary (no assets written)")
    print(f"  version:          {version}")
    print(f"  registered nodes: {count_registered_nodes()}")
    print(f"  user prompts:     {user_prompts}")
    print(f"  system prompts:   {system_prompts}")
    print(f"  demo tracks:      {count_demo_tracks()}")
    print(f"  workflow nodes:   {len(workflow_data.get('nodes', []))}")
    print(f"  workflow links:   {len(workflow_data.get('links', []))}")
    print(f"  workflow rev:     {workflow_data.get('revision')}")
    print(f"  files in zip:     {len(included_files)}")
    print(f"  local-only files: {', '.join(local_only) or 'none'} (excluded from the ZIP)")
    print(f"  privacy scan:     {'CLEAN' if not privacy_hits else 'HITS: ' + ', '.join(privacy_hits)}")
    print(f"  planned assets:   {PROJECT_DIRNAME}-v{version}.zip, MiniMax_Music3_Production_Toolkit_v{version}.json, SHA256SUMS.txt")



def create_zip(output: Path) -> None:
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and should_include(p))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            rel = path.relative_to(ROOT)
            arcname = Path(PROJECT_DIRNAME) / rel
            data = path.read_bytes()
            info = zipfile.ZipInfo(str(arcname).replace(os.sep, "/"))
            # Stable timestamp so identical source content creates reproducible ZIP metadata.
            info.date_time = (2026, 9, 1, 12, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent)
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print a release contents summary without creating assets.")
    args = parser.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit("VERSION is empty")
    if not WORKFLOW_SOURCE.exists():
        raise SystemExit(f"Missing public workflow: {WORKFLOW_SOURCE}")

    if args.dry_run:
        print_dry_run_summary(version)
        return

    if not args.skip_validation:
        run_validation()

    outdir = args.output_dir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    archive = outdir / f"{PROJECT_DIRNAME}-v{version}.zip"
    workflow = outdir / f"MiniMax_Music3_Production_Toolkit_v{version}.json"
    checksums = outdir / "SHA256SUMS.txt"

    if archive.exists():
        archive.unlink()
    create_zip(archive)
    shutil.copyfile(WORKFLOW_SOURCE, workflow)

    assets = [archive, workflow]
    checksum_text = "".join(f"{sha256(p)}  {p.name}\n" for p in assets)
    checksums.write_text(checksum_text, encoding="utf-8", newline="\n")

    print(f"Created: {archive}")
    print(f"Created: {workflow}")
    print(f"Created: {checksums}")
    print(checksum_text, end="")


if __name__ == "__main__":
    main()
