"""FFmpeg discovery, process execution and MP3 encoding shared by the savers.

The three consumers (the two audio savers and the release-prep node) each grew
their own copy of executable discovery, hidden-window subprocess setup, MP3
quality mapping and temporary-WAV cleanup.  They differ in ways that are
**contracts**, not accidents, so this module keeps them as parameters:

* the FFmpeg-not-found message and the process-failure message text,
* whether ``-map_metadata -1`` is emitted (only the absolute saver strips
  pre-existing metadata; the smart saver writes its own ID3 tags afterwards),
* the temporary-interchange policy (a FLOAT WAV, cleaned up in ``finally``).

This module imports nothing from the toolkit and nothing beyond the standard
library, so the diagnostics script can use it without a ComfyUI environment.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any, List, Optional, Sequence, Tuple


def discover_ffmpeg() -> Optional[str]:
    """Return an FFmpeg executable path, or ``None`` when none is available.

    Prefers the user's/system FFmpeg and falls back to the executable bundled
    by ``imageio-ffmpeg`` (installed by ``install_requirements.bat``), which is
    what makes MP3 output work on machines without FFmpeg on ``PATH``.
    """
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    return None


def find_ffmpeg(not_found_message: str) -> str:
    """Like :func:`discover_ffmpeg`, but raise *not_found_message* when absent."""
    exe = discover_ffmpeg()
    if not exe:
        raise RuntimeError(not_found_message)
    return exe


def run_ffmpeg(
    cmd: Sequence[str],
    *,
    failure_message: str,
    tail: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """Run one FFmpeg command without a console window and check its exit code.

    ``failure_message`` is the caller's message text (it already ends with a
    colon); ``tail`` limits how much stderr is included (``None`` = all of it,
    stripped), preserving each caller's historic reporting.
    """
    kwargs = {}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.run(
        list(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() if tail is None else proc.stderr[-tail:]
        raise RuntimeError(f"{failure_message}\n{detail}")
    return proc


def interleaved_f32le_blocks(data_tc: Any, block_frames: int = 1 << 20):
    """Yield raw little-endian f32le blocks of a ``[C, T]`` float32 array.

    The layout is the interleaved, time-major one FFmpeg expects for
    ``-f f32le``: frame 0's channels, then frame 1's, and so on.  Blocks are
    bounded, so a five-minute track is never converted to one huge ``bytes``
    object (that copy alone would be another full-size allocation).
    """
    import numpy as np

    array = np.asarray(data_tc, dtype=np.float32)
    if array.ndim == 1:
        array = array[None, :]
    if array.ndim != 2:
        raise ValueError(f"expected a [C, T] array, got shape {array.shape}")
    frames = int(array.shape[1])
    step = max(1, int(block_frames))
    for start in range(0, frames, step):
        end = min(frames, start + step)
        # ``.T`` gives (frames, channels); a C-contiguous copy of that block is
        # exactly the interleaved byte order FFmpeg reads from the pipe.
        yield np.ascontiguousarray(array[:, start:end].T).tobytes()


def run_ffmpeg_with_pcm(
    cmd: Sequence[str],
    data_tc: Any,
    sample_rate: int,
    *,
    block_frames: int = 1 << 20,
    timeout: Optional[float] = 1800.0,
    failure_message: str,
    tail: Optional[int] = None,
    stderr_limit: int = 2 * 1024 * 1024,
) -> subprocess.CompletedProcess:
    """Run FFmpeg with raw f32le PCM on stdin, without a temporary file.

    ``cmd`` must read from ``pipe:0`` with the matching ``-f f32le -ar <sr>
    -ac <ch>`` input options.  The data is written in bounded blocks, and stdout
    and stderr are drained **concurrently** with a bounded buffer - a chatty
    filter such as ``loudnorm`` would otherwise fill the pipe and deadlock.
    The process timeout, the console-less Windows behaviour and the historic
    failure message (with its optional stderr tail) are preserved.
    """
    import threading

    kwargs = {}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        list(cmd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,
    )
    collected: dict = {"stdout": [], "stderr": []}

    def drain(stream, key):
        total = 0
        try:
            for chunk in iter(lambda: stream.read(65536), b""):
                if total < stderr_limit:
                    collected[key].append(chunk)
                    total += len(chunk)
        except Exception:  # pragma: no cover - stream closed under us
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    threads = [
        threading.Thread(target=drain, args=(proc.stdout, "stdout"), daemon=True),
        threading.Thread(target=drain, args=(proc.stderr, "stderr"), daemon=True),
    ]
    for thread in threads:
        thread.start()

    write_error: Optional[BaseException] = None
    try:
        for block in interleaved_f32le_blocks(data_tc, block_frames):
            proc.stdin.write(block)
        proc.stdin.close()
    except BrokenPipeError as exc:  # FFmpeg died early; the stderr says why
        write_error = exc
        try:
            proc.stdin.close()
        except Exception:
            pass
    except Exception as exc:  # pragma: no cover - defensive
        write_error = exc
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass

    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise RuntimeError(f"{failure_message}\nFFmpeg timed out after {timeout} s.")
    finally:
        for thread in threads:
            thread.join(timeout=5)

    stdout_text = b"".join(collected["stdout"]).decode("utf-8", "replace")
    stderr_text = b"".join(collected["stderr"]).decode("utf-8", "replace")
    if returncode != 0 or write_error is not None:
        detail = stderr_text.strip() if tail is None else stderr_text[-tail:]
        if write_error is not None and returncode == 0:  # pragma: no cover - defensive
            detail = f"{detail}\nPCM write failed: {type(write_error).__name__}: {write_error}"
        raise RuntimeError(f"{failure_message}\n{detail}")
    return subprocess.CompletedProcess(list(cmd), returncode, stdout_text, stderr_text)


def mp3_quality_args(quality: str) -> List[str]:
    """Map a quality label to libmp3lame arguments (empty list when unknown)."""
    if quality == "V0 (~245 kbps)":
        return ["-q:a", "0"]
    if quality == "V2 (~190 kbps)":
        return ["-q:a", "2"]
    if quality in ("192 kbps", "256 kbps", "320 kbps"):
        return ["-b:a", quality.split()[0] + "k"]
    return []


def _soundfile():
    try:
        import soundfile

        return soundfile
    except Exception:
        return None


def write_mp3(
    target: str,
    data_tc: Any,
    sample_rate: int,
    quality: str,
    *,
    not_found_message: str,
    failure_message: str,
    invalid_quality_message: str,
    strip_metadata: bool = False,
    soundfile_missing_message: Optional[str] = None,
) -> None:
    """Encode ``data_tc`` (channels x frames) to MP3 at *target*.

    The intermediate WAV is written as 32-bit float so no avoidable 16-bit
    conversion is introduced, and it is always removed, even on failure.
    """
    sf = _soundfile()
    if sf is None:
        raise RuntimeError(
            soundfile_missing_message or "MP3 output requires soundfile."
        )

    quality_args = mp3_quality_args(quality)
    if not quality_args:
        raise ValueError(invalid_quality_message)

    ffmpeg = find_ffmpeg(not_found_message)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = tmp.name
        sf.write(temp_path, data_tc, sample_rate, format="WAV", subtype="FLOAT")

        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", temp_path]
        if strip_metadata:
            cmd += ["-map_metadata", "-1"]
        cmd += ["-codec:a", "libmp3lame", *quality_args, "-id3v2_version", "3", target]
        run_ffmpeg(cmd, failure_message=failure_message)
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def prepare_samples(
    samples: Any,
    peak_handling: str,
    *,
    unknown_peak_message: str,
) -> Tuple[Any, float, float]:
    """Apply the shared peak policy and return ``(samples, peak, gain)``.

    ``normalize_only_if_clipping`` deliberately leaves signals below full scale
    untouched and only attenuates a genuinely clipping signal; it is not a
    normalizer and must never be replaced by one.
    """
    import numpy as np

    samples = np.asarray(samples, dtype=np.float32)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    gain = 1.0

    if peak_handling == "normalize_only_if_clipping":
        if peak > 1.0:
            gain = 0.999 / peak
            samples = samples * np.float32(gain)
    elif peak_handling == "leave_unchanged":
        pass
    else:
        raise ValueError(unknown_peak_message.format(peak_handling=peak_handling))

    return samples, peak, gain
