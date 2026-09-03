#!/usr/bin/env python3
"""Calibrate the MiniMax prompt token estimator against the real tokenizer.

Loads ``tokenizer_json`` from the MiniMax Music 3 text-encoder checkpoint
(only that small tensor, no model weights), encodes representative
caption/lyrics pairs with the exact ``build_prompt()`` construction ComfyUI
uses, and prints chars-per-token statistics.

Use the printed worst case to review the ``_CHARS_PER_TOKEN`` constant in
``prompt_budget.py`` (must stay <= the worst real chars/token so the estimate
never undershoots).

Usage:

    <comfyui-venv-python> scripts/calibrate_prompt_tokens.py \
        --comfy-dir D:/ComfyUI \
        --checkpoint F:/ComfyUI/models/text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-dir", required=True, help="path to the ComfyUI checkout")
    parser.add_argument("--checkpoint", required=True, help="MiniMax Music 3 text-encoder safetensors file")
    args = parser.parse_args()

    sys.path.insert(0, args.comfy_dir)
    os.chdir(args.comfy_dir)
    try:
        from tokenizers import Tokenizer  # type: ignore
        from safetensors import safe_open  # type: ignore
        from comfy.ldm.minimax_music.prompt import build_prompt  # type: ignore
    except Exception as exc:
        print(f"Could not import ComfyUI/tokenizer dependencies from {args.comfy_dir}: {type(exc).__name__}: {exc}")
        return 1

    checkpoint = Path(args.checkpoint)
    if not checkpoint.is_file():
        print(f"Checkpoint not found: {checkpoint}")
        return 1

    with safe_open(str(checkpoint), framework="np") as f:
        blob = f.get_tensor("tokenizer_json")
    tokenizer = Tokenizer.from_str(blob.tobytes().decode("utf-8"))

    samples = [
        (
            "Instrumental Breakbeat — relentless, percussive and hypnotic, built around a powerful kick.",
            "[Intro]\n(percussive drums build alone)\n[Build]\n(add rolling bass and riser)\n[Drop]\n(breakbeat groove)\n[Outro]\n(decay)",
            "english breakbeat",
        ),
        (
            "Instrumentaler Hardgroove Techno — treibend, hypnotisch, mit hartem Kick und rollendem Bass.",
            "[Intro]\n[Instrumental]\n[Instrumental]\n[Outro]",
            "german techno",
        ),
    ]
    worst = 0.0
    for caption, lyrics, label in samples:
        prompt = build_prompt(caption, lyrics)
        ids = tokenizer.encode(prompt, add_special_tokens=False).ids
        chars_per_token = len(prompt) / len(ids)
        worst = max(worst, len(caption + lyrics) / len(tokenizer.encode(caption + "\n" + lyrics, add_special_tokens=False).ids))
        print(f"{label}: build_prompt {len(ids)} tokens, {len(prompt)} chars, {chars_per_token:.3f} chars/token")

    print(f"\nWorst raw chars/token measured: {worst:.3f}")
    print("prompt_budget._CHARS_PER_TOKEN must be <= that value (current: 3.5).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
