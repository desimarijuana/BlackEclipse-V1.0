"""The agent-facing execution tools.

Public surface (registered into the shared `ToolRegistry`):

    execute_python, execute_javascript, execute_typescript, execute_sql,
    execute_shell, execute_code
    build_project, test_project, discover_tests, run_verification
    start_service, stop_service, restart_service, service_status,
    service_logs, list_services
    execution_get, execution_logs, execution_result,
    execution_artifacts, cancel_execution

Every handler is a thin adapter over the process-wide `ExecutionService`. It
resolves the workspace binding + actor from the run, builds a typed
`ExecutionRequest`, runs it, and returns a plain-text summary plus the structured
result. The autonomy profile is enforced twice: structurally (the write tools are
removed at `plan_only` via `code.policy`) and in the handler (the policy engine
refuses a request the profile does not permit).
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..code import policy
from ..tools import ToolContext
from . import runtime as runtime_mod
from .service import build_request, make_actor, workspace_binding

# The write/execute tools the autonomy boundary must know about. `execute_code`
# and the language wrappers RUN code, so they belong in the code-write set.
EXECUTION_WRITE_TOOLS: tuple[str, ...] = (
    "execute_code", "execute_python", "execute_javascript", "execute_typescript",
    "execute_sql", "execute_shell",
    "build_project", "test_project", "run_verification",
    "start_service", "stop_service", "restart_service", "cancel_execution",
)
EXECUTION_READ_TOOLS: tuple[str, ...] = (
    "discover_tests", "execution_get", "execution_logs", "execution_result",
    "execution_artifacts", "service_status", "service_logs", "list_services",
)

ALL_TOOL_NAMES = EXECUTION_WRITE_TOOLS + EXECUTION_READ_TOOLS

_NO_SERVICE = ("RUNTIME_UNAVAILABLE", "the code execution layer isn't available right now")
_PROFILE_DENIED = ("PROFILE_DENIED", "this session isn't set up to run code")
_NO_WORKSPACE = ("WORKSPACE_UNBOUND", "there's no project open to run code in")


def _refusal(code: str, reason: str) -> tuple[str, Any]:
    return (f"REFUSED ({code}): {reason}", {"status": "refused", "code": code, "reason": reason})


def _service() -> Any:
    return runtime_mod.get_execution_service()


def _grants_execute(ctx: ToolContext) -> bool:
    autonomy = getattr(ctx, "autonomy", None)
    return bool(autonomy and "code.execute" in policy.code_grants(str(autonomy)))


def _binding_available(ctx: ToolContext) -> bool:
    return workspace_binding(ctx) is not None


# ── shared input models ───────────────────────────────────────────────────────


class RunCodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Optional[str] = Field(default=None, max_length=200_000)
    entrypoint: Optional[str] = Field(default=None, max_length=1_000)
    args: list[str] = Field(default_factory=list, max_length=64)
    cwd: str = Field(default="", max_length=1_000)
    runtime: str = Field(default="", max_length=64)
    timeoutMs: Optional[int] = Field(default=None, ge=100, le=900_000)  # noqa: N815
    network: str = Field(default="NONE", max_length=16)


class SqlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(..., min_length=1, max_length=200_000)
    database: str = Field(default="", max_length=1_000)
    dialect: str = Field(default="sqlite", max_length=16)
    params: list[Any] = Field(default_factory=list, max_length=256)
    read_only: bool = True
    row_limit: int = Field(default=1000, ge=1, le=100_000)
    timeoutMs: Optional[int] = Field(default=None, ge=100, le=900_000)  # noqa: N815


class ProjectModeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeoutMs: Optional[int] = Field(default=None, ge=100, le=900_000)  # noqa: N815
    test_policy: dict[str, Any] = Field(default_factory=dict)


class ExecutionIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executionId: str = Field(..., min_length=1, max_length=128)  # noqa: N815


class ServiceStartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., min_length=1, max_length=4_000)
    cwd: str = Field(default="", max_length=1_000)
    port: int = Field(default=0, ge=0, le=65535)
    protocol: str = Field(default="http", max_length=16)
    healthUrl: str = Field(default="", max_length=2_000)  # noqa: N815
    waitReady: bool = True  # noqa: N815


class ServiceIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    serviceId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    tail: int = Field(default=200, ge=0, le=10_000)


# ── handlers ──────────────────────────────────────────────────────────────────


async def _run_language(args: dict[str, Any], ctx: ToolContext, language: str) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    if not _binding_available(ctx):
        return _refusal(*_NO_WORKSPACE)
    model = RunCodeInput(**{k: v for k, v in args.items() if v is not None})
    if not model.code and not model.entrypoint:
        return _refusal("INPUT_INVALID", "there's nothing to run — give me code or a file to run")
    request = build_request(
        ctx, language=language, code=model.code or "", entrypoint=model.entrypoint or "",
        args=model.args, cwd=model.cwd, runtime=model.runtime, mode="RUN",
        timeout_ms=model.timeoutMs, network_policy=model.network,
    )
    await _emit(ctx, "execution.tool.requested", {"tool": f"execute_{language}", "language": language})
    result = await asyncio.to_thread(service.run, request, actor=make_actor(ctx), emit=_emitter(ctx))
    return _render_run(result, language)


async def execute_python(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run_language(args, ctx, "python")


async def execute_javascript(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run_language(args, ctx, "javascript")


async def execute_typescript(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run_language(args, ctx, "typescript")


async def execute_shell(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    if not _binding_available(ctx):
        return _refusal(*_NO_WORKSPACE)
    model = RunCodeInput(**{k: v for k, v in args.items() if v is not None})
    command = (model.code or "").strip()
    if not command:
        return _refusal("INPUT_INVALID", "there's no command to run")
    # Defense in depth: reuse the terminal subsystem's classifier. A destructive
    # shape never runs, even if the authorizer were bypassed.
    from ..code.shell_tools import _verdict  # noqa: PLC0415

    verdict = _verdict(command)
    if verdict.kind == "deny":
        return _refusal("COMMAND_NOT_ALLOWLISTED", verdict.reason)
    request = build_request(
        ctx, language="shell", code=command, cwd=model.cwd, runtime="local",
        mode="RUN", timeout_ms=model.timeoutMs, network_policy=model.network,
        metadata={"shell": model.runtime or ""},
    )
    result = await asyncio.to_thread(service.run, request, actor=make_actor(ctx), emit=_emitter(ctx))
    return _render_run(result, "shell")


async def execute_sql(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    if not _binding_available(ctx):
        return _refusal(*_NO_WORKSPACE)
    model = SqlInput(**{k: v for k, v in args.items() if v is not None})
    request = build_request(
        ctx, language="sql", code=model.sql, mode="RUN",
        timeout_ms=model.timeoutMs, network_policy="NONE",
        metadata={
            "database": model.database, "dialect": model.dialect, "params": model.params,
            "read_only": model.read_only, "row_limit": model.row_limit,
        },
    )
    result = await asyncio.to_thread(service.run, request, actor=make_actor(ctx), emit=_emitter(ctx))
    if result.status == "SECURITY_BLOCKED":
        return _refusal((result.error or {}).get("code", "SECURITY_BLOCKED"),
                        (result.error or {}).get("message", "that query isn't allowed"))
    return _render_run(result, "sql")


async def execute_code(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """The universal interface: dispatch to the language wrapper by `language`."""
    raw = dict(args or {})
    language = str(raw.pop("language", "") or "").strip().casefold()
    if language in ("python", "py"):
        return await execute_python(raw, ctx)
    if language in ("javascript", "js", "node"):
        return await execute_javascript(raw, ctx)
    if language in ("typescript", "ts", "tsx"):
        return await execute_typescript(raw, ctx)
    if language in ("sql", "sqlite", "postgres"):
        sql_args = {"sql": raw.get("code") or raw.get("sql") or "", **{k: v for k, v in raw.items() if k in ("database", "dialect", "params", "read_only", "row_limit", "timeoutMs")}}
        return await execute_sql(sql_args, ctx)
    if language in ("shell", "sh", "bash", "powershell", "pwsh", "cmd"):
        return await execute_shell(raw, ctx)
    return _refusal("UNKNOWN_LANGUAGE", f"I don't know how to run {language or 'that'} code yet")


async def build_project(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _project_mode(args, ctx, "BUILD")


async def test_project(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _project_mode(args, ctx, "TEST")


async def _project_mode(args: dict[str, Any], ctx: ToolContext, mode: str) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    if not _binding_available(ctx):
        return _refusal(*_NO_WORKSPACE)
    cleaned = {k: v for k, v in (args or {}).items() if v is not None and k in ("timeoutMs", "test_policy")}
    model = ProjectModeInput(**cleaned)
    request = build_request(
        ctx, language="", mode=mode, timeout_ms=model.timeoutMs,
        test_policy=(model.test_policy or None),
    )
    result = await asyncio.to_thread(service.run, request, actor=make_actor(ctx), emit=_emitter(ctx))
    return _render_project(result, mode)


async def discover_tests(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    binding = workspace_binding(ctx)
    if binding is None:
        return _refusal(*_NO_WORKSPACE)
    from ..code.workspace import default_root  # noqa: PLC0415
    from .projects import ProjectDetector  # noqa: PLC0415

    root = default_root()
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    project = ProjectDetector().detect(root)
    language = service.registry.resolve_language(project=project)
    adapter = service.registry.get(language)
    discovery = service.orchestrator.test_engine.discover(adapter, root, project) if adapter else None
    data = discovery.to_dict() if discovery else {"framework": "", "tests": 0, "files": []}
    text = (
        f"Found {data['tests']} test file(s) using {data['framework'] or 'an unknown framework'}."
        if data["tests"] else "I couldn't find a test setup for this project."
    )
    return text, {"status": "ok", **data}


async def run_verification(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """The bounded build→test→fix→rebuild→retest loop (no model fix in-process)."""
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    if not _binding_available(ctx):
        return _refusal(*_NO_WORKSPACE)
    model = ProjectModeInput(**{k: v for k, v in (args or {}).items() if k in ("timeoutMs", "test_policy") and v is not None})
    request = build_request(ctx, language="", mode="BUILD_AND_TEST", timeout_ms=model.timeoutMs, test_policy=(model.test_policy or None))
    outcome = await asyncio.to_thread(
        service.verifier.run, request, actor=make_actor(ctx), emit=_emitter(ctx),
    )
    data = outcome.to_dict()
    text = (
        f"Verification {outcome.status} after {outcome.iterations} attempt(s)."
        + (f" {outcome.stopped_reason}." if outcome.stopped_reason else "")
    )
    return text, {"status": outcome.status, **data}


# ── execution retrieval ──────────────────────────────────────────────────────


async def get_execution(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    model = ExecutionIdInput(**{k: v for k, v in args.items() if v is not None})
    record = service.get_execution(model.executionId)
    if record is None:
        return _refusal("NOT_FOUND", "there's no execution with that id")
    return _render_execution_record(record), {"status": "ok", "execution": record}


async def get_execution_logs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    model = ExecutionIdInput(**{k: v for k, v in args.items() if v is not None})
    data = service.get_execution_logs(model.executionId)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no execution with that id")
    return f"Logs for {model.executionId}:\n{data.get('stdout', '')}", data


async def get_execution_result(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await get_execution(args, ctx)


async def get_execution_artifacts(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    model = ExecutionIdInput(**{k: v for k, v in args.items() if v is not None})
    data = service.get_execution_artifacts(model.executionId)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no execution with that id")
    names = ", ".join(a.get("path", "") for a in data.get("artifacts", [])) or "none"
    return f"Artifacts for {model.executionId}: {names}", data


async def cancel_execution(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    model = ExecutionIdInput(**{k: v for k, v in args.items() if v is not None})
    ok = service.cancel_execution(model.executionId)
    if not ok:
        return _refusal("NOT_FOUND", "there's no running execution with that id")
    return f"Cancelling {model.executionId}.", {"status": "ok", "executionId": model.executionId}


# ── services ───────────────────────────────────────────────────────────────────


async def start_service(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    binding = workspace_binding(ctx)
    if binding is None:
        return _refusal(*_NO_WORKSPACE)
    model = ServiceStartInput(**{k: v for k, v in args.items() if v is not None})
    from ..code.shell_tools import _verdict  # noqa: PLC0415

    verdict = _verdict(model.command)
    if verdict.kind == "deny":
        return _refusal("COMMAND_NOT_ALLOWLISTED", verdict.reason)
    cwd = model.cwd or str(binding.root)
    data = await asyncio.to_thread(
        service.start_service,
        command=model.command, cwd=cwd, port=model.port, protocol=model.protocol,
        health_url=model.healthUrl, workspace_id=getattr(binding, "id", None),
        agent_id=getattr(ctx, "agent_id", None), run_id=getattr(ctx, "run_id", None),
        wait_ready=model.waitReady,
    )
    if data.get("status") != "ok":
        return _refusal(data.get("code", "SERVICE_FAILED"), data.get("reason", "the service could not start"))
    info = data["service"]
    health = data.get("health") or {}
    text = f"Started service {info['serviceId']} on port {info['port']} (ready={bool(health.get('ready'))})."
    return text, {"status": "ok", **data}


async def stop_service(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    model = ServiceIdInput(**{k: v for k, v in args.items() if v is not None})
    data = service.stop_service(model.serviceId)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no service with that id")
    return f"Stopped service {model.serviceId}.", data


async def restart_service(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    model = ServiceIdInput(**{k: v for k, v in args.items() if v is not None})
    data = service.restart_service(model.serviceId)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no service with that id")
    return f"Restarted service {model.serviceId}.", data


async def get_service_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    model = ServiceIdInput(**{k: v for k, v in args.items() if v is not None})
    data = service.get_service_status(model.serviceId)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no service with that id")
    return f"Service {model.serviceId}: running={data.get('running')} process={data.get('processState')}", data


async def get_service_logs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    model = ServiceIdInput(**{k: v for k, v in args.items() if v is not None})
    data = service.get_service_logs(model.serviceId, tail=model.tail)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no service with that id")
    return f"Logs for service {model.serviceId}:\n{data.get('logs', '')}", data


async def list_services(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = _service()
    if service is None:
        return _refusal(*_NO_SERVICE)
    services = service.list_services()
    text = "\n".join(f"{s['serviceId']} port={s['port']} ready={s['ready']} {s['command']}" for s in services) or "No services."
    return text, {"status": "ok", "services": services}


# ── rendering helpers ─────────────────────────────────────────────────────────


def _render_run(result: Any, language: str) -> tuple[str, Any]:
    data = result.to_dict()
    if result.status == "COMPLETED":
        text = f"Ran {language}: exit {result.exit_code} in {result.duration_ms}ms."
    elif result.status == "SECURITY_BLOCKED":
        err = result.error or {}
        return _refusal(err.get("code", "SECURITY_BLOCKED"), err.get("message", "that isn't allowed"))
    else:
        text = f"{language} run {result.status}: exit {result.exit_code}."
        if result.diagnostics:
            first = result.diagnostics[0]
            location = f"{first.file}:{first.line}" if first.file else ""
            text += f" {location} {first.message}".rstrip()
    if result.stdout:
        text += f"\n{result.stdout[:4000]}"
    if result.truncated:
        text += "\n[output was truncated]"
    return text, data


def _render_project(result: Any, mode: str) -> tuple[str, Any]:
    data = result.to_dict()
    if result.status == "COMPLETED":
        return f"{mode} passed in {result.duration_ms}ms.", data
    errors = result.diagnostics
    text = f"{mode} failed ({result.status})."
    if errors:
        first = errors[0]
        location = f"{first.file}:{first.line}:{first.column} " if first.file else ""
        text += f" {location}{first.message}"
    return text, data


def _render_execution_record(record: Any) -> str:
    if isinstance(record, dict) and "executionId" in record:
        return (
            f"Execution {record.get('executionId')}: {record.get('status')} "
            f"exit={record.get('exitCode')} language={record.get('language')}"
        )
    return "Execution record."


def _emitter(ctx: ToolContext):
    emitter = getattr(ctx, "emitter", None)
    if emitter is None:
        return None

    def _emit(event_type: str, data: dict[str, Any]) -> None:
        try:
            emitter.emit_sync(event_type, data)
        except Exception:  # noqa: BLE001 - observability must not break a call
            pass

    return _emit


async def _emit(ctx: ToolContext, event_type: str, data: dict[str, Any]) -> None:
    try:
        from ..code.tools import emit_code_event  # noqa: PLC0415

        await emit_code_event(ctx, event_type, data)
    except Exception:  # noqa: BLE001
        pass


# ── schemas + registration ─────────────────────────────────────────────────────


def _obj(properties: dict[str, Any], required: Optional[list[str]] = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def execution_schemas() -> dict[str, dict[str, Any]]:
    code_props = {
        "code": {"type": "string", "description": "The program to run, as text."},
        "entrypoint": {"type": "string", "description": "A file in the project to run instead of inline code."},
        "args": {"type": "array", "items": {"type": "string"}, "description": "Command-line arguments passed to the program."},
        "cwd": {"type": "string", "description": "Working directory, relative to the project root."},
        "runtime": {"type": "string", "description": "An explicit runtime (e.g. python, node). Usually omitted."},
        "timeoutMs": {"type": "integer", "description": "Wall-clock limit in milliseconds."},
        "network": {"type": "string", "enum": ["NONE", "LOCAL_ONLY", "ALLOWLIST", "FULL"], "description": "Network reach (default NONE)."},
    }
    return {
        "execute_python": _obj(code_props),
        "execute_javascript": _obj(code_props),
        "execute_typescript": _obj(code_props),
        "execute_shell": _obj({
            "code": {"type": "string", "description": "The shell command line to run."},
            "cwd": {"type": "string", "description": "Working directory, relative to the project root."},
            "timeoutMs": {"type": "integer"},
            "runtime": {"type": "string", "description": "Shell name (powershell, bash, cmd)."},
        }, ["code"]),
        "execute_sql": _obj({
            "sql": {"type": "string", "description": "The SQL statement to run."},
            "database": {"type": "string", "description": "A SQLite file (relative to the project) or a connection string."},
            "dialect": {"type": "string", "enum": ["sqlite", "postgres"]},
            "params": {"type": "array", "items": {}, "description": "Bound parameters."},
            "read_only": {"type": "boolean", "description": "Refuse statements that change data (the default is true)."},
            "row_limit": {"type": "integer"},
            "timeoutMs": {"type": "integer"},
        }, ["sql"]),
        "execute_code": _obj({
            "language": {"type": "string", "description": "python, javascript, typescript, sql or shell."},
            "code": {"type": "string"},
            "entrypoint": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
            "cwd": {"type": "string"},
            "timeoutMs": {"type": "integer"},
            "network": {"type": "string"},
        }, ["language"]),
        "build_project": _obj({"timeoutMs": {"type": "integer"}, "test_policy": {"type": "object"}}),
        "test_project": _obj({"timeoutMs": {"type": "integer"}, "test_policy": {"type": "object"}}),
        "run_verification": _obj({"timeoutMs": {"type": "integer"}, "test_policy": {"type": "object"}}),
        "discover_tests": _obj({}),
        "execution_get": _obj({"executionId": {"type": "string"}}, ["executionId"]),
        "execution_logs": _obj({"executionId": {"type": "string"}}, ["executionId"]),
        "execution_result": _obj({"executionId": {"type": "string"}}, ["executionId"]),
        "execution_artifacts": _obj({"executionId": {"type": "string"}}, ["executionId"]),
        "cancel_execution": _obj({"executionId": {"type": "string"}}, ["executionId"]),
        "start_service": _obj({
            "command": {"type": "string"},
            "cwd": {"type": "string"},
            "port": {"type": "integer"},
            "protocol": {"type": "string", "enum": ["http", "tcp", "process"]},
            "healthUrl": {"type": "string"},
            "waitReady": {"type": "boolean"},
        }, ["command"]),
        "stop_service": _obj({"serviceId": {"type": "string"}}, ["serviceId"]),
        "restart_service": _obj({"serviceId": {"type": "string"}}, ["serviceId"]),
        "service_status": _obj({"serviceId": {"type": "string"}}, ["serviceId"]),
        "service_logs": _obj({"serviceId": {"type": "string"}, "tail": {"type": "integer"}}, ["serviceId"]),
        "list_services": _obj({}),
    }


_DESCRIPTIONS = {
    "execute_python": "Run a Python program and return its output, exit code and any errors.",
    "execute_javascript": "Run a JavaScript program with Node.js and return its output and errors.",
    "execute_typescript": "Run a TypeScript program using the project's own toolchain.",
    "execute_shell": "Run a shell command in the project folder and return its output.",
    "execute_sql": "Run a SQL statement read-only by default and return the rows.",
    "execute_code": "Run code in a supported language. The universal entry point — prefer the language-specific tools.",
    "build_project": "Build the project and return normalized errors.",
    "test_project": "Run the project's tests and return a normalized pass/fail summary.",
    "run_verification": "Build and test the project until it passes, within a bounded number of attempts.",
    "discover_tests": "Report the project's test framework and test files. Read-only.",
    "execution_get": "Show one past execution and its evidence. Read-only.",
    "execution_logs": "Read a past execution's output. Read-only.",
    "execution_result": "Show a past execution's structured result. Read-only.",
    "execution_artifacts": "List the files a past execution produced. Read-only.",
    "cancel_execution": "Cancel a running execution and stop its process tree.",
    "start_service": "Start a long-running service (e.g. a dev server) on a free port and wait until it answers.",
    "stop_service": "Stop a service started by Eclipse.",
    "restart_service": "Restart a service.",
    "service_status": "Report whether a service is running. Read-only.",
    "service_logs": "Read a service's output. Read-only.",
    "list_services": "List the services Eclipse is running. Read-only.",
}

_HANDLERS = {
    "execute_python": execute_python, "execute_javascript": execute_javascript,
    "execute_typescript": execute_typescript, "execute_shell": execute_shell,
    "execute_sql": execute_sql, "execute_code": execute_code,
    "build_project": build_project, "test_project": test_project,
    "run_verification": run_verification, "discover_tests": discover_tests,
    "execution_get": get_execution, "execution_logs": get_execution_logs,
    "execution_result": get_execution_result, "execution_artifacts": get_execution_artifacts,
    "cancel_execution": cancel_execution,
    "start_service": start_service, "stop_service": stop_service, "restart_service": restart_service,
    "service_status": get_service_status, "service_logs": get_service_logs,
    "list_services": list_services,
}


def register_execution_tools(registry: Any) -> list[str]:
    """Register the execution tools on the shared registry. Returns the names."""
    from ..tools import ToolDefinition  # noqa: PLC0415

    schemas = execution_schemas()
    added: list[str] = []
    for name in ALL_TOOL_NAMES:
        is_read = name in EXECUTION_READ_TOOLS
        registry.register(ToolDefinition(
            name=name,
            description=_DESCRIPTIONS[name],
            input_schema=schemas[name],
            handler=_HANDLERS[name],
            permission=("read" if is_read else "write"),
            risk=("low" if is_read else "high"),
            timeout_ms=(30_000 if is_read else 600_000),
            effect=(None if is_read else "external_action"),
        ))
        added.append(name)
    return added


__all__ = [
    "ALL_TOOL_NAMES",
    "EXECUTION_READ_TOOLS",
    "EXECUTION_WRITE_TOOLS",
    "execution_schemas",
    "register_execution_tools",
]
