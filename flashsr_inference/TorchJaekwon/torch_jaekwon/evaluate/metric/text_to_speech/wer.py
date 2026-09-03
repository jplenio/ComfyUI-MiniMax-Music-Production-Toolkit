"""Intelligibility metric: WER of ASR(generated audio) vs a reference text.

Reproduces the F5-TTS / Seed-TTS objective-WER protocol for English *exactly*
(see ``ref/F5-TTS/src/f5_tts/eval/utils_eval.py::run_asr_wer``): ASR is
``faster-whisper`` (``large-v3`` by default, ``beam_size=5``); both hypothesis
and reference have all punctuation (``zhon.hanzi`` CJK + ASCII ``string.punctuation``)
**deleted** (not spaced, so ``it's -> its``), double spaces collapsed, and are
lowercased, then scored with ``jiwer.process_words(...).wer``. Whisper weights
auto-download from HF on first use. WER only (no CER), to match F5.

``language`` is configurable (default ``"en"``) so the same metric works for
non-English TTS; pass ``language=None`` to let whisper auto-detect.
"""

from __future__ import annotations

import os
import string
from typing import TYPE_CHECKING, Optional

try: import jiwer
except ImportError: print("Warning: jiwer is not installed")
try: from zhon.hanzi import punctuation as _ZH_PUNCT
except ImportError: _ZH_PUNCT = ""; print("Warning: zhon is not installed; CJK punctuation will not be stripped")
import torch

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

# CJK (zhon) + ASCII punctuation, deleted (mapped to None) so contractions/hyphenations collapse identically (it's -> its, well-known -> wellknown).
_DELETE_PUNCT: dict = {ord(c): None for c in _ZH_PUNCT + string.punctuation}


def normalize_text(text: str) -> str:
    text = (text or "").translate(_DELETE_PUNCT)
    return text.replace("  ", " ").lower()


class WordErrorRate:
    def __init__(
        self,
        model_name: str = "large-v3",
        language: str = "en",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        compute_type: str = "float16",
    ) -> None:
        self.model_name: str = model_name
        self.language: str = language
        self.device: str = device
        self.compute_type: str = compute_type
        self._asr: Optional["WhisperModel"] = None  # lazy

    @property
    def asr(self):
        if self._asr is None:
            from faster_whisper import WhisperModel

            self._asr = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        return self._asr

    def transcribe(self, audio_path: str) -> str:
        segments, _ = self.asr.transcribe(audio_path, beam_size=5, language=self.language)
        return "".join(" " + seg.text for seg in segments)

    def __call__(self, audio_path: str, reference_text: str) -> dict:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found for WER: {audio_path}")
        hyp: str = normalize_text(self.transcribe(audio_path))
        ref: str = normalize_text(reference_text)
        if not ref:
            raise ValueError(f"Empty reference text for WER (got {reference_text!r})")
        # Error counts come along so a caller can aggregate a CORPUS WER
        # (total errors / total reference words) instead of averaging per-utterance
        # rates, which lets a 5-word clip outweigh a 500-word one.
        output = jiwer.process_words(ref, hyp)
        return {
            "wer": float(output.wer),
            "asr_text": hyp,
            "num_reference_words": output.substitutions + output.deletions + output.hits,
            "num_word_errors": output.substitutions + output.deletions + output.insertions,
        }
