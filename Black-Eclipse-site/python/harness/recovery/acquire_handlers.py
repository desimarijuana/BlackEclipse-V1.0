"""Production acquisition handlers (round 4, W5/W9 remainder).

The acquisition lifecycle (`acquisition.py`) stops with a typed plan and hands
the actionable steps back to its caller. This module IS that caller for a
production task run: it turns the plan's `build` step into a REAL acquisition
through the existing gated surfaces, and wires the ORIGINAL task to resume
through the existing DAG — no polling loop, no second queue.

Rules (nothing self-grants):

  * `build` for a UI capability → the real `ui_start_engineering` escalation
    (agent-local durable task state, exactly like the `ui_*` tools);
  * `build` otherwise → a durable code-agent task carrying the objective as its
    acceptance criterion (the existing code capability owns the work);
  * `install` / `enable` → handed back as an operator decision with the exact
    missing facts; this module never installs or enables anything. An MCP preset
    install consumes the SAME single-use `mcp_install` approval and writes a
    disabled config; MCP activation stays in Settings → MCP;
  * the original task gains a REQUIRES dependency on the capability task and is
    parked BLOCKED(DEPENDENCY): when the capability task COMPLETES (its own
    verification passed), `_notify_dependents` unblocks and the scheduler
    re-dispatches it — that resume IS the validation gate;
  * an operator-approval step parks the task ASKING_USER; `resume_callback`
    resumes it from its latest durable checkpoint (`retry_task`'s caller half).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .acquisition import AcquisitionProposal, AcquisitionStep, execute_step

#: Surfaces whose acquisition is AGENT-LOCAL orchestration (creating a durable
#: task — the same class of action as the `ui_*`/`task_*` tools, permission
#: `read`): they may run unattended. Every other surface is a real mutation and
#: stays an operator decision.
AGENT_LOCAL_SURFACES: frozenset[str] = frozenset({"engineering"})


def proposal_from_dict(payload: Optional[dict[str, Any]]) -> AcquisitionProposal:
    """Rebuild the typed proposal from the executor's stop payload.

    Accepts either the stop wrapper (`{"stop": True, "acquisition": {...}}`) or
    the acquisition payload itself.
    """
    data = payload or {}
    if isinstance(data.get("acquisition"), dict):
        data = data["acquisition"]
    steps = [
        AcquisitionStep(
            action=str(raw.get("action") or ""),
            description=str(raw.get("description") or ""),
            capability_id=raw.get("capabilityId"),
            requires_approval=bool(raw.get("requiresApproval", False)),
            surface=str(raw.get("surface") or ""),
            ready=bool(raw.get("ready", False)),
            reason=str(raw.get("reason") or ""),
            missing=tuple(raw.get("missing") or ()),
        )
        for raw in (data.get("steps") or [])
        if isinstance(raw, dict)
    ]
    return AcquisitionProposal(
        query=str(data.get("query") or ""), steps=steps,
        resolved_by=data.get("resolvedBy"), retry=dict(data.get("retry") or {}),
    )


def _create_code_task(
    manager: Any, task: Any, objective: str, *, acceptance: Optional[str] = None,
) -> dict[str, Any]:
    """A durable code-agent task for a non-UI build (the existing code surface).

    Created in the ORIGINAL task's plan: the resume edge is a REQUIRES
    dependency, and the DAG deliberately refuses a cross-plan edge. The task
    carries the objective (or an explicit acceptance line) as its criterion, so
    completion means the capability was verified — that IS the acquisition's
    validation gate.
    """
    from ..tasks.model import AcceptanceCriterionInput, CreateTaskInput

    capability_task = manager.create_task(CreateTaskInput(
        title=f"Build capability: {objective[:100]}", plan_id=task.plan_id,
        description=objective, objective=objective, assigned_agent_id="code-agent",
        acceptance_criteria=[AcceptanceCriterionInput(
            text=acceptance or "The requested capability is implemented, tested and verified.",
        )],
        metadata={"kind": "acquisition", "acquiredFor": task.id},
    ))
    return {"taskId": capability_task.id, "planId": task.plan_id}


def _run_async(coro: Any) -> Any:
    """Await an async surface from the SYNCHRONOUS operator route.

    The acquisition handlers run in a worker thread (the FastAPI sync route) and
    from the task executor. A running event loop is refused honestly — an
    install must never be smuggled into an async context where it would block.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "this acquisition surface is synchronous; run it through the operator route"
    )


def _skill_store(service: Any) -> Any:
    """The ONE skill store (the eclipse-memory store the skill registry rides)."""
    return (
        getattr(service, "memory_store", None)
        or getattr(getattr(service, "memory", None), "store", None)
    )


def _available_tools(service: Any) -> list[str]:
    registry = getattr(service, "skill_registry", None)
    try:
        return list(registry._tool_names())  # noqa: SLF001 - the one validated name source
    except Exception:  # noqa: BLE001 - validation stays best-effort
        return []


def _install_skill(service: Any, source: str, facts: dict[str, Any]) -> dict[str, Any]:
    """The REAL skill install (ADR-H211), gated by a single-use approval.

    The approval is the SAME digest-bound `skill_install` claim the agent tool
    consumes: with no granted, unconsumed approval the handler CREATES the
    pending request and returns `approval_required` — it never installs.
    """
    from ..skills.install import (
        InstallError,
        install_from_github,
        parse_source,
        source_digest,
    )

    try:
        parsed = parse_source(
            source,
            ref=facts.get("ref") if isinstance(facts.get("ref"), str) else None,
            subpath=facts.get("subpath") if isinstance(facts.get("subpath"), str) else None,
        )
    except InstallError as exc:
        return {"surface": "skill", "status": "failed", "reason": str(exc)}
    store = _skill_store(service)
    if store is None:
        return {"surface": "skill", "status": "failed",
                "reason": "the skill store is unavailable in this runtime"}
    approvals = getattr(service, "approvals", None)
    digest = source_digest(parsed)
    claimed = None
    if approvals is not None:
        claimed = approvals.consume_kind(kind="skill_install", request_key="skills", digest=digest)
    if claimed is None:
        pending = None
        if approvals is not None:
            try:
                pending = approvals.request_kind(
                    kind="skill_install", request_key="skills", digest=digest,
                    effect="external_action", run_id="recovery-acquisition",
                    action_summary=f"Install skills from {parsed.display}",
                    affected_data={"source": parsed.canonical}, risk="medium",
                )
            except Exception:  # noqa: BLE001 - a store failure must never authorize
                pending = None
        return {
            "surface": "skill", "status": "approval_required",
            "source": parsed.canonical, "digest": digest,
            "approvalId": (pending or {}).get("id"),
            "next": (
                "grant the single-use skill_install approval for this exact source, "
                "then run the step again with approved: true — nothing was installed"
            ),
        }
    try:
        result = install_from_github(
            store, parsed, available_tools=_available_tools(service),
        )
    except InstallError as exc:
        return {"surface": "skill", "status": "failed", "reason": str(exc)}
    return {
        "surface": "skill", "status": "installed", "source": result.get("source"),
        "installed": result.get("installed") or [], "skipped": result.get("skipped") or [],
    }


def _install_plugin(service: Any, path: str) -> dict[str, Any]:
    """The REAL plugin install through the ONE plugin platform (operator-gated)."""
    plugins = getattr(service, "plugins", None)
    if plugins is None:
        return {"surface": "plugin", "status": "failed",
                "reason": "the plugin platform is unavailable in this runtime"}
    try:
        result = _run_async(plugins.install(str(path), operator=True, enable=False))
    except Exception as exc:  # noqa: BLE001 - a failed install is reported, never hidden
        return {"surface": "plugin", "status": "failed", "reason": str(exc)}
    plugin = result.get("plugin") or {}
    return {
        "surface": "plugin", "status": "installed",
        "pluginId": plugin.get("id") or plugin.get("pluginId"),
        "alreadyInstalled": bool(result.get("alreadyInstalled")),
        "enabled": bool(plugin.get("enabled")),
        "next": "enable it with an approved enable step (nothing self-enables)",
    }


def _install_kit(manager: Any, task: Any, kit_id: str) -> dict[str, Any]:
    """The REAL kit route: a durable code task that scaffolds and verifies the kit."""
    objective = f"Scaffold the {kit_id!r} kit into the project and verify the generated files."
    created = _create_code_task(
        manager, task, objective,
        acceptance=f"The kit {kit_id!r} is scaffolded and its generated files are verified.",
    )
    return {"surface": "scaffold_kit", "status": "pending", "resume": "dependency",
            "kitId": kit_id, **created}


def _mcp_credentials(service: Any, integration_id: str, supplied: dict[str, Any]) -> dict[str, Any]:
    """Presence-only credential status for an MCP preset (never a value).

    The external lane requires the operator to supply the named credentials
    BEFORE an install is attempted. An unavailable resolver is `unverified`, not
    "present"; a missing value is named by its vault key only.
    """
    from ..mcp.presets import integration as find_preset

    spec = find_preset(integration_id)
    names: list[str] = []
    if spec is not None and spec.secret_ref:
        names.append(spec.secret_ref)
    try:
        from ..eclipse_memory.decision import looks_like_credential_value
    except Exception:  # noqa: BLE001 - the shape guard is best-effort
        looks_like_credential_value = lambda _text: False  # noqa: E731
    for raw in supplied.get("credentialNames") or supplied.get("credential_names") or ():
        name = str(raw or "").strip()
        if looks_like_credential_value(name):
            raise ValueError(
                "credential values are not accepted; supply vault secret NAMES only"
            )
        if name and name not in names:
            names.append(name)
    manager = getattr(service, "mcp", None)
    reader = getattr(manager, "secret_presence", None)
    if not names:
        return {"status": "not_required", "required": [], "present": {}}
    if reader is None:
        return {"status": "unverified", "required": names, "present": {}}
    try:
        present = _run_async(reader(names))
    except Exception:  # noqa: BLE001 - unverifiable is not present
        present = {}
    if not present:
        status = "unverified"
    elif all(present.get(name) is True for name in names):
        status = "present"
    else:
        status = "missing"
    return {"status": status, "required": names, "present": dict(present)}


def _install_mcp(service: Any, integration_id: str, supplied: dict[str, Any]) -> dict[str, Any]:
    """Install an MCP preset as a DISABLED config through the MCP approval store.

    Reuses the SAME single-use `mcp_install` approval the agent tool consumes.
    Credentials must already be present by NAME; the handler never receives,
    reads or returns a value. It NEVER enables the server: activation remains the
    operator's Settings → MCP decision.
    """
    from ..mcp.config import load_mcp_configs
    from ..mcp.install_ops import find_integration, install_integration
    from ..mcp.install_tools import APPROVAL_KIND, approval_digest

    spec = find_integration(integration_id)
    if spec is None:
        return {"surface": "mcp", "status": "failed",
                "reason": f"unknown MCP integration {integration_id!r}"}
    credentials = _mcp_credentials(service, integration_id, supplied)
    if credentials["status"] != "present" and credentials["status"] != "not_required":
        missing = [
            f"vault secret {name!r} is not set"
            for name in credentials["required"]
            if credentials["present"].get(name) is not True
        ] or ["credential presence could not be verified by the runtime"]
        return {
            "surface": "mcp", "status": "approval_required",
            "reason": "credentials_required", "integrationId": spec.id,
            "credentials": credentials, "missing": missing,
            "installed": False, "enabled": False,
            "next": (
                "set the named vault secret(s) in Settings, then run this step again; "
                "nothing was installed"
            ),
        }
    approvals = getattr(service, "approvals", None)
    if approvals is None:
        return {"surface": "mcp", "status": "approval_required",
                "reason": "the approval store is unavailable", "installed": False,
                "enabled": False}
    digest = approval_digest(APPROVAL_KIND, spec.id)
    claimed = approvals.consume_kind(
        kind=APPROVAL_KIND, request_key="mcp", digest=digest,
    )
    if claimed is None:
        pending = None
        try:
            pending = approvals.request_kind(
                kind=APPROVAL_KIND, request_key="mcp", digest=digest,
                effect="external_action", run_id="recovery-acquisition",
                action_summary=f"Install MCP integration {spec.id} (disabled; nothing selected)",
                affected_data={"integrationId": spec.id}, risk="medium",
            )
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            pending = None
        return {
            "surface": "mcp", "status": "approval_required",
            "integrationId": spec.id, "digest": digest,
            "approvalId": (pending or {}).get("id"),
            "credentials": credentials, "installed": False, "enabled": False,
            "next": (
                "grant the single-use mcp_install approval for this exact preset, "
                "then run the step again with approved: true — nothing was installed"
            ),
        }
    result = install_integration(spec.id)
    if not result.get("success"):
        return {"surface": "mcp", "status": "failed",
                "reason": result.get("reason") or "the MCP install failed"}
    configs, _ = load_mcp_configs()
    entry = next((item for item in configs if item.id == spec.id), None)
    enabled = bool(getattr(entry, "enabled", False)) if entry is not None else False
    return {
        "surface": "mcp", "status": "installed", "integrationId": spec.id,
        "alreadyInstalled": bool(result.get("alreadyInstalled")),
        "enabled": enabled, "credentials": credentials,
        "next": (
            "the config is disabled; the operator enables it and selects tools in "
            "Settings → MCP (nothing self-enables)"
        ),
    }


def build_acquisition_handlers(
    service: Any, manager: Any, task: Any, *, run_id: Optional[str] = None,
    facts: Optional[dict[str, Any]] = None,
) -> dict[str, Callable[[AcquisitionStep], Any]]:
    """Handlers for `execute_step`, each routed through its existing gate.

    `facts` are operator-supplied install inputs (a GitHub source, an MCP preset
    id, a plugin folder, a kit id). They never authorize anything themselves: a
    skill install still consumes its own single-use, digest-bound approval, an MCP
    install consumes the SAME `mcp_install` approval and writes a disabled config,
    a plugin install still runs through the plugin platform's operator gate, and a
    kit becomes a durable code task whose verified completion is the validation.
    """
    supplied = dict(facts or {})

    def _build(step: AcquisitionStep) -> dict[str, Any]:
        objective = (
            step.description or step.capability_id or task.objective or task.title
        )
        engineering = getattr(getattr(service, "ui", None), "engineering", None)
        if engineering is not None and getattr(engineering, "available", False):
            # The REAL UI escalation gate. It creates its own plan, so the DAG
            # cannot carry the resume edge; the caller parks the original task
            # WAITING and resumes it explicitly when the capability lands.
            result = engineering.start(
                objective, title=f"Acquire: {objective[:100]}", run_id=run_id,
            )
            if result.get("created"):
                return {
                    "surface": "engineering", "status": "pending",
                    "taskId": result.get("taskId"), "planId": result.get("planId"),
                    "resume": "operator",
                }
        created = _create_code_task(manager, task, objective)
        return {
            "surface": "code_task", "status": "pending",
            "resume": "dependency", **created,
        }

    def _install(step: AcquisitionStep) -> dict[str, Any]:
        source = str(supplied.get("source") or "").strip()
        if source:
            return _install_skill(service, source, supplied)
        integration_id = str(
            supplied.get("integrationId") or supplied.get("integration_id") or ""
        ).strip()
        if integration_id:
            return _install_mcp(service, integration_id, supplied)
        plugin_path = str(supplied.get("pluginPath") or "").strip()
        if plugin_path:
            return _install_plugin(service, plugin_path)
        kit_id = str(supplied.get("kitId") or "").strip()
        if kit_id:
            return _install_kit(manager, task, kit_id)
        return {
            "surface": step.surface, "status": "approval_required",
            "missing": list(step.missing) or [
                "unknown: no source, credential or dependency was supplied",
            ],
            "next": (
                "provide the source (GitHub), the MCP preset id, the plugin folder or "
                "the kit id and run the approved install path (skill_install / "
                "mcp_install / the plugin platform / a code task); nothing was installed"
            ),
        }

    def _enable(step: AcquisitionStep) -> dict[str, Any]:
        integration_id = str(
            supplied.get("integrationId") or supplied.get("integration_id") or ""
        ).strip()
        plugin_id = str(supplied.get("pluginId") or "").strip()
        if integration_id and not plugin_id:
            return {
                "surface": "mcp", "status": "approval_required",
                "integrationId": integration_id,
                "next": (
                    "the operator enables the installed MCP server and selects tools in "
                    "Settings → MCP; this runtime never enables an MCP server itself"
                ),
            }
        plugins = getattr(service, "plugins", None)
        if plugin_id and plugins is not None:
            try:
                result = _run_async(plugins.enable(plugin_id, operator=True))
            except Exception as exc:  # noqa: BLE001 - a failed enable is reported
                return {"surface": "plugin", "status": "failed", "reason": str(exc)}
            plugin = result.get("plugin") or {}
            return {
                "surface": "plugin", "status": "enabled",
                "pluginId": plugin.get("id") or plugin_id,
                "alreadyEnabled": bool(result.get("alreadyEnabled")),
            }
        return {
            "surface": step.surface, "status": "approval_required",
            "missing": list(step.missing),
            "next": (
                "an operator must enable the installed capability (a plugin: the "
                "approved enable step; a skill: the evaluation + promotion lifecycle)"
            ),
        }

    return {"build": _build, "install": _install, "enable": _enable}


def park_for_acquisition(manager: Any, task: Any, result: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Park the original task for an already-executed acquisition step.

    The public seam shared by `acquire_for_task` (the task-run caller) and the
    operator route: a same-plan capability task wires a REQUIRES dependency and
    the task is parked BLOCKED (the DAG resumes it on completion); a cross-plan
    capability task parks the task WAITING for an explicit checkpoint resume.
    Never executes anything itself.
    """
    result = result or {}
    capability_task_id = result.get("taskId")
    if result.get("resume") == "dependency" and capability_task_id:
        _wire_dependency(manager, task, str(capability_task_id))
        return {"resume": "dependency", "capabilityTaskId": str(capability_task_id)}
    if capability_task_id:
        try:
            manager.wait_task(task.id, reason="AGENT")
        except Exception:  # noqa: BLE001 - parking is best-effort
            pass
        return {"resume": "operator", "capabilityTaskId": str(capability_task_id)}
    return {"resume": None}


def acquire_for_task(
    service: Any, manager: Any, task: Any, *,
    stop_payload: Optional[dict[str, Any]], run_id: Optional[str] = None,
) -> dict[str, Any]:
    """Attempt the first actionable acquisition step for a stopped task run.

    Only agent-local surfaces run unattended (`AGENT_LOCAL_SURFACES`); a build
    wired through the engineering or code-task surface gets the original task a
    REQUIRES dependency + a BLOCKED(DEPENDENCY) park, so the existing DAG
    resumes it when the capability lands. An install/enable step parks the task
    ASKING_USER for the operator. Returns a status dict; never raises.
    """
    proposal = proposal_from_dict(stop_payload)
    handlers = build_acquisition_handlers(service, manager, task, run_id=run_id)
    for index, step in enumerate(proposal.steps):
        if step.action in ("use", "alternative"):
            continue  # read-only routes; nothing to acquire
        if step.action not in handlers:
            continue
        approved = step.surface in AGENT_LOCAL_SURFACES
        outcome = execute_step(proposal, index, handlers=handlers, approved=approved)
        if outcome.get("status") == "executed":
            parked = park_for_acquisition(manager, task, outcome.get("result"))
            return {
                "handled": True, "status": "executed", "step": outcome.get("step"),
                "result": outcome.get("result"), **parked,
            }
        if outcome.get("status") == "approval_required":
            try:
                manager.wait_task(task.id, reason="APPROVAL")
            except Exception:  # noqa: BLE001 - parking is best-effort; the outcome still reports it
                pass
            return {
                "handled": True, "status": "approval_required",
                "step": outcome.get("step"), "reason": outcome.get("reason"),
                "resume": "operator",
            }
        if outcome.get("status") == "requires_caller":
            continue  # try the next step
        return {"handled": True, "status": outcome.get("status"),
                "step": outcome.get("step"), "reason": outcome.get("reason")}
    return {"handled": False, "status": "no_actionable_step",
            "reason": "no actionable acquisition step for this incident"}


def _wire_dependency(manager: Any, task: Any, capability_task_id: str) -> None:
    """Original task REQUIRES the capability task; park it until it completes."""
    try:
        manager.add_dependency(task.id, capability_task_id)
    except Exception:  # noqa: BLE001 - a cycle/race must not lose the capability task
        pass
    try:
        manager.block_task(
            task.id, reason="DEPENDENCY", blocked_by=[capability_task_id],
        )
    except Exception:  # noqa: BLE001
        pass


def resume_callback(manager: Any, task_id: str) -> Callable[[], Any]:
    """The caller half of `acquisition.retry_task`.

    Resumes the original task from its latest DURABLE checkpoint — the same
    `TaskManager.restore_checkpoint` the operator console uses. Raises when no
    checkpoint exists, so a caller never believes it resumed when it did not.
    """

    def _resume() -> dict[str, Any]:
        result = manager.restore_checkpoint(task_id, resume=True)
        checkpoint = result.get("checkpoint") or {}
        return {
            "taskId": task_id, "resumed": bool(result.get("resumed")),
            "checkpointId": checkpoint.get("id"),
        }

    return _resume


__all__ = [
    "AGENT_LOCAL_SURFACES",
    "acquire_for_task",
    "build_acquisition_handlers",
    "proposal_from_dict",
    "resume_callback",
]
