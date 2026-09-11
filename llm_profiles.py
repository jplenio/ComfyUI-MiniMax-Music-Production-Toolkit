"""LLM model-family and hardware profiles (L01).

A recommendation is a **starting point**, not a measurement: this module maps a
resource situation onto concrete, size-anchored GGUF candidates and states its
confidence and caveats.  It never downloads, never overrides a choice and never
claims that "bigger" is better.

Honesty rules encoded here
--------------------------
* every anchor size was read from the repository on **2026-09-11** (see
  ``ANCHOR_DATE``) and is a **file size**, not a VRAM promise - context/KV,
  compute buffers and backend overhead come on top;
* the "active parameters" of an MoE model are *not* a measure of its resident
  weight memory, so no profile reasons from them;
* a candidate is only offered for a machine whose *free* budget was checked
  against it - otherwise the profile says so and stays conservative;
* a small (2-4B) class is recommended only **after a concrete artifact has been
  checked**; until then the profile gives criteria instead of a file name;
* an installed file is matched by name, and its provenance is only called
  verified when its size matches the anchor - a file name alone proves nothing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

GIB = 1024 ** 3
ANCHOR_DATE = "2026-09-11"

# Every size below was read from the Hugging Face API for the pinned revision.
SIZE_SOURCE = (
    "file size read from the repository on " + ANCHOR_DATE + "; not a VRAM promise"
)


@dataclass(frozen=True)
class CandidateModel:
    """One concrete GGUF artifact a profile may suggest."""

    name: str
    family: str
    quantization: str
    bytes: int
    repo_id: str
    revision: str = ""
    filename: str = ""
    note: str = ""

    @property
    def gib(self) -> float:
        return self.bytes / GIB


@dataclass(frozen=True)
class HardwareProfile:
    """What to run on a machine of this class, and why."""

    id: str
    label: str
    vram_upper_gib: Optional[int]
    context_tokens: int
    context_note: str
    reason: str
    candidates: Tuple[CandidateModel, ...] = ()
    requires_artifact_check: bool = False
    caveats: Tuple[str, ...] = ()


COMMON_CAVEATS = (
    SIZE_SOURCE,
    "Context/KV state, compute buffers and backend overhead are extra.",
    "The active parameters of an MoE model are not its resident weight memory.",
    "Bigger is not automatically better or faster for this task.",
    "Model quality for this music workflow is not measured yet (B01).",
)

QWEN_35 = "bartowski/Qwen_Qwen3.5-9B-GGUF"
QWEN_35_REV = "182be2fd6c7bc44887d88a91cb03ff009cc9f549"
GEMMA_12 = "google/gemma-4-12B-it-qat-q4_0-gguf"
GEMMA_12_REV = "29d097773436b69ff9feafd636ab4cf873786537"
QWEN_38 = "unsloth/Qwen3.8-27B-GGUF"
QWEN_38_REV = "4ca720788d1e01f1bff70c033e0d0028fd02e502"

QWEN_9B_Q4KM = CandidateModel(
    name="Qwen_Qwen3.5-9B-Q4_K_M.gguf",
    family="Qwen 3.5 9B",
    quantization="Q4_K_M",
    bytes=6169341984,
    repo_id=QWEN_35,
    revision=QWEN_35_REV,
    filename="Qwen_Qwen3.5-9B-Q4_K_M.gguf",
    note="Only after an actual budget check against the free VRAM, not by default.",
)
QWEN_9B_Q5KM = CandidateModel(
    name="Qwen_Qwen3.5-9B-Q5_K_M.gguf",
    family="Qwen 3.5 9B",
    quantization="Q5_K_M",
    bytes=7111487520,
    repo_id=QWEN_35,
    revision=QWEN_35_REV,
    filename="Qwen_Qwen3.5-9B-Q5_K_M.gguf",
)
QWEN_9B_Q6K = CandidateModel(
    name="Qwen_Qwen3.5-9B-Q6_K.gguf",
    family="Qwen 3.5 9B",
    quantization="Q6_K",
    bytes=7958818848,
    repo_id=QWEN_35,
    revision=QWEN_35_REV,
    filename="Qwen_Qwen3.5-9B-Q6_K.gguf",
)
GEMMA_12_QAT = CandidateModel(
    name="gemma-4-12b-it-qat-q4_0.gguf",
    family="Gemma 4 12B QAT",
    quantization="Q4_0 (QAT)",
    bytes=6975879296,
    repo_id=GEMMA_12,
    revision=GEMMA_12_REV,
    filename="gemma-4-12b-it-qat-q4_0.gguf",
    note="The repository's projector file is not needed for the text workflow.",
)
QWEN_27B_IQ3XXS = CandidateModel(
    name="Qwen3.8-27B-UD-IQ3_XXS.gguf",
    family="Qwen 3.8 27B (MoE)",
    quantization="UD-IQ3_XXS",
    bytes=10934860704,
    repo_id=QWEN_38,
    revision=QWEN_38_REV,
    filename="Qwen3.8-27B-UD-IQ3_XXS.gguf",
    note="Quality comparison; its active parameters do not describe its resident size.",
)
QWEN_27B_IQ4XS = CandidateModel(
    name="Qwen3.8-27B-UD-IQ4_XS.gguf",
    family="Qwen 3.8 27B (MoE)",
    quantization="UD-IQ4_XS",
    bytes=14252845984,
    repo_id=QWEN_38,
    revision=QWEN_38_REV,
    filename="Qwen3.8-27B-UD-IQ4_XS.gguf",
)
QWEN_27B_Q4KM = CandidateModel(
    name="Qwen3.8-27B-UD-Q4_K_M.gguf",
    family="Qwen 3.8 27B (MoE)",
    quantization="UD-Q4_K_M",
    bytes=16464440224,
    repo_id=QWEN_38,
    revision=QWEN_38_REV,
    filename="Qwen3.8-27B-UD-Q4_K_M.gguf",
)

PROFILES: Tuple[HardwareProfile, ...] = (
    HardwareProfile(
        id="cpu_only",
        label="CPU only",
        vram_upper_gib=None,
        context_tokens=4096,
        context_note="Short context and a compact prompt; the prompt budget is not the model limit.",
        reason=(
            "No accelerated device: a small (2-4B) model is the right class, and a large model must not be "
            "pushed onto the CPU by default."
        ),
        candidates=(),
        requires_artifact_check=True,
        caveats=COMMON_CAVEATS,
    ),
    HardwareProfile(
        id="vram_8",
        label="Up to 8 GiB VRAM",
        vram_upper_gib=8,
        context_tokens=4096,
        context_note="4-8k context for the new compact prompts; full GPU offload only if the budget check passes.",
        reason=(
            "A small 4B class is preferred. The 9B Q4_K_M anchor below is only an option after the free VRAM "
            "was actually checked against it."
        ),
        candidates=(QWEN_9B_Q4KM,),
        requires_artifact_check=True,
        caveats=COMMON_CAVEATS,
    ),
    HardwareProfile(
        id="vram_12",
        label="10-12 GiB VRAM",
        vram_upper_gib=12,
        context_tokens=8192,
        context_note="8k as a test start; let actual headroom and the backend decide.",
        reason="The 9B Q5_K_M or the Gemma 4 12B QAT fit this class comfortably at a moderate context.",
        candidates=(QWEN_9B_Q5KM, GEMMA_12_QAT),
        caveats=COMMON_CAVEATS,
    ),
    HardwareProfile(
        id="vram_16",
        label="16 GiB VRAM",
        vram_upper_gib=16,
        context_tokens=16384,
        context_note="Use 8-16k according to the actual input length, not the model maximum.",
        reason=(
            "Gemma 4 12B QAT or Qwen 3.5 9B Q6_K as everyday candidates; the 27B UD-IQ3_XXS is a quality "
            "comparison, not the default."
        ),
        candidates=(GEMMA_12_QAT, QWEN_9B_Q6K, QWEN_27B_IQ3XXS),
        caveats=COMMON_CAVEATS,
    ),
    HardwareProfile(
        id="vram_24",
        label="24 GiB VRAM",
        vram_upper_gib=24,
        context_tokens=16384,
        context_note="More quantization quality; a large context only when the input actually needs it.",
        reason="27B quantizations with more precision become viable here.",
        candidates=(QWEN_27B_IQ3XXS, QWEN_27B_IQ4XS),
        caveats=COMMON_CAVEATS,
    ),
    HardwareProfile(
        id="vram_32",
        label="32 GiB VRAM or more",
        vram_upper_gib=32,
        context_tokens=32768,
        context_note="Context by need; measure rather than reserve the model maximum.",
        reason=(
            "Larger quantizations, an explicit quality profile. On multiple GPUs, measure split operation "
            "against a single GPU instead of assuming a gain."
        ),
        candidates=(QWEN_27B_IQ4XS, QWEN_27B_Q4KM),
        caveats=COMMON_CAVEATS,
    ),
)


def profile_for_vram(total_vram_bytes: Optional[int]) -> HardwareProfile:
    """The profile for a device with this total VRAM (``None`` = CPU only)."""
    if not total_vram_bytes:
        return PROFILES[0]
    gib = total_vram_bytes / GIB
    for profile in PROFILES[1:]:
        if profile.vram_upper_gib is not None and gib <= profile.vram_upper_gib:
            return profile
    return PROFILES[-1]


def match_installed(
    candidates: Sequence[CandidateModel],
    installed: Iterable[str],
    sizes_by_name: Optional[Dict[str, Optional[int]]] = None,
) -> List[Dict[str, Any]]:
    """Match candidates against installed files without overclaiming.

    A name match alone is reported as ``name_match``; ``verified`` is only set
    when the installed file's size equals the anchored size, because a file name
    is not provenance.
    """
    installed_set = {os.path.basename(str(name)) for name in installed}
    sizes = {os.path.basename(str(k)): v for k, v in (sizes_by_name or {}).items()}
    matches: List[Dict[str, Any]] = []
    for candidate in candidates:
        if candidate.name not in installed_set:
            continue
        size = sizes.get(candidate.name)
        verified = size is not None and int(size) == int(candidate.bytes)
        matches.append(
            {
                "name": candidate.name,
                "bytes_installed": size,
                "bytes_expected": candidate.bytes,
                "verified": verified,
                "status": "installed" if verified else "name_match",
                "message": (
                    "installed and its size matches the anchored artifact"
                    if verified
                    else "a file with this name is installed, but its size does not match the anchor "
                    "(provenance not claimed)"
                ),
            }
        )
    return matches


def recommend_llm_setup(
    resources: Any = None,
    installed: Iterable[str] = (),
    sizes_by_name: Optional[Dict[str, Optional[int]]] = None,
) -> Dict[str, Any]:
    """Recommend a profile and its candidates for the detected hardware.

    ``resources`` is a ``resource_profiles.ResourceSnapshot`` (detected lazily
    when omitted).  The free budget is taken from the R01 helper, so an
    occupied GPU lowers the confidence instead of being ignored.
    """
    if resources is None:
        try:
            from . import resource_profiles

            resources = resource_profiles.detect_resources()
        except Exception:  # pragma: no cover - standalone use
            resources = None

    total_vram: Optional[int] = None
    free_vram: Optional[int] = None
    device_id = "cpu"
    if resources is not None:
        accelerators = getattr(resources, "accelerators", None) or []
        if accelerators:
            device = max(accelerators, key=lambda item: item.vram_total_bytes or 0)
            total_vram = device.vram_total_bytes
            free_vram = device.vram_free_bytes
            device_id = device.id

    profile = profile_for_vram(total_vram)
    budget = None
    if resources is not None and device_id != "cpu":
        try:
            from . import resource_profiles

            budget = resource_profiles.device_budget(resources, device_id)
        except Exception:  # pragma: no cover - standalone use
            budget = None

    confidence = "medium"
    reasons: List[str] = [profile.reason]
    if total_vram is None and device_id != "cpu":
        # An accelerator exists but its memory could not be read: stay with the
        # smallest GPU class instead of claiming "no accelerated device".
        profile = PROFILES[1]
        confidence = "missing"
        reasons = [
            "The device memory could not be read; using the smallest GPU class and no size promise.",
            profile.reason,
        ]
    elif total_vram is None:
        confidence = "missing"
        reasons.append("The device memory could not be read; the recommendation stays conservative.")
    elif free_vram is None:
        confidence = "low"
        reasons.append("Free device memory is unknown; check the budget before loading a candidate.")
    elif budget is not None and budget <= 0:
        confidence = "low"
        reasons.append("The device has less free memory than the reserve; free memory or pick another device.")
    elif budget is not None and budget < min((c.bytes for c in profile.candidates), default=0):
        confidence = "low"
        reasons.append(
            "The free budget is below every candidate anchor for this class; a smaller model or a lower "
            "context is the honest choice."
        )

    installed_matches = match_installed(profile.candidates, installed, sizes_by_name)
    installed_names = {entry["name"] for entry in installed_matches}
    to_consider = [candidate for candidate in profile.candidates if candidate.name not in installed_names]
    # A machine with more than one accelerator always gets the pool warning,
    # whatever the profile is - the GPUs are not one contiguous memory pool.
    caveats = list(profile.caveats)
    if resources is not None and len(getattr(resources, "accelerators", []) or []) > 1:
        caveats.append("Several GPUs are separate memory pools; a split is not one big pool.")
    return {
        "profile": profile.id,
        "label": profile.label,
        "confidence": confidence,
        "reason": " ".join(reasons),
        "device": device_id,
        "free_budget_bytes": budget,
        "context_tokens": profile.context_tokens,
        "context_note": profile.context_note,
        "requires_artifact_check": profile.requires_artifact_check,
        "installed": installed_matches,
        "candidates": [
            {
                "name": candidate.name,
                "family": candidate.family,
                "quantization": candidate.quantization,
                "bytes": candidate.bytes,
                "gib": round(candidate.gib, 2),
                "repo_id": candidate.repo_id,
                "revision": candidate.revision,
                "filename": candidate.filename,
                "note": candidate.note,
            }
            for candidate in to_consider
        ],
        "caveats": caveats,
    }


def format_llm_profile_lines(recommendation: Dict[str, Any]) -> List[str]:
    """Readable lines for the node UI, the log and the docs."""
    lines = [
        f"LLM profile: {recommendation.get('label')} ({recommendation.get('confidence')} confidence)",
        f"  {recommendation.get('reason')}",
        f"  suggested context: {recommendation.get('context_tokens')} tokens - {recommendation.get('context_note')}",
    ]
    if recommendation.get("requires_artifact_check"):
        lines.append(
            "  no verified small-model artifact yet: check a concrete GGUF (file size, backend support) "
            "before recommending it."
        )
    for entry in recommendation.get("installed") or []:
        lines.append(f"  installed: {entry['name']} - {entry['message']}")
    for candidate in recommendation.get("candidates") or []:
        lines.append(
            f"  candidate: {candidate['name']} ({candidate['family']}, {candidate['quantization']}, "
            f"{candidate['gib']} GiB file)"
        )
    return lines


def installed_llm_files() -> Tuple[List[str], Dict[str, Optional[int]]]:
    """Names and sizes of the GGUFs the LLM node would offer (no weights read)."""
    try:
        from . import llm_chat
    except Exception:  # pragma: no cover - standalone use
        return [], {}
    names: List[str] = []
    sizes: Dict[str, Optional[int]] = {}
    for directory in llm_chat._llm_search_directories():
        if not Path(directory).is_dir():
            continue
        for path in sorted(Path(directory).glob("*.gguf")):
            if path.name in sizes:
                continue
            names.append(path.name)
            try:
                sizes[path.name] = path.stat().st_size
            except OSError:  # pragma: no cover - race with a delete
                sizes[path.name] = None
    return names, sizes
