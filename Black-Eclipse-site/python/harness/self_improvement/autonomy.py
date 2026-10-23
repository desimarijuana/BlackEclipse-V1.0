"""Supervised autonomy: what may close without a human, and how to stop it.

The loop already discovers and verifies. This module answers a narrower question:
given a measured candidate, may the runtime apply it without an operator click?

Three rules bound the answer:

1. **Risk class.** `L0` (code, tool widening, guardrail removal, model identity)
   is never automatic. `L2` (capability-widening) requires a human. Only `L1`
   surface changes (prompt wording, tool guidance, narrowing a context policy, a
   delegated-child prompt, added guardrails) are auto-eligible.
2. **Evidence.** A paired significant lift, no critical regression, a clean
   canary/replay, and a proposal whose predicted direction matched the measured
   one.
3. **A kill switch.** A persisted pause stops every automatic decision without a
   restart.

The decision function is pure; it never activates anything. The caller owns the
activation path.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Mapping, Optional

from ..persistence import now_iso
from .config import AUTONOMY_LEVELS
from .operators import classify_ops, classify_snapshot
from .runtime_settings import RuntimeSettingsStore

RISK_CLASSES: tuple[str, ...] = ("L0", "L1", "L2")
AUTO_LEVELS: tuple[str, ...] = ("supervised", "bounded")
KILL_SWITCH_KEY = "rsl.autonomy.kill"
ACTIVATIONS_KEY = "rsl.autonomy.activations"

_NEVER_AUTO_FIELDS = frozenset({
    "toolNames",       # widening a tool surface is capability, not wording
    "modelProvider",
    "modelName",
    "temperature",
    "skillDraftIds",
})
_HUMAN_FIELDS = frozenset({
    "guardrails",      # removal is checked separately; addition is L1
    "maxAnswerChars",
    "maxSteps",
    "maxToolCalls",
})


def _higher(current: str, candidate: str) -> str:
    """Rank L0 > L2 > L1 (L0 is the strongest refusal)."""
    order = {"L1": 0, "L2": 1, "L0": 2}
    return candidate if order[candidate] > order[current] else current


def classify_snapshot_risk(base: Any, candidate: Any) -> dict[str, Any]:
    """Classify a surface change as L1 (auto-eligible) or stronger.

    The rules are deliberately conservative: anything that widens capability,
    removes a guardrail, raises a ceiling, changes the model identity or changes
    the tool set is not auto-eligible.
    """
    change = classify_snapshot(base, candidate)
    fields = set(change["fields"])
    if not fields:
        return {
            "riskClass": "L1", "changed": False, "reasons": ["no_change"],
            "fields": [], "operators": [],
        }
    risk = "L1"
    reasons: list[str] = []

    before_tools = set(getattr(base, "toolNames", ()) or ())
    after_tools = set(getattr(candidate, "toolNames", ()) or ())
    if after_tools - before_tools:
        risk = _higher(risk, "L2")
        reasons.append("tool_added")
    if before_tools - after_tools:
        reasons.append("tool_removed")

    before_guardrails = set(getattr(base, "guardrails", ()) or ())
    after_guardrails = set(getattr(candidate, "guardrails", ()) or ())
    if before_guardrails - after_guardrails:
        risk = _higher(risk, "L2")
        reasons.append("guardrail_removed")
    if after_guardrails - before_guardrails:
        reasons.append("guardrail_added")

    for field in ("maxSteps", "maxToolCalls", "maxAnswerChars"):
        before = getattr(base, field, None)
        after = getattr(candidate, field, None)
        if before is not None and after is not None and after > before:
            risk = _higher(risk, "L2")
            reasons.append(f"{field}_raised")
        elif before is not None and after is not None and after < before:
            reasons.append(f"{field}_lowered")

    if fields & _NEVER_AUTO_FIELDS:
        risk = _higher(risk, "L2")
        reasons.append("capability_or_identity_changed")

    if fields & {"systemPrompt", "toolGuidance", "subagentPrompt",
                 "skillManifest", "memoryPolicy"}:
        reasons.append("bounded_surface_change")

    if risk == "L2" and not reasons:
        reasons.append("capability_widening")
    return {
        "riskClass": risk,
        "changed": True,
        "reasons": reasons,
        "fields": change["fields"],
        "operators": change["operators"],
    }


def classify_ops_risk(operator: str) -> str:
    """A code patch is L0; a composition is L2; a surface op is L1."""
    if operator == "code_patch":
        return "L0"
    if operator in ("composition", "unknown"):
        return "L2"
    return "L1"


class AutonomyKillSwitch:
    """A persisted emergency stop for every automatic decision."""

    def __init__(self, store: Any) -> None:
        self.settings = RuntimeSettingsStore(store)

    def status(self) -> dict[str, Any]:
        payload = self.settings.get(KILL_SWITCH_KEY) or {}
        return {
            "paused": bool(payload.get("paused")),
            "at": payload.get("at"),
            "reason": str(payload.get("reason") or ""),
        }

    def pause(self, reason: str = "") -> dict[str, Any]:
        payload = {
            "paused": True,
            "at": now_iso(),
            "reason": str(reason or "")[:200],
        }
        self.settings.put(KILL_SWITCH_KEY, payload)
        return self.status()

    def resume(self) -> dict[str, Any]:
        self.settings.put(
            KILL_SWITCH_KEY, {"paused": False, "at": now_iso(), "reason": ""},
        )
        return self.status()

    def activations_today(self) -> int:
        payload = self.settings.get(ACTIVATIONS_KEY) or {}
        today = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
        if str(payload.get("date") or "") != today:
            return 0
        try:
            return max(0, int(payload.get("count") or 0))
        except (TypeError, ValueError):
            return 0

    def record_activation(self) -> int:
        today = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
        count = self.activations_today() + 1
        self.settings.put(ACTIVATIONS_KEY, {"date": today, "count": count})
        return count


def decide(
    *,
    level: str,
    risk: str,
    kill: bool,
    config: Any,
    delta_ci_low: Optional[float] = None,
    critical_regression: bool = False,
    canary_ok: bool = True,
    replay_ok: bool = True,
    predicted_delta: Optional[float] = None,
    measured_delta: Optional[float] = None,
    activations_today: int = 0,
    changed: bool = True,
) -> dict[str, Any]:
    """Return whether the runtime may apply this candidate without an operator.

    Pure: it reads the config and the arguments, never the store, and never
    activates. A refusal always names every reason.
    """
    reasons: list[str] = []
    selected = str(level or "off").strip().lower()
    risk_class = str(risk or "L2").upper()

    if selected not in AUTONOMY_LEVELS:
        reasons.append("unknown_autonomy_level")
    if selected not in AUTO_LEVELS:
        reasons.append("autonomy_level")
    if kill:
        reasons.append("kill_switch")
    if not changed:
        reasons.append("no_change")
    if risk_class == "L0":
        reasons.append("risk_L0_never_automatic")
    elif risk_class == "L2":
        reasons.append("risk_L2_requires_human")
    elif risk_class != "L1":
        reasons.append("unknown_risk_class")

    if str(getattr(config, "auto_risk", "low") or "low").lower() == "low":
        if risk_class != "L1":
            reasons.append("risk_not_low")
    else:
        reasons.append("auto_risk_must_be_low")

    floor = float(getattr(config, "auto_min_lift", 0.02) or 0.0)
    if delta_ci_low is None:
        reasons.append("no_paired_evidence")
    elif float(delta_ci_low) <= floor:
        reasons.append("lift_below_floor")

    if critical_regression:
        reasons.append("critical_regression")
    if not canary_ok:
        reasons.append("canary_failed")
    if not replay_ok:
        reasons.append("replay_failed")
    if predicted_delta is not None and measured_delta is not None:
        if (float(predicted_delta) > 0) != (float(measured_delta) > 0):
            reasons.append("mispredicted")

    budget = max(0, int(getattr(config, "auto_max_per_day", 0) or 0))
    if int(activations_today) >= budget:
        reasons.append("daily_budget")

    return {
        "allowed": not reasons,
        "level": selected,
        "riskClass": risk_class,
        "reasons": reasons,
        "requiresOperator": bool(reasons),
        "autoMinLift": floor,
        "autoMaxPerDay": budget,
        "activationsToday": int(activations_today),
    }


def autonomy_status(
    config: Any,
    kill: Mapping[str, Any],
    *,
    activations_today: int = 0,
) -> dict[str, Any]:
    level = str(getattr(config, "autonomy", "off") or "off").strip().lower()
    return {
        "level": level if level in AUTONOMY_LEVELS else "off",
        "autoEligible": level in AUTO_LEVELS,
        "riskCeiling": str(getattr(config, "auto_risk", "low") or "low"),
        "autoMinLift": float(getattr(config, "auto_min_lift", 0.02) or 0.0),
        "autoMaxPerDay": max(
            0, int(getattr(config, "auto_max_per_day", 0) or 0)
        ),
        "activationsToday": int(activations_today),
        "killSwitch": dict(kill),
    }


__all__ = [
    "ACTIVATIONS_KEY",
    "AUTO_LEVELS",
    "AutonomyKillSwitch",
    "KILL_SWITCH_KEY",
    "RISK_CLASSES",
    "autonomy_status",
    "classify_ops_risk",
    "classify_snapshot_risk",
    "decide",
]
