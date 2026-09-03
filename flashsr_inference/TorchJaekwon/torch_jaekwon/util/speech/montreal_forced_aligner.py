"""Montreal Forced Aligner: word timestamps for a transcript we already have.

The audio gets one TextGrid beside a symlink of itself -- MFA's TextGrid corpus format is
already our shape, one interval per span, so nothing is sliced and the returned times are on
the source timeline. Docs:
https://montreal-forced-aligner.readthedocs.io/en/v3.4.0/user_guide/corpus_structure.html

MFA is a conda CLI (``conda create -n mfa -c conda-forge montreal-forced-aligner``, then
``mfa model download acoustic/dictionary english_mfa``), driven as a subprocess.

Span and word schema: ``{"start": sec, "end": sec, "text": str}``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

from praatio import textgrid
from praatio.data_classes.interval_tier import IntervalTier
from praatio.utilities.constants import Interval

from ..util_audio import get_duration

SPAN_TOLERANCE_S = 0.01  # a word may start a hair outside the span it belongs to


class MontrealForcedAligner:
    """Aligns spans by handing MFA one TextGrid per audio file.

    One file per call: MFA's per-call setup measured ~0 s against alignment itself, so
    parallelise over files by process. ``num_jobs`` splits ONE file across workers and gains
    nothing (26 s at 1 job, 41 s at 32).

    Alignment settings are all left at MFA's default.
    """

    def __init__(
        self,
        num_jobs: int = 3,  # MFA's own default (config.py NUM_JOBS)
        dictionary: str = "english_mfa",
        acoustic_model: str = "english_mfa",
        mfa_bin_dir: str | None = None,  # bin/ of the conda env holding mfa; None = already on PATH
        beam: int | None = None,  # only to retry a file mfa failed to align
    ) -> None:
        self.num_jobs = num_jobs
        self.dictionary = dictionary
        self.acoustic_model = acoustic_model
        self.mfa_bin = str(Path(mfa_bin_dir) / "mfa") if mfa_bin_dir else "mfa"
        # mfa shells out to kaldi/openfst by bare name, so its bin/ must be searchable too
        self.executable_search_path = os.pathsep.join(filter(None, [mfa_bin_dir, os.environ["PATH"]]))
        self.beam = beam

    def align(
        self,
        audio_path: str,
        spans: list[dict],
        per_span: bool = True,  # False = one flat word list, losing which span each came from
        restore_span_text: bool = True,  # False = mfa's own text: lowercased, no punctuation
    ) -> list[list[dict] | None] | list[dict]:
        """Align ``spans`` -- ``[{"start": sec, "end": sec, "text": str}, ...]`` -- inside
        ``audio_path``.

        Returns one word list per span, on the audio's own timeline:
        [
            [{"start": 1.05, "end": 1.13, "text": "So"}, ...],  # span 0
            None,                                               # span 1: unalignable, see below
        ]

        ``None``, never [], when MFA drops a span -- under its 100 ms floor, or more text
        than the audio can hold -- so a drop cannot pass for a zero-word alignment. With
        ``per_span=False`` those drops are simply absent from the flat list.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            corpus_dir, out_dir = Path(tmp_dir) / "corpus", Path(tmp_dir) / "out"
            corpus_dir.mkdir()
            audio = Path(audio_path).resolve()
            (corpus_dir / audio.name).symlink_to(audio)
            # One file, one speaker: the tier name is arbitrary and tmp_dir is per call.
            write_textgrid(corpus_dir / f"{audio.stem}.TextGrid", spans, "speaker", get_duration(str(audio)))

            # Not alignment settings: json to parse, private tmp so parallel calls are safe.
            command = [self.mfa_bin, "align", str(corpus_dir), self.dictionary, self.acoustic_model, str(out_dir),
                       "--output_format", "json", "--num_jobs", str(self.num_jobs),
                       "--temporary_directory", str(Path(tmp_dir) / "mfa_tmp")]
            if self.beam is not None:
                command += ["--beam", str(self.beam)]
            subprocess.run(command, check=True, env={**os.environ, "PATH": self.executable_search_path})

            produced = next(iter(out_dir.rglob(f"{audio.stem}.json")), None)
            if produced is None:
                raise RuntimeError(f"MFA wrote no alignment for {audio_path}")
            per_span_words = words_per_span(json.loads(produced.read_text()), spans, restore_span_text)
            if per_span:
                return per_span_words
            return [word for span_words in per_span_words if span_words for word in span_words]


def write_textgrid(path: Path, spans: list[dict], speaker: str, duration_s: float) -> None:
    """One IntervalTier holding the spans; praatio fills the gaps between them."""
    intervals = [Interval(span["start"], span["end"], span["text"]) for span in spans]
    grid = textgrid.Textgrid(minTimestamp=0.0, maxTimestamp=duration_s)
    grid.addTier(IntervalTier(speaker, intervals, 0.0, duration_s))
    grid.save(str(path), format="long_textgrid", includeBlankSpaces=True)


def words_per_span(alignment: dict, spans: list[dict], restore_span_text: bool = True) -> list[list[dict] | None]:
    """Bucket MFA's ``tiers.words.entries`` back into the span holding each word's start."""
    entries = alignment["tiers"]["words"]["entries"]
    words = [{"start": float(s), "end": float(e), "text": str(label)} for s, e, label in entries if str(label).strip()]

    per_span: list[list[dict] | None] = []
    for span in spans:
        inside = [w for w in words
                  if span["start"] - SPAN_TOLERANCE_S <= w["start"] < span["end"] + SPAN_TOLERANCE_S]
        if not inside:
            per_span.append(None)
        else:
            per_span.append(restore_text(inside, span["text"]) if restore_span_text else inside)
    return per_span


def restore_text(words: list[dict], text: str) -> list[dict]:
    """Return exactly ``text``'s tokens, timed by ``words``.

    The text was our input, so it rules; the aligner only supplies times. Tokenization
    differs both ways (MFA splits "full-time", Qwen joins "Mm-hmm.That"), so the sequences
    are matched on normalized forms and mismatched runs re-timed: many words into one token
    share its span, one word over many tokens divides evenly.
    """
    # split on whitespace, and where punctuation glues two words ("proud?Okay.")
    tokens = re.sub(r"([.?!,;:])(?=[A-Za-z])", r"\1 ", text).split()
    normalize = lambda token: "".join(c for c in token.lower() if c.isalnum() or c == "'")
    matcher = SequenceMatcher(a=[normalize(w["text"]) for w in words], b=[normalize(t) for t in tokens])

    timed: list[dict] = []
    for tag, word_lo, word_hi, token_lo, token_hi in matcher.get_opcodes():
        if tag == "equal":
            timed += [
                {"start": words[word_lo + i]["start"], "end": words[word_lo + i]["end"], "text": tokens[token_lo + i]}
                for i in range(token_hi - token_lo)
            ]
            continue
        if token_lo == token_hi:
            continue  # words with no token behind them
        block = words[word_lo:word_hi]
        if block:
            span_start, span_end = block[0]["start"], block[-1]["end"]
        else:  # no aligned word: zero-width slot at the neighbour
            span_start = timed[-1]["end"] if timed else (words[0]["start"] if words else 0.0)
            span_end = words[word_hi]["start"] if word_hi < len(words) else span_start
        step = (span_end - span_start) / (token_hi - token_lo)
        timed += [
            {"start": span_start + step * i, "end": span_start + step * (i + 1), "text": tokens[token_lo + i]}
            for i in range(token_hi - token_lo)
        ]
    return timed
