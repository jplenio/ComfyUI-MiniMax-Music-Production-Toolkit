from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from .prompt_library import (PLACEHOLDER, PromptLibraryError, default_combo_values, load_prompt_file, prompt_selection_fingerprint)
from .prompt_budget import (
    DEFAULT_PROMPT_TOKEN_BUDGET,
    MINIMAX_MAX_PROMPT_TOKENS,
    estimate_prompt_tokens,
    trim_prompt_to_budget,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("prompts")

_SECTION_RE = re.compile(r"^\s*\[(Title|Caption|Lyrics|Count|Song-Count|Image[_ ]Prompt)\]\s*$", re.IGNORECASE)
_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

def _load_bundled_default_system_prompt() -> str:
    """Load the shipped production prompt from its canonical library file.

    Keeping the large prompt in one file avoids silent drift between the default
    text shown in the node and the bundled system-prompt library.  A concise
    fallback keeps node discovery alive if an installation is incomplete; file
    mode will still surface the precise missing-file error at execution time.
    """
    path = Path(__file__).resolve().parent / "prompts" / "system" / "minimax-music3-production.txt"
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            raise ValueError("bundled system prompt is empty")
        return text
    except Exception as exc:
        LOGGER.warning("Could not load bundled default system prompt %s: %s", path, exc)
        return (
            "You are a music-production prompt rewriter for MiniMax Music 3. "
            "Return only [Caption], [Lyrics], [Title], and [Image_Prompt], in that order."
        )


DEFAULT_SYSTEM_PROMPT = _load_bundled_default_system_prompt()
DEFAULT_USER_PROMPT = 'Instrumental Progressive House with melodic and subtle trance influences, highly atmospheric and spacious, driven by memorable signature motifs and distinctive recurring synth riffs. Emotional, smooth, modern, with strong progression and evolving layers. create a 4–5 minutes long melodic story in the track.'


def _clean_source_name(value: str) -> str:
    name = _WINDOWS_INVALID.sub("_", (value or "").strip()).strip(" .")
    return name or "song"


def _new_seed() -> int:
    return secrets.randbelow(2**63 - 1)


def _resolve_prompt_directory(value: str) -> Path:
    raw = os.path.expandvars(os.path.expanduser((value or "").strip()))
    if not raw:
        raise ValueError("MiniMax Prompt Source: prompt_directory is empty while source_mode='folder'.")
    p = Path(raw)
    if not p.is_absolute():
        try:
            import folder_paths
            p = Path(folder_paths.base_path) / p
        except Exception:
            p = Path.cwd() / p
    return p.resolve()


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise UnicodeDecodeError("utf-8", data, 0, 1, f"Could not decode {path}")


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


def _parse_sections(text: str) -> Dict[str, Any]:
    """Parse structured LLM output robustly.

    Accepted examples for top-level headers include:
      [Title]
      **[Title]**
      ### [Title]
      Title:
      ## Caption
      Image_Prompt:

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
        r"(?:\[\s*)?(Title|Caption|Lyrics|Count|Song[-_ ]?Count|Image[-_ ]?Prompt)"
        r"(?:\s*\])?\s*(?:\*\*|__)?\s*:?[ \t]*$",
        re.IGNORECASE,
    )
    inline_re = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?\s*"
        r"(?:\[\s*)?(Title|Caption|Lyrics|Count|Song[-_ ]?Count|Image[-_ ]?Prompt)"
        r"(?:\s*\])?\s*(?:\*\*|__)?\s*:\s*(.+?)\s*$",
        re.IGNORECASE,
    )

    def key_for(label: str) -> str:
        key = label.lower().replace("-", "_").replace(" ", "_")
        if key in {"song_count", "song__count"}:
            return "count"
        if key in {"imageprompt", "image__prompt"}:
            return "image_prompt"
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
        missing.append("Caption")
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
        raise ValueError(
            "Could not parse required LLM sections. "
            f"Missing/non-empty: {', '.join(missing)}. "
            f"Detected top-level sections: {unique_detected or ['none']}.\n\n"
            "The external LLM should return [Caption], [Lyrics], [Title], and [Image_Prompt] in that order.\n\n"
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
            allowed = set()
            for ext in (extensions or "").split(","):
                ext = ext.strip().lower()
                if not ext:
                    continue
                if not ext.startswith("."):
                    ext = "." + ext
                allowed.add(ext)
            iterator = directory.rglob("*") if recursive else directory.glob("*")
            files = sorted([p for p in iterator if p.is_file() and p.suffix.lower() in allowed], key=lambda p: str(p).lower())
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
        global_index = 0
        for entry in entries:
            count = entry.get("count_override") or int(song_count)
            for variant in range(1, count + 1):
                seed = _new_seed() if seed_mode == "random_each_song" else (int(base_seed) + global_index) % (2**63 - 1)
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
                global_index += 1
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
    ):
        raw = (structured_llm_output or "").strip()
        status = (llm_status or "").strip()
        try:
            parsed = _parse_sections(raw) if raw else {}
        except ValueError as exc:
            # Carry the upstream LLM status into the error so a failed LLM
            # generation is recognizable instead of looking like a format error.
            if status:
                raise ValueError(f"{exc}\n\nUpstream LLM status: {status}") from exc
            raise

        caption = (parsed.get("caption") or "").strip() or (manual_caption or "").strip()
        lyrics = (parsed.get("lyrics") or "").strip() or (manual_lyrics or "").strip()
        if not caption or not lyrics:
            if raw:
                # _parse_sections already raised for non-empty unparseable text;
                # this guards the edge case of text that parsed but stayed empty.
                raise ValueError("Could not parse required LLM sections. Caption or Lyrics stayed empty.")
            if status:
                raise ValueError(
                    "The LLM chat node returned no text, so there is nothing to parse. "
                    f"Upstream LLM status: {status} "
                    "Fill manual_caption and manual_lyrics to continue without the LLM, or fix the LLM chat node."
                )
            raise ValueError(
                "LLM output is empty (LLM node bypassed or disabled) and no manual fallback is configured. "
                "Fill manual_caption and manual_lyrics, or re-enable the LLM chat node."
            )

        caption, lyrics, budget_info = self._apply_prompt_budget(
            caption, lyrics, int(max_prompt_tokens), bool(trim_long_prompt)
        )

        title = (parsed.get("title") or "").strip() or (manual_title or "").strip() or fallback_title or "llm-song"
        image_prompt = (parsed.get("image_prompt") or "").strip() or (manual_image_prompt or "").strip()
        if not image_prompt:
            image_prompt = _fallback_image_prompt(title, caption, lyrics)
        image_prompt, prohibition_appended = ensure_no_text_prohibition(image_prompt)
        if prohibition_appended:
            LOGGER.info("Appended the text-free prohibition to the FLUX image prompt (the LLM omitted it).")

        source_name = _clean_source_name(source_name_override) if (source_name_override or "").strip() else _clean_source_name(title)
        used_manual = not raw
        provenance = {
            "source_mode": "external_comfyui_llm" if raw else "manual_override",
            "user_prompt": user_prompt,
            "raw_response": raw,
            "manual_fields_used": used_manual,
        }
        provenance.update(budget_info)
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
    def _apply_prompt_budget(caption: str, lyrics: str, max_prompt_tokens: int, trim_long_prompt: bool):
        """Keep the combined Caption+Lyrics inside the MiniMax token budget.

        When the conservative estimate exceeds the budget, the prompt is
        trimmed softly (whole lines from the end, orphan section tags removed,
        caption intact) or, with trim_long_prompt disabled, a clear error is
        raised instead of letting the MiniMax encoder fail cryptically.
        """
        estimate = estimate_prompt_tokens(caption, lyrics)
        if estimate <= max_prompt_tokens:
            return caption, lyrics, {"prompt_tokens_estimated": estimate, "prompt_trimmed": False}
        if not trim_long_prompt:
            raise ValueError(
                f"LLM prompt exceeds the MiniMax token budget: estimated {estimate} tokens "
                f"(budget {max_prompt_tokens}, MiniMax hard limit {MINIMAX_MAX_PROMPT_TOKENS}). "
                "Shorten the source prompt, lower the LLM response length, or enable trim_long_prompt."
            )
        trimmed = trim_prompt_to_budget(caption, lyrics, max_prompt_tokens)
        hard_cut = bool(trimmed["hard_cut_used"])
        LOGGER.warning(
            "LLM prompt exceeded the MiniMax token budget: trimmed from %d to %d estimated tokens%s. "
            "Shorten the source prompt for a cleaner result.",
            trimmed["original_estimated_tokens"],
            trimmed["estimated_tokens"],
            " (hard cut in an oversized single line)" if hard_cut else "",
        )
        return (
            trimmed["caption"],
            trimmed["lyrics"],
            {
                "prompt_tokens_estimated": trimmed["estimated_tokens"],
                "prompt_trimmed": True,
                "original_prompt_tokens_estimated": trimmed["original_estimated_tokens"],
                "hard_cut_used": hard_cut,
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
