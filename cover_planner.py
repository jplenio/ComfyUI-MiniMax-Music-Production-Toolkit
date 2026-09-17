"""The planning stage of the YuE2 Cover Studio.

The plan comes first and the score is transformed second.  That ordering is the
whole point: a model that is asked to "make this more creative" in one step has
no obligation to say what it intended to keep.  A plan that lists the preserved
and the changed elements explicitly can be shown to the user, stored with the
production record, and - most importantly - checked afterwards against the score
that was actually produced.

The planner never touches the ABC.  It only reads the analysis it is given and
answers with a structured plan.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .abc_validate import section_labels
from .cover_profiles import CoverInterpretationProfile, CoverMode, cover_mode_for
from .cover_score import VOCAL_VOICE, count_melody_notes, parse_cover_score
from .cover_transform import _json_block, parse_json_object
from .lyrics_fit import analyse_lyrics_fit

# Minimal built-in fallback. The authoritative prompt text lives in
# ``prompts/system/yue2-cover/cover-planner.txt``; this copy exists only so a
# partial source checkout still produces a usable prompt.
PLANNER_ROLE_FALLBACK = """\
You are the cover planner of a YuE2 cover studio. You read one existing song's
score analysis and answer with a short, concrete production plan. You do not
write music notation and you do not write lyrics. You output a single JSON object
with the keys preserve, change, target and warnings, and nothing else."""

_PLAN_FIELDS = ("preserve", "change", "target")


def _planner_role() -> str:
    """The planner role prompt, resolved from the bundled resource file.

    The text lives in ``resources/yue2/cover-planner.txt``.  Editing that file
    takes effect on the next queue without touching Python.
    """
    from .cover_prompts import planner_role
    return planner_role()


def score_analysis(abc: str, lyrics: str = "") -> Dict[str, object]:
    """Compact, factual summary of the score that the plan is built from."""
    score = parse_cover_score(abc)
    sections: List[Dict[str, object]] = []
    for section in score.sections:
        sections.append({
            "index": section.index,
            "label": section.label,
            "vocal_note_onsets": count_melody_notes(section.melody(VOCAL_VOICE)),
        })
    analysis: Dict[str, object] = {
        "section_labels": section_labels(abc),
        "sections": sections,
        "vocal_note_onsets_total": sum(item["vocal_note_onsets"] for item in sections),
        "has_vocal_notes": any(item["vocal_note_onsets"] for item in sections),
    }
    try:
        from .third_party.yue2_abc import parse_abc
        parsed = parse_abc(abc.strip())
        analysis.update({
            "key": next((line[2:].strip() for line in abc.splitlines()
                         if line.startswith("K:")), ""),
            "meter": next((line[2:].strip() for line in abc.splitlines()
                           if line.startswith("M:")), ""),
            "tempo_bpm": parsed.bpm,
            "measures": len(parsed.voices[VOCAL_VOICE].bars),
            "duration_seconds": round(float(parsed.voices[VOCAL_VOICE].time * 60 / parsed.bpm), 2),
        })
    except (ValueError, KeyError):
        analysis["analysis_note"] = "the strict native structure check did not apply to this score"
    if lyrics.strip():
        fit = analyse_lyrics_fit(abc, lyrics)
        analysis["lyrics_fit"] = fit.as_report()
    return analysis


def plan_prompt(
    profile: CoverInterpretationProfile,
    cover_mode: CoverMode | str,
    source_abc: str,
    target_style: str = "",
    lyrics: str = "",
) -> Tuple[str, str]:
    """The (system, user) pair for the cover-planning call."""
    mode = cover_mode if isinstance(cover_mode, CoverMode) else cover_mode_for(cover_mode)
    audio_reference = "" if mode.carries_lyrics else (
        "This cover is instrumental: the plan must not describe singers, choirs or "
        "sung words, and it must name the instrument that carries the melodic line."
    )
    system = "\n\n".join(part for part in [
        _planner_role(),
        "# Interpretation profile\n" + _profile_brief(profile),
        audio_reference,
    ] if part)

    payload: Dict[str, object] = {
        "task": "plan_yue2_cover",
        "style_priority": (
            "The requested style always governs the result. The plan may decide how much of the "
            "source material survives; it may never reduce, replace or reinterpret the style."
        ),
        "target_style_scope": (
            "Hint for reworking the source material only. The style the track is rendered in comes "
            "from the song request (selected template, user brief and its fields) and is never "
            "changed here. An empty target_style means 'no extra hint', not 'keep the source's "
            "character'."
        ),
        "cover_mode": mode.value,
        "interpretation_freedom": profile.freedom,
        "band": profile.band,
        "preserve_required": [key for key, value in profile.preserve_request().items() if value],
        "allowed_changes": profile.allowed_changes(),
        "target_style": str(target_style or "").strip(),
        "score_analysis": score_analysis(source_abc, lyrics),
    }
    if profile.notes:
        payload["band_guidance"] = list(profile.notes)
    user = ("Plan this cover. Answer with the JSON object only.\n\n" + _json_block(payload))
    return system, user


STYLE_PRIORITY = (
    "Scope: the permissions and the freedom value below apply to the SOURCE MATERIAL only. "
    "They never apply to the requested style. The target style and the selected template keep "
    "governing genre, instrumentation, production and character at every freedom level; a higher "
    "freedom value means that less of the source is retained, never that less of the requested "
    "style is delivered."
)


def _profile_brief(profile: CoverInterpretationProfile) -> str:
    preserve = profile.preserve_request()
    allow = profile.allowed_changes()
    lines = [f"Interpretation freedom {profile.freedom}/100 - {profile.band_label}.",
             STYLE_PRIORITY]
    lines.extend("- " + note for note in profile.notes)
    required = ", ".join(k for k, v in preserve.items() if v)
    lines.append("Must preserve: " + (required or "nothing"))
    lines.append("May change: " + ", ".join(f"{k} ({v})" for k, v in allow.items()))
    return "\n".join(lines)


def parse_plan(text: str) -> Optional[Dict[str, object]]:
    """Validate a planner answer. Returns ``None`` when it is unusable."""
    payload = parse_json_object(text)
    if payload is None:
        return None
    plan: Dict[str, object] = {}
    for field_name in _PLAN_FIELDS:
        value = payload.get(field_name)
        if field_name == "target":
            if value is None:
                plan["target"] = {}
            elif isinstance(value, dict):
                plan["target"] = {str(k): v for k, v in value.items()}
            else:
                return None
            continue
        if value is None:
            plan[field_name] = []
            continue
        if not isinstance(value, (list, tuple)):
            return None
        plan[field_name] = [str(item).strip() for item in value if str(item).strip()]
    warnings = payload.get("warnings") or []
    plan["warnings"] = [str(item) for item in warnings] if isinstance(warnings, (list, tuple)) else []
    plan["source"] = "model"
    return plan


def plan_summary(plan: Optional[Dict[str, object]]) -> str:
    """One compact block for the transformer prompt and the debug output."""
    if not plan:
        return "No plan was available; transform strictly according to the profile."
    lines = ["Keep: " + (", ".join(plan.get("preserve") or []) or "(nothing specified)"),
             "Change: " + (", ".join(plan.get("change") or []) or "(nothing specified)")]
    target = plan.get("target") or {}
    if target:
        lines.append("Target: " + ", ".join(
            f"{key}={value}" for key, value in target.items() if value not in (None, "")))
    if plan.get("warnings"):
        lines.append("Planner warnings: " + "; ".join(str(item) for item in plan["warnings"]))
    return "\n".join(lines)


def plan_contradictions(plan: Optional[Dict[str, object]],
                        profile: CoverInterpretationProfile) -> List[str]:
    """Plan entries that contradict an element the profile pinned.

    The plan is advisory, but a plan that promises to change what the profile
    preserves would make the transformation stage self-contradictory, so the
    conflict is surfaced instead of averaged away.
    """
    if not plan:
        return []
    forbidden = {
        "harmony": ("harmony", "chord", "reharmoni", "progression"),
        "structure": ("structure", "form", "intro", "outro", "verse order", "arrangement"),
        "tempo": ("tempo", "bpm", "speed"),
        "key": ("key", "transpos"),
        "main_melody": ("melody", "tune", "vocal line"),
        "chorus_hook": ("hook", "chorus"),
    }
    preserve = profile.preserve_request()
    conflicts: List[str] = []
    for element, pinned in preserve.items():
        if not pinned:
            continue
        terms = forbidden.get(element, ())
        for entry in plan.get("change") or []:
            lowered = str(entry).casefold()
            if any(term in lowered for term in terms):
                conflicts.append(f"the plan changes '{entry}' although {element} is preserved")
    return conflicts


__all__ = [
    "PLANNER_ROLE_FALLBACK",
    "parse_plan",
    "plan_contradictions",
    "plan_prompt",
    "plan_summary",
    "score_analysis",
]
