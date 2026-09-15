"""Mastering starting points, shared with the browser via the JSON catalog."""
import json
from pathlib import Path

PRESETS = json.loads((Path(__file__).parent / "web" / "mastering_presets.json").read_text(encoding="utf-8"))
CUSTOM = "Custom"


def preset_settings(name):
    if name == CUSTOM:
        return None
    if name not in PRESETS:
        raise ValueError(f"Unknown mastering preset: {name}")
    return dict(PRESETS[name])
