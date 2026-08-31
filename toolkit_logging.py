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
    raw = os.getenv("MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL", _DEFAULT_LEVEL).strip().upper()
    return getattr(logging, raw, logging.INFO)


_base_logger = logging.getLogger(LOGGER_NAME)
_base_logger.setLevel(_level_from_env())


def get_logger(component: str | None = None) -> logging.Logger:
    """Return the toolkit logger (or a child logger) without adding handlers."""
    if not component:
        return _base_logger
    return _base_logger.getChild(component)
