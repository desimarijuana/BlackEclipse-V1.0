"""Tool behaviour fixtures (round 4, W13, ADR-H214).

The metadata audit (`tool_contracts.py`) proves a tool DECLARES a contract; these
fixtures prove a representative tool per audited family actually RUNS through the
ONE `ToolRegistry` and answers in the shape it advertises. A family whose
fixture fails is a family whose tools are not honestly available — the release
test asserts every audited family has a passing fixture, and every fixture's
representative tool is present on the production registry.

Rules:

* every fixture is OFFLINE and deterministic — a private temp dir/store/repo, a
  stub bridge, no network, no browser launch, no real user state;
* the tool is exercised through `ToolRegistry.execute` (the real validation,
  timeout, event and handler path), never by calling a handler directly;
* a degraded environment is still a real result: the browser fixture accepts a
  structured `unavailable`/refusal, but never a fabricated page, and the finance
  fixture asserts the honest `no_data` path — a fixture that can only pass on a
  machine with a live dependency would be a fake.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

#: The families the round-4 audit covers. A family without a fixture is a gap,
#: not a silent omission — `fixture_report()["complete"]` is False.
AUDITED_FAMILIES: tuple[str, ...] = (
    "filesystem", "terminal", "git", "browser", "api", "artifacts", "finance",
)


@dataclass(frozen=True)
class FamilyFixture:
    family: str
    tool: str
    description: str
    check: Callable[[], Awaitable[dict[str, Any]]]


# ── shared helpers ──────────────────────────────────────────────────────────


def _ctx(**fields: Any) -> Any:
    from .tools import ToolContext

    base: dict[str, Any] = {"run_id": "w13-fixture", "log": lambda *_: None}
    base.update(fields)
    return ToolContext(**base)


def _registry_with(register: Callable[[Any], Any]) -> Any:
    from .tools import ToolRegistry

    registry = ToolRegistry()
    register(registry)
    return registry


def _workspace(root: Path, ws_id: str = "ws_w13") -> Any:
    from .code.policy import WorkspaceBinding
    from .code.workspace import ResolvedWorkspace

    real = Path(os.path.realpath(root))
    binding = WorkspaceBinding(id=ws_id, root=real, base_revision="w13", strategy="checkout")
    return ResolvedWorkspace(
        id=ws_id, root=real, base_revision="w13", strategy="checkout", binding=binding,
    )


def _failed(result: Any) -> str:
    error = getattr(result, "error", None)
    message = getattr(error, "message", None) if error is not None else None
    return str(message or getattr(result, "text", "") or "no result")


def _require_ok(result: Any, tool: str) -> Any:
    if not getattr(result, "ok", False):
        raise AssertionError(f"{tool} failed: {_failed(result)}")
    return result


def _git_env() -> dict[str, str]:
    keep = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "PATHEXT")
    return {
        **{key: os.environ[key] for key in keep if key in os.environ},
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "W13",
        "GIT_AUTHOR_EMAIL": "w13@example.com",
        "GIT_COMMITTER_NAME": "W13",
        "GIT_COMMITTER_EMAIL": "w13@example.com",
    }


# ── filesystem ──────────────────────────────────────────────────────────────


async def _check_filesystem() -> dict[str, Any]:
    from .code.fs_tools import register_fs_tools

    registry = _registry_with(register_fs_tools)
    with tempfile.TemporaryDirectory(prefix="be-w13-fs-") as tmp:
        root = Path(tmp)
        (root / "note.txt").write_text("W13 fixture\n", encoding="utf-8")
        result = await registry.execute(
            "read_file", "w13-fs", {"path": "note.txt"},
            _ctx(workspace=_workspace(root), autonomy="edit_verify"),
        )
    _require_ok(result, "read_file")
    blob = f"{result.text}\n{result.data}"
    if "W13 fixture" not in blob:
        raise AssertionError(f"read_file did not return the file's real content: {result.text!r}")
    return {"read": "note.txt", "contentReturned": True}


# ── terminal ────────────────────────────────────────────────────────────────


async def _check_terminal() -> dict[str, Any]:
    from .events import EventBus
    from .persistence import AgentMemoryStore
    from .terminal import runtime as terminal_runtime
    from .terminal.store import TerminalStore
    from .terminal.tools import register_terminal_tools

    with tempfile.TemporaryDirectory(prefix="be-w13-term-") as tmp:
        store = AgentMemoryStore(str(Path(tmp) / "agent-memory.db"))
        previous = terminal_runtime.get_terminal_manager()
        manager = terminal_runtime.build_terminal_manager(
            store=TerminalStore(store), bus=EventBus(),
        )
        terminal_runtime.set_terminal_manager(manager)
        try:
            registry = _registry_with(register_terminal_tools)
            result = await registry.execute("terminal_capabilities", "w13-term", {}, _ctx())
        finally:
            terminal_runtime.set_terminal_manager(previous)
            store.close()
    _require_ok(result, "terminal_capabilities")
    data = result.data if isinstance(result.data, dict) else {}
    if not data.get("platform"):
        raise AssertionError(f"terminal_capabilities returned no platform: {result.data!r}")
    return {"platform": data.get("platform"), "shells": data.get("availableShells")}


# ── git ─────────────────────────────────────────────────────────────────────


async def _check_git() -> dict[str, Any]:
    from .git import repository as repo_module
    from .git.service import GitService, get_git_service, set_git_service
    from .git.tools import register_git_tools
    from .persistence import AgentMemoryStore

    with tempfile.TemporaryDirectory(prefix="be-w13-git-") as tmp:
        base = Path(tmp)
        root = base / "repo"  # the store stays OUTSIDE the tree under test
        root.mkdir()
        env = _git_env()

        def run(*args: str) -> None:
            outcome = subprocess.run(
                ["git", *args], cwd=str(root), capture_output=True, text=True,
                shell=False, env=env, timeout=60,
            )
            if outcome.returncode != 0:
                raise AssertionError(f"git {' '.join(args)} failed: {outcome.stderr.strip()}")

        run("init", "-q", "-b", "main")
        run("config", "user.email", "w13@example.com")
        run("config", "user.name", "W13")
        run("config", "core.autocrlf", "false")
        (root / "README.md").write_text("# W13\n", encoding="utf-8")
        run("add", "-A")
        run("commit", "-qm", "initial")
        if repo_module.discover(root) is None:
            raise AssertionError("the fixture repo did not discover as a repository")

        store = AgentMemoryStore(str(base / "agent-memory.db"))
        previous = get_git_service()
        set_git_service(GitService(store))
        try:
            registry = _registry_with(register_git_tools)
            result = await registry.execute(
                "git_status", "w13-git", {}, _ctx(workspace=_workspace(root)),
            )
        finally:
            set_git_service(previous)
            store.close()
    _require_ok(result, "git_status")
    # A clean fixture repo must report its ACTUAL branch and a clean tree.
    if "main" not in result.text and "main" not in str(result.data):
        raise AssertionError(f"git_status did not report the real branch: {result.text!r}")
    data = result.data if isinstance(result.data, dict) else {}
    if data and data.get("clean") is not True:
        raise AssertionError(f"git_status reported a dirty tree for a clean repo: {result.data!r}")
    return {"branch": "main", "clean": True}


# ── browser ─────────────────────────────────────────────────────────────────


async def _check_browser() -> dict[str, Any]:
    from .browser import config as browser_config
    from .browser.tools import register_browser_tools

    registry = _registry_with(register_browser_tools)
    registered = sorted(registry.names())
    enabled = bool(browser_config.browser_enabled())
    if not enabled:
        # The gate's promise: a disabled browser is never advertised.
        if registered:
            raise AssertionError(
                f"browser disabled but tools were advertised: {registered[:5]}"
            )
        return {"registered": [], "enabled": False, "advertisedOnlyWhenEnabled": True}
    if "browser_status" not in registered:
        raise AssertionError(f"browser enabled but browser_status is missing: {registered[:5]}")
    # A sessionless status call must degrade structurally (manager absent or no
    # session) — never invent a page and never raise out of the registry.
    result = await registry.execute("browser_status", "w13-browser", {}, _ctx())
    blob = f"{result.text}\n{result.data}".lower()
    if "session" not in blob and "available" not in blob:
        raise AssertionError(
            f"browser_status gave no structured session/availability answer: {result.text!r}"
        )
    return {"registered": len(registered), "enabled": True, "sessionlessCallStructured": True}


# ── api / web ───────────────────────────────────────────────────────────────


async def _check_api() -> dict[str, Any]:
    from .research.web_tools import register_research_engine_tools

    registry = _registry_with(register_research_engine_tools)
    result = await registry.execute(
        "source_rank", "w13-api",
        {"url": "https://www.sec.gov/edgar/filing", "research_type": "financial_statements",
         "relevance": 0.9},
        _ctx(),
    )
    _require_ok(result, "source_rank")
    data = result.data if isinstance(result.data, dict) else {}
    ranking = data.get("ranking") if isinstance(data.get("ranking"), dict) else {}
    score = ranking.get("score")
    if not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 1.0:
        raise AssertionError(f"source_rank returned no bounded score: {result.data!r}")
    return {"score": score, "sourceType": (data.get("source") or {}).get("sourceType")}


# ── artifacts ───────────────────────────────────────────────────────────────


async def _check_artifacts() -> dict[str, Any]:
    from .artifacts.service import ArtifactService
    from .artifacts.storage import LocalArtifactStorage
    from .artifacts.store import ArtifactStore
    from .artifacts.tools import register_artifact_tools
    from .persistence import AgentMemoryStore

    registry = _registry_with(register_artifact_tools)
    with tempfile.TemporaryDirectory(prefix="be-w13-art-") as tmp:
        store = AgentMemoryStore(str(Path(tmp) / "agent-memory.db"))
        service = ArtifactService(
            ArtifactStore(store), LocalArtifactStorage(Path(tmp) / "artifacts"),
        )
        try:
            result = await registry.execute(
                "artifact_list", "w13-art", {}, _ctx(artifact_service=service),
            )
        finally:
            store.close()
    _require_ok(result, "artifact_list")
    data = result.data if isinstance(result.data, dict) else {}
    if "artifacts" not in data:
        raise AssertionError(f"artifact_list returned no artifacts list: {result.data!r}")
    return {"artifacts": len(data.get("artifacts") or [])}


# ── finance ─────────────────────────────────────────────────────────────────


class _StubBridge:
    """A deterministic DataBridge stand-in: records calls, returns canned data."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, dict(params or {})))
        if capability == "source_health":
            return {"status": "OK", "rows": [], "summary": {"recordedRoutes": 0}, "withheld": 0}
        return {"status": "UNAVAILABLE", "capability": capability}


async def _check_finance() -> dict[str, Any]:
    from .finance_tools import register_finance_tools

    registry = _registry_with(register_finance_tools)
    bridge = _StubBridge()
    result = await registry.execute(
        "get_source_health", "w13-fin", {}, _ctx(data_bridge=bridge),
    )
    _require_ok(result, "get_source_health")
    data = result.data if isinstance(result.data, dict) else {}
    if not bridge.calls or bridge.calls[0][0] != "source_health":
        raise AssertionError(f"get_source_health did not request source_health: {bridge.calls!r}")
    if data.get("failureClass") != "no_data":
        raise AssertionError(
            f"an empty ledger must report no_data, not health: {result.data!r}"
        )
    return {"capability": "source_health", "failureClass": "no_data"}


# ── the registry ────────────────────────────────────────────────────────────

FAMILY_FIXTURES: tuple[FamilyFixture, ...] = (
    FamilyFixture(
        "filesystem", "read_file",
        "reads a real temp file through the registry and returns its content",
        _check_filesystem,
    ),
    FamilyFixture(
        "terminal", "terminal_capabilities",
        "reports the real platform/shell capabilities through a live manager",
        _check_terminal,
    ),
    FamilyFixture(
        "git", "git_status",
        "reports the real branch and clean state of a temp repository",
        _check_git,
    ),
    FamilyFixture(
        "browser", "browser_status",
        "advertises browser tools only when enabled and degrades structurally without a session",
        _check_browser,
    ),
    FamilyFixture(
        "api", "source_rank",
        "scores a real source URL with a bounded, explainable ranking",
        _check_api,
    ),
    FamilyFixture(
        "artifacts", "artifact_list",
        "lists from a real (empty) artifact store and returns the catalog shape",
        _check_artifacts,
    ),
    FamilyFixture(
        "finance", "get_source_health",
        "requests the source_health capability through the bridge and reports no_data honestly",
        _check_finance,
    ),
)


async def run_family_fixture(fixture: FamilyFixture) -> dict[str, Any]:
    """Run one fixture; raises on failure so the caller names the family."""
    detail = await fixture.check()
    return {"family": fixture.family, "tool": fixture.tool, "ok": True, "detail": detail}


async def run_all_fixtures() -> list[dict[str, Any]]:
    """Run every fixture; a failure is recorded (never raised) so all run."""
    results: list[dict[str, Any]] = []
    for fixture in FAMILY_FIXTURES:
        try:
            results.append(await run_family_fixture(fixture))
        except Exception as exc:  # noqa: BLE001 - a fixture failure is the measurement
            results.append({
                "family": fixture.family, "tool": fixture.tool, "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return results


def fixture_report() -> dict[str, Any]:
    """The declared fixture set (no execution) — the release-gate shape."""
    families = [fixture.family for fixture in FAMILY_FIXTURES]
    return {
        "auditedFamilies": list(AUDITED_FAMILIES),
        "families": families,
        "complete": families == list(AUDITED_FAMILIES),
        "tools": {fixture.family: fixture.tool for fixture in FAMILY_FIXTURES},
    }


__all__ = [
    "AUDITED_FAMILIES",
    "FAMILY_FIXTURES",
    "FamilyFixture",
    "fixture_report",
    "run_all_fixtures",
    "run_family_fixture",
]
