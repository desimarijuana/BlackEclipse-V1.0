"""The Autonomy Envelope — pre-committed, scoped, revocable permission to act.

The recovery engine can *decide* freely, but acting unattended requires standing
authority. This module is that authority: an operator sets an envelope ONCE
(which action classes are allowed, under what risk/reversibility/cost/network
bounds, until when), and the engine then acts without a per-action human in the
loop — as long as every action stays inside it.

It deliberately does NOT replace the security gateway. The security floor,
permissions and effect authorization still apply on top; the envelope only
answers "may the recovery engine take this class of recovery action unattended?"
Defense in depth: the envelope can be narrower than the security layer, never
wider.

Safety defaults:

  * The envelope is ENABLED but conservative: only reversible, low-risk classes
    that merely re-run or re-plan. Effectful classes (install a dependency,
    substitute a provider, build an adapter) are NOT enabled until an operator
    opts in — so zero-config behavior is unchanged.
  * `require_reversible` is True: an irreversible action is never auto-run.
  * Expiry and a global kill switch (`HARNESS_AUTONOMY=0`) revoke everything.
  * The engine itself can never widen the envelope (it is loaded from config, not
    written by an agent).
"""

from __future__ import annotations

import enum
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .policy import RecoveryStrategy


class ActionClass(str, enum.Enum):
    """The classes of recovery action the envelope can authorize."""

    RETRY = "retry"
    RATE_LIMIT_BACKOFF = "rate_limit_backoff"
    REPAIR_INPUT = "repair_input"
    FIX_DEPENDENCY = "fix_dependency"
    SUBSTITUTE_TOOL = "substitute_tool"
    SUBSTITUTE_PROVIDER = "substitute_provider"
    ALTERNATIVE_IMPLEMENTATION = "alternative_implementation"
    REPLAN = "replan"
    RE_EXECUTE_NODE = "re_execute_node"
    RESTORE_CHECKPOINT = "restore_checkpoint"
    DELEGATE_INVESTIGATION = "delegate_investigation"
    ROLLBACK = "rollback"
    COMPENSATE = "compensate"


STRATEGY_TO_CLASS: dict[RecoveryStrategy, ActionClass] = {
    RecoveryStrategy.RETRY: ActionClass.RETRY,
    RecoveryStrategy.RATE_LIMIT_BACKOFF: ActionClass.RATE_LIMIT_BACKOFF,
    RecoveryStrategy.REPAIR_INPUT: ActionClass.REPAIR_INPUT,
    RecoveryStrategy.FIX_DEPENDENCY: ActionClass.FIX_DEPENDENCY,
    RecoveryStrategy.SUBSTITUTE_TOOL: ActionClass.SUBSTITUTE_TOOL,
    RecoveryStrategy.SUBSTITUTE_PROVIDER: ActionClass.SUBSTITUTE_PROVIDER,
    RecoveryStrategy.ALTERNATIVE_IMPLEMENTATION: ActionClass.ALTERNATIVE_IMPLEMENTATION,
    RecoveryStrategy.REPLAN: ActionClass.REPLAN,
    RecoveryStrategy.RE_EXECUTE_NODE: ActionClass.RE_EXECUTE_NODE,
    RecoveryStrategy.RESTORE_CHECKPOINT: ActionClass.RESTORE_CHECKPOINT,
    RecoveryStrategy.DELEGATE_INVESTIGATION: ActionClass.DELEGATE_INVESTIGATION,
    RecoveryStrategy.ROLLBACK: ActionClass.ROLLBACK,
    RecoveryStrategy.COMPENSATE: ActionClass.COMPENSATE,
}

# The default opt-in set: only classes that re-run, re-plan or restore — every one
# reversible and low blast-radius. Effectful classes stay out until an operator
# widens the envelope.
_DEFAULT_CLASSES: frozenset[ActionClass] = frozenset(
    {
        ActionClass.RETRY,
        ActionClass.RATE_LIMIT_BACKOFF,
        ActionClass.REPLAN,
        ActionClass.RE_EXECUTE_NODE,
        ActionClass.RESTORE_CHECKPOINT,
        ActionClass.ROLLBACK,
        ActionClass.COMPENSATE,
    }
)

_RISK_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


class EnvelopeOutcome(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL = "approval"


@dataclass(frozen=True)
class EnvelopeDecision:
    outcome: EnvelopeOutcome
    action_class: Optional[ActionClass]
    reason: str

    @property
    def allowed(self) -> bool:
        return self.outcome == EnvelopeOutcome.ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "actionClass": self.action_class.value if self.action_class else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AutonomyEnvelope:
    enabled: bool = True
    version: int = 1
    action_classes: frozenset[ActionClass] = _DEFAULT_CLASSES
    risk_ceiling: str = "low"
    require_reversible: bool = True
    max_cost_usd: float = 1.0
    max_duration_ms: int = 120_000
    max_files_changed: int = 5
    allowed_network: tuple[str, ...] = ()
    expires_at: Optional[str] = None
    source: str = "default"

    def revoked(self, *, now: Optional[float] = None) -> bool:
        if not self.enabled:
            return True
        if self.expires_at:
            expiry = _parse_iso(self.expires_at)
            if expiry is None:
                return True  # unparseable expiry fails closed
            if expiry <= (now if now is not None else time.time()):
                return True
        return False

    def check(
        self,
        strategy: RecoveryStrategy,
        *,
        risk: str = "low",
        reversible: bool = True,
        cost_usd: float = 0.0,
        duration_ms: int = 0,
        files_changed: int = 0,
        network: tuple[str, ...] = (),
        now: Optional[float] = None,
    ) -> EnvelopeDecision:
        """Whether this recovery action may run unattended right now."""
        action_class = STRATEGY_TO_CLASS.get(strategy)
        if self.revoked(now=now):
            return EnvelopeDecision(EnvelopeOutcome.DENY, action_class, "autonomy envelope is disabled or expired")
        if action_class is None:
            return EnvelopeDecision(EnvelopeOutcome.APPROVAL, None, "strategy has no autonomous action class")
        if action_class not in self.action_classes:
            return EnvelopeDecision(
                EnvelopeOutcome.APPROVAL, action_class,
                f"action class '{action_class.value}' is not enabled in the envelope",
            )
        if self.require_reversible and not reversible:
            return EnvelopeDecision(
                EnvelopeOutcome.APPROVAL, action_class,
                "envelope requires reversible actions; this action is irreversible",
            )
        if _RISK_RANK.get(risk, 3) > _RISK_RANK.get(self.risk_ceiling, 1):
            return EnvelopeDecision(
                EnvelopeOutcome.APPROVAL, action_class,
                f"risk '{risk}' exceeds the envelope ceiling '{self.risk_ceiling}'",
            )
        if cost_usd > self.max_cost_usd:
            return EnvelopeDecision(
                EnvelopeOutcome.APPROVAL, action_class,
                f"estimated cost {cost_usd} exceeds the envelope cap {self.max_cost_usd}",
            )
        if duration_ms > self.max_duration_ms:
            return EnvelopeDecision(
                EnvelopeOutcome.APPROVAL, action_class,
                f"estimated duration {duration_ms}ms exceeds the envelope cap {self.max_duration_ms}ms",
            )
        if files_changed > self.max_files_changed:
            return EnvelopeDecision(
                EnvelopeOutcome.APPROVAL, action_class,
                f"{files_changed} files exceeds the envelope cap {self.max_files_changed}",
            )
        if network and not all(_network_allowed(host, self.allowed_network) for host in network):
            blocked = [h for h in network if not _network_allowed(h, self.allowed_network)]
            return EnvelopeDecision(
                EnvelopeOutcome.APPROVAL, action_class,
                "network destination not permitted by the envelope: " + ", ".join(sorted(set(blocked))),
            )
        return EnvelopeDecision(EnvelopeOutcome.ALLOW, action_class, "within the autonomy envelope")

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "version": self.version,
            "actionClasses": sorted(c.value for c in self.action_classes),
            "riskCeiling": self.risk_ceiling,
            "requireReversible": self.require_reversible,
            "maxCostUsd": self.max_cost_usd,
            "maxDurationMs": self.max_duration_ms,
            "maxFilesChanged": self.max_files_changed,
            "allowedNetwork": list(self.allowed_network),
            "expiresAt": self.expires_at,
            "source": self.source,
        }


def _parse_iso(value: str) -> Optional[float]:
    import datetime as _dt

    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.timestamp()


def _network_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    if not allowed:
        return False
    candidate = (host or "").strip().lower()
    for entry in allowed:
        pattern = entry.strip().lower()
        if not pattern:
            continue
        if candidate == pattern or candidate.endswith("." + pattern):
            return True
    return False


def autonomy_enabled() -> bool:
    """Global kill switch: `HARNESS_AUTONOMY=0`/`false` disables all autonomy."""
    value = os.environ.get("HARNESS_AUTONOMY")
    if value is None:
        return True
    return value.strip().lower() not in ("0", "false", "no", "off")


def default_envelope(*, source: str = "default") -> AutonomyEnvelope:
    return AutonomyEnvelope(source=source)


def load_envelope(path: Optional[str] = None) -> AutonomyEnvelope:
    """Load the envelope from a JSON file (or the default).

    A missing file, unreadable file or malformed content yields the conservative
    default — never a wider envelope. The kill switch overrides everything.
    """
    if not autonomy_enabled():
        return AutonomyEnvelope(enabled=False, source="kill-switch")
    configured = path or os.environ.get("HARNESS_AUTONOMY_ENVELOPE")
    if not configured or not os.path.isfile(configured):
        return default_envelope()
    try:
        with open(configured, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:  # noqa: BLE001 - fail closed to the default
        return default_envelope(source="default(load-failed)")
    return from_dict(data, source=configured)


def from_dict(data: dict[str, Any], *, source: str = "config") -> AutonomyEnvelope:
    """Build an envelope from a JSON object, ignoring anything malformed."""
    default = AutonomyEnvelope(source=source)
    enabled = bool(data.get("enabled", default.enabled)) and autonomy_enabled()
    try:
        classes = frozenset(
            ActionClass(str(c).lower()) for c in (data.get("actionClasses") or [c.value for c in default.action_classes])
        )
    except ValueError:
        classes = default.action_classes
    risk_ceiling = str(data.get("riskCeiling", default.risk_ceiling))
    if risk_ceiling not in _RISK_RANK:
        risk_ceiling = default.risk_ceiling
    return AutonomyEnvelope(
        enabled=enabled,
        version=int(data.get("version", default.version)),
        action_classes=classes,
        risk_ceiling=risk_ceiling,
        require_reversible=bool(data.get("requireReversible", default.require_reversible)),
        max_cost_usd=float(data.get("maxCostUsd", default.max_cost_usd)),
        max_duration_ms=int(data.get("maxDurationMs", default.max_duration_ms)),
        max_files_changed=int(data.get("maxFilesChanged", default.max_files_changed)),
        allowed_network=tuple(str(h) for h in (data.get("allowedNetwork") or [])),
        expires_at=data.get("expiresAt"),
        source=source,
    )


__all__ = [
    "ActionClass",
    "AutonomyEnvelope",
    "EnvelopeDecision",
    "EnvelopeOutcome",
    "STRATEGY_TO_CLASS",
    "autonomy_enabled",
    "default_envelope",
    "from_dict",
    "load_envelope",
]