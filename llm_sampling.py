"""Model-family adapters, context planning and runtime options (L02).

Three small, testable services that the LLM node uses - and that stay honest
about what the installed backend can actually do:

* **Family adapters** describe a GGUF family (chat template, whether thinking can
  really be switched off, documented sampler values for the *non-thinking* case).
  They are versioned (``ADAPTER_VERSION``) so a behaviour change is a visible
  change, and they never override a stored workflow value by themselves.
* **Context planning** picks the smallest context from the documented candidates
  (4k/8k/16k/32k) that holds the tokenized input estimate *plus* the output
  budget *plus* a safety reserve.  It never plans below the input: an overflow is
  reported before generation instead of being silently truncated.
* **Runtime options** (``n_batch``, ``n_ubatch``, ``flash_attn``, KV types, CPU
  thread count) are only offered when the installed ``llama_cpp`` build declares
  the corresponding parameter; unsupported requests are reported, not dropped
  silently.  Accepted options become part of the model cache identity, because
  two different runtime configurations are two different model instances.

Nothing here loads a model or touches the network.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Tuple

ADAPTER_VERSION = "1"

# Documented context candidates (L02).  The planner returns one of these.
CONTEXT_CANDIDATES: Tuple[int, ...] = (4096, 8192, 16384, 32768)
DEFAULT_OUTPUT_TOKENS = 4096
DEFAULT_RESERVE_TOKENS = 512
# Same conservative estimate basis as the MiniMax prompt budget.  This is an
# estimate for planning a context; the authoritative number after a run comes
# from the backend's own usage report.
ESTIMATE_CHARS_PER_TOKEN = 3.5

RUNTIME_OPTION_NAMES = ("n_batch", "n_ubatch", "flash_attn", "type_k", "type_v", "n_threads")
KV_TYPES = ("f16", "f32", "bf16", "q8_0", "q5_1", "q5_0", "q4_1", "q4_0")
# Values worth benchmarking first (the task names these explicitly).
N_UBATCH_CANDIDATES = (128, 256, 512)


@dataclass(frozen=True)
class FamilyAdapter:
    """What is documented and supportable for one model family."""

    id: str
    label: str
    match: Tuple[str, ...]
    chat_format: str
    thinking: str  # "reasoning_budget" | "template_kwarg" | "unsupported"
    non_thinking_sampling: Dict[str, float] = field(default_factory=dict)
    note: str = ""

    def matches(self, model_name: str) -> bool:
        lowered = (model_name or "").lower()
        return any(fragment in lowered for fragment in self.match)


# Versioned adapters.  The first match wins, so the specific entries come first.
FAMILY_ADAPTERS: Tuple[FamilyAdapter, ...] = (
    FamilyAdapter(
        id="qwen3.8",
        label="Qwen 3.8",
        match=("qwen3.8", "qwen3_8", "qwen-3.8", "qwen3-8"),
        chat_format="chatml",
        thinking="reasoning_budget",
        # From the model card's non-thinking recommendation.  Applied only when a
        # profile explicitly asks for the family preset - never automatically.
        non_thinking_sampling={"temperature": 0.7, "top_p": 0.8, "top_k": 20, "repeat_penalty": 1.0},
        note="Non-thinking sampler values follow the Qwen 3.8 model card.",
    ),
    FamilyAdapter(
        id="qwen3.5",
        label="Qwen 3.5",
        match=("qwen3.5", "qwen3_5", "qwen-3.5", "qwen3-5"),
        chat_format="chatml",
        thinking="reasoning_budget",
        note="Same ChatML handling as the rest of the Qwen family.",
    ),
    FamilyAdapter(
        id="qwen",
        label="Qwen (generic)",
        match=("qwen",),
        chat_format="chatml",
        thinking="reasoning_budget",
    ),
    FamilyAdapter(
        id="gemma4",
        label="Gemma 4",
        match=("gemma-4", "gemma4", "gemma_4", "gemma-3", "gemma3"),
        # Gemma's own embedded template is the verified choice; ChatML breaks it.
        chat_format="none",
        thinking="unsupported",
        note="Verified against Gemma 4 with llama-cpp-python 0.3.48; the model emits <|channel> markers.",
    ),
    FamilyAdapter(
        id="llama3",
        label="Llama 3",
        match=("llama-3", "llama3", "llama_3"),
        chat_format="llama-3",
        thinking="unsupported",
    ),
    FamilyAdapter(
        id="generic",
        label="Generic GGUF",
        match=(),
        chat_format="chatml",
        thinking="unsupported",
        note="Fallback: the model's embedded template is used when chat_format is 'none'.",
    ),
)


def detect_family(model_name: str) -> FamilyAdapter:
    """The adapter for a model file name (never ``None``)."""
    for adapter in FAMILY_ADAPTERS:
        if adapter.matches(model_name):
            return adapter
    return FAMILY_ADAPTERS[-1]


def estimate_input_tokens(text: str, chars_per_token: float = ESTIMATE_CHARS_PER_TOKEN) -> int:
    """Conservative plan-time estimate of the input token count."""
    if not text:
        return 0
    return math.ceil(len(text) / max(0.5, float(chars_per_token)))


def plan_context(
    input_chars: int,
    output_tokens: int = DEFAULT_OUTPUT_TOKENS,
    reserve_tokens: int = DEFAULT_RESERVE_TOKENS,
    candidates: Sequence[int] = CONTEXT_CANDIDATES,
) -> Dict[str, Any]:
    """Choose the smallest candidate context that fits; never below the input.

    ``input_chars`` is the raw character count of the prompt (system + user +
    template overhead).  Returns the chosen context, the estimate it was based
    on, and ``fits=False`` with a clear reason when even the largest candidate
    cannot hold input + output + reserve - a case that must be reported before
    generation instead of truncated silently.
    """
    ordered = sorted(int(value) for value in candidates)
    if not ordered:
        raise ValueError("no context candidates configured")
    estimated_input = estimate_input_tokens("x" * max(0, int(input_chars)))
    needed = estimated_input + max(0, int(output_tokens)) + max(0, int(reserve_tokens))
    largest = ordered[-1]
    if needed > largest:
        return {
            "context": largest,
            "estimated_input_tokens": estimated_input,
            "needed_tokens": needed,
            "fits": False,
            "method": "estimate",
            "reason": (
                f"The estimated prompt ({estimated_input} tokens) plus the output budget "
                f"({int(output_tokens)}) and the reserve ({int(reserve_tokens)}) needs {needed} tokens, "
                f"more than the largest context candidate ({largest}). Shorten the prompt or the output "
                f"budget; the input is never truncated silently."
            ),
        }
    for candidate in ordered:
        if candidate >= needed:
            return {
                "context": candidate,
                "estimated_input_tokens": estimated_input,
                "needed_tokens": needed,
                "fits": True,
                "method": "estimate",
                "reason": (
                    f"Smallest candidate that holds the estimated prompt ({estimated_input} tokens), the "
                    f"output budget ({int(output_tokens)}) and the reserve ({int(reserve_tokens)})."
                ),
            }
    return {  # pragma: no cover - unreachable with a positive candidate list
        "context": largest,
        "estimated_input_tokens": estimated_input,
        "needed_tokens": needed,
        "fits": False,
        "method": "estimate",
        "reason": "No context candidate fits.",
    }


def thinking_support(adapter: FamilyAdapter, accepts: Callable[[str], bool]) -> Dict[str, Any]:
    """Whether *this* build can actually switch thinking off for this family.

    Merely removing ``<think>`` tags from the answer is not a speedup, so an
    unsupported switch is reported as unsupported instead of being implied.
    """
    if adapter.thinking == "reasoning_budget" and accepts("reasoning_budget"):
        return {
            "supported": True,
            "mechanism": "reasoning_budget=0",
            "message": "This build accepts reasoning_budget, so thinking can be switched off during generation.",
        }
    if accepts("chat_template_kwargs"):
        return {
            "supported": True,
            "mechanism": "chat_template_kwargs",
            "message": "The template switch is passed through chat_template_kwargs.",
        }
    return {
        "supported": False,
        "mechanism": None,
        "message": (
            f"This llama-cpp-python build can{'not' if adapter.thinking != 'unsupported' else 'not'} switch "
            "thinking off for this family. The toggle only separates reasoning from the answer afterwards and "
            "is therefore not a speedup - expect the same generation time."
        ),
    }


def validate_runtime_option(name: str, value: Any) -> Tuple[bool, str]:
    """Shape check for one runtime option (capability is checked separately)."""
    if name in ("n_batch", "n_ubatch", "n_threads"):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return False, f"{name} must be a positive integer"
        return True, ""
    if name == "flash_attn":
        if not isinstance(value, bool):
            return False, "flash_attn must be a boolean"
        return True, ""
    if name in ("type_k", "type_v"):
        if str(value).lower() not in KV_TYPES:
            return False, f"{name} must be one of {', '.join(KV_TYPES)}"
        return True, ""
    return False, f"unknown runtime option '{name}'"


def build_runtime_options(
    requested: Optional[Dict[str, Any]],
    accepts: Callable[[str], bool],
) -> Dict[str, Any]:
    """Split requested runtime options into accepted and unsupported ones.

    ``accepts(name)`` must answer whether the installed build declares that
    parameter (``llm_chat._accepts_kwarg``).  The accepted options go into the
    model options - and therefore into the model cache identity - while the
    unsupported ones are reported with a reason.
    """
    accepted: Dict[str, Any] = {}
    unsupported: Dict[str, str] = {}
    for name, value in (requested or {}).items():
        if value is None:
            continue
        if name not in RUNTIME_OPTION_NAMES:
            # An unknown option is reported, not dropped: a silent ignore would
            # let a typo look like a supported setting.
            unsupported[name] = f"unknown runtime option '{name}'"
            continue
        ok, problem = validate_runtime_option(name, value)
        if not ok:
            unsupported[name] = problem
            continue
        if not accepts(name):
            unsupported[name] = "not supported by the installed llama-cpp-python build"
            continue
        accepted[name] = value
    return {"options": accepted, "unsupported": unsupported}


def sampling_for(model_name: str, thinking: str = "off") -> Dict[str, float]:
    """Documented sampler values for the non-thinking case, or ``{}``.

    Only a family that documents the values returns them, and only for
    ``thinking="off"``.  The caller decides whether a *new* profile wants them;
    stored workflow values are never overwritten by this module.
    """
    if (thinking or "").strip().lower() != "off":
        return {}
    adapter = detect_family(model_name)
    return dict(adapter.non_thinking_sampling)


def adapter_report(model_name: str, accepts: Callable[[str], bool]) -> Dict[str, Any]:
    """Everything the node logs about the family/template/thinking decision."""
    adapter = detect_family(model_name)
    return {
        "adapter_version": ADAPTER_VERSION,
        "family": adapter.id,
        "label": adapter.label,
        "chat_format": adapter.chat_format,
        "thinking": thinking_support(adapter, accepts),
        "non_thinking_sampling": dict(adapter.non_thinking_sampling),
        "note": adapter.note,
    }


def format_adapter_lines(report: Dict[str, Any]) -> list:
    """Readable lines for the log and the node's status text."""
    thinking = report.get("thinking") or {}
    return [
        f"LLM family: {report.get('label')} (adapter {report.get('adapter_version')}, "
        f"chat_format={report.get('chat_format')})",
        f"  thinking control: {'supported' if thinking.get('supported') else 'NOT supported'} "
        f"- {thinking.get('message')}",
    ]
