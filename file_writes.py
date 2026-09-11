"""Small same-directory staging/publication primitives.

ComfyUI savers write their final artifact, then add tags/covers/sidecars to it.
A failure in any of those later steps used to leave a partial or untagged file
at the *final* path, where it looked like a finished release and could be
picked up as an existing file by the next auto-increment run.

:class:`staged_write` writes into a unique same-directory staging file and only
moves it onto the final path once the whole operation succeeded.  The staging
name keeps the target's extension, so extension-based writers (SoundFile,
FFmpeg, Pillow, Mutagen) still infer the right format.

This is deliberately a single-file primitive.  A filesystem offers no
multi-file atomicity, so companion files (sidecars, prompt-report Markdown) are
published by the caller in a documented order instead of pretending otherwise.
"""
from __future__ import annotations

import itertools
import os
from typing import Callable, Optional

from .output_paths import pick_path

_STAGING_COUNTER = itertools.count()


def _staging_path(target: str) -> str:
    """Return an unused same-directory staging path that keeps ``target``'s extension."""
    directory, name = os.path.split(os.path.abspath(target))
    stem, ext = os.path.splitext(name)
    for _ in range(1_000_000):
        candidate = os.path.join(directory, f"{stem}.part-{os.getpid()}-{next(_STAGING_COUNTER):04d}{ext}")
        if not os.path.exists(candidate):
            return candidate
    raise RuntimeError(f"Could not find a free staging name for {target!r}.")


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


class staged_write:
    """Context manager that stages one output file and publishes it atomically.

    Usage::

        with staged_write(target, reserve=lambda: reserve_target(prefix, "flac", mode)) as staged:
            sf.write(staged.staging, data, rate, format="FLAC", subtype=subtype)
            write_tags(staged.staging)
        final_path = staged.target

    On success the staging file is moved onto the (possibly re-reserved) final
    path with :func:`os.replace`.  On any exception the staging file is removed
    and the final path is never touched.
    """

    def __init__(
        self,
        target: str,
        *,
        create_dirs: bool = False,
        reserve: Optional[Callable[[], str]] = None,
        error_prefix: str = "Output",
    ):
        self.target = target
        self.staging = ""
        self._create_dirs = create_dirs
        self._reserve = reserve
        self._error_prefix = error_prefix

    def __enter__(self) -> "staged_write":
        directory = os.path.dirname(os.path.abspath(self.target))
        if self._create_dirs:
            os.makedirs(directory, exist_ok=True)
        self.staging = _staging_path(self.target)
        return self

    def publish(self) -> str:
        """Reserve the final name (if a policy was given) and move into place."""
        if self._reserve is not None:
            self.target = self._reserve()
        os.replace(self.staging, self.target)
        return self.target

    def discard(self) -> None:
        if self.staging:
            _remove_quietly(self.staging)

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.discard()
            return False
        try:
            self.publish()
        except BaseException:
            self.discard()
            raise
        return False


def reserve_target(
    prefix: str,
    ext: str,
    collision_mode: str,
    *,
    error_prefix: str = "Output",
    exists: Optional[Callable[[str], bool]] = None,
) -> str:
    """Re-check the collision policy immediately before publication.

    The name was picked before the (potentially slow) write, so another
    producer may have taken it in the meantime.  ``auto_increment`` moves to
    the next free name, ``error_if_exists`` fails loudly and ``overwrite``
    keeps the requested path.
    """
    if collision_mode == "overwrite":
        return f"{prefix}.{ext}"
    return pick_path(prefix, ext, collision_mode, error_prefix=error_prefix, exists=exists)


def write_text_staged(
    target: str,
    payload: str,
    *,
    create_dirs: bool = False,
    reserve: Optional[Callable[[], str]] = None,
    error_prefix: str = "Output",
) -> str:
    """Publish *payload* to *target* through a staging file.  Returns the path."""
    with staged_write(target, create_dirs=create_dirs, reserve=reserve, error_prefix=error_prefix) as staged:
        with open(staged.staging, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    return staged.target
