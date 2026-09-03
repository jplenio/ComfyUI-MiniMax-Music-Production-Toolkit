"""Production metadata JSON schema evolution policy.

The canonical production JSON (``MiniMaxSaveProductionJSON``) carries a
top-level ``schema`` field (``minimax_music3_production_metadata_vN``).  This
module is the single source of truth for that version string and the migration
map that keeps files written by older releases loadable.

Policy:

1. Never silently reinterpret existing fields.  Changes either only *add*
   fields or go through an explicit migration entry.
2. Every change to the payload shape bumps the version suffix (v6 -> v7).
3. Every removed/renamed field gets an entry in
   ``PRODUCTION_METADATA_MIGRATIONS`` that transforms an old payload into the
   next version.
4. Loaders and tooling call :func:`migrate_metadata_payload` before using a
   payload; the result is guaranteed to carry the current schema.

``minimax_music3_production_metadata_v6`` was the first versioned payload
(shipped with the early 2.0.0 tree).  ``v7`` added the complete LLM stage
(system/user prompt, raw LLM output and status), the structured-prompt summary
and the FlashSR settings record to the canonical production JSON; the v6→v7
migration only adds defaults, so old files stay loadable.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

CURRENT_PRODUCTION_METADATA_SCHEMA = "minimax_music3_production_metadata_v7"

_MAX_MIGRATION_STEPS = 20

# Old schema name -> migration function (old payload -> next payload).
PRODUCTION_METADATA_MIGRATIONS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}


def register_metadata_migration(
    from_schema: str,
    migrate: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Register one schema-version migration step (old payload -> next)."""
    if from_schema in PRODUCTION_METADATA_MIGRATIONS:
        raise ValueError(f"Metadata migration for '{from_schema}' is already registered.")
    PRODUCTION_METADATA_MIGRATIONS[from_schema] = migrate


def _v6_to_v7(payload: Dict[str, Any]) -> Dict[str, Any]:
    """v7 adds the LLM stage, the structured prompt summary and FlashSR settings."""
    data = dict(payload)
    data.setdefault("llm", {})
    data.setdefault("structured_prompt", {})
    flashsr = data.setdefault("flashsr", {})
    flashsr.setdefault("settings", {})
    data["schema"] = "minimax_music3_production_metadata_v7"
    return data


register_metadata_migration("minimax_music3_production_metadata_v6", _v6_to_v7)


def migrate_metadata_payload(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], list]:
    """Walk a payload forward to the current schema version.

    Returns ``(payload, applied_steps)`` where ``applied_steps`` lists the
    schema versions that were passed through.  Payloads already on the current
    schema are returned unchanged.  Unknown schemas raise instead of being
    silently reinterpreted.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"Production metadata payload must be a dict, got {type(payload).__name__}.")
    schema = str(payload.get("schema") or "")
    applied = []
    guard = 0
    while schema and schema != CURRENT_PRODUCTION_METADATA_SCHEMA:
        if schema not in PRODUCTION_METADATA_MIGRATIONS:
            raise ValueError(
                f"Unknown production metadata schema '{schema}'. "
                f"Current schema is '{CURRENT_PRODUCTION_METADATA_SCHEMA}'. "
                "Load the file with a newer toolkit version that knows this schema."
            )
        payload = PRODUCTION_METADATA_MIGRATIONS[schema](payload)
        guard += 1
        if guard > _MAX_MIGRATION_STEPS:
            raise RuntimeError("Production metadata migration exceeded the step limit (migration cycle?).")
        schema = str(payload.get("schema") or "")
        applied.append(schema)
    if not schema:
        raise ValueError("Production metadata payload has no 'schema' field; cannot migrate safely.")
    payload["schema"] = CURRENT_PRODUCTION_METADATA_SCHEMA
    return payload, applied
