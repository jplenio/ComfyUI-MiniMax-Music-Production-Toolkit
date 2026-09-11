"""Logging helpers for MiniMax Music Production Toolkit.

The package deliberately uses Python logging instead of configuring ComfyUI's
root logger.  Users can raise or lower the package verbosity with the
``MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL`` environment variable.
"""
from __future__ import annotations

import logging
import os

LOGGER_NAME = "minimax_music_toolkit"
_DEFAULT_LEVEL = "INFO"


def _level_from_env() -> int:
    """Resolve the package log level from the environment, safely.

    Only real integer level constants (or a numeric string) are accepted.
    ``getattr(logging, raw)`` also matches non-level attributes such as
    ``BASIC_FORMAT``; passing one of those to ``setLevel`` raised at import time
    and took the whole package import down with it.
    """
    raw = os.getenv("MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL", _DEFAULT_LEVEL).strip().upper()
    if not raw:
        return logging.INFO
    if raw.isdigit():
        value = int(raw)
        if 0 <= value <= logging.CRITICAL + 10:
            return value
        logging.getLogger(LOGGER_NAME).warning(
            "Ignoring out-of-range MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL=%s; using %s.", raw, _DEFAULT_LEVEL
        )
        return logging.INFO
    candidate = getattr(logging, raw, None)
    if isinstance(candidate, int) and not isinstance(candidate, bool):
        return candidate
    logging.getLogger(LOGGER_NAME).warning(
        "Ignoring unknown MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL=%s; using %s.", raw, _DEFAULT_LEVEL
    )
    return logging.INFO


_base_logger = logging.getLogger(LOGGER_NAME)
_base_logger.setLevel(_level_from_env())


def get_logger(component: str | None = None) -> logging.Logger:
    """Return the toolkit logger (or a child logger) without adding handlers."""
    if not component:
        return _base_logger
    return _base_logger.getChild(component)
