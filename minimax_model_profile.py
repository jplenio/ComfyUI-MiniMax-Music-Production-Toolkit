"""Song-model selection node (``MiniMaxMusicModelProfile``).

This node is the toolkit's first decision: *which* song-generation model a run
targets.  It does not generate anything itself - it publishes the selected
model's profile (prompt contract, token budget, duration window, recommended
sampler values, model files) so the prompt side, the settings side and the
canonical production JSON all describe the same model.

The selection is a plain dropdown of the bundled profiles, so adding a third
model is a data change in ``model_profiles.json`` plus a workflow that can run
it - not a code change here.
"""
from __future__ import annotations

import json

from .model_profiles import (
    PROFILE_SCHEMA,
    SongModelProfile,
    display_names,
    get_profile,
)
from .toolkit_logging import get_logger

LOGGER = get_logger("model_profile")


class MiniMaxMusicModelProfile:
    """Publish the selected song model's profile to the rest of the graph."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (list(display_names()), {"default": display_names()[0]}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = (
        "profile_json",
        "model_id",
        "model_name",
        "system_prompt_file",
        "prompt_token_budget",
        "max_duration",
        "duration_ceiling",
        "info",
    )
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/config"
    DESCRIPTION = (
        "Choose the song-generation model (MiniMax Music 3 or YuE2). Its profile drives the system-prompt "
        "family, the LLM prompt-token budget, the duration window and the recommended generation settings "
        "of every node that accepts this output."
    )

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        # The dropdown is data-driven; an unknown entry must not fail validation
        # before build() can explain the fallback in the log.
        return True

    def build(self, model):
        profile: SongModelProfile = get_profile(model)
        info = (
            f"{profile.display_name} | conditioning: [{profile.conditioning_section}] "
            f"({profile.conditioning_kind}) | prompt budget: {profile.prompt_token_budget} tokens "
            f"({'shared context' if profile.is_yue2 else 'hard limit'} {profile.prompt_token_hard_limit}) | duration: "
            f"default {profile.default_duration_seconds:g} s, ceiling {profile.duration_ceiling():g} s"
        )
        if profile.output_sample_rate:
            info += f" | {profile.output_sample_rate} Hz"
        if profile.documentation:
            info += f" | see {profile.documentation}"
        LOGGER.info("Song model: %s", info)
        LOGGER.debug("Selected song-model profile: %s", json.dumps(profile.as_payload(), ensure_ascii=False))
        return (
            json.dumps(profile.as_payload(), ensure_ascii=False),
            profile.id,
            profile.display_name,
            profile.system_prompt_file,
            int(profile.prompt_token_budget),
            float(profile.default_duration_seconds),
            float(profile.duration_ceiling()),
            info,
        )


NODE_CLASS_MAPPINGS = {
    "MiniMaxMusicModelProfile": MiniMaxMusicModelProfile,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxMusicModelProfile": "Song model · MiniMax Music 3 / YuE2",
}

__all__ = [
    "MiniMaxMusicModelProfile",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "PROFILE_SCHEMA",
]
