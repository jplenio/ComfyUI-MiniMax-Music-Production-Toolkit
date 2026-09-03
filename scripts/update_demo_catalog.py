#!/usr/bin/env python3
"""Update the GitHub Pages demo catalog from production metadata JSON files.

The script deliberately extracts only public demo fields from the production JSON.
It preserves existing SoundCloud URLs and playlist configuration when a track is
updated, and it never copies the long LLM system prompt, raw LLM response, or
machine-specific output paths into docs/demo-tracks.js.

Examples:
  python scripts/update_demo_catalog.py "D:/exports/json/*.json" --cover-source "D:/exports/artwork"
  python scripts/update_demo_catalog.py D:/exports/json --cover-source D:/exports/artwork --dry-run

Metadata arguments may be files, directories, or glob patterns. Cover matching
looks for the JSON stem, "Album - Title", and "Title" in the supplied cover
source directory/directories. Existing demo cover paths are preserved when an
updated track already exists.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import shutil
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS = ROOT / "docs"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _slugify(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "track"


def _read_demo_js(path: Path) -> tuple[dict, list[dict]]:
    text = path.read_text(encoding="utf-8")
    cfg_match = re.search(
        r"window\.MINIMAX_DEMO_CONFIG\s*=\s*(\{.*?\});\s*window\.MINIMAX_DEMO_TRACKS",
        text,
        re.S,
    )
    tracks_match = re.search(r"window\.MINIMAX_DEMO_TRACKS\s*=\s*(\[.*\]);\s*$", text, re.S)
    if not cfg_match or not tracks_match:
        raise ValueError(f"Could not parse {path}; expected MINIMAX_DEMO_CONFIG and MINIMAX_DEMO_TRACKS assignments")
    return json.loads(cfg_match.group(1)), json.loads(tracks_match.group(1))


def _write_demo_js(path: Path, config: dict, tracks: list[dict]) -> None:
    header = """// MiniMax Music Production Toolkit — public demo configuration
//
// HOW TO ADD SOUNDCLOUD LINKS:
// 1. Upload the track to SoundCloud and make it publicly playable.
// 2. Paste the NORMAL SoundCloud track URL into soundcloudUrl below.
// 3. Commit this file. No iframe code is required.
//
// This file can also be maintained with scripts/update_demo_catalog.py.
// That helper intentionally copies only public demo fields from production JSON.
//
"""
    text = (
        header
        + "window.MINIMAX_DEMO_CONFIG = "
        + json.dumps(config, ensure_ascii=False, indent=2)
        + ";\n\nwindow.MINIMAX_DEMO_TRACKS = "
        + json.dumps(tracks, ensure_ascii=False, indent=2)
        + ";\n"
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def _expand_metadata_args(values: Iterable[str]) -> list[Path]:
    found: list[Path] = []
    for raw in values:
        expanded = glob.glob(raw)
        candidates = [Path(p) for p in expanded] if expanded else [Path(raw)]
        for candidate in candidates:
            if candidate.is_dir():
                found.extend(sorted(candidate.glob("*.json")))
            elif candidate.is_file() and candidate.suffix.lower() == ".json":
                found.append(candidate)
    # preserve order while de-duplicating
    return list(dict.fromkeys(p.resolve() for p in found))


def _caption_fields(caption: str) -> dict:
    flat = " ".join((caption or "").replace("\n", " ").split())
    out = {"bpm": "", "key": "", "scale": "", "style": "", "description": ""}
    m = re.search(r"bpm is\s*([0-9]+(?:\.[0-9]+)?)", flat, re.I)
    if m:
        value = float(m.group(1))
        out["bpm"] = int(value) if value.is_integer() else value
    m = re.search(
        r"key is\s*(.+?),\s*and scale is\s*(.+?)\.\s*(.*?)\s*Global Emotional Progression:\s*(.*?)(?:\s+Sound Profile:|\s+Vocal Details:|\s+Arrangement:|$)",
        flat,
        re.I | re.S,
    )
    if m:
        out["key"] = m.group(1).strip()
        out["scale"] = m.group(2).strip()
        out["style"] = m.group(3).strip().rstrip(".")
        emotional = m.group(4).strip()
        sentences = re.split(r"(?<=[.!?])\s+", emotional)
        description = " ".join(sentences[:2]).strip()
        out["description"] = description[:417].rstrip() + "…" if len(description) > 420 else description
    return out


def _track_type(lyrics: str) -> str:
    residue = re.sub(r"\[[^\]]+\]", "", lyrics or "").replace("/", " ")
    return "Instrumental" if not re.sub(r"\s+", " ", residue).strip() else "Vocal"


def _language(track_type: str, prompt: str, lyrics: str) -> str:
    if track_type == "Instrumental":
        return "—"
    text = f"{prompt} {lyrics}".lower()
    if re.search(r"\b(deutsch|german|und|der|die|das|nicht|ich|du|wir)\b", text):
        return "German"
    return "English"


def _humanize_slug(value: str) -> str:
    if not value or "-" not in value or " " in value:
        return value
    replacements = {
        "drum-and-bass": "Drum & Bass",
        "liquid-drum-and-bass": "Liquid Drum & Bass",
        "future-rave": "Future Rave",
        "hardgroove-techno": "Hardgroove Techno",
        "breakbeat": "Breakbeat",
        "sparse-vocals": "Sparse Vocals",
        "instrumental": "Instrumental",
    }
    result = value
    for src, dst in sorted(replacements.items(), key=lambda item: -len(item[0])):
        result = result.replace(src, dst)
    result = result.replace("-", " ")
    return " ".join(result.split())


def _genre_for_public(tags_genre: str, style: str) -> str:
    if tags_genre and not ("-" in tags_genre and " " not in tags_genre):
        return tags_genre
    if style:
        return style.split(" / ", 1)[0].strip()
    return _humanize_slug(tags_genre)


def _metadata_key(track: dict) -> tuple[str, str, str]:
    return (str(track.get("album", "")), str(track.get("title", "")), str(track.get("seed", "")))


def _cover_index(sources: Iterable[Path]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for root in sources:
        root = root.expanduser().resolve()
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                result.setdefault(path.stem.casefold(), path)
    return result


def _choose_cover(metadata_path: Path, album: str, title: str, index: dict[str, Path]) -> Path | None:
    for stem in (metadata_path.stem, f"{album} - {title}", title):
        hit = index.get(stem.casefold())
        if hit:
            return hit
    return None


def _public_track(metadata_path: Path, data: dict, existing: dict | None, used_ids: set[str], order: int) -> dict:
    tags = data.get("standard_audio_tags") or {}
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError(f"{metadata_path.name}: missing title")
    raw_album = str(tags.get("album") or data.get("source", {}).get("name") or "Demo").strip()
    album = _humanize_slug(raw_album)
    prompt = str(data.get("source", {}).get("prompt_provenance", {}).get("user_prompt") or "").strip()
    lyrics = str(data.get("lyrics") or "")
    caption = _caption_fields(str(data.get("caption") or ""))
    kind = _track_type(lyrics)
    seed = data.get("generation_seed", "")
    genre = _genre_for_public(str(tags.get("genre") or "").strip(), caption["style"])

    base_id = _slugify(f"{raw_album}-{title}")
    track_id = str(existing.get("id")) if existing and existing.get("id") else base_id
    if track_id in used_ids and not existing:
        seed_suffix = str(seed)[-6:] if str(seed) else "2"
        track_id = f"{base_id}-{seed_suffix}"
        counter = 2
        while track_id in used_ids:
            track_id = f"{base_id}-{seed_suffix}-{counter}"
            counter += 1
    used_ids.add(track_id)

    mm = data.get("minimax_music3") or {}
    te = mm.get("text_encode") or {}
    ks = mm.get("ksampler") or {}
    release = data.get("release_prep") or {}

    return {
        "id": track_id,
        "showcaseOrder": existing.get("showcaseOrder", order) if existing else order,
        "title": title,
        "artist": str(tags.get("artist") or "Pelenio"),
        "album": album,
        "genre": genre,
        "style": caption["style"],
        "type": kind,
        "language": _language(kind, prompt, lyrics),
        "bpm": caption["bpm"],
        "key": caption["key"],
        "scale": caption["scale"],
        "description": caption["description"],
        "startingPrompt": prompt,
        "sourceName": str(data.get("source", {}).get("name") or raw_album),
        "seed": seed,
        "maxDurationSeconds": mm.get("max_duration", ""),
        "textCfg": te.get("cfg_scale", ""),
        "textTopK": te.get("top_k", ""),
        "steps": ks.get("steps", ""),
        "samplerCfg": ks.get("cfg", ""),
        "sampler": ks.get("sampler_name", ks.get("sampler", "")),
        "scheduler": ks.get("scheduler", ""),
        "denoise": ks.get("denoise", ""),
        "coverConcept": str(data.get("image_prompt") or ""),
        "vocalDetails": existing.get("vocalDetails", "n/a" if kind == "Instrumental" else "Vocals") if existing else ("n/a" if kind == "Instrumental" else "Vocals"),
        "release": {
            "sampleRate": release.get("output_sample_rate", ""),
            "targetLufs": release.get("target_lufs", ""),
            "targetTruePeakDbtp": release.get("target_true_peak_dbtp", ""),
            "processing": release.get("processing", ""),
        },
        "cover": existing.get("cover", "") if existing else "",
        "soundcloudUrl": existing.get("soundcloudUrl", "") if existing else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", nargs="+", help="JSON file, directory, or glob pattern")
    parser.add_argument("--cover-source", action="append", default=[], type=Path, help="Directory containing generated JPG/PNG/WEBP covers; may be repeated")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    metadata_paths = _expand_metadata_args(args.metadata)
    if not metadata_paths:
        raise SystemExit("No production metadata JSON files found")

    docs_dir = args.docs_dir.expanduser().resolve()
    demo_js = docs_dir / "demo-tracks.js"
    if not demo_js.exists():
        raise SystemExit(f"Missing {demo_js}")

    config, tracks = _read_demo_js(demo_js)
    existing_by_key = {_metadata_key(track): track for track in tracks}
    used_ids = {str(t.get("id")) for t in tracks if t.get("id")}
    next_order = max((int(t.get("showcaseOrder", 0) or 0) for t in tracks), default=0) + 1
    covers = _cover_index(args.cover_source)
    cover_dest = docs_dir / "assets" / "demo-covers"
    cover_dest.mkdir(parents=True, exist_ok=True)

    updated = 0
    added = 0
    for path in metadata_paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        tags = data.get("standard_audio_tags") or {}
        raw_album = str(tags.get("album") or data.get("source", {}).get("name") or "Demo").strip()
        title = str(data.get("title") or "").strip()
        seed = str(data.get("generation_seed", ""))
        # Match existing with both display and raw album for older/newer catalog conventions.
        existing = next(
            (
                t for t in tracks
                if str(t.get("title")) == title
                and str(t.get("seed", "")) == seed
                and str(t.get("album", "")) in {raw_album, _humanize_slug(raw_album)}
            ),
            None,
        )
        public = _public_track(path, data, existing, used_ids, next_order)
        if existing:
            index = tracks.index(existing)
            tracks[index] = public
            updated += 1
        else:
            tracks.append(public)
            added += 1
            next_order += 1

        hit = _choose_cover(path, raw_album, title, covers)
        if hit:
            # Preserve an existing public cover basename where possible; otherwise use source stem.
            filename = Path(public.get("cover") or "").name or f"{path.stem}.jpg"
            if not filename.lower().endswith(".jpg"):
                filename = Path(filename).with_suffix(".jpg").name
            target = cover_dest / filename
            if not args.dry_run:
                from PIL import Image, ImageOps
                with Image.open(hit) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    im = ImageOps.fit(im, (960, 960), method=Image.Resampling.LANCZOS)
                    im.save(target, "JPEG", quality=86, optimize=True, progressive=True)
            public["cover"] = f"assets/demo-covers/{filename}"

    tracks.sort(key=lambda t: (int(t.get("showcaseOrder", 999999) or 999999), str(t.get("title", ""))))
    if args.dry_run:
        print(f"Dry run: {updated} update(s), {added} addition(s); catalog would contain {len(tracks)} tracks")
        return
    _write_demo_js(demo_js, config, tracks)
    print(f"Updated {demo_js}: {updated} update(s), {added} addition(s), {len(tracks)} total tracks")


if __name__ == "__main__":
    main()
