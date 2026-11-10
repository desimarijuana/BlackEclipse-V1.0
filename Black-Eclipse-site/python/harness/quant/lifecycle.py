"""Model lifecycle gates.

One state machine for a strategy version. A transition needs evidence and an
actor. A skipped gate is refused, not logged and ignored.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .errors import QuantError
from .store import QuantStore

STATES = (
    "draft", "specified", "implemented", "backtested", "validated",
    "paper", "live_trial", "live", "monitored", "retired",
)
_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("specified", "retired"),
    "specified": ("implemented", "retired"),
    "implemented": ("backtested", "retired"),
    "backtested": ("validated", "retired"),
    "validated": ("paper", "retired"),
    "paper": ("live_trial", "retired"),
    "live_trial": ("live", "paper", "retired"),
    "live": ("monitored", "retired"),
    "monitored": ("live", "retired"),
    "retired": (),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS QuantModelLifecycle (
  strategyId TEXT NOT NULL,
  version TEXT NOT NULL,
  state TEXT NOT NULL,
  actor TEXT,
  evidenceJson TEXT,
  note TEXT,
  updatedAt TEXT NOT NULL,
  PRIMARY KEY (strategyId, version)
);
CREATE INDEX IF NOT EXISTS idx_qlife_state ON QuantModelLifecycle(state);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LifecycleError(QuantError):
    def __init__(self, code: str, message: str,
                 detail: dict[str, Any] | None = None) -> None:
        super().__init__(message, detail=detail)
        self.code = code


class LifecycleService:
    def __init__(self, store: QuantStore) -> None:
        self.store = store
        self._db = store._db
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def get(self, strategy_id: str, version: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM QuantModelLifecycle WHERE strategyId=? AND version=?",
            (strategy_id, version),
        ).fetchone()
        if row is None:
            return {"strategyId": strategy_id, "version": version,
                    "state": "draft", "actor": None, "evidence": {},
                    "note": "", "updatedAt": None}
        import json

        return {
            "strategyId": row["strategyId"],
            "version": row["version"],
            "state": row["state"],
            "actor": row["actor"],
            "evidence": json.loads(row["evidenceJson"] or "{}"),
            "note": row["note"],
            "updatedAt": row["updatedAt"],
        }

    def transition(
        self, strategy_id: str, version: str, to_state: str, *,
        actor: str, evidence: dict[str, Any] | None = None, note: str = "",
    ) -> dict[str, Any]:
        if not str(actor or "").strip():
            raise LifecycleError("ACTOR_REQUIRED", "every transition needs an actor")
        if to_state not in STATES:
            raise LifecycleError("UNKNOWN_STATE", f"unknown state {to_state!r}")
        self.store.get_strategy(strategy_id, version)
        current = self.get(strategy_id, version)
        allowed = _TRANSITIONS.get(str(current["state"]), ())
        if to_state not in allowed:
            raise LifecycleError(
                "ILLEGAL_TRANSITION",
                f"{current['state']} cannot move to {to_state}",
                detail={"from": current["state"], "to": to_state,
                        "allowed": list(allowed)},
            )
        evidence = dict(evidence or {})
        self._require_evidence(strategy_id, version, to_state, evidence)
        import json

        self._db.execute(
            "INSERT INTO QuantModelLifecycle "
            "(strategyId,version,state,actor,evidenceJson,note,updatedAt) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(strategyId,version) DO UPDATE SET state=excluded.state, "
            "actor=excluded.actor, evidenceJson=excluded.evidenceJson, "
            "note=excluded.note, updatedAt=excluded.updatedAt",
            (strategy_id, version, to_state, actor,
             json.dumps(evidence, sort_keys=True, default=str), note, _now()),
        )
        self._db.commit()
        result = self.get(strategy_id, version)
        result["previous"] = current["state"]
        return result

    def _require_evidence(self, strategy_id: str, version: str,
                          to_state: str, evidence: dict[str, Any]) -> None:
        def need(key: str) -> Any:
            value = evidence.get(key)
            if value in (None, "", [], {}):
                raise LifecycleError(
                    "EVIDENCE_REQUIRED",
                    f"the {to_state} gate requires evidence.{key}",
                    detail={"state": to_state, "required": key},
                )
            return value

        if to_state == "implemented":
            record = self.store.get_strategy(strategy_id, version)
            spec = record.get("spec") or {}
            if spec.get("implementationStatus") not in ("implemented", "tested", "builtin") \
                    and not evidence.get("implementationId"):
                raise LifecycleError(
                    "EVIDENCE_REQUIRED",
                    "the implemented gate requires a tested implementation",
                )
        elif to_state == "backtested":
            experiment_id = need("experimentId")
            try:
                self.store.get_experiment(str(experiment_id))
            except Exception as exc:  # noqa: BLE001
                raise LifecycleError("EVIDENCE_NOT_FOUND",
                                     f"experiment {experiment_id!r} was not found") from exc
        elif to_state == "validated":
            need("outOfSample")
            need("deflatedSharpe")
            need("pbo")
        elif to_state == "paper":
            need("approvalId")
            need("paperRunId")
        elif to_state == "live_trial":
            need("approvalId")
            need("trialId")
        elif to_state == "live":
            need("trialId")
            status = str(evidence.get("liveTrialStatus") or "")
            if status not in ("filled", "placed", "clean"):
                raise LifecycleError(
                    "EVIDENCE_REQUIRED",
                    "the live gate needs a clean live-trial result",
                    detail={"liveTrialStatus": status},
                )

    def list(self, *, state: str | None = None,
             limit: int = 100) -> list[dict[str, Any]]:
        if state:
            rows = self._db.execute(
                "SELECT * FROM QuantModelLifecycle WHERE state=? "
                "ORDER BY updatedAt DESC LIMIT ?", (state, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM QuantModelLifecycle ORDER BY updatedAt DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self.get(r["strategyId"], r["version"]) for r in rows]


def transitions() -> dict[str, list[str]]:
    return {state: list(allowed) for state, allowed in _TRANSITIONS.items()}


__all__ = ["LifecycleError", "LifecycleService", "STATES", "transitions"]
