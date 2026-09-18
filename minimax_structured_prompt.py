"""Structured Song Prompt node (MiniMaxStructuredPromptV20).

This node is the user-facing prompt control introduced in 2.0.0.  Instead of a
single free-form ``user_prompt`` text field, it exposes structured fields
(Genre, Tempo, Time signature, Key, Lyrics, Language, Voice, Lyrics theme,
Target length) plus a "further description" area.  Prompt library files may *optionally* carry a
metadata block that prefills these fields when the file is selected; the user
can still override every field, and selecting ``custom`` leaves a part out of
the LLM prompt entirely.

The assembled user prompt is a short structured brief followed by the
description text, and is intended to be consumed by the integrated LLM chat
node (or any other LLM node that accepts user/system prompt strings).

The system prompt mirrors the user prompt: selecting a bundled/external system
prompt file copies its text into the editable ``system_prompt`` field, which is
authoritative from then on (so the selection can still be tweaked by hand).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .cover_score import (
    LYRICS_MODE_INSTRUMENTAL,
    LYRICS_MODE_NEW,
    LYRICS_MODE_ORIGINAL,
    parse_cover_score,
    score_syllable_brief,
)
from .model_profiles import SongModelProfile, profile_from_payload
from .prompt_sources import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_SYSTEM_PROMPT_FILE,
    clean_source_name as _clean_source_name,
)
from .prompt_library import (
    PLACEHOLDER,
    PromptLibraryError,
    default_combo_values,
    invalidate_library_options,
    library_options,
    load_prompt_file,
    prompt_selection_fingerprint,
    resolve_prompt,
)
from .prompt_metadata import (
    CUSTOM,
    STRUCTURED_FIELDS,
    assemble_structured_user_prompt,
    parse_prompt_front_matter,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("structured_prompt")

_SOURCES = ["manual", "bundled_library", "external_directory"]

# Default user-prompt file shown by the dropdown (a bundled library entry).
DEFAULT_USER_PROMPT_FILE = "electronic/synth-pop-vocal.txt"

# The aggregated option values are library data; the cache and its invalidation
# live in prompt_library so this node is not a service dependency of the route
# layer.  The historic names stay as delegates.
def invalidate_library_options_cache() -> None:
    """Refresh the aggregated combo options after prompt files changed on disk."""
    invalidate_library_options("user")


def _collect_options() -> dict:
    """Curated vocabulary plus unique values from all bundled user prompt files."""
    return library_options("user")


def _combo(field: str) -> list:
    values = [CUSTOM]
    values += [v for v in _collect_options().get(field, []) if v and v != CUSTOM]
    return values


def _safe_choices(default: list) -> list:
    # Keep the COMBO non-empty even if option discovery failed completely.
    return default or [CUSTOM]


def _resolve_system_prompt(
    system_prompt_source,
    system_prompt_directory,
    system_prompt_file,
    system_prompt,
    profile=None,
):
    """Resolve the effective system prompt text and its origin.

    The ``system_prompt`` field is authoritative in every mode: the frontend
    copies the selected system-prompt file into it on selection (exactly like
    ``description_override`` for the user prompt), so editing the field always
    changes the prompt the LLM receives.  Headless/API runs without the
    frontend prefill fall back to loading the selected file directly, and when
    no file is selected either they fall back to the selected *song model's*
    own default system prompt (``profile``).
    """
    source = (system_prompt_source or "manual").strip().lower()
    # Only bundled, known model templates are translated. Manual and external
    # text stays authoritative; same-family edits are preserved as before.
    if source == "bundled_library" and profile is not None:
        selected = (system_prompt_file or "").strip()
        if selected.startswith("minimax-music3-") and profile.is_yue2:
            selected = "yue2/" + selected.removeprefix("minimax-music3-")
        elif selected.startswith("yue2/") and not profile.is_yue2:
            selected = "minimax-music3-" + selected.removeprefix("yue2/")
        if selected != (system_prompt_file or "").strip():
            return load_prompt_file("system", source, "", selected)
    if source == "manual":
        text = (system_prompt or "").strip()
        if not text:
            raise ValueError("Structured Song Prompt: manual system prompt is empty.")
        return text, "<manual>"

    text = (system_prompt or "").strip()
    if text:
        origin = (system_prompt_file or "").strip() or PLACEHOLDER
        return text, origin

    selected = (system_prompt_file or "").strip()
    if profile is not None and profile.system_prompt_file and (not selected or selected == PLACEHOLDER):
        # Nothing was prefilled and no file was chosen: use the model's own
        # default prompt instead of failing on an empty selection.
        try:
            return load_prompt_file("system", source, system_prompt_directory, profile.system_prompt_file)
        except Exception as exc:
            LOGGER.warning(
                "Could not load the %s default system prompt '%s' (%s); falling back to the node selection.",
                profile.display_name, profile.system_prompt_file, exc,
            )
    return resolve_prompt("system", source, system_prompt_directory, selected)


class MiniMaxStructuredPromptV20:
    """Structured prompt control: metadata-prefilled fields assembled into one LLM user prompt."""

    @classmethod
    def INPUT_TYPES(cls):
        # "custom" as the first real choice of the prompt-file dropdown selects
        # the free mode: no prompt file is loaded and nothing is prefilled, so
        # the user composes every field themselves.  It must stay distinct from
        # the per-field "custom" sentinel (which omits a single field).
        user_file_options = [CUSTOM, *default_combo_values("user")]
        return {
            "required": {
                "user_prompt_source": (_SOURCES, {"default": "bundled_library"}),
                "user_prompt_directory": ("STRING", {"default": "", "multiline": False}),
                "user_prompt_file": (user_file_options, {"default": DEFAULT_USER_PROMPT_FILE}),
                "genre": (_safe_choices(_combo("genre")), {"default": CUSTOM}),
                "tempo": (_safe_choices(_combo("tempo")), {"default": CUSTOM}),
                "meter": (_safe_choices(_combo("meter")), {"default": CUSTOM}),
                "key": (_safe_choices(_combo("key")), {"default": CUSTOM}),
                "lyrics": (_safe_choices(_combo("lyrics")), {"default": CUSTOM}),
                "language": (_safe_choices(_combo("language")), {"default": CUSTOM}),
                "voice": (_safe_choices(_combo("voice")), {"default": CUSTOM}),
                "theme": (_safe_choices(_combo("theme")), {"default": CUSTOM}),
                "length": (_safe_choices(_combo("length")), {"default": CUSTOM}),
                "description_override": ("STRING", {"default": "", "multiline": True}),
                "system_prompt_source": (_SOURCES, {"default": "bundled_library"}),
                "system_prompt_directory": ("STRING", {"default": "", "multiline": False}),
                "system_prompt_file": (default_combo_values("system"), {"default": DEFAULT_SYSTEM_PROMPT_FILE}),
                "source_name_override": ("STRING", {"default": "", "multiline": False}),
                "system_prompt": ("STRING", {"default": DEFAULT_SYSTEM_PROMPT, "multiline": True}),
            },
            "optional": {
                # Appended optional input (2.6.0): the selected song model. The
                # profile decides which system-prompt family this node expects
                # and is recorded in the summary, so a prompt written for the
                # other model is visible instead of silent.
                "model_profile_json": ("STRING", {"forceInput": True, "multiline": True}),
                "cover_source_json": ("STRING", {"forceInput": True}),
                "cover_abc": ("STRING", {"forceInput": True}),
                # 3.1.0: the Whisper transcription of the original words, used
                # when the cover lyrics mode asks for them.  Appended input, so
                # a saved workflow keeps its existing slot order.
                "cover_lyrics": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("system_prompt", "user_prompt", "source_name", "structured_summary_json")
    FUNCTION = "build"
    CATEGORY = "Music Production Toolkit/prompts"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        # Prompt file choices and structured combos can be populated dynamically,
        # so static COMBO membership checks must not reject runtime selections.
        return True

    @classmethod
    def IS_CHANGED(
        cls,
        user_prompt_source,
        user_prompt_directory,
        user_prompt_file,
        genre,
        tempo,
        meter,
        key,
        lyrics,
        language,
        voice,
        theme,
        length,
        description_override,
        system_prompt_source,
        system_prompt_directory,
        system_prompt_file,
        source_name_override="",
        system_prompt="",
        model_profile_json="",
        **kwargs,
    ):
        # "custom" selects free mode (no file is loaded); fingerprint it as such
        # instead of attempting to resolve a file literally named "custom".
        if (user_prompt_file or "").strip() == CUSTOM:
            user_fp = f"user:{CUSTOM}"
        else:
            user_fp = prompt_selection_fingerprint(
                "user", user_prompt_source, user_prompt_directory, user_prompt_file, description_override
            )
        # description_override is authoritative in file mode too, so editing it
        # must invalidate the cache even though the file fingerprint is unchanged.
        description_fp = hashlib.sha256((description_override or "").encode("utf-8", errors="replace")).hexdigest()[:16]
        user_fp = f"{user_fp}|desc={description_fp}"
        system_fp = prompt_selection_fingerprint(
            "system", system_prompt_source, system_prompt_directory, system_prompt_file, system_prompt
        )
        # The system_prompt field is authoritative in every mode, so its text is
        # part of the fingerprint even when a file is selected.
        system_text_fp = hashlib.sha256((system_prompt or "").encode("utf-8", errors="replace")).hexdigest()[:16]
        system_fp = f"{system_fp}|text={system_text_fp}"
        field_state = "|".join(
            f"{f}={v}" for f, v in (
                ("genre", genre), ("tempo", tempo), ("meter", meter), ("key", key),
                ("lyrics", lyrics), ("language", language), ("voice", voice),
                ("theme", theme), ("length", length),
            )
        )
        profile_fp = hashlib.sha256((model_profile_json or "").encode("utf-8", errors="replace")).hexdigest()[:16]
        cover_fp = hashlib.sha256(json.dumps([
            kwargs.get("cover_source_json", ""), kwargs.get("cover_abc", ""),
            kwargs.get("cover_lyrics", ""),
        ]).encode()).hexdigest()
        return f"{user_fp}|{system_fp}|{field_state}|source={source_name_override or ''}|model={profile_fp}|cover={cover_fp}"

    def build(
        self,
        user_prompt_source,
        user_prompt_directory,
        user_prompt_file,
        genre,
        tempo,
        meter,
        key,
        lyrics,
        language,
        voice,
        theme,
        length,
        description_override,
        system_prompt_source,
        system_prompt_directory,
        system_prompt_file,
        source_name_override="",
        system_prompt="",
        model_profile_json="",
        cover_source_json="",
        cover_abc="",
        cover_lyrics="",
    ):
        profile: SongModelProfile | None = profile_from_payload(model_profile_json)
        resolved_system, system_origin = _resolve_system_prompt(
            system_prompt_source, system_prompt_directory, system_prompt_file, system_prompt, profile
        )
        model_prompt_mismatch = False
        if profile is not None:
            family = profile.family_of_file(system_origin)
            if family is not None and family != ("yue2" if profile.is_yue2 else profile.id):
                model_prompt_mismatch = True
                LOGGER.warning(
                    "Structured Song Prompt: the selected system prompt '%s' belongs to a different song model "
                    "than '%s'. The prompt is used as selected - switch the system-prompt file if the model "
                    "should write its own prompt format.",
                    system_origin, profile.display_name,
                )

        widget_values = {
            "genre": genre, "tempo": tempo, "meter": meter, "key": key,
            "lyrics": lyrics, "language": language, "voice": voice,
            "theme": theme, "length": length,
        }

        # The cover branch is resolved first: its lyrics mode decides which words
        # the LLM may write, and that decision must reach the assembled user
        # prompt instead of being appended after it.
        cover = None
        cover_lyrics_record = None
        forced_lyrics = ""
        # Fields the cover lyrics mode removed from the brief; reported so it is
        # visible which instruction won.
        cover_mode_removed: list = []
        if profile is not None and profile.is_cover:
            from .music_cover import cover_record

            cover = cover_record(cover_source_json)
            if not isinstance(cover_abc, str) or not cover_abc.strip():
                raise ValueError("YuE2 Cover requires non-empty SheetSage2 ABC transcription.")
            # The mode, not a leftover field value from another song, owns this.
            # 'new lyrics' additionally refuses a wordless value: a cover that
            # must have new words cannot be asked to sing none.
            forced_lyrics = {
                LYRICS_MODE_INSTRUMENTAL: "instrumental",
                LYRICS_MODE_ORIGINAL: "yes",
            }.get(cover["lyrics_mode"], "")
            current_lyrics = str(widget_values["lyrics"] or "").strip()
            if not forced_lyrics and cover["lyrics_mode"] == LYRICS_MODE_NEW \
                    and current_lyrics.casefold() not in {"yes", "sparse"}:
                forced_lyrics = "yes"
            if forced_lyrics and current_lyrics != forced_lyrics:
                LOGGER.info(
                    "Structured Song Prompt: cover lyrics mode '%s' sets the Lyrics field to '%s' "
                    "(was '%s').", cover["lyrics_mode"], forced_lyrics, current_lyrics,
                )
                widget_values["lyrics"] = forced_lyrics

        raw_cover_lyrics = str(cover_lyrics or "").strip()
        if cover is not None and raw_cover_lyrics:
            try:
                parsed_lyrics_record = json.loads(raw_cover_lyrics)
            except ValueError:
                parsed_lyrics_record = None
            if isinstance(parsed_lyrics_record, dict) and parsed_lyrics_record.get("schema") == "music_cover_lyrics_v1":
                cover_lyrics_record = parsed_lyrics_record
                raw_cover_lyrics = str(parsed_lyrics_record.get("text") or "").strip()
        if cover is not None and cover['lyrics_mode'] == LYRICS_MODE_INSTRUMENTAL:
            raw_cover_lyrics, cover_lyrics_record = '', None
        if cover is not None and cover['lyrics_mode'] == LYRICS_MODE_ORIGINAL and not raw_cover_lyrics:
            raise ValueError('YuE2 Cover: original lyrics require a non-empty Whisper transcription. '
                             'Connect the Whisper lyrics report to cover_lyrics or supply a reviewed transcript.')

        source = (user_prompt_source or "manual").strip().lower()
        # Free mode: the prompt-file dropdown is set to "custom", which means no
        # file is loaded and no fields are touched - the user fills them freely.
        if source != "manual" and (user_prompt_file or "").strip() == CUSTOM:
            source = "manual"
        if source == "manual":
            file_fields = {}
            description = (description_override or "").strip()
            user_origin = "<manual>"
        else:
            try:
                text, user_origin = resolve_prompt(
                    "user", user_prompt_source, user_prompt_directory, user_prompt_file
                )
            except (PromptLibraryError, ValueError) as exc:
                raise ValueError(f"Structured Song Prompt: {exc}") from exc
            file_fields, _file_description = parse_prompt_front_matter(text)
            # description_override is the single source of truth for the
            # description once a prompt file is selected: the frontend copies
            # the file's body text into the field on selection, and only that
            # field content is used from then on.  Clearing the field removes
            # the description; the file body is never used as a silent fallback.
            description = (description_override or "").strip()

        # Precedence: explicit widget choice > file metadata > omit.  An
        # explicit "custom" means the user wants NO specification for this
        # field - it must not fall back to the file's metadata value.
        resolved = {}
        overrides = {}
        for field in STRUCTURED_FIELDS:
            widget_value = widget_values.get(field)
            widget_value = str(widget_value or "").strip()
            if widget_value == CUSTOM:
                continue
            if widget_value:
                resolved[field] = widget_value
                overrides[field] = widget_value
            elif file_fields.get(field):
                # Only reachable when the widget carries no value at all
                # (headless/API runs without the frontend prefill).
                resolved[field] = file_fields[field]

        if cover is not None:
            # The cover lyrics mode owns the vocal fields. Whatever the selected
            # template, the prompt file's front matter or a previous song left in
            # them must not reach the LLM as a competing instruction, so the mode
            # removes them here and the summary records what it removed.
            mode_removed: list = []
            if cover['lyrics_mode'] == LYRICS_MODE_INSTRUMENTAL:
                resolved['lyrics'] = 'instrumental'
                for field in ('voice', 'language', 'theme'):
                    if resolved.pop(field, None) is not None:
                        mode_removed.append(field)
            else:
                if resolved.get('lyrics', '').casefold() not in {'yes', 'sparse'}:
                    resolved['lyrics'] = 'yes'
                if cover['lyrics_mode'] == LYRICS_MODE_ORIGINAL:
                    # The words are the transcription. A lyrics theme would ask the
                    # model to write words that are not in the source, so it goes.
                    if resolved.pop('theme', None) is not None:
                        mode_removed.append('theme')
            cover_mode_removed = mode_removed
            if cover['lyrics_mode'] == LYRICS_MODE_ORIGINAL and (cover_lyrics_record or {}).get('language'):
                # Original English lyrics must not be described as German merely
                # because the selected new-song template requests German.
                from .whisper_lyrics import _LANGUAGE_NAMES
                code = cover_lyrics_record['language']
                # Whisper's own names are lowercase for the engine; the brief uses
                # the same capitalised form as the curated language field.
                name = _LANGUAGE_NAMES.get(code, code)
                resolved['language'] = name[:1].upper() + name[1:]
            if mode_removed:
                LOGGER.info(
                    "Structured Song Prompt: cover lyrics mode '%s' removed %s from the brief "
                    "(the mode, not the template, decides the vocals).",
                    cover['lyrics_mode'], ", ".join(mode_removed),
                )
        if not resolved and not description:
            raise ValueError(
                "Structured Song Prompt: every field is 'custom' and no description is available. "
                "Select a prompt file, set at least one field, or write a description."
            )

        user_prompt = assemble_structured_user_prompt(resolved, description)
        if profile is not None and profile.is_yue2:
            from .song_duration import duration_request, duration_brief
            length_request = duration_request(resolved.get("length"))
            if length_request:
                user_prompt += "\n\n" + duration_brief(length_request)
        if profile is not None and profile.is_yue2 and resolved.get("lyrics", "").casefold() in {"instrumental", "no", "nein", "none"}:
            user_prompt += (
                "\n\nINSTRUMENTAL CONSTRAINT: Lyrics mode is instrumental and overrides any "
                "inherited vocal/language fields or vocal template suggestions above. "
                "Style must explicitly say instrumental, no sung or spoken words, no lead or "
                "backing vocals, no choir. Describe the full chronological arrangement in Style, "
                "including motif development, contrasting passages, instrument entrances/exits "
                "and transitions. Lyrics must contain only the matching instrumental section "
                "tags in exactly the same order and number of occurrences, with no words, "
                "syllables, scat or vocalizations. Do not shorten the structure because it has "
                "no sung text. Only if explicitly requested, allow quiet closed-mouth humming "
                "as the sole background voice in Style; never transcribe it in Lyrics."
            )

        if (source_name_override or "").strip():
            source_name = _clean_source_name(source_name_override)
        elif user_origin not in {"<manual>", PLACEHOLDER}:
            source_name = _clean_source_name(Path(user_origin).stem)
        else:
            source_name = ""

        cover_syllable_map = None
        cover_timing = None
        cover_abc_effective = cover_abc
        if profile is not None and profile.is_cover:
            from .cover_score import adapt_cover_score
            from .music_cover import cover_prompt_instructions

            # The LLM must plan against the score the generator will really
            # receive.  Applying the same (idempotent) rewrite here keeps that
            # true even in a workflow that has no separate score node.
            cover_abc_effective = adapt_cover_score(
                cover_abc, cover["lyrics_mode"], cover["lead_instrument"])["abc"]
            if cover['mode'] == 'melody':
                from .third_party.yue2_abc import strip_chords
                cover_abc_effective = strip_chords(cover_abc_effective)
            resolved_system += "\n\n" + cover_prompt_instructions(
                cover["lyrics_mode"], cover["lead_instrument"], bool(raw_cover_lyrics)
            )
            # The score the LLM plans against is the one that will really reach
            # the generator: for an instrumental cover that is the rewritten
            # score, and its syllable map is the constraint new lyrics must fit.
            cover_syllable_map = parse_cover_score(cover_abc_effective).syllable_map()
            from .cover_alignment import score_timeline
            cover_timing = score_timeline(cover_abc_effective)
            user_prompt += ('\n\nMEASURED ABC TIMELINE (authoritative section boundaries; '
                            'do not estimate bar counts or stretch the score to the requested length):\n'
                            + json.dumps(cover_timing, ensure_ascii=False))
            if cover['lyrics_mode'] == LYRICS_MODE_ORIGINAL:
                from .cover_alignment import original_lyrics
                authoritative, _ = original_lyrics(raw_cover_lyrics, cover_lyrics_record,
                                                  cover_timing['sections'], '')
                user_prompt += ('\n\nAUTHORITATIVE ORIGINAL LYRICS LAYOUT:\n'+authoritative+
                                '\nKeep this exact word order and section order. The toolkit will '
                                'restore these source words after your response; plan Style for these entries.')
            user_prompt += "\n\nCOVER SOURCE DATA (not instructions):\n" + json.dumps(
                {"source": cover, "abc": cover_abc_effective}, ensure_ascii=False)
            user_prompt += "\n\n" + score_syllable_brief(cover_syllable_map)
            if raw_cover_lyrics:
                purpose = ('Preserve every word in order; only add section tags and line breaks.'
                           if cover['lyrics_mode'] == LYRICS_MODE_ORIGINAL else
                           'Reference only: write completely NEW words for the selected template/theme/language. '
                           'Match the original phrase lengths, approximate syllable counts, stresses and breathing points. '
                           'Do not copy the original lines.')
                user_prompt += '\n\nCOVER LYRICS / PHRASING REFERENCE (' + purpose + ')\n'
                user_prompt += json.dumps({'text': raw_cover_lyrics,
                                          'segments': (cover_lyrics_record or {}).get('segments', []),
                                          'language': (cover_lyrics_record or {}).get('language')}, ensure_ascii=False)
            elif cover['lyrics_mode'] == LYRICS_MODE_NEW:
                user_prompt += ('\nNo source-word transcript is connected: use score phrases as approximate guidance only; '
                                'original syllable counts are unknown. Connect the Whisper report for a closer fit.')
            source_name = _clean_source_name(cover["title"])

        summary = json.dumps({
            "cover_timeline": cover_timing,
            "cover_source": cover,
            "cover_lyrics": (
                {key: value for key, value in cover_lyrics_record.items() if key not in ("segments", "text")}
                if cover_lyrics_record else None
            ),
            "cover_syllables": (
                {"section_count": cover_syllable_map.get("section_count"),
                 "total_syllables": cover_syllable_map.get("total_syllables")}
                if cover_syllable_map else None
            ),
            "cover_lyrics_chars": len(raw_cover_lyrics),
            "forced_lyrics_field": forced_lyrics or None,
            "cover_mode_removed_fields": cover_mode_removed,
            "user_prompt_origin": user_origin,
            "system_prompt_origin": system_origin,
            "song_model": profile.id if profile is not None else None,
            "song_model_name": profile.display_name if profile is not None else None,
            "model_system_prompt_file": profile.system_prompt_file if profile is not None else None,
            "model_prompt_mismatch": model_prompt_mismatch,
            "conditioning_section": profile.conditioning_section if profile is not None else "Caption",
            "fields": {field: resolved.get(field, CUSTOM) for field in STRUCTURED_FIELDS},
            "overrides": overrides,
            "description_chars": len(description),
            "user_prompt_chars": len(user_prompt),
        }, ensure_ascii=False)

        LOGGER.info(
            "Structured prompt resolved: user=%s, system=%s, model=%s, fields=%d, user_prompt_chars=%d",
            user_origin, system_origin, profile.id if profile is not None else "<none>",
            len(resolved), len(user_prompt),
        )
        return (resolved_system, user_prompt, source_name, summary)


NODE_CLASS_MAPPINGS = {
    "MiniMaxStructuredPromptV20": MiniMaxStructuredPromptV20,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxStructuredPromptV20": "Structured Song Prompt (Genre / Tempo / Time signature / Lyrics ...)",
}
