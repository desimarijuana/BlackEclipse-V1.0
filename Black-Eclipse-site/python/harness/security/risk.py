"""Risk engine — server-side risk scoring.

Risk is computed from the request itself, never supplied by the caller or the
model. A request may carry a `context` hint, but the hint can only be *raised*,
never lowered, and the engine's own assessment wins.

Factors: action class, resource, environment, irreversibility, external side
effects, financial impact, credential sensitivity, network destination, scope and
blast radius. The output is a `RiskLevel`.
"""

from __future__ import annotations

import ipaddress
from typing import Any, Optional
from urllib.parse import urlparse

from .models import Environment, RiskLevel


_BASE_BY_ACTION_PREFIX: tuple[tuple[str, RiskLevel], ...] = (
    # Most specific first.
    ("financial.withdraw", RiskLevel.CRITICAL),
    ("financial.transfer", RiskLevel.CRITICAL),
    ("financial.live_trade", RiskLevel.CRITICAL),
    ("financial.cancel_order", RiskLevel.HIGH),
    ("financial.paper_trade", RiskLevel.LOW),
    ("financial.portfolio_read", RiskLevel.LOW),
    ("financial.market_read", RiskLevel.LOW),
    ("financial.research", RiskLevel.LOW),
    ("deploy.destroy", RiskLevel.CRITICAL),
    ("deploy.production", RiskLevel.CRITICAL),
    ("deploy.staging", RiskLevel.HIGH),
    ("deploy.dev", RiskLevel.MEDIUM),
    ("database.drop", RiskLevel.CRITICAL),
    ("database.admin", RiskLevel.CRITICAL),
    ("database.ddl", RiskLevel.HIGH),
    ("database.delete", RiskLevel.HIGH),
    ("infrastructure.destroy", RiskLevel.CRITICAL),
    ("infrastructure.write", RiskLevel.HIGH),
    ("database.write", RiskLevel.MEDIUM),
    ("database.read", RiskLevel.LOW),
    ("database.connect", RiskLevel.LOW),
    ("computer.finance", RiskLevel.CRITICAL),
    ("computer.action", RiskLevel.MEDIUM),
    ("external.action", RiskLevel.HIGH),
    ("git.external", RiskLevel.MEDIUM),
    ("git.write", RiskLevel.MEDIUM),
    ("browser.action", RiskLevel.MEDIUM),
    ("vision.external", RiskLevel.MEDIUM),
    ("code.execute", RiskLevel.MEDIUM),
    ("code.write", RiskLevel.MEDIUM),
    ("credential.admin", RiskLevel.CRITICAL),
    ("credential.access", RiskLevel.HIGH),
    ("security.admin", RiskLevel.CRITICAL),
    ("security.policy", RiskLevel.CRITICAL),
    ("filesystem.delete", RiskLevel.HIGH),
    ("filesystem.write", RiskLevel.MEDIUM),
    ("filesystem.read", RiskLevel.LOW),
    ("filesystem.discover", RiskLevel.LOW),
    ("shell.execute", RiskLevel.MEDIUM),
    ("network.request", RiskLevel.MEDIUM),
    ("plugin.invoke", RiskLevel.MEDIUM),
    ("mcp.invoke", RiskLevel.MEDIUM),
    ("skill.execute", RiskLevel.LOW),
)

_IRREVERSIBLE_HINTS = ("delete", "drop", "destroy", "purge", "truncate", "rm -rf", "format", "wipe")
_EXTERNAL_HINTS = ("push", "publish", "deploy", "send", "transfer", "withdraw", "post", "upload")
# Only actual financial SIDE EFFECTS raise the financial-impact factor; read-only
# research / market-read / portfolio-read must not inherit it.
_FINANCIAL_MARKERS = ("trade", "withdraw", "transfer", "payment", "order", "withdrawal")


def _private_host(url: str) -> bool:
    """Whether a URL targets a private/loopback/metadata address. Private-network
    reach raises risk (SSRF blast radius)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
    )


class RiskEngine:
    """Deterministic risk scoring. No I/O, no model input."""

    def base_risk(self, action: str) -> RiskLevel:
        action = str(action or "")
        for prefix, level in _BASE_BY_ACTION_PREFIX:
            if action == prefix or action.startswith(prefix + "."):
                return level
        return RiskLevel.MEDIUM  # unknown action is at least medium (fail-ish)

    def evaluate(
        self,
        *,
        action: str,
        resource: str = "",
        environment: Environment = Environment.DEVELOPMENT,
        irreversibility: Optional[bool] = None,
        external_side_effects: Optional[bool] = None,
        financial_impact: Optional[bool] = None,
        credential_sensitivity: Optional[bool] = None,
        network_destination: Optional[str] = None,
        scope: str = "",
        blast_radius: Optional[str] = None,
        hint: Optional[str] = None,
    ) -> RiskLevel:
        action = str(action or "")
        risk = self.base_risk(action)
        low = action.lower()

        irreversible = irreversibility
        if irreversible is None:
            irreversible = any(h in low for h in _IRREVERSIBLE_HINTS)
        if irreversible:
            risk = risk.max(RiskLevel.HIGH)

        external = external_side_effects
        if external is None:
            external = any(h in low for h in _EXTERNAL_HINTS)
        if external:
            risk = risk.max(RiskLevel.MEDIUM)

        financial = financial_impact
        if financial is None:
            financial = any(m in low for m in _FINANCIAL_MARKERS)
        if financial:
            risk = risk.max(RiskLevel.HIGH)

        credential = credential_sensitivity
        if credential is None:
            credential = action.startswith("credential.") or action.startswith("security.")
        if credential:
            risk = risk.max(RiskLevel.HIGH)

        if network_destination and _private_host(str(network_destination)):
            risk = risk.max(RiskLevel.HIGH)

        if environment is Environment.PRODUCTION:
            # A production write/delete isn't automatically critical, but any
            # mutating production action is high at minimum.
            if action.startswith(("filesystem.write", "filesystem.delete", "database.", "deploy.")):
                risk = risk.max(RiskLevel.CRITICAL if action.startswith(("database.", "deploy.")) else RiskLevel.HIGH)
            else:
                risk = risk.max(RiskLevel.MEDIUM)
        elif environment is Environment.STAGING and action.startswith(("deploy.", "database.")):
            risk = risk.max(RiskLevel.HIGH)

        if blast_radius == "broad":
            risk = risk.max(RiskLevel.HIGH)
        elif blast_radius == "system":
            risk = risk.max(RiskLevel.CRITICAL)

        if scope and scope.startswith("workspace:") is False and scope not in ("", "session"):
            # An unbounded/global scope is riskier than a workspace-scoped one.
            if scope in ("global", "*", "system"):
                risk = risk.max(RiskLevel.HIGH)

        # A caller-supplied hint may raise, never lower.
        if hint:
            try:
                hinted = RiskLevel(str(hint).lower())
                risk = risk.max(hinted)
            except ValueError:
                pass
        return risk


__all__ = ["RiskEngine"]
