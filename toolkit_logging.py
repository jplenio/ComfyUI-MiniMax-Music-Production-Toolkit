"""Logging helpers for Music Production Toolkit.

The package deliberately uses Python logging instead of configuring ComfyUI's
root logger.  Users can raise or lower the package verbosity with the
``MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL`` environment variable.

Every line this package emits carries the local wall-clock time, so a ComfyUI log
can be read as a timeline: when a run started, how long a stage took and which
result belongs to which attempt.  That is done with a record filter rather than a
formatter, because ComfyUI owns the handler that prints these lines - adding a
second handler would print every message twice, and replacing the root formatter
would change every other node's output as well.
"""
from __future__ import annotations

import logging
import os
import time

LOGGER_NAME = "minimax_music_toolkit"
_DEFAULT_LEVEL = "INFO"
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


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


class _TimestampFilter(logging.Filter):
    """Prefix every toolkit record with the local time it was created.

    It is attached to each logger this module hands out, not only to the parent:
    a logger's filters run for records logged *on that logger*, never for records
    that merely propagate up from its children.  The marker keeps a record from
    being stamped twice if it passes more than one of these filters.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging's API
        if not getattr(record, "_minimax_timestamped", False):
            try:
                stamp = time.strftime(_TIMESTAMP_FORMAT)
            except (ValueError, OSError):  # pragma: no cover - defensive
                stamp = ""
            if stamp:
                record.msg = f"{stamp} {record.msg}"
            record._minimax_timestamped = True
        return True


_TIMESTAMP_FILTER = _TimestampFilter()


def get_logger(component: str | None = None) -> logging.Logger:
    """Return the toolkit logger (or a child logger) without adding handlers."""
    logger = _base_logger if not component else _base_logger.getChild(component)
    if not getattr(logger, "_minimax_timestamp_filter", False):
        logger.addFilter(_TIMESTAMP_FILTER)
        logger._minimax_timestamp_filter = True
    return logger
