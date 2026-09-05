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


def format_progress_bar(done: int, total: int, width: int = 20) -> str:
    """Render an ASCII progress bar for the log, spanning 0 (left) to total (right).

    Example: ``[##########----------]  8192/16384``.  The bar mirrors the node's
    progress bar; the right-hand annotation shows ``done/total`` so the left end
    reads as 0 and the right end as the maximum (max_tokens, chunk count, ...).
    """
    total = max(1, int(total))
    done = max(0, min(int(done), total))
    filled = int(round(width * done / total))
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}]  {done}/{total}"
