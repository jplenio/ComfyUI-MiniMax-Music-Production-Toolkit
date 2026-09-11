"""Shared prompt-source helper tests (F16 / T14).

The decisive guarantee is that the two loader dialects still produce the same
prompts, provenance and seeds, because the variant/seed loop is now shared.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = "_prompt_sources_test"
if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg

MODULES = {}
for _name in ("toolkit_logging", "filename_utils", "prompt_sources", "prompt_library",
              "prompt_metadata", "prompt_budget", "minimax_batch", "minimax_prompt_source",
              "minimax_structured_prompt"):
    _full = f"{PKG}.{_name}"
    _spec = importlib.util.spec_from_file_location(_full, ROOT / f"{_name}.py")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_full] = _module
    assert _spec.loader is not None
    _spec.loader.exec_module(_module)
    MODULES[_name] = _module

sources = MODULES["prompt_sources"]
batch = MODULES["minimax_batch"]
rich = MODULES["minimax_prompt_source"]
structured = MODULES["minimax_structured_prompt"]

PROMPT_FILE = """[Title]
Fixture Song

[Caption]
A calm four-minute instrumental with warm pads.

[Lyrics]
[Verse]
la la la
"""


def write_fixture(directory: Path, name: str, text: str = PROMPT_FILE) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write bytes so the fixture keeps LF regardless of the platform's
    # newline translation in ``Path.write_text``.
    path.write_bytes(text.encode("utf-8"))
    return path


class NamingAndDecodingTests(unittest.TestCase):
    def test_clean_source_name_matches_both_node_wrappers(self):
        for value in ("Example Song", 'a<b>c:d', "trailing . ", "", "   "):
            with self.subTest(value=value):
                expected = sources.clean_source_name(value)
                self.assertEqual(batch._clean_source_name(value), expected)
                self.assertEqual(rich._clean_source_name(value), expected)
                self.assertEqual(structured._clean_source_name(value), expected)

    def test_clean_source_name_replaces_windows_invalid_characters(self):
        self.assertEqual(sources.clean_source_name('a/b\\c:d*e?f"g<h>i|j'), "a_b_c_d_e_f_g_h_i_j")
        self.assertEqual(sources.clean_source_name(""), "song")

    def test_new_seed_is_int64_safe(self):
        for _ in range(20):
            seed = sources.new_seed()
            self.assertGreaterEqual(seed, 0)
            self.assertLess(seed, 2**63 - 1)

    def test_read_prompt_text_encodings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bom = root / "bom.txt"
            bom.write_bytes(PROMPT_FILE.encode("utf-8-sig"))
            self.assertEqual(sources.read_prompt_text(bom), PROMPT_FILE)
            plain = root / "plain.txt"
            plain.write_bytes(PROMPT_FILE.encode("utf-8"))
            self.assertEqual(sources.read_prompt_text(plain), PROMPT_FILE)
            cp1252 = root / "old.txt"
            cp1252.write_bytes("Gem\u00fctlich \u2013 Caf\u00e9".encode("cp1252"))
            self.assertEqual(sources.read_prompt_text(cp1252), "Gem\u00fctlich \u2013 Caf\u00e9")
            broken = root / "broken.txt"
            broken.write_bytes(b"\xff\xfe\x00\x81")
            with self.assertRaises(UnicodeDecodeError):
                sources.read_prompt_text(broken)

    def test_resolve_prompt_directory_keeps_each_callers_message(self):
        with self.assertRaises(ValueError) as ctx:
            batch._resolve_prompt_directory("")
        self.assertIn("MiniMax Prompt Batch Loader", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            rich._resolve_prompt_directory("")
        self.assertIn("MiniMax Prompt Source", str(ctx.exception))

    def test_relative_directory_resolves_to_an_absolute_path(self):
        resolved = sources.resolve_prompt_directory("some/relative/dir", error_prefix="T")
        self.assertTrue(resolved.is_absolute())


class DiscoveryTests(unittest.TestCase):
    def test_normalize_extensions(self):
        self.assertEqual(sources.normalize_extensions(".txt, md ,,.prompt"), {".txt", ".md", ".prompt"})
        self.assertEqual(sources.normalize_extensions(""), set())
        self.assertEqual(sources.normalize_extensions("TXT"), {".txt"})

    def test_discovery_filters_extensions_and_sorts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, "b.txt")
            write_fixture(root, "a.md")
            write_fixture(root, "skip.png")
            write_fixture(root, "nested/c.txt")
            allowed = sources.normalize_extensions("txt,md")
            flat = sources.iter_prompt_files(root, allowed, False, relative_sort=True)
            self.assertEqual([p.name for p in flat], ["a.md", "b.txt"])
            recursive = sources.iter_prompt_files(root, allowed, True, relative_sort=True)
            self.assertEqual([p.name for p in recursive], ["a.md", "b.txt", "c.txt"])
            absolute_sorted = sources.iter_prompt_files(root, allowed, True, relative_sort=False)
            self.assertEqual({p.name for p in absolute_sorted}, {"a.md", "b.txt", "c.txt"})


class VariantIterationTests(unittest.TestCase):
    def test_deterministic_seed_sequence_spans_all_entries(self):
        entries = [{"count_override": 2}, {"count_override": 2}]
        yielded = list(sources.iter_variants(
            entries, song_count=1, seed_mode="base", base_seed=1000,
            count_of=lambda e: e["count_override"],
        ))
        self.assertEqual([item[3] for item in yielded], [1000, 1001, 1002, 1003])
        self.assertEqual([item[1] for item in yielded], [1, 2, 1, 2], "variant index resets per entry")
        self.assertEqual([item[2] for item in yielded], [2, 2, 2, 2])
        self.assertEqual([item[4] for item in yielded], [0, 1, 2, 3])

    def test_count_policy_is_the_callers_decision(self):
        entries = [{"count_override": 0}]
        strict = list(sources.iter_variants(
            entries, song_count=3, seed_mode="base", base_seed=1,
            count_of=lambda e: e["count_override"] if e["count_override"] is not None else 3,
        ))
        tolerant = list(sources.iter_variants(
            entries, song_count=3, seed_mode="base", base_seed=1,
            count_of=lambda e: e["count_override"] or 3,
        ))
        self.assertEqual(len(strict), 0, "legacy strict count: explicit 0 means no songs")
        self.assertEqual(len(tolerant), 3, "rich tolerant count: falsy override falls back")

    def test_random_mode_uses_a_fresh_seed_per_song(self):
        generated = iter(range(100, 200))
        saved = sources.new_seed
        try:
            sources.new_seed = lambda: next(generated)
            yielded = list(sources.iter_variants(
                [{"count_override": 3}], song_count=1, seed_mode="random_each_song", base_seed=5,
                count_of=lambda e: e["count_override"],
            ))
        finally:
            sources.new_seed = saved
        self.assertEqual([item[3] for item in yielded], [100, 101, 102])


class LoaderParityTests(unittest.TestCase):
    """Both loaders must yield identical prompts and seeds for one fixture."""

    def test_folder_loaders_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, "a.txt")
            write_fixture(root, "b.txt", PROMPT_FILE.replace("Fixture Song", "Second Song"))

            batch_out = batch.MiniMaxPromptBatchLoader().load(
                "folder", str(root), 2, "base", 1000, "txt", False, "", "", "",
            )
            rich_out = rich.MiniMaxPromptSourceArtworkV16().load(
                "folder", 2, "base", 1000, str(root), "txt", False, "", "", "", "",
            )

            b_captions, b_lyrics, b_titles, b_sources, b_seeds, b_runs, b_paths = batch_out
            r_captions, r_lyrics, r_titles, _r_images, r_sources, r_seeds, r_runs, _r_counts, r_paths, _r_origin, _r_prov = rich_out

            self.assertEqual(b_captions, r_captions)
            self.assertEqual(b_lyrics, r_lyrics)
            self.assertEqual(b_titles, r_titles)
            self.assertEqual(b_sources, r_sources)
            self.assertEqual(b_seeds, r_seeds)
            self.assertEqual(b_runs, r_runs)
            self.assertEqual([os.path.basename(p) for p in b_paths],
                             [os.path.basename(p) for p in r_paths])
            self.assertEqual(b_seeds, [1000, 1001, 1002, 1003])
            self.assertEqual(b_sources, ["a", "a", "b", "b"])
            self.assertEqual(b_runs, [1, 2, 1, 2])

    def test_manual_entry_uses_the_cleaned_title_as_source_name(self):
        out = batch.MiniMaxPromptBatchLoader().load(
            "manual", "", 1, "base", 7, "txt", False, "My<Song>", "caption", "lyrics",
        )
        self.assertEqual(out[3], ["My_Song_"])
        self.assertEqual(out[4], [7])

    def test_legacy_loader_rejects_an_empty_extension_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_fixture(Path(tmp), "a.txt")
            with self.assertRaises(ValueError) as ctx:
                batch.MiniMaxPromptBatchLoader().load(
                    "folder", tmp, 1, "base", 1, "", False, "", "", "",
                )
            self.assertIn("extensions list is empty", str(ctx.exception))


class ImportGraphTests(unittest.TestCase):
    def test_structured_node_no_longer_imports_the_parser_node(self):
        source = (ROOT / "minimax_structured_prompt.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "minimax_prompt_source", source,
            "the structured node must use prompt_sources instead of the parser node module",
        )

    def test_defaults_are_re_exported_by_the_parser_node(self):
        self.assertEqual(rich.DEFAULT_SYSTEM_PROMPT, sources.DEFAULT_SYSTEM_PROMPT)
        self.assertEqual(rich.DEFAULT_SYSTEM_PROMPT_FILE, "minimax-music3-production.txt")
        self.assertTrue(rich.DEFAULT_SYSTEM_PROMPT.strip())


if __name__ == "__main__":
    unittest.main()
