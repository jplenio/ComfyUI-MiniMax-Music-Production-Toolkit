"""Shared song-length contract for prompt planning and YuE2 generation.

Length is a musical target; native max_duration only limits generation. No
audio is padded, repeated or stretched to conceal an early model ending.
"""
from __future__ import annotations

import json
import math
import re


def duration_request(value):
    """Resolve explicit seconds, minutes, mm:ss and ranges; never guess a unit."""
    original = str(value or "").strip()
    value = original.casefold().replace(",", ".")
    value = re.sub(r"^(?:about|approximately|approx\.?|around|ca\.?|circa)\s+", "", value)
    if value in {"", "custom"}:
        return None
    unit = r"(?:seconds?|secs?|s|sekunden?|sek|min(?:utes?|uten)?s?|m)"
    number = r"\d+(?:\.\d+)?"
    atom = rf"(?:\d+:\d{{2}}|{number}\s*{unit}?)"
    match = re.fullmatch(rf"({atom})\s*(?:[-–—]|to|bis)\s*({atom})", value)
    parts = match.groups() if match else (value,)

    def seconds(part, inherited_unit=""):
        clock = re.fullmatch(r"(\d+):(\d{2})", part.strip())
        if clock:
            return int(clock[1]) * 60 + int(clock[2]) if int(clock[2]) < 60 else None
        item = re.fullmatch(rf"({number})\s*({unit})?", part.strip())
        if not item or not (item[2] or inherited_unit):
            return None
        suffix = item[2] or inherited_unit
        return float(item[1]) * (60 if suffix.startswith("m") else 1)

    suffixes = [re.search(rf"({unit})$", part.strip()) for part in parts]
    inherited = next((s[1] for s in reversed(suffixes) if s), "")
    values = [seconds(part, inherited) for part in parts]
    if any(v is None or not math.isfinite(v) or v <= 0 for v in values):
        return None
    low, high = values[0], values[-1]
    if low > high:
        return None
    return {"requested_length": original, "minimum_seconds": low,
            "maximum_seconds": high, "target_seconds": (low + high) / 2}


def request_from_brief(summary_json="", user_prompt=""):
    if summary_json:
        data = json.loads(summary_json)
        # Explicit custom is authoritative: never revive an inherited length.
        return duration_request(data.get("fields", {}).get("length"))
    # Legacy/manual graphs can still pass an explicit labelled duration. Avoid
    # interpreting unrelated numbers, tempo or ABC metadata as song length.
    match = re.search(r"^(?:Length|Song length|Duration):\s*([^\r\n]+)", user_prompt or "", re.I | re.M)
    return duration_request(match[1]) if match else None


def duration_line(request):
    target = request["target_seconds"]
    low, high = request["minimum_seconds"], request["maximum_seconds"]
    window = f"; requested range: {low:g}-{high:g} seconds" if low != high else ""
    return f"Target duration: {target:g} seconds{window}."


def request_from_style(style):
    """Use an explicit final plan for free-form/manual briefs without Length."""
    match = re.search(r"^Target duration:\s*([^\r\n;]+)", style or "", re.I | re.M)
    return duration_request(match[1].strip().rstrip('.')) if match else None


def duration_style(style, request, *, cover=False):
    if not request:
        return style
    # Replace the dedicated target line instead of accumulating contradictory
    # headers across manual retries. Musical section prose stays untouched.
    style = re.sub(r"^Target duration:[^\r\n]*(?:\r?\n)?", "", style, flags=re.I | re.M).lstrip()
    instruction = (
        "Approximate cover duration; follow the supplied ABC phrase order and tempo. "
        "Let the source phrases and final decay finish naturally, even beyond the target. "
        "The source score may end earlier; do not invent score extensions."
        if cover else
        "Aim for approximately this duration with a complete musical form and natural ending; "
        "do not finish after the first theme. Complete the current phrase, final cadence and "
        "decay even if they run beyond the target. Do not cut off or abruptly fade at the target time."
    )
    return duration_line(request) + "\n" + instruction + "\n\n" + style


def duration_brief(request):
    return (
        "DURATION PLAN: " + duration_line(request) + " Use this target for the shared Style/Lyrics "
        "arrangement. Begin Style with the Target duration line. Give every numbered Style "
        "section a consecutive start/end time and a plausible bar/phrase count at the chosen "
        "tempo and meter; the complete form, including the ending, should add up approximately "
        "to the target. This is a musical aim, not a cutoff: allow phrases, the final cadence "
        "and decay to finish naturally even if that takes longer. "
        "Use the identical section order in Lyrics, with enough sung phrases or instrumental "
        "development for each interval. Keep timestamps and bar counts out of Lyrics."
    )


def generation_duration(request, ceiling):
    """Validate feasibility while retaining the full configured generation room.

    A requested Length (including the upper end of a range) is never a cutoff.
    Only the separately configured ceiling limits the native generator.
    """
    if not request:
        return ceiling
    if request["target_seconds"] > ceiling:
        raise ValueError(
            f"Requested song length targets {request['target_seconds']:g} seconds, but "
            f"yue2_max_duration allows only {ceiling:g}. Increase yue2_max_duration "
            "or select a shorter Length before generating."
        )
    return ceiling
