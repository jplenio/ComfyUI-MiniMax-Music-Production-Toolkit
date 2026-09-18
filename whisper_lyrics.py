"""Timed source-lyrics transcription for YuE2 covers.

faster-whisper is optional and runs for new/original-lyrics covers only.
New mode uses the transcript as a phrasing reference; original mode preserves
its words. The pinned large-v3 CTranslate2 checkpoint is a practical default,
not a demonstrated singing-specific optimum. Soundfile/FFmpeg decode source
audio. Speech recognition can mishear singing or hallucinate on accompaniment.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .toolkit_logging import get_logger

LOGGER = get_logger("cover_lyrics")

WHISPER_SAMPLE_RATE = 16000

# On-disk directory names inside ``models/audio_encoders``.  The catalog in
# ``models_config.json`` writes the pinned ``whisper-large-v3`` folder, so the
# dropdown value, the download target and the loader never disagree.  The
# dropdown is derived from that catalog (see ``whisper_model_choices``), so it
# only ever offers a checkpoint the check node can actually obtain.
CATALOG_WHISPER_MODELS = ("whisper-large-v3",)
DEFAULT_WHISPER_MODEL = "whisper-large-v3"
# Kept as the historic name for callers/tests that import it.
WHISPER_MODELS = CATALOG_WHISPER_MODELS

DEVICE_CHOICES = ("auto", "cuda", "cpu")
COMPUTE_CHOICES = ("auto", "float16", "int8_float16", "int8", "float32")

# "auto" lets Whisper detect the language; forcing it improves accuracy and is
# the documented remedy for wrong-language or repeated output.
LANGUAGE_CHOICES = (
    "auto", "en", "de", "fr", "es", "it", "pt", "nl", "pl", "sv", "da", "no",
    "fi", "cs", "hu", "ro", "el", "ru", "uk", "tr", "ar", "he", "hi", "id",
    "th", "vi", "ja", "ko", "zh",
)

# faster-whisper's tokenizer accepts codes, while linked prompt fields and
# older saved workflows may supply display names such as "English".
_LANGUAGE_NAMES = dict(zip(LANGUAGE_CHOICES[1:], (
    'english', 'german', 'french', 'spanish', 'italian', 'portuguese', 'dutch',
    'polish', 'swedish', 'danish', 'norwegian', 'finnish', 'czech', 'hungarian',
    'romanian', 'greek', 'russian', 'ukrainian', 'turkish', 'arabic', 'hebrew',
    'hindi', 'indonesian', 'thai', 'vietnamese', 'japanese', 'korean', 'chinese',
)))
_LANGUAGE_ALIASES = {name: code for code, name in _LANGUAGE_NAMES.items()}
_LANGUAGE_ALIASES.update({'deutsch': 'de', 'englisch': 'en', 'français': 'fr',
                          'español': 'es', 'mandarin': 'zh', 'cantonese': 'yue'})
# Keep API/linked inputs open to every code supported by the inspected Whisper
# tokenizer, not just the short list offered in this node's dropdown.
_WHISPER_LANGUAGE_CODES = set('''af am ar as az ba be bg bn bo br bs ca cs cy da
de el en es et eu fa fi fo fr gl gu ha haw he hi hr ht hu hy id is it ja jw ka
kk km kn ko la lb ln lo lt lv mg mi mk ml mn mr ms mt my ne nl nn no oc pa pl
ps pt ro ru sa sd si sk sl sn so sq sr su sv sw ta te tg th tk tl tr tt uk ur
uz vi yi yo zh yue'''.split())

# The toolkit's own "this field is not set" choice. It reaches the language parameter
# whenever a graph links a structured field's output into this node - the language
# dropdown of *Song request · template & fields* is built from the same sentinel - or
# when a saved workflow kept the placeholder in the widget. It is not a typo, and
# refusing it aborts a run that could simply auto-detect: the toolkit shipped exactly
# this value on the Whisper node, and every original-lyrics cover died with
# "unsupported Whisper source language 'custom'". tests/test_whisper_language.py
# asserts that it stays identical to ``prompt_metadata.CUSTOM``.
_UNSET_LANGUAGE_VALUES = frozenset({'custom'})


def normalize_whisper_language(value) -> Optional[str]:
    """Validate before decoding/loading; never turn an unknown value into auto.

    One deliberate exception: the toolkit's own "not set" sentinel means auto-detect,
    because that is what it means in every other field of this toolkit. Any other
    unknown value still fails loudly rather than silently transcribing in the wrong
    language.
    """
    requested = str(value or '').strip().casefold()
    if requested in {'', 'auto', 'automatic', 'auto-detect', 'automatisch'}:
        return None
    if requested in _UNSET_LANGUAGE_VALUES:
        LOGGER.info(
            "Whisper source language %r means 'not set'; detecting the language instead.",
            value,
        )
        return None
    code = _LANGUAGE_ALIASES.get(requested, requested)
    if code not in _WHISPER_LANGUAGE_CODES:
        raise ValueError(
            f"YuE2 Cover: unsupported Whisper source language {value!r}. "
            "Choose auto or a language code such as en/de; English/German/Deutsch are also accepted. "
            "Use the language of the source audio, not the desired new lyrics."
        )
    return code

_MISSING_ENGINE_MESSAGE = (
    "YuE2 Cover: new/original lyrics need the optional Whisper engine 'faster-whisper', "
    "which is not installed in this ComfyUI environment. Install it with "
    "'pip install -r requirements-whisper.txt' (or 'pip install faster-whisper') in the same "
    "Python environment that runs ComfyUI, restart ComfyUI, and run the model check again. "
    "Select 'instrumental' to cover without any Whisper model."
)

# One loaded model at a time: a second checkpoint would otherwise keep several
# gigabytes of VRAM allocated for the rest of the session.
_MODEL_CACHE: Dict[Tuple[str, str, str], Any] = {}


def whisper_model_dir(model: str = DEFAULT_WHISPER_MODEL) -> Path:
    """Absolute folder of a Whisper checkpoint inside ComfyUI's models directory."""
    from .model_downloader import comfy_models_dir
    name = str(model or "").strip() or DEFAULT_WHISPER_MODEL
    return comfy_models_dir() / "audio_encoders" / name


def whisper_model_choices() -> List[str]:
    """Checkpoint folders the model catalog can provide.

    The list is derived from ``models_config.json``, so it is deterministic for
    a given repository state and always names something the check node can
    actually download - the dropdown never offers a model that nothing can
    obtain. A user who adds another CTranslate2 checkpoint to that catalog (its
    own target folder beside ``models/audio_encoders/...``) gets it here too.
    """
    names: List[str] = []
    try:
        from .model_downloader import load_models_config

        group = (load_models_config() or {}).get("whisper", {}) or {}
        for entry in group.get("files", []) or []:
            target = str((entry or {}).get("target") or group.get("target") or "")
            parts = [part for part in target.replace("\\", "/").split("/") if part]
            if len(parts) >= 3 and parts[0] == "models" and parts[-1] not in names:
                names.append(parts[-1])
    except Exception as exc:  # pragma: no cover - a broken catalog is not fatal here
        LOGGER.debug("Could not read the Whisper checkpoint catalog: %s", exc)
    for name in CATALOG_WHISPER_MODELS:
        if name not in names:
            names.append(name)
    return names


def _load_engine():
    """Check installation; load native code and weights only in a child process."""
    import importlib.util
    if importlib.util.find_spec('faster_whisper') is None:
        raise RuntimeError(_MISSING_ENGINE_MESSAGE)
    from .whisper_worker import IsolatedWhisperModel
    return IsolatedWhisperModel


def _decode_with_soundfile(path: Path) -> Optional[Tuple[Any, int]]:
    import numpy as np

    try:
        import soundfile as sf

        data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:
        LOGGER.debug("soundfile could not decode %s (%s); trying FFmpeg.", path.name, exc)
        return None
    if data.size == 0:
        return None
    return np.asarray(data.mean(axis=1), dtype=np.float32), int(rate)


def _decode_with_ffmpeg(path: Path, target_rate: int):
    """Decode any FFmpeg-readable file to mono float32 PCM at *target_rate*."""
    import numpy as np

    from .ffmpeg_utils import discover_ffmpeg

    exe = discover_ffmpeg()
    if not exe:
        raise RuntimeError(
            "YuE2 Cover: no FFmpeg and no soundfile decoder could read "
            f"'{path.name}'. Install FFmpeg or convert the file to WAV/FLAC."
        )
    cmd = [exe, "-v", "error", "-nostdin", "-i", str(path), "-vn",
           "-f", "f32le", "-ac", "1", "-ar", str(int(target_rate)), "pipe:1"]
    kwargs = {}
    import os
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()[-400:]
        raise RuntimeError(f"YuE2 Cover: FFmpeg could not decode '{path.name}': {detail}")
    return np.frombuffer(proc.stdout, dtype="<f4").astype("float32", copy=False)


def load_audio_mono(path, target_rate: int = WHISPER_SAMPLE_RATE):
    """Read *path* as mono float32 at *target_rate*, without a system FFmpeg need."""
    import numpy as np

    from .audio_utils import resample_kaiser_polyphase

    source = Path(path)
    if not source.is_file():
        raise ValueError(f"YuE2 Cover: audio file not found: {source.name}")
    decoded = _decode_with_soundfile(source)
    if decoded is None:
        return _decode_with_ffmpeg(source, target_rate)
    samples, rate = decoded
    if rate != int(target_rate):
        samples = resample_kaiser_polyphase(
            samples, rate, int(target_rate),
            missing_message="YuE2 Cover: SciPy is required to resample the source for Whisper.",
        )
    return np.asarray(samples, dtype=np.float32)


def _release_models() -> None:
    """Drop every cached checkpoint and hand the device memory back.

    The cover lyrics step runs *before* music generation in the bundled
    workflow, so a checkpoint left cached would compete with the 7.8 GB YuE2
    model for the same GPU.  Releasing it costs a few seconds on the next run
    and removes that risk entirely.
    """
    _MODEL_CACHE.clear()
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # pragma: no cover - torch is ComfyUI's, not ours
        pass


def _resolve_device(requested: str, compute: str) -> Tuple[str, str]:
    """Pick a device/compute pair, degrading from GPU to CPU instead of failing."""
    requested_device = str(requested or "auto").strip().lower()
    requested_compute = str(compute or "auto").strip().lower()
    if requested_device == "cpu":
        return "cpu", ("int8" if requested_compute == "auto" else requested_compute)
    if requested_device == "auto":
        if _CUDA_FAILURE:
            LOGGER.warning('Cover Whisper uses CPU after an earlier CUDA failure: %s', _CUDA_FAILURE)
            return "cpu", "int8"
        try:
            import torch

            if not torch.cuda.is_available():
                return "cpu", ("int8" if requested_compute == "auto" else requested_compute)
        except Exception:
            return "cpu", ("int8" if requested_compute == "auto" else requested_compute)
    return "cuda", ("float16" if requested_compute == "auto" else requested_compute)


def _get_model(model_dir: Path, device: str, compute_type: str):
    WhisperModel = _load_engine()
    key = (str(model_dir), device, compute_type)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    for stale_key in list(_MODEL_CACHE):
        if stale_key != key:
            _MODEL_CACHE.pop(stale_key, None)
    model = WhisperModel(str(model_dir), device=device, compute_type=compute_type)
    _MODEL_CACHE[key] = model
    return model


_CUDA_FAILURE = None


def transcribe(
    audio_path,
    *,
    model: str = DEFAULT_WHISPER_MODEL,
    language: str = "auto",
    device: str = "auto",
    compute_type: str = "auto",
    vad_filter: bool = False,
    beam_size: int = 5,
    condition_on_previous_text: bool = False,
    allow_empty: bool = False,
    purpose: str = "Cover lyrics",
) -> Dict[str, Any]:
    """Transcribe one cover source file and return the record plus its text.

    The record always states which checkpoint, device and precision actually ran
    and whether the language was detected or forced, so a stored result can be
    reproduced without guessing.

    ``allow_empty`` is for the instrumental vocal check, where hearing nothing is
    the result being looked for: an empty transcript is returned as a record
    instead of raising, and the short-fragment guard is skipped because the
    fragment is exactly what the caller wants to count.  ``purpose`` only names
    the run in the log.  Both default to the original behaviour.
    """
    global _CUDA_FAILURE
    from .whisper_worker import WhisperCancelled
    forced_language = normalize_whisper_language(language)
    model_dir = whisper_model_dir(model)
    if not model_dir.is_dir():
        raise RuntimeError(
            f"YuE2 Cover: Whisper checkpoint folder '{model_dir}' does not exist. Keep "
            "'whisper models' enabled in the model check node and run it once to download "
            f"the pinned {DEFAULT_WHISPER_MODEL} files, or add another CTranslate2 checkpoint "
            "to the whisper group in models_config.json so it appears in this list too."
        )

    samples = None
    device_name, compute_name = _resolve_device(device, compute_type)

    # Fail on a missing optional engine before decoding a long file: the message
    # is actionable, and decoding is the slow part.
    _load_engine()
    samples = load_audio_mono(audio_path)
    duration = float(len(samples)) / float(WHISPER_SAMPLE_RATE) if len(samples) else 0.0
    if duration <= 0.0:
        raise ValueError("YuE2 Cover: the source audio is empty, so no lyrics can be transcribed.")

    effective_vad = bool(vad_filter)
    attempts = []

    def _run(device_value: str, compute_value: str):
        whisper = _get_model(model_dir, device_value, compute_value)
        return whisper.transcribe(
            samples,
            language=forced_language,
            beam_size=max(1, int(beam_size)),
            vad_filter=effective_vad,
            condition_on_previous_text=bool(condition_on_previous_text),
            word_timestamps=True,
        )

    segments: List[Dict[str, Any]] = []
    lines: List[str] = []
    def _attempt():
        nonlocal device_name, compute_name
        global _CUDA_FAILURE
        try:
            iterator, info = _run(device_name, compute_name)
            result = list(iterator)  # Inference happens during iteration.
        except WhisperCancelled as exc:
            raise exc.__cause__ or exc
        except Exception as exc:
            if device_name == "cpu" or isinstance(exc, (ValueError, TypeError)):
                raise
            LOGGER.warning(
                "Whisper on %s/%s failed (%s); retrying on CPU with int8 precision.",
                device_name, compute_name, exc,
            )
            _CUDA_FAILURE = str(exc)
            _release_models()
            device_name, compute_name = "cpu", "int8"
            try:
                iterator, info = _run(device_name, compute_name)
                result = list(iterator)
            except WhisperCancelled as cancelled:
                raise cancelled.__cause__ or cancelled
        retained = getattr(info, 'duration_after_vad', None)
        attempts.append(dict(device=device_name, compute_type=compute_name, vad_filter=effective_vad,
                             segment_count=len(result), duration_after_vad_seconds=retained))
        return result, info

    try:
        segments_iter, info = _attempt()
        retained = getattr(info, 'duration_after_vad', None)
        if effective_vad and (not segments_iter or
                             (retained is not None and float(retained) / duration < 0.5)):
            LOGGER.warning('Whisper VAD discarded most of the song or returned no segments; '
                           'retrying the full audio with vad_filter=false.')
            effective_vad = False
            segments_iter, info = _attempt()

        for segment in segments_iter:
            text = str(getattr(segment, "text", "") or "").strip()
            if not text:
                continue
            segments.append({
                "start": round(float(getattr(segment, "start", 0.0)), 3),
                "end": round(float(getattr(segment, "end", 0.0)), 3),
                "text": text,
                "words": [{"word": str(word.word), "start": round(float(word.start), 3),
                           "end": round(float(word.end), 3)}
                          for word in (getattr(segment, 'words', None) or [])],
            })
            lines.append(text)
    finally:
        # Also on failure: a half-consumed generator, or a model that failed on
        # the GPU, must not keep its device memory for the music stage.
        _release_models()

    transcript = "\n".join(lines).strip()
    if not transcript and not allow_empty:
        raise ValueError('YuE2 Cover: Whisper returned no lyrics. Check the audio/language, '
                         'try vad_filter=false, or supply a reviewed transcript through cover_lyrics.')
    if (not allow_empty and duration >= 60 and len(transcript.split()) < 12
            and max(s['end'] for s in segments) < duration * 0.2):
        raise ValueError('YuE2 Cover: Whisper recognized only a short opening fragment of this song. '
                         'Generation stopped to avoid an almost wordless cover. Check the source language, '
                         'try a vocal-isolated transcription source, or connect a reviewed full transcript '
                         'to both cover_lyrics inputs (Structured Song Prompt and prompt parser).')
    record = {
        "schema": "music_cover_lyrics_v1",
        "source": "Whisper (faster-whisper)",
        "model": Path(str(model_dir)).name,
        "model_path": str(model_dir),
        "device": device_name,
        "compute_type": compute_name,
        "language": getattr(info, "language", None) or forced_language,
        "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 4),
        "language_forced": forced_language,
        "language_requested": str(language or 'auto'),
        "duration_seconds": round(float(getattr(info, "duration", duration) or duration), 3),
        "vad_filter": effective_vad,
        "vad_filter_requested": bool(vad_filter),
        "attempts": attempts,
        "execution": "isolated_worker",
        "beam_size": max(1, int(beam_size)),
        "condition_on_previous_text": bool(condition_on_previous_text),
        "segment_count": len(segments),
        "characters": len(transcript),
        "text": transcript,
        "segments": segments,
        "empty": not transcript,
    }
    retained = getattr(info, 'duration_after_vad', None)
    if bool(vad_filter) and attempts[0]['duration_after_vad_seconds'] is not None and duration > 0:
        retained = attempts[0]['duration_after_vad_seconds']
        retained = float(retained)
        record['duration_after_vad_seconds'] = round(retained, 3)
        record['vad_retained_fraction'] = round(retained / duration, 4)
        if not effective_vad:
            warning = ('Whisper VAD discarded most of the song or returned no segments. '
                       'Retried full audio with vad_filter=false; review the transcript for recognition errors.')
            record['warning'] = warning
            LOGGER.warning(warning)
    LOGGER.info(
        "%s transcribed: model=%s device=%s/%s language=%s segments=%d characters=%d",
        purpose, record["model"], device_name, compute_name, record["language"],
        len(segments), len(transcript),
    )
    return record


class MusicCoverLyrics:
    """Transcribe the original lyrics of the cover source with Whisper.

    Does nothing unless the song model is a YuE2 cover *and* the cover lyrics
    mode is new/original lyrics; instrumental and other models never load a
    checkpoint nor requires the optional engine.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model_profile_json": ("STRING", {"forceInput": True}),
            "cover_source_json": ("STRING", {"forceInput": True}),
            "model_check_report": ("STRING", {"forceInput": True}),
            "whisper_model": (whisper_model_choices(), {"default": DEFAULT_WHISPER_MODEL}),
            "language": (list(LANGUAGE_CHOICES), {"default": "auto"}),
            "device": (list(DEVICE_CHOICES), {"default": "auto"}),
            "compute_type": (list(COMPUTE_CHOICES), {"default": "auto"}),
            "vad_filter": ("BOOLEAN", {"default": False}),
            "beam_size": ("INT", {"default": 5, "min": 1, "max": 10, "step": 1}),
            "condition_on_previous_text": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("cover_lyrics", "lyrics_report_json")
    FUNCTION = "transcribe_lyrics"
    CATEGORY = "Music Production Toolkit/generation"
    DESCRIPTION = (
        "For YuE2 Cover with new/original lyrics: transcribe source words and timings as a "
        "phrasing reference for new lyrics or authoritative text for original lyrics. "
        "Other models and instrumental covers return an empty result without loading anything. "
        "Requires the optional faster-whisper engine and the downloaded checkpoint."
    )

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        # The node is reachable in every cover run and must never fail validation
        # for an engine required only in lyric-bearing cover modes.
        return True

    def transcribe_lyrics(self, model_profile_json, cover_source_json="", model_check_report="",
                          whisper_model=DEFAULT_WHISPER_MODEL, language="auto", device="auto",
                          compute_type="auto", vad_filter=False, beam_size=5,
                          condition_on_previous_text=False):
        from .cover_score import LYRICS_MODE_ORIGINAL, normalize_lyrics_mode
        from .model_profiles import profile_from_payload
        from .music_cover import cover_source

        profile = profile_from_payload(model_profile_json)
        if profile is None or not profile.is_cover:
            return ("", json.dumps({"status": "inactive", "reason": "not a YuE2 cover run"}))

        source = cover_source(cover_source_json)
        mode = normalize_lyrics_mode(source["lyrics_mode"])
        if mode not in {LYRICS_MODE_ORIGINAL, "new lyrics"}:
            return ("", json.dumps({
                "status": "not_requested", "lyrics_mode": mode,
                "reason": "the selected cover lyrics mode does not use Whisper",
            }, ensure_ascii=False))

        import folder_paths

        path = Path(folder_paths.get_annotated_filepath(source["audio"]))
        record = transcribe(
            path,
            model=whisper_model,
            language=language,
            device=device,
            compute_type=compute_type,
            vad_filter=bool(vad_filter),
            beam_size=int(beam_size),
            condition_on_previous_text=bool(condition_on_previous_text),
        )
        record["status"] = "transcribed"
        record["purpose"] = "original_words" if mode == LYRICS_MODE_ORIGINAL else "new_lyrics_phrasing_reference"
        record["source_filename"] = source["source_filename"]
        return (record["text"], json.dumps(record, ensure_ascii=False))


NODE_CLASS_MAPPINGS = {"MusicCoverLyrics": MusicCoverLyrics}
NODE_DISPLAY_NAME_MAPPINGS = {"MusicCoverLyrics": "Cover song · source lyrics / phrasing (Whisper)"}
