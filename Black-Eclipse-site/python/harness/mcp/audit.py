"""Supply-chain audit over MCP presets and configured commands (Phase 6, M6).

A bounded, read-only, offline-by-default report: every pinned package in
`presets.py` and every configured `npx`/`uvx` server command, listing the
package, whether it is pinned, and the last-checked date. A network refresh is
operator-gated and on-demand only — never a background call.
"""

from __future__ import annotations

from typing import Any, Optional

from .presets import INTEGRATIONS

# Package runners whose package token is worth reporting.
_RUNNERS = {"npx", "pnpx", "bunx", "uvx", "pipx"}


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


def supply_chain_report(manager: Any = None, *, checked_at: Optional[str] = None) -> dict[str, Any]:
    """The report. Offline: reads presets + the manager's configured runtimes."""
    checked_at = checked_at or "2026-09-29"
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
        "checkedAt": checked_at,
        "packages": packages,
        "unpinnedCount": sum(1 for p in packages if not p["pinned"]),
        "note": (
            "Offline by default: no network call is made. A refresh is operator-"
            "gated and on-demand. An unpinned package (`npx -y foo`) resolves to "
            "whatever is latest at run time — pin a version for reproducibility."
        ),
    }


__all__ = ["supply_chain_report"]
