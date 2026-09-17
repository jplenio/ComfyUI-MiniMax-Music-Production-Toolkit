"""Interpretation profiles for the YuE2 Cover Studio.

The user sees one slider, *Interpretation Freedom* (0-100).  It is a pure
toolkit abstraction: YuE2 has no such parameter, and nothing in this module is
forwarded to the engine verbatim.  The slider is translated here into a
structured :class:`CoverInterpretationProfile` whose individual knobs are then
realised by concrete operations elsewhere:

* ``melody_only``      -> ``third_party.yue2_abc.strip_chords`` (validated)
* ``preserve_tempo``   -> a deterministic ``Q:1/4=`` rewrite (see cover_transform)
* ``preserve_key``     -> a deterministic transposition request
* everything else      -> explicit, structured instructions to the LLM stages

Keeping the mapping in one place is what makes the slider testable and
reviewable: the same freedom value always yields the same profile, and an
explicit user override always wins over the automatic value.

Nothing in this module imports ComfyUI, touches the file system or performs a
model call.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Optional

from .cover_score import (
    LYRICS_MODE_INSTRUMENTAL,
    LYRICS_MODE_NEW,
    LYRICS_MODE_ORIGINAL,
    normalize_lyrics_mode,
)

# --------------------------------------------------------------------------
# Cover mode
# --------------------------------------------------------------------------
# One enumeration instead of free-form strings.  The values are deliberately
# identical to the lyrics-mode strings that cover_score.py has always used, so
# the enum is a typed view over the existing single source of truth and no
# stored workflow value has to be migrated.


class CoverMode(str, Enum):
    """The three supported cover modes."""

    INSTRUMENTAL = LYRICS_MODE_INSTRUMENTAL
    ORIGINAL_LYRICS = LYRICS_MODE_ORIGINAL
    NEW_LYRICS = LYRICS_MODE_NEW

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.value

    @property
    def lyrics_mode(self) -> str:
        """The ``lyrics_mode`` string the rest of the toolkit already speaks."""
        return self.value

    @property
    def carries_lyrics(self) -> bool:
        return self is not CoverMode.INSTRUMENTAL

    @property
    def uses_transcription(self) -> bool:
        """Both lyric-bearing modes need the source words; instrumental does not."""
        return self is CoverMode.ORIGINAL_LYRICS


def cover_mode_for(lyrics_mode) -> CoverMode:
    """Resolve any stored/typed lyrics-mode value onto :class:`CoverMode`.

    Delegates to :func:`cover_score.normalize_lyrics_mode`, so legacy aliases and
    the "unknown explicit mode is an error" rule stay in one place.
    """
    return CoverMode(normalize_lyrics_mode(lyrics_mode))


# --------------------------------------------------------------------------
# Freedom slider
# --------------------------------------------------------------------------
MIN_FREEDOM = 0
MAX_FREEDOM = 100

# The bands are the user-facing semantics of the slider.  Boundaries are the
# values at which the automatic profile starts to move into the next band.
_FREEDOM_BANDS = (
    (0, 20, "faithful", "Faithful cover"),
    (21, 40, "arrangement", "Arrangement cover"),
    (41, 60, "reinterpretation", "Reinterpretation"),
    (61, 80, "creative", "Creative reinterpretation"),
    (81, 95, "loose", "Loose adaptation"),
    (96, 100, "inspired", "Inspired recomposition"),
)

# Automatic profiles at the band boundaries, interpolated linearly in between.
# Anchor 0 is a pure faithful cover; anchor 100 keeps almost nothing but the
# compositional idea.  Every value here is a *request* to the later stages, not
# a claim about what the engine will render.
_ANCHOR_FREEDOMS = (0, 20, 40, 60, 80, 95, 100)

_ANCHOR_PROFILES = (
    # freedom 0 - faithful: only production, sounds and vocal timbre may move.
    dict(preserve_main_melody=1.0, preserve_hook=1.0, preserve_structure=1.0,
         preserve_harmony=1.0, preserve_tempo=1.0, preserve_key=1.0,
         allow_melody_variation=0.0, allow_rhythm_variation=0.0,
         allow_harmony_change=0.0, allow_structure_change=0.0, melody_only=False),
    # freedom 20 - end of the faithful band: still the same song, new clothes.
    dict(preserve_main_melody=1.0, preserve_hook=1.0, preserve_structure=0.95,
         preserve_harmony=0.8, preserve_tempo=1.0, preserve_key=0.9,
         allow_melody_variation=0.1, allow_rhythm_variation=0.1,
         allow_harmony_change=0.25, allow_structure_change=0.1, melody_only=False),
    # freedom 40 - end of the arrangement band: melody and hook stay, harmony may go.
    dict(preserve_main_melody=0.9, preserve_hook=1.0, preserve_structure=0.8,
         preserve_harmony=0.4, preserve_tempo=0.75, preserve_key=0.65,
         allow_melody_variation=0.25, allow_rhythm_variation=0.35,
         allow_harmony_change=0.65, allow_structure_change=0.35, melody_only=True),
    # freedom 60 - end of the reinterpretation band.
    dict(preserve_main_melody=0.65, preserve_hook=0.9, preserve_structure=0.6,
         preserve_harmony=0.25, preserve_tempo=0.5, preserve_key=0.4,
         allow_melody_variation=0.45, allow_rhythm_variation=0.55,
         allow_harmony_change=0.8, allow_structure_change=0.55, melody_only=True),
    # freedom 80 - end of the creative band: only the musical identity is kept.
    dict(preserve_main_melody=0.4, preserve_hook=0.7, preserve_structure=0.4,
         preserve_harmony=0.15, preserve_tempo=0.35, preserve_key=0.25,
         allow_melody_variation=0.65, allow_rhythm_variation=0.7,
         allow_harmony_change=0.9, allow_structure_change=0.75, melody_only=True),
    # freedom 95 - end of the loose band: selected motifs and a rough dramaturgy.
    dict(preserve_main_melody=0.2, preserve_hook=0.45, preserve_structure=0.2,
         preserve_harmony=0.1, preserve_tempo=0.2, preserve_key=0.1,
         allow_melody_variation=0.85, allow_rhythm_variation=0.85,
         allow_harmony_change=0.95, allow_structure_change=0.9, melody_only=True),
    # freedom 100 - inspired recomposition: key, tempo and character, nothing else.
    dict(preserve_main_melody=0.1, preserve_hook=0.3, preserve_structure=0.1,
         preserve_harmony=0.05, preserve_tempo=0.1, preserve_key=0.05,
         allow_melody_variation=1.0, allow_rhythm_variation=1.0,
         allow_harmony_change=1.0, allow_structure_change=1.0, melody_only=True),
)


def clamp_freedom(value) -> int:
    """Coerce any stored/typed slider value onto the documented 0-100 range."""
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        raise ValueError("YuE2 Cover Studio: interpretation_freedom must be a number from 0 to 100.") from None
    return max(MIN_FREEDOM, min(MAX_FREEDOM, number))


def freedom_band(freedom) -> Dict[str, object]:
    """The user-facing band of one freedom value (key, label, inclusive range)."""
    value = clamp_freedom(freedom)
    for low, high, key, label in _FREEDOM_BANDS:
        if low <= value <= high:
            return {"key": key, "label": label, "minimum": low, "maximum": high}
    # Unreachable for a clamped value; keeps the return type total.
    return {"key": "faithful", "label": "Faithful cover", "minimum": 0, "maximum": 20}


@dataclass(frozen=True)
class CoverInterpretationProfile:
    """The structured meaning of one Interpretation-Freedom value.

    ``preserve_*`` and ``allow_*`` are independent 0..1 weights.  They describe
    different questions ("does this element stay recognisable?" versus "is the
    stage permitted to rework it?"), which is why they are not complements: a
    hook can be preserved *and* the melody around it freely ornamented.
    """

    freedom: int
    band: str
    band_label: str

    preserve_main_melody: float
    preserve_hook: float
    preserve_structure: float
    preserve_harmony: float
    preserve_tempo: float
    preserve_key: float

    allow_melody_variation: float
    allow_rhythm_variation: float
    allow_harmony_change: float
    allow_structure_change: float

    melody_only: bool
    cot_mode: str

    @property
    def notes(self) -> tuple:
        """Human-readable rules of the band, for UI help and debug output."""
        return _BAND_NOTES[self.band]

    @property
    def melody_only_note(self) -> str:
        """Why the chord-free reduction is or is not applied."""
        if self.melody_only:
            return ("Applied: a melody-mode cover hands the engine the chord-free score its "
                    "decode mode expects; the freedom level decides how early this starts.")
        if self.cot_mode == "full":
            return ("Not applied: 'full' mode promises melody and harmony, so the score keeps "
                    "its chords and the score stays in agreement with the decode mode. Select "
                    "'melody' on Cover song / source audio for a chord-free score.")
        return "Not applied: this freedom level still preserves the source harmony."

    def preserve_request(self, threshold: float = 0.5) -> Dict[str, bool]:
        """Boolean view of the preserve weights for the structured LLM input."""
        return {
            "main_melody": self.preserve_main_melody >= threshold,
            "chorus_hook": self.preserve_hook >= threshold,
            "structure": self.preserve_structure >= threshold,
            "harmony": self.preserve_harmony >= threshold,
            "tempo": self.preserve_tempo >= threshold,
            "key": self.preserve_key >= threshold,
        }

    def change_degree(self, weight: float) -> str:
        """Map one 0..1 allowance onto the documented four-step vocabulary."""
        if weight <= 0.05:
            return "none"
        if weight < 0.35:
            return "low"
        if weight < 0.7:
            return "moderate"
        return "high"

    def allowed_changes(self) -> Dict[str, str]:
        return {
            "melody_variation": self.change_degree(self.allow_melody_variation),
            "rhythm_variation": self.change_degree(self.allow_rhythm_variation),
            "harmony_change": self.change_degree(self.allow_harmony_change),
            "structure_change": self.change_degree(self.allow_structure_change),
        }

    def as_report(self) -> Dict[str, object]:
        """Serializable snapshot for debug outputs and provenance records."""
        return {
            "schema": "cover_interpretation_profile_v1",
            "freedom": self.freedom,
            "band": self.band,
            "band_label": self.band_label,
            "preserve": {
                "main_melody": round(self.preserve_main_melody, 3),
                "chorus_hook": round(self.preserve_hook, 3),
                "structure": round(self.preserve_structure, 3),
                "harmony": round(self.preserve_harmony, 3),
                "tempo": round(self.preserve_tempo, 3),
                "key": round(self.preserve_key, 3),
            },
            "allow": {
                "melody_variation": round(self.allow_melody_variation, 3),
                "rhythm_variation": round(self.allow_rhythm_variation, 3),
                "harmony_change": round(self.allow_harmony_change, 3),
                "structure_change": round(self.allow_structure_change, 3),
            },
            "melody_only": self.melody_only,
            "melody_only_note": self.melody_only_note,
            "cot_mode": self.cot_mode,
            "cot_note": (
                "Advisory only. The decode mode (cot full/melody) is owned by the cover source "
                "mode, because the same setting also drives the SheetSage2 transcription."
            ),
            "notes": list(self.notes),
        }


_BAND_NOTES = {
    "faithful": (
        "Keep main melody, structure, harmony, tempo, key, hooks and phrase boundaries.",
        "Instruments, sound design, production and vocal timbre may change.",
        "Change the score as little as possible.",
    ),
    "arrangement": (
        "Keep main melody, chorus hook, song structure and the basic tempo.",
        "Harmony, arrangement, instrumentation, accompaniment and intro/outro may change.",
        "Prefer a chord-free melody line for the arrangement stage.",
    ),
    "reinterpretation": (
        "Keep the central melodies, the important hooks and the approximate song structure.",
        "Harmony, tempo, key, accompaniment, rhythm, instrumentation and transitions may change.",
        "The score may be transformed in a controlled way.",
    ),
    "creative": (
        "Keep only the central musical identity: chorus hook, key motifs, characteristic phrases.",
        "Melody may be simplified or ornamented; rhythm, local pitches and section lengths may move.",
        "New accompaniment, new harmony and genre-appropriate adaptation are allowed.",
    ),
    "loose": (
        "Keep selected motifs, optionally the chorus melody, and the basic dramaturgy.",
        "Everything else may be redesigned.",
    ),
    "inspired": (
        "Analyse the source but use it only as a compositional reference.",
        "Extract key, tempo, structure, motifs, a hook description and the harmonic character.",
        "Then compose rather than reproduce.",
    ),
}


def _interpolate(freedom: int, field: str) -> float:
    """Piecewise-linear interpolation of one knob across the anchor profiles."""
    lower = _ANCHOR_FREEDOMS[0]
    for index in range(1, len(_ANCHOR_FREEDOMS)):
        upper = _ANCHOR_FREEDOMS[index]
        if freedom <= upper:
            left = float(_ANCHOR_PROFILES[index - 1][field])
            right = float(_ANCHOR_PROFILES[index][field])
            if upper == lower:
                return right
            position = (freedom - lower) / (upper - lower)
            return round(left + (right - left) * position, 4)
        lower = upper
    return float(_ANCHOR_PROFILES[-1][field])


def interpretation_profile(freedom, cot_mode: str = "melody") -> CoverInterpretationProfile:
    """Build the automatic profile for one Interpretation-Freedom value.

    Deterministic and side-effect free: the same input always yields the same
    profile, which is what the freedom tests assert.
    """
    value = clamp_freedom(freedom)
    band = freedom_band(value)
    cot = _normalize_cot(cot_mode)
    # ``melody_only`` is a property of the *decode mode*, not of the slider: a
    # ``full`` cover promises melody and harmony, so its score keeps its chords
    # whatever the freedom value.  Removing them would hand ``cot="full"`` a
    # score it cannot read as a "melody and harmony" reference and let the model
    # invent the harmony - which is exactly where the requested style used to
    # get lost.
    melody_only = _interpolated_melody_only(value) and cot == "melody"
    return CoverInterpretationProfile(
        freedom=value,
        band=str(band["key"]),
        band_label=str(band["label"]),
        preserve_main_melody=_interpolate(value, "preserve_main_melody"),
        preserve_hook=_interpolate(value, "preserve_hook"),
        preserve_structure=_interpolate(value, "preserve_structure"),
        preserve_harmony=_interpolate(value, "preserve_harmony"),
        preserve_tempo=_interpolate(value, "preserve_tempo"),
        preserve_key=_interpolate(value, "preserve_key"),
        allow_melody_variation=_interpolate(value, "allow_melody_variation"),
        allow_rhythm_variation=_interpolate(value, "allow_rhythm_variation"),
        allow_harmony_change=_interpolate(value, "allow_harmony_change"),
        allow_structure_change=_interpolate(value, "allow_structure_change"),
        melody_only=melody_only,
        cot_mode=_normalize_cot(cot_mode),
    )


def _interpolated_melody_only(freedom: int) -> bool:
    """A chord-free melody line is the documented default from the arrangement
    band upward; below that the harmony is preserved, so the chords stay."""
    return freedom > 20


def _normalize_cot(value) -> str:
    text = str(value or "").strip().casefold()
    if text not in {"full", "melody"}:
        raise ValueError("YuE2 Cover Studio: cot mode must be 'full' or 'melody'.")
    return text


# --------------------------------------------------------------------------
# Explicit user overrides
# --------------------------------------------------------------------------
# The node widgets are tri-state on purpose.  A boolean cannot express the
# difference between "do not override" and "explicitly allow the change", and
# that difference is exactly what the override rule needs.
AUTO = "auto"
YES = "yes"
NO = "no"
OVERRIDE_CHOICES = (AUTO, YES, NO)

# The allowance knobs use a degree vocabulary instead of yes/no, because
# "allow the harmony to change: yes" says nothing about how far.
NONE = "none"
LOW = "low"
MODERATE = "moderate"
HIGH = "high"
DEGREE_CHOICES = (AUTO, NONE, LOW, MODERATE, HIGH)
_DEGREE_WEIGHTS = {NONE: 0.0, LOW: 0.25, MODERATE: 0.55, HIGH: 1.0}


def degree_weight(value: str, current: float) -> float:
    """Resolve one degree override; ``auto`` keeps the automatic weight."""
    text = str(value or AUTO).strip().casefold()
    if text == AUTO:
        return current
    if text not in _DEGREE_WEIGHTS:
        raise ValueError(
            f"YuE2 Cover Studio: expected one of {', '.join(DEGREE_CHOICES)} for a change degree.")
    return _DEGREE_WEIGHTS[text]


@dataclass(frozen=True)
class CoverOverrides:
    """Explicit user decisions. ``AUTO`` everywhere means "use the profile"."""

    preserve_main_melody: str = AUTO
    preserve_hook: str = AUTO
    preserve_structure: str = AUTO
    preserve_harmony: str = AUTO
    preserve_tempo: str = AUTO
    preserve_key: str = AUTO

    melody_only: str = AUTO
    structure_freedom: str = AUTO
    melody_variation: str = AUTO
    harmony_freedom: str = AUTO
    rhythm_variation: str = AUTO

    def normalized(self) -> "CoverOverrides":
        def check(value, name, choices=OVERRIDE_CHOICES):
            text = str(value or AUTO).strip().casefold()
            if text not in choices:
                raise ValueError(
                    f"YuE2 Cover Studio: {name} must be one of {', '.join(choices)}.")
            return text

        return replace(
            self,
            preserve_main_melody=check(self.preserve_main_melody, "preserve_main_melody"),
            preserve_hook=check(self.preserve_hook, "preserve_chorus_hook"),
            preserve_structure=check(self.preserve_structure, "preserve_structure"),
            preserve_harmony=check(self.preserve_harmony, "preserve_harmony"),
            preserve_tempo=check(self.preserve_tempo, "preserve_tempo"),
            preserve_key=check(self.preserve_key, "preserve_key"),
            melody_only=check(self.melody_only, "melody_only"),
            structure_freedom=check(self.structure_freedom, "structure_freedom", DEGREE_CHOICES),
            melody_variation=check(self.melody_variation, "melody_variation", DEGREE_CHOICES),
            harmony_freedom=check(self.harmony_freedom, "harmony_freedom", DEGREE_CHOICES),
            rhythm_variation=check(self.rhythm_variation, "rhythm_variation", DEGREE_CHOICES),
        )

    def active(self) -> Dict[str, str]:
        """Only the fields the user actually set, for report and provenance."""
        data = self.normalized()
        return {name: value for name, value in vars(data).items() if value != AUTO}


def _apply_override(current: float, override: str, preserve: bool) -> float:
    """``yes`` pins the knob to its maximum, ``no`` releases it to its minimum."""
    if override == YES:
        return 1.0 if preserve else 0.0
    if override == NO:
        return 0.0 if preserve else 1.0
    return current


def resolve_profile(
    profile: CoverInterpretationProfile,
    overrides: Optional[CoverOverrides] = None,
) -> CoverInterpretationProfile:
    """Automatic profile in, explicit user decisions on top.

    The result is a new frozen profile; the input is never mutated.  Every
    override that the user actually set is recorded in the returned report so a
    later stage (and the user) can see why the final configuration differs from
    the automatic one.
    """
    if overrides is None:
        return profile
    data = overrides.normalized()
    if data.melody_only == YES and profile.cot_mode != "melody":
        raise ValueError(
            "YuE2 Cover Studio: melody_only would remove the harmony from a 'full' cover, so the "
            "score and the decode mode would disagree. Select 'melody' on Cover song / source "
            "audio first, or set melody_only back to auto.")
    melody_only = profile.melody_only if data.melody_only == AUTO else data.melody_only == YES
    return replace(
        profile,
        preserve_main_melody=_apply_override(profile.preserve_main_melody, data.preserve_main_melody, True),
        preserve_hook=_apply_override(profile.preserve_hook, data.preserve_hook, True),
        preserve_structure=_apply_override(profile.preserve_structure, data.preserve_structure, True),
        preserve_harmony=_apply_override(profile.preserve_harmony, data.preserve_harmony, True),
        preserve_tempo=_apply_override(profile.preserve_tempo, data.preserve_tempo, True),
        preserve_key=_apply_override(profile.preserve_key, data.preserve_key, True),
        allow_melody_variation=degree_weight(data.melody_variation, profile.allow_melody_variation),
        allow_rhythm_variation=degree_weight(data.rhythm_variation, profile.allow_rhythm_variation),
        allow_harmony_change=degree_weight(data.harmony_freedom, profile.allow_harmony_change),
        allow_structure_change=degree_weight(data.structure_freedom, profile.allow_structure_change),
        melody_only=melody_only,
    )


def build_profile(
    freedom,
    cover_mode: CoverMode | str,
    overrides: Optional[CoverOverrides] = None,
    cot_mode: str = "melody",
) -> CoverInterpretationProfile:
    """The one entry point the nodes use: freedom + mode + overrides -> profile."""
    mode = cover_mode if isinstance(cover_mode, CoverMode) else cover_mode_for(cover_mode)
    base = interpretation_profile(freedom, cot_mode)
    if mode is CoverMode.INSTRUMENTAL:
        # Instrumental covers have no words, so "preserve the hook" cannot mean
        # the sung hook.  The melodic line still carries the identity.
        base = replace(base, preserve_main_melody=max(base.preserve_main_melody, 0.9))
    return resolve_profile(base, overrides)


def transformation_request(
    profile: CoverInterpretationProfile,
    cover_mode: CoverMode | str,
    source_abc: str,
    target_style: str = "",
    plan: Optional[Dict] = None,
) -> Dict[str, object]:
    """The structured input the ABC transformer receives - never free prose."""
    mode = cover_mode if isinstance(cover_mode, CoverMode) else cover_mode_for(cover_mode)
    request: Dict[str, object] = {
        "task": "transform_abc_for_yue2_cover",
        "cover_mode": mode.value,
        "interpretation_freedom": profile.freedom,
        "band": profile.band,
        "preserve": profile.preserve_request(),
        "allowed_changes": profile.allowed_changes(),
        "melody_only": profile.melody_only,
        "cot_mode": profile.cot_mode,
        "target_style": str(target_style or "").strip(),
        "target_style_scope": (
            "Hint for reworking the source material only. The style the track is rendered in comes "
            "from the song request (selected template, user brief and its fields) and is never "
            "changed here. An empty target_style means 'no extra hint', not 'keep the source's "
            "character'."
        ),
        "abc_input": str(source_abc or "").strip(),
    }
    if plan:
        request["plan"] = plan
    return request


__all__ = [
    "AUTO",
    "CoverInterpretationProfile",
    "CoverMode",
    "CoverOverrides",
    "DEGREE_CHOICES",
    "MAX_FREEDOM",
    "MIN_FREEDOM",
    "NO",
    "OVERRIDE_CHOICES",
    "YES",
    "build_profile",
    "clamp_freedom",
    "cover_mode_for",
    "degree_weight",
    "freedom_band",
    "interpretation_profile",
    "resolve_profile",
    "transformation_request",
]
