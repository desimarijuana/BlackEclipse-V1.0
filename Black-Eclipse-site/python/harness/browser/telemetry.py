"""Browser observability aggregates — counters, cost and structured logs (Phase 8).

`BrowserTrace` is the per-task forensic record; this module is the process-wide
AGGREGATE over all of them. It answers, without any content: how many sessions,
actions, failures, timeouts and crashes; navigation/action latency; vision calls;
provider failures; downloads/uploads — plus a real-measurement cost model and a
bounded, content-free structured log ring queryable by code.

Three hard rules, matching the rest of the harness:

  * **Content-free.** A counter is a number; a log line is a code + a short plain
    sentence. No page text, no URL query, no credential value ever lands here.
  * **Never estimate without a label.** Cost accrues from REAL measurements
    (browser-seconds, screenshot count, artifact bytes, vision tokens). A money
    figure appears only when the operator configured a rate; otherwise the
    measurement is reported with `ratesConfigured: false` and no fabricated price.
  * **Bounded.** Counters live in a fixed-vocabulary dict; latencies keep a sum,
    count and max (never a per-call list); the log ring is a fixed-size deque.
    Memory is the top constraint, so nothing here grows without a cap.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

# The log ring is bounded: debugging needs the recent activity, not an archive.
DEFAULT_LOG_CAP = 500
_MAX_PROVIDERS = 64
_MAX_ACTIONS = 128

# Error codes → a coarse, queryable category. Kept as data so the classifier
# cannot drift and a new code is a table edit, not a new branch.
_ERROR_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("TIMEOUT", "timeout"),
    ("CAPABILITY_UNSUPPORTED", "capability"),
    ("PROVIDER_UNAVAILABLE", "provider"),
    ("PROVIDER_ERROR", "provider"),
    ("LAUNCH_FAILED", "crash"),
    ("DISCONNECTED", "crash"),
    ("ELEMENT_NOT_FOUND", "element"),
    ("STALE_ELEMENT", "element"),
    ("NAVIGATION_FAILED", "navigation"),
    ("AUTHENTICATION_FAILED", "auth"),
    ("CREDENTIAL_UNAVAILABLE", "auth"),
    ("DOWNLOAD_FAILED", "download"),
    ("UPLOAD_FAILED", "upload"),
    ("DIALOG_ERROR", "dialog"),
    ("CDP_ERROR", "cdp"),
    ("EXECUTION_FAILED", "execution"),
    ("PERMISSION_DENIED", "permission"),
    ("APPROVAL_REQUIRED", "permission"),
    ("HUMAN_REQUIRED", "human"),
    ("SESSION_LIMIT", "limit"),
    ("UNAVAILABLE", "unavailable"),
)


def classify_error(code: Optional[str]) -> str:
    """Map a stable browser error code to a coarse queryable category."""
    if not code:
        return "unknown"
    upper = str(code).upper()
    for needle, category in _ERROR_CATEGORIES:
        if needle in upper:
            return category
    return "error"


# A successful action bumps its matching domain counter by this fixed table.
ACTION_DOMAIN_COUNTERS: dict[str, str] = {
    "navigate": "navigations",
    "download": "downloads",
    "upload": "uploads",
    "screenshot": "screenshots",
}


@dataclass
class CostRates:
    """Operator-configured micro-rates. ALL default to 0 = no price invented.

    A measurement is always recorded; a money figure is produced ONLY when at
    least one rate is non-zero, and is then labelled `estimated`.
    """

    localBrowserSecondMicros: int = 0
    cloudBrowserSecondMicros: int = 0
    visionTokenMicros: int = 0
    screenshotMicros: int = 0
    artifactMbMicros: int = 0

    @property
    def configured(self) -> bool:
        return any(
            v
            for v in (
                self.localBrowserSecondMicros, self.cloudBrowserSecondMicros,
                self.visionTokenMicros, self.screenshotMicros, self.artifactMbMicros,
            )
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "localBrowserSecondMicros": self.localBrowserSecondMicros,
            "cloudBrowserSecondMicros": self.cloudBrowserSecondMicros,
            "visionTokenMicros": self.visionTokenMicros,
            "screenshotMicros": self.screenshotMicros,
            "artifactMbMicros": self.artifactMbMicros,
        }


@dataclass
class _ProviderStat:
    sessions: int = 0
    actions: int = 0
    failures: int = 0
    providerFailures: int = 0
    latencySumMs: int = 0
    latencyMaxMs: int = 0
    browserMs: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": self.sessions,
            "actions": self.actions,
            "failures": self.failures,
            "providerFailures": self.providerFailures,
            "latencySumMs": self.latencySumMs,
            "latencyMaxMs": self.latencyMaxMs,
            "browserMs": self.browserMs,
            "avgLatencyMs": int(self.latencySumMs / self.actions) if self.actions else 0,
        }


@dataclass
class _ActionStat:
    count: int = 0
    failures: int = 0
    latencySumMs: int = 0
    latencyMaxMs: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "failures": self.failures,
            "latencySumMs": self.latencySumMs,
            "latencyMaxMs": self.latencyMaxMs,
            "avgLatencyMs": int(self.latencySumMs / self.count) if self.count else 0,
        }


class BrowserTelemetry:
    """Thread-safe, content-free aggregate over browser activity."""

    def __init__(self, *, rates: Optional[CostRates] = None, log_cap: int = DEFAULT_LOG_CAP) -> None:
        # Re-entrant: a counter method may call `log()` while holding the lock.
        self._lock = threading.RLock()
        self._started_at = time.time()
        self._rates = rates or CostRates()
        # Flat counters (fixed vocabulary).
        self._counters: dict[str, int] = {
            "sessionsCreated": 0, "sessionsClosed": 0, "sessionsFailed": 0,
            "crashRestarts": 0,
            "actionCalls": 0, "actionFailures": 0, "timeouts": 0, "crashes": 0,
            "navigations": 0, "downloads": 0, "uploads": 0,
            "screenshots": 0, "visionCalls": 0, "visionUnavailable": 0,
            "humanInterventions": 0, "providerFailures": 0,
            "artifactBytes": 0, "downloadBytes": 0, "uploadCount": 0,
        }
        self._activeSessions = 0
        self._peakSessions = 0
        self._errorCategories: dict[str, int] = {}
        self._providers: dict[str, _ProviderStat] = {}
        self._actions: dict[str, _ActionStat] = {}
        self._browserMs = {"local": 0, "cloud": 0}
        self._visionTokens = 0
        self._logs: deque[dict[str, Any]] = deque(maxlen=max(1, int(log_cap)))

    # ── session lifecycle ─────────────────────────────────────────────────────

    def session_opened(self, provider: str, *, locality: str = "local", session_id: str = "") -> None:
        with self._lock:
            self._counters["sessionsCreated"] += 1
            self._activeSessions += 1
            self._peakSessions = max(self._peakSessions, self._activeSessions)
            self._provider(provider).sessions += 1
        self.log("info", "BROWSER_SESSION_OPENED",
                 f"{locality} session opened", session_id=session_id, provider=provider)

    def session_closed(self, provider: str, *, browser_ms: int = 0, locality: str = "local") -> None:
        with self._lock:
            self._counters["sessionsClosed"] += 1
            self._activeSessions = max(0, self._activeSessions - 1)
            stat = self._provider(provider)
            stat.browserMs += max(0, int(browser_ms))
            self._browserMs[locality if locality in self._browserMs else "local"] += max(0, int(browser_ms))
        self.log("info", "BROWSER_SESSION_CLOSED", "session closed", provider=provider)

    def session_failed(self, provider: str, *, code: Optional[str] = None, session_id: str = "") -> None:
        # A failed CREATE never became an active session, so it does NOT decrement
        # the active gauge (that would drift the count negative over time).
        with self._lock:
            self._counters["sessionsFailed"] += 1
            self._error_categories_inc(classify_error(code))
        self.log("error", code or "BROWSER_SESSION_FAILED", "session failed",
                 session_id=session_id, provider=provider)

    # ── actions ───────────────────────────────────────────────────────────────

    def record_action(
        self, action: str, *, provider: str = "", duration_ms: int = 0,
        ok: bool = True, error_code: Optional[str] = None,
    ) -> None:
        duration_ms = max(0, int(duration_ms))
        with self._lock:
            self._counters["actionCalls"] += 1
            stat = self._action(action)
            stat.count += 1
            stat.latencySumMs += duration_ms
            stat.latencyMaxMs = max(stat.latencyMaxMs, duration_ms)
            pstat = self._provider(provider) if provider else None
            if pstat is not None:
                pstat.actions += 1
                pstat.latencySumMs += duration_ms
                pstat.latencyMaxMs = max(pstat.latencyMaxMs, duration_ms)
            if not ok:
                self._counters["actionFailures"] += 1
                stat.failures += 1
                category = classify_error(error_code)
                self._error_categories_inc(category)
                if category == "timeout":
                    self._counters["timeouts"] += 1
                elif category == "crash":
                    self._counters["crashes"] += 1
                elif category == "provider":
                    self._counters["providerFailures"] += 1
                    if pstat is not None:
                        pstat.providerFailures += 1
                if pstat is not None:
                    pstat.failures += 1
                self.log("error", error_code or "BROWSER_ACTION_FAILED",
                         f"{action} failed", provider=provider)
            else:
                # A successful, recognised op also bumps its domain counter.
                key = ACTION_DOMAIN_COUNTERS.get(action)
                if key:
                    self._counters[key] += 1

    def record_provider_failure(self, provider: str, *, code: Optional[str] = None) -> None:
        with self._lock:
            self._counters["providerFailures"] += 1
            self._provider(provider).providerFailures += 1
            self._error_categories_inc(classify_error(code))
        self.log("error", code or "BROWSER_PROVIDER_ERROR", "provider failure", provider=provider)

    def record_crash_restart(self, provider: str = "") -> None:
        with self._lock:
            self._counters["crashRestarts"] += 1
        self.log("warn", "BROWSER_CRASH_RESTART", "browser restart after a crash", provider=provider)

    # ── domain-specific counters ──────────────────────────────────────────────

    def record_navigation(self, provider: str = "") -> None:
        with self._lock:
            self._counters["navigations"] += 1
        self.log("info", "BROWSER_NAVIGATED", "page opened", provider=provider)

    def record_screenshot(self, count: int = 1) -> None:
        with self._lock:
            self._counters["screenshots"] += max(0, int(count))

    def record_vision(self, *, tokens: int = 0, available: bool = True) -> None:
        with self._lock:
            self._counters["visionCalls"] += 1
            if not available:
                self._counters["visionUnavailable"] += 1
            self._visionTokens += max(0, int(tokens))

    def record_download(self) -> None:
        with self._lock:
            self._counters["downloads"] += 1

    def note_download_size(self, size: Optional[int]) -> None:
        """Add a completed download's byte size (measurement only)."""
        if size and size > 0:
            with self._lock:
                self._counters["downloadBytes"] += int(size)

    def note_upload_count(self, count: int) -> None:
        """Add how many files an upload carried (measurement only)."""
        with self._lock:
            self._counters["uploadCount"] += max(0, int(count))

    def record_upload(self, *, count: int = 1) -> None:
        with self._lock:
            self._counters["uploads"] += 1
            self._counters["uploadCount"] += max(0, int(count))

    def record_human_intervention(self, session_id: str = "") -> None:
        with self._lock:
            self._counters["humanInterventions"] += 1
        self.log("info", "BROWSER_HUMAN_REQUESTED", "human intervention requested", session_id=session_id)

    def record_artifact(self, *, bytes_: int = 0, kind: str = "") -> None:
        with self._lock:
            self._counters["artifactBytes"] += max(0, int(bytes_))
        if kind:
            self.log("debug", "BROWSER_ARTIFACT", f"{kind} artifact stored")

    # ── structured logs (content-free, queryable by code) ─────────────────────

    def log(
        self, level: str, code: str, message: str, *,
        session_id: str = "", run_id: str = "", provider: str = "",
    ) -> None:
        """Append one bounded, content-free log line.

        `message` MUST be a short plain sentence the caller already vetted — no
        page text, no URL query, no secret. It is truncated defensively anyway.
        """
        entry = {
            "at": time.time(),
            "level": str(level)[:16],
            "code": str(code)[:64],
            "message": str(message)[:300],
            "sessionId": session_id or None,
            "runId": run_id or None,
            "provider": provider or None,
        }
        with self._lock:
            self._logs.append(entry)

    def logs(
        self, *, code: Optional[str] = None, level: Optional[str] = None,
        session_id: Optional[str] = None, category: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        capped = max(1, min(int(limit), DEFAULT_LOG_CAP))
        with self._lock:
            entries = list(self._logs)
        out: list[dict[str, Any]] = []
        for entry in reversed(entries):
            if code and str(code).upper() not in entry["code"].upper():
                continue
            if level and entry["level"] != level:
                continue
            if session_id and entry["sessionId"] != session_id:
                continue
            if category and classify_error(entry["code"]) != category:
                continue
            out.append(entry)
            if len(out) >= capped:
                break
        return out

    # ── snapshots / cost ──────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """The full content-free aggregate, including cost and per-provider rows."""
        with self._lock:
            counters = dict(self._counters)
            active = self._activeSessions
            peak = self._peakSessions
            errors = dict(self._errorCategories)
            providers = {pid: stat.to_dict() for pid, stat in self._providers.items()}
            actions = {name: stat.to_dict() for name, stat in self._actions.items()}
            browser_ms = dict(self._browserMs)
            vision_tokens = self._visionTokens
            uptime = int(time.time() - self._started_at)
        return {
            "uptimeSeconds": uptime,
            "sessions": {
                "created": counters["sessionsCreated"],
                "closed": counters["sessionsClosed"],
                "failed": counters["sessionsFailed"],
                "active": active,
                "peak": peak,
            },
            "actions": {
                "calls": counters["actionCalls"],
                "failures": counters["actionFailures"],
                "timeouts": counters["timeouts"],
                "crashes": counters["crashes"],
                "crashRestarts": counters["crashRestarts"],
                "navigations": counters["navigations"],
                "downloads": counters["downloads"],
                "uploads": counters["uploads"],
                "screenshots": counters["screenshots"],
                "visionCalls": counters["visionCalls"],
                "visionUnavailable": counters["visionUnavailable"],
                "humanInterventions": counters["humanInterventions"],
                "providerFailures": counters["providerFailures"],
                "errorCategories": errors,
            },
            "providers": providers,
            "byAction": actions,
            "cost": self._cost(browser_ms, vision_tokens, counters, providers),
            "logs": {"count": len(self._logs)},
        }

    def cost(self) -> dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            browser_ms = dict(self._browserMs)
            vision_tokens = self._visionTokens
            providers = {pid: stat.to_dict() for pid, stat in self._providers.items()}
        return self._cost(browser_ms, vision_tokens, counters, providers)

    def _cost(
        self, browser_ms: dict[str, int], vision_tokens: int,
        counters: dict[str, int], providers: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        measurements = {
            "localBrowserSeconds": round(browser_ms.get("local", 0) / 1000.0, 3),
            "cloudBrowserSeconds": round(browser_ms.get("cloud", 0) / 1000.0, 3),
            "visionTokens": vision_tokens,
            "screenshots": counters["screenshots"],
            "artifactBytes": counters["artifactBytes"],
            "downloadBytes": counters["downloadBytes"],
        }
        rates = self._rates
        result: dict[str, Any] = {
            "measurements": measurements,
            "rates": rates.to_dict(),
            "ratesConfigured": rates.configured,
            "estimatedMicros": None,
            "perProvider": {
                pid: {"browserSeconds": round(row.get("browserMs", 0) / 1000.0, 3)}
                for pid, row in providers.items()
            },
        }
        if rates.configured:
            micros = (
                measurements["localBrowserSeconds"] * rates.localBrowserSecondMicros
                + measurements["cloudBrowserSeconds"] * rates.cloudBrowserSecondMicros
                + measurements["visionTokens"] * rates.visionTokenMicros
                + measurements["screenshots"] * rates.screenshotMicros
                + (measurements["artifactBytes"] / 1_000_000.0) * rates.artifactMbMicros
            )
            result["estimatedMicros"] = int(round(micros))
            result["estimatedUsd"] = round(micros / 1_000_000.0, 6)
        return result

    # ── maintenance ───────────────────────────────────────────────────────────

    def reset(self) -> None:
        with self._lock:
            self.__init__(rates=self._rates, log_cap=self._logs.maxlen or DEFAULT_LOG_CAP)  # noqa: PLC2801

    # ── internals ─────────────────────────────────────────────────────────────

    def _provider(self, provider: str) -> _ProviderStat:
        pid = (provider or "unknown")[:_MAX_PROVIDERS]
        stat = self._providers.get(pid)
        if stat is None:
            stat = _ProviderStat()
            self._providers[pid] = stat
        return stat

    def _action(self, action: str) -> _ActionStat:
        name = (action or "unknown")[:64]
        stat = self._actions.get(name)
        if stat is None:
            stat = _ActionStat()
            self._actions[name] = stat
        return stat

    def _error_categories_inc(self, category: str) -> None:
        self._errorCategories[category] = self._errorCategories.get(category, 0) + 1


_TELEMETRY: Optional[BrowserTelemetry] = None
_TELEMETRY_LOCK = threading.Lock()


def _rates_from_config() -> CostRates:
    try:
        from .config import browser_config  # noqa: PLC0415

        cfg = browser_config()
        return CostRates(
            localBrowserSecondMicros=int(getattr(cfg, "cost_local_second_micros", 0) or 0),
            cloudBrowserSecondMicros=int(getattr(cfg, "cost_cloud_second_micros", 0) or 0),
            visionTokenMicros=int(getattr(cfg, "cost_vision_token_micros", 0) or 0),
            screenshotMicros=int(getattr(cfg, "cost_screenshot_micros", 0) or 0),
            artifactMbMicros=int(getattr(cfg, "cost_artifact_mb_micros", 0) or 0),
        )
    except Exception:  # noqa: BLE001 - telemetry must never break boot
        return CostRates()


def get_telemetry() -> BrowserTelemetry:
    """The process-wide aggregate (created lazily, bound to the browser config)."""
    global _TELEMETRY
    if _TELEMETRY is None:
        with _TELEMETRY_LOCK:
            if _TELEMETRY is None:
                cap = DEFAULT_LOG_CAP
                try:
                    from .config import browser_config  # noqa: PLC0415

                    cap = int(getattr(browser_config(), "telemetry_log_cap", DEFAULT_LOG_CAP) or DEFAULT_LOG_CAP)
                except Exception:  # noqa: BLE001 - telemetry must never break boot
                    cap = DEFAULT_LOG_CAP
                _TELEMETRY = BrowserTelemetry(rates=_rates_from_config(), log_cap=cap)
    return _TELEMETRY


def set_telemetry(telemetry: Optional[BrowserTelemetry]) -> None:
    global _TELEMETRY
    _TELEMETRY = telemetry


def reset_telemetry() -> BrowserTelemetry:
    telemetry = get_telemetry()
    telemetry.reset()
    return telemetry


__all__ = [
    "BrowserTelemetry",
    "CostRates",
    "DEFAULT_LOG_CAP",
    "classify_error",
    "get_telemetry",
    "reset_telemetry",
    "set_telemetry",
]
