"""Resource detection and transparent hardware recommendations (R01).

The toolkit is a product for many different machines, so no part of it may
assume a particular GPU, two GPUs, 64 GB RAM or a personal model directory.
This module answers two questions:

* **What is there?** :func:`detect_resources` returns a plain data object with
  CPU cores, RAM and the visible compute devices (stable identifier, name,
  backend, free/total VRAM).  A value that could not be determined is ``None``,
  never ``0`` - "unknown" and "nothing" are different answers.
* **What does that mean?** :func:`recommend_profiles` turns a snapshot into
  labelled recommendations with a reason and an explicit confidence, so the UI
  can show the automatic suggestion next to the setting the user actually
  chose.  Recommendations are starting points, never silent overrides.

Design constraints kept deliberately:

* importing this module never imports ``torch`` - CPU-only installations work;
* no OOM probe loading, no network, no download, no writes;
* several GPUs are **not** one contiguous memory pool; budgets are per device;
* a low-RAM machine is never told to "just offload more to CPU".
"""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

GIB = 1024 ** 3

# Conservative starting reserve: the larger of a fixed minimum and a fraction
# of the device's total memory.  Real workloads may need more; the reserve is
# a floor, not a fit test.
RESERVE_MIN_BYTES = 1 * GIB
RESERVE_FRACTION = 0.10

# VRAM classes checked by the plan (GiB, inclusive upper bound).
VRAM_CLASSES: Sequence[int] = (4, 8, 12, 16, 24, 32)

_LOW_RAM_BYTES = 8 * GIB


@dataclass(frozen=True)
class DeviceInfo:
    """One visible compute device.

    ``id`` is the stable identifier used in settings and reports.  ``logical``
    is the index as the runtime sees it (after ``CUDA_VISIBLE_DEVICES``
    renumbering), ``physical`` the hardware index when it is knowable - both are
    reported so a renumbered device is not mistaken for a different card.
    """

    id: str
    name: str
    kind: str  # "cuda" | "mps" | "cpu"
    backend: str  # "cuda" | "rocm" | "mps" | "cpu"
    logical: Optional[int] = None
    physical: Optional[int] = None
    vram_total_bytes: Optional[int] = None
    vram_free_bytes: Optional[int] = None
    supported: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "backend": self.backend,
            "logical_index": self.logical,
            "physical_index": self.physical,
            "vram_total_bytes": self.vram_total_bytes,
            "vram_free_bytes": self.vram_free_bytes,
            "supported": self.supported,
        }


@dataclass
class ResourceSnapshot:
    """Point-in-time resource picture; unknown values are ``None``."""

    cpu_count: Optional[int] = None
    ram_total_bytes: Optional[int] = None
    ram_available_bytes: Optional[int] = None
    devices: List[DeviceInfo] = field(default_factory=list)
    backends: Dict[str, bool] = field(default_factory=dict)
    backend_versions: Dict[str, str] = field(default_factory=dict)
    visible_devices_env: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    captured_at: str = ""

    def device(self, device_id: str) -> Optional[DeviceInfo]:
        for device in self.devices:
            if device.id == device_id:
                return device
        return None

    @property
    def accelerators(self) -> List[DeviceInfo]:
        return [d for d in self.devices if d.kind in ("cuda", "mps") and d.supported]

    @property
    def is_cpu_only(self) -> bool:
        return not self.accelerators

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_count": self.cpu_count,
            "ram_total_bytes": self.ram_total_bytes,
            "ram_available_bytes": self.ram_available_bytes,
            "devices": [d.to_dict() for d in self.devices],
            "backends": dict(self.backends),
            "backend_versions": dict(self.backend_versions),
            "visible_devices_env": self.visible_devices_env,
            "notes": list(self.notes),
            "captured_at": self.captured_at,
        }


def _windows_memory() -> Optional[tuple]:
    """(total, available) RAM on Windows without psutil, else ``None``."""
    if platform.system() != "Windows":  # pragma: no cover - platform dependent
        return None
    try:  # pragma: no cover - Windows only
        import ctypes

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return int(status.ullTotalPhys), int(status.ullAvailPhys)
    except Exception:
        return None


def read_system_memory() -> tuple:
    """``(total, available)`` RAM bytes; either element may be ``None``."""
    try:  # pragma: no cover - depends on the environment
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        return int(memory.total), int(memory.available)
    except Exception:
        pass
    fallback = _windows_memory()
    if fallback is not None:
        return fallback
    return None, None


def _probe_torch_devices() -> tuple:
    """Torch-based device probe: ``(devices, backends)`` or ``([], {})``."""
    devices: List[DeviceInfo] = []
    backends: Dict[str, bool] = {}
    versions: Dict[str, str] = {}
    try:  # pragma: no cover - depends on the environment
        import torch  # type: ignore
    except Exception:
        return devices, backends, versions
    backends["torch"] = True
    versions["torch"] = str(getattr(torch, "__version__", "") or "unknown")
    cuda_runtime = getattr(getattr(torch, "version", None), "cuda", None)
    if cuda_runtime:
        versions["cuda"] = str(cuda_runtime)
    cuda = False
    try:
        cuda = bool(torch.cuda.is_available())
    except Exception:
        cuda = False
    backends["cuda"] = cuda
    if cuda:
        try:  # pragma: no cover - needs a GPU
            count = int(torch.cuda.device_count())
        except Exception:
            count = 0
        for index in range(count):
            name = f"cuda:{index}"
            total = free = None
            try:
                free, total = (int(v) for v in torch.cuda.mem_get_info(index))
            except Exception:
                pass
            try:
                name = torch.cuda.get_device_name(index)
            except Exception:
                pass
            devices.append(
                DeviceInfo(
                    id=f"cuda:{index}",
                    name=name,
                    kind="cuda",
                    backend="cuda",
                    logical=index,
                    physical=index,
                    vram_total_bytes=total,
                    vram_free_bytes=free,
                )
            )
    mps = False
    try:
        mps = bool(getattr(getattr(torch, "backends", None), "mps", None) and torch.backends.mps.is_available())
    except Exception:
        mps = False
    backends["mps"] = mps
    if mps:  # pragma: no cover - Apple silicon only
        devices.append(DeviceInfo(id="mps:0", name="Apple MPS", kind="mps", backend="mps", logical=0))
    return devices, backends, versions


def detect_resources(
    device_probe: Optional[Callable[[], tuple]] = None,
    memory_reader: Optional[Callable[[], tuple]] = None,
    cpu_counter: Optional[Callable[[], Optional[int]]] = None,
    environ: Optional[Dict[str, str]] = None,
) -> ResourceSnapshot:
    """Detect the resources of the current machine.

    Every probe is injectable so tests can cover hardware this machine does not
    have.  Failures are recorded as notes and ``None`` values, never raised.
    """
    environ = os.environ if environ is None else environ
    notes: List[str] = []
    cpu = (cpu_counter or os.cpu_count)()
    total, available = (memory_reader or read_system_memory)()
    if total is None:
        notes.append("System RAM could not be detected.")
    probe = device_probe or _probe_torch_devices
    try:
        probed = probe()
        if len(probed) == 3:
            devices, backends, backend_versions = probed
        else:  # pragma: no cover - injected two-tuple probe
            devices, backends = probed
            backend_versions = {}
    except Exception as exc:  # pragma: no cover - defensive
        devices, backends, backend_versions = [], {}, {}
        notes.append(f"Device detection failed: {type(exc).__name__}: {exc}")
    visible = environ.get("CUDA_VISIBLE_DEVICES")
    if visible:
        notes.append(
            f"CUDA_VISIBLE_DEVICES={visible}: device indices are renumbered; logical and physical ids are reported."
        )
    if not any(d.kind in ("cuda", "mps") for d in devices):
        notes.append("No accelerated device detected - CPU-only execution.")
    if any(d.vram_total_bytes is None for d in devices if d.kind == "cuda"):
        notes.append("Free/total VRAM could not be read for at least one device.")
    devices = list(devices) + [
        DeviceInfo(
            id="cpu",
            name=platform.processor() or "CPU",
            kind="cpu",
            backend="cpu",
            vram_total_bytes=None,
            vram_free_bytes=None,
        )
    ]
    return ResourceSnapshot(
        cpu_count=cpu,
        ram_total_bytes=total,
        ram_available_bytes=available,
        devices=devices,
        backends=backends,
        backend_versions=backend_versions,
        visible_devices_env=visible,
        notes=notes,
        captured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def device_budget(resources: ResourceSnapshot, device_id: str) -> Optional[int]:
    """Usable bytes for one device: currently free VRAM minus the reserve.

    ``None`` when the free VRAM is unknown - the caller must then treat the
    budget as unknown instead of assuming it is zero (or unlimited).
    """
    device = resources.device(device_id)
    if device is None or device.kind != "cuda":
        return None
    if device.vram_free_bytes is None:
        return None
    reserve = RESERVE_MIN_BYTES
    if device.vram_total_bytes:
        reserve = max(reserve, int(device.vram_total_bytes * RESERVE_FRACTION))
    return max(0, int(device.vram_free_bytes) - reserve)


def _vram_class(total_bytes: Optional[int]) -> Optional[int]:
    if not total_bytes:
        return None
    gib = total_bytes / GIB
    for upper in VRAM_CLASSES:
        if gib <= upper:
            return upper
    return VRAM_CLASSES[-1]


def recommend_profiles(
    resources: ResourceSnapshot,
    catalog: Optional[Iterable[Dict[str, Any]]] = None,
    workload: str = "music",
) -> List[Dict[str, Any]]:
    """Recommend working profiles with a reason and an explicit confidence.

    Each entry is ``{"id", "label", "device", "budget_bytes", "confidence",
    "reason", "notes"}``.  ``device_file_size_is_only_a_lower_bound`` is part of
    the documentation on purpose: a GGUF's file size is a lower bound for its
    resident footprint (context/KV, compute buffers and backend overhead are
    extra), so it is never used as a sufficient fit test here.
    """
    recommendations: List[Dict[str, Any]] = []
    low_ram = resources.ram_available_bytes is not None and resources.ram_available_bytes < _LOW_RAM_BYTES
    ram_unknown = resources.ram_available_bytes is None

    def _notes() -> List[str]:
        out: List[str] = []
        if low_ram:
            out.append(
                "Little free RAM: do not simply increase CPU offload - free memory first or use a smaller model."
            )
        if ram_unknown:
            out.append("Free RAM unknown; the recommendation is conservative.")
        if resources.visible_devices_env:
            out.append("Device indices are renumbered by CUDA_VISIBLE_DEVICES.")
        if len(resources.accelerators) > 1:
            out.append(
                f"{len(resources.accelerators)} GPUs detected; they are separate memory pools, budgets are per device."
            )
        return out

    if resources.is_cpu_only:
        if resources.backends.get("torch") is False or not resources.backends:
            reason = "No accelerated device and no CUDA backend detected."
        else:
            reason = "No accelerated device detected."
        recommendations.append(
            {
                "id": "cpu_only",
                "label": "CPU only",
                "device": "cpu",
                "budget_bytes": resources.ram_available_bytes,
                "confidence": "missing" if ram_unknown else ("low" if low_ram else "medium"),
                "reason": reason,
                "loader": "small models first; large models are not automatically pushed to CPU",
                "notes": _notes(),
            }
        )
        return recommendations

    for device in resources.accelerators:
        budget = device_budget(resources, device.id)
        vram_class = _vram_class(device.vram_total_bytes)
        if device.vram_free_bytes is None or device.vram_total_bytes is None:
            confidence = "missing"
            reason = f"VRAM of {device.id} could not be read; treat the budget as unknown."
        elif budget == 0:
            confidence = "low"
            reason = f"{device.id} has less free memory than the reserve; free memory or pick another device."
        elif (device.vram_free_bytes / device.vram_total_bytes) < 0.25:
            confidence = "low"
            reason = f"{device.id} is largely occupied; the budget already subtracts the reserve."
        else:
            confidence = "medium"
            reason = (
                f"{device.id} has {device.vram_free_bytes / GIB:.1f} GiB free of "
                f"{device.vram_total_bytes / GIB:.1f} GiB (class <= {vram_class} GiB)."
            )
        recommendations.append(
            {
                "id": f"gpu_{vram_class or 'unknown'}_{device.id.replace(':', '_')}",
                "label": f"GPU {device.id} (<= {vram_class} GiB class)" if vram_class else f"GPU {device.id}",
                "device": device.id,
                "budget_bytes": budget,
                "confidence": confidence,
                "reason": reason,
                "workload": workload,
                "notes": _notes(),
            }
        )
    return recommendations


def format_resource_report(resources: ResourceSnapshot) -> List[str]:
    """Human-readable lines for the diagnostics script and the UI."""
    lines = [f"CPU cores: {resources.cpu_count if resources.cpu_count is not None else 'unknown'}"]
    if resources.ram_total_bytes is None:
        lines.append("RAM: unknown")
    else:
        available = resources.ram_available_bytes
        lines.append(
            f"RAM: {resources.ram_total_bytes / GIB:.1f} GiB total"
            + (f", {available / GIB:.1f} GiB available" if available is not None else ", available unknown")
        )
    for device in resources.devices:
        if device.kind == "cpu":
            continue
        if device.vram_total_bytes is None:
            vram = "VRAM unknown"
        else:
            free = device.vram_free_bytes
            vram = f"{device.vram_total_bytes / GIB:.1f} GiB total"
            if free is not None:
                vram += f", {free / GIB:.1f} GiB free"
        lines.append(f"Device {device.id} ({device.name}, {device.backend}): {vram}")
    for name, version in sorted(resources.backend_versions.items()):
        lines.append(f"Backend {name}: {version}")
    for note in resources.notes:
        lines.append(f"Note: {note}")
    for recommendation in recommend_profiles(resources):
        lines.append(
            f"Recommendation [{recommendation['id']}] ({recommendation['confidence']}): "
            f"{recommendation['reason']}"
        )
    return lines
