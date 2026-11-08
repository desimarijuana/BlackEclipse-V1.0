"""The typed vocabulary of the trade-learning loop.

Three things live here and nowhere else:

* **`Trade`** — the bounded shape the journal bridge sends. Every field is
  optional except the identity, because a manual trade genuinely may not carry
  `mfe`/`mae`/`riskAmount`. Missing is `None`, never `0`.
* **`Finding`** — one recorded observation about one trade. It always names the
  detector, the expected state, the actual state and the evidence. It is not a
  lesson and not an action.
* **`Playbook`** — the *trading model* the loop is allowed to improve: a set of
  risk/selection knobs plus the operator's bounds. The bounds are authority; the
  loop may only move a knob toward "tighter".

The dataclasses are deliberately small and JSON-friendly: the graph runtime
hands them across node boundaries as plain dicts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

# ── deterministic helpers ─────────────────────────────────────────────────────


def stable_hash(payload: Any) -> str:
    """A stable digest of a JSON-able value (sorted keys, no whitespace)."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # reject NaN


def _int(value: Any) -> Optional[int]:
    number = _float(value)
    return int(number) if number is not None else None


def _bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
    return None


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            parsed = [part.strip() for part in value.split(",")]
        value = parsed
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


# ── trades ────────────────────────────────────────────────────────────────────

#: The execution-event kinds the journal actually writes.
EXECUTION_KINDS = (
    "created", "entry_modified", "stop_modified", "target_modified",
    "partial_exit", "final_exit", "closed",
)


@dataclass(frozen=True)
class Trade:
    id: str
    symbol: str = ""
    direction: str = ""
    entry: Optional[float] = None
    exit: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    quantity: Optional[float] = None
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    status: str = "closed"
    session: Optional[str] = None
    strategy_id: Optional[str] = None
    strategy_name: Optional[str] = None
    setup_id: Optional[str] = None
    setup_name: Optional[str] = None
    emotion: Optional[str] = None
    confidence: Optional[int] = None
    checklist: dict[str, bool] = field(default_factory=dict)
    rules: tuple[dict[str, Any], ...] = ()
    grade: Optional[str] = None
    notes: Optional[str] = None
    mistakes: tuple[str, ...] = ()
    risk_amount: Optional[float] = None
    r_multiple: Optional[float] = None
    mfe: Optional[float] = None
    mae: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    duration_sec: Optional[int] = None
    actual_rr: Optional[float] = None
    rules_checked: bool = False

    @classmethod
    def from_dict(cls, raw: Any) -> Optional["Trade"]:
        if not isinstance(raw, dict):
            return None
        trade_id = _text(raw.get("id"))
        if not trade_id:
            return None
        checklist_raw = raw.get("checklist")
        checklist: dict[str, bool] = {}
        if isinstance(checklist_raw, dict):
            checklist = {str(k): bool(v) for k, v in checklist_raw.items()}
        elif isinstance(checklist_raw, str) and checklist_raw.strip():
            try:
                parsed = json.loads(checklist_raw)
            except (TypeError, ValueError):
                parsed = {}
            if isinstance(parsed, dict):
                checklist = {str(k): bool(v) for k, v in parsed.items()}
        rules_raw = raw.get("strategyRules") or raw.get("rules") or ()
        rules = tuple(
            dict(rule) for rule in rules_raw if isinstance(rule, dict)
        ) if isinstance(rules_raw, (list, tuple)) else ()
        status = (_text(raw.get("status")) or "closed").lower()
        exit_time = _text(raw.get("exitTime"))
        return cls(
            id=trade_id[:120],
            symbol=(_text(raw.get("symbol")) or "").upper()[:40],
            direction=(_text(raw.get("direction")) or "").upper()[:10],
            entry=_float(raw.get("entry")),
            exit=_float(raw.get("exit")),
            stop_loss=_float(raw.get("stopLoss")),
            take_profit=_float(raw.get("takeProfit")),
            quantity=_float(raw.get("quantity")),
            entry_time=_text(raw.get("entryTime")),
            exit_time=exit_time,
            status="open" if status == "open" else "closed",
            session=_text(raw.get("session")),
            strategy_id=_text(raw.get("strategyId")),
            strategy_name=_text(raw.get("strategyName")),
            setup_id=_text(raw.get("setupId")),
            setup_name=_text(raw.get("setupName")),
            emotion=_text(raw.get("emotion")),
            confidence=_int(raw.get("confidence")),
            checklist=checklist,
            rules=rules,
            grade=_text(raw.get("grade")),
            notes=_text(raw.get("notes")),
            mistakes=tuple(_list(raw.get("mistakes"))),
            risk_amount=_float(raw.get("riskAmount")),
            r_multiple=_float(raw.get("rMultiple")),
            mfe=_float(raw.get("mfe")),
            mae=_float(raw.get("mae")),
            pnl=_float(raw.get("pnl")),
            pnl_pct=_float(raw.get("pnlPct")),
            duration_sec=_int(raw.get("durationSec")),
            actual_rr=_float(raw.get("actualRR")),
            rules_checked=bool(raw.get("strategyRules") or raw.get("rules")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry": self.entry,
            "exit": self.exit,
            "stopLoss": self.stop_loss,
            "takeProfit": self.take_profit,
            "quantity": self.quantity,
            "entryTime": self.entry_time,
            "exitTime": self.exit_time,
            "status": self.status,
            "session": self.session,
            "strategyId": self.strategy_id,
            "strategyName": self.strategy_name,
            "setupId": self.setup_id,
            "setupName": self.setup_name,
            "emotion": self.emotion,
            "confidence": self.confidence,
            "checklist": dict(self.checklist),
            "grade": self.grade,
            "notes": self.notes,
            "mistakes": list(self.mistakes),
            "riskAmount": self.risk_amount,
            "rMultiple": self.r_multiple,
            "mfe": self.mfe,
            "mae": self.mae,
            "pnl": self.pnl,
            "pnlPct": self.pnl_pct,
            "durationSec": self.duration_sec,
            "actualRR": self.actual_rr,
        }


def parse_trades(raw: Any) -> list[Trade]:
    """Accept bridge dicts and already-parsed `Trade` objects alike."""
    if not isinstance(raw, (list, tuple)):
        return []
    parsed: list[Trade] = []
    for item in raw:
        if isinstance(item, Trade):
            parsed.append(item)
            continue
        trade = Trade.from_dict(item)
        if trade is not None:
            parsed.append(trade)
    return parsed


# ── findings ──────────────────────────────────────────────────────────────────

#: Fixed severity per category. Deliberately data, not a model judgement.
SEVERITY: dict[str, str] = {
    "no_stop": "high",
    "risk_over_limit": "high",
    "stop_widened": "high",
    "held_past_stop": "high",
    "checklist_violation": "high",
    "revenge_trade": "high",
    "target_reduced": "medium",
    "early_exit": "medium",
    "overtraded": "medium",
    "duplicate_entry": "medium",
    "no_plan": "medium",
    "off_session": "medium",
    "off_symbol": "medium",
    "unreviewed": "low",
}

#: The journal's own free-text vocabulary, so an accepted finding can be written
#: back without inventing a second label set.
JOURNAL_LABEL: dict[str, str] = {
    "no_stop": "No stop",
    "risk_over_limit": "Oversized",
    "stop_widened": "Moved stop",
    "target_reduced": "Moved target",
    "early_exit": "Early exit",
    "held_past_stop": "Held loser",
    "overtraded": "Overtraded",
    "revenge_trade": "Revenge",
    "no_plan": "No plan",
    "checklist_violation": "Broke rule",
    "off_session": "Off-session",
    "off_symbol": "Off-plan symbol",
    "duplicate_entry": "Double entry",
    "unreviewed": "Unreviewed",
}


@dataclass(frozen=True)
class Finding:
    trade_id: str
    category: str
    expected: str
    actual: str
    evidence: dict[str, Any]
    signature: str
    detector_version: str = "1"
    r_multiple: Optional[float] = None
    r_available: bool = False
    symbol: str = ""
    strategy_id: Optional[str] = None
    session: Optional[str] = None
    occurred_at: Optional[str] = None

    @property
    def severity(self) -> str:
        return SEVERITY.get(self.category, "medium")

    @property
    def label(self) -> str:
        return JOURNAL_LABEL.get(self.category, self.category)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tradeId": self.trade_id,
            "category": self.category,
            "severity": self.severity,
            "expected": self.expected,
            "actual": self.actual,
            "evidence": dict(self.evidence),
            "signature": self.signature,
            "detectorVersion": self.detector_version,
            "rMultiple": self.r_multiple,
            "rAvailable": self.r_available,
            "symbol": self.symbol,
            "strategyId": self.strategy_id,
            "session": self.session,
            "occurredAt": self.occurred_at,
            "label": self.label,
        }


def finding_from_dict(raw: Any) -> Optional[Finding]:
    if not isinstance(raw, dict):
        return None
    trade_id = _text(raw.get("tradeId"))
    category = _text(raw.get("category"))
    if not trade_id or not category:
        return None
    evidence = raw.get("evidence")
    return Finding(
        trade_id=trade_id,
        category=category,
        expected=str(raw.get("expected") or "")[:500],
        actual=str(raw.get("actual") or "")[:500],
        evidence=dict(evidence) if isinstance(evidence, dict) else {},
        signature=str(raw.get("signature") or "")[:80],
        detector_version=str(raw.get("detectorVersion") or "1")[:20],
        r_multiple=_float(raw.get("rMultiple")),
        r_available=bool(raw.get("rAvailable")),
        symbol=(_text(raw.get("symbol")) or "").upper()[:40],
        strategy_id=_text(raw.get("strategyId")),
        session=_text(raw.get("session")),
        occurred_at=_text(raw.get("occurredAt")),
    )


# ── the playbook: the thing the loop may improve ──────────────────────────────

#: `direction` is the only safe direction the loop may move a knob on its own.
#: `off` is the value that means "no limit" (a 0 limit disables the rule).
KNOBS: dict[str, dict[str, Any]] = {
    "riskPerTradePct": {"kind": "number", "direction": "lower", "off": 0.0, "step": 0.25},
    "maxTradesPerDay": {"kind": "integer", "direction": "lower", "off": 0, "step": 1},
    "maxConsecutiveLosses": {"kind": "integer", "direction": "lower", "off": 0, "step": 1},
    "maxDailyLossR": {"kind": "number", "direction": "lower", "off": 0.0, "step": 0.5},
    "requireStop": {"kind": "boolean", "direction": "boolean", "off": False},
    "minPlannedRR": {"kind": "number", "direction": "higher", "off": 0.0, "step": 0.25},
    "symbolBlocklist": {"kind": "list", "direction": "longer"},
    "sessionAllowlist": {"kind": "list", "direction": "narrower"},
    "suspendedStrategies": {"kind": "list", "direction": "longer"},
}

DEFAULT_LIMITS: dict[str, Any] = {
    "riskPerTradePct": 0.0,
    "maxTradesPerDay": 0,
    "maxConsecutiveLosses": 0,
    "maxDailyLossR": 0.0,
    "requireStop": False,
    "minPlannedRR": 0.0,
    "symbolBlocklist": [],
    "sessionAllowlist": [],
    "suspendedStrategies": [],
}


def _normalise_limit(name: str, value: Any) -> Any:
    meta = KNOBS[name]
    kind = meta["kind"]
    if kind == "boolean":
        return bool(value)
    if kind in ("number", "integer"):
        number = _float(value)
        if number is None:
            return DEFAULT_LIMITS[name]
        return int(number) if kind == "integer" else round(number, 6)
    return sorted({str(item).strip() for item in _list(value) if str(item).strip()})


@dataclass(frozen=True)
class Playbook:
    limits: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    bounds: dict[str, Any] = field(default_factory=dict)
    version: int = 0
    playbook_id: str = ""

    @classmethod
    def from_dict(cls, raw: Any) -> "Playbook":
        if not isinstance(raw, dict):
            return cls()
        limits_raw = raw.get("limits") if isinstance(raw.get("limits"), dict) else raw
        limits = dict(DEFAULT_LIMITS)
        for name in KNOBS:
            if name in limits_raw:
                limits[name] = _normalise_limit(name, limits_raw[name])
        bounds = raw.get("bounds") if isinstance(raw.get("bounds"), dict) else {}
        return cls(
            limits=limits,
            bounds={str(k): dict(v) for k, v in bounds.items() if isinstance(v, dict)},
            version=int(_float(raw.get("version")) or 0),
            playbook_id=_text(raw.get("id")) or "",
        )

    @property
    def hash(self) -> str:
        return stable_hash({"limits": self.limits})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.playbook_id,
            "version": self.version,
            "hash": self.hash,
            "limits": dict(self.limits),
            "bounds": {k: dict(v) for k, v in self.bounds.items()},
        }


__all__ = [
    "DEFAULT_LIMITS",
    "EXECUTION_KINDS",
    "Finding",
    "JOURNAL_LABEL",
    "KNOBS",
    "Playbook",
    "SEVERITY",
    "Trade",
    "finding_from_dict",
    "parse_trades",
    "stable_hash",
]
