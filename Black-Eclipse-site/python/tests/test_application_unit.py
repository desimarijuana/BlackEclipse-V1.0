"""Application Runtime layer — unit tests (pure, fast, no subprocesses).

Covers discovery, environment/secret masking, the registry + capability contract,
the state machine, the port manager, the health engine, diagnostics and bounded
recovery. The integration/security tests live in the sibling test modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.execution.application import (
    ApplicationState,
    ApplicationStateMachine,
    DiagnosticCategory,
    EnvironmentManager,
    HealthCheck,
    HealthCheckEngine,
    HealthStatus,
    PortManager,
    RecoveryEngine,
    RecoveryStrategy,
    RuntimeDiagnosticsEngine,
    RuntimeDiagnosis,
    build_package_manager_registry,
    build_service_graph,
    discover_application,
    is_secret_name,
    recovery_budget,
)
from harness.execution.application.discovery import _parse_compose_services
from harness.execution.application.registry import (
    ContainerRuntimeRegistry,
    PackageManagerRegistry,
    supports,
)

# ── state machine ──────────────────────────────────────────────────────────────


def test_state_machine_happy_path():
    machine = ApplicationStateMachine(ApplicationState.UNKNOWN)
    for state in (
        ApplicationState.DISCOVERING, ApplicationState.DISCOVERED,
        ApplicationState.VALIDATING, ApplicationState.PREPARING,
        ApplicationState.INSTALLING, ApplicationState.BUILDING,
        ApplicationState.STARTING, ApplicationState.RUNNING,
        ApplicationState.STOPPING, ApplicationState.STOPPED,
    ):
        machine.to(state)
    assert machine.state is ApplicationState.STOPPED
    assert machine.terminal


def test_terminal_states_have_no_outgoing_edges():
    from harness.execution.application.state import can_transition

    for state in (ApplicationState.STOPPED, ApplicationState.FAILED):
        for target in ApplicationState:
            assert not can_transition(state, target)


def test_invalid_transition_refused():
    from harness.execution.application.state import InvalidTransition

    machine = ApplicationStateMachine(ApplicationState.DISCOVERING)
    with pytest.raises(InvalidTransition):
        machine.to(ApplicationState.RUNNING)


def test_force_terminal_only_accepts_terminal():
    from harness.execution.application.state import InvalidTransition

    machine = ApplicationStateMachine(ApplicationState.RUNNING)
    with pytest.raises(InvalidTransition):
        machine.force_terminal(ApplicationState.RUNNING)
    machine.force_terminal(ApplicationState.FAILED)
    assert machine.state is ApplicationState.FAILED


# ── discovery ──────────────────────────────────────────────────────────────────


def test_discover_node_pnpm_nextjs(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"name":"demo","scripts":{"dev":"next dev","build":"next build","test":"vitest"},'
        '"dependencies":{"next":"14"},"devDependencies":{"typescript":"5","vitest":"1"}}',
        encoding="utf-8",
    )
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM node", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        'services:\n  web:\n    build: .\n    ports:\n      - "3000:3000"\n'
        "    depends_on:\n      - db\n  db:\n    image: postgres:16\n    ports:\n      - \"5432:5432\"\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text("DATABASE_URL=\nAPI_KEY=\n", encoding="utf-8")
    descriptor = discover_application(tmp_path)
    assert descriptor.framework == "nextjs"
    assert descriptor.language == "typescript"
    assert descriptor.package_manager == "pnpm"
    assert descriptor.lockfile == "pnpm-lock.yaml"
    assert descriptor.docker is True and descriptor.compose is True
    assert descriptor.compose_file == "docker-compose.yml"
    assert set(descriptor.services) == {"web", "db"}
    assert 3000 in descriptor.ports and 5432 in descriptor.ports
    assert "postgresql" in descriptor.databases
    assert descriptor.commands["dev"] == "pnpm run dev"
    assert "DATABASE_URL" in descriptor.required_env


def test_discover_python_fastapi(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='api'\ndependencies=['fastapi']\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi==0.110\nuvicorn\n", encoding="utf-8")
    descriptor = discover_application(tmp_path)
    assert descriptor.language == "python"
    assert descriptor.framework == "fastapi"
    assert 8000 in descriptor.ports


def test_discover_rust_go(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    descriptor = discover_application(tmp_path)
    assert descriptor.language == "rust"
    assert descriptor.package_manager == "cargo"


def test_discover_no_manifests_is_honest(tmp_path):
    descriptor = discover_application(tmp_path)
    assert descriptor.language == ""
    assert descriptor.docker is False and descriptor.compose is False
    assert descriptor.commands == {}


def test_compose_parser_handles_nested_depends_on():
    text = (
        "services:\n  web:\n    build: .\n    ports:\n      - 3000:3000\n"
        "    depends_on:\n      - db\n      - cache\n  db:\n    image: postgres\n"
    )
    services = _parse_compose_services(text)
    by_name = {s.name: s for s in services}
    assert set(by_name) == {"web", "db"}
    assert by_name["web"].ports == [3000]
    assert set(by_name["web"].depends_on) == {"db", "cache"}
    assert by_name["db"].image == "postgres"


def test_service_graph_startup_order():
    (tmp := __import__("tempfile").mkdtemp())
    root = Path(tmp)
    (root / "docker-compose.yml").write_text(
        "services:\n  web:\n    build: .\n    depends_on:\n      - api\n"
        "  api:\n    build: .\n    depends_on:\n      - db\n  db:\n    image: postgres\n",
        encoding="utf-8",
    )
    descriptor = discover_application(root)
    graph = build_service_graph(descriptor, _parse_compose_services((root / "docker-compose.yml").read_text()))
    order = graph.startup_order()
    assert order.index("db") < order.index("api") < order.index("web")


# ── environment ────────────────────────────────────────────────────────────────


def test_secret_name_detection():
    assert is_secret_name("DATABASE_URL")
    assert is_secret_name("POSTGRES_PASSWORD")
    assert is_secret_name("API_KEY")
    assert is_secret_name("AWS_SECRET_ACCESS_KEY")
    assert not is_secret_name("PORT")
    assert not is_secret_name("NODE_ENV")
    assert not is_secret_name("NEXT_PUBLIC_APP_NAME")


def test_environment_manager_masks_secrets(tmp_path):
    (tmp_path / ".env").write_text("PORT=3000\nDATABASE_URL=postgres://u:p@h/db\nAPI_KEY=sk-123\n", encoding="utf-8")
    manager = EnvironmentManager()
    report = manager.load(tmp_path)
    values = {v.name: v.safe_value() for v in report.vars}
    assert values["PORT"] == "3000"
    assert values["DATABASE_URL"] == "[SECRET]"
    assert values["API_KEY"] == "[SECRET]"
    meta = manager.metadata(tmp_path)
    # The metadata NEVER contains a secret value.
    assert all("value" not in item for item in meta["variables"])
    assert set(meta["variables"][1].keys()) == {"name", "secret", "empty", "source"}


def test_environment_validate_missing(tmp_path):
    (tmp_path / ".env.example").write_text("DATABASE_URL=\nAPI_KEY=\n", encoding="utf-8")
    manager = EnvironmentManager()
    result = manager.validate(tmp_path)
    assert result["ok"] is False
    assert "DATABASE_URL" in result["missing"]


def test_environment_set_refuses_example(tmp_path):
    (tmp_path / ".env.example").write_text("A=1\n", encoding="utf-8")
    manager = EnvironmentManager()
    result = manager.set(tmp_path / ".env.example", "B", "2")
    assert result["status"] == "refused"


def test_environment_set_and_unset(tmp_path):
    manager = EnvironmentManager()
    path = tmp_path / ".env"
    assert manager.set(path, "PORT", "3000")["status"] == "ok"
    assert manager.set(path, "API_KEY", "secret")["status"] == "ok"
    report = manager.load(tmp_path)
    assert any(v.name == "PORT" and v.value == "3000" for v in report.vars)
    assert manager.unset(path, "API_KEY")["removed"] is True
    assert not any(v.name == "API_KEY" for v in manager.load(tmp_path).vars)


# ── registry / capabilities ─────────────────────────────────────────────────────


def test_package_manager_registry_declared_is_authoritative():
    registry = build_package_manager_registry()
    descriptor = discover_application(Path(__file__).parent)  # any root
    descriptor.package_manager = "pnpm"
    adapter = registry.detect(Path("."), descriptor)
    assert adapter is not None and adapter.name == "pnpm"


def test_capability_contract_is_closed():
    from harness.execution.application.registry import ALL_CAPABILITIES

    registry = build_package_manager_registry()
    for adapter in (registry.get("cargo"), registry.get("go")):
        assert supports(adapter, "build")
        # An adapter never declares a capability it does not implement.
        assert not supports(adapter, "compose.up")


def test_container_registry_detect_absent_is_none():
    registry = ContainerRuntimeRegistry()
    # Empty registry → honestly no engine, never a fake.
    assert registry.detect() is None


# ── ports ──────────────────────────────────────────────────────────────────────


def test_port_manager_check_and_find_free():
    ports = PortManager(terminal=None, range_start=45000, range_end=45100)
    result = ports.check(45050)
    # Either free or (rarely) used by something; both are honest.
    assert "inUse" in result
    free = ports.find_free()
    assert 45000 <= free <= 45100
    record = ports.allocate(owner="test")
    assert record.port == free
    # A reserved port is reported in use and managed.
    conflict = ports.identify(free)
    assert conflict is not None and conflict.managed
    ports.release(free)


# ── health ──────────────────────────────────────────────────────────────────────


def test_health_process_check_unhealthy_without_terminal():
    engine = HealthCheckEngine(terminal=None)
    result = engine.process(HealthCheck(kind="process", target="proc_x"))
    assert result.ok is False
    assert result.status is HealthStatus.UNHEALTHY


def test_health_tcp_check_unreachable():
    engine = HealthCheckEngine()
    result = engine.tcp(HealthCheck(kind="tcp", target="127.0.0.1:1", timeout_s=0.2))
    assert result.ok is False


def test_health_evaluate_no_checks_is_unknown():
    engine = HealthCheckEngine()
    report = engine.evaluate([])
    assert report.status is HealthStatus.UNKNOWN


def test_health_custom_check_raising_is_unhealthy_not_crash():
    engine = HealthCheckEngine()

    def boom(_check):
        raise RuntimeError("nope")

    result = engine.custom(HealthCheck(kind="custom", name="c"), boom)
    assert result.status is HealthStatus.UNHEALTHY


# ── diagnostics ─────────────────────────────────────────────────────────────────


def test_diagnose_port_conflict():
    engine = RuntimeDiagnosticsEngine()
    diag = engine.classify(port_conflict=3000)
    assert diag.category is DiagnosticCategory.PORT_CONFLICT
    assert RecoveryStrategy.SELECT_ALTERNATIVE_PORT in diag.suggested_actions


def test_diagnose_missing_env():
    engine = RuntimeDiagnosticsEngine()
    diag = engine.classify(missing_env=["POSTGRES_PASSWORD"])
    assert diag.category is DiagnosticCategory.ENVIRONMENT_MISSING


def test_diagnose_command_not_found():
    engine = RuntimeDiagnosticsEngine()
    diag = engine.classify(output="'pnpm' is not recognized as an internal or external command")
    assert diag.category is DiagnosticCategory.COMMAND_NOT_FOUND
    assert diag.recoverable


def test_diagnose_dependency_conflict():
    engine = RuntimeDiagnosticsEngine()
    diag = engine.classify(output="npm ERR! ERESOLVE unable to resolve dependency tree\nconflicting peer dependency")
    assert diag.category in (DiagnosticCategory.DEPENDENCY_CONFLICT, DiagnosticCategory.DEPENDENCY_FAILURE)


def test_diagnose_database_unavailable():
    engine = RuntimeDiagnosticsEngine()
    diag = engine.classify(output="Error: connect ECONNREFUSED 127.0.0.1:5432\nconnection refused")
    assert diag.category is DiagnosticCategory.DATABASE_UNAVAILABLE


def test_diagnose_extracts_code_location():
    engine = RuntimeDiagnosticsEngine()
    diag = engine.classify(
        output="TypeError: boom\n    at handle (src/server/db.ts:42:7)", language="typescript",
    )
    # The location links the runtime error to the code-intelligence layer.
    assert diag.location is not None
    assert diag.location["file"] == "src/server/db.ts"
    assert diag.location["line"] == 42


# ── recovery ────────────────────────────────────────────────────────────────────


def test_recovery_is_bounded_and_stops_on_success():
    engine = RecoveryEngine(max_attempts=3)
    calls = {"n": 0}

    def diagnose(attempt, last):
        return RuntimeDiagnosis(
            category=DiagnosticCategory.PROCESS_CRASH, severity="high", message="crashed",
            suggested_actions=[RecoveryStrategy.RESTART], recoverable=True,
        )

    def act(strategy, diag):
        calls["n"] += 1
        return True

    state = {"ok": False}

    def verify():
        state["ok"] = calls["n"] >= 2
        return state["ok"]

    outcome = engine.run(diagnose=diagnose, act=act, verify=verify)
    assert outcome.recovered is True
    assert outcome.attempts == 2
    assert len(outcome.history) == 2


def test_recovery_never_acts_on_irrecoverable():
    engine = RecoveryEngine(max_attempts=3)
    acted = {"n": 0}

    def diagnose(attempt, last):
        return RuntimeDiagnosis(
            category=DiagnosticCategory.PERMISSION_DENIED, severity="high",
            message="denied", suggested_actions=[], recoverable=False,
        )

    def act(strategy, diag):
        acted["n"] += 1
        return True

    outcome = engine.run(diagnose=diagnose, act=act, verify=lambda: False)
    assert outcome.recovered is False
    assert acted["n"] == 0


def test_recovery_budget_is_bounded():
    import os

    os.environ["HARNESS_APP_RECOVERY_MAX_ATTEMPTS"] = "999"
    try:
        assert recovery_budget() == 10
    finally:
        del os.environ["HARNESS_APP_RECOVERY_MAX_ATTEMPTS"]
    assert recovery_budget() == 3


# ── events ──────────────────────────────────────────────────────────────────────


def test_event_vocabulary_is_closed():
    from harness.execution.application import events

    names = events.EVENT_NAMES
    assert "runtime.started" in names
    assert "container.started" in names
    assert "health_check.passed" in names
    assert "deployment.failed" in names
    # The emitter only ever emits a name from the closed set.
    emitter = events.RuntimeEventEmitter(store=None, bus=None)
    for name in names:
        event = emitter.emit("rt_x", name, {})
        assert event["type"] == name


# ── package managers ──────────────────────────────────────────────────────────────


def test_package_managers_build_argv():
    registry = build_package_manager_registry()
    npm = registry.get("npm")
    assert npm.install_dependencies(Path("."))[1:] == ["install", "--no-audit", "--no-fund"]
    assert npm.install_package(Path("."), ["left-pad"])[1:] == ["install", "--no-save", "--ignore-scripts", "left-pad"]
    cargo = registry.get("cargo")
    assert cargo.build(Path("."))[1:] == ["build"]
    assert cargo.test(Path("."))[1:] == ["test"]
    go = registry.get("go")
    assert go.build(Path("."))[1:] == ["build", "./..."]
    uv = registry.get("uv")
    assert uv.install_dependencies(Path("."))[1:] == ["sync"]


def test_package_manager_capabilities_are_honest():
    registry = build_package_manager_registry()
    # pip cannot "build"; it must not declare it.
    pip = registry.get("pip")
    assert "build" not in pip.capabilities
    assert "install" in pip.capabilities


# ── environment detection ─────────────────────────────────────────────────────────


def test_environment_detector_reports_nonsensitive_metadata():
    from harness.execution.application.environment import EnvironmentDetector

    data = EnvironmentDetector().detect()
    assert data["os"]["name"]
    assert "tools" in data and isinstance(data["tools"], dict)
    # No value here is a secret; only availability + version strings.
    for info in data["tools"].values():
        assert set(info.keys()) == {"available", "version"}


def test_env_manager_compare_never_returns_values(tmp_path):
    (tmp_path / ".env").write_text("A=1\nAPI_KEY=sk-1\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("A=\nAPI_KEY=\nB=\n", encoding="utf-8")
    manager = EnvironmentManager()
    result = manager.compare(tmp_path / ".env", tmp_path / ".env.example")
    serialized = str(result)
    assert "sk-1" not in serialized
    assert set(result["onlyInRight"]) == {"B"}
