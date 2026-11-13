"""Run-level flag snapshot (W0).

The snapshot makes a run reproducible after a flag default changes: every run
records the effective values it started under, both as a durable `run.flags`
event and under `HarnessRun.context.flags`.

The snapshot is additive. It does not mutate the run's input, prompt, tool
surface or model choice. A failure to record it is a diagnostic, never a run
failure.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .config import flags


def snapshot() -> dict[str, str]:
    """The effective values of every declared flag."""
    return flags.snapshot()


def merge_context(
    context: Optional[Mapping[str, Any]],
    values: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Return `context` with `flags` and `flagsHash` added.

    Existing keys (for example `status`, `windowKnown`, or a prior run's
    context) are preserved. Re-recording on resume replaces only the flag map,
    so a resumed run records the flags it actually resumed under.
    """
    effective = dict(values or snapshot())
    merged: dict[str, Any] = dict(context or {})
    merged["flags"] = effective
    merged["flagsHash"] = flags.snapshot_hash(effective)
    return merged


def event_payload(values: Optional[Mapping[str, str]] = None) -> dict[str, Any]:
    effective = dict(values or snapshot())
    return {
        "flags": effective,
        "snapshotHash": flags.snapshot_hash(effective),
        "count": len(effective),
    }


async def record_run_flags(
    emitter: Any,
    store: Any,
    run_id: str,
    *,
    existing_context: Optional[Mapping[str, Any]] = None,
    runtime_id: Optional[str] = None,
) -> dict[str, str]:
    """Emit `run.flags` and persist the same snapshot on the run row.

    Fail-open: observability must never break a run. Returns the snapshot so the
    caller can merge it into a later context blob without re-reading env.

    W6: when `runtime_id` is supplied the write is fenced, so a stale worker
    cannot overwrite the live owner's flag snapshot. A lost lease is a
    diagnostic, not a run failure.
    """
    values = snapshot()
    try:
        await emitter.emit("run.flags", event_payload(values))
    except Exception:  # noqa: BLE001 - a missing event must not break the run
        pass
    merged = merge_context(existing_context, values)
    try:
        if runtime_id is not None:
            from .run_lease import fenced_update_run  # noqa: PLC0415

            fenced_update_run(store, run_id, runtime_id=runtime_id, context=merged)
        else:
            store.update_run(run_id, context=merged)
    except Exception:  # noqa: BLE001 - the event remains the durable record
        pass
    return values


def with_flags(
    context: Optional[Mapping[str, Any]],
    values: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Merge a captured snapshot into a context blob (success/overflow paths)."""
    return merge_context(context, values)


__all__ = [
    "event_payload",
    "merge_context",
    "record_run_flags",
    "snapshot",
    "with_flags",
]
