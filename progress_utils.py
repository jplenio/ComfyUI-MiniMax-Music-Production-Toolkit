"""ComfyUI progress-bar helper that degrades gracefully outside ComfyUI.

Inside ComfyUI this returns the standard ``comfy.utils.ProgressBar`` (the blue
bar rendered inside the node).  Outside ComfyUI (unit tests, scripts) it
returns a silent no-op with the same two methods, so toolkit code can use the
progress bar unconditionally.
"""
from __future__ import annotations

from typing import Any

try:
    from comfy.utils import ProgressBar as _ComfyProgressBar  # type: ignore
except Exception:  # pragma: no cover - outside ComfyUI
    _ComfyProgressBar = None


def make_progress_bar(total: int) -> Any:
    """Return a ComfyUI ``ProgressBar`` for ``total`` steps, or a silent no-op."""
    if _ComfyProgressBar is not None:
        return _ComfyProgressBar(int(total))

    class _NoopProgress:
        def update(self, amount: int = 1) -> None:
            pass

        def update_absolute(self, value: int) -> None:
            pass

    return _NoopProgress()
