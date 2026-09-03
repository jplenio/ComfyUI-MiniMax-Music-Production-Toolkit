#!/usr/bin/env python3
"""Automated version bump helper.

Updates every place the release version is stored and creates a release-notes
skeleton, so a manual mismatch between VERSION / pyproject.toml / project_info
/ CITATION.cff / the example workflow metadata cannot happen by accident.

Usage:
    python scripts/bump_version.py 2.0.1
    python scripts/bump_version.py --patch|--minor|--major [--date 2026-09-05]

The script refuses to overwrite an existing release-notes file; delete it
first if you really want to regenerate it.  It prints every changed file and
does not commit or tag anything.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VERSION_FILES = (
    ("VERSION", ROOT / "VERSION", "plain"),
    ("project_info.py", ROOT / "project_info.py", "python"),
    ("pyproject.toml", ROOT / "pyproject.toml", "toml"),
    ("CITATION.cff", ROOT / "CITATION.cff", "cff"),
)
WORKFLOW = ROOT / "example_workflows" / "MiniMax_Music3_Production_Toolkit.json"

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def current_version(root: Path = ROOT) -> str:
    text = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not _VERSION_RE.match(text):
        raise SystemExit(f"VERSION file does not contain a plain x.y.z version: {text!r}")
    return text


def next_version(current: str, bump: str) -> str:
    major, minor, patch = (int(part) for part in current.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def update_version_files(old: str, new: str, root: Path = ROOT) -> list[str]:
    changed = []
    for label, _path, kind in VERSION_FILES:
        path = root / _path.name
        text = path.read_text(encoding="utf-8")
        if kind == "plain":
            updated = new + "\n" if text.rstrip("\n") == old else text.replace(old, new, 1)
        elif kind == "python":
            updated = text.replace(f'VERSION = "{old}"', f'VERSION = "{new}"', 1)
        elif kind == "toml":
            updated = text.replace(f'version = "{old}"', f'version = "{new}"', 1)
        else:  # cff
            updated = text.replace(f"version: {old}", f"version: {new}", 1)
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")
            changed.append(label)
        else:
            print(f"WARNING: version pattern not found in {label} - left unchanged")
    return changed


def update_workflow_metadata(new: str) -> bool:
    if not WORKFLOW.exists():
        return False
    data = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    extra = data.setdefault("extra", {})
    if extra.get("workflow_version") == new:
        return False
    extra["workflow_version"] = new
    WORKFLOW.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return True


def create_release_notes(new: str, today: str) -> Path:
    path = ROOT / f"RELEASE_NOTES_v{new}.md"
    if path.exists():
        raise SystemExit(f"Release notes already exist: {path.name} (delete it first to regenerate)")
    skeleton = (
        f"# Release Notes – v{new}\n\n"
        f"Release date: {today}\n\n"
        "## Summary\n\n"
        "_Short summary of what this release changes._\n\n"
        "## Added\n\n- \n\n## Changed\n\n- \n\n## Fixed\n\n- \n\n"
        "## Breaking changes\n\n- None.\n\n"
        "## Upgrade notes\n\n- Existing workflows keep working; reload "
        "`example_workflows/MiniMax_Music3_Production_Toolkit.json` to pick up serialized fixes.\n\n"
        "## Assets\n\n- `ComfyUI-MiniMax-Music-Production-Toolkit-vX.Y.Z.zip`\n"
        "- `MiniMax_Music3_Production_Toolkit_vX.Y.Z.json`\n- `SHA256SUMS.txt`\n"
    )
    path.write_text(skeleton, encoding="utf-8", newline="\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help="Explicit new version, e.g. 2.0.1.")
    parser.add_argument("--patch", action="store_true")
    parser.add_argument("--minor", action="store_true")
    parser.add_argument("--major", action="store_true")
    parser.add_argument("--date", default=date.today().isoformat(), help="Release date (YYYY-MM-DD) for the notes skeleton.")
    parser.add_argument("--no-release-notes", action="store_true", help="Do not create a release-notes skeleton.")
    args = parser.parse_args()

    bumps = [args.patch, args.minor, args.major]
    if args.version and any(bumps):
        raise SystemExit("Pass either an explicit version or one of --patch/--minor/--major, not both.")
    if not args.version and sum(bumps) != 1:
        raise SystemExit("Pass an explicit version or exactly one of --patch/--minor/--major.")

    old = current_version()
    new = args.version if args.version else next_version(old, "major" if args.major else "minor" if args.minor else "patch")
    if not _VERSION_RE.match(new):
        raise SystemExit(f"Invalid version format: {new!r} (expected x.y.z)")
    if new == old:
        raise SystemExit(f"New version equals the current version ({old}).")
    # Guard against accidental downgrades (published versions are immutable).
    def key(v: str) -> tuple[int, int, int]:
        return tuple(int(p) for p in v.split("."))  # type: ignore[return-value]
    if key(new) < key(old):
        raise SystemExit(f"Refusing downgrade: {new} < {old}. Published versions are immutable; pick a higher version.")

    changed = update_version_files(old, new)
    if update_workflow_metadata(new):
        changed.append(WORKFLOW.name)

    notes = None
    if not args.no_release_notes:
        notes = create_release_notes(new, args.date)
        changed.append(notes.name)

    print(f"Version bumped: {old} -> {new}")
    for name in changed:
        print(f"  updated: {name}")
    print("Reminder: update CHANGELOG.md, then run scripts/validate_release.py and scripts/package_release.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
