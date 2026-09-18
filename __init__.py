"""ComfyUI Music Production Toolkit.

The node class identifiers intentionally remain backwards-compatible with the
earlier workflow versions, while display names and documentation use the
public project naming introduced in 1.0.0.
"""
from __future__ import annotations

from .project_info import PROJECT_NAME, VERSION
from .toolkit_logging import get_logger

LOGGER = get_logger("startup")

# MiniMax Music 3 uses dynamic layer loading and can be affected by stale
# ComfyUI 0.35 compiler/CUDA-graph captures on some accelerator backends.
# The helper is deliberately opt-in, so installing the toolkit does not change
# the user's normal performance profile. It is also a no-op outside ComfyUI.
try:
    from .runtime_safety import configure_runtime
    configure_runtime()
except Exception:  # pragma: no cover - startup must remain resilient
    LOGGER.debug("Runtime safety configuration was unavailable", exc_info=True)

from .audio_lowpass import (
    NODE_CLASS_MAPPINGS as LOWPASS_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as LOWPASS_NODE_DISPLAY_NAME_MAPPINGS,
)
from .save_audio_absolute import (
    NODE_CLASS_MAPPINGS as SAVEABS_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as SAVEABS_NODE_DISPLAY_NAME_MAPPINGS,
)
from .save_audio_smart_prefix import (
    NODE_CLASS_MAPPINGS as SAVESMART_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as SAVESMART_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_batch import (
    NODE_CLASS_MAPPINGS as BATCH_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as BATCH_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_settings import (
    NODE_CLASS_MAPPINGS as SETTINGS_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as SETTINGS_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_model_profile import (
    NODE_CLASS_MAPPINGS as MODEL_PROFILE_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as MODEL_PROFILE_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_metadata import (
    NODE_CLASS_MAPPINGS as META_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as META_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_prompt_source import (
    NODE_CLASS_MAPPINGS as PROMPT_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as PROMPT_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_structured_prompt import (
    NODE_CLASS_MAPPINGS as STRUCTURED_PROMPT_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as STRUCTURED_PROMPT_NODE_DISPLAY_NAME_MAPPINGS,
)
from .ksampler_config import (
    NODE_CLASS_MAPPINGS as KSAMPLER_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as KSAMPLER_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_audio_tags import (
    NODE_CLASS_MAPPINGS as TAG_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as TAG_NODE_DISPLAY_NAME_MAPPINGS,
)
from .audio_declip import (
    NODE_CLASS_MAPPINGS as DECLIP_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as DECLIP_NODE_DISPLAY_NAME_MAPPINGS,
)
from .audio_hf_repair import (
    NODE_CLASS_MAPPINGS as HFREPAIR_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as HFREPAIR_NODE_DISPLAY_NAME_MAPPINGS,
)
from .audio_release_prep import (
    NODE_CLASS_MAPPINGS as RELEASE_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as RELEASE_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_artwork import (
    NODE_CLASS_MAPPINGS as ART_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as ART_NODE_DISPLAY_NAME_MAPPINGS,
)
from .session_utils import (
    NODE_CLASS_MAPPINGS as SESSION_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as SESSION_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_json_output import (
    NODE_CLASS_MAPPINGS as JSON_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as JSON_NODE_DISPLAY_NAME_MAPPINGS,
)
from .flashsr_audio import (
    NODE_CLASS_MAPPINGS as FLASHSR_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as FLASHSR_NODE_DISPLAY_NAME_MAPPINGS,
)
from .llm_chat import (
    NODE_CLASS_MAPPINGS as LLM_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as LLM_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_autodownload import (
    NODE_CLASS_MAPPINGS as AUTODOWNLOAD_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as AUTODOWNLOAD_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_prompt_report import (
    NODE_CLASS_MAPPINGS as PROMPT_REPORT_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as PROMPT_REPORT_NODE_DISPLAY_NAME_MAPPINGS,
)
from .minimax_audio_branch import (
    NODE_CLASS_MAPPINGS as AUDIO_BRANCH_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as AUDIO_BRANCH_NODE_DISPLAY_NAME_MAPPINGS,
)
# Instrumental vocal check (3.1.0): a bounded regeneration loop around the raw
# generation.  Both nodes are additive; the check only runs when it is switched
# on for an instrumental cover.
from .instrumental_check import (
    NODE_CLASS_MAPPINGS as INSTRUMENTAL_CHECK_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as INSTRUMENTAL_CHECK_NODE_DISPLAY_NAME_MAPPINGS,
)
# Source-tag reader (3.1.0): copies an existing file's metadata and cover art onto
# an enhanced export so both files look the same.
from .audio_tag_copy import (
    NODE_CLASS_MAPPINGS as TAG_COPY_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as TAG_COPY_NODE_DISPLAY_NAME_MAPPINGS,
)
# Style hint (3.1.0): the one place the Cover Studio can get the requested style
# from, without a dependency cycle - the master node is downstream of the studio.
from .style_hint import (
    NODE_CLASS_MAPPINGS as STYLE_HINT_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as STYLE_HINT_NODE_DISPLAY_NAME_MAPPINGS,
)
# YuE2 Cover Studio (3.1.0): a separate, additive cover path.  Importing it only
# adds three new node identifiers; it does not touch the existing cover, MiniMax
# or plain YuE2 nodes, and it exposes no import-time work beyond a couple of
# module-level constants.
from .cover_studio import (
    NODE_CLASS_MAPPINGS as COVER_STUDIO_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as COVER_STUDIO_NODE_DISPLAY_NAME_MAPPINGS,
)

NODE_CLASS_MAPPINGS = {
    **LOWPASS_NODE_CLASS_MAPPINGS,
    **SAVEABS_NODE_CLASS_MAPPINGS,
    **SAVESMART_NODE_CLASS_MAPPINGS,
    **BATCH_NODE_CLASS_MAPPINGS,
    **SETTINGS_NODE_CLASS_MAPPINGS,
    **MODEL_PROFILE_NODE_CLASS_MAPPINGS,
    **META_NODE_CLASS_MAPPINGS,
    **PROMPT_NODE_CLASS_MAPPINGS,
    **STRUCTURED_PROMPT_NODE_CLASS_MAPPINGS,
    **KSAMPLER_NODE_CLASS_MAPPINGS,
    **TAG_NODE_CLASS_MAPPINGS,
    **ART_NODE_CLASS_MAPPINGS,
    **RELEASE_NODE_CLASS_MAPPINGS,
    **HFREPAIR_NODE_CLASS_MAPPINGS,
    **DECLIP_NODE_CLASS_MAPPINGS,
    **SESSION_NODE_CLASS_MAPPINGS,
    **JSON_NODE_CLASS_MAPPINGS,
    **FLASHSR_NODE_CLASS_MAPPINGS,
    **LLM_NODE_CLASS_MAPPINGS,
    **AUTODOWNLOAD_NODE_CLASS_MAPPINGS,
    **PROMPT_REPORT_NODE_CLASS_MAPPINGS,
    **AUDIO_BRANCH_NODE_CLASS_MAPPINGS,
    **COVER_STUDIO_NODE_CLASS_MAPPINGS,
    **INSTRUMENTAL_CHECK_NODE_CLASS_MAPPINGS,
    **TAG_COPY_NODE_CLASS_MAPPINGS,
    **STYLE_HINT_NODE_CLASS_MAPPINGS,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **LOWPASS_NODE_DISPLAY_NAME_MAPPINGS,
    **SAVEABS_NODE_DISPLAY_NAME_MAPPINGS,
    **SAVESMART_NODE_DISPLAY_NAME_MAPPINGS,
    **BATCH_NODE_DISPLAY_NAME_MAPPINGS,
    **SETTINGS_NODE_DISPLAY_NAME_MAPPINGS,
    **MODEL_PROFILE_NODE_DISPLAY_NAME_MAPPINGS,
    **META_NODE_DISPLAY_NAME_MAPPINGS,
    **PROMPT_NODE_DISPLAY_NAME_MAPPINGS,
    **STRUCTURED_PROMPT_NODE_DISPLAY_NAME_MAPPINGS,
    **KSAMPLER_NODE_DISPLAY_NAME_MAPPINGS,
    **TAG_NODE_DISPLAY_NAME_MAPPINGS,
    **ART_NODE_DISPLAY_NAME_MAPPINGS,
    **RELEASE_NODE_DISPLAY_NAME_MAPPINGS,
    **HFREPAIR_NODE_DISPLAY_NAME_MAPPINGS,
    **DECLIP_NODE_DISPLAY_NAME_MAPPINGS,
    **SESSION_NODE_DISPLAY_NAME_MAPPINGS,
    **JSON_NODE_DISPLAY_NAME_MAPPINGS,
    **FLASHSR_NODE_DISPLAY_NAME_MAPPINGS,
    **LLM_NODE_DISPLAY_NAME_MAPPINGS,
    **AUTODOWNLOAD_NODE_DISPLAY_NAME_MAPPINGS,
    **PROMPT_REPORT_NODE_DISPLAY_NAME_MAPPINGS,
    **AUDIO_BRANCH_NODE_DISPLAY_NAME_MAPPINGS,
    **COVER_STUDIO_NODE_DISPLAY_NAME_MAPPINGS,
    **INSTRUMENTAL_CHECK_NODE_DISPLAY_NAME_MAPPINGS,
    **TAG_COPY_NODE_DISPLAY_NAME_MAPPINGS,
    **STYLE_HINT_NODE_DISPLAY_NAME_MAPPINGS,
}

from .audio_eq import MiniMaxParametricEQ
from .audio_auto_eq import MiniMaxAutoEQAnalyze
from .audio_mastering import MiniMaxMasteringCompressor
from .audio_decode import MiniMaxSafeAudioDecode

NODE_CLASS_MAPPINGS.update({
    "MiniMaxSafeAudioDecode": MiniMaxSafeAudioDecode,
    "MiniMaxParametricEQ": MiniMaxParametricEQ,
    "MiniMaxAutoEQAnalyze": MiniMaxAutoEQAnalyze,
    "MiniMaxMasteringCompressor": MiniMaxMasteringCompressor,
})
NODE_DISPLAY_NAME_MAPPINGS.update({
    "MiniMaxSafeAudioDecode": "MiniMax Safe Audio Decode",
    "MiniMaxParametricEQ": "Parametric EQ – 8 Bands",
    "MiniMaxAutoEQAnalyze": "Auto-EQ – Analyze / Propose",
    "MiniMaxMasteringCompressor": "Mastering Compressor – LUFS / True Peak",
})

from .music_generation import NODE_CLASS_MAPPINGS as MUSIC_NODES, NODE_DISPLAY_NAME_MAPPINGS as MUSIC_NAMES
NODE_CLASS_MAPPINGS.update(MUSIC_NODES)
NODE_DISPLAY_NAME_MAPPINGS.update(MUSIC_NAMES)

from .music_production_control import NODE_CLASS_MAPPINGS as PRODUCTION_NODES, NODE_DISPLAY_NAME_MAPPINGS as PRODUCTION_NAMES
NODE_CLASS_MAPPINGS.update(PRODUCTION_NODES)
NODE_DISPLAY_NAME_MAPPINGS.update(PRODUCTION_NAMES)

from .music_cover import NODE_CLASS_MAPPINGS as COVER_NODES, NODE_DISPLAY_NAME_MAPPINGS as COVER_NAMES
NODE_CLASS_MAPPINGS.update(COVER_NODES)
NODE_DISPLAY_NAME_MAPPINGS.update(COVER_NAMES)

from .whisper_lyrics import NODE_CLASS_MAPPINGS as COVER_LYRICS_NODES, NODE_DISPLAY_NAME_MAPPINGS as COVER_LYRICS_NAMES
NODE_CLASS_MAPPINGS.update(COVER_LYRICS_NODES)
NODE_DISPLAY_NAME_MAPPINGS.update(COVER_LYRICS_NAMES)

from .audio_artifact_reduction import NODE_CLASS_MAPPINGS as ARTIFACT_NODES, NODE_DISPLAY_NAME_MAPPINGS as ARTIFACT_NAMES
NODE_CLASS_MAPPINGS.update(ARTIFACT_NODES)
NODE_DISPLAY_NAME_MAPPINGS.update(ARTIFACT_NAMES)

from .ui_help import install_input_tooltips, merge_input_tooltips, NODE_INPUT_TOOLTIPS
from .audio_tools_help import AUDIO_TOOLTIPS
from .cover_studio import studio_input_tooltips as _cover_studio_tooltips
_COVER_STUDIO_TOOLTIPS = _cover_studio_tooltips()
merge_input_tooltips(AUDIO_TOOLTIPS,
                     {node: _COVER_STUDIO_TOOLTIPS
                      for node in ("YuE2CoverStudioPlan", "YuE2CoverStudioTransform", "YuE2CoverStudioApply")})
install_input_tooltips(NODE_CLASS_MAPPINGS)

# WEB_DIRECTORY must point to the directory containing both JavaScript files and
# docs/.  ComfyUI loads .js extensions and node documentation from this root.
WEB_DIRECTORY = "./web"

try:
    from .prompt_library import register_routes
    register_routes()
except Exception:  # pragma: no cover - keep node import alive if server API changes
    LOGGER.exception("Prompt-library route registration failed")

try:
    from .model_manager_routes import register_routes as register_model_manager_routes
    register_model_manager_routes()
except Exception:  # pragma: no cover - an optional surface must not break the nodes
    LOGGER.exception("Model-manager route registration failed")

LOGGER.info("Loaded %s %s (%d nodes)", PROJECT_NAME, VERSION, len(NODE_CLASS_MAPPINGS))

try:
    from .capabilities import capability_lines, missing_capabilities

    _missing_required, _missing_optional = missing_capabilities()
    for _line in capability_lines():
        LOGGER.info(_line)
    if _missing_required:
        LOGGER.warning(
            "Required dependencies are missing, so the toolkit will fail at run time. "
            "Install them into the ComfyUI Python environment with: "
            "python -m pip install -r requirements.txt"
        )
except Exception:  # pragma: no cover - a report must never break node loading
    LOGGER.exception("Could not report the installation's capabilities")

try:
    from .llm_provider_routes import register_routes as register_llm_provider_routes
    register_llm_provider_routes()
except Exception:
    LOGGER.exception("LLM-provider route registration failed")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
