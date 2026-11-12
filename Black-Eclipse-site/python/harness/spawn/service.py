"""Spawn over the Execution Fabric + deterministic synthesis (C5).

A child is a normal Fabric `agent` job: the Fabric owns its lease, retry,
timeout and cancellation. The parent gets a typed `ChildOutcome`; the child's
evidence claims are copied into the parent's ledger with a `child:<runId>`
verifier, so the parent can cite them.

There is no second scheduler and no model-based merge.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any, Iterable, Optional

from ..goals import EvidenceLedger
from ..goals.ledger import digest_text
from ..run_lineage import RunLineage
from .model import (
    MAX_CHILDREN,
    MAX_DEPTH,
    MAX_TOKENS,
    ChildOutcome,
    SpawnBudget,
    SpawnSpec,
)


class SpawnError(ValueError):
    pass


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())[:400]


def _claim_value(claim: dict[str, Any]) -> tuple[Any, ...]:
    handles = claim.get("handles") or []
    return (
        claim.get("status"),
        tuple(sorted((h.get("kind"), h.get("ref")) for h in handles)),
    )


def synthesize(outcomes: Iterable[ChildOutcome]) -> dict[str, Any]:
    """Deterministic dedupe + conflict detection over child claims."""
    groups: dict[str, dict[str, Any]] = {}
    for outcome in outcomes:
        for claim in outcome.claims:
            key = _normal(claim.get("text", ""))
            if not key:
                continue
            group = groups.setdefault(key, {
                "text": claim.get("text", "")[:500],
                "children": [], "values": set(), "handles": set(),
                "statuses": set(),
            })
            if outcome.run_id:
                group["children"].append(outcome.run_id)
            group["values"].add(_claim_value(claim))
            group["statuses"].add(claim.get("status") or "unverified")
            for handle in claim.get("handles") or []:
                group["handles"].add((handle.get("kind"), handle.get("ref")))

    supported: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for key, group in groups.items():
        entry = {
            "text": group["text"],
            "children": sorted(set(group["children"])),
            "statuses": sorted(group["statuses"]),
            "handles": [{"kind": k, "ref": r} for k, r in sorted(group["handles"])],
        }
        if len(group["values"]) > 1:
            conflicts.append({**entry, "reason": "children disagree on value/evidence"})
        elif "unsupported" in group["statuses"]:
            dropped.append({**entry, "reason": "rejected by a verifier"})
        elif "supported" in group["statuses"]:
            supported.append(entry)
        else:
            dropped.append({**entry, "reason": "unverified"})

    lines = [
        f"children: {len(list(outcomes))}",
        f"supported: {len(supported)} | conflicts: {len(conflicts)} | dropped: {len(dropped)}",
    ]
    for item in supported[:8]:
        lines.append(f"- {item['text']}")
    for item in conflicts[:8]:
        lines.append(f"- CONFLICT: {item['text']} ({item['reason']})")
    return {
        "supported": supported[:24],
        "conflicts": conflicts[:16],
        "dropped": dropped[:16],
        "text": "\n".join(lines)[:8_000],
    }


def reconcile_budget(
    specs: list[SpawnSpec], outcomes: list[ChildOutcome],
) -> dict[str, Any]:
    """The budget tree's accounting: allocated = used + returned.

    Allocation is reserved up front from the clamped child specs; usage is what
    each child reported. Unused allocation is RETURNED, never silently spent.
    """
    allocated = sum(spec.budget.clamped().tokens for spec in specs)
    used = sum(int(outcome.tokens_used or 0) for outcome in outcomes)
    used = max(0, min(used, allocated))
    return {
        "allocated": allocated,
        "used": used,
        "returned": allocated - used,
        "exhausted": used >= allocated,
    }


def _depth(store: Any, run_id: str) -> int:
    try:
        lineage = RunLineage(store).lineage(run_id).get("parents") or []
        return len(lineage)
    except Exception:  # noqa: BLE001 - an unknown parent is depth 0
        return 0


def _copy_evidence(store: Any, parent_run_id: str, child: ChildOutcome) -> None:
    if not child.run_id:
        return
    ledger = EvidenceLedger(store)
    existing = {claim.verifier for claim in ledger.claims(parent_run_id)}
    marker = f"child:{child.run_id}"
    if marker in existing:
        return
    for claim in child.claims[:32]:
        ledger.record(
            run_id=parent_run_id,
            text=str(claim.get("text", ""))[:4_000],
            handles=claim.get("handles") or [],
            status=claim.get("status") or "unverified",
            verifier=marker,
        )


async def spawn_child(
    spec: SpawnSpec, ctx: Any, *, parent_run_id: Optional[str] = None,
    fabric: Any = None,
) -> ChildOutcome:
    """Spawn one child as a Fabric `agent` job and return its typed outcome."""
    from ..fabric.tools import get_fabric_manager  # noqa: PLC0415

    parent = parent_run_id or str(getattr(ctx, "run_id", "") or "")
    store = getattr(ctx, "memory_store", None)
    if store is None or not parent:
        return ChildOutcome(
            status="failed", error="spawn needs a run and a memory store",
            error_class="RUNTIME_UNAVAILABLE",
        )
    objective = str(spec.objective or "").strip()
    if not objective:
        return ChildOutcome(status="failed", error="empty objective",
                            error_class="INVALID_INPUT")

    depth = _depth(store, parent)
    if depth >= MAX_DEPTH:
        return ChildOutcome(
            status="refused", error=f"spawn depth {depth} exceeds {MAX_DEPTH}",
            error_class="DEPTH_EXCEEDED",
        )
    fabric = fabric or get_fabric_manager()
    if fabric is None:
        return ChildOutcome(
            status="failed", error="the Execution Fabric is unavailable",
            error_class="RUNTIME_UNAVAILABLE",
        )

    budget = spec.budget.clamped()
    payload = {
        "query": objective[:4_000],
        "agentId": spec.agent,
        "modelSettings": spec.model,
        "parentRunId": parent,
        "userId": getattr(ctx, "user_id", None),
        "workspaceId": getattr(ctx, "workspace_id", None),
        "sessionId": getattr(ctx, "session_id", None),
        "maxSteps": budget.steps,
        "runTimeoutMs": budget.timeout_s * 1000,
        "context": {
            "source": "spawn",
            "spawnDepth": depth + 1,
            "boardRootRunId": parent,
            "budget": budget.to_dict(),
        },
    }
    try:
        result = await fabric.submit(
            "agent", payload,
            worker_kind="agent",
            await_result=not spec.background,
            timeout_ms=budget.timeout_s * 1000,
            max_attempts=1,
            correlation_id=parent,
            idempotency_key=f"spawn:{parent}:{uuid.uuid4().hex}",
        )
    except Exception as exc:  # noqa: BLE001 - a spawn failure is data
        return ChildOutcome(status="failed", error=str(exc)[:2_000],
                            error_class="SPAWN_FAILED")

    if not isinstance(result, dict):
        return ChildOutcome(status="failed", error="the Fabric returned no result",
                            error_class="SPAWN_FAILED")
    job_id = str(result.get("jobId") or "")
    if spec.background:
        return ChildOutcome(status="queued", job_id=job_id)

    status = str(result.get("status") or "").upper()
    outcome = result.get("outcome") if isinstance(result.get("outcome"), dict) else {}
    metrics = outcome.get("metrics") if isinstance(outcome, dict) else {}
    run_id = str((metrics or {}).get("runId") or "")
    child = ChildOutcome(
        status="completed" if status in ("SUCCEEDED", "COMPLETED") else "failed",
        run_id=run_id,
        job_id=job_id,
        output=str(result.get("output") or ""),
        tokens_used=int((metrics or {}).get("totalTokens") or 0),
        error=str(result.get("error") or ""),
        error_class=str(result.get("errorClass") or ""),
    )
    if run_id:
        claims = EvidenceLedger(store).claims(run_id)
        child.claims = [claim.to_dict() for claim in claims]
        child.artifacts = [
            handle.to_dict()
            for claim in claims
            for handle in claim.handles
            if handle.kind == "artifact"
        ][:16]
        _copy_evidence(store, parent, child)
    return child


async def spawn_many(
    specs: list[SpawnSpec], ctx: Any, *, parent_run_id: Optional[str] = None,
) -> list[ChildOutcome]:
    if len(specs) > MAX_CHILDREN:
        return [ChildOutcome(
            status="refused", error=f"at most {MAX_CHILDREN} children",
            error_class="CHILD_LIMIT",
        )]
    total_tokens = sum(spec.budget.clamped().tokens for spec in specs)
    if total_tokens > MAX_TOKENS:
        return [ChildOutcome(
            status="refused",
            error=f"child token allocations total {total_tokens}, over {MAX_TOKENS}",
            error_class="BUDGET_EXCEEDED",
        )]
    return list(await asyncio.gather(*[
        spawn_child(spec, ctx, parent_run_id=parent_run_id) for spec in specs
    ]))


def spec_from_dict(raw: dict[str, Any]) -> SpawnSpec:
    budget_raw = raw.get("budget") if isinstance(raw.get("budget"), dict) else {}
    budget = SpawnBudget(
        tokens=int(budget_raw.get("tokens") or budget_raw.get("tokensBudget") or 120_000),
        steps=int(budget_raw.get("steps") or 24),
        timeout_s=int(budget_raw.get("timeout_s") or budget_raw.get("timeoutS") or 900),
    )
    model = raw.get("model") if isinstance(raw.get("model"), dict) else None
    return SpawnSpec(
        objective=str(raw.get("objective") or raw.get("query") or ""),
        agent=str(raw.get("agent") or raw.get("agentId") or "eclipse-agent"),
        budget=budget.clamped(),
        board=str(raw.get("board") or "shared"),
        background=bool(raw.get("background") or False),
        model=model,
    )


__all__ = [
    "SpawnError",
    "spec_from_dict",
    "spawn_child",
    "spawn_many",
    "synthesize",
]
