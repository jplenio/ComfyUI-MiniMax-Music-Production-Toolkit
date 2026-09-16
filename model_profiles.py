"""Song-model profiles: which music model the toolkit drives, and its rules.

This module is the single place that knows the differences between the
supported song-generation models (currently MiniMax Music 3 and YuE2).  It is a
pure data module: it reads ``model_profiles.json`` from the package root and
exposes typed, validated profiles.  It imports nothing from ComfyUI and nothing
from the node modules, so it stays usable from tests, scripts and the frontend
route layer.

Why a data file and not constants: the profile carries author-facing rules
(what the conditioning text has to look like, how long it may be, which sampler
values are a sane start) that documentation and the prompt library also need to
agree with.  Keeping them in one JSON file means the node, the parser, the docs
gate and the frontend all read the same numbers.

Nothing in here is a benchmark claim.  ``practical_max_duration_seconds`` and
``prompt_token_budget`` are derived limits and carry a ``derived`` flag in the
payload so a consumer never presents them as model specifications.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .toolkit_logging import get_logger

LOGGER = get_logger("model_profiles")

PROFILE_FILE_NAME = "model_profiles.json"
PROFILE_SCHEMA = "minimax_music_toolkit_song_model_profile_v1"

# Fallback used only when the data file is unreadable.  It deliberately mirrors
# the historic single-model behaviour so an incomplete installation still runs.
_FALLBACK_ID = "minimax_music3"
_FALLBACK_DISPLAY = "MiniMax Music 3"
_FALLBACK_SYSTEM_PROMPT_FILE = "minimax-music3-production.txt"


@dataclass(frozen=True)
class SongModelProfile:
    """Validated view over one entry of ``model_profiles.json``."""

    id: str
    display_name: str
    short_name: str = ""
    engine: str = ""
    system_prompt_file: str = ""
    system_prompt_folder: str = "prompts/system"
    conditioning_section: str = "Caption"
    conditioning_section_aliases: Tuple[str, ...] = ("Caption",)
    conditioning_kind: str = "caption"
    conditioning_description: str = ""
    lyrics_kind: str = "sectioned"
    lyrics_description: str = ""
    prompt_token_budget: int = 4500
    prompt_token_hard_limit: int = 5000
    prompt_token_counter: str = "estimate"
    context_tokens: Optional[int] = None
    frames_per_second: Optional[int] = None
    default_duration_seconds: float = 300.0
    max_duration_seconds: float = 360.0
    practical_max_duration_seconds: float = 360.0
    sampler_defaults: Dict[str, Any] = field(default_factory=dict)
    text_defaults: Dict[str, Any] = field(default_factory=dict)
    output_sample_rate: Optional[int] = None
    generation_nodes: Tuple[str, ...] = ()
    model_files: Dict[str, Any] = field(default_factory=dict)
    documentation: str = ""
    notes: Tuple[str, ...] = ()

    # -- derived helpers ---------------------------------------------------

    @property
    def is_yue2(self) -> bool:
        return self.id in {"yue2", "yue2_cover"}

    @property
    def is_cover(self) -> bool:
        return self.id == "yue2_cover"

    @property
    def sections(self) -> Tuple[str, ...]:
        """Top-level LLM output sections this model's system prompt must emit."""
        return (
            f"[{self.conditioning_section}]",
            "[Lyrics]",
            "[Title]",
            "[Image_Prompt]",
        )

    def matches_system_prompt_file(self, relative_path: str) -> bool:
        """True when *relative_path* belongs to this model's prompt family.

        YuE2 prompts live in ``prompts/system/yue2/``; the MiniMax prompts are
        the files directly under ``prompts/system/``.  A custom prompt saved to
        ``_custom/`` deliberately belongs to neither family.
        """
        relative = (relative_path or "").strip().replace("\\", "/").lstrip("/")
        if not relative or relative.startswith("_custom/"):
            return False
        return relative.startswith("yue2/") if self.is_yue2 else not relative.startswith("yue2/")

    def family_of_file(self, relative_path: str) -> Optional[str]:
        """``'yue2'``, ``'minimax_music3'`` or ``None`` for a custom/unknown file."""
        relative = (relative_path or "").strip().replace("\\", "/").lstrip("/")
        if not relative or relative.startswith("_custom/"):
            return None
        return "yue2" if relative.startswith("yue2/") else "minimax_music3"

    def duration_ceiling(self) -> float:
        """The largest ``max_duration`` this profile recommends, in seconds."""
        return float(min(self.max_duration_seconds, self.practical_max_duration_seconds))

    def clamp_duration(self, seconds: float) -> Tuple[float, Optional[str]]:
        """Clamp *seconds* to this profile's window; returns ``(value, note)``."""
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            value = self.default_duration_seconds
            note = f"unreadable duration, using the {self.display_name} default"
        else:
            note = None
        ceiling = self.duration_ceiling()
        if value > ceiling:
            value = ceiling
            note = f"clamped to the {self.display_name} ceiling of {ceiling:g} s"
        elif value < 1.0:
            value = 1.0
            note = "clamped to the 1 s minimum"
        return float(value), note

    def feasible_duration_seconds(self, prompt_tokens: int) -> Optional[float]:
        """Upper bound before ABC/instruction overhead, never a duration promise.

        Only meaningful for a model whose prompt shares the context with the
        generated music (YuE2).  Returns ``None`` when the profile does not
        declare a context length.
        """
        if not self.context_tokens or not self.frames_per_second:
            return None
        remaining = max(0, int(self.context_tokens) - int(prompt_tokens))
        return remaining / float(self.frames_per_second)

    def as_payload(self) -> Dict[str, Any]:
        """The machine-readable record written to ``profile_json``.

        Stable keys, additive changes only.  ``derived`` lists the fields that
        are toolkit policy rather than model specification.
        """
        return {
            "schema": PROFILE_SCHEMA,
            "id": self.id,
            "display_name": self.display_name,
            "engine": self.engine,
            "prompt": {
                "system_prompt_file": self.system_prompt_file,
                "system_prompt_folder": self.system_prompt_folder,
                "conditioning_section": self.conditioning_section,
                "conditioning_section_aliases": list(self.conditioning_section_aliases),
                "conditioning_kind": self.conditioning_kind,
                "conditioning_description": self.conditioning_description,
                "lyrics_kind": self.lyrics_kind,
                "lyrics_description": self.lyrics_description,
                "token_budget": self.prompt_token_budget,
                "token_hard_limit": self.prompt_token_hard_limit,
                "token_counter": self.prompt_token_counter,
                "context_tokens": self.context_tokens,
                "frames_per_second": self.frames_per_second,
                "feasible_duration_seconds": self.feasible_duration_seconds(self.prompt_token_budget),
            },
            "duration": {
                "default_seconds": self.default_duration_seconds,
                "ceiling_seconds": self.duration_ceiling(),
                "node_max_seconds": self.max_duration_seconds,
            },
            "sampler_defaults": dict(self.sampler_defaults),
            "text_defaults": dict(self.text_defaults),
            "output_sample_rate": self.output_sample_rate,
            "generation_nodes": list(self.generation_nodes),
            "model_files": dict(self.model_files),
            "documentation": self.documentation,
            "notes": list(self.notes),
            "derived": [
                "duration.ceiling_seconds",
                "prompt.token_budget",
                "prompt.feasible_duration_seconds",
            ],
        }


def profiles_path() -> Path:
    """Absolute path of the bundled profile data file."""
    return Path(__file__).resolve().parent / PROFILE_FILE_NAME


def _profile_from_mapping(raw: Dict[str, Any]) -> Optional[SongModelProfile]:
    """Build a profile from one decoded JSON object, or ``None`` when unusable."""
    if not isinstance(raw, dict):
        return None
    model_id = str(raw.get("id") or "").strip()
    if not model_id:
        LOGGER.warning("Ignoring a song-model profile without an id.")
        return None

    def _text(key: str, default: str = "") -> str:
        value = raw.get(key, default)
        return str(value).strip() if value is not None else default

    def _number(key: str, default: float) -> float:
        try:
            return float(raw.get(key, default))
        except (TypeError, ValueError):
            LOGGER.warning("Song-model profile '%s': %s is not a number, using %s.", model_id, key, default)
            return float(default)

    def _integer(key: str, default: Optional[int]) -> Optional[int]:
        value = raw.get(key, default)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            LOGGER.warning("Song-model profile '%s': %s is not an integer, ignoring it.", model_id, key)
            return None

    def _strings(key: str) -> Tuple[str, ...]:
        value = raw.get(key) or []
        if isinstance(value, str):
            value = [value]
        return tuple(str(item).strip() for item in value if str(item).strip())

    def _mapping(key: str) -> Dict[str, Any]:
        value = raw.get(key)
        return dict(value) if isinstance(value, dict) else {}

    aliases = tuple(
        dict.fromkeys(
            [str(alias).strip() for alias in (_strings("conditioning_section_aliases") or (_text("conditioning_section", "Caption"),))]
        )
    )
    return SongModelProfile(
        id=model_id,
        display_name=_text("display_name") or model_id,
        short_name=_text("short_name") or _text("display_name") or model_id,
        engine=_text("engine"),
        system_prompt_file=_text("system_prompt_file"),
        system_prompt_folder=_text("system_prompt_folder", "prompts/system") or "prompts/system",
        conditioning_section=_text("conditioning_section", "Caption") or "Caption",
        conditioning_section_aliases=aliases,
        conditioning_kind=_text("conditioning_kind", "caption") or "caption",
        conditioning_description=_text("conditioning_description"),
        lyrics_kind=_text("lyrics_kind", "sectioned") or "sectioned",
        lyrics_description=_text("lyrics_description"),
        prompt_token_budget=int(_number("prompt_token_budget", 4500)),
        prompt_token_hard_limit=int(_number("prompt_token_hard_limit", 5000)),
        prompt_token_counter=_text("prompt_token_counter", "estimate") or "estimate",
        context_tokens=_integer("context_tokens", None),
        frames_per_second=_integer("frames_per_second", None),
        default_duration_seconds=_number("default_duration_seconds", 300.0),
        max_duration_seconds=_number("max_duration_seconds", 360.0),
        practical_max_duration_seconds=_number(
            "practical_max_duration_seconds", _number("max_duration_seconds", 360.0)
        ),
        sampler_defaults=_mapping("sampler_defaults"),
        text_defaults=_mapping("text_defaults"),
        output_sample_rate=_integer("output_sample_rate", None),
        generation_nodes=_strings("generation_nodes"),
        model_files=_mapping("model_files"),
        documentation=_text("documentation"),
        notes=_strings("notes"),
    )


def _fallback_profile() -> SongModelProfile:
    return SongModelProfile(
        id=_FALLBACK_ID,
        display_name=_FALLBACK_DISPLAY,
        short_name="MiniMax",
        system_prompt_file=_FALLBACK_SYSTEM_PROMPT_FILE,
    )


_CACHE: Optional[Dict[str, SongModelProfile]] = None
_DEFAULT_ID: Optional[str] = None


def load_profiles(force: bool = False) -> Dict[str, SongModelProfile]:
    """All bundled song-model profiles, keyed by id, in file order.

    A broken or missing data file degrades to the historic single-model profile
    instead of breaking node registration.
    """
    global _CACHE, _DEFAULT_ID
    if _CACHE is not None and not force:
        return _CACHE

    profiles: Dict[str, SongModelProfile] = {}
    default_id = ""
    path = profiles_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        LOGGER.warning("Song-model profile file is missing (%s); using the built-in MiniMax profile.", path)
        data = None
    except (OSError, ValueError) as exc:
        LOGGER.warning("Song-model profile file %s could not be read (%s); using the built-in profile.", path, exc)
        data = None

    if isinstance(data, dict):
        for raw in data.get("profiles") or []:
            profile = _profile_from_mapping(raw)
            if profile is None:
                continue
            if profile.id in profiles:
                LOGGER.warning("Duplicate song-model profile id '%s' - the later entry is ignored.", profile.id)
                continue
            profiles[profile.id] = profile
        default_id = str(data.get("default") or "").strip()

    if not profiles:
        fallback = _fallback_profile()
        profiles[fallback.id] = fallback
        default_id = fallback.id

    if default_id not in profiles:
        if default_id:
            LOGGER.warning("Song-model profile default '%s' is unknown; falling back to '%s'.", default_id, next(iter(profiles)))
        default_id = next(iter(profiles))

    _CACHE = profiles
    _DEFAULT_ID = default_id
    return profiles


def profile_ids() -> List[str]:
    """All profile ids in file order."""
    return list(load_profiles().keys())


def display_names() -> List[str]:
    """The selection values shown by the model dropdown (default first)."""
    profiles = load_profiles()
    default_id = default_profile_id()
    ordered = [default_id] + [key for key in profiles if key != default_id]
    return [profiles[key].display_name for key in ordered]


def default_profile_id() -> str:
    load_profiles()
    return _DEFAULT_ID or _FALLBACK_ID


def default_profile() -> SongModelProfile:
    return load_profiles()[default_profile_id()]


def get_profile(selection: str) -> SongModelProfile:
    """Look a profile up by id *or* display name, with a safe default."""
    profiles = load_profiles()
    key = str(selection or "").strip()
    if key in profiles:
        return profiles[key]
    folded = key.casefold()
    if folded:
        for profile in profiles.values():
            if profile.display_name.casefold() == folded or profile.short_name.casefold() == folded:
                return profile
    if folded:
        LOGGER.warning(
            "Unknown song model '%s'; using '%s'. Available: %s",
            selection, default_profile_id(), ", ".join(p.display_name for p in profiles.values()),
        )
    return default_profile()


def profile_from_payload(payload: Any) -> Optional[SongModelProfile]:
    """Rebuild a profile from a ``profile_json`` string/object, or ``None``.

    Downstream nodes receive the profile as text over a wire.  Rebuilding it
    from the payload (instead of trusting an id and looking the model up) keeps
    the run self-consistent: an archived workflow replays the profile it was
    built with, even after the bundled data file changes.
    """
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except ValueError:
            LOGGER.warning("Song-model profile payload is not valid JSON; ignoring it.")
            return None
    if not isinstance(payload, dict):
        return None
    if "profiles" in payload and isinstance(payload.get("profiles"), list):
        # A whole data file was connected by mistake; use its default profile.
        for raw in payload["profiles"]:
            profile = _profile_from_mapping(raw)
            if profile is not None:
                return profile
        return None
    model_id = str(payload.get("id") or "").strip()
    if not model_id:
        return None
    merged: Dict[str, Any] = dict(payload)
    prompt = payload.get("prompt") if isinstance(payload.get("prompt"), dict) else {}
    duration = payload.get("duration") if isinstance(payload.get("duration"), dict) else {}
    merged.setdefault("system_prompt_file", prompt.get("system_prompt_file", ""))
    merged.setdefault("system_prompt_folder", prompt.get("system_prompt_folder", "prompts/system"))
    merged.setdefault("conditioning_section", prompt.get("conditioning_section", "Caption"))
    merged.setdefault(
        "conditioning_section_aliases",
        prompt.get("conditioning_section_aliases") or [prompt.get("conditioning_section", "Caption")],
    )
    merged.setdefault("conditioning_kind", prompt.get("conditioning_kind", "caption"))
    merged.setdefault("conditioning_description", prompt.get("conditioning_description", ""))
    merged.setdefault("lyrics_kind", prompt.get("lyrics_kind", "sectioned"))
    merged.setdefault("lyrics_description", prompt.get("lyrics_description", ""))
    merged.setdefault("prompt_token_budget", prompt.get("token_budget", 4500))
    merged.setdefault("prompt_token_hard_limit", prompt.get("token_hard_limit", 5000))
    merged.setdefault("prompt_token_counter", prompt.get("token_counter", "estimate"))
    merged.setdefault("context_tokens", prompt.get("context_tokens"))
    merged.setdefault("frames_per_second", prompt.get("frames_per_second"))
    merged.setdefault("default_duration_seconds", duration.get("default_seconds", 300.0))
    merged.setdefault("max_duration_seconds", duration.get("node_max_seconds", 360.0))
    merged.setdefault("practical_max_duration_seconds", duration.get("ceiling_seconds", 360.0))
    return _profile_from_mapping(merged)
