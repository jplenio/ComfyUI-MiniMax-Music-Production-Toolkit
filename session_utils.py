"""Small dependency-free helpers for external LLM session nodes."""
from __future__ import annotations


class MiniMaxLLMSessionId:
    """Create a changing session ID from a ComfyUI seed widget.

    Setting ``control_after_generate`` to Randomize in the UI makes the external
    LLM node receive a different input on every queue run, preventing ComfyUI's
    output cache from reusing an old LLM response when the musical prompt itself
    is unchanged.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": (
                    "INT",
                    {
                        "default": 1,
                        "min": 0,
                        "max": 0x7FFFFFFFFFFFFFFE,
                        "step": 1,
                        "control_after_generate": True,
                    },
                ),
                "prefix": ("STRING", {"default": "song_", "multiline": False}),
            }
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("session_id", "seed")
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/utilities"

    def build(self, seed, prefix):
        value = int(seed)
        return (f"{prefix or ''}{value}", value)


NODE_CLASS_MAPPINGS = {"MiniMaxLLMSessionId": MiniMaxLLMSessionId}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxLLMSessionId": "LLM Session ID / Cache Buster"}
