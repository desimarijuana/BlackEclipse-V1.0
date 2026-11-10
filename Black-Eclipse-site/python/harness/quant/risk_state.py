"""Persistent risk state for a live trial.

Daily loss and drawdown need memory. This store keeps the day-start equity and
the peak equity for each trial, resets the day at UTC midnight, and calls the
same `kill_state` used by pre-trade checks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .risk_engine import DEFAULT_LIMITS, kill_state
from .store import QuantStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS QuantRiskState (
  trialId TEXT PRIMARY KEY,
  day TEXT NOT NULL,
  dayStartEquity REAL NOT NULL,
  peakEquity REAL NOT NULL,
  updatedAt TEXT NOT NULL
);
"""


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RiskState:
    def __init__(self, store: QuantStore) -> None:
        self.store = store
        self._db = store._db
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def get(self, trial_id: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT * FROM QuantRiskState WHERE trialId=?", (trial_id,)
        ).fetchone()
        if row is None:
            return None
        return {"trialId": row["trialId"], "day": row["day"],
                "dayStartEquity": row["dayStartEquity"],
                "peakEquity": row["peakEquity"], "updatedAt": row["updatedAt"]}

    def check(self, trial_id: str, account: dict[str, Any],
              limits: dict[str, Any] | None = None, *,
              data_healthy: bool = True,
              broker_healthy: bool = True) -> dict[str, Any]:
        equity = _num(account.get("equity") or account.get("balance"))
        today = _today()
        state = self.get(trial_id)
        if state is None or state["day"] != today:
            state = {"trialId": trial_id, "day": today,
                     "dayStartEquity": equity, "peakEquity": equity,
                     "updatedAt": _now()}
        else:
            state["peakEquity"] = max(float(state["peakEquity"]), equity)
            state["updatedAt"] = _now()
        self._db.execute(
            "INSERT INTO QuantRiskState "
            "(trialId,day,dayStartEquity,peakEquity,updatedAt) "
            "VALUES (?,?,?,?,?) ON CONFLICT(trialId) DO UPDATE SET "
            "day=excluded.day, dayStartEquity=excluded.dayStartEquity, "
            "peakEquity=excluded.peakEquity, updatedAt=excluded.updatedAt",
            (trial_id, state["day"], state["dayStartEquity"],
             state["peakEquity"], state["updatedAt"]),
        )
        self._db.commit()
        return {
            "state": state,
            "kill": kill_state(
                account=account, limits=limits or DEFAULT_LIMITS,
                peak_equity=state["peakEquity"],
                day_start_equity=state["dayStartEquity"],
                data_healthy=data_healthy, broker_healthy=broker_healthy,
            ),
        }

    def reset(self, trial_id: str) -> dict[str, Any]:
        self._db.execute("DELETE FROM QuantRiskState WHERE trialId=?", (trial_id,))
        self._db.commit()
        return {"reset": True, "trialId": trial_id}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = ["RiskState"]
