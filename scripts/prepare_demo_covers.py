#!/usr/bin/env python3
"""Prepare the cover images referenced by the demo catalogs.

Usage:
  python scripts/prepare_demo_covers.py --source "D:/path/to/generated/artwork"

The expected output names are read dynamically from ``docs/demo-tracks.js`` and
``docs/demo-covers.js``, so this helper does not need a code change whenever demo
tracks or covers are added. It searches recursively for source images by the
requested output stem, center-crops them to a square, resizes to 960x960 by
default, and writes progressive JPEGs to ``docs/assets/demo-covers/``.

An image that is already prepared is skipped, so a second run for a new batch does
not need the artwork of the earlier ones. Pass ``--force`` to prepare everything
again.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
DEMO_JS = ROOT / "docs" / "demo-tracks.js"
COVER_JS = ROOT / "docs" / "demo-covers.js"


def expected_names() -> list[str]:
    names: list[str] = []
    text = DEMO_JS.read_text(encoding="utf-8")
    match = re.search(r"window\.MINIMAX_DEMO_TRACKS\s*=\s*(\[.*\]);\s*$", text, re.S)
    if not match:
        raise SystemExit(f"Could not parse {DEMO_JS}")
    for track in json.loads(match.group(1)):
        cover = str(track.get("cover") or "").strip()
        if cover:
            names.append(Path(cover).name)

    if COVER_JS.exists():
        cover_text = COVER_JS.read_text(encoding="utf-8")
        groups_match = re.search(r"window\.DEMO_COVER_GROUPS\s*=\s*(\[.*\]);\s*$", cover_text, re.S)
        if not groups_match:
            raise SystemExit(f"Could not parse {COVER_JS}")
        for group in json.loads(groups_match.group(1)):
            for item in group.get("covers", []):
                art = str(item.get("coverArt") or "").strip()
                if art:
                    names.append(Path(art).name)
    return list(dict.fromkeys(names))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--size", type=int, default=960)
    ap.add_argument("--quality", type=int, default=86)
    ap.add_argument("--force", action="store_true",
                    help="Prepare images that already exist in the destination.")
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
        if (dest / out_name).exists() and not args.force:
            continue
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
