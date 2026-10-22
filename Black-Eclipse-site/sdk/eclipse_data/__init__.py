"""eclipse_data — Eclipse's data and research from a notebook.

The runtime is the authority; this package is a thin client for it. Everything
here is a call the runtime already serves, so a notebook and the app see the
SAME bars, the SAME verdict and the SAME project.

```python
import eclipse_data as ed

bars = ed.get_bars("AAPL", interval="1d", start="2024-01-01", end="2024-06-30")
report = ed.edge_report("exp_abc123")
print(report["verdict"]["grade"], report["verdict"]["summary"])
```

The client talks to the local runtime by default (``http://127.0.0.1:8765``)
and authenticates with the runtime's operator token when one is configured
(``CRON_SECRET``). It never invents a value: a refusal from the runtime is
raised as an :class:`EclipseRuntimeError` with the runtime's own code and
message.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

__all__ = [
    "EclipseData",
    "EclipseRuntimeError",
    "get_bars",
    "list_projects",
    "project",
    "project_digest",
    "project_proposals",
    "edge_report",
    "prop_firm",
    "pine",
    "pine_report",
]

DEFAULT_BASE_URL = "http://127.0.0.1:8765"


class EclipseRuntimeError(RuntimeError):
    """The runtime refused the call. Its own code and message are kept."""

    def __init__(self, message: str, *, code: str = "RUNTIME_ERROR",
                 status: Optional[int] = None, detail: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.detail = detail


class EclipseData:
    """A client for the local Eclipse runtime."""

    def __init__(self, base_url: Optional[str] = None, *, token: Optional[str] = None,
                 timeout: float = 30.0) -> None:
        self.base_url = (base_url or os.environ.get("ECLIPSE_HARNESS_URL")
                         or os.environ.get("HARNESS_PY_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.token = token if token is not None else os.environ.get("CRON_SECRET")
        self.timeout = timeout

    # ── transport ────────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: Optional[dict[str, Any]] = None
                 ) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(url, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("X-Harness-Operator", self.token)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            detail: Any = raw
            message = f"the runtime refused the call ({exc.code})"
            try:
                parsed = json.loads(raw)
                detail = parsed
                if isinstance(parsed, dict):
                    inner = parsed.get("detail")
                    if isinstance(inner, dict) and inner.get("message"):
                        message = str(inner["message"])
                    elif isinstance(inner, str):
                        message = inner
            except ValueError:
                pass
            raise EclipseRuntimeError(message, code=f"HTTP_{exc.code}",
                                      status=exc.code, detail=detail) from exc
        except URLError as exc:
            raise EclipseRuntimeError(
                f"the Eclipse runtime is not reachable at {self.base_url}: "
                f"{exc.reason}",
                code="RUNTIME_UNREACHABLE") from exc
        try:
            return json.loads(payload) if payload else {}
        except ValueError as exc:
            raise EclipseRuntimeError("the runtime's response was not JSON",
                                     code="BAD_RESPONSE") from exc

    # ── market data ──────────────────────────────────────────────────────────

    def get_bars(self, symbol: str, *, interval: str = "1d",
                  start: Optional[str] = None, end: Optional[str] = None,
                  provider: Optional[str] = None,
                  verification_policy: Optional[str] = None) -> dict[str, Any]:
        """Normalized OHLCV for one instrument, with its provenance.

        The runtime's answer carries the provider, the timestamps, the quality
        findings and - when the policy asks for it - an independent
        cross-source verification outcome. It never averages two sources.
        """
        body: dict[str, Any] = {"symbols": [symbol], "interval": interval}
        if start:
            body["start"] = start
        if end:
            body["end"] = end
        if provider:
            body["provider"] = provider
        if verification_policy:
            body["verification_policy"] = verification_policy
        return self._request("POST", "/research-data/market-data", body)

    def coverage(self, symbol: str, *, interval: str = "1d") -> dict[str, Any]:
        """What the runtime already holds for an instrument."""
        return self._request("GET", f"/research-data/series?symbol={symbol}"
                                          f"&interval={interval}")

    # ── projects ─────────────────────────────────────────────────────────────

    def list_projects(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/projects").get("projects") or [])

    def project(self, project_id: str) -> dict[str, Any]:
        return self._request("GET", f"/projects/{project_id}")

    def project_digest(self, project_id: str) -> dict[str, Any]:
        """The curated view: what the project is, and what it lacks."""
        return self._request("GET", f"/projects/{project_id}/digest").get("digest", {})

    def project_proposals(self, project_id: str) -> dict[str, Any]:
        """What the project proposes next, from its own evidence."""
        return self._request("GET", f"/projects/{project_id}/proposals")

    # ── research ─────────────────────────────────────────────────────────────

    def edge_report(self, experiment_id: str, *,
                    monte_carlo_experiment_id: Optional[str] = None) -> dict[str, Any]:
        """The Edge Report of a stored backtest: the grade and the evidence."""
        body: dict[str, Any] = {"experimentId": experiment_id}
        if monte_carlo_experiment_id:
            body["monteCarloExperimentId"] = monte_carlo_experiment_id
        return self._request("POST", "/quant/edge-report", body)

    def prop_firm(self, trades: list[dict[str, Any]], *, firm: str = "topstep",
                  size: str = "50k", simulations: int = 300) -> dict[str, Any]:
        """A trade log against a firm's real evaluation rules."""
        return self._request("POST", "/quant/prop-firm", {
            "trades": trades, "firm": firm, "size": size, "simulations": simulations,
        })

    def pine(self, source: str, bars: list[dict[str, Any]], *,
             symbol: str = "UNKNOWN", timeframe: str = "1d") -> dict[str, Any]:
        """Run a Pine Script on bars and get its plots and trades."""
        return self._request("POST", "/quant/pine", {
            "source": source, "bars": bars, "symbol": symbol, "timeframe": timeframe,
        })

    def pine_report(self, source: str, bars: list[dict[str, Any]], *,
                    symbol: str = "UNKNOWN", timeframe: str = "1d") -> dict[str, Any]:
        """Run a Pine Script and grade it with ECLIPSE's own machinery."""
        return self._request("POST", "/quant/pine/report", {
            "source": source, "bars": bars, "symbol": symbol, "timeframe": timeframe,
        })


_DEFAULT: Optional[EclipseData] = None


def _client() -> EclipseData:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = EclipseData()
    return _DEFAULT


def get_bars(symbol: str, **kwargs: Any) -> dict[str, Any]:
    """Normalized OHLCV for one instrument."""
    return _client().get_bars(symbol, **kwargs)


def coverage(symbol: str, **kwargs: Any) -> dict[str, Any]:
    """What the runtime already holds for an instrument."""
    return _client().coverage(symbol, **kwargs)


def list_projects() -> list[dict[str, Any]]:
    """Every project the runtime holds."""
    return _client().list_projects()


def project(project_id: str) -> dict[str, Any]:
    """One project and its members."""
    return _client().project(project_id)


def project_digest(project_id: str) -> dict[str, Any]:
    """The curated view of a project."""
    return _client().project_digest(project_id)


def project_proposals(project_id: str) -> dict[str, Any]:
    """What a project proposes next."""
    return _client().project_proposals(project_id)


def edge_report(experiment_id: str, **kwargs: Any) -> dict[str, Any]:
    """The Edge Report of a stored backtest."""
    return _client().edge_report(experiment_id, **kwargs)


def prop_firm(trades: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """A trade log against a firm's real evaluation rules."""
    return _client().prop_firm(trades, **kwargs)


def pine(source: str, bars: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """Run a Pine Script on bars."""
    return _client().pine(source, bars, **kwargs)


def pine_report(source: str, bars: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """Run a Pine Script and grade it with ECLIPSE's own machinery."""
    return _client().pine_report(source, bars, **kwargs)
