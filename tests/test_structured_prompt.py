from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_toolkit_modules():
    """Load the prompt modules as a synthetic package so the tests never import ComfyUI."""
    pkg_name = "_toolkit_structured_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in (
        "toolkit_logging",
        "prompt_library",
        "prompt_metadata",
        "minimax_prompt_source",
        "minimax_structured_prompt",
    ):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


MODULES = load_toolkit_modules()
prompt_library = MODULES["prompt_library"]
prompt_metadata = MODULES["prompt_metadata"]
structured_node = MODULES["minimax_structured_prompt"].MiniMaxStructuredPromptV20
parser_node = MODULES["minimax_prompt_source"].MiniMaxParseExternalLLMOutputV16
PLACEHOLDER = prompt_library.PLACEHOLDER
CUSTOM = prompt_metadata.CUSTOM
STRUCTURED_FIELDS = prompt_metadata.STRUCTURED_FIELDS


class PromptFrontMatterTests(unittest.TestCase):
    def test_plain_file_has_no_fields_and_full_description(self):
        text = "A plain prompt\nwith several lines."
        fields, description = prompt_metadata.parse_prompt_front_matter(text)
        self.assertEqual(fields, {})
        self.assertEqual(description, text)

    def test_metadata_block_parses_all_fields(self):
        text = (
            "---\n"
            "Genre: Melodic Techno\n"
            "Tempo: 128 BPM\n"
            "Key: A minor\n"
            "Lyrics: sparse\n"
            "Language: English\n"
            "Voice: female vocal, airy\n"
            "Theme: escape into the night\n"
            "Length: 4-5 minutes\n"
            "---\n"
            "Deep rolling bassline with hypnotic arps."
        )
        fields, description = prompt_metadata.parse_prompt_front_matter(text)
        self.assertEqual(fields["genre"], "Melodic Techno")
        self.assertEqual(fields["tempo"], "128 BPM")
        self.assertEqual(fields["key"], "A minor")
        self.assertEqual(fields["lyrics"], "sparse")
        self.assertEqual(fields["language"], "English")
        self.assertEqual(fields["voice"], "female vocal, airy")
        self.assertEqual(fields["theme"], "escape into the night")
        self.assertEqual(fields["length"], "4-5 minutes")
        self.assertEqual(description, "Deep rolling bassline with hypnotic arps.")

    def test_unclosed_block_treated_as_plain_text(self):
        text = "---\nGenre: House\nnot really metadata"
        fields, description = prompt_metadata.parse_prompt_front_matter(text)
        self.assertEqual(fields, {})
        self.assertEqual(description, text)

    def test_unknown_keys_are_ignored(self):
        text = "---\nMood: bright\nGenre: House\n---\nbody"
        fields, description = prompt_metadata.parse_prompt_front_matter(text)
        self.assertEqual(fields, {"genre": "House"})
        self.assertEqual(description, "body")

    def test_aliases_are_normalized(self):
        text = "---\nTonart: F# minor\nSprache: Deutsch\nStimme: male\nBPM: 124\n---\nbody"
        fields, _ = prompt_metadata.parse_prompt_front_matter(text)
        self.assertEqual(fields["key"], "F# minor")
        self.assertEqual(fields["language"], "Deutsch")
        self.assertEqual(fields["voice"], "male")
        self.assertEqual(fields["tempo"], "124")

    def test_description_key_fallback_when_body_empty(self):
        text = "---\nGenre: Ambient\nDescription: Short description only\n---\n"
        fields, description = prompt_metadata.parse_prompt_front_matter(text)
        self.assertEqual(fields, {"genre": "Ambient"})
        self.assertEqual(description, "Short description only")

    def test_lyrics_values_normalized(self):
        for raw, expected in (
            ("Ja", "yes"),
            ("no", "instrumental"),
            ("wenig", "sparse"),
            ("instrumental", "instrumental"),
            ("some unusual phrasing", "some unusual phrasing"),
        ):
            self.assertEqual(prompt_metadata.normalize_lyrics_value(raw), expected, raw)


class PromptAssemblyTests(unittest.TestCase):
    def test_custom_fields_are_omitted(self):
        prompt = prompt_metadata.assemble_structured_user_prompt(
            {"genre": "House", "tempo": CUSTOM, "lyrics": "instrumental"},
            "Pumping groove with warm chords.",
        )
        self.assertIn("Genre: House", prompt)
        self.assertIn("Lyrics: instrumental", prompt)
        self.assertNotIn("Tempo", prompt)
        self.assertTrue(prompt.endswith("Pumping groove with warm chords."))

    def test_all_custom_without_description_raises(self):
        with self.assertRaises(ValueError):
            prompt_metadata.assemble_structured_user_prompt(
                {field: CUSTOM for field in STRUCTURED_FIELDS}, ""
            )

    def test_description_only_is_returned_verbatim(self):
        prompt = prompt_metadata.assemble_structured_user_prompt({}, "Just a description.")
        self.assertEqual(prompt, "Just a description.")

    def test_field_order_matches_canonical_order(self):
        prompt = prompt_metadata.assemble_structured_user_prompt(
            {"length": "3 minutes", "genre": "Jazz", "tempo": "120 BPM"}, ""
        )
        self.assertLess(prompt.index("Genre: Jazz"), prompt.index("Tempo: 120 BPM"))
        self.assertLess(prompt.index("Tempo: 120 BPM"), prompt.index("Length: 3 minutes"))


class LibraryAggregationTests(unittest.TestCase):
    def test_bundled_library_aggregation_has_unique_values(self):
        root = prompt_library.bundled_root("user")
        paths = [p for p in root.rglob("*") if p.is_file()]
        self.assertGreater(len(paths), 50, "expected the bundled prompt library")
        options = prompt_metadata.collect_file_field_values(paths)
        for field in STRUCTURED_FIELDS:
            values = options[field]
            self.assertEqual(len(values), len(set(values)), f"{field} has duplicates")
            self.assertIsInstance(values, list)

    def test_aggregation_with_broken_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "good.txt").write_text(
                "---\nGenre: House\nLyrics: sparse\n---\nbody", encoding="utf-8"
            )
            (root / "bad.txt").write_bytes(b"\xff\xfe\x00not utf-8")
            (root / "plain.txt").write_text("no metadata here", encoding="utf-8")
            options = prompt_metadata.collect_file_field_values(
                [root / "good.txt", root / "bad.txt", root / "plain.txt"]
            )
            self.assertEqual(options["genre"], ["House"])
            self.assertEqual(options["lyrics"], ["sparse"])
            self.assertEqual(options["tempo"], [])

    def test_curated_options_cover_every_field(self):
        for field in STRUCTURED_FIELDS:
            self.assertTrue(
                prompt_metadata.CURATED_FIELD_OPTIONS.get(field),
                f"{field} has no curated options",
            )

    def test_merge_field_options_includes_curated_vocabulary(self):
        merged = prompt_metadata.merge_field_options({
            "genre": ["Weird Library Genre"],
            "tempo": [],
            "key": ["D minor"],
            "lyrics": ["yes"],
            "language": [],
            "voice": [],
            "theme": [],
            "length": [],
        })
        self.assertIn("House", merged["genre"])
        self.assertIn("Weird Library Genre", merged["genre"])
        self.assertIn("Uptempo (130-145 BPM)", merged["tempo"])
        self.assertIn("D minor", merged["key"])
        self.assertEqual(merged["lyrics"], list(prompt_metadata.LYRICS_CHOICES))
        self.assertIn("English", merged["language"])
        self.assertIn("female vocal", merged["voice"])
        self.assertIn("4-5 minutes", merged["length"])
        for field in STRUCTURED_FIELDS:
            values = merged[field]
            self.assertEqual(len(values), len(set(values)), f"{field} has duplicates")
            self.assertNotIn(CUSTOM, values)


class StructuredPromptNodeTests(unittest.TestCase):
    def _build(self, **overrides):
        base = dict(
            user_prompt_source="manual",
            user_prompt_directory="",
            user_prompt_file=PLACEHOLDER,
            genre=CUSTOM,
            tempo=CUSTOM,
            key=CUSTOM,
            lyrics=CUSTOM,
            language=CUSTOM,
            voice=CUSTOM,
            theme=CUSTOM,
            length=CUSTOM,
            description_override="",
            system_prompt="You are a music assistant.",
            system_prompt_source="manual",
            system_prompt_directory="",
            system_prompt_file=PLACEHOLDER,
            source_name_override="",
        )
        base.update(overrides)
        return structured_node().build(**base)

    def test_node_build_with_metadata_prefill_and_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "song.txt").write_text(
                "---\nGenre: EDM\nLyrics: instrumental\nTempo: 128 BPM\n---\nBig room anthem.",
                encoding="utf-8",
            )
            # Explicit widget values flow into the brief.
            system, user, source_name, summary = self._build(
                user_prompt_source="external_directory",
                user_prompt_directory=str(root),
                user_prompt_file="song.txt",
                genre="EDM",
                lyrics="instrumental",
                tempo="128 BPM",
                description_override="Big room anthem.",
            )
            self.assertEqual(system, "You are a music assistant.")
            self.assertIn("Genre: EDM", user)
            self.assertIn("Lyrics: instrumental", user)
            self.assertIn("Tempo: 128 BPM", user)
            self.assertTrue(user.endswith("Big room anthem."))
            self.assertEqual(source_name, "song")
            summary_data = json.loads(summary)
            self.assertEqual(summary_data["user_prompt_origin"], "song.txt")

            # Explicit widget override beats the file metadata.
            _s, user2, _n, _x = self._build(
                user_prompt_source="external_directory",
                user_prompt_directory=str(root),
                user_prompt_file="song.txt",
                genre="Techno",
                description_override="Big room anthem.",
            )
            self.assertIn("Genre: Techno", user2)
            self.assertNotIn("Genre: EDM", user2)

    def test_explicit_custom_omits_field_even_with_file_metadata(self):
        # "custom" means NO specification: it must not fall back to the file's
        # metadata value, otherwise the headings the user wanted removed would
        # reappear ("Musical brief:" with file values instead of being omitted).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "song.txt").write_text(
                "---\nGenre: EDM\nLyrics: instrumental\nTempo: 128 BPM\n---\nBig room anthem.",
                encoding="utf-8",
            )
            _s, user, _n, summary = self._build(
                user_prompt_source="external_directory",
                user_prompt_directory=str(root),
                user_prompt_file="song.txt",
                description_override="Big room anthem.",
            )
            # Every field is custom -> no "Musical brief:" heading at all.
            self.assertNotIn("Musical brief", user)
            self.assertNotIn("Genre", user)
            self.assertEqual(user, "Big room anthem.")
            summary_data = json.loads(summary)
            for field in STRUCTURED_FIELDS:
                self.assertEqual(summary_data["fields"][field], CUSTOM)

    def test_all_custom_without_description_raises_in_file_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "song.txt").write_text(
                "---\nGenre: EDM\n---\nOriginal body text.",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                self._build(
                    user_prompt_source="external_directory",
                    user_prompt_directory=str(root),
                    user_prompt_file="song.txt",
                    description_override="",
                )

    def test_node_file_mode_description_override_is_authoritative(self):
        # The frontend copies the file body into description_override; the
        # backend then uses only that field - never the file body as fallback.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "song.txt").write_text(
                "---\nGenre: EDM\n---\nOriginal body text.",
                encoding="utf-8",
            )
            _s, user, _n, _x = self._build(
                user_prompt_source="external_directory",
                user_prompt_directory=str(root),
                user_prompt_file="song.txt",
                genre="EDM",
                description_override="Edited description.",
            )
            self.assertIn("Edited description.", user)
            self.assertNotIn("Original body text.", user)

    def test_node_manual_mode_with_description(self):
        system, user, source_name, _summary = self._build(
            genre="Funk",
            lyrics="yes",
            description_override="Upbeat bassline and horns.",
        )
        self.assertEqual(system, "You are a music assistant.")
        self.assertIn("Genre: Funk", user)
        self.assertIn("Lyrics: yes", user)
        self.assertTrue(user.endswith("Upbeat bassline and horns."))
        self.assertEqual(source_name, "")

    def test_node_requires_something(self):
        with self.assertRaises(ValueError):
            self._build()

    def test_node_input_types_shape(self):
        data = structured_node.INPUT_TYPES()
        required = data["required"]
        for field in STRUCTURED_FIELDS:
            self.assertIn(field, required)
            self.assertEqual(required[field][0][0], CUSTOM)
        self.assertEqual(data["optional"]["source_name_override"][1].get("default"), "")
        # The prompt-file dropdown exposes the free mode as its first real choice.
        file_options = required["user_prompt_file"][0]
        self.assertIn(CUSTOM, file_options)
        self.assertIn(PLACEHOLDER, file_options)

    def test_tempo_combo_offers_curated_bpm_ranges(self):
        # Tempo is a combo whose first entry is custom and whose curated
        # entries are BPM ranges (not single fixed values), so a selection
        # always leaves the LLM a comfortable musical window.
        _combo = MODULES["minimax_structured_prompt"]._combo
        options = _combo("tempo")
        self.assertEqual(options[0], CUSTOM)
        self.assertGreaterEqual(len(options), 7)
        range_re = re.compile(r"\(\d{2,3}-\d{2,3} BPM\)$")
        for option in options[1:]:
            self.assertRegex(option, range_re)

    def test_custom_prompt_file_acts_as_free_manual_mode(self):
        # "custom" in the prompt-file dropdown means: load no file, touch no
        # fields, and use only what the user typed themselves.
        system, user, source_name, summary = self._build(
            user_prompt_source="bundled_library",
            user_prompt_file=CUSTOM,
            genre="Funk",
            lyrics="yes",
            description_override="Upbeat bassline and horns.",
        )
        self.assertEqual(system, "You are a music assistant.")
        self.assertIn("Genre: Funk", user)
        self.assertIn("Lyrics: yes", user)
        self.assertTrue(user.endswith("Upbeat bassline and horns."))
        self.assertEqual(source_name, "")
        summary_data = json.loads(summary)
        self.assertEqual(summary_data["user_prompt_origin"], "<manual>")
        self.assertEqual(summary_data["fields"]["genre"], "Funk")

    def test_custom_prompt_file_requires_something(self):
        with self.assertRaises(ValueError):
            self._build(
                user_prompt_source="bundled_library",
                user_prompt_file=CUSTOM,
            )


    def test_is_changed_includes_field_state(self):
        fp1 = structured_node.IS_CHANGED(
            user_prompt_source="manual", user_prompt_directory="", user_prompt_file=PLACEHOLDER,
            genre="House", tempo=CUSTOM, key=CUSTOM, lyrics=CUSTOM, language=CUSTOM,
            voice=CUSTOM, theme=CUSTOM, length=CUSTOM, description_override="",
            system_prompt="SYS", system_prompt_source="manual", system_prompt_directory="",
            system_prompt_file=PLACEHOLDER, source_name_override="",
        )
        fp2 = structured_node.IS_CHANGED(
            user_prompt_source="manual", user_prompt_directory="", user_prompt_file=PLACEHOLDER,
            genre="Techno", tempo=CUSTOM, key=CUSTOM, lyrics=CUSTOM, language=CUSTOM,
            voice=CUSTOM, theme=CUSTOM, length=CUSTOM, description_override="",
            system_prompt="SYS", system_prompt_source="manual", system_prompt_directory="",
            system_prompt_file=PLACEHOLDER, source_name_override="",
        )
        self.assertNotEqual(fp1, fp2)

    def test_is_changed_handles_custom_prompt_file(self):
        # Free mode must not try to resolve a file literally named "custom".
        fp = structured_node.IS_CHANGED(
            user_prompt_source="bundled_library", user_prompt_directory="", user_prompt_file=CUSTOM,
            genre="House", tempo=CUSTOM, key=CUSTOM, lyrics=CUSTOM, language=CUSTOM,
            voice=CUSTOM, theme=CUSTOM, length=CUSTOM, description_override="",
            system_prompt="SYS", system_prompt_source="manual", system_prompt_directory="",
            system_prompt_file=PLACEHOLDER, source_name_override="",
        )
        self.assertIn(f"user:{CUSTOM}", fp)


    def test_is_changed_includes_description_override_in_file_mode(self):
        def fingerprint(description):
            return structured_node.IS_CHANGED(
                user_prompt_source="external_directory",
                user_prompt_directory=str(Path("/nonexistent")),
                user_prompt_file="song.txt",
                genre=CUSTOM, tempo=CUSTOM, key=CUSTOM, lyrics=CUSTOM, language=CUSTOM,
                voice=CUSTOM, theme=CUSTOM, length=CUSTOM,
                description_override=description,
                system_prompt="SYS", system_prompt_source="manual", system_prompt_directory="",
                system_prompt_file=PLACEHOLDER, source_name_override="",
            )
        # description_override is authoritative in file mode too, so editing it
        # must invalidate the cache even though the file selection is unchanged.
        self.assertNotEqual(fingerprint("first description"), fingerprint("second description"))
        self.assertNotEqual(fingerprint("first description"), fingerprint(""))

    def test_combo_options_include_curated_and_library_values(self):
        _combo = MODULES["minimax_structured_prompt"]._combo

        genres = _combo("genre")
        self.assertEqual(genres[0], CUSTOM)
        self.assertIn("House", genres)
        self.assertIn("Alternative", genres)  # bundled-library value merged in
        self.assertIn("English", _combo("language"))
        self.assertIn("Deutsch", _combo("language"))
        self.assertIn("4-5 minutes", _combo("length"))
        self.assertIn("female vocal", _combo("voice"))
        self.assertEqual(_combo("lyrics"), [CUSTOM, "yes", "sparse", "only voice - no words", "instrumental"])


class PromptSourceCountParseTests(unittest.TestCase):
    """The [Count] section must never crash the run on LLM prose."""
    def _parse_sections(self, text):
        return MODULES["minimax_prompt_source"]._parse_sections(text)

    def test_plain_integer_count(self):
        parsed = self._parse_sections(
            "[Caption]\ncap\n[Lyrics]\n[Intro]\n[Count]\n3\n[Title]\nt\n[Image_Prompt]\nimg"
        )
        self.assertEqual(parsed["count_override"], 3)

    def test_decorated_count_is_tolerated(self):
        # Regression: 'Count must contain an integer, got 1 +8? Let's number:'
        parsed = self._parse_sections(
            "[Caption]\ncap\n[Lyrics]\n[Intro]\n[Count]\n1 +8? Let's number:\n[Title]\nt\n[Image_Prompt]\nimg"
        )
        self.assertEqual(parsed["count_override"], 1)

    def test_count_without_integer_is_ignored(self):
        parsed = self._parse_sections(
            "[Caption]\ncap\n[Lyrics]\n[Intro]\n[Song-Count]\nseveral songs\n[Title]\nt\n[Image_Prompt]\nimg"
        )
        self.assertIsNone(parsed["count_override"])

    def test_out_of_range_count_is_clamped(self):
        parsed = self._parse_sections(
            "[Caption]\ncap\n[Lyrics]\n[Intro]\n[Count]\n250\n[Title]\nt\n[Image_Prompt]\nimg"
        )
        self.assertEqual(parsed["count_override"], 100)
        parsed = self._parse_sections(
            "[Caption]\ncap\n[Lyrics]\n[Intro]\n[Count]\n0\n[Title]\nt\n[Image_Prompt]\nimg"
        )
        self.assertEqual(parsed["count_override"], 1)


class ParserFallbackTests(unittest.TestCase):
    """The parser's LLM input is optional since 2.0.0; manual fields take over."""

    def _parse(self, structured_llm_output=None, **overrides):
        kwargs = dict(
            song_count=1,
            seed_mode="increment_from_base",
            base_seed=7,
            user_prompt="a user prompt",
            source_name_override="",
            fallback_title="llm-song",
            structured_llm_output=structured_llm_output,
            manual_caption="",
            manual_lyrics="",
            manual_title="",
            manual_image_prompt="",
            model_check_report="",
        )
        kwargs.update(overrides)
        return parser_node().parse(**kwargs)

    def test_manual_fallback_without_llm(self):
        result = self._parse(
            None,
            manual_caption="Manual caption text.",
            manual_lyrics="[Intro]\n[Verse]",
            manual_title="Manual Title",
            manual_image_prompt="A square cover, no text.",
        )
        self.assertEqual(result[0], ["Manual caption text."])
        self.assertEqual(result[1], ["[Intro]\n[Verse]"])
        self.assertEqual(result[2], ["Manual Title"])
        # The text-free prohibition is appended so FLUX never renders lettering.
        self.assertIn("A square cover, no text.", result[3][0])
        self.assertTrue(result[3][0].endswith(MODULES["minimax_prompt_source"].NO_TEXT_PROHIBITION))
        self.assertEqual(result[5], [7])
        provenance = json.loads(result[10][0])
        self.assertEqual(provenance["source_mode"], "manual_override")
        self.assertTrue(provenance["manual_fields_used"])

    def test_image_prompt_fallback_is_built_without_manual(self):
        result = self._parse(
            None,
            manual_caption="Caption only.",
            manual_lyrics="[Intro]",
            manual_title="Fallback Cover Song",
        )
        self.assertEqual(result[2], ["Fallback Cover Song"])
        self.assertIn("Caption only.", result[3][0])
        self.assertIn("No text", result[3][0])

    def test_empty_llm_without_manual_fallback_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._parse("")
        self.assertIn("no manual fallback", str(ctx.exception))

    def test_empty_llm_with_status_reports_upstream_failure(self):
        # The integrated LLM chat node's status output is wired into the parser;
        # a failed/empty generation must be recognizable as such, not as a format error.
        with self.assertRaises(ValueError) as ctx:
            self._parse("", llm_status="LLM disabled (enabled=False): returning empty text.")
        self.assertIn("LLM disabled (enabled=False)", str(ctx.exception))

    def test_unparseable_llm_with_status_keeps_upstream_hint(self):
        with self.assertRaises(ValueError) as ctx:
            self._parse("[Caption]\ncap\n[Lyrics]", llm_status="LLM ok: chars=42")
        self.assertIn("Upstream LLM status: LLM ok: chars=42", str(ctx.exception))

    def test_llm_output_still_parses_as_before(self):
        raw = "[Caption]\nLLM caption\n\n[Lyrics]\n[Intro]\n[Title]\nLLM Title\n\n[Image_Prompt]\nLLM image"
        result = self._parse(raw)
        self.assertEqual(result[0], ["LLM caption"])
        self.assertEqual(result[2], ["LLM Title"])
        provenance = json.loads(result[10][0])
        self.assertEqual(provenance["source_mode"], "external_comfyui_llm")

    def test_input_types_contract(self):
        data = parser_node.INPUT_TYPES()
        required = data["required"]
        optional = data["optional"]
        self.assertEqual(list(required)[:3], ["song_count", "seed_mode", "base_seed"])
        self.assertIn("structured_llm_output", optional)
        for field in ("manual_caption", "manual_lyrics", "manual_title", "manual_image_prompt", "model_check_report", "llm_status"):
            self.assertIn(field, optional)


class ParserLeakAndImagePromptTests(unittest.TestCase):
    """LLMs may leak planning text behind an early section header; the parsed
    image prompt must stay the clean final section and always end with the
    text-free prohibition (regression: covers rendered with lots of text)."""

    def _parse_sections(self, text):
        return MODULES["minimax_prompt_source"]._parse_sections(text)

    def test_repeated_section_header_last_occurrence_wins(self):
        raw = (
            "[Image_Prompt]\n"
            "planning draft: maybe a lantern, no text. Need end exact prohibition. Good.\n"
            "Need Caption word count <=120? Let's craft tight.\n"
            "[Caption]\n"
            "Global Metadata\n"
            "Basic Attributes: bpm is 72. key is D, and scale is Dorian. Nordic Folk / Atmospheric Folk.\n"
            "[Lyrics]\n"
            "[Intro]\n"
            "[Verse]\n"
            "[Title]\n"
            "The Snow-Kept Road\n"
            "[Image_Prompt]\n"
            "Square album cover artwork, a lantern in a snowy pine forest, no text, no letters, no words.\n"
        )
        parsed = self._parse_sections(raw)
        self.assertEqual(parsed["title"], "The Snow-Kept Road")
        self.assertNotIn("planning draft", parsed["image_prompt"])
        self.assertNotIn("Let's craft tight", parsed["image_prompt"])
        self.assertIn("Square album cover artwork", parsed["image_prompt"])
        self.assertIn("no text, no letters", parsed["image_prompt"])

    def test_single_header_behavior_is_unchanged(self):
        raw = "[Caption]\ncap\n[Lyrics]\n[Intro]\n[Title]\nt\n[Image_Prompt]\nimg"
        parsed = self._parse_sections(raw)
        self.assertEqual(parsed["caption"], "cap")
        self.assertEqual(parsed["image_prompt"], "img")

    def test_title_ellipsis_and_blank_lines_are_stripped(self):
        # Regression: the LLM wrote "...\n\n\nThe Snow-Kept Road" as the
        # title; the newlines became underscores in the filename.
        raw = (
            "[Caption]\ncap\n[Lyrics]\n[Intro]\n[Title]\n...\n\n\nThe Snow-Kept Road\n"
            "[Image_Prompt]\nimg, no text, no letters"
        )
        parsed = self._parse_sections(raw)
        self.assertEqual(parsed["title"], "The Snow-Kept Road")

    def test_no_text_prohibition_is_appended_when_missing(self):
        mod = MODULES["minimax_prompt_source"]
        text, appended = mod.ensure_no_text_prohibition("A calm forest cover.")
        self.assertTrue(appended)
        self.assertTrue(text.endswith(mod.NO_TEXT_PROHIBITION))

        text2, appended2 = mod.ensure_no_text_prohibition("A cover, no text, no letters, done.")
        self.assertFalse(appended2)
        self.assertNotIn("No text, no letters, no words", text2)

    def test_parser_keeps_clean_image_prompt_from_leaked_llm_output(self):
        raw = (
            "[Image_Prompt]\n"
            "planning: need end exact prohibition. Good.\n"
            "[Caption]\n"
            "Global Metadata\n"
            "Basic Attributes: bpm is 72. key is D. Nordic Folk.\n"
            "[Lyrics]\n"
            "[Intro]\n"
            "[Title]\n"
            "The Snow-Kept Road\n"
            "[Image_Prompt]\n"
            "Square album cover artwork, a lantern in snow, cold blue palette."
        )
        result = parser_node().parse(
            song_count=1,
            seed_mode="increment_from_base",
            base_seed=7,
            user_prompt="a user prompt",
            source_name_override="",
            fallback_title="llm-song",
            structured_llm_output=raw,
        )
        image_prompt = result[3][0]
        self.assertNotIn("planning", image_prompt)
        self.assertNotIn("Good.", image_prompt)
        self.assertIn("Square album cover artwork", image_prompt)
        # The prohibition was missing in the LLM text -> appended by the parser.
        self.assertTrue(image_prompt.endswith(MODULES["minimax_prompt_source"].NO_TEXT_PROHIBITION))


if __name__ == "__main__":
    unittest.main()
