"""Supply-chain audit over MCP presets and configured commands (Phase 6, M6).

A bounded, read-only, OFFLINE-ONLY report: every pinned package in `presets.py`
and every configured `npx`/`uvx` server command, listing the package, whether it
is pinned, and the date the entry was last reviewed.

This report never contacts the network and there is no background or scheduled
refresh. A network refresh (querying the package registry for the latest version)
is a deliberate non-goal of this phase: it would need a new dependency and an
opt-in network call. So `generatedAt` is the date the report was produced, and a
package's `checkedAt` is the date its launch values were last REVIEWED against
the package registry or the endpoint's own documentation — it is NOT a live
freshness check. An unpinned package resolves to whatever is latest at run time,
which the `note` states plainly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .presets import INTEGRATIONS

# Package runners whose package token is worth reporting.
_RUNNERS = {"npx", "pnpx", "bunx", "uvx", "pipx"}


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _package_from_command(command: str, args: list[str]) -> Optional[str]:
    if (command or "").split("/")[-1].split("\\")[-1].lower() not in _RUNNERS:
        return None
    for arg in args or []:
        if isinstance(arg, str) and arg and not arg.startswith("-"):
            return arg
    return None


def _is_pinned(spec: str) -> bool:
    """A package is pinned when it carries an explicit version (`name@1.2.3`)."""
    if spec.startswith("@"):
        # A scoped package `@scope/name` may carry a version after the name.
        at = spec.rfind("@")
        return at > 0
    return "@" in spec


def supply_chain_report(
    manager: Any = None, *, checked_at: Optional[str] = None, upstream_checked: bool = False
) -> dict[str, Any]:
    """The report. Offline: reads presets + the manager's configured runtimes.

    `checked_at` defaults to today (UTC) so the report is honestly dated at
    generation time rather than pinned to a hardcoded string. It is the
    generation/review date, never a network freshness check.

    `upstream_checked=True` is set by a CALLER that also performed a live OSV
    check (see `supply_chain.py`); this function itself never contacts the
    network, and with the default the report stays honestly offline.
    """
    checked_at = checked_at or _today_utc()
    packages: list[dict[str, Any]] = []
    seen: set[str] = set()

    for spec in INTEGRATIONS:
        if spec.transport != "stdio" or not spec.command:
            continue
        package = _package_from_command(spec.command, list(spec.args))
        if not package or package in seen:
            continue
        seen.add(package)
        packages.append({
            "package": package,
            "source": "preset",
            "integrationId": spec.id,
            "pinned": _is_pinned(package),
            "verified": spec.verified,
            "verifiedAgainst": spec.verified_against,
            "checkedAt": spec.verified_at or checked_at,
        })

    if manager is not None:
        for rt in getattr(manager, "_runtimes", {}).values():
            config = rt.config
            if config.transport != "stdio":
                continue
            package = _package_from_command(config.command, list(config.args))
            if not package or package in seen:
                continue
            seen.add(package)
            packages.append({
                "package": package,
                "source": "configured",
                "serverId": config.id,
                "pinned": _is_pinned(package),
                "verified": False,
                "verifiedAgainst": None,
                "checkedAt": checked_at,
            })

    return {
        "readOnly": True,
        "offline": True,
        # Explicit: this report never contacts the network and is never refreshed
        # in the background or on a schedule. `generatedAt` is when it was produced;
        # per-package `checkedAt` is the review date, not live freshness.
        # This report itself never contacts the network; `upstreamChecked`
        # records whether a live OSV check was performed ALONGSIDE it.
        "offlineOnly": True,
        "upstreamChecked": upstream_checked,
        "generatedAt": checked_at,
        "checkedAt": checked_at,
        "packages": packages,
        "unpinnedCount": sum(1 for p in packages if not p["pinned"]),
        "note": (
            "Offline only: no network call is made and this report is not refreshed "
            "in the background. 'checkedAt' is the date the entry was last REVIEWED, "
            "not a live version check. An unpinned package (`npx -y foo`) resolves to "
            "whatever is latest at run time - pin a version for reproducibility."
        ),
    }


__all__ = ["supply_chain_report"]
