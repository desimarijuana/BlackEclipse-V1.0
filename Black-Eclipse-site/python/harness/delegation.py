"""Bounded fan-out of child runs, and honest aggregation of their results.

A child is a normal run: same graph, same registry, same policy engine, same
persistence. The only things this module owns are the BUDGET, the NARROWING, and
the AGGREGATION rule. It never executes anything itself and never talks to a
model.

The narrowing rule (``child_actor``) is the safety core: a child holds the
parent's grants INTERSECTED with the child's scope, never a superset, and it
NEVER inherits the ``operator`` flag — an operator flag is proof of *who called*,
and a child did not make that call, so inheriting it would launder authority.

The aggregation rule (``aggregate``) is the honesty core: a child's PROSE is
quoted; a child's CLAIM is repeated only when it carries a handle the parent can
re-check (a run id that exists, a path inside the workspace, a check record in
the Phase 4 ledger). A claim with no handle goes to ``dropped_claims`` and is
rendered as unconfirmed — never silently discarded.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .skills.permissions import Actor, OPERATOR_PERMISSIONS

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

# ── Caps ─────────────────────────────────────────────────────────────────────
MAX_CHILDREN: int = 4          # per delegation
MAX_DEPTH: int = 2             # parent → child → grandchild; beyond this, refused
DEFAULT_CHILD_TIMEOUT_S: int = 900
DEFAULT_CHILD_TOKEN_BUDGET: int = 120_000
MIN_TOKENS_PER_CHILD: int = 1_000
# Bounded concurrency: a desktop app, not a server.
MAX_IN_FLIGHT: int = 4

# Structured refusal codes (§6.3).
WIDTH_EXCEEDED = "DELEGATION_WIDTH_EXCEEDED"
DEPTH_EXCEEDED = "DELEGATION_DEPTH_EXCEEDED"
TOOL_NOT_HELD = "DELEGATION_TOOL_NOT_HELD"
PERMISSION_NOT_HELD = "DELEGATION_PERMISSION_NOT_HELD"
BUDGET_EXHAUSTED = "DELEGATION_BUDGET_EXHAUSTED"
SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"


class DelegationError(ValueError):
    """A structured refusal. ``code`` is stable and testable."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


# ── Contracts (§6.1) ─────────────────────────────────────────────────────────


class DelegationChild(BaseModel):
    model_config = _CAMEL

    goal: str = Field(..., max_length=2000)
    context: str = Field("", max_length=8000)     # background THIS child needs
    agent_id: Optional[str] = None                # defaults to the parent's agent
    tool_subset: Optional[list[str]] = None       # must be ⊆ the parent's allowlist
    workspace_id: Optional[str] = None            # writing children only


Aggregate = Literal["list", "compare", "merge_claims"]
ChildStatus = Literal["completed", "failed", "timed_out", "refused", "cancelled"]


class DelegationRequest(BaseModel):
    model_config = _CAMEL

    # The BOUND here is deliberately looser than `MAX_CHILDREN` so the cap fires
    # in `run_delegation` with the structured `DELEGATION_WIDTH_EXCEEDED` code
    # (a pydantic rejection would leave no code and no recorded reason).
    children: list[DelegationChild] = Field(..., min_length=1, max_length=8)
    aggregate: Aggregate = "list"
    token_budget: int = Field(DEFAULT_CHILD_TOKEN_BUDGET, ge=1_000, le=2_000_000)


HandleKind = Literal["path", "run_id", "artifact_digest", "check_record_id", "citation"]


@dataclass(frozen=True)
class VerifiableHandle:
    kind: HandleKind
    value: str


class ChildOutcome(BaseModel):
    model_config = _CAMEL

    child_index: int
    run_id: Optional[str] = None               # None when the child never started
    status: ChildStatus
    summary: str = ""                          # the child's own words — UNTRUSTED
    handles: list[VerifiableHandle] = Field(default_factory=list)
    reason: Optional[str] = None               # plain sentence on failure/refusal
    claimed: list[str] = Field(default_factory=list)      # assertions with a handle
    dropped: list[str] = Field(default_factory=list)      # assertions with NO handle


class BudgetReport(BaseModel):
    model_config = _CAMEL

    requestedTokens: int = DEFAULT_CHILD_TOKEN_BUDGET  # noqa: N815
    consumedTokens: int = 0  # noqa: N815
    children: int = 0
    inFlightMax: int = MAX_IN_FLIGHT  # noqa: N815
    timedOut: int = 0  # noqa: N815
    wallMs: int = 0  # noqa: N815


class DelegationResult(BaseModel):
    model_config = _CAMEL

    delegationId: str  # noqa: N815
    outcomes: list[ChildOutcome] = Field(default_factory=list)
    aggregate: str = ""
    droppedClaims: list[str] = Field(default_factory=list)  # noqa: N815
    budget: BudgetReport = Field(default_factory=BudgetReport)
    workflowId: Optional[str] = None  # noqa: N815

    def to_blob(self) -> dict[str, Any]:
        """A bounded JSON blob for `HarnessRun.delegation`."""
        return {
            "delegationId": self.delegationId,
            "workflowId": self.workflowId,
            "children": [
                {
                    "childIndex": o.child_index, "runId": o.run_id, "status": o.status,
                    "handles": [{"kind": h.kind, "value": h.value} for h in o.handles],
                    "reason": o.reason, "claimed": o.claimed[:20], "dropped": o.dropped[:20],
                }
                for o in self.outcomes
            ],
            "droppedClaims": self.droppedClaims[:20],
            "budget": self.budget.model_dump(by_alias=True),
        }


# ── Narrowing (§6.2) ─────────────────────────────────────────────────────────


def child_actor(parent: Actor, child: DelegationChild) -> Actor:
    """A child holds the parent's grants INTERSECTED with the child's scope.

    - never a superset: scopes only ever narrow (`permissions.Actor.granted`)
    - never a new permission class: code.* only if the parent held it
    - never a wider workspace: the child's workspace is one the parent already had
    - `operator` is NEVER inherited: a child is never an operator, so it can
      never approve its own effectful action or enable a skill.
    """
    parent_grants = parent.granted()
    # `operator` is deliberately omitted (defaults to False). The parent's
    # operator-only grants (skill.create/review/enable/disable/portfolio.modify)
    # are NEVER passed down — they can only be held by an actor that PROVED
    # operator authorization for this exact call, which a child has not.
    grants = frozenset(parent_grants - OPERATOR_PERMISSIONS)
    scopes = frozenset(grants)
    # A writing child keeps the parent's workspace; a read-only child gets none.
    workspace_id = child.workspace_id
    if workspace_id is not None and workspace_id != getattr(parent, "workspace_id", None):
        raise DelegationError(
            PERMISSION_NOT_HELD,
            "A child cannot work in a folder its parent does not already have.",
        )
    return Actor(
        id=f"child:{parent.id}",
        operator=False,               # NEVER inherited — this is the laundering guard
        grants=grants,
        scopes=scopes,
        workspace_id=workspace_id,
        autonomy=getattr(parent, "autonomy", None) if workspace_id else None,
    )


def narrow_tools(parent_allowed: Optional[set[str]], child: DelegationChild) -> Optional[set[str]]:
    """The child's tool set: a requested subset, or the parent's own allowlist.

    A requested tool the parent does not hold is refused with
    `DELEGATION_TOOL_NOT_HELD`. ``None`` on either side means "no allowlist" (the
    unrestricted case), and a child can still only narrow, never widen.
    """
    if child.tool_subset is None:
        return set(parent_allowed) if parent_allowed is not None else None
    requested = set(child.tool_subset)
    if parent_allowed is None:
        return requested
    missing = sorted(requested - parent_allowed)
    if missing:
        raise DelegationError(
            TOOL_NOT_HELD,
            f"This child asked for {missing[0]}, which this task isn't allowed to use.",
        )
    return requested


# ── Aggregation (§6.4) ───────────────────────────────────────────────────────


# Deterministic pass-claim patterns — the same discipline as
# `code/verify.CLAIM_PATTERNS`. A negation is not a claim.
import re  # noqa: E402

_CLAIM_RE = re.compile(
    r"\b(all\s+|the\s+)?tests?\s+(pass|passed|are\s+passing|are\s+green)\b"
    r"|\bbuild\s+(succeeds|succeeded|passes|passed)\b"
    r"|\btype[\s-]?check(ing)?\s+(passes|passed|is\s+clean)\b",
    re.I,
)
_NEGATION_RE = re.compile(r"\b(not|no|never|did\s?n'?t|could\s?n'?t|failed|skipped)\b", re.I)


@dataclass
class HandleVerifier:
    """Re-checks handles against real state — no handle is trusted on the say-so.

    `run_exists(run_id)` and `ledger_has(check_record_id)` are injected so this
    value object never reaches a store or a global; the tool supplies them from
    the runtime it already holds.
    """

    run_exists: Callable[[str], bool] = lambda _rid: False
    ledger_has: Callable[[str], bool] = lambda _cid: False
    artifact_exists: Callable[[str], bool] = lambda _digest: False

    def verify(self, handle: VerifiableHandle) -> bool:
        try:
            if handle.kind == "run_id":
                return bool(self.run_exists(handle.value))
            if handle.kind == "check_record_id":
                return bool(self.ledger_has(handle.value))
            if handle.kind == "artifact_digest":
                return bool(self.artifact_exists(handle.value))
            # A path/citation is admitted by shape; the child's run already
            # confined it. Emptiness is the only local rejection.
            return bool(handle.value)
        except Exception:  # noqa: BLE001 - a verifier failure must never confirm
            return False


def _claim_sentences(summary: str) -> list[str]:
    out: list[str] = []
    for line in re.split(r"[\n]+", summary or ""):
        for segment in re.split(r"(?<=[.!?])\s+", line):
            text = segment.strip()
            if text and _CLAIM_RE.search(text) and not _NEGATION_RE.search(text):
                out.append(text)
    return out[:50]


def partition_claims(
    summary: str, handles: list[VerifiableHandle], verifier: HandleVerifier,
) -> tuple[list[str], list[str]]:
    """Split a child's check-claims into (proven, dropped).

    A check-claim ("all tests pass") is a specific, re-checkable assertion, so it
    is admitted ONLY when the child supplied a `check_record_id` handle that the
    verifier CONFIRMS against a real execution record. A `run_id`, `path` or
    `citation` handle does NOT back a check-claim — a child cannot launder a
    pass-claim by attaching an unrelated handle. Everything unproven is dropped
    and rendered as unconfirmed. A child's ordinary PROSE is neither a claim nor
    dropped; it remains quoted in `summary`.
    """
    claims = _claim_sentences(summary)
    if not claims:
        return [], []
    proven = any(
        h.kind == "check_record_id" and verifier.verify(h) for h in handles
    )
    if proven:
        return claims, []
    return [], claims


def aggregate(result: DelegationResult) -> str:
    """Render the handle-backed summary. Only admitted claims become facts.

    Reads like a plain list of the *things*, never the machinery. A partial
    answer is a normal answer: the children that worked are named, and the rest
    get one sentence.
    """
    done = [o for o in result.outcomes if o.status == "completed"]
    other = [o for o in result.outcomes if o.status != "completed"]
    lines: list[str] = []
    if done:
        lines.append(f"I looked at {len(done)} of {len(result.outcomes)}: "
                     + ", ".join(o.summary.strip().split("\n")[0][:80] or f"item {o.child_index + 1}"
                                 for o in done) + ".")
        for outcome in done:
            for claim in outcome.claimed:
                lines.append(f"- {claim}")
    if other:
        names = ", ".join(f"item {o.child_index + 1}" for o in other)
        lines.append(f"I couldn't finish {names}.")
    if not done and not other:
        lines.append("I didn't have anything to look at.")
    dropped = result.droppedClaims
    if dropped:
        lines.append(
            f"{len(dropped)} statement(s) could not be confirmed, so I'm not repeating them as fact."
        )
    return "\n".join(lines)


# ── The fan-out executor ─────────────────────────────────────────────────────


async def run_delegation(
    request: DelegationRequest,
    *,
    parent_run_id: str,
    parent_actor: Actor,
    parent_allowed: Optional[set[str]],
    depth: int,
    run_child: Callable[[DelegationChild, str, Optional[set[str]], Actor], Any],
    verifier: Optional[HandleVerifier] = None,
    workflow_id: Optional[str] = None,
    child_timeout_s: int = DEFAULT_CHILD_TIMEOUT_S,
    max_in_flight: int = MAX_IN_FLIGHT,
    on_event: Optional[Callable[[str, dict[str, Any]], Any]] = None,
) -> DelegationResult:
    """Fan out bounded child runs, then aggregate only what each proved.

    ``run_child(child, child_run_id, allowed, actor)`` is the ONE execution seam a
    caller supplies — it must run the child through the EXISTING runtime (a child
    is `execute_run` with a parent link), never a second path. Caps are enforced
    here, at construction: width, depth, tool narrowing, and budget.
    """
    if len(request.children) > MAX_CHILDREN:
        raise DelegationError(
            WIDTH_EXCEEDED,
            f"This asks for {len(request.children)} at once; the most Eclipse does is {MAX_CHILDREN}.",
        )
    if depth >= MAX_DEPTH:
        raise DelegationError(
            DEPTH_EXCEEDED,
            "This work is nested too deeply for Eclipse to keep it straight.",
        )

    # Budget: each child needs at least its own floor; a request that leaves less
    # than that per child is refused rather than started and starved.
    if request.token_budget < len(request.children) * MIN_TOKENS_PER_CHILD:
        raise DelegationError(
            BUDGET_EXHAUSTED,
            "There isn't enough room to do all of these at once; try fewer at a time.",
        )

    delegation_id = "dlg_" + uuid.uuid4().hex[:16]
    started = time.monotonic()
    verifier = verifier or HandleVerifier()
    semaphore = asyncio.Semaphore(max(1, max_in_flight))
    outcomes: list[ChildOutcome] = [None] * len(request.children)  # type: ignore[list-item]

    async def _emit(event_type: str, data: dict[str, Any]) -> None:
        if on_event is None:
            return
        try:
            maybe = on_event(event_type, data)
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception:  # noqa: BLE001 - an event must never break a delegation
            pass

    await _emit("delegation.started", {"delegationId": delegation_id, "children": len(request.children)})

    async def _one(index: int, child: DelegationChild) -> None:
        try:
            actor = child_actor(parent_actor, child)
            allowed = narrow_tools(parent_allowed, child)
        except DelegationError as exc:
            outcomes[index] = ChildOutcome(
                child_index=index, status="refused", reason=exc.reason, dropped=[],
            )
            await _emit("delegation.child.refused", {
                "delegationId": delegation_id, "childIndex": index, "code": exc.code,
            })
            return
        child_run_id = f"{parent_run_id}_child{index}_{uuid.uuid4().hex[:8]}"
        await _emit("delegation.child.started", {
            "delegationId": delegation_id, "childIndex": index, "runId": child_run_id,
        })
        async with semaphore:
            try:
                raw = await asyncio.wait_for(
                    run_child(child, child_run_id, allowed, actor),
                    timeout=child_timeout_s,
                )
                outcome = _coerce_outcome(index, child_run_id, raw, verifier)
            except asyncio.TimeoutError:
                outcome = ChildOutcome(
                    child_index=index, run_id=child_run_id, status="timed_out",
                    reason="This part took too long and was stopped.",
                )
            except asyncio.CancelledError:
                outcome = ChildOutcome(
                    child_index=index, run_id=child_run_id, status="cancelled",
                    reason="This part was stopped.",
                )
                outcomes[index] = outcome
                raise
            except Exception as exc:  # noqa: BLE001 - a child failure is data
                outcome = ChildOutcome(
                    child_index=index, run_id=child_run_id, status="failed", reason=str(exc),
                )
        outcomes[index] = outcome
        await _emit(f"delegation.child.{'completed' if outcome.status == 'completed' else 'failed'}", {
            "delegationId": delegation_id, "childIndex": index,
            "runId": child_run_id, "status": outcome.status,
        })

    tasks = [asyncio.create_task(_one(i, child)) for i, child in enumerate(request.children)]
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        # Every child must reach exactly one terminal status; none is left running.
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    final: list[ChildOutcome] = [o for o in outcomes if o is not None]
    dropped: list[str] = []
    for outcome in final:
        dropped.extend(outcome.dropped)

    budget = BudgetReport(
        requestedTokens=request.token_budget,
        children=len(final),
        timedOut=sum(1 for o in final if o.status == "timed_out"),
        wallMs=int((time.monotonic() - started) * 1000),
    )
    result = DelegationResult(
        delegationId=delegation_id,
        outcomes=final,
        droppedClaims=dropped,
        budget=budget,
        workflowId=workflow_id,
    )
    result.aggregate = aggregate(result)
    await _emit("delegation.aggregated", {
        "delegationId": delegation_id,
        "completed": sum(1 for o in final if o.status == "completed"),
        "droppedClaims": len(dropped),
    })
    return result


def _coerce_outcome(
    index: int, run_id: str, raw: Any, verifier: HandleVerifier,
) -> ChildOutcome:
    """Build a ChildOutcome from whatever the child runner returned.

    Accepts a `ChildOutcome` directly (tests / a caller that already computed it)
    or a mapping with `status`/`summary`/`handles`/`reason`.
    """
    if isinstance(raw, ChildOutcome):
        claimed, dropped = partition_claims(raw.summary, raw.handles, verifier)
        return raw.model_copy(update={"child_index": index, "claimed": claimed, "dropped": dropped})
    if isinstance(raw, dict):
        handles = [
            VerifiableHandle(kind=str(h.get("kind")), value=str(h.get("value")))
            for h in (raw.get("handles") or [])
            if isinstance(h, dict) and h.get("kind") in
            ("path", "run_id", "artifact_digest", "check_record_id", "citation")
        ]
        summary = str(raw.get("summary") or "")
        claimed, dropped = partition_claims(summary, handles, verifier)
        return ChildOutcome(
            child_index=index,
            run_id=raw.get("runId") or run_id,
            status=str(raw.get("status") or "failed"),  # type: ignore[arg-type]
            summary=summary,
            handles=handles,
            reason=raw.get("reason"),
            claimed=claimed,
            dropped=dropped,
        )
    return ChildOutcome(
        child_index=index, run_id=run_id, status="failed",
        reason="That part didn't return a result.",
    )


__all__ = [
    "BUDGET_EXHAUSTED",
    "DEFAULT_CHILD_TIMEOUT_S",
    "DEFAULT_CHILD_TOKEN_BUDGET",
    "DEPTH_EXCEEDED",
    "DelegationChild",
    "DelegationError",
    "DelegationRequest",
    "DelegationResult",
    "ChildOutcome",
    "BudgetReport",
    "HandleVerifier",
    "MAX_CHILDREN",
    "MAX_DEPTH",
    "MAX_IN_FLIGHT",
    "MIN_TOKENS_PER_CHILD",
    "PERMISSION_NOT_HELD",
    "SANDBOX_UNAVAILABLE",
    "TOOL_NOT_HELD",
    "WIDTH_EXCEEDED",
    "VerifiableHandle",
    "aggregate",
    "child_actor",
    "narrow_tools",
    "partition_claims",
    "run_delegation",
]
