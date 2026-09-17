"""Instrumental vocal check with a bounded regeneration loop (opt-in).

YuE2 can add vocal-like material to an instrumental cover even though the score
contains no vocal notes at all - that was verified against real production logs.
The only honest way to catch it is to listen, so this stage transcribes the
*raw* generated audio with the Whisper engine the toolkit already ships and
counts the words it hears. Hearing nothing is the pass.

Two nodes implement it. :class:`MiniMaxInstrumentalVocalCheck` transcribes one
candidate and passes its audio through; :class:`MiniMaxInstrumentalPick` owns the
decision and uses ComfyUI's lazy inputs to request only as many candidates as it
actually needs, so an acceptable first take never pays for the retries.

The check runs on the freshly decoded song, before refinement, equalisation,
mastering and release encoding: those change the sound but not whether someone
is singing, and re-running them for every attempt would only waste time.

Every candidate is written to a temporary WAV on the way to Whisper, so each
take exists as a file that can be auditioned later. When no take reaches the
word tolerance, the selection keeps the take with the *fewest* recognised words
- "least vocal" is the best take the run produced - and deletes the other
candidate files. The words Whisper heard are logged per take, because "humming
without words" and "the chorus came back" need different answers.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .toolkit_logging import get_logger
from .whisper_lyrics import DEFAULT_WHISPER_MODEL

LOGGER = get_logger("instrumental_check")

# 1 initial generation plus at most 10 retries.
MAX_RETRIES = 10
MAX_ATTEMPTS = MAX_RETRIES + 1

# Each attempt moves both seeds by this stride, so retries are different takes
# and a stored seed still reproduces the first one exactly.
RETRY_SEED_STRIDE = 1

CHECK_SCHEMA = "instrumental_vocal_check_v1"

# Candidate WAVs live here until the selection node removes the losers.
TEMP_ROOT_NAME = "mmt-instrumental-check"
# Leftovers from a run that was cancelled before its selection node ran.
STALE_RUN_HOURS = 24
# The log names what was heard; the report keeps the full transcript.
TRANSCRIPT_LOG_CHARS = 500


def _split_audio(audio: Any) -> Tuple[Any, int]:
    """``(waveform[B, C, T], sample_rate)`` for an AUDIO value, or a clear error."""
    if not isinstance(audio, dict) or "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError("Instrumental vocal check: the input is not a valid AUDIO value.")
    waveform = audio["waveform"]
    if waveform.dim() == 2:
        waveform = waveform.unsqueeze(0)
    if waveform.dim() != 3:
        raise ValueError(
            f"Instrumental vocal check: unexpected audio shape {tuple(waveform.shape)}; expected [B, C, T].")
    return waveform, int(audio["sample_rate"])


def write_candidate_wav(audio: Any, directory: str, name: str = "candidate.wav") -> Path:
    """Write the first batch element to a temporary WAV for the Whisper engine."""
    import soundfile as sf

    waveform, rate = _split_audio(audio)
    path = Path(directory) / name
    samples = waveform[0].detach().to("cpu").transpose(0, 1).numpy()
    sf.write(str(path), samples, rate, format="WAV", subtype="PCM_16")
    return path


def candidate_root() -> Path:
    """Directory all candidate WAVs live in until the selection node decides."""
    root = Path(tempfile.gettempdir()) / TEMP_ROOT_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def prune_stale_runs(root: Optional[Path] = None, hours: int = STALE_RUN_HOURS) -> int:
    """Remove candidate directories older than ``hours``.

    A run that is cancelled, or a standalone check node with no selection node
    behind it, would otherwise leave its WAVs behind forever.
    """
    cutoff = time.time() - max(1, int(hours)) * 3600
    removed = 0
    for entry in (root or candidate_root()).iterdir():
        try:
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


def store_candidate(audio: Any, label: str = "") -> Path:
    """Write one candidate to its own temporary directory and return the path.

    The file outlives the check so the take can be auditioned; the selection node
    deletes every candidate except the one it keeps.
    """
    root = candidate_root()
    prune_stale_runs(root)
    name = (re.sub(r"[^A-Za-z0-9._-]+", "-", str(label or "")).strip("-.") or "take")
    directory = Path(tempfile.mkdtemp(prefix=f"{name}-", dir=root))
    return write_candidate_wav(audio, str(directory))


def count_words(text: str) -> int:
    """Words Whisper heard. Nothing heard means zero and therefore a pass."""
    return len(re.findall(r"\S+", str(text or "")))


def _flatten(text: str) -> str:
    return " ".join(str(text or "").split())


def _log_transcript(label: str, transcript: str, words: int) -> None:
    """Log what Whisper heard - the only way to tell humming from singing."""
    flat = _flatten(transcript)
    if not words:
        LOGGER.info("Instrumental vocal check %s: Whisper heard no words.", label)
        return
    shown = flat if len(flat) <= TRANSCRIPT_LOG_CHARS else flat[:TRANSCRIPT_LOG_CHARS] + "…"
    suffix = "" if len(flat) <= TRANSCRIPT_LOG_CHARS else f" ({len(flat)} characters in total)"
    LOGGER.info("Instrumental vocal check %s: Whisper heard %d words: %s%s",
                label, words, shown, suffix)


def check_instrumental(
    audio: Any,
    *,
    word_tolerance: int = 0,
    model: str = DEFAULT_WHISPER_MODEL,
    language: str = "auto",
    device: str = "auto",
    compute_type: str = "auto",
    beam_size: int = 1,
    label: str = "",
) -> Dict[str, Any]:
    """Transcribe one candidate and decide whether it counts as instrumental.

    ``word_tolerance`` is a count of spoken/sung **words** (not letters). 0 - the
    default - means the render must contain no recognisable words at all. A
    higher value tolerates a stray syllable without re-rendering the take.

    The candidate is written to a temporary WAV and every word Whisper heard is
    logged. The report carries the transcript and the file path, so the selection
    node can keep the least vocal take and delete the rest.
    """
    from . import whisper_lyrics

    tolerance = max(0, int(word_tolerance or 0))
    name = str(label or "take") or "take"
    path = store_candidate(audio, name)
    record = whisper_lyrics.transcribe(
        path,
        model=model,
        language=language,
        device=device,
        compute_type=compute_type,
        # VAD is tuned for speech and would clip sung fragments away; the
        # point here is to hear anything voice-like at all.
        vad_filter=False,
        beam_size=max(1, int(beam_size or 1)),
        condition_on_previous_text=False,
        allow_empty=True,
        purpose="Instrumental vocal check",
    )
    transcript = str(record.get("text") or "").strip()
    words = count_words(transcript)
    passed = words <= tolerance
    _log_transcript(name, transcript, words)
    LOGGER.info(
        "Instrumental vocal check %s: %d words (tolerance %d) -> %s",
        name, words, tolerance, "instrumental" if passed else "voice detected",
    )
    return {
        "schema": CHECK_SCHEMA,
        "passed": passed,
        "words": words,
        "word_tolerance": tolerance,
        "transcript": transcript,
        "candidate_label": name,
        "candidate_path": str(path),
        "model": record.get("model"),
        "device": record.get("device"),
        "compute_type": record.get("compute_type"),
        "language": record.get("language"),
        "language_probability": record.get("language_probability"),
        "duration_seconds": record.get("duration_seconds"),
        "segment_count": record.get("segment_count"),
        "attempts": record.get("attempts"),
    }


def _report_missing(value: Any) -> bool:
    """ComfyUI hands an unevaluated input as ``(None,)``."""
    return value is None or (isinstance(value, tuple) and len(value) == 1 and value[0] is None)


def _as_report(value: Any) -> Optional[Dict[str, Any]]:
    if _report_missing(value):
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        data = json.loads(value)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def choose_attempt(max_retries: int, reports: List[Optional[Dict[str, Any]]]) -> Tuple[int, bool]:
    """Index of the take to keep, and whether the retry budget was exhausted.

    A passing take wins immediately. When no take passes, the one with the
    **fewest recognised words** is kept: the checks have already measured how
    vocal each take is, and handing back whichever take happened to be last
    throws that measurement away. Ties keep the earliest take, so a stored seed
    still reproduces the same result.
    """
    limit = max(0, min(int(max_retries or 0), MAX_RETRIES))
    best_index: Optional[int] = None
    best_words = 0
    for index in range(limit + 1):
        report = reports[index] if index < len(reports) else None
        if not report:
            continue
        if report.get("passed"):
            return index, False
        words = report.get("words")
        # An unreadable count cannot win a comparison; it only fills the gap.
        words = int(words) if isinstance(words, (int, float)) else 10 ** 9
        # Strictly fewer words wins, so a tie keeps the earliest take.
        if best_index is None or words < best_words:
            best_index, best_words = index, words
    if best_index is None:
        return limit, True
    return best_index, True


def remove_unkept_candidates(reports: List[Optional[Dict[str, Any]]], keep: str = "") -> Tuple[List[str], List[str]]:
    """Delete every candidate file except the kept one; return (removed, failed)."""
    removed: List[str] = []
    failed: List[str] = []
    for report in reports:
        if not report:
            continue
        path = str(report.get("candidate_path") or "")
        if not path or (keep and os.path.normcase(path) == os.path.normcase(keep)):
            continue
        try:
            Path(path).unlink()
            try:
                Path(path).parent.rmdir()
            except OSError:
                pass  # another candidate still lives there, or the directory is busy
            removed.append(path)
        except OSError as exc:
            failed.append(path)
            LOGGER.warning("Instrumental vocal check: could not delete %s (%s).", path, exc)
    return removed, failed


class MiniMaxInstrumentalVocalCheck:
    """Transcribe one candidate; the audio is passed through unchanged."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "word_tolerance": ("INT", {"default": 0, "min": 0, "max": 50, "step": 1}),
            },
            "optional": {
                "whisper_model": ("STRING", {"default": DEFAULT_WHISPER_MODEL}),
                "language": ("STRING", {"default": "auto"}),
                "device": ("STRING", {"default": "auto"}),
                "compute_type": ("STRING", {"default": "auto"}),
                "beam_size": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
                "candidate_label": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "check_report_json")
    FUNCTION = "check"
    CATEGORY = "MiniMax Music Production Toolkit/generation"
    DESCRIPTION = (
        "Counts the words Whisper hears in one generated candidate and logs them. An instrumental passes "
        "when it hears none (or no more than the tolerance). The audio is passed through untouched, and the "
        "take is kept as a temporary WAV until the selection node deletes the ones it does not keep."
    )

    def check(self, audio, word_tolerance=0, whisper_model=DEFAULT_WHISPER_MODEL,
              language="auto", device="auto", compute_type="auto", beam_size=1,
              candidate_label=""):
        report = check_instrumental(
            audio, word_tolerance=word_tolerance, model=whisper_model, language=language,
            device=device, compute_type=compute_type, beam_size=beam_size,
            label=candidate_label)
        return (audio, json.dumps(report, ensure_ascii=False))


class MiniMaxInstrumentalPick:
    """Keep the least vocal candidate and delete the takes it rejects.

    Every candidate input is lazy, so ComfyUI builds and runs only the takes this
    node actually asks for. A clean first render therefore costs one generation,
    not eleven. When nothing reaches the tolerance, the take with the fewest
    recognised words is used and the other candidate files are removed.
    """

    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, Any] = {}
        for index in range(MAX_ATTEMPTS):
            optional[f"candidate_{index}"] = ("AUDIO", {"lazy": True})
            optional[f"report_{index}"] = ("STRING", {"lazy": True})
        return {
            "required": {
                "max_retries": ("INT", {"default": 2, "min": 0, "max": MAX_RETRIES, "step": 1}),
                "word_tolerance": ("INT", {"default": 0, "min": 0, "max": 50, "step": 1}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "check_report_json")
    FUNCTION = "pick"
    CATEGORY = "MiniMax Music Production Toolkit/generation"
    DESCRIPTION = (
        "Keeps the first instrumental candidate and asks ComfyUI for the next one only when the previous "
        "take contained words. If none reaches the tolerance, the take with the fewest words is used and "
        "the remaining candidate files are deleted."
    )

    def check_lazy_status(self, max_retries=2, word_tolerance=0, **kwargs):
        """Ask for candidates one at a time until one passes."""
        limit = max(0, min(int(max_retries or 0), MAX_RETRIES))
        for index in range(limit + 1):
            if _report_missing(kwargs.get(f"report_{index}")) or _report_missing(kwargs.get(f"candidate_{index}")):
                LOGGER.info("Instrumental vocal check: requesting candidate %d of %d.",
                            index + 1, limit + 1)
                return [f"candidate_{index}", f"report_{index}"]
            report = _as_report(kwargs.get(f"report_{index}"))
            if report and report.get("passed"):
                return []
        return []

    def pick(self, max_retries=2, word_tolerance=0, **kwargs):
        limit = max(0, min(int(max_retries or 0), MAX_RETRIES))
        reports = [_as_report(kwargs.get(f"report_{index}")) for index in range(limit + 1)]
        index, exhausted = choose_attempt(limit, reports)

        audio = kwargs.get(f"candidate_{index}")
        if _report_missing(audio):
            raise ValueError(
                "Instrumental vocal check: no candidate audio reached the selection node. "
                f"Connect candidate_{index} to its check node, or set max_retries lower.")

        kept = reports[index] or {}
        kept_path = str(kept.get("candidate_path") or "")
        removed, failed = remove_unkept_candidates(reports, keep=kept_path)
        if kept_path:
            LOGGER.info(
                "Instrumental vocal check: kept take %d of %d (%s words) at %s; "
                "deleted %d other candidate file(s)%s.",
                index + 1, limit + 1, kept.get("words"), kept_path, len(removed),
                f", {len(failed)} could not be removed" if failed else "",
            )
        summary = {
            "schema": "instrumental_vocal_check_summary_v1",
            "attempts_run": index + 1,
            "attempts_allowed": limit + 1,
            "max_retries": limit,
            "word_tolerance": max(0, int(word_tolerance or 0)),
            "kept_attempt": index + 1,
            "kept_words": kept.get("words"),
            "kept_candidate_path": kept_path,
            "kept_transcript": kept.get("transcript"),
            "removed_candidates": removed,
            "removal_failed": failed,
            "passed": bool(kept.get("passed")),
            "retry_budget_exhausted": exhausted,
            "selection": "first_pass" if kept.get("passed") else "fewest_words",
            "attempts": [dict(report, attempt=position + 1)
                         for position, report in enumerate(reports) if report],
        }
        if exhausted:
            words = summary["kept_words"]
            LOGGER.warning(
                "Instrumental vocal check: none of the %d attempts reached the tolerance (%d). "
                "Kept take %d with the fewest words (%s) and deleted the rest - listen to it, raise "
                "the tolerance, or try melody conditioning on the cover source.",
                summary["attempts_run"], summary["word_tolerance"], summary["kept_attempt"], words,
            )
            summary["note"] = (
                f"No attempt reached the tolerance ({summary['word_tolerance']} words). Kept take "
                f"{summary['kept_attempt']} with the fewest words; the other candidate files were deleted.")
        else:
            LOGGER.info("Instrumental vocal check: kept attempt %d of %d.",
                        summary["kept_attempt"], summary["attempts_allowed"])
        return (audio, json.dumps(summary, ensure_ascii=False))


NODE_CLASS_MAPPINGS = {
    "MiniMaxInstrumentalVocalCheck": MiniMaxInstrumentalVocalCheck,
    "MiniMaxInstrumentalPick": MiniMaxInstrumentalPick,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxInstrumentalVocalCheck": "Instrumental check · words heard",
    "MiniMaxInstrumentalPick": "Instrumental check · keep least vocal take",
}


__all__ = [
    "MAX_ATTEMPTS",
    "MAX_RETRIES",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "RETRY_SEED_STRIDE",
    "candidate_root",
    "check_instrumental",
    "choose_attempt",
    "count_words",
    "prune_stale_runs",
    "remove_unkept_candidates",
    "store_candidate",
]
