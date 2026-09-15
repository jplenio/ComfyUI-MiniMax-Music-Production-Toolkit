"""Pure assembly of the canonical production-metadata payload (F19 / T16).

Extracted from ``minimax_json_output`` so the section builders can be reasoned
about (and tested) without a ComfyUI node.  Two JSON parsing policies are kept
explicit and separate, because they are a documented dialect difference:

* :func:`parse_object` is the **strict** policy used by the canonical writer: a
  malformed section is an error, never silently reinterpreted.
* :func:`parse_legacy_object` is the **tolerant** policy used by the legacy song
  metadata node: an unparsable section is preserved verbatim as ``{"raw": ...}``
  so old records stay readable.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from .metadata_schema import CURRENT_PRODUCTION_METADATA_SCHEMA
from .project_info import PROJECT_NAME, VERSION

DEFAULT_WORKFLOW_NAME = f"{PROJECT_NAME} {VERSION}"


def parse_legacy_object(text: Any) -> Dict[str, Any]:
    """Tolerant parse: keep unparsable content as ``{"raw": <text>}``.

    This is the legacy song-metadata node's policy; it never raises.
    """
    if not text:
        return {}
    try:
        value = json.loads(text)
    except Exception:
        return {"raw": text}
    return value if isinstance(value, dict) else {"raw": text}


def parse_object(text: str, label: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Save Production JSON: invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Save Production JSON: {label} must contain a JSON object.")
    return value

def overlay(base: Dict[str, Any], key: str, value: Any) -> None:
    """Set ``base[key]`` only when the value carries real content."""
    if isinstance(value, str):
        value = value.strip()
    if value is None or value == "":
        return
    base[key] = value


def build_generation_metadata(
    legacy_metadata: Dict[str, Any],
    *,
    llm_system_prompt: str = "",
    llm_user_prompt: str = "",
    llm_output: str = "",
    llm_status: str = "",
    llm_thinking: str = "",
    structured_summary_json: str = "",
    caption: str = "",
    lyrics: str = "",
    image_prompt: str = "",
    source_name: str = "",
    source_path: str = "",
    prompt_origin: str = "",
    prompt_provenance_json: str = "",
    generation_seed: Optional[int] = None,
    run_index: Optional[int] = None,
    variant_count: Optional[int] = None,
    max_duration: Optional[float] = None,
    text_seed: Optional[int] = None,
    text_cfg_scale: Optional[float] = None,
    text_top_k: Optional[int] = None,
    ksampler_seed: Optional[int] = None,
    ksampler_steps: Optional[int] = None,
    ksampler_cfg: Optional[float] = None,
    denoise: Optional[float] = None,
    flashsr_settings_json: str = "",
    pre_preset: str = "",
    pre_settings_json: str = "",
    post_preset: str = "",
    post_settings_json: str = "",
    hybrid_crossover_json: str = "",
    hf_repair_json: str = "",
    declip_json: str = "",
    release_prep_json: str = "",
    eq_report_json: str = "",
    auto_eq_analysis_json: str = "",
    mastering_json: str = "",
    resource_profile_json: str = "",
    llm_runtime_json: str = "",
    model_identity_json: str = "",
    template_version: str = "",
    workflow_name: str = DEFAULT_WORKFLOW_NAME,
) -> Dict[str, Any]:
    """Assemble the complete generation metadata payload (schema v7).

    A legacy ``metadata_json`` payload (pre-2.0.0 song-metadata node) is used
    as the base; every directly wired input overlays it.  The schema key is
    rewritten to the current version at the end.

    Since V01 the payload also carries the additive report sections ``mastering``
    (this file's EQ, auto-EQ and mastering chain reports), ``runtime`` (the
    *effective* resource profile and LLM runtime, as opposed to a
    recommendation) and ``models`` (model identity for reproducibility).  These
    are plain additions: every section is omitted when its input is empty, so a
    payload written before V01 stays byte-identical and same-schema readers that
    do not know the new keys keep working.  No schema bump is needed for
    additions - see ``metadata_schema`` for the rule.
    """
    payload: Dict[str, Any] = dict(legacy_metadata)

    payload["schema"] = CURRENT_PRODUCTION_METADATA_SCHEMA
    overlay(payload, "workflow", workflow_name or DEFAULT_WORKFLOW_NAME)

    llm: Dict[str, Any] = dict(payload.get("llm") or {})
    overlay(llm, "system_prompt", llm_system_prompt)
    overlay(llm, "user_prompt", llm_user_prompt)
    overlay(llm, "output", llm_output)
    overlay(llm, "status", llm_status)
    overlay(llm, "thinking", llm_thinking)
    # V01: the version of the system-prompt template that actually produced this
    # run (a template swap is a reproducibility-relevant input).
    overlay(llm, "template_version", template_version)
    if llm:
        payload["llm"] = llm

    structured = parse_object(structured_summary_json, "structured_summary_json")
    if structured:
        payload["structured_prompt"] = structured

    overlay(payload, "caption", caption)
    overlay(payload, "lyrics", lyrics)
    overlay(payload, "image_prompt", image_prompt)

    source: Dict[str, Any] = dict(payload.get("source") or {})
    overlay(source, "name", source_name)
    overlay(source, "path", source_path)
    overlay(source, "origin", prompt_origin)
    if run_index is not None:
        source["run_index"] = int(run_index)
    if variant_count is not None:
        source["variant_count"] = int(variant_count)
    provenance = parse_object(prompt_provenance_json, "prompt_provenance_json")
    if provenance:
        source["prompt_provenance"] = provenance
    if source:
        payload["source"] = source

    if generation_seed is not None:
        payload["generation_seed"] = int(generation_seed)

    minimax: Dict[str, Any] = dict(payload.get("minimax_music3") or {})
    if max_duration is not None:
        minimax["max_duration"] = float(max_duration)
    text_encode: Dict[str, Any] = dict(minimax.get("text_encode") or {})
    if text_seed is not None:
        text_encode["seed"] = int(text_seed)
    if text_cfg_scale is not None:
        text_encode["cfg_scale"] = float(text_cfg_scale)
    if text_top_k is not None:
        text_encode["top_k"] = int(text_top_k)
    if text_encode:
        minimax["text_encode"] = text_encode
    ksampler: Dict[str, Any] = dict(minimax.get("ksampler") or {})
    if ksampler_seed is not None:
        ksampler["seed"] = int(ksampler_seed)
    if ksampler_steps is not None:
        ksampler["steps"] = int(ksampler_steps)
    if ksampler_cfg is not None:
        ksampler["cfg"] = float(ksampler_cfg)
    if denoise is not None:
        ksampler["denoise"] = float(denoise)
    if ksampler:
        minimax["ksampler"] = ksampler
    if minimax:
        payload["minimax_music3"] = minimax

    flashsr: Dict[str, Any] = dict(payload.get("flashsr") or {})
    flashsr_settings = parse_object(flashsr_settings_json, "flashsr_settings_json")
    if flashsr_settings:
        flashsr["settings"] = flashsr_settings
    pre_settings = parse_object(pre_settings_json, "pre_settings_json")
    if pre_preset or pre_settings:
        flashsr["pre_lowpass"] = {
            "preset": (pre_preset or "").strip(),
            "settings": pre_settings,
        }
    post_settings = parse_object(post_settings_json, "post_settings_json")
    if post_preset or post_settings:
        flashsr["post_lowpass"] = {
            "preset": (post_preset or "").strip(),
            "settings": post_settings,
        }
    hybrid = parse_object(hybrid_crossover_json, "hybrid_crossover_json")
    if hybrid:
        flashsr["hybrid_crossover"] = hybrid
    hf_repair = parse_object(hf_repair_json, "hf_repair_json")
    if hf_repair:
        flashsr["hf_cymbal_shimmer_repair"] = hf_repair
    if flashsr:
        payload["flashsr"] = flashsr

    declip = parse_object(declip_json, "declip_json")
    if declip:
        # Copy the nested section first - mutating the caller's legacy dict
        # would leak this run's declip report into their payload object.
        restoration: Dict[str, Any] = dict(payload.get("restoration") or {})
        restoration["declip"] = declip
        payload["restoration"] = restoration

    release_prep = parse_object(release_prep_json, "release_prep_json")
    if release_prep:
        payload["release_prep"] = release_prep

    # --- V01 additive report sections -------------------------------------
    # The EQ / auto-EQ / mastering nodes already emit self-describing JSON
    # (``minimax_eq_report_v1``, ``minimax_auto_eq_report_v1``,
    # ``minimax_mastering_v1``); the canonical record stores them verbatim
    # instead of flattening them into new scalar fields.
    mastering: Dict[str, Any] = dict(payload.get("mastering") or {})
    eq_report = parse_object(eq_report_json, "eq_report_json")
    if eq_report:
        mastering["eq"] = eq_report
    auto_eq_analysis = parse_object(auto_eq_analysis_json, "auto_eq_analysis_json")
    if auto_eq_analysis:
        mastering["auto_eq"] = auto_eq_analysis
    mastering_chain = parse_object(mastering_json, "mastering_json")
    if mastering_chain:
        mastering["chain"] = mastering_chain
    if mastering:
        payload["mastering"] = mastering

    runtime: Dict[str, Any] = dict(payload.get("runtime") or {})
    resource_profile = parse_object(resource_profile_json, "resource_profile_json")
    if resource_profile:
        # The caller supplies the *effective* decision (which device/model was
        # really used), never a recommendation - the two must stay separable.
        runtime["resource_profile"] = resource_profile
    llm_runtime = parse_object(llm_runtime_json, "llm_runtime_json")
    if llm_runtime:
        runtime["llm"] = llm_runtime
    if runtime:
        payload["runtime"] = runtime

    model_identity = parse_object(model_identity_json, "model_identity_json")
    if model_identity:
        payload["models"] = model_identity
        if model_identity.get("schema") == "minimax_music_model_settings_v1":
            payload["generation"] = model_identity
            payload["song_model"] = model_identity["song_model"]
            if model_identity["song_model"] == "yue2":
                payload.pop("minimax_music3", None)
                payload["style"] = caption

    return payload


# --- V01: public-example sanitising ----------------------------------------

# Key names that must never reach a public example, a bug report or the demo
# catalog, whatever their section.
SECRET_KEY_PATTERN = re.compile(
    r"(?i)("
    r"hf[_-]?token|access[_-]?token|auth(orization)?|api[_-]?key|secret|password|"
    r"credential|cookie|bearer"
    r")"
)

# Absolute local paths.  Public examples keep the file name, never the layout.
ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/]"),          # Windows drive root
    re.compile(r"\\\\[^\\/\s]+[\\/]"),      # UNC share
    re.compile(r"/(?:home|Users|mnt|media|opt|var)/"),  # POSIX user/system roots
)


def contains_private_path(value: str) -> bool:
    """Return whether *value* embeds an absolute local path."""
    return any(pattern.search(value) for pattern in ABSOLUTE_PATH_PATTERNS)


def redact_private_path(value: str) -> str:
    """Replace an absolute local path with ``<path>/<last one or two parts>``.

    The trailing components are kept on purpose: an example must still show that
    the file is, say, ``Album - Title.flac`` without disclosing where the author
    keeps it.
    """
    parts = [part for part in re.split(r"[\\/]+", value) if part]
    parts = [part for part in parts if not re.fullmatch(r"[A-Za-z]:", part)]
    if not parts:
        return "<path>"
    return "<path>/" + "/".join(parts[-2:])


def public_safe_payload(payload: Any) -> Any:
    """Return a deep copy of *payload* that is safe to publish.

    Call this before a production payload is embedded in a public example, a
    documentation snippet or a pasted bug report.  It is deliberately a pure
    function (the input is never modified) and conservative: secret-named keys
    and every absolute path are replaced, everything else - including the
    audio-processing parameters that make the record reproducible - is kept.

    The runtime writer itself does *not* sanitise: the canonical JSON beside the
    rendered files is the user's own record and legitimately names their paths.
    """
    if isinstance(payload, dict):
        cleaned: Dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(key, str) and SECRET_KEY_PATTERN.search(key):
                continue
            cleaned[key] = public_safe_payload(value)
        return cleaned
    if isinstance(payload, list):
        return [public_safe_payload(item) for item in payload]
    if isinstance(payload, str):
        return redact_private_path(payload) if contains_private_path(payload) else payload
    return payload
