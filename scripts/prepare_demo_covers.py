#!/usr/bin/env python3
"""Prepare all cover images referenced by docs/demo-tracks.js.

Usage:
  python scripts/prepare_demo_covers.py --source "D:/path/to/generated/artwork"

The expected output names are read dynamically from the demo catalog, so this
helper does not need a code change whenever demo tracks are added. It searches
recursively for source images by the requested output stem, center-crops them to
a square, resizes to 960x960 by default, and writes progressive JPEGs to
`docs/assets/demo-covers/`.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
DEMO_JS = ROOT / "docs" / "demo-tracks.js"


def expected_names() -> list[str]:
    text = DEMO_JS.read_text(encoding="utf-8")
    match = re.search(r"window\.MINIMAX_DEMO_TRACKS\s*=\s*(\[.*\]);\s*$", text, re.S)
    if not match:
        raise SystemExit(f"Could not parse {DEMO_JS}")
    tracks = json.loads(match.group(1))
    names = []
    for track in tracks:
        cover = str(track.get("cover") or "").strip()
        if cover:
            names.append(Path(cover).name)
    return list(dict.fromkeys(names))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--size", type=int, default=960)
    ap.add_argument("--quality", type=int, default=86)
    args = ap.parse_args()

    source = args.source.expanduser().resolve()
    dest = ROOT / "docs" / "assets" / "demo-covers"
    dest.mkdir(parents=True, exist_ok=True)
    candidates: dict[str, Path] = {}
    for path in source.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            candidates.setdefault(path.stem.casefold(), path)

    missing = []
    for out_name in expected_names():
        stem = Path(out_name).stem.casefold()
        src = candidates.get(stem)
        if not src:
            missing.append(out_name)
            continue
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im = ImageOps.fit(im, (args.size, args.size), method=Image.Resampling.LANCZOS)
            im.save(dest / out_name, "JPEG", quality=args.quality, optimize=True, progressive=True)
            print(f"OK  {src.name} -> {out_name}")

    if missing:
        print("\nMissing covers:")
        for name in missing:
            print(" -", name)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
