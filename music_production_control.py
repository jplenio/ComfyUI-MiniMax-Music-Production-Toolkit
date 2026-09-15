"""Central production choices and lazy, report-aware audio stage switches."""
from __future__ import annotations

import json

from .minimax_model_profile import MiniMaxMusicModelProfile
from .model_profiles import display_names, get_profile


class MusicProductionControl(MiniMaxMusicModelProfile):
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": (list(display_names()), {"default": "YuE2"}),
            "cover_enabled": ("BOOLEAN", {"default": True}),
            "refinement": (["Model default", "On", "Off"], {"default": "Model default"}),
            "mastering_enabled": ("BOOLEAN", {"default": True}),
        }}

    RETURN_TYPES = MiniMaxMusicModelProfile.RETURN_TYPES + ("BOOLEAN",) * 3
    RETURN_NAMES = MiniMaxMusicModelProfile.RETURN_NAMES + (
        "cover_enabled", "refinement_enabled", "mastering_enabled",
    )
    DESCRIPTION = (
        "Choose the song model and production stages. Model default enables refinement for "
        "MiniMax and disables it for YuE2. On/Off override that choice. Cover and mastering "
        "are independent and enabled by default."
    )

    def build(self, model="YuE2", cover_enabled=True, refinement="Model default", mastering_enabled=True):
        if refinement not in ("Model default", "On", "Off"):
            raise ValueError(f"Unknown refinement choice: {refinement}")
        refined = (not get_profile(model).is_yue2) if refinement == "Model default" else refinement == "On"
        result = list(super().build(model))
        payload = json.loads(result[0])
        payload["production_stages"] = {
            "cover": bool(cover_enabled), "refinement": refined,
            "refinement_selection": refinement, "mastering": bool(mastering_enabled),
        }
        result[0] = json.dumps(payload, ensure_ascii=False)
        result[7] += f" | cover: {bool(cover_enabled)} | refinement: {refined} | mastering: {bool(mastering_enabled)}"
        return tuple(result) + (bool(cover_enabled), refined, bool(mastering_enabled))


class MusicOptionalStage:
    """Gate both audio and metadata so report consumers cannot awaken a skipped stage."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "enabled": ("BOOLEAN", {"forceInput": True}),
            "stage": (["Refinement", "Mastering"],),
            "original_audio": ("AUDIO", {"lazy": True}),
            "processed_audio": ("AUDIO", {"lazy": True}),
        }, "optional": {
            f"report_{i}": ("STRING", {"forceInput": True, "lazy": True, "default": ""})
            for i in range(1, 9)
        }}

    RETURN_TYPES = ("AUDIO",) + ("STRING",) * 8
    RETURN_NAMES = ("audio",) + tuple(f"report_{i}" for i in range(1, 9))
    FUNCTION = "select"
    CATEGORY = "MiniMax Music Production Toolkit/config"
    DESCRIPTION = (
        "Skip an entire audio stage including its report dependencies. Disabled stages "
        "pass the original audio through unchanged and report that processing was bypassed."
    )

    def check_lazy_status(self, enabled, stage, original_audio=None, processed_audio=None, **reports):
        if not enabled:
            return ["original_audio"] if original_audio is None else []
        needed = ["processed_audio"] if processed_audio is None else []
        return needed + [name for name, value in reports.items() if value is None]

    def select(self, enabled, stage, original_audio=None, processed_audio=None, **reports):
        if enabled:
            return (processed_audio,) + tuple(reports.get(f"report_{i}", "") for i in range(1, 9))
        bypass = json.dumps({"stage": stage.lower(), "enabled": False, "status": "bypassed"})
        values = [bypass] * 8
        if stage == "Refinement":
            values[1] = values[3] = "Bypassed"
        return (original_audio,) + tuple(values)


class MusicOptionalCoverPreview:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE", {"lazy": True}),
            "enabled": ("BOOLEAN", {"forceInput": True}),
        }}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "preview"
    OUTPUT_NODE = True
    CATEGORY = "MiniMax Music Production Toolkit/artwork"
    DESCRIPTION = "Preview cover artwork only when cover creation is enabled. Off also skips upstream rendering."

    def check_lazy_status(self, enabled, images=None):
        return ["images"] if enabled and images is None else []

    def preview(self, enabled, images=None):
        if not enabled:
            return {"ui": {"images": []}, "result": (None,)}
        from nodes import PreviewImage
        result = PreviewImage().save_images(images, filename_prefix="MusicToolkit")
        return {"ui": result.get("ui", {}), "result": (images,)}


NODE_CLASS_MAPPINGS = {
    "MusicProductionControl": MusicProductionControl,
    "MusicOptionalStage": MusicOptionalStage,
    "MusicOptionalCoverPreview": MusicOptionalCoverPreview,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MusicProductionControl": "Production choices · YuE2 / MiniMax",
    "MusicOptionalStage": "Optional audio stage · Audio + reports",
    "MusicOptionalCoverPreview": "Cover preview · follows production choice",
}
