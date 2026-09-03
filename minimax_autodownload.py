"""Model auto-download / presence check node.

``MiniMaxModelAutodownload`` verifies the model files referenced by the
bundled workflow before the generation stages run.  Files with a configured
download URL are fetched automatically when missing (with progress logging);
files without a URL (gated MiniMax / FLUX.2 weights) are reported with
guidance instead.  The run continues afterwards; only download failures with
auto_download enabled raise an error.
"""
from __future__ import annotations

from .model_downloader import (
    check_file_entries,
    format_check_report,
    load_models_config,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("autodownload")


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
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report",)
    FUNCTION = "check"
    CATEGORY = "MiniMax Music Production Toolkit/utilities"

    def check(self, minimax_models=True, flux2_models=True, flashsr_models=True, llm_model=True, auto_download=True):
        config = load_models_config()
        entries = []

        if minimax_models:
            note = config.get("minimax", {}).get("note", "")
            for entry in config.get("minimax", {}).get("files", []):
                entries.append({**entry, "note": entry.get("note") or note})
        if flux2_models:
            note = config.get("flux2", {}).get("note", "")
            for entry in config.get("flux2", {}).get("files", []):
                entries.append({**entry, "note": entry.get("note") or note})
        if flashsr_models:
            weights = config.get("flashsr", {}).get("weights", {})
            default_target = weights.get("target", "models/audio/flashsr")
            for entry in weights.get("files", []):
                entries.append({**entry, "target": entry.get("target") or default_target})
        if llm_model:
            example = config.get("llm", {}).get("example", {})
            entries.append({**example, "note": example.get("note") or config.get("llm", {}).get("note", "")})

        report = check_file_entries(entries, base_path=None, auto_download=bool(auto_download))
        text = format_check_report(report)
        for line in text.splitlines():
            LOGGER.info("%s", line)

        failed = [item for item in report if item["status"] == "failed"]
        if failed and auto_download:
            raise RuntimeError(
                "Model auto-download failed for: "
                + ", ".join(f"{item['name']} ({item['message']})" for item in failed)
            )
        return (text,)


NODE_CLASS_MAPPINGS = {
    "MiniMaxModelAutodownload": MiniMaxModelAutodownload,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxModelAutodownload": "Model Auto-Download / Check",
}
