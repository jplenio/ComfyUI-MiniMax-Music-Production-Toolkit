from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cover_score import LYRICS_MODE_ORIGINAL, normalize_lyrics_mode
from .model_profiles import profile_from_payload
from .prompt_library import (PLACEHOLDER, PromptLibraryError, default_combo_values, load_prompt_file, prompt_selection_fingerprint)
from .prompt_sources import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_SYSTEM_PROMPT_FILE,
    DEFAULT_USER_PROMPT,
    clean_source_name as _clean_source_name_impl,
    iter_prompt_files,
    iter_variants,
    load_bundled_default_system_prompt as _load_bundled_default_system_prompt,
    new_seed as _new_seed_impl,
    normalize_extensions,
    read_prompt_text as _read_text_impl,
    resolve_prompt_directory as _resolve_prompt_directory_impl,
)
from .prompt_budget import (
    DEFAULT_PROMPT_TOKEN_BUDGET,
    MINIMAX_MAX_PROMPT_TOKENS,
    estimate_prompt_tokens,
    token_counter,
    trim_prompt_to_budget,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("prompts")

# Top-level sections the parser understands.  ``Style``/``Styles``/``Tags``/
# ``Genre`` are the YuE2 names for the primary conditioning text; they are
# parsed into the same ``caption`` field, because that field *is* "the text
# that conditions the music model" - MiniMax calls it a caption, YuE2 calls it
# a style line.
_CONDITIONING_LABELS = r"Caption|Style|Styles|Tags|Genre"
_SECTION_LABELS = rf"Title|{_CONDITIONING_LABELS}|Lyrics|Count|Song[-_ ]?Count|Image[-_ ]?Prompt"
_SECTION_RE = re.compile(rf"^\s*\[({_SECTION_LABELS})\]\s*$", re.IGNORECASE)

# The default prompt constants, their loader and the small source helpers live in
# prompt_sources so the structured-prompt node no longer has to import them from
# this module.  The names stay re-exported here for compatibility.
__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_SYSTEM_PROMPT_FILE",
    "DEFAULT_USER_PROMPT",
    "_load_bundled_default_system_prompt",
]


def _clean_source_name(value: str) -> str:
    """Compatibility wrapper around :func:`prompt_sources.clean_source_name`."""
    return _clean_source_name_impl(value)


def _new_seed() -> int:
    """Compatibility wrapper around :func:`prompt_sources.new_seed`."""
    return _new_seed_impl()


def _resolve_prompt_directory(value: str) -> Path:
    """Compatibility wrapper around :func:`prompt_sources.resolve_prompt_directory`."""
    return _resolve_prompt_directory_impl(value, error_prefix="MiniMax Prompt Source")


def _read_text(path: Path) -> str:
    """Compatibility wrapper around :func:`prompt_sources.read_prompt_text`."""
    return _read_text_impl(path)

NO_TEXT_PROHIBITION = (
    "No text, no letters, no words, no numbers, no digits, no symbols, no typography, no logo, "
    "no watermark, no signature, no captions, no labels, no signage, no written characters."
)


def ensure_no_text_prohibition(image_prompt: str) -> tuple:
    """Guarantee the FLUX image prompt ends with the text-free prohibition.

    Returns ``(text, appended)``.  The bundled system prompt asks the LLM to
    end the Image_Prompt with this exact sentence; this helper is the parser
    safety net for models that omit or mangle it (otherwise FLUX happily
    renders words and lettering onto the cover).
    """
    text = (image_prompt or "").strip()
    if not text:
        return text, False
    if re.search(r"no\s+text\s*,\s*no\s+letters", text, re.IGNORECASE):
        return text, False
    return text.rstrip() + "\n\n" + NO_TEXT_PROHIBITION, True


def _fallback_image_prompt(title: str, caption: str, lyrics: str = "") -> str:
    caption_one_line = " ".join((caption or "").split())
    if len(caption_one_line) > 900:
        caption_one_line = caption_one_line[:897].rstrip() + "..."
    return (
        "Square album cover artwork, visually striking and atmospheric, matching this music concept: "
        + caption_one_line
        + " Create a polished cover with a strong focal point, expressive lighting, rich depth, cohesive composition and no dependence on text-bearing objects. "
        + NO_TEXT_PROHIBITION
    ).strip()


def _clean_section_content(text: str, *, drop_ellipsis: bool = True) -> str:
    """Remove thinking artifacts from parsed section content.

    LLMs prepend things like ``...``, ``\n\n`` or ``---`` to sections (the
    Title especially).  Leading/trailing blank lines and ellipsis-only lines
    are dropped so filenames/tags never carry stray punctuation or underscores.
    """
    lines = [line.rstrip() for line in (text or "").splitlines()]
    noise = {"", "...", "\u2026", "---", "***", "---", "\u2500\u2500\u2500"}
    while lines and (not lines[0].strip() or (drop_ellipsis and lines[0].strip() in noise)):
        lines.pop(0)
    while lines and (not lines[-1].strip() or (drop_ellipsis and lines[-1].strip() in noise)):
        lines.pop()
    return "\n".join(lines).strip()


def _parse_sections(text: str, required_section: str = "Caption") -> Dict[str, Any]:
    """Parse structured LLM output robustly.

    Accepted examples for top-level headers include:
      [Title]
      **[Title]**
      ### [Title]
      Title:
      ## Caption
      Image_Prompt:
      [Style]
      [Tags]

    ``required_section`` only names the model's own label in the error message
    (MiniMax Music 3 asks for ``[Caption]``, YuE2 for ``[Style]``); the accepted
    vocabulary is the same for both.

    MiniMax section tags inside Lyrics such as [Intro] / [Instrumental] are
    deliberately NOT treated as top-level sections.
    """
    raw = "" if text is None else str(text)
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")

    # Remove common thinking blocks. They are not part of the structured answer
    # and can themselves contain misleading words such as Title/Caption.
    normalized = re.sub(r"<think>.*?</think>", "", normalized, flags=re.IGNORECASE | re.DOTALL)

    sections: Dict[str, List[str]] = {
        "title": [], "caption": [], "lyrics": [], "count": [], "image_prompt": []
    }
    current: Optional[str] = None
    detected: List[str] = []

    # Flexible top-level heading syntax, but still limited to our known section
    # names so [Intro], [Verse], [Instrumental] etc. remain Lyrics content.
    header_re = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?\s*"
        rf"(?:\[\s*)?({_SECTION_LABELS})"
        r"(?:\s*\])?\s*(?:\*\*|__)?\s*:?[ \t]*$",
        re.IGNORECASE,
    )
    inline_re = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?\s*"
        rf"(?:\[\s*)?({_SECTION_LABELS})"
        r"(?:\s*\])?\s*(?:\*\*|__)?\s*:\s*(.+?)\s*$",
        re.IGNORECASE,
    )

    # The model's own names for its primary conditioning text all land in
    # ``caption`` so the rest of the graph stays model-agnostic.
    conditioning_aliases = {"style", "styles", "tags", "genre"}

    def key_for(label: str) -> str:
        key = label.lower().replace("-", "_").replace(" ", "_")
        if key in {"song_count", "song__count"}:
            return "count"
        if key in {"imageprompt", "image__prompt"}:
            return "image_prompt"
        if key in conditioning_aliases:
            return "caption"
        return key

    for line in normalized.split("\n"):
        # Ignore pure Markdown code-fence lines.
        if line.strip().startswith("```"):
            continue

        m_inline = inline_re.match(line)
        if m_inline:
            key = key_for(m_inline.group(1))
            current = key
            detected.append(key)
            # A repeated top-level header restarts its section: LLMs sometimes
            # leak planning/self-check text behind an early header and then
            # write the real section again at the end.  The last occurrence is
            # the answer; earlier drafts must not pollute the parsed fields.
            sections[key] = [m_inline.group(2).strip()]
            continue

        m = header_re.match(line)
        if m:
            key = key_for(m.group(1))
            current = key
            detected.append(key)
            sections[key] = []
            continue

        if current is not None:
            sections[current].append(line)

    title = _clean_section_content("\n".join(sections["title"]).strip())
    caption = _clean_section_content("\n".join(sections["caption"]).strip())
    lyrics = _clean_section_content("\n".join(sections["lyrics"]).strip(), drop_ellipsis=False)
    image_prompt = _clean_section_content("\n".join(sections["image_prompt"]).strip())
    count_text = "\n".join(sections["count"]).strip()

    missing = []
    if not caption:
        missing.append(required_section)
    if not lyrics:
        missing.append("Lyrics")
    if missing:
        preview = normalized.strip()
        if len(preview) > 1800:
            preview = preview[:1800] + "\n... [truncated]"
        unique_detected = []
        for item in detected:
            if item not in unique_detected:
                unique_detected.append(item)
        sections_hint = f"[{required_section}], [Lyrics], [Title], and [Image_Prompt]"
        if required_section != "Caption":
            sections_hint += " ([Caption]/[Tags] are accepted as well)"
        raise ValueError(
            "Could not parse required LLM sections. "
            f"Missing/non-empty: {', '.join(missing)}. "
            f"Detected top-level sections: {unique_detected or ['none']}.\n\n"
            f"The external LLM should return {sections_hint} in that order.\n\n"
            "Beginning of received assistant_text:\n"
            + preview
        )

    count_override = None
    if count_text:
        # LLMs occasionally decorate the value (e.g. "Count: 1 +8? Let's
        # number:").  Extract the first standalone integer instead of failing
        # the whole run on prose; a section without any number is ignored.
        integer_match = re.search(r"(?<!\d)\d{1,3}(?!\d)", count_text)
        if integer_match:
            count_override = int(integer_match.group(0))
            if count_override < 1 or count_override > 100:
                clamped = max(1, min(100, count_override))
                LOGGER.warning(
                    "LLM [Count] value %d is outside 1-100; clamped to %d.",
                    count_override, clamped,
                )
                count_override = clamped
        else:
            LOGGER.warning(
                "LLM [Count] section contained no usable integer; ignoring: %r",
                count_text[:200],
            )

    return {
        "title": title,
        "caption": caption,
        "lyrics": lyrics,
        "image_prompt": image_prompt,
        "count_override": count_override,
    }


_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _cover_lyrics_payload(value: str):
    """Split the cover-lyrics input into its record and its plain text.

    The node's output is normally the Whisper record; a plain text string is
    also accepted so a hand-written or externally produced transcript can be
    connected without inventing a record for it.
    """
    raw = (value or "").strip()
    if not raw:
        return None, ""
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("schema") == "music_cover_lyrics_v1":
            return data, str(data.get("text") or "").strip()
    return None, raw


def _lyrics_word_coverage(transcript, lyrics):
    """Share of the transcribed words that survive into the final lyrics.

    A soft, informative check - wording and casing may legitimately differ - so
    it is reported as a ratio instead of failing a run.  ``None`` when there is
    nothing to compare, and words shorter than four characters are ignored so
    articles and filler cannot flatter the number.
    """
    source_words = {word.casefold() for word in _WORD_RE.findall(str(transcript or ""))}
    source_words = {word for word in source_words if len(word) >= 4}
    if not source_words:
        return None
    final_words = {word.casefold() for word in _WORD_RE.findall(str(lyrics or ""))}
    return round(len(source_words & final_words) / len(source_words), 4)


def _parse_prompt_text(text: str, source_name: str, source_path: str) -> Dict[str, Any]:
    parsed = _parse_sections(text)
    final_title = parsed["title"] or Path(source_name).stem or "song"
    image_prompt, prohibition_appended = ensure_no_text_prohibition(
        parsed["image_prompt"] or _fallback_image_prompt(final_title, parsed["caption"], parsed["lyrics"])
    )
    if prohibition_appended:
        LOGGER.info("Appended the text-free prohibition to the image prompt from '%s'.", source_name)
    return {
        "title": final_title,
        "caption": parsed["caption"],
        "lyrics": parsed["lyrics"],
        "image_prompt": image_prompt,
        "count_override": parsed["count_override"],
        "source_name": _clean_source_name(Path(source_name).stem),
        "source_path": source_path,
    }


class MiniMaxPromptSourceArtworkV16:
    """Folder/manual prompt source. It never calls any LLM."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_mode": (["folder", "manual"], {"default": "manual"}),
                "song_count": ("INT", {"default": 1, "min": 1, "max": 100, "step": 1}),
                "seed_mode": (["random_each_song", "increment_from_base"], {"default": "random_each_song"}),
                "base_seed": ("INT", {"default": 1, "min": 0, "max": 9223372036854775806, "step": 1}),
                "prompt_directory": ("STRING", {"default": "", "multiline": False}),
                "extensions": ("STRING", {"default": ".txt,.prompt,.md", "multiline": False}),
                "recursive": ("BOOLEAN", {"default": False}),
                "manual_title": ("STRING", {"default": "manual-song", "multiline": False}),
                "manual_caption": ("STRING", {"default": "", "multiline": True}),
                "manual_lyrics": ("STRING", {"default": "", "multiline": True}),
                "manual_image_prompt": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "INT", "INT", "INT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("caption", "lyrics", "title", "image_prompt", "source_name", "generation_seed", "run_index", "variant_count", "source_path", "prompt_origin", "prompt_provenance_json")
    OUTPUT_IS_LIST = (True, True, True, True, True, True, True, True, True, True, True)
    FUNCTION = "load"
    CATEGORY = "MiniMax Music Production Toolkit/batch"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def load(self, source_mode, song_count, seed_mode, base_seed, prompt_directory, extensions, recursive,
             manual_title, manual_caption, manual_lyrics, manual_image_prompt):
        entries: List[Dict[str, Any]] = []
        if source_mode == "folder":
            directory = _resolve_prompt_directory(prompt_directory)
            if not directory.exists() or not directory.is_dir():
                raise ValueError(f"MiniMax Prompt Source: invalid prompt directory: {directory}")
            allowed = normalize_extensions(extensions)
            files = iter_prompt_files(directory, allowed, recursive, relative_sort=False)
            if not files:
                raise ValueError(f"MiniMax Prompt Source: no prompt files found in {directory}")
            errors = []
            for p in files:
                try:
                    e = _parse_prompt_text(_read_text(p), p.name, str(p))
                    e["prompt_origin"] = "folder"
                    e["provenance"] = {"source_mode": "folder", "source_path": str(p)}
                    entries.append(e)
                except Exception as exc:
                    errors.append(f"{p.name}: {exc}")
            if errors:
                raise ValueError("MiniMax Prompt Source: invalid prompt file(s):\n- " + "\n- ".join(errors))
        else:
            caption = (manual_caption or "").strip()
            lyrics = (manual_lyrics or "").strip()
            if not caption or not lyrics:
                raise ValueError("MiniMax Prompt Source: manual_caption and manual_lyrics must be non-empty.")
            title = (manual_title or "manual-song").strip() or "manual-song"
            image_prompt, prohibition_appended = ensure_no_text_prohibition(
                (manual_image_prompt or "").strip() or _fallback_image_prompt(title, caption, lyrics)
            )
            if prohibition_appended:
                LOGGER.info("Appended the text-free prohibition to the manual image prompt.")
            entries.append({
                "title": title,
                "caption": caption,
                "lyrics": lyrics,
                "image_prompt": image_prompt,
                "count_override": None,
                "source_name": _clean_source_name(title),
                "source_path": "<manual>",
                "prompt_origin": "manual",
                "provenance": {"source_mode": "manual"},
            })

        out = {k: [] for k in ["caption", "lyrics", "title", "image_prompt", "source_name", "generation_seed", "run_index", "variant_count", "source_path", "prompt_origin", "prompt_provenance_json"]}
        for entry, variant, count, seed, _global_index in iter_variants(
            entries,
            song_count=song_count,
            seed_mode=seed_mode,
            base_seed=base_seed,
            # Tolerant count: a falsy [Count] override falls back to song_count.
            count_of=lambda e: e.get("count_override") or int(song_count),
        ):
            out["caption"].append(entry["caption"])
            out["lyrics"].append(entry["lyrics"])
            out["title"].append(entry["title"])
            out["image_prompt"].append(entry["image_prompt"])
            out["source_name"].append(_clean_source_name(entry["source_name"]))
            out["generation_seed"].append(seed)
            out["run_index"].append(variant)
            out["variant_count"].append(count)
            out["source_path"].append(entry["source_path"])
            out["prompt_origin"].append(entry["prompt_origin"])
            out["prompt_provenance_json"].append(json.dumps(entry["provenance"], ensure_ascii=False))
        return tuple(out[k] for k in ["caption", "lyrics", "title", "image_prompt", "source_name", "generation_seed", "run_index", "variant_count", "source_path", "prompt_origin", "prompt_provenance_json"])


class MiniMaxLLMTemplateV16:
    """Resolve manual or file-based system/user prompts for an external ComfyUI LLM.

    The legacy class name is intentionally kept so existing workflows continue to
    load.  The public display name is "LLM Prompt Library / Template".
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # Keep these first three fields in their historical order for backwards compatibility.
                "user_prompt": ("STRING", {"default": DEFAULT_USER_PROMPT, "multiline": True}),
                "system_prompt": ("STRING", {"default": DEFAULT_SYSTEM_PROMPT, "multiline": True}),
                "source_name_override": ("STRING", {"default": "", "multiline": False}),
            },
            "optional": {
                "user_prompt_source": (["manual", "bundled_library", "external_directory"], {"default": "manual"}),
                "user_prompt_directory": ("STRING", {"default": "", "multiline": False}),
                "user_prompt_file": (default_combo_values("user"), {"default": PLACEHOLDER}),
                "system_prompt_source": (["manual", "bundled_library", "external_directory"], {"default": "manual"}),
                "system_prompt_directory": ("STRING", {"default": "", "multiline": False}),
                "system_prompt_file": (default_combo_values("system"), {"default": PLACEHOLDER}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("system_prompt", "user_prompt", "source_name")
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/prompts"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        # Prompt file choices can be populated dynamically by the frontend from an
        # external directory, so ComfyUI's static COMBO membership check must not
        # reject valid runtime selections.  Real validation happens in build().
        return True

    @classmethod
    def IS_CHANGED(
        cls,
        user_prompt,
        system_prompt,
        source_name_override,
        user_prompt_source="manual",
        user_prompt_directory="",
        user_prompt_file=PLACEHOLDER,
        system_prompt_source="manual",
        system_prompt_directory="",
        system_prompt_file=PLACEHOLDER,
        **kwargs,
    ):
        """Invalidate ComfyUI cache when a selected prompt file changes on disk."""
        user_fp = prompt_selection_fingerprint(
            "user", user_prompt_source, user_prompt_directory, user_prompt_file, user_prompt
        )
        system_fp = prompt_selection_fingerprint(
            "system", system_prompt_source, system_prompt_directory, system_prompt_file, system_prompt
        )
        return f"{user_fp}|{system_fp}|source={source_name_override or ''}"

    @staticmethod
    def _resolve_prompt(kind: str, manual_text: str, source: str, directory: str, selected_file: str) -> tuple[str, str]:
        source = (source or "manual").strip().lower()
        if source == "manual":
            text = (manual_text or "").strip()
            if not text:
                raise ValueError(f"LLM Prompt Library / Template: manual {kind}_prompt is empty.")
            return text, "<manual>"
        try:
            return load_prompt_file(kind, source, directory, selected_file)
        except PromptLibraryError as exc:
            raise ValueError(f"LLM Prompt Library / Template: {exc}") from exc

    def build(
        self,
        user_prompt,
        system_prompt,
        source_name_override,
        user_prompt_source="manual",
        user_prompt_directory="",
        user_prompt_file=PLACEHOLDER,
        system_prompt_source="manual",
        system_prompt_directory="",
        system_prompt_file=PLACEHOLDER,
    ):
        resolved_user, user_origin = self._resolve_prompt(
            "user", user_prompt, user_prompt_source, user_prompt_directory, user_prompt_file
        )
        resolved_system, system_origin = self._resolve_prompt(
            "system", system_prompt, system_prompt_source, system_prompt_directory, system_prompt_file
        )

        if (source_name_override or "").strip():
            source_name = _clean_source_name(source_name_override)
        elif user_origin not in {"<manual>", PLACEHOLDER}:
            source_name = _clean_source_name(Path(user_origin).stem)
        else:
            source_name = ""

        LOGGER.info(
            "Resolved LLM prompts: user=%s, system=%s, user_chars=%d, system_chars=%d",
            user_origin, system_origin, len(resolved_user), len(resolved_system),
        )
        return (resolved_system, resolved_user, source_name)


class MiniMaxParseExternalLLMOutputV16:
    """Parses an LLM response generated by a separate ComfyUI LLM node.

    Since 2.0.0 the LLM output is optional: when the integrated LLM chat node
    is bypassed or disabled (or any other LLM source delivers nothing), manual
    fallback fields take over, so the LLM section of a workflow can be switched
    off without a validation error.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "song_count": ("INT", {"default": 1, "min": 1, "max": 100, "step": 1}),
                "seed_mode": (["random_each_song", "increment_from_base"], {"default": "random_each_song"}),
                "base_seed": ("INT", {"default": 1, "min": 0, "max": 9223372036854775806, "step": 1}),
                "user_prompt": ("STRING", {"default": DEFAULT_USER_PROMPT, "multiline": True}),
                "source_name_override": ("STRING", {"default": "", "multiline": False}),
                "fallback_title": ("STRING", {"default": "llm-song", "multiline": False}),
            },
            "optional": {
                "structured_llm_output": ("STRING", {"forceInput": True, "multiline": True}),
                "manual_caption": ("STRING", {"default": "", "multiline": True}),
                "manual_lyrics": ("STRING", {"default": "", "multiline": True}),
                "manual_title": ("STRING", {"default": "", "multiline": False}),
                "manual_image_prompt": ("STRING", {"default": "", "multiline": True}),
                "model_check_report": ("STRING", {"default": "", "multiline": True}),
                "llm_status": ("STRING", {"default": "", "multiline": True}),
                "max_prompt_tokens": ("INT", {"default": DEFAULT_PROMPT_TOKEN_BUDGET, "min": 500, "max": MINIMAX_MAX_PROMPT_TOKENS - 200, "step": 50}),
                "trim_long_prompt": ("BOOLEAN", {"default": True}),
                # Appended optional input (2.6.0): the selected song model. It
                # names the LLM output section in errors and provenance and
                # enforces that model's own hard prompt limit.
                "model_profile_json": ("STRING", {"forceInput": True, "multiline": True}),
                "cover_source_json": ("STRING", {"forceInput": True}),
                "structured_summary_json": ("STRING", {"forceInput": True}),
                # Appended optional input (3.1.0): the Whisper transcription of
                # the original cover words.  It is recorded as provenance and
                # used for a soft fidelity check; it never replaces the LLM's
                # sectioned lyrics.
                "cover_lyrics": ("STRING", {"forceInput": True}),
                # Appended optional input (3.1.0, Cover Studio), and it stays
                # last on purpose: ComfyUI maps a saved workflow's slots
                # positionally, so a new input anywhere earlier would shift
                # every socket after it.  Non-empty, it replaces whatever the
                # LLM wrote, and the mode rules are told the words are
                # intentional rather than a lazy copy of the source.  Empty
                # keeps the previous behaviour byte for byte.
                "cover_lyrics_lock": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "INT", "INT", "INT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("caption", "lyrics", "title", "image_prompt", "source_name", "generation_seed", "run_index", "variant_count", "source_path", "prompt_origin", "prompt_provenance_json")
    OUTPUT_IS_LIST = (True, True, True, True, True, True, True, True, True, True, True)
    FUNCTION = "parse"
    CATEGORY = "MiniMax Music Production Toolkit/prompts"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def parse(
        self,
        song_count,
        seed_mode,
        base_seed,
        user_prompt,
        source_name_override,
        fallback_title,
        structured_llm_output=None,
        manual_caption="",
        manual_lyrics="",
        manual_title="",
        manual_image_prompt="",
        model_check_report="",
        llm_status="",
        max_prompt_tokens=DEFAULT_PROMPT_TOKEN_BUDGET,
        trim_long_prompt=True,
        model_profile_json="",
        cover_source_json="",
        structured_summary_json="",
        cover_lyrics="",
        cover_lyrics_lock="",
    ):
        profile = profile_from_payload(model_profile_json)
        required_section = profile.conditioning_section if profile is not None else "Caption"
        raw = (structured_llm_output or "").strip()
        status = (llm_status or "").strip()
        # Read once, up front: the cover mode gates the trim guard below, and the
        # transcription is named in the errors when the LLM returned nothing.
        cover_lyrics_record, cover_lyrics_text = _cover_lyrics_payload(cover_lyrics)
        cover_mode = ""
        if profile is not None and profile.is_cover:
            try:
                cover_mode = normalize_lyrics_mode(json.loads(cover_source_json).get("lyrics_mode"))
            except (ValueError, TypeError, AttributeError):
                cover_mode = ""
        try:
            parsed = _parse_sections(raw, required_section) if raw else {}
        except ValueError as exc:
            # Carry the upstream LLM status into the error so a failed LLM
            # generation is recognizable instead of looking like a format error.
            if status:
                raise ValueError(f"{exc}\n\nUpstream LLM status: {status}") from exc
            raise

        caption = (parsed.get("caption") or "").strip() or (manual_caption or "").strip()
        lyrics = (parsed.get("lyrics") or "").strip() or (manual_lyrics or "").strip()
        # A locked block is a user decision, not an LLM answer: it wins over the
        # model text and is then checked by the same mode rules as any other
        # lyrics value.
        lyrics_lock_text = str(cover_lyrics_lock or "").strip()
        lyrics_locked = bool(lyrics_lock_text) and profile is not None and profile.is_cover
        if lyrics_locked:
            if lyrics_lock_text != lyrics:
                LOGGER.info("Cover lyrics lock applied (%d chars) and replaces the LLM lyrics.",
                            len(lyrics_lock_text))
            lyrics = lyrics_lock_text
        cover_constraints = None
        if profile is not None and profile.is_cover and caption:
            from .cover_lyrics_contract import apply_cover_lyrics
            before = (caption, lyrics)
            alignment = None
            try:
                sections = (json.loads(structured_summary_json or '{}').get('cover_timeline') or {}).get('sections')
            except (ValueError, AttributeError):
                sections = None
            if cover_mode == LYRICS_MODE_ORIGINAL:
                from .cover_alignment import original_lyrics
                lyrics, alignment = original_lyrics(cover_lyrics_text, cover_lyrics_record, sections, lyrics)
                # The authoritative source layout owns section tags; a differing
                # LLM arrangement must not silently mismatch the repaired lyrics.
                if sections:
                    import re
                    entries = list(re.finditer(r'^\s*\d+[.)]?\s*\[([^\]\n]+)\]', caption, re.M))
                    if entries and len(entries) != len(sections):
                        raise ValueError('YuE2 Cover: Style section count differs from the measured score. Retry the arrangement.')
                    for entry, section in reversed(list(zip(entries, sections))):
                        caption = caption[:entry.start(1)] + section['tag'] + caption[entry.end(1):]
            if sections:
                from .cover_alignment import measured_style_headers
                caption = measured_style_headers(caption, sections)
            caption, lyrics = apply_cover_lyrics(cover_mode, caption, lyrics, cover_lyrics_text,
                                                 lyrics_locked=lyrics_locked)
            cover_constraints = {"mode": cover_mode, "instrumental_text_sanitized": before != (caption, lyrics),
                                 "original_word_order_verified": cover_mode == LYRICS_MODE_ORIGINAL,
                                 "lyrics_locked": lyrics_locked,
                                 "original_lyrics_alignment": alignment}
        if not caption or not lyrics:
            # A connected transcription is evidence the run should have worked;
            # saying so turns "Lyrics stayed empty" into an actionable message.
            transcription_hint = (
                (" The source transcription is connected, but a musical Style is still required. "
                 "Supply manual_caption or restore the LLM output; original words are restored automatically."
                 if cover_mode == LYRICS_MODE_ORIGINAL else
                 " The source transcription is connected as a phrasing reference. New words must "
                 "be supplied by the LLM's [Lyrics] section or manual_lyrics, together with a musical Style.")
                if cover_lyrics_text else ""
            )
            if raw:
                # _parse_sections already raised for non-empty unparseable text;
                # this guards the edge case of text that parsed but stayed empty.
                raise ValueError(
                    f"Could not parse required LLM sections. {required_section} or Lyrics stayed empty."
                    + transcription_hint
                )
            if status:
                raise ValueError(
                    "The LLM chat node returned no text, so there is nothing to parse. "
                    f"Upstream LLM status: {status}"
                    " Fill manual_caption and manual_lyrics to continue without the LLM, or fix the LLM chat node."
                    + transcription_hint
                )
            raise ValueError(
                "LLM output is empty (LLM node bypassed or disabled) and no manual fallback is configured. "
                "Fill manual_caption and manual_lyrics, or re-enable the LLM chat node."
                + transcription_hint
            )

        length_request = None
        duration_source = None
        if profile is not None and profile.is_yue2:
            from .song_duration import request_from_brief, request_from_style, duration_style
            length_request = request_from_brief(structured_summary_json, user_prompt)
            if length_request:
                duration_source = "brief_length"
            else:
                length_request = request_from_style(caption)
                if length_request:
                    duration_source = "style_duration_plan"
            caption = duration_style(caption, length_request, cover=profile.is_cover)

        effective_budget, budget_note = self._effective_token_budget(int(max_prompt_tokens), profile)
        caption, lyrics, budget_info = self._apply_prompt_budget(
            caption, lyrics, effective_budget, bool(trim_long_prompt), profile
        )
        if budget_note:
            budget_info["budget_note"] = budget_note
        if length_request and budget_info.get("prompt_trimmed"):
            raise ValueError(
                "YuE2 prompt trimming would shorten the requested timed arrangement. "
                "Shorten redundant Style wording or raise max_prompt_tokens; keep all sections and lyrics."
            )
        if cover_mode and budget_info.get("prompt_trimmed"):
            # The user asked for the original words; dropping the end of them
            # silently would be worse than stopping.
            raise ValueError(
                "YuE2 prompt trimming would drop cover sections or transcribed original lyrics. "
                "Shorten redundant Style wording or raise max_prompt_tokens; the transcription must "
                "stay complete, or choose the 'new lyrics' cover mode."
            )

        title = (parsed.get("title") or "").strip() or (manual_title or "").strip() or fallback_title or "llm-song"
        cover = None
        if profile is not None and profile.is_cover:
            from .music_cover import cover_record
            cover = cover_record(cover_source_json)
            title = cover["title"]
        image_prompt = (parsed.get("image_prompt") or "").strip() or (manual_image_prompt or "").strip()
        if not image_prompt:
            image_prompt = _fallback_image_prompt(title, caption, lyrics)
        image_prompt, prohibition_appended = ensure_no_text_prohibition(image_prompt)
        if prohibition_appended:
            LOGGER.info("Appended the text-free prohibition to the FLUX image prompt (the LLM omitted it).")

        source_name = _clean_source_name(source_name_override) if (source_name_override or "").strip() else _clean_source_name(title)
        if cover:
            source_name = _clean_source_name(title)
        used_manual = not raw
        provenance = {
            "source_mode": "external_comfyui_llm" if raw else "manual_override",
            "user_prompt": user_prompt,
            "raw_response": raw,
            "manual_fields_used": used_manual,
            "song_model": profile.id if profile is not None else None,
            "song_model_name": profile.display_name if profile is not None else None,
            "conditioning_section": required_section,
        }
        provenance.update(budget_info)
        if length_request:
            provenance["duration_request"] = length_request
            provenance["duration_source"] = duration_source
        if cover:
            provenance.update(cover_source=cover, title_source="audio_filename")
            provenance['cover_lyrics_validation'] = cover_constraints
            if cover_lyrics_record:
                provenance["cover_lyrics"] = {
                    "source": cover_lyrics_record.get("source"),
                    "model": cover_lyrics_record.get("model"),
                    "language": cover_lyrics_record.get("language"),
                    "language_probability": cover_lyrics_record.get("language_probability"),
                    "device": cover_lyrics_record.get("device"),
                    "compute_type": cover_lyrics_record.get("compute_type"),
                    "segment_count": cover_lyrics_record.get("segment_count"),
                    "characters": cover_lyrics_record.get("characters"),
                    "lyrics_word_coverage": _lyrics_word_coverage(
                        cover_lyrics_record.get("text"), lyrics),
                }
        out = {k: [] for k in ["caption", "lyrics", "title", "image_prompt", "source_name", "generation_seed", "run_index", "variant_count", "source_path", "prompt_origin", "prompt_provenance_json"]}
        for idx in range(int(song_count)):
            seed = _new_seed() if seed_mode == "random_each_song" else (int(base_seed) + idx) % (2**63 - 1)
            out["caption"].append(caption)
            out["lyrics"].append(lyrics)
            out["title"].append(title)
            out["image_prompt"].append(image_prompt)
            out["source_name"].append(source_name)
            out["generation_seed"].append(seed)
            out["run_index"].append(idx + 1)
            out["variant_count"].append(int(song_count))
            out["source_path"].append("<external_comfyui_llm>" if raw else "<manual_override>")
            out["prompt_origin"].append("external_comfyui_llm" if raw else "manual_override")
            out["prompt_provenance_json"].append(json.dumps(provenance, ensure_ascii=False))
        return tuple(out[k] for k in ["caption", "lyrics", "title", "image_prompt", "source_name", "generation_seed", "run_index", "variant_count", "source_path", "prompt_origin", "prompt_provenance_json"])

    @staticmethod
    def _effective_token_budget(max_prompt_tokens: int, profile) -> tuple:
        """Clamp the trim budget to the selected model's own hard prompt limit.

        A budget *above* the model's technical limit cannot be honoured - the
        encoder rejects the prompt - so it is lowered to that limit with a note
        instead of failing later. A budget below it is left exactly as the user
        set it.
        """
        if profile is None:
            return int(max_prompt_tokens), None
        hard_limit = int(profile.prompt_token_hard_limit)
        if int(max_prompt_tokens) > hard_limit:
            note = (
                f"max_prompt_tokens {int(max_prompt_tokens)} is above the {profile.display_name} hard prompt limit "
                f"of {hard_limit} tokens; using {hard_limit}."
            )
            LOGGER.warning("LLM prompt budget reduced: %s", note)
            return hard_limit, note
        return int(max_prompt_tokens), None

    @staticmethod
    def _apply_prompt_budget(caption: str, lyrics: str, max_prompt_tokens: int, trim_long_prompt: bool, profile=None):
        """Keep the combined Caption+Lyrics inside the MiniMax token budget.

        The decision counts with the real MiniMax tokenizer when its checkpoint
        is readable (exact) and with the documented conservative estimate
        otherwise; the returned provenance names which one was used, so an
        estimate is never presented as a measurement.

        When the count exceeds the budget, the prompt is trimmed softly (whole
        lines from the end, orphan section tags removed, caption intact) or,
        with trim_long_prompt disabled, a clear error is raised instead of
        letting the MiniMax encoder fail cryptically.
        """
        counter, tokenizer_id = (None, "") if profile is not None and profile.is_yue2 else token_counter()
        count = counter or estimate_prompt_tokens
        method = "tokenizer" if counter is not None else "estimate"
        count_now = count(caption, lyrics)
        if count_now <= max_prompt_tokens:
            return caption, lyrics, {
                "prompt_tokens": count_now,
                "prompt_tokens_estimated": estimate_prompt_tokens(caption, lyrics),
                "prompt_token_count_method": method,
                "prompt_tokenizer": tokenizer_id,
                "prompt_trimmed": False,
            }
        if not trim_long_prompt:
            model_name = profile.display_name if profile is not None else "MiniMax"
            hard_limit_text = (
                f", {profile.display_name} hard limit {profile.prompt_token_hard_limit}"
                if profile is not None
                else f", MiniMax hard limit {MINIMAX_MAX_PROMPT_TOKENS}"
            )
            raise ValueError(
                f"LLM prompt exceeds the {model_name} token budget: {count_now} "
                f"{'tokens (measured)' if method == 'tokenizer' else 'estimated tokens'} "
                f"(budget {max_prompt_tokens}{hard_limit_text}). "
                "Shorten the source prompt, lower the LLM response length, or enable trim_long_prompt."
            )
        trimmed = trim_prompt_to_budget(caption, lyrics, max_prompt_tokens, counter=counter)
        hard_cut = bool(trimmed["hard_cut_used"])
        if not (trimmed["caption"] or trimmed["lyrics"]):
            model_name = profile.display_name if profile is not None else "MiniMax"
            raise ValueError(
                f"The {model_name} token budget ({max_prompt_tokens}) is too small for any content: "
                f"trimming removed everything. Raise max_prompt_tokens or shorten the prompt."
            )
        LOGGER.warning(
            "LLM prompt exceeded the %s token budget: trimmed from %d to %d %s "
            "(%d lines and %d section tags removed)%s. Shorten the source prompt for a cleaner result.",
            profile.display_name if profile is not None else "MiniMax",
            trimmed["original_estimated_tokens"],
            trimmed["estimated_tokens"],
            "measured tokens" if method == "tokenizer" else "estimated tokens",
            int(trimmed.get("removed_lines", 0)),
            int(trimmed.get("removed_sections", 0)),
            " (hard cut in an oversized single line)" if hard_cut else "",
        )
        return (
            trimmed["caption"],
            trimmed["lyrics"],
            {
                "prompt_tokens": trimmed["estimated_tokens"],
                "prompt_tokens_estimated": estimate_prompt_tokens(trimmed["caption"], trimmed["lyrics"]),
                "original_prompt_tokens": trimmed["original_estimated_tokens"],
                "original_prompt_tokens_estimated": estimate_prompt_tokens(caption, lyrics),
                "prompt_token_count_method": method,
                "prompt_tokenizer": tokenizer_id,
                "prompt_trimmed": True,
                "hard_cut_used": hard_cut,
                "removed_lines": int(trimmed.get("removed_lines", 0)),
                "removed_sections": int(trimmed.get("removed_sections", 0)),
            },
        )


NODE_CLASS_MAPPINGS = {
    "MiniMaxPromptSourceArtworkV16": MiniMaxPromptSourceArtworkV16,
    "MiniMaxLLMTemplateV16": MiniMaxLLMTemplateV16,
    "MiniMaxParseExternalLLMOutputV16": MiniMaxParseExternalLLMOutputV16,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxPromptSourceArtworkV16": "Structured Song Prompt Source (Folder / Manual)",
    "MiniMaxLLMTemplateV16": "LLM Prompt Library / Template",
    "MiniMaxParseExternalLLMOutputV16": "Parse Structured Music LLM Output",
}
