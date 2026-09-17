"""Instrumental vocal check, its retry loop, the tag reader and the consolidated workflows."""
from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _toolkit_bootstrap import load_entry_point
from test_cover_lyrics import ABC as COVER_ABC  # noqa: F401 - shared fixture check

ROOT = Path(__file__).resolve().parents[1]

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
"""


def audio(seconds=1.0, rate=48000):
    import torch
    samples = int(seconds * rate)
    return {"waveform": torch.zeros(1, 2, samples), "sample_rate": rate}


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pkg, _ = load_entry_point()
        cls.pkg = pkg
        cls.check = importlib.import_module(pkg.__name__ + ".instrumental_check")
        cls.tags = importlib.import_module(pkg.__name__ + ".audio_tag_copy")
        cls.settings_mod = importlib.import_module(pkg.__name__ + ".minimax_settings")
        cls.whisper = importlib.import_module(pkg.__name__ + ".whisper_lyrics")

    def node(self, name):
        return self.pkg.NODE_CLASS_MAPPINGS[name]()


class WordCountTests(_Base):
    def test_words_not_letters_are_counted(self):
        self.assertEqual(self.check.count_words(""), 0)
        self.assertEqual(self.check.count_words("   "), 0)
        self.assertEqual(self.check.count_words("hold on"), 2)
        self.assertEqual(self.check.count_words("la la la la"), 4)
        self.assertEqual(self.check.count_words("hold\non"), 2)

    def test_the_summary_picks_the_first_passing_take(self):
        reports = [{"passed": False, "words": 3}, {"passed": True, "words": 0}, None]
        self.assertEqual(self.check.choose_attempt(2, reports), (1, False))

    def test_the_summary_falls_back_to_the_take_with_the_fewest_words(self):
        """No pass: the measured counts decide, not the order the takes ran in.

        This used to hand back the *last* take, which ignored the word counts the
        checks had already produced (2026-09-17 change: keep the least vocal one).
        """
        reports = [{"passed": False, "words": 9}, {"passed": False, "words": 4}]
        self.assertEqual(self.check.choose_attempt(2, reports), (1, True))
        self.assertEqual(self.check.choose_attempt(
            2, [{"passed": False, "words": 2}, {"passed": False, "words": 7}]), (0, True))

    def test_equal_word_counts_keep_the_earliest_take(self):
        reports = [{"passed": False, "words": 5}, {"passed": False, "words": 5}]
        self.assertEqual(self.check.choose_attempt(2, reports), (0, True),
                         "a tie must keep the earliest take so a stored seed stays reproducible")

    def test_a_take_without_a_readable_count_cannot_win(self):
        reports = [{"passed": False, "words": None}, {"passed": False, "words": 6}]
        self.assertEqual(self.check.choose_attempt(2, reports), (1, True))

    def test_the_retry_budget_is_capped_at_ten(self):
        self.assertEqual(self.check.MAX_RETRIES, 10)
        self.assertEqual(self.check.MAX_ATTEMPTS, 11)


class CheckInstrumentalTests(_Base):
    def record(self, text):
        return {"text": text, "model": "whisper-large-v3", "device": "cuda", "compute_type": "float16",
                "language": "en", "language_probability": 0.9, "duration_seconds": 1.0,
                "segment_count": 1 if text else 0, "attempts": []}

    def test_a_silent_transcript_passes(self):
        with patch.object(self.whisper, "transcribe", return_value=self.record("")):
            report = self.check.check_instrumental(audio(), word_tolerance=0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["words"], 0)
        self.assertEqual(report["schema"], "instrumental_vocal_check_v1")

    def test_words_are_reported_and_fail_a_zero_tolerance(self):
        with patch.object(self.whisper, "transcribe", return_value=self.record("hold on to me")):
            report = self.check.check_instrumental(audio(), word_tolerance=0)
        self.assertFalse(report["passed"])
        self.assertEqual(report["words"], 4)
        self.assertIn("hold on", report["transcript"])

    def test_a_tolerance_accepts_a_stray_word(self):
        with patch.object(self.whisper, "transcribe", return_value=self.record("oh")):
            report = self.check.check_instrumental(audio(), word_tolerance=1)
        self.assertTrue(report["passed"])
        self.assertEqual(report["word_tolerance"], 1)

    def test_the_check_asks_whisper_for_an_empty_result(self):
        calls = {}

        def fake(path, **kwargs):
            calls.update(kwargs)
            calls["path"] = str(path)
            return self.record("")

        with patch.object(self.whisper, "transcribe", side_effect=fake):
            self.check.check_instrumental(audio(seconds=0.5), word_tolerance=0)
        self.assertTrue(calls["allow_empty"])
        self.assertFalse(calls["vad_filter"], "VAD would clip sung fragments away")
        self.assertEqual(calls["beam_size"], 1)
        self.assertTrue(calls["path"].endswith("candidate.wav"))

    def test_the_recognised_lyrics_are_logged(self):
        with patch.object(self.whisper, "transcribe", return_value=self.record("hold on to me\nnow")):
            with self.assertLogs("minimax_music_toolkit.instrumental_check", level="INFO") as captured:
                self.check.check_instrumental(audio(), word_tolerance=0, label="take-2")
        joined = "\n".join(captured.output)
        self.assertIn("take-2", joined)
        self.assertIn("hold on to me now", joined, "the words Whisper heard belong in the log")

    def test_a_quiet_take_says_so_instead_of_logging_nothing(self):
        with patch.object(self.whisper, "transcribe", return_value=self.record("")):
            with self.assertLogs("minimax_music_toolkit.instrumental_check", level="INFO") as captured:
                report = self.check.check_instrumental(audio(), word_tolerance=0, label="take-1")
        self.assertIn("no words", "\n".join(captured.output))
        self.assertEqual(report["candidate_label"], "take-1")

    def test_a_very_long_transcript_is_shortened_in_the_log_but_kept_in_the_report(self):
        text = " ".join(f"word{i}" for i in range(400))
        with patch.object(self.whisper, "transcribe", return_value=self.record(text)):
            with self.assertLogs("minimax_music_toolkit.instrumental_check", level="INFO") as captured:
                report = self.check.check_instrumental(audio(), word_tolerance=0)
        self.assertIn("characters in total", "\n".join(captured.output))
        self.assertEqual(report["transcript"], text, "the report keeps the full text")

    def test_every_candidate_is_written_to_its_own_temporary_file(self):
        with patch.object(self.whisper, "transcribe", return_value=self.record("")):
            first = self.check.check_instrumental(audio(), word_tolerance=0, label="take-1")
            second = self.check.check_instrumental(audio(), word_tolerance=0, label="take-2")
        for report, label in ((first, "take-1"), (second, "take-2")):
            path = Path(report["candidate_path"])
            self.assertTrue(path.is_file(), path)
            self.assertIn(self.check.TEMP_ROOT_NAME, str(path))
            self.assertIn(label, str(path))
        self.assertNotEqual(first["candidate_path"], second["candidate_path"])
        for report in (first, second):
            Path(report["candidate_path"]).unlink(missing_ok=True)

    def test_an_invalid_audio_value_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not a valid AUDIO"):
            self.check.check_instrumental({"waveform": None}, word_tolerance=0)


class PickNodeTests(_Base):
    def report(self, passed, words, path=None, transcript=""):
        payload = {"schema": "instrumental_vocal_check_v1", "passed": passed, "words": words,
                   "word_tolerance": 0, "transcript": transcript}
        if path is not None:
            payload["candidate_path"] = str(path)
        return json.dumps(payload)

    def test_the_first_clean_take_is_used_without_asking_for_more(self):
        node = self.node("MiniMaxInstrumentalPick")
        pending = node.check_lazy_status(max_retries=3, word_tolerance=0)
        self.assertEqual(pending, ["candidate_0", "report_0"])
        pending = node.check_lazy_status(max_retries=3, word_tolerance=0,
                                         candidate_0=audio(), report_0=self.report(True, 0))
        self.assertEqual(pending, [], "a clean first take must not request a second generation")

    def test_a_dirty_take_asks_for_the_next_one(self):
        node = self.node("MiniMaxInstrumentalPick")
        pending = node.check_lazy_status(max_retries=3, word_tolerance=0,
                                         candidate_0=audio(), report_0=self.report(False, 4))
        self.assertEqual(pending, ["candidate_1", "report_1"])

    def test_the_budget_stops_the_asking(self):
        node = self.node("MiniMaxInstrumentalPick")
        kwargs = {"max_retries": 1, "word_tolerance": 0, "candidate_0": audio(),
                  "report_0": self.report(False, 3), "candidate_1": audio(),
                  "report_1": self.report(False, 2)}
        self.assertEqual(node.check_lazy_status(**kwargs), [])

    def test_the_selected_take_and_the_summary_are_returned(self):
        node = self.node("MiniMaxInstrumentalPick")
        chosen = audio(seconds=2.0)
        result, report = node.pick(max_retries=2, word_tolerance=0,
                                   candidate_0=audio(), report_0=self.report(False, 5),
                                   candidate_1=chosen, report_1=self.report(True, 0))
        self.assertIs(result, chosen)
        data = json.loads(report)
        self.assertEqual(data["kept_attempt"], 2)
        self.assertEqual(data["attempts_run"], 2)
        self.assertFalse(data["retry_budget_exhausted"])
        self.assertTrue(data["passed"])

    def test_an_exhausted_budget_keeps_the_least_vocal_take_and_deletes_the_rest(self):
        node = self.node("MiniMaxInstrumentalPick")
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for index in range(3):
                candidate = Path(tmp) / f"take{index + 1}" / "candidate.wav"
                candidate.parent.mkdir(parents=True)
                candidate.write_bytes(b"RIFF")
                paths.append(candidate)
            best = audio(seconds=3.0)
            result, report = node.pick(
                max_retries=2, word_tolerance=0,
                candidate_0=audio(), report_0=self.report(False, 7, paths[0], "la la"),
                candidate_1=best, report_1=self.report(False, 2, paths[1], "oh"),
                candidate_2=audio(), report_2=self.report(False, 5, paths[2], "hey now"))
            data = json.loads(report)
            self.assertIs(result, best, "the take with the fewest words must feed the rest of the graph")
            self.assertEqual(data["kept_attempt"], 2)
            self.assertEqual(data["kept_words"], 2)
            self.assertEqual(data["selection"], "fewest_words")
            self.assertTrue(data["retry_budget_exhausted"])
            self.assertEqual(data["kept_candidate_path"], str(paths[1]))
            self.assertEqual(data["kept_transcript"], "oh")
            self.assertEqual(sorted(data["removed_candidates"]), sorted([str(paths[0]), str(paths[2])]))
            self.assertEqual(data["removal_failed"], [])
            self.assertTrue(paths[1].is_file(), "the kept take stays on disk for auditioning")
            self.assertFalse(paths[0].exists())
            self.assertFalse(paths[2].exists())
            self.assertFalse(paths[0].parent.exists(), "the emptied take directory goes too")
            self.assertIn("fewest words", data["note"])
            attempts = data["attempts"]
            self.assertEqual([entry["words"] for entry in attempts], [7, 2, 5])
            self.assertTrue(all("transcript" in entry for entry in attempts))

    def test_a_passing_take_keeps_its_file_and_deletes_the_earlier_ones(self):
        node = self.node("MiniMaxInstrumentalPick")
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a" / "candidate.wav"
            second = Path(tmp) / "b" / "candidate.wav"
            for path in (first, second):
                path.parent.mkdir(parents=True)
                path.write_bytes(b"RIFF")
            chosen = audio(seconds=2.0)
            result, report = node.pick(max_retries=2, word_tolerance=0,
                                       candidate_0=audio(), report_0=self.report(False, 5, first),
                                       candidate_1=chosen, report_1=self.report(True, 0, second))
            data = json.loads(report)
            self.assertIs(result, chosen)
            self.assertEqual(data["selection"], "first_pass")
            self.assertEqual(data["attempts_run"], 2)
            self.assertFalse(first.exists())
            self.assertTrue(second.is_file())

    def test_a_take_that_stays_behind_is_reported_not_hidden(self):
        reports = [{"candidate_path": "/nonexistent/take/candidate.wav"},
                   {"candidate_path": ""}]
        removed, failed = self.check.remove_unkept_candidates(reports, keep="")
        self.assertEqual(removed, [])
        self.assertEqual(failed, ["/nonexistent/take/candidate.wav"])

    def test_stale_candidate_directories_are_pruned(self):
        import os as _os
        import time as _time
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fresh = root / "fresh"
            old = root / "old"
            for path in (fresh, old):
                path.mkdir()
                (path / "candidate.wav").write_bytes(b"RIFF")
            stamp = _time.time() - 48 * 3600
            _os.utime(old, (stamp, stamp))
            self.assertEqual(self.check.prune_stale_runs(root, hours=24), 1)
            self.assertTrue(fresh.exists())
            self.assertFalse(old.exists())

    def test_the_candidate_inputs_are_lazy(self):
        declared = self.pkg.NODE_CLASS_MAPPINGS["MiniMaxInstrumentalPick"].INPUT_TYPES()["optional"]
        self.assertEqual(len(declared), self.check.MAX_ATTEMPTS * 2)
        for name, spec in declared.items():
            self.assertTrue(spec[1].get("lazy"), name)


def cover_source(lyrics_mode="instrumental", mode="full"):
    return json.dumps({"schema": "music_cover_source_v1", "audio": "song.wav", "mode": mode,
                       "audio_encoder": "sheetsage2_bf16.safetensors",
                       "lyrics_mode": lyrics_mode, "lead_instrument": "Saxophone"})


class SettingsWiringTests(_Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from test_cover_lyrics import CoverChainEndToEndTests
        cls.helper = CoverChainEndToEndTests()
        cls.helper.pkg = cls.pkg

    def build(self, lyrics_mode="instrumental", **overrides):
        node = self.settings_mod.MiniMaxMusicModelSettings()
        spec = node.INPUT_TYPES()["required"]
        args = {name: options[1]["default"] for name, options in spec.items()
                if "default" in options[1]}
        args.update(generation_seed=11, profile_json=self.helper.profile(),
                    cover_source_json=cover_source(lyrics_mode))
        args.update(overrides)
        return json.loads(node.build(**args)[-1])

    def test_the_check_is_off_by_default_and_recorded_as_off(self):
        data = self.build()
        self.assertEqual(data["instrumental_check"], {"enabled": False})

    def test_enabling_it_records_the_tolerance_and_the_cap(self):
        data = self.build(instrumental_check=True, instrumental_word_tolerance=2,
                          instrumental_max_retries=7)
        entry = data["instrumental_check"]
        self.assertTrue(entry["enabled"])
        self.assertEqual(entry["word_tolerance"], 2)
        self.assertEqual(entry["max_retries"], 7)
        self.assertEqual(entry["max_attempts"], 8)
        self.assertIn("before refinement", entry["position"])
        self.assertTrue(any("Instrumental vocal check" in note for note in data["notes"]))

    def test_the_retry_cap_is_enforced_in_the_settings(self):
        data = self.build(instrumental_check=True, instrumental_max_retries=99)
        self.assertEqual(data["instrumental_check"]["max_retries"], self.check.MAX_RETRIES)


class ExpansionTests(_Base):
    """The retry loop is built into the generation graph, and only when asked."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import types
        from test_cover_lyrics import CoverChainEndToEndTests
        from test_yue2 import Graph
        cls.graph_module = types.SimpleNamespace(GraphBuilder=Graph)
        helper = CoverChainEndToEndTests()
        helper.pkg = cls.pkg
        cls.helper = helper

    def source(self, lyrics_mode="instrumental", mode="full"):
        return cover_source(lyrics_mode, mode)

    def expand(self, lyrics_mode="instrumental", check=None):
        profile = self.helper.profile()
        settings_node = self.settings_mod.MiniMaxMusicModelSettings()
        spec = settings_node.INPUT_TYPES()["required"]
        args = {name: options[1]["default"] for name, options in spec.items()
                if "default" in options[1]}
        settings = settings_node.build(**args, generation_seed=5, profile_json=profile,
                                       cover_source_json=self.source(lyrics_mode),
                                       **(check or {}))[-1]
        with patch.dict(__import__("sys").modules,
                        {"comfy_execution.graph_utils": self.graph_module}):
            lyrics = "[Instrumental]" if lyrics_mode == "instrumental" else "[Verse]\nwords here"
            expanded = self.pkg.NODE_CLASS_MAPPINGS["MusicGeneration"]().generate(
                profile, settings, "style", lyrics, "yue.safetensors", "dit", "clip", "vae",
                cover_source_json=self.source(lyrics_mode), cover_abc=ABC)["expand"]
        return {node["class_type"]: node["inputs"] for node in expanded.values()}, expanded

    def test_no_check_nodes_without_the_switch(self):
        by_type, expanded = self.expand()
        self.assertNotIn("MiniMaxInstrumentalVocalCheck", by_type)
        self.assertNotIn("MiniMaxInstrumentalPick", by_type)
        self.assertEqual(len([n for n in expanded.values()
                              if n["class_type"] == "YuE2GenerateMusic"]), 1)

    def test_the_switch_builds_one_candidate_per_allowed_attempt(self):
        by_type, expanded = self.expand(check={"instrumental_check": True,
                                               "instrumental_max_retries": 3,
                                               "instrumental_word_tolerance": 1})
        generators = [n for n in expanded.values() if n["class_type"] == "YuE2GenerateMusic"]
        checks = [n for n in expanded.values() if n["class_type"] == "MiniMaxInstrumentalVocalCheck"]
        self.assertEqual(len(generators), 4)
        self.assertEqual(len(checks), 4)
        self.assertEqual([c["inputs"]["word_tolerance"] for c in checks], [1, 1, 1, 1])
        self.assertEqual(len([n for n in expanded.values() if n["class_type"] == "KSamplerWithConfig"]), 4)
        pick = by_type["MiniMaxInstrumentalPick"]
        self.assertEqual(pick["max_retries"], 3)

    def test_every_attempt_uses_a_different_seed(self):
        _by_type, expanded = self.expand(check={"instrumental_check": True,
                                                "instrumental_max_retries": 2})
        seeds = [n["inputs"]["seed"] for n in expanded.values() if n["class_type"] == "YuE2GenerateMusic"]
        self.assertEqual(len(seeds), len(set(seeds)), "retries must not repeat the same take")

    def test_the_check_is_ignored_for_a_non_instrumental_cover(self):
        for lyrics_mode in ("new lyrics", "original lyrics"):
            by_type, _ = self.expand(lyrics_mode=lyrics_mode,
                                     check={"instrumental_check": True, "instrumental_max_retries": 3})
            self.assertNotIn("MiniMaxInstrumentalPick", by_type, lyrics_mode)

    def test_the_selection_feeds_the_audio_output_and_the_receipt(self):
        by_type, _ = self.expand(check={"instrumental_check": True, "instrumental_max_retries": 1})
        pick = by_type["MiniMaxInstrumentalPick"]
        self.assertEqual(len(pick["candidate_0"]), 2)
        self.assertEqual(len(pick["report_0"]), 2)
        receipt = by_type["MusicGenerationReceipt"]
        self.assertEqual(len(receipt["instrumental_check_json"]), 2)

    def test_the_check_label_reaches_each_candidate_node(self):
        _by_type, expanded = self.expand(check={"instrumental_check": True,
                                                "instrumental_max_retries": 2})
        labels = [node["inputs"]["candidate_label"] for node in expanded.values()
                  if node["class_type"] == "MiniMaxInstrumentalVocalCheck"]
        self.assertEqual(labels, ["take-1", "take-2", "take-3"],
                         "each take must be traceable to its own temporary WAV")


class TagReaderTests(_Base):
    def make_tagged_flac(self, directory):
        import numpy as np
        import soundfile as sf
        path = Path(directory) / "source.flac"
        sf.write(str(path), np.zeros(8000, dtype="float32"), 8000, format="FLAC")
        from mutagen.flac import FLAC, Picture
        audio_file = FLAC(str(path))
        audio_file["title"] = "Daddy Cool"
        audio_file["artist"] = "Boney M"
        audio_file["album"] = "Gold"
        audio_file["date"] = "1976-05-01"
        audio_file["tracknumber"] = "2/20"
        audio_file["genre"] = "Disco"
        picture = Picture()
        picture.type = 3
        picture.mime = "image/jpeg"
        picture.data = b"\xff\xd8\xff\xe0not-a-real-jpeg-but-bytes"
        audio_file.add_picture(picture)
        audio_file.save()
        return path

    def test_tags_are_read_with_the_expected_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_tagged_flac(tmp)
            tags = self.tags.read_tags(path)
        self.assertEqual(tags["title"], "Daddy Cool")
        self.assertEqual(tags["artist"], "Boney M")
        self.assertEqual(tags["album"], "Gold")
        self.assertEqual(tags["year"], "1976", "the year is trimmed to four digits")
        self.assertEqual(tags["track"], "2", "the track number drops its total")
        self.assertEqual(tags["genre"], "Disco")

    def test_the_embedded_cover_is_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_tagged_flac(tmp)
            cover = self.tags.extract_cover_art(path, tmp)
            self.assertTrue(cover)
            self.assertTrue(Path(cover).is_file())
            self.assertTrue(Path(cover).read_bytes().startswith(b"\xff\xd8"))

    def test_a_file_without_tags_yields_an_empty_mapping(self):
        import numpy as np
        import soundfile as sf
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bare.flac"
            sf.write(str(path), np.zeros(800, dtype="float32"), 800, format="FLAC")
            self.assertEqual(self.tags.read_tags(path), {})
            self.assertEqual(self.tags.extract_cover_art(path, tmp), "")

    def test_the_node_reports_what_it_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_tagged_flac(tmp)

            def fake_annotated(name):
                return str(path)

            folder_paths = __import__("types").ModuleType("folder_paths")
            folder_paths.get_annotated_filepath = fake_annotated
            with patch.dict(__import__("sys").modules, {"folder_paths": folder_paths}):
                tags_json, cover, report = self.node("MiniMaxAudioTagReader").read(str(path))
        self.assertEqual(json.loads(tags_json)["artist"], "Boney M")
        self.assertTrue(cover)
        data = json.loads(report)
        self.assertEqual(data["schema"], "music_source_tags_v1")
        self.assertIn("title", data["fields_found"])
        self.assertIn("composer", data["fields_missing"])
        self.assertTrue(data["cover_art"])

    def test_no_file_selected_is_an_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "select the audio file"):
            self.node("MiniMaxAudioTagReader").read("<select audio>")


class ConsolidatedWorkflowTests(_Base):
    EXAMPLES = ROOT / "example_workflows"

    def test_only_two_workflows_are_shipped(self):
        self.assertEqual({path.name for path in self.EXAMPLES.glob("*.json")},
                         {"Music_Production_Toolkit.json", "Music_Production_AudioEnhance.json"})

    def test_the_main_workflow_carries_the_check_widgets(self):
        data = json.loads((self.EXAMPLES / "Music_Production_Toolkit.json").read_text(encoding="utf-8"))
        settings = next(node for node in data["nodes"] if node["type"] == "MiniMaxMusicModelSettings")
        names = [entry["name"] for entry in settings["inputs"]]
        self.assertEqual(names[-3:], ["instrumental_check", "instrumental_word_tolerance",
                                      "instrumental_max_retries"])
        self.assertEqual(settings["widgets_values"][-3:], [False, 0, 2])

    def test_the_enhance_workflow_has_every_enhancement_stage(self):
        data = json.loads((self.EXAMPLES / "Music_Production_AudioEnhance.json").read_text(encoding="utf-8"))
        types = {node["type"] for node in data["nodes"]}
        for required in ("LoadAudio", "AudioDeclipRepair", "FlashSRLowpassLab", "MiniMaxFlashSRAudio",
                         "FlashSRHybridCrossover", "HFCymbalShimmerRepair", "AudioArtifactReduction",
                         "MiniMaxAutoEQAnalyze", "MiniMaxParametricEQ", "MiniMaxMasteringCompressor",
                         "AudioReleasePrep", "SaveAudioSmartPrefix", "MiniMaxAudioTagReader"):
            self.assertIn(required, types)
        self.assertEqual(len([n for n in data["nodes"] if n["type"] == "MusicOptionalStage"]), 2)

    def test_the_enhance_workflow_copies_the_source_tags_onto_both_exports(self):
        data = json.loads((self.EXAMPLES / "Music_Production_AudioEnhance.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in data["nodes"]}
        reader = next(node for node in data["nodes"] if node["type"] == "MiniMaxAudioTagReader")
        targets = {(nodes[link[3]]["type"], nodes[link[3]]["inputs"][link[4]]["name"])
                   for link in data["links"] if link[1] == reader["id"]}
        self.assertIn(("SaveAudioSmartPrefix", "audio_tags_json"), targets)
        self.assertIn(("SaveAudioSmartPrefix", "cover_image_path"), targets)
        tagged = [link for link in data["links"] if link[1] == reader["id"]
                  and nodes[link[3]]["inputs"][link[4]]["name"] == "audio_tags_json"]
        self.assertEqual(len(tagged), 2, "both the FLAC and the MP3 export carry the source tags")

    def test_the_enhance_workflow_loads_no_personal_file(self):
        data = json.loads((self.EXAMPLES / "Music_Production_AudioEnhance.json").read_text(encoding="utf-8"))
        loader = next(node for node in data["nodes"] if node["type"] == "LoadAudio")
        self.assertFalse(str((loader.get("widgets_values") or [""])[0]).strip())
        reader = next(node for node in data["nodes"] if node["type"] == "MiniMaxAudioTagReader")
        self.assertEqual(reader["widgets_values"][0], "<select audio>")


if __name__ == "__main__":
    unittest.main()
