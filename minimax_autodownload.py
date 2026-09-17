"""Model auto-download / presence check node.

``MiniMaxModelAutodownload`` verifies the model files referenced by the
bundled workflow before the generation stages run.  Files with a configured
download URL are fetched automatically when missing (with progress logging);
files without a URL are reported with guidance instead.  The run continues
afterwards; only download failures with auto_download enabled raise an error.

The node is the *deliberately triggered* setup action (D04): the same
inventory/space report is available as
``model_downloader.preflight_models()`` for scripts and HTTP routes, and it is
never executed at import time or inside ``INPUT_TYPES()``.
"""
from __future__ import annotations

import json

from .model_downloader import (
    format_check_report,
    format_preflight_report,
    load_models_config,
    normalize_model_entries,
    preflight_models,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("autodownload")


def wants_original_lyrics(profile, cover_source_json="") -> bool:
    """Whether this run needs the optional Whisper checkpoint at all.

    YuE2 covers with new or original lyrics need source-word transcription.  An
    unreadable or unconnected source is not a request, so the 3 GB checkpoint
    is never pulled in because a widget happened to default to true.
    """
    if profile is None or not profile.is_cover:
        return False
    from .cover_score import LYRICS_MODE_ORIGINAL, normalize_lyrics_mode
    from .music_cover import cover_source

    try:
        source = cover_source(cover_source_json)
    except ValueError:
        return False
    return normalize_lyrics_mode(source.get("lyrics_mode")) in {LYRICS_MODE_ORIGINAL, "new lyrics"}


class MiniMaxModelAutodownload:
    """Check and optionally download the models used by the example workflow."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "minimax_models": ("BOOLEAN", {"default": True}),
                "flux2_models": ("BOOLEAN", {"default": True}),
                "flashsr_models": ("BOOLEAN", {"default": True}),
                "llm_model": ("BOOLEAN", {"default": True}),
                "auto_download": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "yue2_models": ("BOOLEAN", {"default": True}),
                "model_profile_json": ("STRING", {"forceInput": True}),
                "sheetsage2_models": ("BOOLEAN", {"default": True}),
                # Optional lyrics transcription for YuE2 covers; appended so a
                # saved workflow's positional widget values keep their meaning.
                "whisper_models": ("BOOLEAN", {"default": True}),
                # The cover source carries the lyrics mode, so the check node
                # asks for Whisper only when 'original lyrics' is selected.
                "cover_source_json": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report",)
    FUNCTION = "check"
    CATEGORY = "MiniMax Music Production Toolkit/utilities"

    def check(self, minimax_models=True, flux2_models=True, flashsr_models=True, llm_model=True, auto_download=True,
              yue2_models=None, model_profile_json="", sheetsage2_models=True, whisper_models=True,
              cover_source_json=""):
        from .model_profiles import profile_from_payload
        profile = profile_from_payload(model_profile_json)
        # Old API/workflow calls omit the additive flag and must not download
        # a new 7.8 GB engine. With a YuE2 profile, omission follows its default.
        if yue2_models is None:
            yue2_models = profile is not None and profile.is_yue2
        # Group notes and the FlashSR default target live in one place
        # (model_downloader.normalize_model_entries) so this node, the FlashSR
        # runtime and the diagnostics script resolve identical entries.
        entries = normalize_model_entries(
            load_models_config(),
            minimax=bool(minimax_models) and (profile is None or not profile.is_yue2),
            yue2=bool(yue2_models) and (profile is None or profile.is_yue2),
            sheetsage2=bool(sheetsage2_models) and bool(yue2_models) and profile is not None and profile.is_cover,
            flux2=bool(flux2_models),
            flashsr=bool(flashsr_models),
            llm=bool(llm_model),
            # Whisper is only ever needed for one combination: a YuE2 cover
            # whose lyrics mode asks for original words or source phrasing.
            whisper=bool(whisper_models) and wants_original_lyrics(profile, cover_source_json),
        )

        # The preflight is the inventory/space report; it downloads only because
        # the node's own auto_download widget asks for it.  Only the selected
        # branches are in ``entries``, and optional artifacts (the int8 DiT) are
        # never pulled in implicitly.
        preflight = preflight_models(entries, base_path=None, auto_download=bool(auto_download))
        text = format_check_report(preflight["entries"])
        for line in format_preflight_report(preflight):
            LOGGER.info("%s", line)

        failed = [item for item in preflight["entries"] if item["status"] == "failed"]
        if failed and auto_download:
            raise RuntimeError(
                "Model auto-download failed for: "
                + ", ".join(f"{item['name']} ({item['message']})" for item in failed)
            )
        # The single STRING output stays exactly as before (workflow compatible);
        # the structured report is offered through the node's UI payload so a
        # frontend can show counts, missing bytes and space without parsing text.
        return {
            "ui": {
                "text": (text,),
                "preflight_json": (json.dumps(preflight, ensure_ascii=False),),
            },
            "result": (text,),
        }


NODE_CLASS_MAPPINGS = {
    "MiniMaxModelAutodownload": MiniMaxModelAutodownload,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxModelAutodownload": "Model Auto-Download / Check",
}
