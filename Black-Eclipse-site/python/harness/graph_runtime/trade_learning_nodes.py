"""Graph nodes for the trade-learning loop.

Six small adapters, not one monolith: load → observe → learn → improve → commit,
plus a read of the current envelope. Each stage has its own side-effect class, so
a test run can review and a dry climb can propose, while only an explicit
operator run can change the envelope the risk gate enforces.

The runtime owns no broker path here. `trade.commit` writes a playbook version on
`agent-memory.db`; it never places, modifies or cancels an order.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)

#: `(context, params) -> DataBridgeResult`; bound at boot to the server bridge.
_journal_loader: Optional[Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]] = None
#: The process-wide trade-learning service (built on the ONE agent-memory store).
_service: Any = None


def set_journal_loader(loader: Optional[Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]]) -> None:
    global _journal_loader
    _journal_loader = loader


def set_trade_learning_service(service: Any) -> None:
    global _service
    _service = service


def _require_service() -> Any:
    if _service is None:
        raise ValueError("the trade-learning store is not configured in this runtime")
    return _service


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _json_object(raw: Any, *, field: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field} must be a JSON object")
    return parsed


def _csv(raw: Any) -> list[str]:
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


# ── executors ─────────────────────────────────────────────────────────────────

def exec_journal(context: NodeExecContext) -> dict[str, Any]:
    wired = context.inputs.get("trades")
    if isinstance(wired, list) and wired:
        return {
            "trades": wired,
            "executions": _as_dict(context.inputs.get("executions")),
            "completeness": {},
            "provenance": {"source": "wired", "retrievedAt": None},
        }
    if _journal_loader is None:
        raise ValueError("the journal data bridge is not configured in this runtime")
    params = {
        "lookbackDays": int(context.config.get("lookbackDays", 90)),
        "status": str(context.config.get("status") or "closed"),
        "symbols": _csv(context.config.get("symbols")),
        "strategyId": str(context.config.get("strategyId") or ""),
        "setupId": str(context.config.get("setupId") or ""),
        "limit": int(context.config.get("limit", 200)),
        "includeExecutions": bool(context.config.get("includeExecutions", True)),
    }
    result = _journal_loader(context, params)
    if not isinstance(result, dict):
        raise ValueError("the journal bridge returned no payload")
    status = str(result.get("status") or "")
    if status and status != "OK":
        raise ValueError(str(result.get("error") or "journal data is UNAVAILABLE"))
    value = result.get("value") if isinstance(result.get("value"), dict) else result
    return {
        "trades": _as_list(value.get("trades")),
        "executions": _as_dict(value.get("executions")),
        "completeness": _as_dict(value.get("completeness")),
        "provenance": _as_dict(value.get("provenance")) or {"source": "jdds"},
    }


def exec_review(context: NodeExecContext) -> dict[str, Any]:
    trades = _as_list(context.inputs.get("trades"))
    if not trades:
        raise ValueError("trade.review needs trades (wire trade.journal or a literal)")
    from ..trade_learning.detectors import review  # noqa: PLC0415

    detectors = _csv(context.config.get("detectors")) or None
    review_config = {
        "riskPct": float(context.config.get("riskPct", 1.0)),
        "accountEquity": float(context.config.get("accountEquity", 0.0)),
        "maxTradesPerDay": int(context.config.get("maxTradesPerDay", 3)),
        "revengeWindowMin": int(context.config.get("revengeWindowMin", 30)),
        "duplicateWindowMin": int(context.config.get("duplicateWindowMin", 60)),
        "reviewGraceHours": int(context.config.get("reviewGraceHours", 24)),
        "minRForEarlyExit": float(context.config.get("minRForEarlyExit", 1.0)),
        "includeOpen": bool(context.config.get("includeOpen", False)),
    }
    playbook = context.inputs.get("playbook")
    return review(
        trades,
        executions=_as_dict(context.inputs.get("executions")),
        playbook=playbook if isinstance(playbook, dict) else None,
        detectors=detectors,
        config=review_config,
    )


def exec_learn(context: NodeExecContext) -> dict[str, Any]:
    service = _require_service()
    if context.test_run:
        # Recurrence is durable evidence used to change risk behaviour, not
        # scratch. A test run must not inflate the ONE ledger, so it is refused
        # here rather than silently polluting it.
        raise ValueError(
            "trade.learn records durable recurrence; run it as an operator run"
        )
    findings = _as_list(context.inputs.get("findings"))
    if not findings:
        return {"recorded": 0, "recurring": [], "candidates": [], "thresholds": {}}
    return service.learn(
        findings,
        coverage=_as_dict(context.inputs.get("coverage")),
        profile_id=str(context.user_id or "local"),
        min_occurrences=int(context.config.get("minOccurrences", 3)),
        window_days=int(context.config.get("windowDays", 90)),
        min_cost_r=float(context.config.get("minCostR", 1.0)),
        min_coverage=float(context.config.get("minCoverage", 0.8)),
        draft_candidates=bool(context.config.get("draftCandidates", True)),
    )


def exec_improve(context: NodeExecContext) -> dict[str, Any]:
    service = _require_service()
    trades = _as_list(context.inputs.get("trades"))
    if not trades:
        raise ValueError("trade.improve needs trades")
    bounds = _json_object(context.config.get("boundsJson"), field="Bounds (JSON)")
    playbook = context.inputs.get("playbook")
    return service.improve(
        trades,
        findings=_as_list(context.inputs.get("findings")),
        playbook=playbook if isinstance(playbook, dict) else None,
        bounds=bounds or None,
        profile_id=str(context.user_id or "local"),
        k=int(context.config.get("k", 3)),
        generations=int(context.config.get("generations", 2)),
        split_pct=float(context.config.get("splitPct", 0.7)),
        min_validation_trades=int(context.config.get("minValidationTrades", 10)),
        min_lift_r=float(context.config.get("minLiftR", 0.02)),
        seed=int(context.config.get("seed", 7)),
        equity=float(context.config.get("equity", 0.0)),
        apply="off",
    )


def exec_commit(context: NodeExecContext) -> dict[str, Any]:
    service = _require_service()
    if context.test_run:
        raise ValueError(
            "trade.commit changes the envelope future orders are checked against; "
            "run it as an operator run"
        )
    candidate = _as_dict(context.inputs.get("candidate"))
    if not candidate and isinstance(context.inputs.get("improvement"), dict):
        candidate = _as_dict(context.inputs["improvement"].get("best"))
    limits = _as_dict(candidate.get("limits"))
    if not limits:
        raise ValueError("trade.commit needs a candidate playbook with limits")
    bounds = _as_dict(context.inputs.get("bounds")) or _as_dict(candidate.get("bounds"))
    saved = service.store.save_playbook(
        limits,
        bounds=bounds,
        profile_id=str(context.user_id or "local"),
        reason=str(context.config.get("reason") or "operator commit")[:500],
        mode="apply",
        ttl_days=int(context.config.get("ttlDays", 14)),
        approved_by=str(context.user_id or "local"),
    )
    return {
        "playbook": _as_dict(saved.get("playbook")),
        "changed": bool(saved.get("changed")),
        "revertsAt": str(saved.get("revertsAt") or ""),
    }


def exec_playbook(context: NodeExecContext) -> dict[str, Any]:
    service = _require_service()
    payload = service.playbook(
        profile_id=str(context.user_id or "local"),
        history=bool(context.config.get("includeHistory", False)),
    )
    return {
        "playbook": _as_dict(payload.get("playbook")),
        "versions": _as_list(payload.get("versions")),
        "provenance": _as_dict(payload.get("provenance")),
    }


# ── definitions ───────────────────────────────────────────────────────────────

def _port(port_id: str, name: str, port_type: PortType, *, optional: bool = False) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, optional=optional)


def build_trade_learning_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="trade.journal", version="1.0.0", label="Journal trades",
            category="learning",
            inputs=(_port("trades", "Trades", PortType.ARRAY, optional=True),),
            outputs=(
                _port("trades", "Trades", PortType.ARRAY),
                _port("executions", "Execution log", PortType.OBJECT),
                _port("completeness", "Data completeness", PortType.OBJECT),
                _port("provenance", "Provenance", PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("lookbackDays", "integer", 90, minimum=1, maximum=3650),
                ConfigField("status", "enum", "closed", enum=("closed", "open", "all")),
                ConfigField("symbols", "string", "", max_length=400),
                ConfigField("strategyId", "string", "", max_length=80),
                ConfigField("setupId", "string", "", max_length=80),
                ConfigField("limit", "integer", 200, minimum=1, maximum=500),
                ConfigField("includeExecutions", "boolean", True),
            ),
            capabilities=("journal.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            timeout_ms=20_000,
            executor=exec_journal,
        ),
        NodeDef(
            type="trade.review", version="1.0.0", label="Review trades",
            category="learning",
            inputs=(
                _port("trades", "Trades", PortType.ARRAY),
                _port("executions", "Execution log", PortType.OBJECT, optional=True),
                _port("playbook", "Playbook", PortType.OBJECT, optional=True),
            ),
            outputs=(
                _port("findings", "Findings", PortType.ARRAY),
                _port("summary", "Summary", PortType.OBJECT),
                _port("reviewed", "Clean trades", PortType.ARRAY),
                _port("coverage", "Data coverage", PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("detectors", "string", "", max_length=400),
                ConfigField("riskPct", "number", 1.0, minimum=0.0, maximum=100.0),
                ConfigField("accountEquity", "number", 0.0, minimum=0.0, maximum=1e15),
                ConfigField("maxTradesPerDay", "integer", 3, minimum=0, maximum=100),
                ConfigField("revengeWindowMin", "integer", 30, minimum=0, maximum=1440),
                ConfigField("duplicateWindowMin", "integer", 60, minimum=0, maximum=1440),
                ConfigField("reviewGraceHours", "integer", 24, minimum=0, maximum=8760),
                ConfigField("minRForEarlyExit", "number", 1.0, minimum=0.0, maximum=100.0),
                ConfigField("includeOpen", "boolean", False),
            ),
            capabilities=(),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_review,
        ),
        NodeDef(
            type="trade.learn", version="1.0.0", label="Learn from review",
            category="learning",
            inputs=(
                _port("findings", "Findings", PortType.ARRAY),
                _port("coverage", "Data coverage", PortType.OBJECT, optional=True),
            ),
            outputs=(
                _port("recorded", "Findings recorded", PortType.NUMBER),
                _port("recurring", "Recurring patterns", PortType.ARRAY),
                _port("candidates", "Inert candidates", PortType.ARRAY),
                _port("thresholds", "Thresholds", PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("minOccurrences", "integer", 3, minimum=1, maximum=100),
                ConfigField("windowDays", "integer", 90, minimum=1, maximum=3650),
                ConfigField("minCostR", "number", 1.0, minimum=0.0, maximum=1e6),
                ConfigField("minCoverage", "number", 0.8, minimum=0.0, maximum=1.0),
                ConfigField("draftCandidates", "boolean", True),
            ),
            capabilities=("learning.write",),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            executor=exec_learn,
        ),
        NodeDef(
            type="trade.improve", version="1.0.0", label="Improve playbook",
            category="learning",
            inputs=(
                _port("trades", "Trades", PortType.ARRAY),
                _port("findings", "Findings", PortType.ARRAY, optional=True),
                _port("playbook", "Playbook", PortType.OBJECT, optional=True),
            ),
            outputs=(
                _port("candidates", "Ranked candidates", PortType.ARRAY),
                _port("best", "Best playbook", PortType.OBJECT),
                _port("accepted", "Improved", PortType.BOOLEAN),
                _port("reason", "Reason", PortType.STRING),
                _port("baseline", "Baseline (in/out of sample)", PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("boundsJson", "string", "", max_length=8000),
                ConfigField("k", "integer", 3, minimum=1, maximum=5),
                ConfigField("generations", "integer", 2, minimum=1, maximum=3),
                ConfigField("splitPct", "number", 0.7, minimum=0.5, maximum=0.95),
                ConfigField("minValidationTrades", "integer", 10, minimum=2, maximum=1000),
                ConfigField("minLiftR", "number", 0.02, minimum=0.0, maximum=100.0),
                ConfigField("seed", "integer", 7, minimum=0, maximum=1_000_000_000),
                ConfigField("equity", "number", 0.0, minimum=0.0, maximum=1e15),
            ),
            capabilities=(),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            timeout_ms=60_000,
            executor=exec_improve,
        ),
        NodeDef(
            type="trade.commit", version="1.0.0", label="Commit playbook",
            category="learning",
            inputs=(
                _port("candidate", "Candidate", PortType.OBJECT),
                _port("bounds", "Bounds", PortType.OBJECT, optional=True),
            ),
            outputs=(
                _port("playbook", "Active playbook", PortType.OBJECT),
                _port("changed", "Changed", PortType.BOOLEAN),
                _port("revertsAt", "Reverts at", PortType.STRING),
            ),
            config_fields=(
                ConfigField("reason", "string", "operator commit", max_length=500),
                ConfigField("ttlDays", "integer", 14, minimum=1, maximum=90),
            ),
            capabilities=("learning.write", "learning.self_modify"),
            side_effects=SideEffect.WRITE,
            allowed_modes=_ALL,
            executor=exec_commit,
        ),
        NodeDef(
            type="trade.playbook", version="1.0.0", label="Read playbook",
            category="learning",
            inputs=(),
            outputs=(
                _port("playbook", "Playbook", PortType.OBJECT),
                _port("versions", "Versions", PortType.ARRAY),
                _port("provenance", "Provenance", PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("includeHistory", "boolean", False),
                ConfigField("limit", "integer", 10, minimum=1, maximum=50),
            ),
            capabilities=("learning.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_playbook,
        ),
    ]


__all__ = [
    "build_trade_learning_nodes",
    "exec_commit",
    "exec_improve",
    "exec_journal",
    "exec_learn",
    "exec_playbook",
    "exec_review",
    "set_journal_loader",
    "set_trade_learning_service",
]
