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
    if path.name in {"SHA256SUMS.txt"}:
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


def create_zip(output: Path) -> None:
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and should_include(p))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            rel = path.relative_to(ROOT)
            arcname = Path(PROJECT_DIRNAME) / rel
            data = path.read_bytes()
            info = zipfile.ZipInfo(str(arcname).replace(os.sep, "/"))
            # Stable timestamp so identical source content creates reproducible ZIP metadata.
            info.date_time = (2026, 8, 31, 12, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent)
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit("VERSION is empty")
    if not WORKFLOW_SOURCE.exists():
        raise SystemExit(f"Missing public workflow: {WORKFLOW_SOURCE}")

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
