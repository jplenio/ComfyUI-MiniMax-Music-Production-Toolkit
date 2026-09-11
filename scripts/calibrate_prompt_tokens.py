#!/usr/bin/env python3
"""Calibrate the MiniMax prompt token estimator against the real tokenizer.

Loads ``tokenizer_json`` from the MiniMax Music 3 text-encoder checkpoint
(only that small metadata tensor, no model weights, no GPU), encodes
representative caption/lyrics pairs with the exact ``build_prompt()``
construction ComfyUI uses, and prints chars-per-token statistics.

**Which statistic matters.**  ``prompt_budget.estimate_prompt_tokens`` divides
the character count by ``_CHARS_PER_TOKEN`` and therefore over-counts tokens
only while the constant stays *below* the real chars-per-token ratio of every
prompt.  The binding constraint is the **minimum** ratio across the samples, not
the maximum: a single dense script (CJK, Urdu, Devanagari, unusual Unicode)
lowers the bound.  This script reports min/median/max and fails (exit code 1)
when the configured constant exceeds the minimum.

Keeping the two apart matters - an earlier revision of this script printed the
*maximum* ratio as the "worst case", which is the least constraining sample and
would have accepted a constant that undershoots on multilingual input.

Usage:

    <comfyui-venv-python> scripts/calibrate_prompt_tokens.py \
        --comfy-dir D:/ComfyUI \
        --checkpoint F:/ComfyUI/models/text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors

    # machine-readable:
    ... --json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

# Must match ``prompt_budget._CHARS_PER_TOKEN``; overridable with
# ``--chars-per-token`` so the verdict logic can be exercised without editing
# the toolkit.
DOCUMENTED_CHARS_PER_TOKEN = 3.5

# (label, caption, lyrics) - deliberately multilingual: the heuristic was
# calibrated on German/English only, so the dense scripts below decide whether
# the constant is still conservative.
SAMPLES: Tuple[Tuple[str, str, str], ...] = (
    (
        "english-pop",
        "Warm 2000s pop ballad - piano, brushed drums, intimate female lead.",
        "[Verse]\nI keep your letter in my coat\nI read it when the city sleeps\n"
        "[Chorus]\nSay my name like it still means something\nSay it slow before the morning",
    ),
    (
        "german-techno",
        "Instrumentaler Hardgroove Techno - treibend, hypnotisch, mit hartem Kick und rollendem Bass.",
        "[Intro]\n[Instrumental]\n[Build]\n(stampfende Kick, offene Hats, Riser)\n[Drop]\n[Instrumental]\n[Outro]",
    ),
    (
        "japanese-citypop",
        "都会の夜を描くシティポップ、きらめくシンセと軽やかなドラム。",
        "[Verse]\nネオンの海を渡って\n君の名前を呼んでみる\n[Chorus]\n夜が明けるまで踊ろう",
    ),
    (
        "chinese-ballad",
        "温柔的民谣，木吉他、弦乐与清亮的女声。",
        "[Verse]\n风吹过旧时的巷口\n我把思念写成了歌\n[Chorus]\n月落之前 请再靠近我",
    ),
    (
        "korean-rap",
        "새벽 감성의 한국 힙합, 묵직한 베이스와 절제된 드럼.",
        "[Verse]\n어둔 골목 끝에서 숨을 고르고\n멈춘 발걸음을 다시 옮겨\n[Hook]\n새벽이 오면 다시",
    ),
    (
        "urdu-ghazal",
        "روایتی غزل، سارنگی اور ہلکی تبلا کے ساتھ۔",
        "[Verse]\nتیرے بغیر یہ شامیں ادھوری سی لگتی ہیں\nہر آہٹ میں تیرا ہی گمان رہتا ہے\n[Verse]\nچراغ جلے تو راہیں پہچان لیں",
    ),
    (
        "russian-rock",
        "Гитарный рок с чистым вокалом и живыми барабанами.",
        "[Verse]\nГород спит под серым снегом\nЯ иду по кромке льда\n[Chorus]\nЗажги огонь, пока не поздно",
    ),
    (
        "hindi-film",
        "फ़िल्मी बैलेड, सितार और हल्के ढोलक के साथ।",
        "[Verse]\nतेरी आँखों में सपने बसते हैं\nरात भर जागते सितारे\n[Chorus]\nसाथ निभा दे, साथी",
    ),
)


def build_rows(
    samples: Sequence[Tuple[str, str, str]],
    count_tokens: Callable[[str, str], int],
) -> List[Dict[str, object]]:
    """One row per sample: the estimator's input text vs the real token count.

    ``count_tokens(caption, lyrics)`` must return the token count of the exact
    text MiniMax consumes (``build_prompt``) for the *same* caption+lyrics pair
    that :func:`prompt_budget.estimate_prompt_tokens` measures, so the ratio is
    comparable with ``_CHARS_PER_TOKEN``.
    """
    rows: List[Dict[str, object]] = []
    for label, caption, lyrics in samples:
        prompt_chars = len(caption) + 1 + len(lyrics)
        tokens = int(count_tokens(caption, lyrics))
        rows.append(
            {
                "label": label,
                "prompt_chars": prompt_chars,
                "tokens": tokens,
                "chars_per_token": (prompt_chars / tokens) if tokens > 0 else None,
            }
        )
    return rows


def summarize_rows(rows: Sequence[Dict[str, object]]) -> Dict[str, object]:
    """min/median/max chars-per-token plus the binding (minimum) sample.

    The minimum is the binding constraint for a conservative constant: it is
    the sample that needs the most tokens per character.
    """
    usable = [row for row in rows if row.get("chars_per_token")]
    if not usable:
        return {
            "binding_min": None,
            "median": None,
            "max": None,
            "binding_label": None,
            "samples": len(rows),
        }
    binding = min(usable, key=lambda row: float(row["chars_per_token"]))
    ratios = [float(row["chars_per_token"]) for row in usable]
    return {
        "binding_min": min(ratios),
        "median": statistics.median(ratios),
        "max": max(ratios),
        "binding_label": binding["label"],
        "samples": len(usable),
    }


def verdict(summary: Dict[str, object], constant: float) -> Dict[str, object]:
    """Compare the configured constant against the binding minimum."""
    binding = summary.get("binding_min")
    if binding is None:
        return {"ok": None, "reason": "no measurable sample", "binding_min": None}
    ok = float(constant) <= float(binding)
    return {
        "ok": ok,
        "reason": (
            "constant is at or below the minimum chars/token - the estimate "
            "over-counts on every sample"
            if ok
            else "constant exceeds the minimum chars/token - the estimate "
            "undershoots on the binding sample"
        ),
        "binding_min": float(binding),
        "constant": float(constant),
        "binding_label": summary.get("binding_label"),
    }


def _load_encode_pair(args) -> Callable[[str, str], int]:
    """Build ``count_tokens(caption, lyrics)`` from the real ComfyUI pieces."""
    from tokenizers import Tokenizer  # type: ignore
    from safetensors import safe_open  # type: ignore
    from comfy.ldm.minimax_music.prompt import build_prompt  # type: ignore

    checkpoint = Path(args.checkpoint)
    with safe_open(str(checkpoint), framework="np") as handle:
        blob = handle.get_tensor("tokenizer_json")
    tokenizer = Tokenizer.from_str(bytes(blob.tobytes()).decode("utf-8"))

    def count_tokens(caption: str, lyrics: str) -> int:
        prompt = build_prompt(caption, lyrics)
        return len(tokenizer.encode(prompt, add_special_tokens=False).ids)

    return count_tokens


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--comfy-dir", help="path to the ComfyUI checkout (needed for build_prompt)")
    parser.add_argument("--checkpoint", required=True, help="MiniMax Music 3 text-encoder safetensors file")
    parser.add_argument(
        "--chars-per-token",
        type=float,
        default=DOCUMENTED_CHARS_PER_TOKEN,
        help="constant to evaluate (default: the documented prompt_budget value)",
    )
    parser.add_argument("--json", action="store_true", help="print the summary as JSON only")
    args = parser.parse_args()

    if args.comfy_dir:
        sys.path.insert(0, args.comfy_dir)
        os.chdir(args.comfy_dir)
    try:
        count_tokens = _load_encode_pair(args)
    except Exception as exc:
        print(f"Could not load tokenizer/build_prompt: {type(exc).__name__}: {exc}")
        print("Pass --comfy-dir <ComfyUI checkout> so comfy.ldm.minimax_music.prompt is importable.")
        return 1

    checkpoint = Path(args.checkpoint)
    if not checkpoint.is_file():
        print(f"Checkpoint not found: {checkpoint}")
        return 1

    rows = build_rows(SAMPLES, count_tokens)
    summary = summarize_rows(rows)
    result = verdict(summary, args.chars_per_token)

    if args.json:
        print(json.dumps({"rows": rows, "summary": summary, "verdict": result}, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    print(f"{'sample':<16} {'chars':>8} {'tokens':>8} {'chars/token':>12}")
    for row in rows:
        ratio = row["chars_per_token"]
        ratio_text = f"{ratio:.3f}" if ratio else "n/a"
        print(f"{row['label']:<16} {row['prompt_chars']:>8} {row['tokens']:>8} {ratio_text:>12}")

    if summary["binding_min"] is None:
        print("\nNo sample produced usable token counts.")
        return 1

    print(
        f"\nchars/token  min (binding): {summary['binding_min']:.3f} "
        f"[{summary['binding_label']}]   median: {summary['median']:.3f}   max: {summary['max']:.3f}"
    )
    print(f"_CHARS_PER_TOKEN evaluated: {args.chars_per_token:.3f}")
    if result["ok"]:
        print("OK: the constant is at or below the binding minimum; the estimate over-counts on every sample.")
        return 0
    print(
        "FAIL: the constant exceeds the binding minimum, so the estimate undershoots on "
        f"'{result['binding_label']}'. Lower _CHARS_PER_TOKEN below {summary['binding_min']:.3f} "
        "or treat the value as an estimate only."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
