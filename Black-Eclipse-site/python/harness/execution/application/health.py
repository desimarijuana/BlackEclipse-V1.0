"""The health-check engine — process_running is NOT application_healthy.

A check is one of: process (the managed process is alive), tcp (a listener
answers), http (an endpoint returns an expected status), container (the engine's
health status), database (a socket to a DB port, where safely supported) or a
project-defined custom check. Every check is bounded by a timeout and a retry
count; a check that never passes reports UNHEALTHY with the reason, never a
fabricated OK.

The engine never touches a secret: a database check is a plain TCP connection to
a host:port, not an authenticated query.
"""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .models import HealthCheck, HealthReport, HealthResult, HealthStatus


class HealthCheckEngine:
    """Run process / tcp / http / container / database / custom checks."""

    def __init__(self, *, terminal: Any = None, container: Any = None) -> None:
        self._terminal = terminal
        self._container = container

    # ── individual checks ────────────────────────────────────────────────────────
    def process(self, check: HealthCheck, *, process_id: str = "") -> HealthResult:
        pid = process_id or check.target
        alive = False
        detail = "the process is not running"
        if self._terminal is not None and pid:
            info = self._terminal.get_process(pid)
            if info is not None:
                state = str(info.get("state") or "")
                alive = state in ("RUNNING", "STARTING", "PAUSED")
                detail = f"process state is {state}"
        else:
            alive = False
        return HealthResult(
            check=check.name or check.kind, kind="process",
            status=HealthStatus.HEALTHY if alive else HealthStatus.UNHEALTHY,
            ok=alive, detail=detail, evidence={"processId": pid},
        )

    def tcp(self, check: HealthCheck) -> HealthResult:
        host, port = _split_host_port(check.target)
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=check.timeout_s):
                ok = True
                detail = f"{host}:{port} answered"
        except OSError as exc:
            ok = False
            detail = f"nothing answered on {host}:{port}"
            _ = exc
        return HealthResult(
            check=check.name or check.kind, kind="tcp",
            status=HealthStatus.HEALTHY if ok else HealthStatus.UNHEALTHY, ok=ok,
            detail=detail, latency_ms=int((time.monotonic() - started) * 1000),
            evidence={"host": host, "port": port},
        )

    def http(self, check: HealthCheck) -> HealthResult:
        url = check.target
        started = time.monotonic()
        ok = False
        detail = f"{url} did not answer"
        status_code = 0
        try:
            request = urllib.request.Request(url, method=check.method, data=(check.body.encode() if check.body else None))
            for key, value in (check.headers or {}).items():
                request.add_header(str(key), str(value))
            with urllib.request.urlopen(request, timeout=check.timeout_s) as response:  # noqa: S310 - local health only
                status_code = int(getattr(response, "status", 200))
                ok = _status_ok(status_code, check.expected_status)
                detail = f"{url} returned {status_code}"
        except urllib.error.HTTPError as exc:
            status_code = int(getattr(exc, "code", 0))
            ok = _status_ok(status_code, check.expected_status)
            detail = f"{url} returned {status_code}"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            detail = f"{url} is unreachable"
            _ = exc
        return HealthResult(
            check=check.name or check.kind, kind="http",
            status=HealthStatus.HEALTHY if ok else HealthStatus.UNHEALTHY, ok=ok,
            detail=detail, latency_ms=int((time.monotonic() - started) * 1000),
            evidence={"url": url, "status": status_code},
        )

    def container(self, check: HealthCheck) -> HealthResult:
        if self._container is None or not check.target:
            return HealthResult(check=check.name or check.kind, kind="container",
                                status=HealthStatus.UNKNOWN, ok=False, detail="no container engine")
        result = self._container.healthcheck(check.target)
        state = result.data.get("Status") if isinstance(result.data, dict) else ""
        health = result.data.get("Health", {}).get("Status") if isinstance(result.data, dict) else ""
        ok = bool(result.ok)
        return HealthResult(
            check=check.name or check.kind, kind="container",
            status=HealthStatus.HEALTHY if ok else HealthStatus.UNHEALTHY, ok=ok,
            detail=f"container {check.target}: {health or state or result.code}",
            evidence={"containerId": check.target, "raw": result.data},
        )

    def database(self, check: HealthCheck) -> HealthResult:
        """A plain TCP reachability check to a database port — never an auth query."""
        return self.tcp(HealthCheck(kind="database", name=check.name, target=check.target,
                                    timeout_s=check.timeout_s))

    def custom(self, check: HealthCheck, fn: Optional[Callable[[HealthCheck], bool]] = None) -> HealthResult:
        if fn is None:
            return HealthResult(check=check.name or "custom", kind="custom",
                                status=HealthStatus.SKIPPED, ok=False, detail="no custom check registered")
        try:
            ok = bool(fn(check))
        except Exception as exc:  # noqa: BLE001 - a raising check is unhealthy, not a crash
            return HealthResult(check=check.name or "custom", kind="custom",
                                status=HealthStatus.UNHEALTHY, ok=False, detail=f"the check raised: {type(exc).__name__}")
        return HealthResult(check=check.name or "custom", kind="custom",
                            status=HealthStatus.HEALTHY if ok else HealthStatus.UNHEALTHY, ok=ok,
                            detail="custom check passed" if ok else "custom check failed")

    # ── aggregate ────────────────────────────────────────────────────────────────
    def check(
        self, check: HealthCheck, *,
        process_id: str = "",
        custom: Optional[Callable[[HealthCheck], bool]] = None,
    ) -> HealthResult:
        if check.kind == "process":
            return self.process(check, process_id=process_id)
        if check.kind == "tcp":
            return self.tcp(check)
        if check.kind == "http":
            return self.http(check)
        if check.kind == "container":
            return self.container(check)
        if check.kind == "database":
            return self.database(check)
        if check.kind == "custom":
            return self.custom(check, custom)
        return HealthResult(check=check.name or check.kind, kind=check.kind,
                            status=HealthStatus.UNKNOWN, ok=False, detail=f"unknown check kind {check.kind!r}")

    def check_with_retries(
        self, check: HealthCheck, *,
        process_id: str = "",
        custom: Optional[Callable[[HealthCheck], bool]] = None,
        backoff: bool = True,
    ) -> HealthResult:
        """Run one check, retrying up to `check.retries` times with `check.interval_s`.

        Returns the LAST result. A check that never passes reports its honest
        unhealthy state; readiness is never asserted early. With `backoff` the
        interval grows between attempts (a slow-booting service is polled gently
        rather than hammered): `interval * min(2**attempt, 8)`, capped by the
        check's own `interval_s * 8`.
        """
        attempts = max(1, int(check.retries) + 1)
        base_interval = max(0.0, float(check.interval_s))
        result = HealthResult(check=check.name or check.kind, kind=check.kind)
        for attempt in range(1, attempts + 1):
            result = self.check(check, process_id=process_id, custom=custom)
            result.attempts = attempt
            if result.ok:
                return result
            if attempt < attempts:
                interval = base_interval
                if backoff and base_interval:
                    # Grow gently (2x per attempt) so a slow-booting service is
                    # polled rather than hammered. The first interval in the loop
                    # is still the check's own; this only affects later attempts.
                    interval = min(base_interval * (2 ** (attempt - 1)), 8.0)
                time.sleep(interval)
        return result

    def evaluate(
        self, checks: list[HealthCheck], *,
        process_ids: Optional[dict[str, str]] = None,
        custom: Optional[dict[str, Callable[[HealthCheck], bool]]] = None,
    ) -> HealthReport:
        """Run every check and aggregate. DEGRADED when some pass and some fail."""
        process_ids = process_ids or {}
        custom = custom or {}
        results: list[HealthResult] = []
        for check in checks:
            result = self.check_with_retries(
                check, process_id=process_ids.get(check.service, ""),
                custom=custom.get(check.name),
            )
            results.append(result)
        if not results:
            return HealthReport(status=HealthStatus.UNKNOWN, checks=[], reason="no health checks are defined")
        passed = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok and r.status is not HealthStatus.SKIPPED]
        if not failed:
            return HealthReport(status=HealthStatus.HEALTHY, checks=results)
        if passed:
            return HealthReport(
                status=HealthStatus.DEGRADED, checks=results,
                reason=f"{len(passed)} of {len(results)} checks passed",
            )
        return HealthReport(
            status=HealthStatus.UNHEALTHY, checks=results,
            reason=results[0].detail if results else "all checks failed",
        )


def _split_host_port(target: str) -> tuple[str, int]:
    text = str(target or "")
    if text.startswith("tcp://"):
        text = text[len("tcp://"):]
    host, _, port_text = text.rpartition(":")
    try:
        port = int(port_text)
    except ValueError:
        port = 0
    return (host or "127.0.0.1"), port


def _status_ok(observed: int, expected: int) -> bool:
    if expected:
        return observed == expected
    return 200 <= observed < 400


__all__ = ["HealthCheckEngine"]
