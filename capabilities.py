"""What this installation can and cannot do, reported once when ComfyUI loads.

A fresh ComfyUI environment is the normal case for a new user, and a missing
package must never look like a broken toolkit. Every optional engine is detected
by name here and named in the log with the exact command that installs it, so the
one line a user needs is in the console before the first run instead of in a
traceback during it.

``requirements.txt`` installs everything that is needed for the documented
features; the entries marked *optional* below are either fully replaceable by a
fallback (``soxr``, ``psutil``) or add one engine on top of a working toolkit
(``llama_cpp``). The detection here is deliberately read-only: it never imports
the engine, so a broken native library cannot take the node package down with it.
"""
from __future__ import annotations

import importlib.util
from typing import List, NamedTuple, Tuple


class Capability(NamedTuple):
    module: str               # importable module name
    label: str                # what the user sees
    needed_for: str           # which feature stops working without it
    install: str              # the exact command that fixes it
    fallback: str             # what still works instead
    required: bool            # True = the toolkit is broken without it


CAPABILITIES: Tuple[Capability, ...] = (
    Capability(
        "numpy", "numpy", "all audio processing",
        "python -m pip install -r requirements.txt", "nothing", True,
    ),
    Capability(
        "scipy", "scipy", "de-clipping, filtering and EQ",
        "python -m pip install -r requirements.txt", "nothing", True,
    ),
    Capability(
        "soundfile", "soundfile", "reading and writing FLAC/WAV",
        "python -m pip install -r requirements.txt", "nothing", True,
    ),
    Capability(
        "PIL", "Pillow", "artwork saving and embedded cover art",
        "python -m pip install -r requirements.txt", "nothing", True,
    ),
    Capability(
        "mutagen", "mutagen", "audio tags and the source-tag reader",
        "python -m pip install -r requirements.txt", "no tags, no tag copy", True,
    ),
    Capability(
        "imageio_ffmpeg", "imageio-ffmpeg", "loudness measurement and MP3 export",
        "python -m pip install -r requirements.txt", "no LUFS report, no MP3", True,
    ),
    Capability(
        "faster_whisper", "faster-whisper (Whisper engine)",
        "cover lyrics mode 'original lyrics' and the instrumental vocal check",
        "python -m pip install -r requirements.txt",
        "the other cover modes and every non-cover path", False,
    ),
    Capability(
        "llama_cpp", "llama-cpp-python (integrated GGUF LLM)",
        "the LLM Chat mode 'In ComfyUI (GGUF)'",
        "python -m pip install llama-cpp-python   # or use 'Local app / server' or 'Cloud service'",
        "local-server and cloud LLM modes", False,
    ),
    Capability(
        "psutil", "psutil", "free-RAM figures in the resource report",
        "python -m pip install psutil", "a Windows-only RAM fallback, no VRAM figures", False,
    ),
    Capability(
        "soxr", "soxr", "high-quality resampling in the FlashSR chain",
        "python -m pip install soxr", "scipy polyphase resampling", False,
    ),
)


def is_available(module: str) -> bool:
    """True when *module* can be imported, without importing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):  # a broken parent package must not raise here
        return False


def missing_capabilities() -> Tuple[List[Capability], List[Capability]]:
    """``(missing_required, missing_optional)`` for this environment."""
    missing = [capability for capability in CAPABILITIES if not is_available(capability.module)]
    return ([c for c in missing if c.required], [c for c in missing if not c.required])


def capability_lines() -> List[str]:
    """Log lines describing this installation, one per problem and none when clean."""
    required, optional = missing_capabilities()
    lines: List[str] = []
    if required:
        lines.append(
            "Missing required dependency/dependencies: "
            + ", ".join(c.label for c in required)
            + ". The toolkit cannot run correctly. Install them with: "
            + required[0].install
        )
    for capability in optional:
        lines.append(
            f"Optional engine not installed: {capability.label}. Without it, "
            f"{capability.needed_for} is unavailable ({capability.fallback} still work). "
            f"Install with: {capability.install}"
        )
    if not lines:
        lines.append("All optional engines are installed; every feature is available.")
    return lines
