"""Agent-facing capability detection and build tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..tools import ToolContext
from . import builder
from .adapter import author_adapter
from .external import propose_external
from .request import CapabilityRequest, assess, classify, slug_for
from .registry import refresh_generated_recipes
from .resume import resume_original_task
from .store import CapabilityStore

_TOOL_NAMES = (
    "capability_request",
    "capability_build",
    "capability_status",
    "capability_external",
    "capability_adapter",
    "capability_activate",
    "capability_rollback",
    "capability_remove",
)


class CapabilityBuildInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requestId: str = Field(..., min_length=1, max_length=64)  # noqa: N815
    implementation: Optional[str] = Field(default=None, max_length=20_000)
    test: Optional[str] = Field(default=None, max_length=20_000)
    sampleInputs: Optional[dict[str, Any]] = None  # noqa: N815
    acceptance: Optional[list[str]] = Field(default=None, max_length=12)
    version: Optional[str] = Field(default=None, max_length=16)
    capabilityId: Optional[str] = Field(default=None, max_length=64)  # noqa: N815
    kind: Optional[str] = Field(default=None, max_length=32)
    scope: Optional[str] = Field(default=None, max_length=16)
    imports: Optional[list[str]] = Field(default=None, max_length=32)


class CapabilityIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilityId: str = Field(..., min_length=1, max_length=64)  # noqa: N815
    version: Optional[str] = Field(default=None, max_length=16)


class CapabilityStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requestId: Optional[str] = Field(default=None, max_length=64)  # noqa: N815
    capabilityId: Optional[str] = Field(default=None, max_length=64)  # noqa: N815


class ExternalProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need: str = Field(..., min_length=1, max_length=2_000)
    kind: str = Field(default="auto", max_length=16)
    integrationId: Optional[str] = Field(default=None, max_length=64)  # noqa: N815
    pluginPath: Optional[str] = Field(default=None, max_length=1_000)  # noqa: N815
    serverUrl: Optional[str] = Field(default=None, max_length=2_000)  # noqa: N815
    serverCommand: Optional[str] = Field(default=None, max_length=500)  # noqa: N815
    credentialNames: Optional[list[str]] = Field(default=None, max_length=16)  # noqa: N815


class AdapterAuthorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need: str = Field(..., min_length=1, max_length=2_000)
    baseUrl: str = Field(..., min_length=8, max_length=2_000)  # noqa: N815
    tools: list[dict[str, Any]] = Field(..., min_length=1, max_length=12)
    adapterId: Optional[str] = Field(default=None, max_length=64)  # noqa: N815
    kind: str = Field(default="auto", max_length=16)
    credentialNames: Optional[list[str]] = Field(default=None, max_length=8)  # noqa: N815
    label: Optional[str] = Field(default=None, max_length=120)


def _refusal(code: str, reason: str, **extra: Any) -> tuple[str, Any]:
    return (
        f"REFUSED ({code}): {reason}",
        {"status": "refused", "code": code, "reason": reason, **extra},
    )


def _presence_label(present: Optional[bool]) -> str:
    if present is True:
        return "set"
    if present is False:
        return "missing"
    return "unknown"


def _store(ctx: ToolContext) -> CapabilityStore:
    return CapabilityStore(getattr(ctx, "memory_store", None))


def _root(ctx: ToolContext) -> Optional[Path]:
    workspace = getattr(ctx, "workspace", None)
    root = getattr(workspace, "root", None)
    if root:
        return Path(root)
    try:
        from ..code.workspace import default_root

        return default_root()
    except Exception:
        return None


def _analysis_allowed(ctx: ToolContext) -> bool:
    if not bool(getattr(ctx, "analysis_enabled", False)):
        return False
    try:
        from ..skills.permissions import Actor

        actor = Actor(
            id=getattr(ctx, "user_id", None) or "local",
            operator=False,
            workspace_id=getattr(getattr(ctx, "workspace", None), "id", None),
            autonomy=getattr(ctx, "autonomy", None),
        )
        return "analysis.execute" in actor.granted()
    except Exception:
        return False


async def _emit(ctx: ToolContext, event: str, data: dict[str, Any]) -> None:
    try:
        from ..code.tools import emit_code_event

        await emit_code_event(ctx, event, data)
    except Exception:
        pass


def _verification_event(report: dict[str, Any]) -> dict[str, Any]:
    checks = list(report.get("checks") or [])
    return {
        "status": report.get("status") or "",
        "ok": bool(report.get("ok")),
        "checks": checks[:20],
        "failed": [check for check in checks if not check.get("ok")][:5],
        "stderr": str(report.get("stderr") or "")[:2_000],
    }


def _build_event(request: CapabilityRequest, result: dict[str, Any]) -> dict[str, Any]:
    manifest = result.get("manifest") or {}
    verification = result.get("verification") or {}
    handoff = result.get("handoff") or {}
    return {
        "requestId": request.request_id,
        "need": request.need,
        "capabilityId": result.get("capabilityId"),
        "version": result.get("version"),
        "kind": manifest.get("kind") or handoff.get("kind") or request.kind,
        "title": manifest.get("title") or handoff.get("title") or request.need[:120],
        "description": manifest.get("description") or "",
        "scope": manifest.get("scope") or request.scope,
        "surface": handoff.get("surface") or result.get("surface") or "capability_builder",
        "status": result.get("status"),
        "activation": result.get("activation") or handoff.get("activation"),
        "requiresApproval": bool(result.get("requiresApproval")),
        "inputs": manifest.get("inputs") or [],
        "outputs": manifest.get("outputs") or [],
        "tests": manifest.get("tests") or [],
        "testStatus": verification.get("status") or "",
        "verification": _verification_event(verification) if verification else None,
        "sourceDigest": verification.get("sourceDigest") or "",
        "testDigest": verification.get("testDigest") or "",
        "dir": result.get("dir") or "",
        "reason": result.get("reason") or handoff.get("verification") or "",
        "steps": handoff.get("evidence") or [],
        "missing": handoff.get("missing") or [],
        "nextTool": handoff.get("nextTool") or result.get("nextTool") or "",
    }


async def capability_request(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    try:
        request = CapabilityRequest(**{k: v for k, v in (args or {}).items() if v is not None})
    except Exception as exc:
        return _refusal("INPUT_INVALID", f"the capability request is not valid: {exc}")
    store = _store(ctx)
    # The dynamic recipe registry is process-wide, but a capability belongs to
    # the PROJECT it was built in. Refresh it for THIS run's root before we
    # assess, so discovery and what `analysis_run` can actually execute agree
    # (project B's recipe is not callable from project A).
    refresh_generated_recipes(store, _root(ctx))
    if not request.resume_task_id:
        request.resume_task_id = str(getattr(ctx, "task_id", "") or "")
    assessment = assess(
        request.need,
        kind=request.kind,
        scope=request.scope,
        tool_registry=getattr(ctx, "tool_registry", None),
        store=store,
        root=_root(ctx),
        capability_id=request.capability_id,
    )
    store.save_request(request, status=assessment.status)
    capability_id = slug_for(request.need, request.capability_id)
    data = {
        "status": assessment.status,
        "requestId": request.request_id,
        "capabilityId": capability_id,
        "assessment": assessment.to_dict(),
        "request": request.to_dict(),
    }
    if assessment.kind == "plugin":
        data["external"] = propose_external(request.need).to_dict()
    await _emit(ctx, "capability.requested", {
        "requestId": request.request_id,
        "capabilityId": capability_id,
        "need": request.need,
        "kind": assessment.kind,
        "status": assessment.status,
        "surface": assessment.surface,
        "scope": assessment.scope,
        "requiresApproval": assessment.requires_approval,
        "steps": list(assessment.steps),
        "missing": list(assessment.missing),
        "reason": assessment.reason,
        "matches": list(assessment.matches),
    })
    if assessment.status == "satisfied":
        return (
            f"I can already do that with {assessment.resolved_by}.",
            data,
        )
    if assessment.status == "one_off":
        return (
            "This is a one-off computation. I can work it out once with analysis_run "
            "and won't save it as a recipe.",
            data,
        )
    if assessment.kind == "plugin":
        return (
            "That needs an external adapter (broker, API or MCP), which I cannot "
            "install or enable by myself.\n"
            "I can only propose the existing MCP preset, plugin or endpoint route, name "
            "the credentials the operator must supply, and state the approval it needs. "
            "Nothing is enabled automatically.",
            data,
        )
    if assessment.kind in ("tool", "skill", "ui_widget", "ui_page", "harness_change"):
        return (
            f"That needs a {assessment.kind.replace('_', ' ')} build on "
            f"{assessment.surface}. I can prepare a typed hand-off for "
            f"`{assessment.next_tool}`; the existing surface owns the build, its "
            "approval and its acceptance evidence. Nothing is enabled by this step.",
            data,
        )
    missing = ", ".join(assessment.missing) if assessment.missing else "the build plan"
    return (
        "I can't do that yet — but I can build it.\n"
        f"Need: {request.need}\n"
        f"Surface: {assessment.surface}\n"
        f"Status: ready to build ({missing})\n"
        f"Request: {request.request_id}\n"
        f'Next: call capability_build with requestId="{request.request_id}" plus the '
        "implementation and a test. Do not invent a request id.",
        data,
    )


async def capability_build(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    try:
        model = CapabilityBuildInput(**{k: v for k, v in (args or {}).items() if v is not None})
    except Exception as exc:
        return _refusal("INPUT_INVALID", f"the build request is not valid: {exc}")
    store = _store(ctx)
    saved = store.get_request(model.requestId)
    if saved is None:
        return _refusal("REQUEST_NOT_FOUND", "there is no capability request with that id")
    payload = dict(saved.get("payload") or {})
    for field, value in (
        ("implementation", model.implementation),
        ("test", model.test),
        ("sampleInputs", model.sampleInputs),
        ("acceptance", model.acceptance),
        ("version", model.version),
        ("capabilityId", model.capabilityId),
        ("kind", model.kind),
        ("scope", model.scope),
        ("imports", model.imports),
    ):
        if value is not None:
            payload[field] = value
    try:
        request = CapabilityRequest.from_dict(payload)
    except Exception as exc:
        return _refusal("INPUT_INVALID", f"the saved capability request is not valid: {exc}")
    if classify(request.need, request.kind) in ("recipe", "report_template") and not _analysis_allowed(ctx):
        return _refusal(
            "ANALYSIS_NOT_ENABLED",
            "building and testing a recipe needs the analysis sandbox for this turn",
        )
    result = builder.build(request, store=store, root=_root(ctx), run_id=getattr(ctx, "run_id", None))
    status = str(result.get("status") or "")
    data = {**result, "requestId": request.request_id}
    event = _build_event(request, result)
    if status in ("active", "tested", "approval_required", "unverified", "handoff_required"):
        await _emit(ctx, "capability.built", event)
    if status == "handoff_required":
        handoff = result.get("handoff") or {}
        next_tool = handoff.get("nextTool") or result.get("nextTool") or "the named surface"
        missing = list(handoff.get("missing") or [])
        text = (
            f"This is a {handoff.get('kind', 'capability')} build; the existing "
            f"{handoff.get('surface', 'surface')} owns it. I prepared the hand-off for "
            f"`{next_tool}`."
        )
        if missing:
            text += " Still needed: " + "; ".join(missing[:6]) + "."
        return (
            text + " Nothing was activated; the target surface owns the build, approval "
            "and acceptance evidence.",
            data,
        )
    if status == "active":
        await _emit(ctx, "capability.activated", event)
        tests = len((result.get("verification") or {}).get("checks") or [])
        return (
            f"Built `{result.get('capabilityId')}` v{result.get('version')} and tested it "
            f"({tests} checks). It is active and ready to use.",
            data,
        )
    if status == "tested":
        return (
            f"Built `{result.get('capabilityId')}` v{result.get('version')} and its tests passed. "
            "It still needs an operator to activate it.",
            data,
        )
    if status in ("unverified", "approval_required"):
        report = result.get("verification") or {}
        stderr = str(report.get("stderr") or result.get("reason") or "")
        reason = stderr.splitlines()[0][:300] if stderr else str(result.get("reason") or "needs review")
        await _emit(ctx, "capability.verification_failed", {**event, "reason": reason})
        return (
            f"I built `{result.get('capabilityId')}` but it did not activate: {reason}",
            data,
        )
    if status in ("one_off", "needs_source", "refused"):
        await _emit(ctx, "capability.verification_failed", {**event, "reason": result.get("reason") or status})
    if status == "one_off":
        return (
            "That request is a one-off; use analysis_run instead of saving a capability.",
            data,
        )
    if status == "needs_source":
        return (
            "I need the short implementation program before I can build this capability.",
            data,
        )
    return (
        f"I couldn't build that capability: {result.get('reason') or status}",
        data,
    )


async def capability_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    try:
        model = CapabilityStatusInput(**{k: v for k, v in (args or {}).items() if v is not None})
    except Exception as exc:
        return _refusal("INPUT_INVALID", f"the status request is not valid: {exc}")
    store = _store(ctx)
    if model.requestId:
        request = store.get_request(model.requestId)
        if request is None:
            return _refusal("REQUEST_NOT_FOUND", "there is no capability request with that id")
        payload = request.get("payload") or {}
        capability_id = slug_for(str(payload.get("need") or ""), str(payload.get("capabilityId") or ""))
        records = store.records(capability_id=capability_id, limit=50)
        text = f"Capability request {model.requestId}: {request.get('status')}."
        handoff = payload.get("handoff") or {}
        if handoff:
            text += (
                f" Hand-off: {handoff.get('surface')} via {handoff.get('nextTool')}"
                f" (activation: {handoff.get('activation') or 'operator'})."
            )
        if records:
            latest = records[0]
            text += (
                f" Latest build: {latest.get('capabilityId')} v{latest.get('version')} "
                f"({latest.get('status')})."
            )
        return text, {
            "status": "ok",
            "request": request,
            "records": records,
            "handoff": handoff,
        }
    capability_id = model.capabilityId or ""
    if not capability_id:
        return _refusal("INPUT_INVALID", "give me a request id or a capability id")
    records = store.records(capability_id=capability_id, limit=50)
    if not records:
        return _refusal("NOT_FOUND", "there is no capability with that id")
    latest = records[0]
    return (
        f"{capability_id}: v{latest.get('version')} is {latest.get('status')} "
        f"({len(records)} version(s)).",
        {"status": "ok", "records": records},
    )


async def capability_external(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Propose an operator-gated external adapter. Read-only."""
    try:
        model = ExternalProposalInput(**{k: v for k, v in (args or {}).items() if v is not None})
    except Exception as exc:
        return _refusal("INPUT_INVALID", f"the external proposal is not valid: {exc}")
    names = list(model.credentialNames or [])
    if model.integrationId:
        try:
            from ..mcp.presets import integration as find_preset

            spec = find_preset(model.integrationId)
            if spec is not None and spec.secret_ref and spec.secret_ref not in names:
                names.append(spec.secret_ref)
        except Exception:  # noqa: BLE001 - a catalog failure leaves presence unknown
            pass
    presence: dict[str, bool] = {}
    manager = getattr(ctx, "mcp_manager", None)
    reader = getattr(manager, "secret_presence", None)
    if reader is not None and names:
        try:
            presence = await reader(names)
        except Exception:  # noqa: BLE001 - presence stays unknown, never optimistic
            presence = {}
    try:
        proposal = propose_external(
            model.need,
            kind=model.kind,
            integration_id=model.integrationId or "",
            plugin_path=model.pluginPath or "",
            server_url=model.serverUrl or "",
            server_command=model.serverCommand or "",
            credential_names=names,
            secret_present=lambda name: presence.get(name),
        )
    except ValueError as exc:
        return _refusal("CREDENTIAL_VALUE", str(exc))
    data = {"status": "proposed", **proposal.to_dict()}
    if proposal.surface == "operator":
        return (
            "I can't name an external surface yet. Tell me the MCP preset id, the "
            "plugin folder, or the MCP endpoint/command, plus the credential NAMES "
            "(never values). Nothing was installed or enabled.",
            data,
        )
    credential_line = ", ".join(
        f"{item.name} ({_presence_label(item.present)})"
        for item in proposal.credentials
    ) or "none declared"
    approval = proposal.approval_kind or "operator"
    return (
        f"External adapter proposal: {proposal.kind} via {proposal.surface}.\n"
        f"Adapter: {proposal.adapter_id or 'not named'}\n"
        f"Credentials (names only): {credential_line}\n"
        f"Approval: {approval}. Activation: operator only. Next tool: {proposal.next_action}.\n"
        "Nothing was installed or enabled. Next: "
        + "; ".join(proposal.next_steps[:4]),
        data,
    )


async def capability_adapter(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Author a REVIEWABLE, DISABLED broker/API adapter draft. Installs nothing."""
    try:
        model = AdapterAuthorInput(**{k: v for k, v in (args or {}).items() if v is not None})
    except Exception as exc:
        return _refusal("INPUT_INVALID", f"the adapter contract is not valid: {exc}")
    root = _root(ctx)
    if root is None:
        return _refusal(
            "WORKSPACE_UNAVAILABLE",
            "authoring an adapter draft needs a writable workspace",
        )
    try:
        draft = author_adapter(
            model.need,
            base_url=model.baseUrl,
            tools=model.tools,
            root=root,
            adapter_id=model.adapterId or "",
            kind=model.kind,
            credential_names=model.credentialNames or (),
            label=model.label or "",
        )
    except ValueError as exc:
        text = str(exc).lower()
        code = "CREDENTIAL_VALUE" if "credential" in text else "INPUT_INVALID"
        return _refusal(code, str(exc))
    except OSError as exc:
        return _refusal("WRITE_FAILED", f"the adapter draft could not be written: {exc}")
    data = {"status": "drafted", **draft.to_dict()}
    credential_line = ", ".join(draft.credentials) or "none"
    return (
        f"Adapter draft written to {draft.directory}: {draft.kind}, "
        f"{len(draft.tool_names)} tool(s).\n"
        f"Credentials (names only): {credential_line}\n"
        "It is NOT installed and NOT enabled. The operator must review the auth "
        "scheme, install it through the plugin platform, supply the secrets and "
        "enable it explicitly.",
        data,
    )


async def capability_activate(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    try:
        model = CapabilityIdInput(**{k: v for k, v in (args or {}).items() if v is not None})
    except Exception as exc:
        return _refusal("INPUT_INVALID", f"the activation request is not valid: {exc}")
    result = builder.activate(
        model.capabilityId, model.version, store=_store(ctx), root=_root(ctx),
    )
    status = str(result.get("status") or "")
    if status == "active":
        resume = resume_original_task(
            getattr(ctx, "task_manager", None),
            (result.get("record") or {}).get("taskId"),
        )
        result["resume"] = resume
        await _emit(ctx, "capability.activated", {
            "capabilityId": model.capabilityId,
            "version": result.get("version"),
            "activation": "manual",
            "status": "active",
            "requiresApproval": False,
            "resume": resume,
        })
        suffix = (
            " Resumed the original task from its checkpoint."
            if resume.get("resumed") else ""
        )
        return (
            f"Activated {model.capabilityId} v{result.get('version')}.{suffix}",
            result,
        )
    if status == "approval_required":
        return (
            "That capability is effectful and needs an operator to activate it; nothing changed.",
            result,
        )
    return (
        f"I couldn't activate it: {result.get('reason') or status}",
        result,
    )


async def capability_rollback(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    try:
        model = CapabilityIdInput(**{k: v for k, v in (args or {}).items() if v is not None})
    except Exception as exc:
        return _refusal("INPUT_INVALID", f"the rollback request is not valid: {exc}")
    result = builder.rollback(
        model.capabilityId, model.version, store=_store(ctx), root=_root(ctx),
    )
    if result.get("status") == "active":
        resume = resume_original_task(
            getattr(ctx, "task_manager", None),
            (result.get("record") or {}).get("taskId"),
        )
        result["resume"] = resume
        await _emit(ctx, "capability.activated", {
            "capabilityId": model.capabilityId,
            "version": result.get("version"),
            "activation": "rollback",
            "status": "active",
            "requiresApproval": False,
            "resume": resume,
        })
        suffix = (
            " Resumed the original task from its checkpoint."
            if resume.get("resumed") else ""
        )
        return (
            f"Rolled back {model.capabilityId} to v{result.get('version')}.{suffix}",
            result,
        )
    return (
        f"I couldn't roll it back: {result.get('reason') or result.get('status')}",
        result,
    )


async def capability_remove(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    try:
        model = CapabilityIdInput(**{k: v for k, v in (args or {}).items() if v is not None})
    except Exception as exc:
        return _refusal("INPUT_INVALID", f"the removal request is not valid: {exc}")
    result = builder.retire(model.capabilityId, store=_store(ctx))
    if result.get("status") == "retired":
        await _emit(ctx, "capability.retired", {
            "capabilityId": model.capabilityId,
            "version": result.get("version"),
            "status": "retired",
        })
        return (
            f"Retired {model.capabilityId}; its files remain for audit.",
            result,
        )
    return (
        f"I couldn't retire it: {result.get('reason') or result.get('status')}",
        result,
    )


def _obj(properties: dict[str, Any], required: Optional[list[str]] = None) -> dict[str, Any]:
    return {
        "type": "object", "properties": properties,
        "required": required or [], "additionalProperties": False,
    }


def capability_schemas() -> dict[str, dict[str, Any]]:
    port = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": ["series", "table", "scalar", "text"]},
            "required": {"type": "boolean"},
            "description": {"type": "string"},
        },
        "required": ["name", "kind"],
        "additionalProperties": False,
    }
    return {
        "capability_request": _obj({
            "need": {"type": "string", "description": "What Eclipse should be able to do, in the user's words."},
            "examples": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "string", "description": "Why this is missing or what was tried."},
            "kind": {"type": "string", "enum": [
                "auto", "one_off", "recipe", "report_template", "tool", "skill",
                "ui_widget", "ui_page", "plugin", "harness_change",
            ]},
            "scope": {"type": "string", "enum": ["workspace", "global"]},
            "capabilityId": {"type": "string"},
            "version": {"type": "string"},
            "inputs": {"type": "array", "items": port},
            "outputs": {"type": "array", "items": port},
            "permissions": {"type": "array", "items": {"type": "string"}},
            "imports": {"type": "array", "items": {"type": "string"}},
            "acceptance": {"type": "array", "items": {"type": "string"}},
            "timeoutMs": {"type": "integer"},
            "implementation": {"type": "string", "description": "A short Python program for a recipe: reads `inputs`, puts the answer in `result`."},
            "test": {"type": "string", "description": "A contract test fragment: assertions over `inputs` and `result`."},
            "sampleInputs": {"type": "object", "description": "Representative inputs used only to run the contract test."},
        }, ["need"]),
        "capability_build": _obj({
            "requestId": {"type": "string"},
            "implementation": {"type": "string"},
            "test": {"type": "string"},
            "sampleInputs": {"type": "object"},
            "acceptance": {"type": "array", "items": {"type": "string"}},
            "version": {"type": "string"},
            "capabilityId": {"type": "string"},
            "kind": {"type": "string"},
            "scope": {"type": "string"},
            "imports": {"type": "array", "items": {"type": "string"}},
        }, ["requestId"]),
        "capability_status": _obj({
            "requestId": {"type": "string"},
            "capabilityId": {"type": "string"},
        }),
        "capability_external": _obj({
            "need": {
                "type": "string",
                "description": "The external capability needed, e.g. 'read my broker positions'.",
            },
            "kind": {"type": "string", "enum": ["auto", "broker", "api", "mcp"]},
            "integrationId": {
                "type": "string",
                "description": "An MCP preset id from mcp_integrations, when one fits.",
            },
            "pluginPath": {
                "type": "string",
                "description": "An operator-supplied local plugin folder.",
            },
            "serverUrl": {
                "type": "string",
                "description": "An operator-supplied MCP server URL (never with credentials).",
            },
            "serverCommand": {
                "type": "string",
                "description": "An operator-supplied stdio MCP server command.",
            },
            "credentialNames": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Vault secret NAMES only; never a secret value.",
            },
        }, ["need"]),
        "capability_adapter": _obj({
            "need": {
                "type": "string",
                "description": "What the adapter must reach, e.g. 'read my broker positions'.",
            },
            "baseUrl": {
                "type": "string",
                "description": "HTTPS base URL; never embed credentials.",
            },
            "tools": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "method": {"type": "string", "enum": ["GET", "POST"]},
                        "path": {"type": "string", "description": "Fixed path beginning with /."},
                        "description": {"type": "string"},
                    },
                    "required": ["name"],
                },
                "description": "GET tools are read-only; POST tools are external actions.",
            },
            "adapterId": {"type": "string"},
            "kind": {"type": "string", "enum": ["auto", "broker", "api"]},
            "credentialNames": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Vault secret NAMES only; never a secret value.",
            },
            "label": {"type": "string"},
        }, ["need", "baseUrl", "tools"]),
        "capability_activate": _obj({
            "capabilityId": {"type": "string"},
            "version": {"type": "string"},
        }, ["capabilityId"]),
        "capability_rollback": _obj({
            "capabilityId": {"type": "string"},
            "version": {"type": "string"},
        }, ["capabilityId"]),
        "capability_remove": _obj({
            "capabilityId": {"type": "string"},
            "version": {"type": "string"},
        }, ["capabilityId"]),
    }


_DESCRIPTIONS = {
    "capability_request": (
        "Check whether Eclipse already has a capability for a need. If not, decide whether "
        "it is a one-off computation, a reusable recipe/template, or an effectful capability "
        "with an existing owner, and return the cheapest safe route. Read-only."
    ),
    "capability_build": (
        "Build a reusable analysis recipe from a capability request: write a versioned "
        "manifest, run its contract test in the sandbox, and auto-activate a pure workspace "
        "recipe only when the test passes. An effectful kind (tool, skill, UI, harness, "
        "plugin) instead returns a typed hand-off for its existing owner; it never builds "
        "or activates it."
    ),
    "capability_status": (
        "Show a capability request or build's status, versions and any effectful hand-off. Read-only."
    ),
    "capability_external": (
        "Propose an external adapter (broker, API or MCP) through the existing MCP preset "
        "or plugin platform. Returns the credential NAMES the operator must supply, the "
        "single-use/operator approval each step needs, and the acquisition route. It "
        "installs nothing and never enables anything. Read-only."
    ),
    "capability_adapter": (
        "Author a reviewable broker/API plugin DRAFT (manifest, code, README) from an "
        "operator-supplied HTTPS endpoint and tool list. Credential NAMES only. Writes "
        "to the disabled draft area; installs nothing and enables nothing. The operator "
        "reviews the auth scheme, installs, supplies secrets and enables explicitly."
    ),
    "capability_activate": "Activate a tested pure recipe; effectful capabilities require an operator.",
    "capability_rollback": "Restore a previously tested version of a capability.",
    "capability_remove": "Retire a capability; its files remain for audit.",
}

_HANDLERS = {
    "capability_request": capability_request,
    "capability_build": capability_build,
    "capability_status": capability_status,
    "capability_external": capability_external,
    "capability_adapter": capability_adapter,
    "capability_activate": capability_activate,
    "capability_rollback": capability_rollback,
    "capability_remove": capability_remove,
}


def register_capability_tools(registry: Any) -> list[str]:
    from ..tools import ToolDefinition

    schemas = capability_schemas()
    added: list[str] = []
    for name in _TOOL_NAMES:
        registry.register(ToolDefinition(
            name=name,
            description=_DESCRIPTIONS[name],
            input_schema=schemas[name],
            handler=_HANDLERS[name],
            permission="read",
            risk="low",
            timeout_ms=(180_000 if name == "capability_build" else 30_000),
        ))
        added.append(name)
    return added


__all__ = [
    "capability_adapter",
    "capability_build",
    "capability_external",
    "capability_request",
    "capability_schemas",
    "register_capability_tools",
]
