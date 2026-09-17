"""Cover lyrics modes: score rewrite, syllable map, Whisper gate and prompt wiring.

No model weights, no downloads and no GPU: the Whisper engine is replaced by a
recording stub, so these tests prove the wiring and the contracts, not the
transcription quality.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from _toolkit_bootstrap import load_entry_point

ROOT = Path(__file__).resolve().parents[1]

# A SheetSage2-shaped score: two voices, structure labels, chords on the vocal
# voice and one tie per section.  Section syllable counts are intro 4,
# verse 5, chorus 5.
ABC = """X:1
T:
M:4/4
L:1/8
Q:1/4=100
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% intro
V: Vocal
z2 "Cmaj7"C2 E2 G2-|G2 c2 z4|
V: Ins
C,2 G,2 C2 E2|G2 c2 z4|
% verse
V: Vocal
"Cmaj7"C2 D2 E2 F2|"Fmaj7"G4- G2 z2|
V: Ins
C,2 G,2 C2 E2|F,2 C2 F2 A2|
% chorus
V: Vocal
"Am7"A2 A2 c2 c2|"Fmaj7"f4 z4|
V: Ins
A,2 E2 A2 C2|F,2 C2 F2 A2|
"""


class CoverScoreTests(unittest.TestCase):
    """The pure ABC parser, rewrite and syllable measurement."""

    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.score = importlib.import_module(cls.pkg.__name__ + ".cover_score")

    def test_sections_and_syllables_come_from_the_vocal_voice(self):
        parsed = self.score.parse_cover_score(ABC)
        self.assertEqual(parsed.voices, ["Vocal", "Ins"])
        self.assertTrue(parsed.has_vocal_voice)
        self.assertEqual([s.label for s in parsed.sections], ["intro", "verse", "chorus"])
        self.assertEqual([s.syllables() for s in parsed.sections], [4, 5, 5])
        self.assertEqual(parsed.total_syllables(), 14)

    def test_ties_rests_and_chords_do_not_add_syllables(self):
        count = self.score.count_melody_notes
        self.assertEqual(count("C2-C2 C2 z2 D4"), 3)
        self.assertEqual(count('"Cmaj7"C2 "Fmaj7"F2'), 2)
        self.assertEqual(count("z8"), 0)
        self.assertEqual(count(""), 0)

    def test_lyric_writing_modes_hand_the_score_back_unchanged(self):
        for mode in (self.score.LYRICS_MODE_NEW, self.score.LYRICS_MODE_ORIGINAL):
            result = self.score.adapt_cover_score(ABC, mode)
            self.assertEqual(result["abc"], ABC)
            self.assertFalse(result["adapted"])
            self.assertEqual(result["changes"], [])
            self.assertEqual(result["syllables"]["total_syllables"], 14)

    def test_instrumental_mode_retargets_the_vocal_voice_and_keeps_the_music(self):
        result = self.score.adapt_cover_score(ABC, self.score.LYRICS_MODE_INSTRUMENTAL, "Piano")
        self.assertTrue(result["adapted"])
        self.assertIn("lead_blocks_moved_to_Ins:3", result["changes"][0])
        self.assertIn('V: Ins clef=treble name="Ins Melody" snm="Inst."', result["abc"])
        self.assertIn("Vocal Melody", result["abc"])
        # The former vocal line is still there, note for note - it is played,
        # not deleted.
        original = self.score.parse_cover_score(ABC)
        adapted = self.score.parse_cover_score(result["abc"])
        self.assertEqual([s.syllables("Ins") for s in adapted.sections],
                         [s.syllables("Vocal") for s in original.sections])
        self.assertEqual(adapted.total_syllables(), 0)

    def test_instrumental_mode_can_drop_the_vocal_line_entirely(self):
        result = self.score.adapt_cover_score(
            ABC, self.score.LYRICS_MODE_INSTRUMENTAL, self.score.REMOVE_LEAD_INSTRUMENT)
        self.assertEqual(result["removed_voice"], "Vocal")
        self.assertEqual(self.score.parse_cover_score(result["abc"]).total_syllables(), 0)
        self.assertIn("V: Vocal", result["abc"])
        self.assertIn("V: Ins", result["abc"])

    def test_a_score_without_a_vocal_voice_is_reported_not_invented(self):
        plain = "X:1\nM:4/4\nL:1/8\nK:C\nV: Lead\nC2 E2|\n"
        result = self.score.adapt_cover_score(plain, self.score.LYRICS_MODE_INSTRUMENTAL)
        self.assertIn("V: Lead\nC2 E2|", result["abc"])
        self.assertEqual(result["syllables"]["total_syllables"], 0)

    def test_field_values_are_normalized_against_typos_and_legacy_payloads(self):
        self.assertEqual(self.score.normalize_lyrics_mode("Original Vocals"),
                         self.score.LYRICS_MODE_ORIGINAL)
        self.assertEqual(self.score.normalize_lyrics_mode("Whisper"),
                         self.score.LYRICS_MODE_ORIGINAL)
        self.assertEqual(self.score.normalize_lyrics_mode("instrumental"),
                         self.score.LYRICS_MODE_INSTRUMENTAL)
        self.assertEqual(self.score.normalize_lyrics_mode(""), self.score.DEFAULT_LYRICS_MODE)
        self.assertEqual(self.score.normalize_lyrics_mode(None), self.score.DEFAULT_LYRICS_MODE)
        self.assertEqual(self.score.normalize_lead_instrument("piano"), "Piano")
        self.assertEqual(self.score.normalize_lead_instrument(""),
                         self.score.DEFAULT_LEAD_INSTRUMENT)

    def test_syllable_brief_lists_every_section(self):
        brief = self.score.score_syllable_brief(self.score.parse_cover_score(ABC).syllable_map())
        self.assertIn("01 [intro]: 4 note onsets", brief)
        self.assertIn("03 [chorus]: 5 note onsets", brief)
        self.assertIn("Total: 14 note onsets", brief)


class CoverSourceTests(unittest.TestCase):
    """The lyrics choice travels inside the existing cover source payload."""

    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.mod = importlib.import_module(cls.pkg.__name__ + ".music_cover")
        cls.score = importlib.import_module(cls.pkg.__name__ + ".cover_score")

    def node(self, name):
        return self.pkg.NODE_CLASS_MAPPINGS[name]()

    def profile(self, name="YuE2 Cover"):
        return self.pkg.NODE_CLASS_MAPPINGS["MusicProductionControl"]().build(name)[0]

    def test_new_widgets_are_appended_and_defaulted(self):
        spec = self.node("MusicCoverSource").INPUT_TYPES()["required"]
        self.assertEqual(
            list(spec)[-2:], ["lyrics_mode", "lead_instrument"],
            "new widgets must stay last: stored widget values are positional",
        )
        self.assertEqual(spec["lyrics_mode"][0], list(self.score.LYRICS_MODES))
        # Standard since 2026-09-18: instrumental needs no Whisper engine, so it is the
        # mode that works out of the box.
        self.assertEqual(spec["lyrics_mode"][1]["default"], "instrumental")
        self.assertEqual(spec["lead_instrument"][1]["default"], "Lead synth")

    def test_record_carries_the_mode_and_survives_legacy_payloads(self):
        record = self.mod.cover_record(json.dumps({
            "schema": "music_cover_source_v1", "audio": "Night.theme.wav", "mode": "full",
            "audio_encoder": "sheetsage2_bf16.safetensors",
            "lyrics_mode": "original lyrics", "lead_instrument": "Strings"}))
        self.assertEqual(record["lyrics_mode"], "original lyrics")
        self.assertEqual(record["lead_instrument"], "Strings")
        legacy = self.mod.cover_record(json.dumps({
            "schema": "music_cover_source_v1", "audio": "Night.theme.wav", "mode": "full",
            "audio_encoder": "sheetsage2_bf16.safetensors"}))
        self.assertEqual(legacy["lyrics_mode"], "instrumental",
                         "a payload without a mode gets the current default")
        self.assertEqual(legacy["lead_instrument"], "Lead synth")

    def test_select_writes_the_choice_into_the_source_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "song.wav"
            path.write_bytes(b"audio fixture")
            host = types.SimpleNamespace(get_annotated_filepath=lambda _: str(path))
            with patch.dict(sys.modules, {"folder_paths": host}):
                payload, title = self.node("MusicCoverSource").select(
                    self.profile(), "song.wav", lyrics_mode="instrumental",
                    lead_instrument="Piano")
        data = json.loads(payload)
        self.assertEqual(data["lyrics_mode"], "instrumental")
        self.assertEqual(data["lead_instrument"], "Piano")
        self.assertEqual(title, "song-cover")

    def test_cache_signature_changes_with_the_lyrics_choice(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "song.wav"
            path.write_bytes(b"audio fixture")
            host = types.SimpleNamespace(get_annotated_filepath=lambda _: str(path))
            with patch.dict(sys.modules, {"folder_paths": host}):
                first = self.node("MusicCoverSource").IS_CHANGED(
                    self.profile(), "song.wav", "new lyrics", "Lead synth")
                second = self.node("MusicCoverSource").IS_CHANGED(
                    self.profile(), "song.wav", "instrumental", "Lead synth")
        self.assertNotEqual(first, second)


class CoverScoreNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.mod = importlib.import_module(cls.pkg.__name__ + ".music_cover")

    def node(self):
        return self.pkg.NODE_CLASS_MAPPINGS["MusicCoverScore"]()

    def source(self, lyrics_mode, lead_instrument="Lead synth"):
        return json.dumps({"schema": "music_cover_source_v1", "audio": "Night.wav",
                           "mode": "full", "audio_encoder": "sheetsage2_bf16.safetensors",
                           "lyrics_mode": lyrics_mode, "lead_instrument": lead_instrument})

    def test_inactive_without_a_cover_source(self):
        self.assertEqual(self.node().adapt("", ABC), ("", "", json.dumps({"status": "inactive"})))

    def test_empty_transcription_stops_the_run(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            self.node().adapt(self.source("new lyrics"), "  ")

    def test_instrumental_reports_the_rewrite_and_the_syllables(self):
        abc, brief, report = self.node().adapt(
            self.source("instrumental", "Piano"), ABC)
        self.assertIn('name="Ins Melody"', abc)
        self.assertIn("Total: 14 note onsets", brief)
        data = json.loads(report)
        self.assertEqual(data["schema"], "music_cover_score_v1")
        self.assertTrue(data["adapted"])
        self.assertEqual(data["lead_instrument"], "Piano")
        self.assertEqual(data["syllables"]["sections"][0]["melody_notes"], 4)

    def test_lyric_modes_pass_the_score_through(self):
        abc, _brief, report = self.node().adapt(self.source("new lyrics"), ABC)
        self.assertEqual(abc, ABC)
        self.assertFalse(json.loads(report)["adapted"])


class CoverLyricsNodeTests(unittest.TestCase):
    """The Whisper node must be a no-op outside its one combination."""

    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.mod = importlib.import_module(cls.pkg.__name__ + ".whisper_lyrics")

    def node(self):
        return self.pkg.NODE_CLASS_MAPPINGS["MusicCoverLyrics"]()

    def profile(self, name="YuE2 Cover"):
        return self.pkg.NODE_CLASS_MAPPINGS["MusicProductionControl"]().build(name)[0]

    def source(self, lyrics_mode):
        return json.dumps({"schema": "music_cover_source_v1", "audio": "Night.wav",
                           "mode": "full", "audio_encoder": "sheetsage2_bf16.safetensors",
                           "lyrics_mode": lyrics_mode, "lead_instrument": "Lead synth"})

    def test_other_models_do_not_touch_the_engine(self):
        with patch.dict(sys.modules, {"faster_whisper": None}):
            for name in ("YuE2", "MiniMax Music 3"):
                text, report = self.node().transcribe_lyrics(self.profile(name), self.source("original lyrics"))
                self.assertEqual(text, "")
                self.assertEqual(json.loads(report)["status"], "inactive")

    def test_other_lyrics_modes_do_not_load_a_checkpoint(self):
        for mode in ("instrumental",):
            text, report = self.node().transcribe_lyrics(self.profile(), self.source(mode))
            self.assertEqual(text, "")
            data = json.loads(report)
            self.assertEqual(data["status"], "not_requested")
            self.assertEqual(data["lyrics_mode"], mode)

    def test_missing_checkpoint_names_the_folder_and_the_way_out(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(self.mod, "whisper_model_dir", lambda _model="": Path(folder) / "absent"):
                with self.assertRaisesRegex(RuntimeError, "does not exist"):
                    self.mod.transcribe("song.wav")

    def test_missing_engine_is_reported_only_when_it_is_needed(self):
        with patch.dict(sys.modules, {"faster_whisper": None}):
            with tempfile.TemporaryDirectory() as folder:
                with patch.object(self.mod, "whisper_model_dir", lambda _model="": Path(folder)):
                    with self.assertRaisesRegex(RuntimeError, "requirements-whisper.txt"):
                        self.mod.transcribe("song.wav")

    def test_engine_missing_is_explained_by_import_error(self):
        real_import = __import__

        def blocked(name, *args, **kwargs):
            if name == "faster_whisper":
                raise ImportError("no faster_whisper")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=blocked):
            self.mod._MODEL_CACHE.clear()
            with self.assertRaisesRegex(RuntimeError, "faster-whisper"):
                self.mod._load_engine()

    def test_the_checkpoint_is_released_after_every_transcription(self):
        class Model:
            def transcribe(self, samples, **kwargs):
                return iter([]), types.SimpleNamespace(
                    language="en", language_probability=0.5, duration=3.0)

        with tempfile.TemporaryDirectory() as folder:
            model_dir = Path(folder)
            with patch.object(self.mod, "_load_engine",
                              lambda: (lambda path, device, compute_type: Model())), \
                 patch.object(self.mod, "whisper_model_dir", lambda _model="": model_dir), \
                 patch.object(self.mod, "load_audio_mono",
                              lambda path, target_rate=16000: [0.0] * 16000):
                self.mod._MODEL_CACHE.clear()
                with self.assertRaisesRegex(ValueError, "Whisper returned no lyrics"):
                    self.mod.transcribe("song.wav")
        # The music stage must not find a stale 3 GB checkpoint in the cache.
        self.assertEqual(self.mod._MODEL_CACHE, {})

    def test_transcription_records_what_actually_ran(self):
        class Segment:
            def __init__(self, start, end, text):
                self.start, self.end, self.text = start, end, text

        class Info:
            language = "en"
            language_probability = 0.98
            duration = 12.0

        class Model:
            def __init__(self, path, device, compute_type):
                self.path, self.device, self.compute_type = path, device, compute_type

            def transcribe(self, samples, **kwargs):
                self.kwargs = kwargs
                return iter([Segment(0.0, 4.0, " I left a lantern "),
                             Segment(4.0, 8.0, "by the door "),
                             Segment(8.0, 12.0, "  ")]), Info()

        created = {}

        def fake_model_class(path, device, compute_type):
            created["path"] = path
            created["device"] = device
            created["compute_type"] = compute_type
            return Model(path, device, compute_type)

        with tempfile.TemporaryDirectory() as folder:
            model_dir = Path(folder)
            with patch.object(self.mod, "_load_engine", lambda: fake_model_class), \
                 patch.object(self.mod, "whisper_model_dir", lambda _model="": model_dir), \
                 patch.object(self.mod, "load_audio_mono", lambda path, target_rate=16000: [0.0] * 16000), \
                 patch.object(self.mod, "_resolve_device", lambda device, compute: ("cpu", "int8")):
                self.mod._MODEL_CACHE.clear()
                record = self.mod.transcribe("song.wav", language="en")
        self.assertEqual(record["text"], "I left a lantern\nby the door")
        self.assertEqual(record["language"], "en")
        self.assertEqual(record["segment_count"], 2)
        self.assertEqual(record["compute_type"], "int8")
        self.assertEqual(created["device"], "cpu")
        self.assertEqual(Path(created["path"]).name, model_dir.name)
        self.assertTrue(record["characters"])


class StructuredPromptCoverTests(unittest.TestCase):
    """The three modes must reach the LLM prompt and pin the Lyrics field."""

    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.node = cls.pkg.NODE_CLASS_MAPPINGS["MiniMaxStructuredPromptV20"]()

    def profile(self):
        return self.pkg.NODE_CLASS_MAPPINGS["MusicProductionControl"]().build("YuE2 Cover")[0]

    def args(self, lyrics_mode, lyrics_field="custom", cover_lyrics=""):
        spec = self.node.INPUT_TYPES()
        args = {name: options[1].get("default", options[0][0] if isinstance(options[0], list) else "")
                for name, options in spec["required"].items()}
        args.update(
            user_prompt_source="manual",
            description_override="A varied arrangement of the source",
            lyrics=lyrics_field,
            model_profile_json=self.profile(),
            cover_source_json=json.dumps({
                "schema": "music_cover_source_v1", "audio": "Night.wav", "mode": "full",
                "audio_encoder": "sheetsage2_bf16.safetensors",
                "lyrics_mode": lyrics_mode, "lead_instrument": "Piano"}),
            cover_abc=ABC,
            cover_lyrics=cover_lyrics,
        )
        return args

    def test_new_lyrics_mode_sends_the_measured_syllable_map(self):
        system, user, _name, summary = self.node.build(**self.args("new lyrics", "custom"))
        self.assertIn("MELODY PHRASING MAP", user)
        self.assertIn("01 [intro]: 4 note onsets", user)
        self.assertIn("LYRICS MODE - NEW LYRICS", system)
        self.assertIn("syllable", system)
        self.assertEqual(json.loads(summary)["cover_syllables"]["total_syllables"], 14)

    def test_instrumental_mode_pins_the_lyrics_field_and_the_instrument(self):
        system, user, _name, summary = self.node.build(
            **self.args("instrumental", lyrics_field="yes"))
        data = json.loads(summary)
        self.assertEqual(data["fields"]["lyrics"], "instrumental")
        self.assertEqual(data["forced_lyrics_field"], "instrumental")
        self.assertIn("LYRICS MODE - INSTRUMENTAL", system)
        self.assertIn("Piano", system)
        self.assertIn("INSTRUMENTAL CONSTRAINT", user)
        # The prompt and the generator must plan against the same rewritten score.
        self.assertIn('"lead_instrument": "Piano"', user)

    def test_original_lyrics_mode_uses_the_transcription_verbatim(self):
        record = json.dumps({"schema": "music_cover_lyrics_v1", "model": "whisper-large-v3",
                             "device": "cuda", "compute_type": "float16", "language": "en",
                             "language_probability": 0.97, "segment_count": 2,
                             "characters": 31, "text": "I left a lantern\nby the door"})
        system, user, _name, summary = self.node.build(
            **self.args("original lyrics", lyrics_field="instrumental", cover_lyrics=record))
        self.assertEqual(json.loads(summary)["fields"]["lyrics"], "yes")
        self.assertIn("COVER LYRICS", user)
        self.assertIn("I left a lantern", user)
        self.assertIn("LYRICS MODE - ORIGINAL LYRICS", system)
        data = json.loads(summary)
        self.assertEqual(data["cover_lyrics"]["model"], "whisper-large-v3")
        self.assertEqual(data["cover_lyrics_chars"], len("I left a lantern\nby the door"))
        self.assertNotIn("segments", data["cover_lyrics"])

    def test_original_lyrics_without_a_transcription_says_so(self):
        with self.assertRaisesRegex(ValueError, "non-empty Whisper"):
            self.node.build(**self.args("original lyrics", lyrics_field="yes"))

    def test_a_plain_text_transcript_is_accepted(self):
        _system, user, _name, summary = self.node.build(
            **self.args("original lyrics", "yes", cover_lyrics="I left a lantern"))
        self.assertIn("I left a lantern", user)
        self.assertIsNone(json.loads(summary)["cover_lyrics"])

    def test_the_cache_signature_follows_the_transcription(self):
        args = self.args("original lyrics", "yes", cover_lyrics="first words")
        first = self.node.IS_CHANGED(**args)
        self.assertNotEqual(first, self.node.IS_CHANGED(**(args | {"cover_lyrics": "other words"})))


class ParserCoverLyricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.mod = importlib.import_module(cls.pkg.__name__ + ".minimax_prompt_source")

    def test_record_and_plain_text_are_both_understood(self):
        record = json.dumps({"schema": "music_cover_lyrics_v1", "text": "hello there"})
        self.assertEqual(self.mod._cover_lyrics_payload(record)[1], "hello there")
        self.assertEqual(self.mod._cover_lyrics_payload("hello there"), (None, "hello there"))
        self.assertEqual(self.mod._cover_lyrics_payload(""), (None, ""))

    def test_word_coverage_is_informative_not_a_gate(self):
        self.assertIsNone(self.mod._lyrics_word_coverage("", "anything"))
        self.assertEqual(self.mod._lyrics_word_coverage("lantern door", "lantern door"), 1.0)
        self.assertEqual(self.mod._lyrics_word_coverage("lantern door", "nothing here"), 0.0)
        self.assertEqual(self.mod._lyrics_word_coverage("the and", "the and"), None)


class CoverGenerationTests(unittest.TestCase):
    """The generator must receive the score the selected mode calls for."""

    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        from test_yue2 import Graph
        cls.graph_module = types.SimpleNamespace(GraphBuilder=Graph)

    def profile(self, name="YuE2 Cover"):
        return self.pkg.NODE_CLASS_MAPPINGS["MusicProductionControl"]().build(name)[0]

    def source(self, lyrics_mode, lead_instrument="Piano"):
        return json.dumps({"schema": "music_cover_source_v1", "audio": "Night.theme.wav",
                           "mode": "full", "audio_encoder": "sheetsage2_bf16.safetensors",
                           "lyrics_mode": lyrics_mode, "lead_instrument": lead_instrument})

    def settings(self, source):
        node = self.pkg.NODE_CLASS_MAPPINGS["MiniMaxMusicModelSettings"]()
        args = {name: options[1]["default"]
                for name, options in node.INPUT_TYPES()["required"].items() if "default" in options[1]}
        return node.build(**args, generation_seed=42, profile_json=self.profile(),
                          cover_source_json=source, yue2_max_duration=360)[-1]

    def generated_abc(self, lyrics_mode, abc=ABC):
        source = self.source(lyrics_mode)
        with patch.dict(sys.modules, {"comfy_execution.graph_utils": self.graph_module}):
            expanded = self.pkg.NODE_CLASS_MAPPINGS["MusicGeneration"]().generate(
                self.profile(), self.settings(source), "folk", "[Verse]\nNew words here" if lyrics_mode != "instrumental" else "[Instrumental]",
                "yue.safetensors", "dit", "clip", "vae",
                cover_source_json=source, cover_abc=abc)["expand"]
        return {node["class_type"]: node["inputs"] for node in expanded.values()}

    def test_instrumental_cover_sends_the_rewritten_score_to_yue2(self):
        nodes = self.generated_abc("instrumental")
        self.assertIn("Ins Melody", nodes["YuE2GenerateMusic"]["abc"])
        self.assertIn("Vocal Melody", nodes["YuE2GenerateMusic"]["abc"])

    def test_lyric_modes_send_the_original_score_unchanged(self):
        for mode in ("new lyrics", "original lyrics"):
            self.assertEqual(self.generated_abc(mode)["YuE2GenerateMusic"]["abc"], ABC)

    def test_the_rewrite_is_idempotent(self):
        # The bundled graph runs the score node and the generator applies the
        # same rewrite again; both must land on the same string.
        once = self.generated_abc("instrumental")["YuE2GenerateMusic"]["abc"]
        twice = self.generated_abc("instrumental", abc=once)["YuE2GenerateMusic"]["abc"]
        self.assertEqual(once, twice)

    def test_the_prompt_and_the_generator_agree(self):
        source = self.source("instrumental")
        node = self.pkg.NODE_CLASS_MAPPINGS["MiniMaxStructuredPromptV20"]()
        args = {name: options[1].get("default", options[0][0] if isinstance(options[0], list) else "")
                for name, options in node.INPUT_TYPES()["required"].items()}
        args.update(user_prompt_source="manual", description_override="arrangement",
                    model_profile_json=self.profile(), cover_source_json=source, cover_abc=ABC)
        _system, user, _name, _summary = node.build(**args)
        generated = self.generated_abc("instrumental")["YuE2GenerateMusic"]["abc"]
        self.assertIn(json.dumps(generated, ensure_ascii=False), user)


class CoverChainEndToEndTests(unittest.TestCase):
    """The whole cover chain with a simulated LLM answer.

    source -> SheetSage2 score -> score node -> LLM prompt -> LLM text ->
    parser -> Generate song.  These are the assertions that answer "does the
    rewritten score / the new words / the Whisper words really arrive at the
    engine?" without any model weights.
    """

    WHISPER_TEXT = "I left a lantern by the door\nits little sun across the floor"

    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        from test_yue2 import Graph
        cls.Graph = Graph

    # -- helpers ---------------------------------------------------------
    def profile(self, name="YuE2 Cover"):
        return self.pkg.NODE_CLASS_MAPPINGS["MusicProductionControl"]().build(name)[0]

    def source(self, lyrics_mode, lead="Piano"):
        return json.dumps({"schema": "music_cover_source_v1", "audio": "Night.theme.wav",
                           "mode": "full", "audio_encoder": "sheetsage2_bf16.safetensors",
                           "lyrics_mode": lyrics_mode, "lead_instrument": lead})

    def whisper_record(self):
        return json.dumps({"schema": "music_cover_lyrics_v1", "source": "Whisper (faster-whisper)",
                           "model": "whisper-large-v3", "device": "cuda", "compute_type": "float16",
                           "language": "en", "language_probability": 0.97, "segment_count": 2,
                           "characters": len(self.WHISPER_TEXT), "text": self.WHISPER_TEXT})

    def build_prompt(self, cover_abc, lyrics_mode, cover_lyrics="", lyrics_field="yes"):
        node = self.pkg.NODE_CLASS_MAPPINGS["MiniMaxStructuredPromptV20"]()
        args = {name: options[1].get("default", options[0][0] if isinstance(options[0], list) else "")
                for name, options in node.INPUT_TYPES()["required"].items()}
        args.update(user_prompt_source="manual", description_override="A folk-pop arrangement",
                    lyrics=lyrics_field, model_profile_json=self.profile(),
                    cover_source_json=self.source(lyrics_mode), cover_abc=cover_abc,
                    cover_lyrics=cover_lyrics)
        return node.build(**args)

    def settings(self, source):
        node = self.pkg.NODE_CLASS_MAPPINGS["MiniMaxMusicModelSettings"]()
        spec = node.INPUT_TYPES()["required"]
        args = {name: options[1]["default"] for name, options in spec.items() if "default" in options[1]}
        return node.build(**args, generation_seed=42, profile_json=self.profile(),
                          cover_source_json=source, yue2_max_duration=360)[-1]

    def parse(self, raw, source, summary, user_prompt, cover_lyrics=""):
        node = self.pkg.NODE_CLASS_MAPPINGS["MiniMaxParseExternalLLMOutputV16"]()
        return node.parse(1, "fixed", 1, user_prompt, "", "llm-song", structured_llm_output=raw,
                          manual_caption="", manual_lyrics="", manual_title="",
                          manual_image_prompt="", model_profile_json=self.profile(),
                          cover_source_json=source, structured_summary_json=summary,
                          cover_lyrics=cover_lyrics)

    def generate(self, source, settings_json, style, lyrics, cover_abc):
        module = types.ModuleType("comfy_execution.graph_utils")
        module.GraphBuilder = self.Graph
        with patch.dict(sys.modules, {"comfy_execution.graph_utils": module}):
            expanded = self.pkg.NODE_CLASS_MAPPINGS["MusicGeneration"]().generate(
                self.profile(), settings_json, style, lyrics, "yue2.safetensors", "dit", "clip", "vae",
                cover_source_json=source, cover_abc=cover_abc)["expand"]
        return {node["class_type"]: node["inputs"] for node in expanded.values()}

    # -- the three modes -------------------------------------------------
    def test_instrumental_cover_sends_the_rewritten_score_to_the_engine(self):
        source = self.source("instrumental")
        score_node = self.pkg.NODE_CLASS_MAPPINGS["MusicCoverScore"]()
        adapted, _brief, _report = score_node.adapt(source, ABC)
        system, user, _name, summary = self.build_prompt(adapted, "instrumental")
        self.assertIn('"lead_instrument": "Piano"', user, "the LLM receives the selected lead separately")
        self.assertIn("Vocal Melody", user)
        self.assertIn("LYRICS MODE - INSTRUMENTAL", system)
        raw = ("[Style]\nfolk-pop instrumental, 92 BPM\nArrangement (section order):\n"
               "01 [Intro]: piano theme\n02 [Verse]: piano theme\n03 [Chorus]: full band\n\n[Lyrics]\n[Intro]\n\n[Verse]\n\n[Chorus]\n\n"
               "[Title]\nLantern Glow\n\n[Image_Prompt]\nA quiet lamp. No text, letters, words.\n")
        parsed = self.parse(raw, source, summary, user)
        nodes = self.generate(source, self.settings(source), parsed[0][0], parsed[1][0], adapted)
        engine_abc = nodes["YuE2GenerateMusic"]["abc"]
        self.assertIn("Ins Melody", engine_abc)
        self.assertIn("Vocal Melody", engine_abc)
        # The bundled instruction for instrumentals forbids vocal-oriented section
        # tags, so the compiled text uses the instrumental vocabulary instead.  The
        # source labels stay in the report and in report_arrangement_tags.
        self.assertEqual(nodes["YuE2GenerateMusic"]["lyrics"],
                         "[Intro]\n\n[Instrumental]\n\n[Instrumental]")
        self.assertNotIn("Verse", nodes["YuE2GenerateMusic"]["lyrics"])
        self.assertNotIn("Chorus", nodes["YuE2GenerateMusic"]["lyrics"])
        conditioning = json.loads(nodes['MusicGenerationReceipt']['settings_json'])['cover_conditioning']
        self.assertEqual(conditioning['native_lyrics'], '[Intro]\n\n[Instrumental]\n\n[Instrumental]')
        self.assertEqual(conditioning['report_arrangement_tags'], ['Intro', 'Verse', 'Chorus'])
        self.assertEqual(conditioning['section_tag_map'],
                         {'2 Verse': 'Instrumental', '3 Chorus': 'Instrumental'})

    def test_new_lyrics_words_reach_the_engine(self):
        source = self.source("new lyrics")
        system, user, _name, summary = self.build_prompt(ABC, "new lyrics")
        self.assertIn("MELODY PHRASING MAP", user)
        self.assertIn("LYRICS MODE - NEW LYRICS", system)
        raw = ("[Style]\nfolk-pop, warm female voice, 92 BPM\nArrangement (section order):\n"
               "01 [Intro]: guitar\n02 [Verse]: voice over guitar\n03 [Chorus]: full band\n\n[Lyrics]\n[Intro]\n[Verse]\n"
               "I left a lantern by the door\nits little sun across the floor\n\n[Chorus]\n"
               "When the road runs out of light\nlet it bring you home tonight\n\n"
               "[Title]\nLantern Glow\n\n[Image_Prompt]\nA quiet lamp. No text, letters, words.\n")
        parsed = self.parse(raw, source, summary, user)
        nodes = self.generate(source, self.settings(source), parsed[0][0], parsed[1][0], ABC)
        self.assertEqual(nodes["YuE2GenerateMusic"]["abc"], ABC,
                         "a lyric-writing cover must keep the source score")
        self.assertIn("I left a lantern by the door", nodes["YuE2GenerateMusic"]["lyrics"])

    def test_whisper_words_travel_through_the_llm_to_the_engine(self):
        source = self.source("original lyrics")
        record = self.whisper_record()
        system, user, _name, summary = self.build_prompt(ABC, "original lyrics", cover_lyrics=record)
        self.assertIn(self.WHISPER_TEXT.splitlines()[0], user)
        self.assertIn("LYRICS MODE - ORIGINAL LYRICS", system)
        raw = ("[Style]\nfolk-pop cover, 92 BPM\nArrangement (section order):\n"
               "01 [Intro]: instrumental\n02 [Verse]: original vocal line\n03 [Chorus]: full band\n\n[Lyrics]\n[Intro]\n[Verse]\n"
               + self.WHISPER_TEXT
               + "\n\n[Chorus]\n\n[Title]\nLantern Glow\n\n"
               "[Image_Prompt]\nA quiet lamp. No text, letters, words.\n")
        parsed = self.parse(raw, source, summary, user, cover_lyrics=record)
        nodes = self.generate(source, self.settings(source), parsed[0][0], parsed[1][0], ABC)
        self.assertIn("I left a lantern by the door", nodes["YuE2GenerateMusic"]["lyrics"])
        provenance = json.loads(parsed[10][0])["cover_lyrics"]
        self.assertEqual(provenance["model"], "whisper-large-v3")
        self.assertEqual(provenance["lyrics_word_coverage"], 1.0)


class CoverGuardTests(unittest.TestCase):
    """Contradictions and data loss must be refused, not silently resolved."""

    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.prompt = cls.pkg.NODE_CLASS_MAPPINGS["MiniMaxStructuredPromptV20"]()
        cls.parser = cls.pkg.NODE_CLASS_MAPPINGS["MiniMaxParseExternalLLMOutputV16"]()

    def profile(self, name="YuE2 Cover"):
        return self.pkg.NODE_CLASS_MAPPINGS["MusicProductionControl"]().build(name)[0]

    def source(self, lyrics_mode):
        return json.dumps({"schema": "music_cover_source_v1", "audio": "Night.theme.wav",
                           "mode": "full", "audio_encoder": "sheetsage2_bf16.safetensors",
                           "lyrics_mode": lyrics_mode, "lead_instrument": "Piano"})

    def build(self, lyrics_mode, lyrics_field):
        args = {name: options[1].get("default", options[0][0] if isinstance(options[0], list) else "")
                for name, options in self.prompt.INPUT_TYPES()["required"].items()}
        args.update(user_prompt_source="manual", description_override="arrangement",
                    lyrics=lyrics_field, model_profile_json=self.profile(),
                    cover_source_json=self.source(lyrics_mode), cover_abc=ABC)
        return self.prompt.build(**args)

    def test_new_lyrics_cannot_be_asked_to_sing_nothing(self):
        for field in ("instrumental", "only voice - no words"):
            _system, _user, _name, summary = self.build("new lyrics", field)
            data = json.loads(summary)
            self.assertEqual(data["fields"]["lyrics"], "yes")
            self.assertEqual(data["forced_lyrics_field"], "yes")

    def test_new_lyrics_keeps_a_lyric_bearing_choice(self):
        for field in ("yes", "sparse"):
            _system, _user, _name, summary = self.build("new lyrics", field)
            data = json.loads(summary)
            self.assertEqual(data["fields"]["lyrics"], field)
            self.assertIsNone(data["forced_lyrics_field"])

    def parse(self, raw, lyrics_mode, cover_lyrics="", max_prompt_tokens=1200):
        return self.parser.parse(1, "fixed", 1, "brief", "", "llm-song", structured_llm_output=raw,
                                 manual_caption="", manual_lyrics="", manual_title="",
                                 manual_image_prompt="", model_profile_json=self.profile(),
                                 cover_source_json=self.source(lyrics_mode),
                                 structured_summary_json="", cover_lyrics=cover_lyrics,
                                 max_prompt_tokens=max_prompt_tokens, trim_long_prompt=True)

    def test_a_transcribed_cover_is_never_silently_trimmed(self):
        long_lyrics = "\n".join(f"[Verse]\nline number {i} of the original words here" for i in range(200))
        raw = ("[Style]\nfolk-pop arrangement\n[Lyrics]\n" + long_lyrics +
               "\n[Title]\nLantern Glow\n[Image_Prompt]\nA quiet lamp. No text.\n")
        record = json.dumps({"schema": "music_cover_lyrics_v1", "text": long_lyrics})
        with self.assertRaisesRegex(ValueError, "transcribed original lyrics"):
            self.parse(raw, "original lyrics", cover_lyrics=record, max_prompt_tokens=600)

    def test_the_trim_guard_does_not_fire_for_other_cover_modes(self):
        long_lyrics = "\n".join(f"[Verse]\nline number {i} of some new words here" for i in range(200))
        raw = ("[Style]\nfolk-pop arrangement\n[Lyrics]\n" + long_lyrics +
               "\n[Title]\nLantern Glow\n[Image_Prompt]\nA quiet lamp. No text.\n")
        with self.assertRaisesRegex(ValueError, "drop cover sections"):
            self.parse(raw, "new lyrics", max_prompt_tokens=600)

    def test_an_empty_llm_answer_mentions_the_available_transcription(self):
        record = json.dumps({"schema": "music_cover_lyrics_v1", "text": "the original words"})
        with self.assertRaisesRegex(ValueError, r"source transcription.*musical Style"):
            self.parse("", "original lyrics", cover_lyrics=record)


class CoverMetadataTests(unittest.TestCase):
    """Both cover reports must reach the canonical production JSON."""

    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.meta = importlib.import_module(cls.pkg.__name__ + ".production_metadata")

    def test_cover_section_is_omitted_without_cover_reports(self):
        payload = self.meta.build_generation_metadata({})
        self.assertNotIn("cover", payload)

    def test_cover_section_records_score_and_lyrics_source(self):
        payload = self.meta.build_generation_metadata(
            {},
            cover_score_json=json.dumps({"schema": "music_cover_score_v1", "adapted": True}),
            cover_lyrics_json=json.dumps({"schema": "music_cover_lyrics_v1", "model": "whisper-large-v3"}),
        )
        self.assertTrue(payload["cover"]["score"]["adapted"])
        self.assertEqual(payload["cover"]["lyrics_source"]["model"], "whisper-large-v3")

    def test_the_writer_accepts_the_two_new_reports(self):
        socket = self.pkg.NODE_CLASS_MAPPINGS["MiniMaxSaveProductionJSON"].INPUT_TYPES()["optional"]
        for name in ("cover_score_json", "cover_lyrics_json"):
            self.assertIn(name, socket)
            self.assertTrue(socket[name][1].get("forceInput"))


class WhisperCatalogTests(unittest.TestCase):
    """The pinned checkpoint must be downloadable and resolvable as one folder."""

    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.downloader = importlib.import_module(cls.pkg.__name__ + ".model_downloader")
        cls.whisper = importlib.import_module(cls.pkg.__name__ + ".whisper_lyrics")

    def test_catalog_entry_is_pinned_and_complete(self):
        config = json.loads((ROOT / "models_config.json").read_text(encoding="utf-8"))
        group = config["whisper"]
        self.assertEqual(group["target"], "models/audio_encoders/whisper-large-v3")
        names = [entry["name"] for entry in group["files"]]
        self.assertEqual(names, ["model.bin", "config.json", "preprocessor_config.json",
                                 "tokenizer.json", "vocabulary.json"])
        for entry in group["files"]:
            self.assertEqual(entry["repo_id"], "Systran/faster-whisper-large-v3")
            self.assertEqual(entry["revision"], "edaa852ec7e145841d8ffdb056a99866b5f0a478")
            self.assertGreater(entry["bytes"], 0)

    def test_group_is_off_unless_requested(self):
        config = self.downloader.load_models_config()
        default = {entry["name"] for entry in self.downloader.normalize_model_entries(config)}
        self.assertNotIn("model.bin", default)
        selected = self.downloader.normalize_model_entries(
            config, minimax=False, flux2=False, flashsr=False, llm=False, whisper=True)
        self.assertEqual({entry["name"] for entry in selected}, {
            "model.bin", "config.json", "preprocessor_config.json",
            "tokenizer.json", "vocabulary.json"})
        self.assertTrue(all(entry["target"] == "models/audio_encoders/whisper-large-v3"
                            for entry in selected))

    def test_loader_and_catalog_agree_on_the_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(self.downloader, "comfy_models_dir", lambda: Path(folder)):
                self.assertEqual(
                    self.whisper.whisper_model_dir("whisper-large-v3"),
                    Path(folder) / "audio_encoders" / "whisper-large-v3")

    def test_default_checkpoint_is_the_quality_choice(self):
        spec = self.pkg.NODE_CLASS_MAPPINGS["MusicCoverLyrics"].INPUT_TYPES()["required"]
        self.assertEqual(spec["whisper_model"][1]["default"], "whisper-large-v3")
        # The dropdown is derived from the catalog, so it never offers a model
        # that the check node cannot obtain.
        self.assertEqual(list(spec["whisper_model"][0]), self.whisper.whisper_model_choices())
        self.assertIn("whisper-large-v3", spec["whisper_model"][0])
        self.assertEqual(spec["language"][1]["default"], "auto")
        self.assertIs(spec["condition_on_previous_text"][1]["default"], False)
        self.assertIs(spec["vad_filter"][1]["default"], False)


class WhisperAutodownloadTests(unittest.TestCase):
    """The 3 GB checkpoint is only requested for the one combination that needs it."""

    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.mod = importlib.import_module(cls.pkg.__name__ + ".minimax_autodownload")

    def profile(self, name):
        return self.pkg.NODE_CLASS_MAPPINGS["MusicProductionControl"]().build(name)[0]

    def source(self, lyrics_mode):
        return json.dumps({"schema": "music_cover_source_v1", "audio": "Night.wav",
                           "mode": "full", "audio_encoder": "sheetsage2_bf16.safetensors",
                           "lyrics_mode": lyrics_mode, "lead_instrument": "Lead synth"})

    def selected_names(self, model, enabled, lyrics_mode):
        with patch.object(self.mod, "preflight_models", return_value={"entries": []}) as run, \
             patch.object(self.mod, "format_preflight_report", return_value=[]):
            self.pkg.NODE_CLASS_MAPPINGS["MiniMaxModelAutodownload"]().check(
                False, False, False, False, False, yue2_models=False,
                model_profile_json=self.profile(model), sheetsage2_models=False,
                whisper_models=enabled, cover_source_json=self.source(lyrics_mode))
            return [entry["name"] for entry in run.call_args.args[0]]

    def test_only_original_lyrics_covers_request_whisper(self):
        for model in ("YuE2", "MiniMax Music 3"):
            self.assertNotIn("model.bin", self.selected_names(model, True, "original lyrics"))
        for mode in ("instrumental",):
            self.assertNotIn("model.bin", self.selected_names("YuE2 Cover", True, mode))
        self.assertIn("model.bin", self.selected_names("YuE2 Cover", True, "original lyrics"))
        self.assertIn("model.bin", self.selected_names("YuE2 Cover", True, "new lyrics"))

    def test_the_switch_can_turn_it_off(self):
        self.assertNotIn("model.bin", self.selected_names("YuE2 Cover", False, "original lyrics"))

    def test_route_flags_keep_branch_only_groups_off(self):
        routes = importlib.import_module(self.pkg.__name__ + ".model_manager_routes")
        flags = routes._parse_flags({})
        self.assertTrue(flags["minimax"])
        self.assertFalse(flags["sheetsage2"])
        self.assertFalse(flags["whisper"])
        flags = routes._parse_flags({"whisper": "1", "sheetsage2": "true"})
        self.assertTrue(flags["whisper"])
        self.assertTrue(flags["sheetsage2"])


if __name__ == "__main__":
    unittest.main()
