#!/usr/bin/env python3
"""Prepare demo cover art for GitHub Pages.

Usage:
  python scripts/prepare_demo_covers.py --source "D:/path/to/generated/artwork"

The script searches recursively for the expected cover names as JPG/JPEG/PNG/WEBP,
center-crops them to a square, resizes to 960x960, and writes JPEGs to
docs/assets/demo-covers/. Existing output files are replaced.
"""
from pathlib import Path
from PIL import Image, ImageOps
import argparse

EXPECTED = ['Strange Horizons - The Amber Frame.jpg', 'Beyond the Known - The Long Resonance.jpg', 'After Midnight - Piano in the Low Light.jpg', 'Places We Left Behind - The Light Was Different.jpg', 'Groove Theory - Pocket City.jpg', 'Celtic Folk - lyrics - A Name on the Dark.jpg', 'Neon Memories - Violet Static.jpg', 'Wir waren analog - Freigabe.jpg', 'Between Earth and Sky - The Long Afternoon.jpg', 'Echoes Of Tomorrow - Where the Melody Rests.jpg', 'Strange Horizons - The Long Way Back.jpg', 'Beyond the Known - The Frequency of Dusk.jpg', 'Wir waren analog - Vergeben.jpg', 'Strange Horizons - The Slow Meridian.jpg', 'Beyond the Known - Beneath the Meridian.jpg', 'Strange Horizons - Marrow.jpg', 'Beyond the Known - The Shape of Returning.jpg']

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',required=True,type=Path)
    ap.add_argument('--size',type=int,default=960)
    ap.add_argument('--quality',type=int,default=86)
    args=ap.parse_args()
    source=args.source.expanduser().resolve()
    dest=Path(__file__).resolve().parents[1]/'docs'/'assets'/'demo-covers'
    dest.mkdir(parents=True,exist_ok=True)
    candidates={}
    for p in source.rglob('*'):
        if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.webp'}:
            candidates.setdefault(p.stem.lower(),p)
    missing=[]
    for out_name in EXPECTED:
        stem=Path(out_name).stem.lower()
        src=candidates.get(stem)
        if not src:
            missing.append(out_name); continue
        with Image.open(src) as im:
            im=ImageOps.exif_transpose(im).convert('RGB')
            im=ImageOps.fit(im,(args.size,args.size),method=Image.Resampling.LANCZOS)
            im.save(dest/out_name,'JPEG',quality=args.quality,optimize=True,progressive=True)
            print(f'OK  {src.name} -> {out_name}')
    if missing:
        print('\nMissing covers:')
        for name in missing: print(' -',name)
        raise SystemExit(1)

if __name__=='__main__': main()
