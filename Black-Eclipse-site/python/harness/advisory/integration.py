"""The Fiduciary Gate's integration seam (`graph.execute_run`).

Keeps the answer-seam wiring to a few lines in `graph.py`: build the collector,
run the gate over the final answer, and attach the verdict to the run's blob.
Thin by design — all logic lives in `collector.py` and `gate.py`.
"""

from __future__ import annotations

from typing import Any, Optional

from .collector import AdvisoryCollector


def new_collector() -> AdvisoryCollector:
    return AdvisoryCollector()


async def verify(
    answer: str, collector: AdvisoryCollector, emitter: Any = None,
) -> tuple[str, Optional[dict[str, Any]]]:
    """Run the gate over `answer` against the collector's computations."""
    from .gate import apply  # noqa: PLC0415

    return await apply(
        answer,
        collector.computations(),
        consulted=collector.consulted_symbols(),
        emitter=emitter,
    )


def attach(
    research_blob: Optional[dict[str, Any]], verdict: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Attach the advisory verdict to the run blob (no-op without claims)."""
    if not verdict or not verdict.get("claims"):
        return research_blob
    blob = dict(research_blob or {})
    metadata = dict(blob.get("metadata") or {})
    metadata["advisoryIntegrity"] = verdict
    blob["metadata"] = metadata
    blob.setdefault("status", "collected")
    blob.setdefault("collected", True)
    return blob


__all__ = ["attach", "new_collector", "verify"]
