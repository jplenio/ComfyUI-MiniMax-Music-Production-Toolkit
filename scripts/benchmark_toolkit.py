#!/usr/bin/env python3
"""Reproducible performance and quality baseline for the toolkit (B01).

What this harness is for
------------------------
Improvements may only be called improvements when they are compared against the
same workload.  This script measures the stages of the audio chain on
deterministic synthetic audio, so a "before" and an "after" run use byte-identical
input, and it reports the environment next to the numbers so a result can be
attributed to a machine instead of to folklore.

Honesty rules baked into the output
-----------------------------------
* torch's ``allocated``/``reserved`` counters do **not** account for llama.cpp
  or the aimdo/VBAR allocator, so the report uses process RSS (current and peak)
  instead of pretending CUDA counters are total memory;
* CUDA synchronisation happens at measurement boundaries only - never inside the
  measured stage;
* standard telemetry contains sizes, parameters and timings, never prompt text
  or audio content (``tests/fixtures/benchmark_briefs.json`` holds the briefs);
* stages that cannot run on this machine (no weights, no GPU, no llama-cpp) are
  listed under ``not_measured`` with a reason - they are never silently omitted
  and never guessed;
* hardware classes that do not exist on the measuring machine stay ``untested``.

Usage
-----
    python scripts/benchmark_toolkit.py --list
    python scripts/benchmark_toolkit.py                      # fast default profile
    python scripts/benchmark_toolkit.py --full --repeats 3   # whole matrix
    python scripts/benchmark_toolkit.py --json results.json
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
MATRIX_FILE = FIXTURES / "benchmark_matrix.json"

# Audio stages that run on synthetic data without any model weights.  ``audio_args``
# names the inputs that receive the generated audio; every other widget value is
# taken from the node's own INPUT_TYPES defaults, so the benchmark never invents
# settings the product would not use.
AUDIO_STAGES: Dict[str, Dict[str, Any]] = {
    "declip": {
        "module": "audio_declip",
        "class": "AudioDeclipRepair",
        "function": "process",
        "audio_args": ("audio",),
    },
    "lowpass": {
        "module": "audio_lowpass",
        "class": "FlashSRLowpassLab",
        "function": "run",
        "audio_args": ("audio",),
    },
    "hf_repair": {
        "module": "audio_hf_repair",
        "class": "HFCymbalShimmerRepair",
        "function": "process",
        "audio_args": ("audio",),
    },
    "hybrid_crossover": {
        "module": "audio_hf_repair",
        "class": "FlashSRHybridCrossover",
        "function": "process",
        "audio_args": ("original_audio", "flashsr_audio"),
    },
    "release_prep": {
        "module": "audio_release_prep",
        "class": "AudioReleasePrep",
        "function": "process",
        "audio_args": ("audio",),
        "needs": "ffmpeg",
    },
}

# Stages that exist in the product but cannot be measured with fixtures alone.
UNMEASURABLE_STAGES: Dict[str, str] = {
    "flashsr": "requires the FlashSR checkpoints under models/audio/flashsr; the weights are not bundled",
    "minimax_generation": "requires the MiniMax Music 3 diffusion model and a GPU",
    "flux_artwork": "requires the FLUX.2 Klein model",
    "llm_chat": "requires llama-cpp-python and a GGUF model",
    "downloads": "requires network access; measured separately with the download tests",
}


# --------------------------------------------------------------------------
# matrix and workload handling
# --------------------------------------------------------------------------


def load_matrix(path: Path = MATRIX_FILE) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def describe_workload(workload: Dict[str, int]) -> str:
    return (
        f"{workload['seconds']}s_{workload['channels']}ch_"
        f"{workload['sample_rate']}Hz_b{workload['batch']}"
    )


def expand_audio_workloads(matrix: Dict[str, Any], full: bool = False) -> List[Dict[str, int]]:
    """Default profile, or the whole axis product with ``full=True``."""
    audio = matrix.get("audio") or {}
    if not full:
        profile = dict(audio.get("default_profile") or {})
        return [profile] if profile else []
    axes = audio.get("axes") or {}
    workloads: List[Dict[str, int]] = []
    for seconds in axes.get("seconds", []):
        for channels in axes.get("channels", []):
            for rate in axes.get("sample_rate", []):
                for batch in axes.get("batch", []):
                    workloads.append(
                        {"seconds": int(seconds), "channels": int(channels), "sample_rate": int(rate), "batch": int(batch)}
                    )
    return workloads


def synthesize_audio(seconds: int, channels: int, sample_rate: int, batch: int, seed: int = 1234):
    """Deterministic broadband test signal with transients, clipping and silence.

    Deliberately contains the things the chain reacts to (clipped peaks for
    declip, bright noise for the low-pass, a quiet tail so loudness is not
    trivial), so the stages do real work instead of timing an early return.
    """
    import numpy as np
    import torch

    rng = np.random.default_rng(seed)
    total = int(seconds * sample_rate)
    timeline = np.arange(total) / float(sample_rate)
    mono = (
        0.30 * np.sin(2 * np.pi * 220.0 * timeline)
        + 0.20 * np.sin(2 * np.pi * 3000.0 * timeline)
        + 0.10 * np.sin(2 * np.pi * 11000.0 * timeline)
        + 0.03 * rng.standard_normal(total)
    )
    # Periodic transient every 0.5 s so the envelope followers see real events.
    click = max(1, sample_rate // 200)
    for start in range(0, total, max(1, sample_rate // 2)):
        end = min(total, start + click)
        mono[start:end] += 1.4
    # A few hard-clipped peaks (the case declip exists for).
    clip_points = rng.integers(0, max(1, total - 1), size=32)
    mono[clip_points] = np.sign(mono[clip_points]) * 1.0
    mono[-max(1, sample_rate // 10):] *= 0.02
    signal = np.tile(mono, (channels, 1))
    waveform = torch.from_numpy(signal.astype("float32"))
    if batch > 1:
        waveform = waveform.unsqueeze(0).repeat(batch, 1, 1)
    else:
        waveform = waveform.unsqueeze(0)
    return {"waveform": waveform.contiguous(), "sample_rate": int(sample_rate)}


# --------------------------------------------------------------------------
# measurement primitives
# --------------------------------------------------------------------------


def _windows_process_memory() -> tuple:
    """(working_set, peak_working_set) bytes on Windows, or (None, None)."""
    if platform.system() != "Windows":  # pragma: no cover - platform dependent
        return None, None
    try:  # pragma: no cover - Windows only
        import ctypes

        class _ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        handle = kernel32.GetCurrentProcess()
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        # The handle must be a void pointer: with the default ``c_int`` restype
        # it is truncated on 64-bit Windows and the call silently fails.
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None, None
        return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)
    except Exception:
        return None, None


def process_memory_bytes() -> Dict[str, Optional[int]]:
    """Current and peak process RSS; unknown values are ``None``, never ``0``."""
    current, peak = _windows_process_memory()
    if current is None:  # pragma: no cover - POSIX path
        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            current = int(usage.ru_maxrss) * 1024
            peak = current
        except Exception:
            pass
    if peak is None:
        peak = current
    return {"rss_bytes": current, "peak_rss_bytes": peak}


def synchronize_devices() -> None:
    """CUDA synchronisation for measurement boundaries only."""
    try:  # pragma: no cover - needs a GPU
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except Exception:
        pass


def summarize_times(times_ms: Sequence[float]) -> Dict[str, Any]:
    """Median plus spread. A single sample reports no spread instead of faking it."""
    values = [float(value) for value in times_ms]
    if not values:
        return {"count": 0, "median_ms": None, "min_ms": None, "max_ms": None, "stdev_ms": None}
    return {
        "count": len(values),
        "median_ms": round(statistics.median(values), 3),
        "min_ms": round(min(values), 3),
        "max_ms": round(max(values), 3),
        "stdev_ms": round(statistics.stdev(values), 3) if len(values) > 1 else None,
    }


def measure(callable_: Callable[[], Any], repeats: int = 3, warmups: int = 1) -> Dict[str, Any]:
    """Time ``callable_``; warm-up runs are excluded from the reported spread."""
    for _ in range(max(0, int(warmups))):
        synchronize_devices()
        callable_()
    times: List[float] = []
    for _ in range(max(1, int(repeats))):
        synchronize_devices()
        started = time.perf_counter()
        callable_()
        synchronize_devices()
        times.append((time.perf_counter() - started) * 1000.0)
    return summarize_times(times)


# --------------------------------------------------------------------------
# stage plumbing
# --------------------------------------------------------------------------


def load_toolkit_module(module_name: str):
    """Load one toolkit module under a synthetic package (no ComfyUI import)."""
    import importlib.util
    import types

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    package_name = "_minimax_benchmark_pkg"
    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(ROOT)]
        sys.modules[package_name] = package
    full = f"{package_name}.{module_name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def default_for_input(entry: Any) -> Any:
    """The node's own documented default for one INPUT_TYPES entry."""
    if not (isinstance(entry, (tuple, list)) and entry):
        return None
    declared = entry[0]
    options = entry[1] if len(entry) > 1 and isinstance(entry[1], dict) else {}
    if "default" in options:
        return options["default"]
    if isinstance(declared, (list, tuple)) and declared:
        return declared[0]
    return {"INT": 0, "FLOAT": 0.0, "BOOLEAN": False, "STRING": ""}.get(str(declared), None)


def stage_kwargs(node_class, audio_args: Sequence[str], audio: Any) -> Dict[str, Any]:
    """Widget values from INPUT_TYPES defaults, with the fixture audio injected."""
    spec = node_class.INPUT_TYPES() or {}
    kwargs: Dict[str, Any] = {}
    missing: List[str] = []
    for section in ("required", "optional"):
        for name, entry in (spec.get(section) or {}).items():
            if name in audio_args:
                kwargs[name] = audio
                continue
            options = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else {}
            if isinstance(options, dict) and options.get("forceInput"):
                if section == "required":
                    missing.append(name)
                continue
            kwargs[name] = default_for_input(entry)
    if missing:
        raise ValueError(f"required inputs cannot be supplied by the benchmark: {', '.join(sorted(missing))}")
    return kwargs


def run_audio_stage(
    stage: str,
    workload: Dict[str, int],
    audio: Any = None,
    node_loader: Callable[[str], Any] = load_toolkit_module,
) -> Dict[str, Any]:
    """Run one stage once; returns the callable result plus the node identity."""
    spec = AUDIO_STAGES[stage]
    module = node_loader(spec["module"])
    node_class = getattr(module, spec["class"])
    instance = node_class()
    audio = audio if audio is not None else synthesize_audio(**workload)
    kwargs = stage_kwargs(node_class, spec["audio_args"], audio)
    if len(spec["audio_args"]) > 1:
        for name in spec["audio_args"][1:]:
            kwargs[name] = audio
    return {
        "stage": stage,
        "node": spec["class"],
        "function": spec["function"],
        "call": lambda: getattr(instance, spec["function"])(**kwargs),
    }


def environment_report() -> Dict[str, Any]:
    """Backend/device facts that belong next to any number in this report."""
    report: Dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    try:  # pragma: no cover - environment dependent
        import torch

        report["torch"] = str(getattr(torch, "__version__", "unknown"))
        report["torch_cuda"] = str(getattr(getattr(torch, "version", None), "cuda", None))
        report["cuda_available"] = bool(torch.cuda.is_available())
        report["cuda_device_count"] = int(torch.cuda.device_count()) if torch.cuda.is_available() else 0
    except Exception as exc:
        report["torch"] = None
        report["torch_error"] = f"{type(exc).__name__}: {exc}"
    try:
        module = load_toolkit_module("resource_profiles")
        snapshot = module.detect_resources()
        report["resources"] = snapshot.to_dict()
        report["recommendations"] = module.recommend_profiles(snapshot)
    except Exception as exc:  # pragma: no cover - defensive
        report["resources"] = None
        report["resources_error"] = f"{type(exc).__name__}: {exc}"
    report["memory"] = process_memory_bytes()
    report["telemetry_note"] = (
        "torch allocated/reserved counters do not cover llama.cpp or the aimdo/VBAR allocator; "
        "process RSS is reported instead"
    )
    return report


def run_benchmark(
    stages: Optional[Sequence[str]] = None,
    full: bool = False,
    repeats: int = 3,
    warmups: int = 1,
    matrix: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Measure every requested stage on every requested workload."""
    matrix = matrix if matrix is not None else load_matrix()
    chosen = list(stages) if stages else sorted(AUDIO_STAGES)
    unknown = [name for name in chosen if name not in AUDIO_STAGES]
    if unknown:
        raise ValueError(f"unknown stage(s): {', '.join(unknown)} (known: {', '.join(sorted(AUDIO_STAGES))})")
    workloads = expand_audio_workloads(matrix, full=full)
    results: List[Dict[str, Any]] = []
    not_measured: Dict[str, str] = dict(UNMEASURABLE_STAGES)
    for workload in workloads:
        try:
            audio = synthesize_audio(**workload)
        except Exception as exc:
            not_measured[f"audio:{describe_workload(workload)}"] = (
                f"could not build the fixture signal: {type(exc).__name__}: {exc}"
            )
            continue
        for stage in chosen:
            label = f"{stage}:{describe_workload(workload)}"
            try:
                runner = run_audio_stage(stage, workload, audio=audio)
                timing = measure(runner["call"], repeats=repeats, warmups=warmups)
            except Exception as exc:
                not_measured[label] = f"{type(exc).__name__}: {exc}"
                continue
            results.append(
                {
                    "stage": stage,
                    "node": runner["node"],
                    "workload": dict(workload),
                    "workload_id": describe_workload(workload),
                    "timing": timing,
                    "memory": process_memory_bytes(),
                }
            )
    return {
        "results": results,
        "not_measured": not_measured,
        "environment": environment_report(),
        "matrix": {
            "file": MATRIX_FILE.name,
            "full": bool(full),
            "repeats": int(repeats),
            "warmups": int(warmups),
        },
        "hardware_to_measure": (matrix.get("hardware") or {}).get("vram_gib_classes", []),
        "hardware_status": (matrix.get("hardware") or {}).get("status", "untested"),
    }


def format_report(report: Dict[str, Any]) -> str:
    lines = ["Music Production Toolkit - performance baseline", ""]
    environment = report["environment"]
    lines.append(
        f"Python {environment.get('python')} on {environment.get('platform')} "
        f"(torch {environment.get('torch')}, cuda {environment.get('torch_cuda')}, "
        f"cuda_available={environment.get('cuda_available')})"
    )
    memory = environment.get("memory") or {}
    lines.append(
        "Process memory: "
        + (
            f"{memory.get('rss_bytes')} bytes RSS, peak {memory.get('peak_rss_bytes')} bytes"
            if memory.get("rss_bytes") is not None
            else "unknown"
        )
    )
    resources = environment.get("resources") or {}
    for device in resources.get("devices", []):
        if device.get("kind") == "cpu":
            continue
        lines.append(
            f"Device {device.get('id')} ({device.get('name')}): "
            f"{device.get('vram_free_bytes')} / {device.get('vram_total_bytes')} bytes free"
        )
    for recommendation in environment.get("recommendations", []):
        lines.append(f"Recommendation [{recommendation['id']}] ({recommendation['confidence']})")
    lines.append("")
    lines.append("Stage timings (median of the timed runs, ms):")
    if not report["results"]:
        lines.append("  (nothing was measured - see the not-measured list)")
    for result in report["results"]:
        timing = result["timing"]
        spread = "" if timing["stdev_ms"] is None else f" +/- {timing['stdev_ms']:.3f}"
        lines.append(
            f"  {result['workload_id']:<26} {result['stage']:<18} "
            f"median {timing['median_ms']:.3f}{spread} ms  (n={timing['count']}, "
            f"min {timing['min_ms']:.3f}, max {timing['max_ms']:.3f})"
        )
    lines.append("")
    lines.append("Not measured here (reported, never guessed):")
    for name, reason in sorted(report["not_measured"].items()):
        lines.append(f"  -- {name}: {reason}")
    lines.append("")
    lines.append(
        "Hardware classes from the matrix are '"
        + str(report.get("hardware_status", "untested"))
        + "': this run only measured the machine it ran on."
    )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="list measurable and unmeasurable stages, then exit")
    parser.add_argument("--stages", default="", help="comma-separated stage names (default: all measurable)")
    parser.add_argument("--full", action="store_true", help="measure the whole axis product, not just the default profile")
    parser.add_argument("--repeats", type=int, default=3, help="timed runs per stage/workload")
    parser.add_argument("--warmups", type=int, default=1, help="warm-up runs excluded from the timing")
    parser.add_argument("--json", dest="json_path", default=None, help="also write the raw report to this file")
    args = parser.parse_args(argv)

    if args.list:
        print("Measurable stages (synthetic audio, no model weights):")
        for name, spec in sorted(AUDIO_STAGES.items()):
            needs = f" (needs {spec['needs']})" if spec.get("needs") else ""
            print(f"  {name:<18} {spec['module']}.{spec['class']}.{spec['function']}{needs}")
        print("Declared but not measurable with fixtures alone:")
        for name, reason in sorted(UNMEASURABLE_STAGES.items()):
            print(f"  {name:<18} {reason}")
        return 0

    stages = [name.strip() for name in args.stages.split(",") if name.strip()]
    try:
        report = run_benchmark(stages or None, full=args.full, repeats=args.repeats, warmups=args.warmups)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2
    print(format_report(report))
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json_path}")
    return 0 if report["results"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
