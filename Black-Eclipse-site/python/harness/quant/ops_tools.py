"""Strategy ops tools: source inspection, governance (approvals/deployments) and
multi-file Python projects — all driven from the chatbot.

These close the remaining lifecycle gaps WITHOUT any live-trading capability:
  * `inspect_python_strategy` statically reports imports / third-party deps /
    dangerous calls (advisory — process isolation is the real boundary);
  * approval + deployment records implement a governed paper path; `live` is
    refused outright (`LIVE_TRADING_DISABLED`) and a deployment never routes orders;
  * `run_python_project` runs a multi-file strategy project in the same isolated,
    env-scrubbed, time-limited worker.
"""

from __future__ import annotations

import ast
import asyncio
import sys
from typing import Any

from .datasets import resolve_dataset
from .errors import QuantError, StoreUnavailable

_STDLIB = getattr(sys, "stdlib_module_names", set())
_DANGEROUS_NAMES = {"eval", "exec", "compile", "__import__", "open"}
_DANGEROUS_MODULES = {"os", "subprocess", "socket", "shutil", "ctypes", "pathlib",
                      "importlib", "sys", "pickle", "marshal"}


def inspect_source(source: str) -> dict[str, Any]:
    """Static, advisory inspection of strategy source (not a security boundary)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"ok": False, "error": f"syntax error: {exc}", "imports": [],
                "thirdPartyImports": [], "findings": [
                    {"code": "SYNTAX_ERROR", "message": str(exc)}]}
    imports: set[str] = set()
    dangerous: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None)
            if name in _DANGEROUS_NAMES:
                dangerous.add(name)
    third_party = sorted(m for m in imports
                         if m not in _STDLIB and m != "harness" and not m.startswith("harness"))
    findings: list[dict[str, Any]] = []
    for module in third_party:
        findings.append({"code": "THIRD_PARTY_IMPORT", "severity": "warning",
                         "message": f"imports third-party module {module!r}"})
    for module in sorted(imports & _DANGEROUS_MODULES):
        findings.append({"code": "RESTRICTED_IMPORT", "severity": "warning",
                         "message": f"imports restricted module {module!r}"})
    for name in sorted(dangerous):
        findings.append({"code": "DANGEROUS_CALL", "severity": "warning",
                         "message": f"calls {name!r}"})
    return {
        "ok": True, "imports": sorted(imports), "thirdPartyImports": third_party,
        "dangerousCalls": sorted(dangerous), "findings": findings,
        "note": "advisory only — the isolated worker process is the security boundary",
    }


def _store(ctx: Any):
    store = getattr(ctx, "quant_store", None)
    if store is None:
        raise StoreUnavailable("the quant store is not configured")
    return store


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, QuantError):
        return (f"ERROR — {exc.code}: {exc.message}", {"status": "ERROR", "error": exc.to_dict()})
    return (f"ERROR — {type(exc).__name__}: {exc}",
            {"status": "ERROR", "error": {"message": str(exc)}})


# ── Handlers ─────────────────────────────────────────────────────────────────

async def inspect_python_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        code = str(args.get("strategyCode") or "")
        if not code.strip():
            return ("ERROR — `strategyCode` is required.",
                    {"status": "ERROR", "error": {"code": "SDK_EMPTY_SOURCE"}})
        result = inspect_source(code)
        if not result["ok"]:
            return (result["error"], {"status": "INVALID", **result})
        note = (f"{len(result['findings'])} finding(s); imports: "
                f"{', '.join(result['imports']) or 'none'}")
        return (f"Source inspection: {note}", {"status": "OK", **result})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def request_strategy_approval(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        record = store.request_approval(
            str(args.get("strategyId")), str(args.get("version") or "1.0.0"),
            actor=args.get("actor"), note=args.get("note"))
        return (f"Approval {record['id']} requested for {record['strategyId']} "
                f"v{record['version']}.", {"status": "OK", "approval": record})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def decide_strategy_approval(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        record = store.decide_approval(
            str(args.get("approvalId")), approve=bool(args.get("approve")),
            actor=args.get("actor"), note=args.get("note"))
        return (f"Approval {record['id']} → {record['status']}.",
                {"status": "OK", "approval": record})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def list_strategy_approvals(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        items = store.list_approvals(args.get("strategyId"))
        text = "\n".join(f"  {a['id']} {a['strategyId']} v{a['version']} → {a['status']}"
                         for a in items) or "  (none)"
        return (f"{len(items)} approval(s):\n{text}", {"status": "OK", "approvals": items})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def create_strategy_deployment(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        record = store.create_deployment(
            str(args.get("strategyId")), str(args.get("version") or "1.0.0"),
            mode=str(args.get("mode") or "paper"), note=args.get("note"),
            require_approval=bool(args.get("requireApproval", True)))
        return (f"Deployment {record['id']} created ({record['mode']}, record-only — "
                f"no live routing).", {"status": "OK", "deployment": record})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def list_strategy_deployments(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        items = store.list_deployments(args.get("strategyId"))
        text = "\n".join(f"  {d['id']} {d['strategyId']} v{d['version']} {d['mode']} {d['status']}"
                         for d in items) or "  (none)"
        return (f"{len(items)} deployment(s):\n{text}", {"status": "OK", "deployments": items})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def stop_strategy_deployment(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        record = store.stop_deployment(str(args.get("deploymentId")))
        return (f"Deployment {record['id']} stopped.", {"status": "OK", "deployment": record})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def run_python_project(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .sdk_runtime import run_strategy_source
        from .tools import _flag, _gateway, _render_result, _result_data, _series_rows

        store = _store(ctx)  # noqa: F841 - _store validates availability
        files = args.get("files") or {}
        entry = str(args.get("entry") or "main.py")
        if not isinstance(files, dict) or entry not in files:
            return ("ERROR — `files` must include the `entry` module.",
                    {"status": "ERROR", "error": {"code": "SDK_NO_ENTRY"}})
        symbols = [str(s).upper() for s in (args.get("symbols") or [])]
        if not symbols:
            return ("ERROR — `symbols` is required.",
                    {"status": "ERROR", "error": {"code": "SDK_NO_SYMBOLS"}})
        interval = str(args.get("interval") or "1d")
        dataset = await resolve_dataset(
            _gateway(ctx), symbols, primary=interval, start=args.get("start"), end=args.get("end"))
        rows = _series_rows(dataset)
        extra = {name: src for name, src in files.items() if name != entry}
        result, err = await asyncio.to_thread(
            run_strategy_source, str(files[entry]), rows,
            symbols=symbols, interval=interval,
            initial_capital=float(args.get("initialCapital") or 100_000.0),
            random_seed=int(args.get("randomSeed") or 42), params=args.get("params") or {},
            class_name=args.get("className"), strategy_id=args.get("strategyId"),
            timeout_s=min(300.0, float(args.get("timeoutSeconds") or 60.0)),
            extra_files=extra, entry=entry)
        if err is not None:
            return (f"ERROR — {err.get('code')}: {err.get('message')}",
                    {"status": "ERROR", "error": err})
        exp_id = None
        if _flag(args, "save", True):
            exp_id = store.save_experiment(
                result, strategy_id=args.get("strategyId") or result.metadata.get("strategyId"),
                strategy_version=result.metadata.get("strategyVersion"), kind="python_project")
        return (_render_result(result, exp_id), _result_data(result, exp_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Registration ─────────────────────────────────────────────────────────────

def register_strategy_ops_tools(registry: Any) -> list[str]:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 60_000, long_running: bool = False) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout, long_running=long_running,
        ))

    _def("inspect_python_strategy",
         "Statically inspect strategy source: imports, third-party dependencies and dangerous "
         "calls (advisory; the isolated worker is the security boundary).",
         inspect_python_strategy, {"type": "object", "properties": {
             "strategyCode": {"type": "string"}}, "required": ["strategyCode"]})
    _def("request_strategy_approval",
         "Request approval for a strategy version (governed, record-only).",
         request_strategy_approval, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "actor": {"type": "string"}, "note": {"type": "string"}},
             "required": ["strategyId"]})
    _def("decide_strategy_approval",
         "Approve or reject a pending strategy approval.",
         decide_strategy_approval, {"type": "object", "properties": {
             "approvalId": {"type": "string"}, "approve": {"type": "boolean"},
             "actor": {"type": "string"}, "note": {"type": "string"}},
             "required": ["approvalId", "approve"]})
    _def("list_strategy_approvals",
         "List strategy approvals (optionally for one strategy).",
         list_strategy_approvals, {"type": "object", "properties": {
             "strategyId": {"type": "string"}}})
    _def("create_strategy_deployment",
         "Create a governed PAPER deployment record for an approved version; live trading is "
         "refused and no orders are routed.",
         create_strategy_deployment, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "mode": {"type": "string", "enum": ["paper", "live"]},
             "note": {"type": "string"}, "requireApproval": {"type": "boolean"}},
             "required": ["strategyId"]})
    _def("list_strategy_deployments",
         "List strategy deployment records.",
         list_strategy_deployments, {"type": "object", "properties": {
             "strategyId": {"type": "string"}}})
    _def("stop_strategy_deployment",
         "Stop a deployment record.",
         stop_strategy_deployment, {"type": "object", "properties": {
             "deploymentId": {"type": "string"}}, "required": ["deploymentId"]})
    _def("run_python_project",
         "Run a multi-file Python strategy project (entry + sibling modules) in the isolated, "
         "env-scrubbed, time-limited worker.",
         run_python_project, {"type": "object", "properties": {
             "entry": {"type": "string"}, "files": {"type": "object"},
             "className": {"type": "string"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "randomSeed": {"type": "integer"},
             "params": {"type": "object"}, "timeoutSeconds": {"type": "number"},
             "save": {"type": "boolean"}}, "required": ["files", "symbols"]}, 180_000, long_running=True)

    return list(OPS_TOOLS)


OPS_TOOLS: tuple[str, ...] = (
    "inspect_python_strategy",
    "request_strategy_approval", "decide_strategy_approval", "list_strategy_approvals",
    "create_strategy_deployment", "list_strategy_deployments", "stop_strategy_deployment",
    "run_python_project",
)


__all__ = ["OPS_TOOLS", "inspect_source", "register_strategy_ops_tools"]
