"""Deterministic replay.

A recorded trajectory can be replayed in two modes:

  * **inspect** (default) — walk the recorded steps and report them without
    touching the desktop. This is always deterministic and safe.
  * **execute** — re-issue the recorded actions against the live desktop. This
    can DRIFT (the UI may have changed), so each action is re-grounded and
    re-verified; a mismatch halts the replay rather than clicking blind.

Replay never bypasses policy or the finance firewall — it goes through the same
core actions as a live run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ReplayStep:
    seq: int
    kind: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "kind": self.kind, "data": self.data}


@dataclass
class ReplayReport:
    session_id: str
    mode: str
    steps: list[ReplayStep] = field(default_factory=list)
    executed: int = 0
    diverged_at: Optional[int] = None
    ok: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id, "mode": self.mode,
            "stepCount": len(self.steps), "executed": self.executed,
            "divergedAt": self.diverged_at, "ok": self.ok, "notes": self.notes,
        }


class Replayer:
    @staticmethod
    def load(path: str) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("a trajectory must be a JSON object")
        return payload

    def inspect(self, trajectory: dict[str, Any]) -> ReplayReport:
        steps = [ReplayStep(seq=int(s.get("seq", i)), kind=str(s.get("kind", "")), data=s.get("data") or {})
                 for i, s in enumerate(trajectory.get("steps", []))]
        return ReplayReport(session_id=str(trajectory.get("sessionId", "")), mode="inspect", steps=steps)

    async def execute(self, trajectory: dict[str, Any], actions: Any, *, stop_on_divergence: bool = True) -> ReplayReport:
        """Replay live. `actions` is a core facade exposing `perform_action(action, **kwargs)`."""
        report = ReplayReport(session_id=str(trajectory.get("sessionId", "")), mode="execute")
        for i, raw in enumerate(trajectory.get("steps", [])):
            step = ReplayStep(seq=int(raw.get("seq", i)), kind=str(raw.get("kind", "")), data=raw.get("data") or {})
            report.steps.append(step)
            if step.kind != "action":
                continue
            action = str(step.data.get("action") or "")
            target = step.data.get("target") or {}
            try:
                result = await actions.perform_action(action, target=target, replay=True)
            except Exception as exc:  # noqa: BLE001 - a replay failure is data
                report.ok = False
                report.diverged_at = i
                report.notes.append(f"step {i}: {type(exc).__name__}: {str(exc)[:160]}")
                if stop_on_divergence:
                    break
                continue
            report.executed += 1
            if not result.get("success") and stop_on_divergence:
                report.ok = False
                report.diverged_at = i
                report.notes.append(f"step {i}: the recorded action diverged on replay")
                break
        return report


__all__ = ["ReplayReport", "ReplayStep", "Replayer"]
