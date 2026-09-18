#!/usr/bin/env python3
"""Build the cover-song part of the GitHub Pages demo from production JSON files.

The demo page shows two categories: the generated songs (see
``scripts/update_demo_catalog.py``) and the cover songs. For covers the page is
organised the other way round: one **original track**, and the covers made from it
underneath. That grouping is what this script produces.

Usage:
  python scripts/update_cover_demo_catalog.py --source "D:/exports/Cover-Demos-github"

The result is written to ``docs/demo-covers.js``, which ``docs/index.html`` loads next
to the generated-song catalog ``docs/demo-tracks.js``.

``--source`` is a toolkit output folder, i.e. it contains ``log/*.json`` next to
``artwork/`` and the audio folders. Every ``log/*.json`` that records a cover run
becomes one entry.

What is taken from a run, and what is not
-----------------------------------------
Only facts the run recorded are copied: the source file it was made from, the
measured tempo and length of that source, the chosen style template and musical
fields, the cover mode, the lyrics mode, the lead instrument, the model, seed,
scheduler settings, target duration and the output sample rate. Machine-specific
absolute paths and the long LLM prompt are never copied into the public catalog.

Two fields are left empty **on purpose**:

* ``soundcloudUrl`` — filled in by hand after uploading (same convention as
  ``demo-tracks.js``).
* ``freedom`` — the interpretation freedom is not part of the canonical production
  JSON, so it cannot be read. Type the value you used if you want it on the page.

Both are preserved when you re-run this script, as is ``comment`` on an original and
any ``coverArt`` already chosen.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "demo-covers.js"
COVER_ART_DIR = "assets/demo-covers"

HEADER = """// Music Production Toolkit — cover song demos
//
// Each entry is one ORIGINAL track plus the covers made from it.
//
// HOW TO FILL THIS IN:
// 1. Upload the original and its covers to SoundCloud, make them publicly playable.
// 2. Paste the NORMAL SoundCloud track URL into "soundcloudUrl" (original and cover).
// 3. Optional: write something about the original into "comment".
// 4. Optional: the interpretation freedom you used into "freedom" (0-100) — the
//    production JSON does not record it, so it is empty until you type it in.
// 5. Put the cover images into docs/assets/demo-covers/ (see
//    scripts/prepare_demo_covers.py) and commit.
//
// "variant" is the toolkit's own export numbering: when the target file name already
// exists the saver appends _001, _002 … Those are separate runs of the same song, and
// the export title is identical for all of them - use "freedom" and the file name to
// tell them apart.
//
// Re-running scripts/update_cover_demo_catalog.py refreshes the facts from the
// production JSON and KEEPS everything you filled in by hand here.
//
"""


def _slugify(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "cover"


def _read_existing(path: Path) -> list[dict]:
    """Read a previously written catalog, so hand edits survive a refresh."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    match = re.search(r"window\.DEMO_COVER_GROUPS\s*=\s*(\[.*\]);\s*$", text, re.S)
    if not match:
        return []
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return []


def _dig(data: dict, *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _source_title(filename: str) -> str:
    stem = Path(str(filename)).stem
    return stem.strip() or "Original"


def _source_bpm(data: dict) -> Any:
    bpm = _dig(data, "structured_prompt", "cover_timeline", "bpm")
    return round(float(bpm), 1) if isinstance(bpm, (int, float)) else None


def _source_seconds(data: dict) -> Any:
    seconds = _dig(data, "structured_prompt", "cover_timeline", "duration_seconds")
    return round(float(seconds), 1) if isinstance(seconds, (int, float)) else None


def _release_name(data: dict) -> str:
    """File name of the exported audio, which carries the toolkit's own numbering."""
    for key in ("release_mp3", "release_flac", "original_audio"):
        path = _dig(data, "outputs", key, "path")
        if isinstance(path, str) and path.strip():
            return Path(path.replace("\\", "/")).name
    return ""


def _variant_label(filename: str) -> str:
    """Turn the toolkit's collision counter into a readable label.

    When the target file name already exists the saver appends ``_001``, ``_002`` …
    Those are separate runs of the same song, so the number is the only thing that
    tells them apart - the export title is identical for all of them.
    """
    match = re.search(r"_(\d{3,})$", Path(filename).stem)
    return f"Take {int(match.group(1)) + 1}" if match else "Take 1"


def _cover_entry(data: dict, artwork_name: str | None) -> dict:
    score = _dig(data, "cover", "score", default={}) or {}
    fields = _dig(data, "structured_prompt", "fields", default={}) or {}
    yue2 = _dig(data, "generation", "yue2", default={}) or {}
    title = str(data.get("title") or "").strip()
    release = _release_name(data)
    entry: dict = {
        "id": _slugify(Path(release).stem or title),
        "title": title,
        "variant": _variant_label(release),
        "file": release,
        "soundcloudUrl": "",
        "coverArt": f"{COVER_ART_DIR}/{artwork_name}" if artwork_name else "",
        "model": _dig(data, "structured_prompt", "song_model_name") or data.get("song_model") or "",
        "genre": str(fields.get("genre") or "").strip(),
        "tempoLabel": str(fields.get("tempo") or "").strip(),
        "styleTemplate": _dig(data, "structured_prompt", "user_prompt_origin") or "",
        "lyricsMode": str(score.get("lyrics_mode") or "").strip(),
        "coverMode": str(yue2.get("mode") or "").strip(),
        "leadInstrument": str(score.get("lead_instrument") or "").strip(),
        "freedom": "",
        "targetDurationSeconds": _dig(data, "generation", "max_duration"),
        "seed": _dig(data, "generation", "generation_seed"),
        "steps": yue2.get("steps"),
        "cfg": yue2.get("cfg"),
        "sampler": str(yue2.get("sampler_name") or ""),
        "scheduler": str(yue2.get("scheduler") or ""),
        "outputSampleRate": _dig(data, "release_prep", "output_sample_rate"),
        "scoreChanges": [str(item) for item in (score.get("changes") or [])],
    }
    return {key: value for key, value in entry.items()
            if value not in ("", None, []) or key in {"title", "soundcloudUrl", "freedom", "coverArt"}}

def _artwork_name(data: dict) -> str | None:
    path = _dig(data, "outputs", "artwork", "path")
    if not isinstance(path, str) or not path.strip():
        return None
    return Path(path.replace("\\", "/")).name


def build_groups(json_paths: Iterable[Path]) -> list[dict]:
    """Group every cover run by the source file it was made from."""
    groups: dict[str, dict] = {}
    for path in sorted(json_paths):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source = _dig(data, "structured_prompt", "cover_source")
        if not isinstance(source, dict):
            continue  # not a cover run
        source_file = str(source.get("source_filename") or "").strip()
        if not source_file:
            continue
        title = _source_title(source_file)
        group = groups.setdefault(source_file, {
            "id": _slugify(title),
            "title": title,
            "sourceFile": source_file,
            "sourceBpm": _source_bpm(data),
            "sourceDurationSeconds": _source_seconds(data),
            "soundcloudUrl": "",
            "comment": "",
            "covers": [],
        })
        group["covers"].append(_cover_entry(data, _artwork_name(data)))

    ordered = sorted(groups.values(), key=lambda item: item["title"].casefold())
    for group in ordered:
        group["covers"].sort(key=lambda item: (item.get("variant", ""), item["title"].casefold()))
        group["coverCount"] = len(group["covers"])
    return ordered


def merge_hand_edits(groups: list[dict], previous: list[dict]) -> list[dict]:
    """Keep URLs, freedom values and comments that were typed in by hand."""
    old_groups = {group.get("id"): group for group in previous}
    for group in groups:
        old_group = old_groups.get(group["id"], {})
        for key in ("soundcloudUrl", "comment"):
            if old_group.get(key):
                group[key] = old_group[key]
        old_covers = {cover.get("id"): cover for cover in old_group.get("covers", [])}
        for cover in group["covers"]:
            old_cover = old_covers.get(cover["id"], {})
            for key in ("soundcloudUrl", "freedom"):
                if old_cover.get(key) not in (None, ""):
                    cover[key] = old_cover[key]
            if old_cover.get("coverArt"):
                cover["coverArt"] = old_cover["coverArt"]
    return groups


def write_catalog(path: Path, groups: list[dict]) -> None:
    text = (
        HEADER
        + "window.DEMO_COVER_GROUPS = "
        + json.dumps(groups, ensure_ascii=False, indent=2)
        + ";\n"
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path,
                        help="Toolkit output folder that contains log/ and artwork/.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Where to write the catalog (default: docs/demo-covers.js).")
    parser.add_argument("--dry-run", action="store_true", help="Print a summary only.")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    log_dir = source / "log"
    if not log_dir.is_dir():
        raise SystemExit(f"No log/ folder in {source}")
    json_paths = sorted(log_dir.glob("*.json"))
    if not json_paths:
        raise SystemExit(f"No production JSON in {log_dir}")

    groups = build_groups(json_paths)
    if not groups:
        raise SystemExit("No cover runs found in those JSON files (no cover_source recorded).")
    groups = merge_hand_edits(groups, _read_existing(args.output))

    covers = sum(len(group["covers"]) for group in groups)
    print(f"{len(json_paths)} JSON file(s) -> {len(groups)} original(s), {covers} cover(s)")
    for group in groups:
        print(f"  {group['title']} ({group['coverCount']} cover(s), source {group['sourceBpm']} BPM)")
        for cover in group["covers"]:
            print(f"     - {cover['title']} · {cover.get('variant', '')}")
    if args.dry_run:
        print("dry run: nothing written")
        return 0
    write_catalog(args.output, groups)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
