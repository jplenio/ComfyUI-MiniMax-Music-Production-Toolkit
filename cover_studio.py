"""The YuE2 Cover Studio nodes.

Three small nodes instead of one large one, because each one is a single
reviewable step and ComfyUI already owns scheduling, caching and the graph:

    Cover Studio · 1 plan          -> system/user prompt + studio state
        (existing LLM Chat node)
    Cover Studio · 2 transform     -> system/user prompt + studio state
        (existing LLM Chat node)
    Cover Studio · 3 validate      -> final, validated ABC + report

The pipeline is deliberately ANALYZE -> PLAN -> TRANSFORM -> VALIDATE -> RENDER.
Two model calls at most (one plan, one transform, plus an optional repair), and
every score the model returns is validated before it can reach the generator.
When the studio is disabled, not wired, or attached to a non-cover model, the
score passes through byte for byte.

Nothing here changes an existing node or an existing workflow.  The studio is a
new, separate path that hands its result to the same ``cover_abc`` socket the
current cover pipeline already uses.
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, Optional

from .abc_validate import abc_reference, validate_abc
from .cover_planner import parse_plan, plan_contradictions, plan_prompt, plan_summary
from .cover_profiles import (
    AUTO,
    DEGREE_CHOICES,
    OVERRIDE_CHOICES,
    CoverMode,
    CoverOverrides,
    build_profile,
    cover_mode_for,
)
from .cover_transform import (
    TransformResult,
    apply_deterministic,
    apply_model_transform,
    build_result_report,
    transform_prompt,
)
from .cover_score import normalize_lead_instrument
from .lyrics_fit import repair_hint
from .music_cover import cover_source

STATE_SCHEMA = "cover_studio_state_v1"
STATE_PREFIX = "cover-studio:"

CATEGORY = "Music Production Toolkit/generation"

VOCAL_RANGES = (
    "auto",
    "Low male (E2-E4)",
    "Baritone (A2-A4)",
    "Tenor (C3-C5)",
    "Alto (F3-F5)",
    "Mezzo-soprano (A3-A5)",
    "Soprano (C4-C6)",
)

_COMMON_TOOLTIPS = {
    "enabled": "Turn the whole Cover Studio path on or off. Disabled, the incoming score is passed "
               "through byte for byte, so an existing workflow keeps behaving exactly as before.",
    "advanced_mode": "Off keeps the debug report concise. On adds the full transformation request "
                     "and a per-knob breakdown. It never changes which values are applied.",
    "interpretation_freedom": "Toolkit abstraction, not a YuE2 parameter: 0 keeps the song as faithful as "
                              "possible, 100 uses it only as a compositional reference. The slider drives "
                              "several real settings at once (what is preserved, what may be reworked).",
    "target_style": "Hint for how the studio should rework the source material toward the requested "
                    "style - it is NOT the style source. What the track sounds like is set by "
                    "'Song request · template & fields' (its template, fields and description), and that "
                    "request's STYLE PRIORITY rule is forwarded to the model unchanged. Left empty "
                    "there is simply no extra hint; filling it only guides the score rework and must "
                    "never contradict the song request. Do NOT wire the song request node into this "
                    "field: it consumes this studio's rewritten score, so it sits downstream of the "
                    "studio and a link from it back into the studio is a dependency cycle that makes "
                    "ComfyUI reject the whole prompt ('Dependency cycle detected'). Connect the "
                    "'Style hint · template or text' node here instead - it reads the same template "
                    "from outside the studio's chain - or type the hint, or leave it empty. The studio "
                    "prompts already state that the requested style is fixed by the song request and "
                    "is not theirs to change.",
    "cover_abc": "SheetSage2 score of the source audio. The Cover Studio validates and transforms a copy; "
                 "the original stays untouched in the graph.",
    "cover_source_json": "Cover source identity from Cover song / Source audio. It selects the cover mode "
                         "and is required before the studio does anything.",
    "cover_lyrics": "Optional transcription of the original words (the Whisper report). The studio uses "
                    "it to report how well the words fit the melodic material before a render is "
                    "spent; it never changes the words themselves. Which words are sung is decided by "
                    "the cover lyrics mode, and the master node (Song request) carries that decision.",
    "studio_json": "Cover Studio state passed between the studio nodes. It carries the profile, the plan, "
                   "the source score and the warnings so each step stays inspectable.",
    "plan_text": "Answer of the planning LLM call. A missing or unusable plan is not fatal: the studio then "
                 "follows the interpretation profile alone.",
    "transform_text": "Answer of the transformation LLM call, expected as a JSON object with the keys "
                      "abc, changes and warnings. Invalid scores are rejected and replaced by the "
                      "validated deterministic result.",
    "repair_text": "Optional answer of one repair attempt. It is only consulted when the first "
                   "transformation answer failed validation, and it is validated the same way.",
    "key_change": "Deterministic transposition in semitones, applied exactly and re-spelled against the "
                  "target key. 0 leaves the key alone.",
    "tempo_change": "Relative tempo change in percent, applied exactly by rewriting the Q: field. "
                    "0 leaves the tempo alone.",
    "vocal_range": "Requested singing range for the melody. It is a request to the model, not an enforced "
                   "constraint; the report says so.",
    "melody_only": "Explicit user decision that always wins over the automatic profile. Selecting yes "
                   "produces the chord-free melody line a melody-mode cover expects; auto follows the slider.",
    "lyrics_policy": "What happens to the words, independent of the Interpretation Freedom slider. auto lets "
                      "the cover lyrics mode decide (the normal case, and the only one where the words come "
                      "from Song request / Whisper); 'keep source words' locks the transcription verbatim; "
                      "'keep supplied words' locks the text in supplied_lyrics. These two are the only way the "
                      "studio contributes words, so the impossible combinations are refused instead of "
                      "guessed: an instrumental cover has no words to keep, and 'original lyrics' owns its "
                      "words from the transcription. The locked block leaves the studio on the locked_lyrics "
                      "output and reaches the parser by wire.",
    "supplied_lyrics": "The words to keep when lyrics_policy is 'keep supplied words'. They replace the "
                       "LLM's words verbatim in the parser, so they win over the template's lyrics theme and "
                       "over any model draft. They cannot create words where the mode forbids them: with "
                       "'instrumental' nothing is sung (the parser strips words from a cover even if a lock "
                       "arrives), and with 'original lyrics' the transcription is authoritative - the studio "
                       "refuses that combination. Write them with the same section tags as the arrangement, "
                       "because nothing is rewritten or syllable-aligned here.",
    "locked_lyrics": "The verbatim lyrics block the policy asks for, or empty for auto. Connect it to the "
                     "parser's cover_lyrics_lock input. Empty output changes nothing downstream.",
}

_PRESERVE_TOOLTIP = (
    "Explicit user decision that always wins over the automatic profile. "
    "'auto' uses the value the Interpretation Freedom slider produced; 'yes' pins the "
    "element to be preserved; 'no' releases it explicitly."
)
_DEGREE_TOOLTIP = (
    "Explicit user decision that always wins over the automatic profile. 'auto' uses the "
    "Interpretation Freedom value; otherwise none/low/moderate/high set how far this element "
    "may be reworked."
)


def studio_input_tooltips() -> Dict[str, str]:
    """Tooltips for the three studio nodes, keyed by input name."""
    tooltips = dict(_COMMON_TOOLTIPS)
    for name in ("preserve_main_melody", "preserve_chorus_hook", "preserve_structure",
                 "preserve_harmony", "preserve_tempo", "preserve_key"):
        tooltips[name] = _PRESERVE_TOOLTIP
    for name in ("melody_variation", "rhythm_variation", "harmony_freedom", "structure_freedom"):
        tooltips[name] = _DEGREE_TOOLTIP
    return tooltips


# Spent when the studio is inactive. The model calls still happen, so they are
# given a harmless, tiny job; the score itself is passed through untouched.
# What happens to the words.  Deliberately independent of the Interpretation
# Freedom slider: the slider changes the music, never the lyrics.  ``auto`` keeps
# the previous behaviour (the cover lyrics mode decides), the two locked policies
# make the words an explicit user decision.
LYRICS_POLICY_AUTO = "auto (mode decides)"
LYRICS_POLICY_SOURCE = "keep source words"
LYRICS_POLICY_SUPPLIED = "keep supplied words"
LYRICS_POLICIES = (LYRICS_POLICY_AUTO, LYRICS_POLICY_SOURCE, LYRICS_POLICY_SUPPLIED)


def _normalize_lyrics_policy(value) -> str:
    text = str(value or "").strip().casefold()
    for policy in LYRICS_POLICIES:
        if policy.casefold() == text:
            return policy
    legacy = {"auto": LYRICS_POLICY_AUTO, "source": LYRICS_POLICY_SOURCE,
              "source words": LYRICS_POLICY_SOURCE, "original": LYRICS_POLICY_SOURCE,
              "supplied": LYRICS_POLICY_SUPPLIED,
              "supplied words": LYRICS_POLICY_SUPPLIED, "manual": LYRICS_POLICY_SUPPLIED}
    if text in legacy:
        return legacy[text]
    raise ValueError(
        f"YuE2 Cover Studio: lyrics_policy must be one of {', '.join(LYRICS_POLICIES)}.")


_INACTIVE_SYSTEM = (
    "Cover Studio is inactive for this run. The score is passed through unchanged, so do not plan "
    "or transform anything. Answer with exactly {} and nothing else."
)
_INACTIVE_USER = "{}"


def _sha256(text: str) -> str:
    return hashlib.sha256(str(text or "").strip().encode("utf-8")).hexdigest()


def _cover_lyrics_text(value) -> str:
    """Plain transcript from either a Whisper report or raw text."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except ValueError:
            return raw
        if isinstance(data, dict) and data.get("schema") == "music_cover_lyrics_v1":
            return str(data.get("text") or "").strip()
        return raw
    return raw


def _dump(state: Dict) -> str:
    return json.dumps(state, ensure_ascii=False)


def _load(text) -> Optional[Dict]:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith(STATE_PREFIX):
        raw = raw[len(STATE_PREFIX):]
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("schema") != STATE_SCHEMA:
        return None
    return data


def _inactive_state(reason: str, abc: str = "") -> Dict:
    """An inactive state still carries the score, so it can pass through untouched."""
    return {
        "schema": STATE_SCHEMA,
        "enabled": False,
        "stage": "inactive",
        "reason": reason,
        "source_abc": str(abc or ""),
        "warnings": [reason],
    }


def _cover_mode_of(source: Optional[Dict]) -> Optional[CoverMode]:
    if not source:
        return None
    try:
        return cover_mode_for(source.get("lyrics_mode"))
    except ValueError:
        return None


class CoverStudioPlan:
    """Step 1: resolve the slider, analyse the score and build the planning prompt."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "cover_source_json": ("STRING", {"forceInput": True}),
                "cover_abc": ("STRING", {"forceInput": True}),
                "interpretation_freedom": ("INT", {"default": 30, "min": 0, "max": 100, "step": 1}),
                "target_style": ("STRING", {"default": "", "multiline": True}),
            },
            "optional": {
                "enabled": ("BOOLEAN", {"default": True}),
                "advanced_mode": ("BOOLEAN", {"default": False}),
                "cover_lyrics": ("STRING", {"forceInput": True}),
                "preserve_main_melody": (list(OVERRIDE_CHOICES), {"default": AUTO}),
                "preserve_chorus_hook": (list(OVERRIDE_CHOICES), {"default": AUTO}),
                "preserve_structure": (list(OVERRIDE_CHOICES), {"default": AUTO}),
                "preserve_harmony": (list(OVERRIDE_CHOICES), {"default": AUTO}),
                "preserve_tempo": (list(OVERRIDE_CHOICES), {"default": AUTO}),
                "preserve_key": (list(OVERRIDE_CHOICES), {"default": AUTO}),
                "melody_only": (list(OVERRIDE_CHOICES), {"default": AUTO}),
                "melody_variation": (list(DEGREE_CHOICES), {"default": AUTO}),
                "rhythm_variation": (list(DEGREE_CHOICES), {"default": AUTO}),
                "harmony_freedom": (list(DEGREE_CHOICES), {"default": AUTO}),
                "structure_freedom": (list(DEGREE_CHOICES), {"default": AUTO}),
                "key_change": ("INT", {"default": 0, "min": -12, "max": 12, "step": 1}),
                "tempo_change": ("INT", {"default": 0, "min": -50, "max": 50, "step": 5}),
                "vocal_range": (list(VOCAL_RANGES), {"default": VOCAL_RANGES[0]}),
                "lyrics_policy": (list(LYRICS_POLICIES), {"default": LYRICS_POLICY_AUTO}),
                "supplied_lyrics": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("system_prompt", "user_prompt", "studio_json")
    FUNCTION = "plan"
    CATEGORY = CATEGORY
    DESCRIPTION = (
        "YuE2 Cover Studio, step 1. Turns the Interpretation Freedom slider into a structured "
        "cover profile, analyses the source score and builds the planning prompt for the LLM Chat "
        "node. Never changes the score itself; the original ABC is passed through in the state.\n\n"
        "WHAT THIS NODE OWNS: how freely the source material may be reworked (the slider, the "
        "preserve/variation knobs, key and tempo changes) and, optionally, a hint for that rework "
        "(target_style) plus a lyrics lock (lyrics_policy / supplied_lyrics).\n"
        "WHAT IT DOES NOT OWN: what the track sounds like, and the other musical fields (genre, "
        "tempo, meter, key, language, voice, lyrics theme, length). Those come from 'Song request "
        "· template & fields' and reach the model through the final prompt; the cover lyrics mode "
        "there also decides which words are used. An empty target_style means 'no extra hint for "
        "the rework', not 'follow the source's character'."
    )

    def plan(self, cover_source_json="", cover_abc="", interpretation_freedom=30,
             target_style="", enabled=True, advanced_mode=False, cover_lyrics="",
             preserve_main_melody=AUTO, preserve_chorus_hook=AUTO, preserve_structure=AUTO,
             preserve_harmony=AUTO, preserve_tempo=AUTO, preserve_key=AUTO,
             melody_only=AUTO, melody_variation=AUTO, rhythm_variation=AUTO,
             harmony_freedom=AUTO, structure_freedom=AUTO,
             key_change=0, tempo_change=0, vocal_range=VOCAL_RANGES[0],
             lyrics_policy=LYRICS_POLICY_AUTO, supplied_lyrics=""):
        if not enabled:
            return (_INACTIVE_SYSTEM, _INACTIVE_USER,
                    _dump(_inactive_state("Cover Studio is switched off.", cover_abc)))
        source = None
        try:
            source = cover_source(cover_source_json)
        except (ValueError, TypeError):
            source = None
        mode = _cover_mode_of(source)
        if mode is None:
            return (_INACTIVE_SYSTEM, _INACTIVE_USER, _dump(_inactive_state(
                "Cover Studio needs a connected Cover source; the score passes through unchanged.",
                cover_abc)))
        score = str(cover_abc or "").strip()
        if not score:
            return (_INACTIVE_SYSTEM, _INACTIVE_USER, _dump(_inactive_state(
                "Cover Studio needs the transcribed score; connect Cover song / SheetSage2.",
                cover_abc)))

        validation = validate_abc(score)
        warnings = list(validation.warnings)
        if not validation.ok:
            warnings.extend(validation.errors)
        overrides = CoverOverrides(
            preserve_main_melody=preserve_main_melody,
            preserve_hook=preserve_chorus_hook,
            preserve_structure=preserve_structure,
            preserve_harmony=preserve_harmony,
            preserve_tempo=preserve_tempo,
            preserve_key=preserve_key,
            melody_only=melody_only,
            melody_variation=melody_variation,
            rhythm_variation=rhythm_variation,
            harmony_freedom=harmony_freedom,
            structure_freedom=structure_freedom,
        )
        profile = build_profile(
            interpretation_freedom, mode, overrides,
            cot_mode=str(source.get("mode") or "melody"))
        lyrics = _cover_lyrics_text(cover_lyrics)
        policy = _normalize_lyrics_policy(lyrics_policy)
        supplied = str(supplied_lyrics or "").strip()
        if policy == LYRICS_POLICY_SUPPLIED and not supplied:
            raise ValueError(
                "YuE2 Cover Studio: lyrics_policy 'keep supplied words' needs text in supplied_lyrics.")
        if policy == LYRICS_POLICY_SOURCE and not lyrics:
            raise ValueError(
                "YuE2 Cover Studio: lyrics_policy 'keep source words' needs the Whisper "
                "transcription connected to cover_lyrics (or use 'keep supplied words').")
        if policy != LYRICS_POLICY_AUTO and mode is CoverMode.INSTRUMENTAL:
            raise ValueError(
                "YuE2 Cover Studio: an instrumental cover has no lyrics to keep; "
                "set lyrics_policy back to auto.")
        if policy == LYRICS_POLICY_SUPPLIED and mode is CoverMode.ORIGINAL_LYRICS:
            raise ValueError(
                "YuE2 Cover Studio: 'original lyrics' mode owns the words from the transcription. "
                "Use 'new lyrics' mode with supplied lyrics, or 'keep source words'.")
        system, user = plan_prompt(profile, mode, validation.abc or score, target_style, lyrics)
        if policy != LYRICS_POLICY_AUTO:
            system += ("\n\n# Lyrics are locked\nThe words are fixed by the user and identical to "
                       "the source. You are planning and transforming the music only: do not "
                       "propose, move or rewrite words, and do not change the score in a way that "
                       "assumes different lyrics.")

        state = {
            "schema": STATE_SCHEMA,
            "enabled": True,
            "stage": "planned",
            "advanced_mode": bool(advanced_mode),
            "cover_mode": mode.value,
            "cover_title": source.get("title"),
            "lead_instrument": normalize_lead_instrument(source.get("lead_instrument")),
            "freedom": profile.freedom,
            "profile": profile.as_report(),
            "overrides": overrides.active(),
            "key_change": int(key_change),
            "tempo_change": int(tempo_change),
            "vocal_range": str(vocal_range or VOCAL_RANGES[0]),
            "lyrics_policy": policy,
            "supplied_lyrics": supplied,
            "lyrics_report": str(cover_lyrics or "").strip(),
            "target_style": str(target_style or ""),
            "lyrics": lyrics,
            "source_abc": validation.abc or score,
            "source_abc_sha256": _sha256(validation.abc or score),
            "source_validation": validation.as_report(),
            "plan": None,
            "warnings": warnings,
        }
        return (system, user, _dump(state))


class CoverStudioTransform:
    """Step 2: fold the model's plan into the state and build the transform prompt."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "studio_json": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "plan_text": ("STRING", {"forceInput": True}),
                "enabled": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("system_prompt", "user_prompt", "studio_json")
    FUNCTION = "transform"
    CATEGORY = CATEGORY
    DESCRIPTION = (
        "YuE2 Cover Studio, step 2. Reads the planner's answer, records where it contradicts the "
        "interpretation profile, and builds the transformation prompt. The explicit local ABC "
        "reference is injected automatically; the model must answer with one JSON object."
    )

    def transform(self, studio_json="", plan_text="", enabled=True):
        state = _load(studio_json)
        if state is None or not state.get("enabled"):
            return (_INACTIVE_SYSTEM, _INACTIVE_USER,
                    studio_json if isinstance(studio_json, str) and studio_json.strip()
                    else _dump(_inactive_state("No active Cover Studio state.")))
        if not enabled:
            state = {**state, "enabled": False, "stage": "inactive",
                     "warnings": [*state.get("warnings", []), "Cover Studio is switched off."]}
            return (_INACTIVE_SYSTEM, _INACTIVE_USER, _dump(state))

        plan = parse_plan(plan_text)
        warnings = list(state.get("warnings") or [])
        if str(plan_text or "").strip() and plan is None:
            warnings.append("The planner answer was not a usable JSON plan; the profile alone is used.")
        profile = _profile_from_state(state)
        if plan is not None:
            conflicts = plan_contradictions(plan, profile)
            if conflicts:
                warnings.extend(conflicts)
                # A plan that promises to change a pinned element is not
                # silently averaged away: the contradiction is recorded and the
                # plan is kept only for the elements it does not contradict.
                plan = {**plan, "conflicts": conflicts}

        system, user = transform_prompt(
            profile, _mode_from_state(state), state.get("source_abc", ""),
            state.get("target_style", ""), plan, reference=abc_reference())
        system += ("\n\n# Cover plan\n" + plan_summary(plan))
        vocal_range = str(state.get("vocal_range") or VOCAL_RANGES[0])
        if vocal_range != VOCAL_RANGES[0]:
            system += ("\n\n# Vocal range\nKeep the melody inside " + vocal_range +
                       ". Move a phrase by an octave rather than rewriting its rhythm.")
        state = {**state, "stage": "transformed", "plan": plan, "warnings": warnings}
        return (system, user, _dump(state))


class CoverStudioApply:
    """Step 3: apply the exact knobs, validate the model score, fall back if needed."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "studio_json": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "transform_text": ("STRING", {"forceInput": True}),
                "repair_text": ("STRING", {"forceInput": True}),
                # Safety net: wire the score node here as well, so bypassing or
                # muting the studio nodes degrades to the untouched score
                # instead of breaking the chain with an empty ABC.
                "cover_abc": ("STRING", {"forceInput": True}),
                "enabled": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("cover_abc", "studio_report_json", "warnings", "locked_lyrics")
    FUNCTION = "apply"
    CATEGORY = CATEGORY
    DESCRIPTION = (
        "YuE2 Cover Studio, step 3. Applies tempo, key and melody-only changes exactly, validates the "
        "model's score against the profile and the native ABC structure, and falls back to the "
        "validated deterministic result when the model answer does not hold up. When the studio is "
        "off, the incoming score is returned byte for byte. The locked_lyrics output carries the "
        "verbatim words when the lyrics policy asks for them; connect it to the parser's "
        "cover_lyrics_lock input."
    )

    def apply(self, studio_json="", transform_text="", repair_text="", cover_abc="",
              enabled=True):  # noqa: C901 - one linear pipeline, documented step by step
        state = _load(studio_json)
        if state is None:
            # A bypassed, muted or missing studio must not break the chain: the
            # directly wired score is handed on untouched.
            fallback = str(cover_abc or "")
            reason = ("No Cover Studio state was connected; the score was passed through untouched."
                      if fallback.strip() else
                      "No Cover Studio state and no fallback score were connected.")
            report = {"schema": "cover_studio_report_v1", "enabled": False, "reason": reason}
            return (fallback, _dump(report), "" if fallback.strip() else reason, "")
        if not state.get("enabled") or not enabled:
            # Inactive means byte-for-byte pass-through, never an empty score.
            reason = ("Cover Studio is switched off; the score was not touched." if state.get("enabled")
                      else state.get("reason") or "Cover Studio is inactive; the score was not touched.")
            passthrough = str(state.get("source_abc") or "") or str(cover_abc or "")
            return (passthrough,
                    _dump({"schema": "cover_studio_report_v1", "enabled": False,
                           "reason": reason}),
                    "", "")

        profile = _profile_from_state(state)
        source_abc = str(state.get("source_abc") or "")
        mode = _mode_from_state(state)

        deterministic = apply_deterministic(
            source_abc, profile,
            key_change=int(state.get("key_change") or 0),
            tempo_change=int(state.get("tempo_change") or 0))

        result: TransformResult = deterministic
        if str(transform_text or "").strip():
            result = apply_model_transform(
                deterministic.abc, transform_text, deterministic, profile)
        if result.model_abc_rejected and str(repair_text or "").strip():
            repaired = apply_model_transform(
                deterministic.abc, repair_text, deterministic, profile)
            repaired.warnings = [*result.warnings, "one repair attempt was made", *repaired.warnings]
            result = repaired

        lyrics = _cover_lyrics_text(state.get("lyrics"))
        report = build_result_report(profile, mode, source_abc, result, lyrics)
        fit = report.get("lyrics_fit")
        if isinstance(fit, dict) and fit.get("sections"):
            hint = repair_hint(_fit_from_report(fit))
            if hint:
                report["lyrics_fit_advice"] = hint
        report.update({
            "enabled": True,
            "stage": "applied",
            "cover_title": state.get("cover_title"),
            "lead_instrument": state.get("lead_instrument"),
            "freedom": state.get("freedom"),
            "overrides": state.get("overrides") or {},
            "plan": state.get("plan"),
            "final_abc": result.abc if state.get("advanced_mode") else None,
        })
        locked_lyrics, lock_warnings = build_locked_lyrics(state, result.abc)
        if lock_warnings:
            report["lyrics_lock"] = lock_warnings
        warnings = " | ".join(str(item) for item in [*(result.warnings or []), *lock_warnings])
        return (result.abc, _dump(report), warnings, locked_lyrics)


def build_locked_lyrics(state: Dict, final_abc: str):
    """The verbatim lyrics block the policy asks for, or ``""`` for ``auto``.

    ``keep source words`` reuses the existing lossless placer, so the locked text
    is the same text the original-lyrics mode would have produced - just aligned
    to the *final*, transformed score.  ``keep supplied words`` returns the
    user's text untouched.  Anything else returns an empty string, which leaves
    the downstream behaviour exactly as it was.
    """
    try:
        policy = _normalize_lyrics_policy(state.get("lyrics_policy"))
    except ValueError:
        return "", []
    if policy == LYRICS_POLICY_AUTO:
        return "", []
    if policy == LYRICS_POLICY_SUPPLIED:
        supplied = str(state.get("supplied_lyrics") or "").strip()
        return supplied, ([] if supplied else ["supplied lyrics were empty; nothing was locked"])

    from .cover_alignment import original_lyrics, score_timeline
    transcript = str(state.get("lyrics") or "").strip()
    if not transcript:
        return "", ["no transcription was available; the source words could not be locked"]
    record = None
    raw_report = str(state.get("lyrics_report") or "").strip()
    if raw_report.startswith("{"):
        try:
            candidate = json.loads(raw_report)
        except ValueError:
            candidate = None
        if isinstance(candidate, dict) and candidate.get("schema") == "music_cover_lyrics_v1":
            record = candidate
    try:
        sections = score_timeline(final_abc).get("sections") or []
    except (ValueError, KeyError):
        sections = []
    try:
        locked, alignment = original_lyrics(transcript, record, sections, "")
    except ValueError as exc:
        return "", [f"the source words could not be locked: {exc}"]
    note = [] if alignment.get("word_order_verified") else ["the locked source words were not order-verified"]
    return locked, note


def _fit_from_report(report: Dict):
    """Rebuild the fit object from its serialized report, for the advice helper."""
    from .lyrics_fit import LyricsFit, SectionFit
    sections = [SectionFit(
        index=int(item.get("index", 0)), label=str(item.get("label", "")),
        note_onsets=int(item.get("note_onsets", 0)), phrases=int(item.get("phrases", 0)),
        measures=int(item.get("measures", 0)), rests=int(item.get("rests", 0)),
        lyric_syllables=int(item.get("lyric_syllables", 0)),
        verdict=str(item.get("verdict", "")), advice=str(item.get("advice", "")))
        for item in report.get("sections") or []]
    return LyricsFit(sections, [str(item) for item in report.get("warnings") or []])


def _profile_from_state(state: Dict):
    from .cover_profiles import CoverInterpretationProfile
    data = state.get("profile") or {}
    preserve = data.get("preserve") or {}
    allow = data.get("allow") or {}
    return CoverInterpretationProfile(
        freedom=int(data.get("freedom", state.get("freedom", 0)) or 0),
        band=str(data.get("band") or ""),
        band_label=str(data.get("band_label") or ""),
        preserve_main_melody=float(preserve.get("main_melody", 1.0)),
        preserve_hook=float(preserve.get("chorus_hook", 1.0)),
        preserve_structure=float(preserve.get("structure", 1.0)),
        preserve_harmony=float(preserve.get("harmony", 1.0)),
        preserve_tempo=float(preserve.get("tempo", 1.0)),
        preserve_key=float(preserve.get("key", 1.0)),
        allow_melody_variation=float(allow.get("melody_variation", 0.0)),
        allow_rhythm_variation=float(allow.get("rhythm_variation", 0.0)),
        allow_harmony_change=float(allow.get("harmony_change", 0.0)),
        allow_structure_change=float(allow.get("structure_change", 0.0)),
        melody_only=bool(data.get("melody_only", False)),
        cot_mode=str(data.get("cot_mode") or "melody"),
    )


def _mode_from_state(state: Dict) -> CoverMode:
    try:
        return cover_mode_for(state.get("cover_mode"))
    except ValueError:
        return CoverMode.NEW_LYRICS


NODE_CLASS_MAPPINGS = {
    "YuE2CoverStudioPlan": CoverStudioPlan,
    "YuE2CoverStudioTransform": CoverStudioTransform,
    "YuE2CoverStudioApply": CoverStudioApply,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "YuE2CoverStudioPlan": "YuE2 Cover Studio · 1 plan",
    "YuE2CoverStudioTransform": "YuE2 Cover Studio · 2 transform score",
    "YuE2CoverStudioApply": "YuE2 Cover Studio · 3 validate & apply",
}


__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "CoverStudioApply",
    "CoverStudioPlan",
    "CoverStudioTransform",
    "STATE_SCHEMA",
    "studio_input_tooltips",
]
