"""Python/JavaScript preset parity (F20 / T18).

``web/preset_sync.js`` mirrors the numeric DSP presets so the visible widgets
stay honest when a preset is selected.  Python is authoritative, so this test
fails when the two sides drift apart - in either direction.

The JS file cannot be imported (it pulls in ComfyUI's ``app.js``), so the
literal objects are read with a small brace-matching scanner.
"""
from __future__ import annotations

import importlib
import re
import unittest
from pathlib import Path

import _toolkit_bootstrap

ROOT = Path(__file__).resolve().parents[1]
_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
declip = importlib.import_module(f"{_PACKAGE.__name__}.audio_declip")
hf_repair = importlib.import_module(f"{_PACKAGE.__name__}.audio_hf_repair")
release = importlib.import_module(f"{_PACKAGE.__name__}.audio_release_prep")
lowpass = importlib.import_module(f"{_PACKAGE.__name__}.audio_lowpass")

JS_SOURCE = (ROOT / "web" / "preset_sync.js").read_text(encoding="utf-8")

_STRING = r'"((?:[^"\\]|\\.)*)"'


def _js_object_literal(source: str, name: str) -> str:
    """Return the body of ``const <name> = { ... };`` with brace matching."""
    match = re.search(rf"const\s+{re.escape(name)}\s*=\s*\{{", source)
    if not match:
        raise AssertionError(f"{name} not found in preset_sync.js")
    start = match.end() - 1
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1 : index]
    raise AssertionError(f"unbalanced braces for {name}")


def _split_top_level(body: str, separator: str = ",") -> list[str]:
    parts = []
    depth = 0
    in_string = False
    escaped = False
    current = []
    for char in body:
        if in_string:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            current.append(char)
        elif char in "{[":
            depth += 1
            current.append(char)
        elif char in "}]":
            depth -= 1
            current.append(char)
        elif char == separator and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if "".join(current).strip():
        parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _parse_js_map(name: str) -> dict:
    """Parse a two-level JS object literal into ``{key: {field: value}}``."""
    body = _js_object_literal(JS_SOURCE, name)
    entries = {}
    for chunk in _split_top_level(body):
        key_match = re.match(rf"^{_STRING}\s*:\s*\{{(.*)\}}\s*$", chunk, re.S)
        assert key_match, f"could not parse entry of {name}: {chunk[:60]!r}"
        key = key_match.group(1)
        fields = {}
        for field in _split_top_level(key_match.group(2)):
            field_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$", field, re.S)
            assert field_match, f"could not parse field of {name}.{key}: {field[:60]!r}"
            raw = field_match.group(2).strip().rstrip(",")
            if raw.startswith('"'):
                fields[field_match.group(1)] = raw.strip('"')
            else:
                fields[field_match.group(1)] = float(raw) if "." in raw else int(raw)
        entries[key] = fields
    return entries


class ScannerTests(unittest.TestCase):
    """The scanner itself must be trustworthy before it can judge parity."""

    def test_finds_all_four_maps(self):
        for name in ("DECLIP_PRESETS", "HF_PRESETS", "RELEASE_PRESETS", "LOWPASS_PRESETS"):
            with self.subTest(name=name):
                self.assertTrue(_parse_js_map(name))

    def test_parses_a_known_entry(self):
        self.assertEqual(
            _parse_js_map("DECLIP_PRESETS")["Auto / conservative"]["detection_threshold_percent"],
            98.0,
        )
        self.assertEqual(_parse_js_map("LOWPASS_PRESETS")["PRE 12 kHz - recommended"]["phase"], "zero_phase")


class DeclipParityTests(unittest.TestCase):
    def test_presets_match_python(self):
        js = _parse_js_map("DECLIP_PRESETS")
        self.assertEqual(
            sorted(js),
            sorted(m for m in ("Auto / conservative", "Standard", "Strong")),
        )
        for mode, fields in js.items():
            with self.subTest(mode=mode):
                values = declip._preset(mode, 1.0, 1.0, 1, 1, 1.0, 1.0, -1.0, 1.0)
                expected = (
                    fields["detection_threshold_percent"],
                    fields["plateau_tolerance_percent"],
                    fields["min_flat_samples"],
                    fields["slope_context_samples"],
                    fields["max_repair_ms"],
                    fields["max_peak_extension_db"],
                    fields["output_ceiling_dbfs"],
                    fields["mix"],
                )
                self.assertEqual(tuple(values), expected, f"declip preset '{mode}' drifted")


class HfRepairParityTests(unittest.TestCase):
    def test_presets_match_python(self):
        js = _parse_js_map("HF_PRESETS")
        self.assertEqual(sorted(js), sorted(["Gentle", "Cymbal clarity", "Reverb / shimmer control"]))
        for mode, fields in js.items():
            with self.subTest(mode=mode):
                values = hf_repair._preset_repair(mode, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, 1.0)
                expected = (
                    fields["start_frequency_hz"],
                    fields["sustain_reduction_db"],
                    fields["fast_envelope_ms"],
                    fields["slow_envelope_ms"],
                    fields["transient_sensitivity"],
                    fields["side_hf_reduction_db"],
                    fields["static_hf_trim_db"],
                    fields["min_hf_level_dbfs"],
                    fields["mix"],
                )
                self.assertEqual(tuple(values), expected, f"HF preset '{mode}' drifted")


class ReleaseParityTests(unittest.TestCase):
    def test_presets_match_python(self):
        js = _parse_js_map("RELEASE_PRESETS")
        for name, fields in js.items():
            with self.subTest(preset=name):
                lufs, tp = release._preset_values(name, 0.0, 0.0)
                self.assertEqual((lufs, tp), (fields["custom_target_lufs"], fields["custom_true_peak_dbtp"]))

    def test_every_javascript_preset_exists_in_the_node_combo(self):
        js = _parse_js_map("RELEASE_PRESETS")
        combo = release.AudioReleasePrep.INPUT_TYPES()["required"]["processing"][0]
        for name in js:
            with self.subTest(preset=name):
                self.assertIn(name, combo)


class LowpassParityTests(unittest.TestCase):
    def test_presets_match_python(self):
        js = _parse_js_map("LOWPASS_PRESETS")
        listed = {
            "PRE 14 kHz - light",
            "PRE 12 kHz - recommended",
            "PRE 10 kHz - strong",
            "PRE 8 kHz - aggressive",
            "POST 20 kHz - recommended gentle",
            "POST 19 kHz - slightly stronger",
        }
        self.assertEqual(sorted(js), sorted(listed))
        for name, fields in js.items():
            with self.subTest(preset=name):
                config = lowpass.PRESETS[name]
                self.assertEqual(config["cutoff_hz"], fields["cutoff"])
                self.assertEqual(config["order"], fields["order"])
                self.assertEqual(config["phase_mode"], fields["phase"])

    def test_python_presets_are_all_mirrored(self):
        js = _parse_js_map("LOWPASS_PRESETS")
        mirrored = set(js)
        for name in lowpass.PRESETS:
            if name == "CUSTOM":
                continue
            with self.subTest(preset=name):
                self.assertIn(name, mirrored, f"{name} exists in Python but not in preset_sync.js")

    def test_lowpass_combo_lists_every_preset_plus_the_sentinel(self):
        js = _parse_js_map("LOWPASS_PRESETS")
        combo = lowpass.FlashSRLowpassLab.INPUT_TYPES()["required"]["preset"][0]
        self.assertIn("CUSTOM", combo, "the custom sentinel stays uppercase for this node")
        for name in js:
            with self.subTest(preset=name):
                self.assertIn(name, combo)


if __name__ == "__main__":
    unittest.main()
