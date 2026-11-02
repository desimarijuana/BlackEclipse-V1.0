"""Human-approval gate node.

The gate creates ONE approval request in the runtime's single-use approval store
(`service.approvals`), then either waits inline (a synchronous run, bounded by
`maxWaitS`) or asks a DURABLE run to pause and re-check later
(`DeferredWait(rerun=True)`), which is why the executor leaves the node pending.

Nothing is consumed: the decision is a gate for this run+node, so a resumed run
reads the same decision instead of needing a fresh one.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortKind, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
RISKS = ("low", "medium", "high")
APPROVED = "approved"
DENIED = "denied"
PENDING = "pending"

ApprovalRunner = Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]
_runner: Optional[ApprovalRunner] = None


def set_approval_runner(runner: Optional[ApprovalRunner]) -> None:
    global _runner
    _runner = runner


def _digest(context: NodeExecContext, title: str, message: str) -> str:
    """Stable for this run + node + request text, so a resume matches its row."""
    seed = f"{context.run_id}|{context.node_id}|{title}|{message}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def _approved(decision: dict[str, Any]) -> bool:
    return str(decision.get("status") or "").strip().lower() == APPROVED


def _denied(decision: dict[str, Any]) -> bool:
    return str(decision.get("status") or "").strip().lower() == DENIED


def _decided_by(decision: dict[str, Any]) -> str:
    approval = decision.get("approval")
    if isinstance(approval, dict):
        return str(approval.get("decidedBy") or "").strip()
    return str(decision.get("decidedBy") or "").strip()


def _request_args(context: NodeExecContext) -> dict[str, Any]:
    title = str(context.config.get("title") or "").strip() or "Approval required"
    message = str(
        context.inputs.get("message") or context.config.get("message") or ""
    ).strip()
    risk = str(context.config.get("risk") or "medium").strip().lower()
    if risk not in RISKS:
        raise ValueError(f"unsupported risk {risk!r}")
    try:
        ttl_hours = int(context.config.get("ttlHours", 12))
    except (TypeError, ValueError) as exc:
        raise ValueError("TTL must be a whole number of hours") from exc
    return {
        "requestKey": f"graph:{context.run_id}:{context.node_id}",
        "digest": _digest(context, title, message[:1_000]),
        "title": title[:200],
        "message": message[:1_000],
        "risk": risk,
        "ttlHours": max(1, min(ttl_hours, 24)),
    }


def exec_human_approval(context: NodeExecContext) -> dict[str, Any]:
    if context.test_run:
        # A test run must not create a pending request in the operator's queue.
        raise ValueError(
            "logic.human_approval needs a real decision; run it as an operator run "
            "and approve it in Approvals (a test run never requests one)"
        )
    if _runner is None:
        raise ValueError("the approval store is not configured in this graph runtime")
    args = _request_args(context)

    decision = _runner(context, args)
    if not isinstance(decision, dict):
        raise ValueError("the approval store returned no structured result")
    if _approved(decision):
        context.emit(f"approved by {_decided_by(decision) or 'operator'}")
        return _done(context, decision)
    if _denied(decision):
        by = _decided_by(decision)
        raise ValueError(f"approval denied{f' by {by}' if by else ''}")

    context.emit(f"requested approval: {args['title']}")
    try:
        poll = int(context.config.get("pollSeconds", 5))
    except (TypeError, ValueError) as exc:
        raise ValueError("Poll interval must be a whole number of seconds") from exc
    poll = max(2, min(poll, 60))

    if context.allow_defer:
        # Durable run: pause and re-enter this node later. The node stays PENDING
        # (no checkpoint), so no downstream step runs until a decision exists.
        from .model import DeferredWait  # noqa: PLC0415

        raise DeferredWait(poll, {}, rerun=True)

    try:
        max_wait = int(context.config.get("maxWaitS", 300))
    except (TypeError, ValueError) as exc:
        raise ValueError("Max wait must be a whole number of seconds") from exc
    deadline = time.monotonic() + max(10, min(max_wait, 3_600))
    while time.monotonic() < deadline:
        if context.should_cancel():
            raise ValueError("cancelled while waiting for approval")
        time.sleep(min(poll, max(0.0, deadline - time.monotonic())))
        decision = _runner(context, args)
        if not isinstance(decision, dict):
            raise ValueError("the approval store returned no structured result")
        if _approved(decision):
            context.emit(f"approved by {_decided_by(decision) or 'operator'}")
            return _done(context, decision)
        if _denied(decision):
            by = _decided_by(decision)
            raise ValueError(f"approval denied{f' by {by}' if by else ''}")
    raise ValueError(
        f"approval still pending after {max_wait}s; it is waiting in Approvals, "
        "so a later run with the same request can be approved"
    )


def _done(context: NodeExecContext, decision: dict[str, Any]) -> dict[str, Any]:
    by = _decided_by(decision)
    return {
        "value": context.inputs.get("value"),
        "approved": True,
        "decidedBy": by or None,
        "_control": ["done"],
    }


def build_approval_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="logic.human_approval", version="1.0.0", label="Wait for approval",
            category="logic",
            inputs=(
                PortDef(id="in", name="Run", type=PortType.ANY, kind=PortKind.CONTROL, optional=True),
                PortDef(id="value", name="Value", type=PortType.ANY, optional=True),
                PortDef(id="message", name="Message", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="value", name="Value", type=PortType.ANY, nullable=True),
                PortDef(id="approved", name="Approved", type=PortType.BOOLEAN),
                PortDef(id="decidedBy", name="Decided by", type=PortType.STRING, nullable=True),
                PortDef(id="done", name="Done", type=PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                ConfigField("title", "string", "", max_length=200),
                ConfigField("message", "string", "", max_length=1_000),
                ConfigField("risk", "enum", "medium", enum=RISKS),
                ConfigField("ttlHours", "integer", 12, minimum=1, maximum=24),
                ConfigField("pollSeconds", "integer", 5, minimum=2, maximum=60),
                ConfigField("maxWaitS", "integer", 300, minimum=10, maximum=3_600),
            ),
            capabilities=("approval.request",),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            timeout_ms=3_700_000,
            executor=exec_human_approval,
            metadata={
                "docs": (
                    "Creates ONE approval of kind `graph_approval` for this run+node "
                    "and passes only after an operator approves it. A denial fails "
                    "the node with the approver. A durable run pauses and re-checks "
                    "instead of holding a worker; a synchronous run polls up to "
                    "Max wait and then fails honestly (the request stays in "
                    "Approvals). Test runs never request one."
                ),
            },
        ),
    ]


__all__ = [
    "APPROVED",
    "DENIED",
    "PENDING",
    "RISKS",
    "build_approval_nodes",
    "exec_human_approval",
    "set_approval_runner",
]
