"""Bounded auto-reproduction — the smallest safe re-run of a failure.

Diagnosis ranks hypotheses from evidence; the strongest evidence is a *successful
reproduction*. Only the caller knows how to safely re-run the failing operation
(a tool call, a compile, a scoped test), so reproduction is a REGISTRY: a caller
registers a reproducer per failure kind, and this module runs the matching one
under a hard timeout, classifying the outcome as reproduced / not-reproduced /
errored. It never mutates state beyond the reproducer's own (sandboxed, reversible
by contract) action, and it never runs more than one reproducer per call.

The result is fed back as evidence (`reproduced`) so the diagnosis can become
decisive — turning "a timeout happened" into "a timeout reproduces when the same
call is re-issued".
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .taxonomy import FailureKind, NormalizedFailure

# A reproducer returns True when the failure reproduces, False when it does not.
# It may raise (treated as an errored reproduction, never fatal).
Reproducer = Callable[[NormalizedFailure], Any]


@dataclass(frozen=True)
class ReproductionResult:
    attempted: bool
    reproduced: bool
    reproducer: Optional[str]
    detail: str = ""
    duration_ms: int = 0
    errored: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "reproduced": self.reproduced,
            "reproducer": self.reproducer,
            "detail": self.detail,
            "durationMs": self.duration_ms,
            "errored": self.errored,
        }


@dataclass
class _Entry:
    name: str
    fn: Reproducer


class ReproducerRegistry:
    def __init__(self) -> None:
        self._by_kind: dict[FailureKind, _Entry] = {}

    def register(self, kind: FailureKind, name: str, fn: Reproducer) -> None:
        self._by_kind[kind] = _Entry(name, fn)

    def get(self, kind: FailureKind) -> Optional[_Entry]:
        return self._by_kind.get(kind)

    def kinds(self) -> list[str]:
        return [k.value for k in self._by_kind]


def _maybe_await(value: Any) -> Any:
    return value


async def reproduce(
    registry: ReproducerRegistry,
    failure: NormalizedFailure,
    *,
    timeout_s: float = 10.0,
) -> ReproductionResult:
    """Run the registered reproducer for this failure kind, bounded by a timeout."""
    entry = registry.get(failure.kind)
    if entry is None:
        return ReproductionResult(attempted=False, reproduced=False, reproducer=None, detail="no reproducer")

    started = time.monotonic()
    try:
        value = entry.fn(failure)
        if asyncio.iscoroutine(value):
            value = await asyncio.wait_for(value, timeout=timeout_s)
        reproduced = bool(value)
        return ReproductionResult(
            attempted=True, reproduced=reproduced, reproducer=entry.name,
            detail="reproduced" if reproduced else "not reproduced",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except asyncio.TimeoutError:
        return ReproductionResult(
            attempted=True, reproduced=False, reproducer=entry.name,
            detail=f"reproducer timed out after {timeout_s}s", errored=True,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:  # noqa: BLE001 - an errored reproduction is data
        return ReproductionResult(
            attempted=True, reproduced=False, reproducer=entry.name,
            detail=f"reproducer error: {exc}", errored=True,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


__all__ = ["Reproducer", "ReproducerRegistry", "ReproductionResult", "reproduce"]