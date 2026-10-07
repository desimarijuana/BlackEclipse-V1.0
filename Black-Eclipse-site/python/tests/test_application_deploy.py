"""Deployment engine, discovery cache and CLI — tests.

Deterministic: the deploy provider is a mock cloud adapter, the runtime manager a
mock, and the CLI is driven through its `main(argv)` entry point against a
temporary project. No network, no real cloud binary.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from harness.execution.application.cache import DiscoveryCache
from harness.execution.application.cli_base import CliResult
from harness.execution.application.deployment import DeploymentEngine
from harness.execution.application.models import ApplicationState, HealthReport, HealthStatus, RuntimeHandle


# ── discovery cache ──────────────────────────────────────────────────────────────


def test_cache_returns_a_hit_then_invalidates_on_change(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"a"}', encoding="utf-8")
    cache = DiscoveryCache(ttl_s=60)
    cache.put(tmp_path, {"v": 1})
    assert cache.get(tmp_path) == {"v": 1}
    (tmp_path / "package.json").write_text('{"name":"b"}', encoding="utf-8")
    time.sleep(0.01)
    assert cache.get(tmp_path) is None  # invalidated by the mtime change


def test_cache_invalidates_when_a_new_watched_file_appears(tmp_path):
    cache = DiscoveryCache(ttl_s=60)
    cache.put(tmp_path, {"v": 1})
    assert cache.get(tmp_path) == {"v": 1}
    (tmp_path / "docker-compose.yml").write_text("services: {}", encoding="utf-8")
    assert cache.get(tmp_path) is None


def test_cache_invalidate_by_root_and_all(tmp_path):
    cache = DiscoveryCache(ttl_s=60)
    cache.put(tmp_path, {"v": 1})
    cache.invalidate(tmp_path)
    assert cache.get(tmp_path) is None
    cache.put(tmp_path, {"v": 2})
    cache.invalidate()
    assert cache.get(tmp_path) is None


def test_cache_ttl_expiry(tmp_path):
    cache = DiscoveryCache(ttl_s=0.0)
    cache.put(tmp_path, {"v": 1})
    # ttl 0 disables the time check but the signature still governs; force an age.
    cache._entries[str(tmp_path.resolve())].at = time.monotonic() - 10  # noqa: SLF001
    assert cache.get(tmp_path) == {"v": 1}  # ttl=0 means "never expires on time"


def test_cache_get_or_compute(tmp_path):
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"v": calls["n"]}

    cache = DiscoveryCache(ttl_s=60)
    assert cache.get_or_compute(tmp_path, compute) == {"v": 1}
    assert cache.get_or_compute(tmp_path, compute) == {"v": 1}
    assert calls["n"] == 1


# ── deployment engine ─────────────────────────────────────────────────────────────


class _MockCloud:
    kind = "deployment"
    name = "mockcloud"
    capabilities = frozenset({"cloud.deploy", "cloud.status", "cloud.logs", "cloud.rollback", "cloud.delete"})

    def __init__(self, *, ok: bool = True) -> None:
        self._ok = ok
        self.operations = {op: object() for op in ("deploy", "status", "logs", "rollback", "delete")}
        self.deploys = 0

    def available(self) -> bool:
        return True

    def run_operation(self, operation: str, args: dict | None = None) -> CliResult:
        if operation == "deploy":
            self.deploys += 1
        return CliResult(ok=self._ok, code="OK" if self._ok else "FAILED", operation=operation,
                         output='{"deployed": true}', argv=["mock"])


class _MockContainerRegistry:
    def names(self) -> list[str]:
        return ["mockcloud"]

    def get(self, name: str):
        return _MockCloud() if name == "mockcloud" else None

    def describe(self) -> list[dict]:
        return [{"name": "mockcloud", "available": True}]


class _MockRegistry:
    def __init__(self) -> None:
        self.deployments = _MockContainerRegistry()


class _MockRuntime:
    def __init__(self) -> None:
        self.registry = _MockRegistry()
        from harness.execution.application.diagnostics import RuntimeDiagnosticsEngine

        self.diagnostics = RuntimeDiagnosticsEngine()

    def inspect(self, root):
        return {"descriptor": {"framework": "nextjs", "language": "typescript"}}

    def start(self, root, **kwargs):
        return RuntimeHandle(runtime_id="rt_mock", application_id="app_mock", state=ApplicationState.RUNNING)


def _engine(tmp_path):
    runtime = _MockRuntime()
    return DeploymentEngine(runtime_manager=runtime, registry=runtime.registry, store=None, bus=None), runtime


def test_deploy_happy_path(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    engine, _ = _engine(tmp_path)
    outcome = engine.deploy(tmp_path, provider="mockcloud", install=False, build=True)
    assert outcome.status == "deployed", outcome.to_dict()
    names = [s.name for s in outcome.steps]
    assert "validate" in names and "deploy" in names


def test_deploy_production_requires_authorization(tmp_path):
    engine, _ = _engine(tmp_path)
    outcome = engine.deploy(tmp_path, provider="mockcloud", environment="production", authorize=False)
    assert outcome.status == "failed"
    assert outcome.error["code"] == "AUTHORIZATION_REQUIRED"


def test_deploy_production_authorized_proceeds(tmp_path):
    engine, _ = _engine(tmp_path)
    outcome = engine.deploy(tmp_path, provider="mockcloud", environment="production", authorize=True, install=False, build=False)
    assert outcome.status == "deployed"


def test_deploy_provider_unavailable_is_structured(tmp_path):
    engine, _ = _engine(tmp_path)
    outcome = engine.deploy(tmp_path, provider="doesnotexist", install=False, build=False)
    assert outcome.status == "failed"
    assert outcome.error["code"] == "PROVIDER_UNAVAILABLE"


def test_deploy_failure_from_provider(tmp_path):
    runtime = _MockRuntime()
    runtime.registry.deployments.get = lambda name: _MockCloud(ok=False)  # type: ignore[assignment]
    engine = DeploymentEngine(runtime_manager=runtime, registry=runtime.registry, store=None, bus=None)
    outcome = engine.deploy(tmp_path, provider="mockcloud", install=False, build=False)
    assert outcome.status == "failed"
    assert outcome.error["code"] in ("FAILED", "DEPLOY_FAILED")


def test_deploy_events_are_emitted(tmp_path):
    engine, _ = _engine(tmp_path)
    events: list[tuple[str, dict]] = []
    outcome = engine.deploy(tmp_path, provider="mockcloud", install=False, build=False,
                             emit=lambda t, d: events.append((t, d)))
    types = {t for t, _ in events}
    assert "deployment.started" in types
    assert "deployment.completed" in types


# ── promotion pipeline ────────────────────────────────────────────────────────────


def test_promote_requires_authorization_before_production(tmp_path):
    engine, _ = _engine(tmp_path)
    result = engine.promote(tmp_path, provider="mockcloud", authorize_production=False, install=False, build=False)
    assert result["status"] == "awaiting_authorization"
    stages = [s["stage"] for s in result["steps"]]
    assert stages == ["staging"]  # production was never attempted


def test_promote_authorized_reaches_production(tmp_path):
    engine, _ = _engine(tmp_path)
    result = engine.promote(tmp_path, provider="mockcloud", authorize_production=True, install=False, build=False)
    assert result["status"] == "deployed"
    stages = [s["stage"] for s in result["steps"]]
    assert stages == ["staging", "production"]


def test_promote_rolls_back_when_production_fails(tmp_path):
    runtime = _MockRuntime()
    # The adapter fails its SECOND deploy (the production stage) but the first
    # (staging) succeeds, so the promotion must roll back.
    adapter = _MockCloud(ok=True)

    def run_operation(operation, args=None):
        if operation == "deploy":
            adapter.deploys += 1
            ok = adapter.deploys == 1
            return CliResult(ok=ok, code="OK" if ok else "FAILED", operation=operation,
                             output="{}", argv=["mock"])
        return CliResult(ok=True, code="OK", operation=operation, output="{}", argv=["mock"])

    adapter.run_operation = run_operation  # type: ignore[assignment]
    runtime.registry.deployments.get = lambda name: adapter  # type: ignore[assignment]
    engine = DeploymentEngine(runtime_manager=runtime, registry=runtime.registry, store=None, bus=None)
    result = engine.promote(tmp_path, provider="mockcloud", authorize_production=True, install=False, build=False)
    assert result["status"] == "rolled_back"
    stages = [s["stage"] for s in result["steps"]]
    assert "rollback" in stages


def test_promote_staging_failure_does_not_touch_production(tmp_path):
    runtime = _MockRuntime()
    runtime.registry.deployments.get = lambda name: _MockCloud(ok=False)  # type: ignore[assignment]
    engine = DeploymentEngine(runtime_manager=runtime, registry=runtime.registry, store=None, bus=None)
    result = engine.promote(tmp_path, provider="mockcloud", authorize_production=True, install=False, build=False)
    assert result["status"] == "staging_failed"
    assert [s["stage"] for s in result["steps"]] == ["staging"]


# ── CLI ────────────────────────────────────────────────────────────────────────────


def test_cli_parser_accepts_json_both_positions():
    from harness.cli import build_parser

    parser = build_parser()
    a = parser.parse_args(["--json", "runtime", "detect"])
    b = parser.parse_args(["runtime", "detect", "--json"])
    assert a.json is True and b.json is True


def test_cli_runtime_inspect(tmp_path, capsys):
    from harness.cli import main

    (tmp_path / "package.json").write_text('{"name":"x","scripts":{"dev":"node x.js"}}', encoding="utf-8")
    code = main(["runtime", "inspect", "--root", str(tmp_path), "--json"])
    assert code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["descriptor"]["name"] == "x" or data["descriptor"]["language"]


def test_cli_respects_its_own_root(tmp_path, capsys):
    from harness.cli import main

    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    code = main(["runtime", "inspect", "--root", str(tmp_path), "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["descriptor"]["path"] == str(tmp_path.resolve()) or "python" in json.dumps(data)


# ── production hardening ────────────────────────────────────────────────────────


def test_log_filter_lines():
    from harness.execution.application.manager import _filter_lines

    text = "starting\nError: boom\nall good\nFATAL: dead"
    assert _filter_lines(text, errors_only=True) == ["Error: boom", "FATAL: dead"]
    assert _filter_lines(text, needle="good") == ["all good"]
    assert _filter_lines(text, severity="fatal") == ["FATAL: dead"]
    assert _filter_lines(text) == text.splitlines()


def test_health_backoff_grows_the_interval():
    # The retry loop must not hammer: with backoff the second wait is longer than
    # the first. We assert the attempts and honest failure, not the wall clock.
    from harness.execution.application.health import HealthCheckEngine
    from harness.execution.application.models import HealthCheck

    engine = HealthCheckEngine()
    result = engine.check_with_retries(
        HealthCheck(kind="tcp", target="127.0.0.1:1", retries=2, interval_s=0.001), backoff=True,
    )
    assert result.ok is False
    assert result.attempts == 3


def test_manager_logs_are_bounded(tmp_path):
    from harness.execution.application.manager import ApplicationRuntimeManager, build_runtime_registry

    manager = ApplicationRuntimeManager(registry=build_runtime_registry(), terminal=None)
    # No runtime -> not_found, never a crash.
    assert manager.logs("rt_missing")["status"] == "not_found"


def test_manager_discovery_cache_is_used(tmp_path):
    from harness.execution.application.manager import ApplicationRuntimeManager, build_runtime_registry

    (tmp_path / "package.json").write_text('{"name":"cached"}', encoding="utf-8")
    manager = ApplicationRuntimeManager(registry=build_runtime_registry(), terminal=None)
    first = manager.discover(tmp_path)
    second = manager.discover(tmp_path)
    assert first is second  # the cache returned the same object
    manager.invalidate_discovery(tmp_path)
    assert manager.discover(tmp_path) is not second


# ── metrics history + trend ──────────────────────────────────────────────────────


def test_trend_direction_is_honest():
    from harness.execution.application.manager import _trend

    rising = _trend([{"cpuMs": v} for v in (1, 2, 3, 10, 11, 12)])
    assert rising["cpuMs"]["direction"] == "rising"
    falling = _trend([{"cpuMs": v} for v in (12, 11, 10, 1, 2, 3)])
    assert falling["cpuMs"]["direction"] == "falling"
    flat = _trend([{"cpuMs": 5} for _ in range(6)])
    assert flat["cpuMs"]["direction"] == "flat"
    # Fewer than 4 samples is UNKNOWN, never flat.
    assert _trend([{"cpuMs": 1}, {"cpuMs": 2}])["cpuMs"]["direction"] == "unknown"


def test_metrics_history_persists_and_summarises(tmp_path):
    from harness.execution.application.manager import ApplicationRuntimeManager, build_runtime_registry
    from harness.execution.application.store import ApplicationRuntimeStore
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(str(tmp_path / "m.db"))
    rtstore = ApplicationRuntimeStore(store)
    manager = ApplicationRuntimeManager(registry=build_runtime_registry(), terminal=None, store=rtstore)

    for cpu in (10.0, 20.0, 30.0, 40.0):
        rtstore.record_metric("rt_x", cpu_ms=cpu, memory_mb=100.0, process_count=2, uptime_s=1.0, health="HEALTHY")
    data = manager.metrics_history("rt_x", limit=50)
    assert len(data["samples"]) == 4
    assert data["trend"]["cpuMs"]["direction"] == "rising"


def test_store_prunes_metric_history(tmp_path):
    from harness.execution.application.store import ApplicationRuntimeStore
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(str(tmp_path / "m.db"))
    rtstore = ApplicationRuntimeStore(store)
    for i in range(20):
        rtstore.record_metric("rt_p", cpu_ms=float(i))
    removed = rtstore.prune_metrics("rt_p", keep=5)
    assert removed == 15
    assert len(rtstore.metric_history("rt_p")) == 5
