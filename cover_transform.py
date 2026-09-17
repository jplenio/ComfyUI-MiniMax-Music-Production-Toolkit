"""Score transformation for the YuE2 Cover Studio.

Two kinds of change live here, and they are deliberately separated:

*Deterministic* changes are exact, verifiable rewrites of the native ABC that
need no model at all - tempo, transposition and the chord-free melody line.
They are validated with the vendored upstream checker before they are returned,
and each one either applies cleanly or is reported as skipped.

*Interpretive* changes (harmony, arrangement, structure, ornamentation) are
requested from the language model as a structured job.  The model's answer is
never trusted: it is extracted, structurally validated and compared with its
source, and when it does not hold up the deterministic result is used instead.
YuE2 therefore never receives unvalidated model output.

Transposition is implemented here rather than delegated because it can be done
exactly: every note's sounding pitch is shifted by the requested interval and
re-spelled against the target key with the minimal accidentals the native
dialect allows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .abc_validate import AbcValidation, abc_reference, validate_abc
from .cover_profiles import CoverInterpretationProfile, CoverMode, cover_mode_for, transformation_request
from .third_party.yue2_abc import (
    AbcError,
    CHORD,
    KEYS,
    NATURAL,
    TOKEN,
    key_accidentals,
    parse_abc,
    strip_chords,
)

LETTERS = "CDEFGAB"
# Semitone position of each natural letter above C.
STEP_PC = dict(zip(LETTERS, (0, 2, 4, 5, 7, 9, 11)))

# Key spellings by tonic pitch class, grouped by mode.  Built from the native
# KEYS table and ordered by the number of accidentals, so the simplest spelling
# wins: C major for 0, G for 7, F for 5, Eb for 3 and so on.
def _build_key_table() -> Dict[Tuple[bool, int], str]:
    table: Dict[Tuple[bool, int], List[Tuple[int, str]]] = {}
    for name, count in KEYS.items():
        minor = name.endswith("m")
        letter, accidental = _split_tonic(name[:-1] if minor else name)
        pitch_class = (STEP_PC[letter] + accidental) % 12
        table.setdefault((minor, pitch_class), []).append((abs(count), name))
    return {key: sorted(values)[0][1] for key, values in table.items()}


def _split_tonic(name: str) -> Tuple[str, int]:
    """``"Ebm"`` -> (``"E"``, -1); ``"F#"`` -> (``"F"``, +1)."""
    text = str(name or "").strip()
    if not text or text[0].upper() not in LETTERS:
        raise AbcError(f"Unsupported key name {name!r}")
    letter = text[0].upper()
    accidental = 0
    rest = text[1:]
    if rest.startswith("bb"):
        accidental, rest = -2, rest[2:]
    elif rest.startswith("##"):
        accidental, rest = 2, rest[2:]
    elif rest.startswith("b"):
        accidental, rest = -1, rest[1:]
    elif rest.startswith("#"):
        accidental, rest = 1, rest[1:]
    if rest:
        raise AbcError(f"Unsupported key name {name!r}")
    return letter, accidental


KEY_TABLE = _build_key_table()

# Pitch-class spelling for absolute chord roots and slash basses.
_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
_ACCIDENTAL_TEXT = {2: "^^", 1: "^", 0: "=", -1: "_", -2: "__"}

_CHORD_TOKEN_RE = __import__("re").compile(
    r'^(?P<root>[A-G](?:bb|##|b|#)?)(?P<quality>.*?)(?:/(?P<bass>[A-G](?:bb|##|b|#)?))?$')


def transpose_key_name(key: str, semitones: int) -> str:
    """The simplest spelling of *key* shifted by *semitones*."""
    if semitones % 12 == 0:
        return key
    text = str(key).strip()
    minor = text.endswith("m")
    letter, accidental = _split_tonic(text[:-1] if minor else text)
    target = (STEP_PC[letter] + accidental + semitones) % 12
    return KEY_TABLE[(minor, target)]


def _spell_pitch_class(pitch_class: int, prefer_flats: bool) -> str:
    return (_FLAT_NAMES if prefer_flats else _SHARP_NAMES)[pitch_class % 12]


def transpose_chord(chord: str, semitones: int, prefer_flats: bool) -> str:
    """Transpose a native chord symbol, preserving its quality and slash bass."""
    match = _CHORD_TOKEN_RE.match(chord)
    if match is None or CHORD.fullmatch(chord) is None:
        raise AbcError(f"Unsupported chord symbol {chord!r}")
    root_letter, root_accidental = _split_tonic(match.group("root"))
    new_root = _spell_pitch_class(
        STEP_PC[root_letter] + root_accidental + semitones, prefer_flats)
    bass = match.group("bass")
    if bass:
        bass_letter, bass_accidental = _split_tonic(bass)
        new_bass = "/" + _spell_pitch_class(
            STEP_PC[bass_letter] + bass_accidental + semitones, prefer_flats)
    else:
        new_bass = ""
    return new_root + match.group("quality") + new_bass


def _shift_letter(letter: str, step: int) -> Tuple[str, int]:
    """Shift a letter by *step* diatonic positions; returns (letter, octave carry)."""
    index = LETTERS.index(letter) + step
    return LETTERS[index % 7], index // 7


def transpose_abc(abc: str, semitones: int) -> str:
    """Shift every sounding pitch by *semitones*, preserving rhythm and structure.

    Keys, inline key changes and chord symbols move with the music; ties, rests,
    meter, phrase order and section comments stay untouched.  Accidentals are
    re-spelled against the target key with the minimum the dialect allows, so the
    result stays readable instead of marking every note.
    """
    semitones = int(semitones)
    if semitones % 12 == 0:
        return abc
    parse_abc(abc)  # fail closed on unsupported input instead of half-rewriting it

    lines = str(abc).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    header_key = next((line[2:].strip() for line in lines if line.startswith("K:")), None)
    if not header_key:
        raise AbcError("Transposition requires a header K: field")
    current_key = transpose_key_name(header_key, semitones)
    prefer_flats = key_accidentals(current_key)["B"] == -1
    source_key = header_key
    out: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("K:"):
            out.append("K:" + current_key)
            continue
        if not stripped or stripped.startswith(("%", "V:", "X:", "T:", "M:", "L:", "Q:")):
            out.append(line)
            continue
        out.append(_transpose_music_line(line, source_key, current_key, semitones, prefer_flats))
    return "\n".join(out)


def _diatonic_step(source_key: str, target_key: str) -> int:
    """Letter distance between two keys, normalised to the smaller direction."""
    source = LETTERS.index(_split_tonic(_tonic(source_key))[0])
    target = LETTERS.index(_split_tonic(_tonic(target_key))[0])
    step = target - source
    if step > 3:
        step -= 7
    elif step < -3:
        step += 7
    return step


def _tonic(key: str) -> str:
    """``"Ebm"`` -> ``"Eb"``; ``"Am"`` -> ``"A"``."""
    text = str(key).strip()
    return text[:-1] if text.endswith("m") else text


def _transpose_music_line(line: str, source_key: str, target_key: str,
                          semitones: int, prefer_flats: bool) -> str:
    """Rewrite one music line, tracking key changes and per-bar accidental state.

    The propagated accidental state resets at every barline and at every inline
    key change, exactly as the native parser resolves it.
    """
    step = _diatonic_step(source_key, target_key)
    source_defaults = key_accidentals(source_key)
    target_defaults = key_accidentals(target_key)
    propagation: Dict[str, int] = {}
    pieces: List[str] = []
    cursor = 0
    for match in TOKEN.finditer(line):
        literal = line[cursor:match.start()]
        if "|" in literal:
            propagation = {}
        pieces.append(literal)
        cursor = match.end()
        chord = match.group("chord")
        if chord is not None:
            pieces.append('"' + transpose_chord(chord, semitones, prefer_flats) + '"')
            continue
        key = match.group("key")
        if key is not None:
            new_key = transpose_key_name(key, semitones)
            pieces.append("[K:" + new_key + "]")
            source_key, target_key = key, new_key
            step = _diatonic_step(source_key, target_key)
            source_defaults = key_accidentals(source_key)
            target_defaults = key_accidentals(target_key)
            prefer_flats = target_defaults["B"] == -1
            propagation = {}
            continue
        token = match.group("note")
        if token is None or token == "z":
            pieces.append(match.group(0))
            continue
        letter = token.upper()       # rests are the only non-letter token here
        case = token.islower()
        octave = match.group("oct")
        effective = propagation.get(letter, source_defaults.get(letter, 0))
        if match.group("acc"):
            effective = {"=": 0, "_": -1, "__": -2, "^": 1, "^^": 2}[match.group("acc")]
        sounding = 60 + NATURAL[letter] + (12 if case else 0)
        sounding += 12 * (octave.count("'") - octave.count(",")) + effective
        target_pitch = sounding + semitones

        new_letter, carry = _shift_letter(letter, step)
        marks = octave.count("'") - octave.count(",") + carry
        residual = target_pitch - (60 + NATURAL[new_letter] + (12 if case else 0) + 12 * marks)
        while residual > 2:
            marks += 1
            residual -= 12
        while residual < -2:
            marks -= 1
            residual += 12
        marks_text = "'" * marks if marks > 0 else "," * (-marks)
        written = new_letter.lower() if case else new_letter
        current = propagation.get(new_letter, target_defaults.get(new_letter, 0))
        if residual == current:
            accidental = ""
        else:
            accidental = _ACCIDENTAL_TEXT[residual]
            propagation[new_letter] = residual
        pieces.append(accidental + written + marks_text + (match.group("duration") or "")
                      + (match.group("tie") or ""))
    pieces.append(line[cursor:])
    return "".join(pieces)


def set_tempo(abc: str, bpm: int) -> str:
    """Rewrite ``Q:1/4=<bpm>`` without touching anything else."""
    lines = str(abc).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(lines):
        if line.startswith("Q:1/4="):
            lines[index] = f"Q:1/4={int(bpm)}"
            break
    return "\n".join(lines)


def scaled_tempo(abc: str, percent: int) -> int:
    """The target BPM for a relative tempo change, clamped to a sane range."""
    current = parse_abc(abc).bpm
    target = int(round(current * (1 + float(percent) / 100.0)))
    return max(20, min(300, target))


@dataclass
class TransformResult:
    """One transformation outcome, deterministic or model-produced."""

    abc: str
    changes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source: str = "deterministic"
    validation: Optional[AbcValidation] = None
    model_abc_rejected: bool = False

    def as_report(self) -> Dict[str, object]:
        return {
            "schema": "cover_abc_transformation_v1",
            "source": self.source,
            "changes": list(self.changes),
            "warnings": list(self.warnings),
            "model_abc_rejected": self.model_abc_rejected,
            "validation": self.validation.as_report() if self.validation else None,
        }


def apply_deterministic(
    abc: str,
    profile: CoverInterpretationProfile,
    key_change: int = 0,
    tempo_change: int = 0,
    melody_only: Optional[bool] = None,
) -> TransformResult:
    """Apply the exact knobs. A knob that cannot be applied is reported, not fatal."""
    current = str(abc)
    changes: List[str] = []
    warnings: List[str] = []

    def guard(label: str, candidate: str) -> bool:
        if candidate == current:
            return False
        result = validate_abc(candidate)
        if not result.ok:
            warnings.append(f"{label} was skipped: {result.errors[0] if result.errors else 'invalid ABC'}")
            return False
        return True

    if tempo_change:
        try:
            target_bpm = scaled_tempo(current, int(tempo_change))
            if target_bpm != parse_abc(current).bpm:
                candidate = set_tempo(current, target_bpm)
                if guard("tempo change", candidate):
                    changes.append(f"tempo {parse_abc(current).bpm} -> {target_bpm} BPM")
                    current = candidate
            else:
                warnings.append("tempo change rounded to the source tempo and was not applied")
        except (AbcError, ValueError) as exc:
            warnings.append(f"tempo change was skipped: {exc}")

    if key_change:
        try:
            candidate = transpose_abc(current, int(key_change))
            if guard("transposition", candidate):
                before = next(line[2:] for line in current.splitlines() if line.startswith("K:"))
                after = next(line[2:] for line in candidate.splitlines() if line.startswith("K:"))
                changes.append(f"key {before} -> {after} ({int(key_change):+d} semitones)")
                current = candidate
        except (AbcError, ValueError, KeyError) as exc:
            warnings.append(f"transposition was skipped: {exc}")

    wants_melody_only = profile.melody_only if melody_only is None else bool(melody_only)
    if wants_melody_only:
        try:
            candidate = strip_chords(current)
            if guard("melody-only reduction", candidate):
                changes.append("chord symbols removed; both melodies preserved note for note")
                current = candidate
        except (AbcError, ValueError) as exc:
            warnings.append(f"melody-only reduction was skipped: {exc}")

    return TransformResult(current, changes, warnings, "deterministic",
                           validate_abc(current) if current != str(abc) else None)


# --------------------------------------------------------------------------
# Model-driven transformation
# --------------------------------------------------------------------------
# Minimal built-in fallback. The authoritative prompt text lives in
# ``prompts/system/yue2-cover/abc-transformer.txt``.
TRANSFORMER_ROLE_FALLBACK = """\
You are the score transformer of a YuE2 cover studio. You receive a native
two-voice ABC score, a structured interpretation profile and a cover plan, and
you return one revised score in the same dialect. You output a single JSON object
with the keys abc, changes and warnings, and nothing else."""


def _transformer_role() -> str:
    """The transformer role prompt, resolved from the bundled resource file.

    The text lives in ``resources/yue2/abc-transformer.txt``.
    """
    from .cover_prompts import transformer_role
    return transformer_role()


def transform_prompt(
    profile: CoverInterpretationProfile,
    cover_mode: CoverMode | str,
    source_abc: str,
    target_style: str = "",
    plan: Optional[Dict] = None,
    reference: Optional[str] = None,
) -> Tuple[str, str]:
    """The (system, user) pair for the ABC transformation call."""
    request = transformation_request(profile, cover_mode, source_abc, target_style, plan)
    system = "\n\n".join([
        _transformer_role(),
        "# YuE2 native ABC reference (authoritative for this task)\n"
        + (reference if reference is not None else abc_reference()),
        "# Interpretation profile\n"
        + _profile_lines(profile),
    ])
    user = (
        "Transform the score for this cover. Answer with the JSON object only.\n\n"
        + _json_block(request)
    )
    return system, user


def _profile_lines(profile: CoverInterpretationProfile) -> str:
    preserve = profile.preserve_request()
    allow = profile.allowed_changes()
    return "\n".join([
        f"Interpretation freedom: {profile.freedom}/100 ({profile.band_label}).",
        "Preserve: " + ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in preserve.items()),
        "Allowed changes: " + ", ".join(f"{k}={v}" for k, v in allow.items()),
        "Melody-only (chord-free) target: " + ("yes" if profile.melody_only else "no"),
    ])


def _json_block(payload: Dict) -> str:
    import json
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


def parse_json_object(text: str) -> Optional[Dict]:
    """First JSON object in a model answer, fences and prose tolerated."""
    import json
    raw = str(text or "")
    if not raw.strip():
        return None
    fence = raw.find("```")
    while fence != -1:
        start = raw.find("\n", fence)
        if start == -1:
            break
        end = raw.find("```", start)
        if end == -1:
            break
        candidate = raw[start:end]
        try:
            data = json.loads(candidate)
        except ValueError:
            fence = raw.find("```", end + 3)
            continue
        if isinstance(data, dict):
            return data
        fence = raw.find("```", end + 3)
    depth = 0
    begin = -1
    for index, char in enumerate(raw):
        if char == "{":
            if depth == 0:
                begin = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and begin != -1:
                try:
                    data = json.loads(raw[begin:index + 1])
                except ValueError:
                    begin = -1
                    continue
                if isinstance(data, dict):
                    return data
                begin = -1
    return None


def apply_model_transform(
    source_abc: str,
    model_text: str,
    fallback: TransformResult,
    profile: CoverInterpretationProfile,
) -> TransformResult:
    """Validate a model answer and fall back to the deterministic result if it fails.

    The fallback is always a valid score, so a bad model answer degrades the
    amount of reinterpretation but never the ability to render the cover.
    """
    payload = parse_json_object(model_text)
    if payload is None:
        return TransformResult(
            fallback.abc, list(fallback.changes),
            [*fallback.warnings, "the transformer returned no JSON object; deterministic result kept"],
            "deterministic_fallback", fallback.validation, model_abc_rejected=True)

    candidate = payload.get("abc")
    if not isinstance(candidate, str) or not candidate.strip():
        return TransformResult(
            fallback.abc, list(fallback.changes),
            [*fallback.warnings, "the transformer JSON carried no ABC string; deterministic result kept"],
            "deterministic_fallback", fallback.validation, model_abc_rejected=True)

    validation = validate_abc(candidate, source=source_abc)
    warnings = list(fallback.warnings) + [str(item) for item in (payload.get("warnings") or [])]
    if not validation.ok:
        return TransformResult(
            fallback.abc, list(fallback.changes),
            [*warnings, "the transformed ABC failed validation: " + "; ".join(validation.errors[:3])],
            "deterministic_fallback", fallback.validation, model_abc_rejected=True)

    comparison = validation.facts.get("comparison") or {}
    guard = _invariant_guard(profile, comparison)
    if guard:
        return TransformResult(
            fallback.abc, list(fallback.changes),
            [*warnings, guard],
            "deterministic_fallback", fallback.validation, model_abc_rejected=True)

    changes = [str(item) for item in (payload.get("changes") or [])]
    return TransformResult(validation.abc, changes, warnings, "model", validation)


def _invariant_guard(profile: CoverInterpretationProfile, comparison: Dict) -> str:
    """Reject a model score that broke an invariant the profile pinned.

    An element counts as pinned when the profile both preserves it and allows no
    variation.  That is exactly the faithful end of the slider: at freedom 0 the
    model may not touch a single note, chord, bar or the tempo, whatever it
    decided the score should sound like.  Further up the slider the corresponding
    line is released and the change is reported instead of rejected.
    """
    if not comparison.get("comparable"):
        return ""
    changes = comparison.get("changes") or {}
    notes = changes.get("notes") or {}
    bars = changes.get("bars") or {}
    chords = changes.get("chords") or {}

    if profile.preserve_tempo >= 0.9 and changes.get("tempo"):
        return ("the transformed ABC changed the tempo although the profile requires it "
                "to be preserved; deterministic result kept")
    if (profile.allow_structure_change <= 0.0 and profile.preserve_structure >= 0.9
            and (bars.get("Vocal") or bars.get("Ins"))):
        return ("the transformed ABC changed the bar/meter grid although the profile "
                "requires the structure to be preserved; deterministic result kept")
    if (profile.allow_melody_variation <= 0.0 and profile.preserve_main_melody >= 0.9
            and (notes.get("Vocal") or notes.get("Ins"))):
        return ("the transformed ABC rewrote sounding notes although the profile allows no "
                "melody variation; deterministic result kept")
    if (profile.allow_harmony_change <= 0.0 and profile.preserve_harmony >= 0.9
            and (chords.get("Vocal") or chords.get("Ins"))):
        return ("the transformed ABC changed the chord symbols although the profile requires "
                "the harmony to be preserved; deterministic result kept")
    return ""


def build_result_report(
    profile: CoverInterpretationProfile,
    cover_mode: CoverMode | str,
    source_abc: str,
    result: TransformResult,
    cover_lyrics: str = "",
) -> Dict[str, object]:
    """The debug/apply record: profile, plan, score and fit in one place."""
    mode = cover_mode if isinstance(cover_mode, CoverMode) else cover_mode_for(cover_mode)
    report: Dict[str, object] = {
        "schema": "cover_studio_report_v1",
        "cover_mode": mode.value,
        "profile": profile.as_report(),
        "transformation": result.as_report(),
        "final_abc_sha256": _sha256(result.abc),
        "lyrics_fit": None,
    }
    if cover_lyrics.strip():
        from .lyrics_fit import analyse_lyrics_fit
        report["lyrics_fit"] = analyse_lyrics_fit(result.abc, cover_lyrics).as_report()
    return report


def _sha256(text: str) -> str:
    import hashlib
    return hashlib.sha256(str(text).strip().encode("utf-8")).hexdigest()


__all__ = [
    "TRANSFORMER_ROLE_FALLBACK",
    "TransformResult",
    "apply_deterministic",
    "apply_model_transform",
    "build_result_report",
    "parse_json_object",
    "scaled_tempo",
    "set_tempo",
    "transform_prompt",
    "transpose_abc",
    "transpose_chord",
    "transpose_key_name",
]
