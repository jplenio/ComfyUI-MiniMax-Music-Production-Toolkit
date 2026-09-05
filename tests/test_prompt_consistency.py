"""Consistency checks for the bundled user prompt library.

The library follows one unified format: a ``---``-delimited metadata block with
canonical keys (genre, tempo, key, lyrics, language, voice, theme, length) plus
free description text.  The description must never repeat information that can
be selected through the structured fields (lyrics mode, voice gender, BPM,
duration, language, ...), and the dropdown listing must stay alphabetical with
files grouped under their category directories.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_DIR = ROOT / "prompts" / "user"

CANONICAL_FIELDS = ("genre", "tempo", "key", "lyrics", "language", "voice", "theme", "length")

# Description text must not duplicate anything these fields already express.
FIELD_DUPLICATION_PATTERNS = [
    (re.compile(r"\binstrumental\b", re.IGNORECASE), "lyrics mode (instrumental)"),
    (re.compile(r"\bsparse\b", re.IGNORECASE), "lyrics mode (sparse)"),
    (re.compile(r"\bBPM\b", re.IGNORECASE), "tempo (BPM)"),
    (re.compile(r"\bminute[s]?\b", re.IGNORECASE), "length (minutes)"),
    (re.compile(r"female vocal", re.IGNORECASE), "voice (female vocal)"),
    (re.compile(r"male vocal", re.IGNORECASE), "voice (male vocal)"),
    (re.compile(r"\bDeutsch\b", re.IGNORECASE), "language (Deutsch)"),
    (re.compile(r"\bdeutschen\b", re.IGNORECASE), "language (Deutsch)"),
    (re.compile(r"German-language", re.IGNORECASE), "language (Deutsch)"),
]


def parse_prompt_file(path: Path) -> tuple[list[tuple[str, str]] | None, str]:
    """Return (front-matter pairs, description) for one prompt file."""
    lines = path.read_text(encoding="utf-8-sig").strip().splitlines()
    if not lines or lines[0].strip() != "---":
        return None, "\n".join(lines)
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        return None, "\n".join(lines)
    pairs: list[tuple[str, str]] = []
    for raw in lines[1:end]:
        line = raw.strip()
        if not line:
            continue
        key, sep, value = line.partition(":")
        if sep and value.strip():
            pairs.append((key.strip().lower(), value.strip()))
    return pairs, "\n".join(lines[end + 1:]).strip()


def load_prompt_library() -> object:
    pkg_name = "_prompt_consistency_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    for module_name in ("toolkit_logging", "prompt_library"):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return sys.modules[f"{pkg_name}.prompt_library"]


class PromptLibraryConsistencyTests(unittest.TestCase):
    """The bundled user prompt library follows one unified, field-first format."""

    def test_every_prompt_has_metadata_and_description(self):
        files = sorted(p for p in USER_DIR.rglob("*") if p.is_file())
        self.assertGreaterEqual(len(files), 90, "world-music-extended library should keep 90+ prompts")
        for path in files:
            pairs, description = parse_prompt_file(path)
            self.assertIsNotNone(pairs, f"{path.name}: missing metadata block")
            assert pairs is not None
            self.assertGreaterEqual(len(pairs), 1, f"{path.name}: empty metadata block")
            self.assertTrue(description, f"{path.name}: empty description")

    def test_front_matter_uses_canonical_keys_in_order(self):
        for path in USER_DIR.rglob("*"):
            if not path.is_file():
                continue
            pairs, _description = parse_prompt_file(path)
            if pairs is None:
                continue
            keys = [key for key, _value in pairs]
            self.assertEqual(
                keys,
                sorted(keys, key=CANONICAL_FIELDS.index),
                f"{path.name}: front-matter keys must follow the canonical field order",
            )
            for key in keys:
                self.assertIn(key, CANONICAL_FIELDS, f"{path.name}: unknown front-matter key '{key}'")

    def test_lyrics_values_are_canonical(self):
        for path in USER_DIR.rglob("*"):
            if not path.is_file():
                continue
            pairs, _description = parse_prompt_file(path)
            if pairs is None:
                continue
            for key, value in pairs:
                if key == "lyrics":
                    self.assertIn(value, {"yes", "sparse", "only voice - no words", "instrumental"}, f"{path.name}: {value!r}")

    def test_tempo_values_are_curated_bpm_ranges(self):
        # Tempo metadata must use one of the curated BPM ranges (the combo's
        # first entry is custom), never a single fixed value.
        import importlib.util as _iu
        import sys as _sys
        import types as _types

        pkg_name = "_prompt_consistency_meta"
        pkg = _types.ModuleType(pkg_name)
        pkg.__path__ = [str(ROOT)]
        _sys.modules[pkg_name] = pkg
        for module_name in ("toolkit_logging", "prompt_metadata"):
            spec = _iu.spec_from_file_location(f"{pkg_name}.{module_name}", ROOT / f"{module_name}.py")
            loaded = _iu.module_from_spec(spec)
            _sys.modules[f"{pkg_name}.{module_name}"] = loaded
            assert spec and spec.loader
            spec.loader.exec_module(loaded)
        curated = set(_sys.modules[f"{pkg_name}.prompt_metadata"].CURATED_FIELD_OPTIONS["tempo"])
        for path in USER_DIR.rglob("*"):
            if not path.is_file():
                continue
            pairs, _description = parse_prompt_file(path)
            if pairs is None:
                continue
            for key, value in pairs:
                if key == "tempo":
                    self.assertIn(value, curated, f"{path.name}: tempo {value!r} is not a curated BPM range")

    def test_description_does_not_duplicate_field_values(self):
        for path in USER_DIR.rglob("*"):
            if not path.is_file():
                continue
            pairs, description = parse_prompt_file(path)
            if pairs is None:
                continue
            for pattern, label in FIELD_DUPLICATION_PATTERNS:
                self.assertIsNone(
                    pattern.search(description),
                    f"{path.name}: description mentions {label}, which is covered by a field",
                )

    def test_listing_is_alphabetical_and_directory_grouped(self):
        prompt_library = load_prompt_library()
        files = prompt_library.list_prompt_files("user", "bundled_library")
        self.assertEqual(files, sorted(files, key=str.casefold), "file listing must be alphabetical")
        directories: list[str] = []
        for relative in files:
            self.assertIn("/", relative, f"{relative}: every bundled prompt lives in a category folder")
            directories.append(relative.split("/", 1)[0])
        unique_dirs = list(dict.fromkeys(directories))
        self.assertEqual(unique_dirs, sorted(unique_dirs, key=str.casefold), "directories must be alphabetical")
        # Within each directory the files are already sorted (full-path sort).
        for directory in unique_dirs:
            names = [f for f in files if f.startswith(directory + "/")]
            self.assertEqual(names, sorted(names, key=str.casefold), f"{directory}: files must be alphabetical")


if __name__ == "__main__":
    unittest.main()
