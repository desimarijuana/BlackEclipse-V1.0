"""Live supply-chain check for the spawn path (continuation Milestone 6).

`screening.py` matches a small hardcoded IOC list; `audit.py` is offline. Neither
asks an advisory database about the exact package version about to be executed —
and `npx -y <pkg>` is arbitrary third-party code execution.

This module queries the public **OSV** API (`https://api.osv.dev/v1/query`) for
the package + version being launched, filtering to malware advisories.

Policy (stated exactly):

  * **Fail closed on a confirmed malware advisory** — the spawn is refused with a
    diagnostic naming the advisory id.
  * **Fail open on a network error** (timeout, DNS, non-200) — the package is
    allowed to proceed, and the verdict says so. Never a silent allow.

Verdicts are cached in-process keyed by `(ecosystem, package, version)` with an
absolute expiry, so a flapping server does not produce a query stream. Clean and
blocked verdicts are cacheable; network failures are NOT (a retry may succeed).

Network access is injected (`fetcher`) so the offline suite tests recorded
responses without touching the network. Nothing here runs in the default suite.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import quote

log = logging.getLogger("harness.mcp.supply_chain")

OSV_QUERY_URL = "https://api.osv.dev/v1/query"

# Verdict codes.
CLEAN = "clean"
BLOCKED = "blocked"
UNKNOWN = "unknown"  # a network/upstream failure: fail-open, labelled

# An absolute cache lifetime. Long enough to avoid a query stream for a flapping
# server, short enough that a newly-published advisory is picked up the same day.
CACHE_TTL_S = 6 * 60 * 60

# Ecosystem mapping for OSV. npm is the only runner we currently launch.
_NPM_RUNNERS = {"npx", "pnpx", "bunx"}
_PYPI_RUNNERS = {"uvx", "pipx"}


@dataclass
class SupplyChainVerdict:
    code: str  # clean | blocked | unknown
    package: str
    version: Optional[str] = None
    ecosystem: Optional[str] = None
    advisory_ids: list[str] = field(default_factory=list)
    reason: Optional[str] = None
    cached: bool = False

    @property
    def blocked(self) -> bool:
        return self.code == BLOCKED

    def public(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "package": self.package,
            "version": self.version,
            "ecosystem": self.ecosystem,
            "advisoryIds": list(self.advisory_ids),
            "reason": self.reason,
            "cached": self.cached,
        }


def parse_package_spec(spec: str) -> tuple[str, Optional[str], Optional[str]]:
    """Split `name`, `name@1.2.3`, `@scope/name@1.2.3` into (name, version, ecosystem).

    Ecosystem is `None` here; the runner (`npx` vs `uvx`) decides it. A scoped npm
    name's leading `@` is preserved.
    """
    text = (spec or "").strip()
    if not text:
        return "", None, None
    if text.startswith("@"):
        # `@scope/name` or `@scope/name@version`.
        at = text.rfind("@")
        if at > 0:
            return text[:at], text[at + 1:] or None, None
        return text, None, None
    if "@" in text:
        name, _, version = text.partition("@")
        return name, (version or None), None
    return text, None, None


def ecosystem_for_runner(command: str) -> Optional[str]:
    """The OSV ecosystem for a package runner, or None when not a package runner."""
    runner = (command or "").split("/")[-1].split("\\")[-1].lower()
    if runner in _NPM_RUNNERS:
        return "npm"
    if runner in _PYPI_RUNNERS:
        return "PyPI"
    return None


def _is_malware_advisory(vuln: dict[str, Any]) -> bool:
    """Whether an OSV entry is a malware advisory.

    OSV marks known-malicious packages with an `MAL-` id prefix, and/or the
    database-specific `malicious-packages`/`malware` ecosystem entries. We match
    conservatively: an id starting `MAL-`, or a `database_specific.type`/`source`
    naming malware.
    """
    vid = str(vuln.get("id") or "")
    if vid.upper().startswith("MAL-"):
        return True
    db = vuln.get("database_specific") or {}
    if isinstance(db, dict):
        kind = str(db.get("type") or db.get("malware") or "").lower()
        if "malware" in kind or "malicious" in kind:
            return True
        source = str(db.get("source") or "").lower()
        if "malware" in source or "malicious" in source:
            return True
    summary = str(vuln.get("summary") or "").lower()
    return "malware" in summary or "malicious" in summary


class SupplyChainChecker:
    """Queries OSV (malware advisories only) with an in-process, expiring cache.

    `fetcher` is an injected async `(url, payload) -> dict` returning the OSV
    response JSON. The default performs the real HTTP call; tests inject a fake.
    """

    def __init__(
        self,
        fetcher: Optional[Callable[[str, dict[str, Any]], Any]] = None,
        *,
        ttl_s: int = CACHE_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetcher = fetcher
        self._ttl = ttl_s
        self._clock = clock
        # (ecosystem, package, version) -> (verdict, stored_at)
        self._cache: dict[tuple[str, str, Optional[str]], tuple[SupplyChainVerdict, float]] = {}

    async def _default_fetch(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def check(self, command: str, args: list[str]) -> SupplyChainVerdict:
        """The verdict for the package a `command args...` would launch.

        A non-package runner (a real executable) is never queried: returns
        `CLEAN` with a note that no package was involved.
        """
        ecosystem = ecosystem_for_runner(command)
        if ecosystem is None:
            return SupplyChainVerdict(CLEAN, package="", reason="not a package runner")
        spec = next((a for a in args or [] if isinstance(a, str) and a and not a.startswith("-")), None)
        if not spec:
            return SupplyChainVerdict(CLEAN, package="", ecosystem=ecosystem, reason="no package argument")
        package, version, _ = parse_package_spec(spec)
        if not package:
            return SupplyChainVerdict(CLEAN, package="", ecosystem=ecosystem, reason="unparseable package")

        key = (ecosystem, package, version)
        cached = self._cache.get(key)
        if cached is not None:
            verdict, stored_at = cached
            if self._clock() - stored_at < self._ttl:
                out = SupplyChainVerdict(**{**verdict.__dict__, "cached": True})
                return out

        verdict = await self._query(ecosystem, package, version)
        if verdict.code in (CLEAN, BLOCKED):
            self._cache[key] = (verdict, self._clock())
        # A network failure (UNKNOWN) is deliberately NOT cached.
        return verdict

    async def _query(self, ecosystem: str, package: str, version: Optional[str]) -> SupplyChainVerdict:
        payload: dict[str, Any] = {"package": {"name": package, "ecosystem": ecosystem}}
        if version:
            payload["version"] = version
        fetcher = self._fetcher or self._default_fetch
        try:
            data = await fetcher(OSV_QUERY_URL, payload)
        except Exception as exc:  # noqa: BLE001 - a network error fails OPEN, labelled
            return SupplyChainVerdict(
                UNKNOWN, package=package, version=version, ecosystem=ecosystem,
                reason=f"advisory lookup failed: {type(exc).__name__}",
            )
        if not isinstance(data, dict):
            return SupplyChainVerdict(
                UNKNOWN, package=package, version=version, ecosystem=ecosystem,
                reason="advisory lookup returned an unexpected payload",
            )
        vulns = data.get("vulns") or []
        malware = [v for v in vulns if isinstance(v, dict) and _is_malware_advisory(v)]
        if malware:
            ids = [str(v.get("id") or "unknown") for v in malware]
            return SupplyChainVerdict(
                BLOCKED, package=package, version=version, ecosystem=ecosystem,
                advisory_ids=ids,
                reason=f"malware advisory: {', '.join(ids)}",
            )
        return SupplyChainVerdict(CLEAN, package=package, version=version, ecosystem=ecosystem)


# One process-wide checker for the spawn path (no per-call client churn).
_CHECKER = SupplyChainChecker()


def checker() -> SupplyChainChecker:
    return _CHECKER


def reset_cache() -> None:
    """Clear the process-wide cache (tests / an operator refresh)."""
    _CHECKER._cache.clear()  # noqa: SLF001 - deliberate test seam


async def check_spawn(command: str, args: list[str], *, enabled: bool = True) -> SupplyChainVerdict:
    """The verdict for a spawn. `enabled=False` skips the network entirely."""
    if not enabled:
        return SupplyChainVerdict(CLEAN, package="", reason="live check disabled")
    return await _CHECKER.check(command, args)


async def screen_spawn(config: Any, resolved: Any) -> Optional[str]:
    """Spawn-path guard used by `MCPManager._connect`.

    Returns a refusal message when a confirmed malware advisory covers the exact
    package about to launch, else None. Never raises: a lookup failure allows the
    spawn and is recorded on `config` (so it can be surfaced) via the return of
    None — a network failure is fail-open by design, and the manager's diagnostic
    is only set for a confirmed block.
    """
    if getattr(config, "transport", "") != "stdio":
        return None
    command = getattr(resolved, "command", None) or getattr(config, "command", "")
    args = list(getattr(resolved, "args", None) or getattr(config, "args", []) or [])
    verdict = await _CHECKER.check(command, args)
    if verdict.blocked:
        return (
            f"refused: the package `{verdict.package}`"
            f"{'@' + verdict.version if verdict.version else ''} matches a known-malware "
            f"advisory ({', '.join(verdict.advisory_ids) or 'unknown id'}). Remove or replace "
            "this server's package to continue."
        )
    if verdict.code == UNKNOWN:
        log.info(
            "supply-chain lookup inconclusive for %s (%s); allowing spawn",
            verdict.package, verdict.reason,
        )
    return None


__all__ = [
    "SupplyChainVerdict",
    "SupplyChainChecker",
    "check_spawn",
    "checker",
    "reset_cache",
    "parse_package_spec",
    "ecosystem_for_runner",
    "OSV_QUERY_URL",
    "CLEAN",
    "BLOCKED",
    "UNKNOWN",
]
