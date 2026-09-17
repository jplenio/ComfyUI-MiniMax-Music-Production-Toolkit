"""Shared test bootstrap: load the real package entry point outside ComfyUI.

The toolkit is a ComfyUI custom-node folder whose directory name is not a valid
Python package identifier, and ``__init__.py`` talks to the host (``server``,
``aiohttp``) only while registering HTTP routes.  Tests therefore load the real
``__init__.py`` as a synthetic package with a minimal fake host, which is much
closer to the real discovery path than importing individual submodules.

Importing this helper has no side effects; call :func:`load_entry_point` once
per test class.
"""
from __future__ import annotations

import importlib.util
import itertools
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "_toolkit_entry"
CONTRACT_FIXTURE = ROOT / "tests" / "fixtures" / "node_contracts.json"
_INSTANCES = itertools.count()

# Toolkit node identifier -> defining module (section 2 of docs/REFACTOR-PLAN.md).
NODE_OWNER = {
    "AudioArtifactReduction": "audio_artifact_reduction",
    "MusicCoverSource": "music_cover",
    "MusicCoverTranscription": "music_cover",
    "MusicCoverScore": "music_cover",
    "YuE2CoverStudioPlan": "cover_studio",
    "YuE2CoverStudioTransform": "cover_studio",
    "YuE2CoverStudioApply": "cover_studio",
    "MiniMaxInstrumentalVocalCheck": "instrumental_check",
    "MiniMaxInstrumentalPick": "instrumental_check",
    "MiniMaxAudioTagReader": "audio_tag_copy",
    "MiniMaxStyleHint": "style_hint",
    "MusicCoverLyrics": "whisper_lyrics",
    "MusicOptionalCoverPreview": "music_production_control",
    "MusicProductionControl": "music_production_control",
    "MusicOptionalStage": "music_production_control",
    "MusicGeneration": "music_generation",
    "MusicGenerationReceipt": "music_generation",
    "MiniMaxSafeAudioDecode": "audio_decode",
    "MiniMaxParametricEQ": "audio_eq",
    "MiniMaxAutoEQAnalyze": "audio_auto_eq",
    "MiniMaxMasteringCompressor": "audio_mastering",
    "AudioDeclipRepair": "audio_declip",
    "AudioReleasePrep": "audio_release_prep",
    "FlashSRHybridCrossover": "audio_hf_repair",
    "FlashSRLowpassLab": "audio_lowpass",
    "FlashSRProcessingSettings": "minimax_settings",
    "HFCymbalShimmerRepair": "audio_hf_repair",
    "KSamplerWithConfig": "ksampler_config",
    "MiniMaxFlashSRAudio": "flashsr_audio",
    "MiniMaxAudioBranchSelect": "minimax_audio_branch",
    "MiniMaxLLMChat": "llm_chat",
    "MiniMaxLLMSessionId": "session_utils",
    "MiniMaxLLMTemplateV16": "minimax_prompt_source",
    "MiniMaxLLMUnload": "llm_chat",
    "MiniMaxMetadataLoader": "minimax_metadata",
    "MiniMaxModelAutodownload": "minimax_autodownload",
    "MiniMaxMusic3GenerationSettings": "minimax_settings",
    "MiniMaxMusicModelSettings": "minimax_settings",
    "MiniMaxMusicModelProfile": "minimax_model_profile",
    "MiniMaxOutputPaths": "minimax_batch",
    "MiniMaxParseExternalLLMOutputV16": "minimax_prompt_source",
    "MiniMaxPromptBatchLoader": "minimax_batch",
    "MiniMaxPromptReport": "minimax_prompt_report",
    "MiniMaxPromptSourceArtworkV16": "minimax_prompt_source",
    "MiniMaxSaveProductionJSON": "minimax_json_output",
    "MiniMaxSongMetadata": "minimax_metadata",
    "MiniMaxSquareImageSize": "minimax_artwork",
    "MiniMaxStandardAudioTags": "minimax_audio_tags",
    "MiniMaxStructuredPromptV20": "minimax_structured_prompt",
    "SaveAudioAbsolutePath": "save_audio_absolute",
    "SaveAudioSmartPrefix": "save_audio_smart_prefix",
    "SaveImageSmartPrefix": "minimax_artwork",
    "MiniMaxCoverControl": "minimax_artwork",
}

# At least these routes must be registered; the assertions are additive, so a new
# surface may add routes without rewriting this list.
EXPECTED_ROUTES = (
    ("GET", "/minimax_music_toolkit/prompt_files"),
    ("GET", "/minimax_music_toolkit/prompt_metadata"),
    ("POST", "/minimax_music_toolkit/save_prompt"),
    ("GET", "/minimax_music_toolkit/prompt_text"),
    ("POST", "/minimax_music_toolkit/save_system_prompt"),
    # The deliberately triggered model preflight (D04): GET reports, POST downloads.
    ("GET", "/minimax_music_toolkit/model_preflight"),
    ("POST", "/minimax_music_toolkit/model_preflight"),
    ("GET", "/minimax_music_toolkit/llm/providers"),
    ("POST", "/minimax_music_toolkit/llm/configure"),
)


class FakeHost:
    """Records the routes a fake PromptServer would receive."""

    def __init__(self):
        self.routes = []


def fake_host_modules(host: FakeHost | None = None):
    """Return minimal ``aiohttp``/``aiohttp.web``/``server`` stand-ins."""
    host = host or FakeHost()
    aiohttp = types.ModuleType("aiohttp")

    class _Response:
        def __init__(self, payload, status=200):
            self.payload = payload
            self.status = status

    def json_response(payload, status=200):
        return _Response(payload, status)

    web = types.ModuleType("aiohttp.web")
    web.json_response = json_response
    aiohttp.web = web

    class _RouteTable:
        def __init__(self, routes):
            self._routes = routes

        def _add(self, method, path):
            def decorator(handler):
                self._routes.append((method, path, handler))
                return handler

            return decorator

        def get(self, path):
            return self._add("GET", path)

        def post(self, path):
            return self._add("POST", path)

    class _PromptServer:
        instance = types.SimpleNamespace(routes=_RouteTable(host.routes))

    server = types.ModuleType("server")
    server.PromptServer = _PromptServer
    return host, {"aiohttp": aiohttp, "aiohttp.web": web, "server": server}


def load_entry_point(package_name: str | None = None, host: FakeHost | None = None):
    """Execute the real ``__init__.py`` as a package and return ``(package, host)``.

    Every call gets a unique synthetic package name, so test modules that each
    load the entry point stay fully isolated from one another (module-level
    state such as ``_ROUTES_REGISTERED`` is per instance).
    """
    host, modules = fake_host_modules(host)
    for name, module in modules.items():
        sys.modules[name] = module
    package_name = f"{package_name or PACKAGE_NAME}_{next(_INSTANCES)}"
    spec = importlib.util.spec_from_file_location(
        package_name,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, host


def normalize(value):
    if isinstance(value, dict):
        return {str(k): normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    return value


def _strip_tooltip(options):
    if isinstance(options, dict):
        return {k: normalize(v) for k, v in options.items() if k != "tooltip"}
    return normalize(options)


def _inputs(section):
    out = {}
    for name, spec in (section or {}).items():
        if isinstance(spec, tuple) and len(spec) == 2:
            out[name] = [normalize(spec[0]), _strip_tooltip(spec[1])]
        else:
            out[name] = normalize(spec)
    return out


def contract_for(cls):
    data = cls.INPUT_TYPES() if callable(getattr(cls, "INPUT_TYPES", None)) else {}
    data = data or {}
    return {
        "python_class": getattr(cls, "__name__", None),
        "category": getattr(cls, "CATEGORY", None),
        "function": getattr(cls, "FUNCTION", None),
        "output_node": bool(getattr(cls, "OUTPUT_NODE", False)),
        "output_is_list": list(getattr(cls, "OUTPUT_IS_LIST", []) or []),
        "input_is_list": bool(getattr(cls, "INPUT_IS_LIST", False)),
        "return_types": normalize(list(getattr(cls, "RETURN_TYPES", []) or [])),
        "return_names": list(getattr(cls, "RETURN_NAMES", []) or []),
        "required": _inputs(data.get("required")),
        "optional": _inputs(data.get("optional")),
        "hidden": _inputs(data.get("hidden")),
    }


def collect(package):
    return {node_type: contract_for(cls) for node_type, cls in package.NODE_CLASS_MAPPINGS.items()}
