"""The `scaffold_kit` tool handler (Phase 9), extracted from `code/tools.py`.

Make "build me X" produce a real, working, VERIFIED artefact. The handler:

  * renders the chosen kit to its CLOSED `produces` set (nothing else),
  * writes it into the TASK'S WORKSPACE (never the user's checkout),
  * runs the kit's `checks` through the Phase 3 command broker, recording them in
    the Phase 4 ledger,
  * keeps the scaffold on a failed check for inspection — never silently deletes.

The tool is OFF unless the run holds `code.write` through a bound workspace and a
profile (the same gate the write tools use).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .code import patch as patch_mod
from .code import policy
from .code.kits import KitLoadError, get_kit, render_checks, render_kit
from .tools import ToolContext


class ScaffoldKitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kit_id: str = Field(..., min_length=1, max_length=64)
    inputs: dict[str, Any] = Field(default_factory=dict)


def scaffold_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "kit_id": {
                "type": "string",
                "description": "Which ready-made shape to build (e.g. ratio_calculator, market_data_adapter, research_workflow).",
            },
            "inputs": {
                "type": "object",
                "description": "The answers the shape needs (e.g. a name and a short description).",
            },
        },
        "required": ["kit_id"],
        "additionalProperties": False,
    }


def _refusal(code: str, reason: str, *, data: Optional[dict[str, Any]] = None) -> tuple[str, Any]:
    payload = {"status": "refused", "code": code, "reason": reason}
    if data:
        payload.update(data)
    return f"REFUSED ({code}): {reason}", payload


def _autonomy_grants_write(ctx: ToolContext) -> bool:
    autonomy = getattr(ctx, "autonomy", None)
    return bool(autonomy and "code.write" in policy.code_grants(str(autonomy)))


async def scaffold_kit(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    # Imported lazily: `code/tools.py` imports this module's schema at load time.
    from .code.tools import _ensure_code_workspace, emit_code_event  # noqa: PLC0415

    model = ScaffoldKitInput(**{k: v for k, v in args.items() if v is not None})

    if getattr(ctx, "workspace", None) is None:
        await emit_code_event(ctx, "kit.refused", {"kitId": model.kit_id, "code": "WORKSPACE_UNBOUND"})
        return _refusal(
            "WORKSPACE_UNBOUND",
            "there is no project folder bound to this run. scaffold_kit writes files, so "
            "it needs a code task; for a reusable procedure use skill_create and for a "
            "scheduled agent use bot_create.",
        )
    if not _autonomy_grants_write(ctx):
        await emit_code_event(ctx, "kit.refused", {"kitId": model.kit_id, "code": "PROFILE_DENIED"})
        return _refusal(
            "PROFILE_DENIED",
            "this run's profile does not grant code.write, so a kit cannot write files "
            "here. This is not a missing capability: use skill_create for a procedure, "
            "bot_create for a scheduled agent, or start a code-enabled task for a file build.",
        )

    kit = get_kit(model.kit_id)
    if kit is None:
        await emit_code_event(ctx, "kit.refused", {"kitId": model.kit_id, "code": "KIT_UNKNOWN"})
        return _refusal("KIT_UNKNOWN", f"there's no ready-made shape named {model.kit_id!r}")

    try:
        rendered = render_kit(model.kit_id, model.inputs or {})
    except KitLoadError as exc:
        await emit_code_event(ctx, "kit.refused", {"kitId": model.kit_id, "code": exc.code})
        code = exc.code if exc.code != "KIT_INPUT_MISSING" else "KIT_INPUT_MISSING"
        return _refusal(code, exc.message)

    # The declared set is closed: the rendered paths are the only thing written.
    declared = set(rendered)
    if not declared:
        return _refusal("OUTPUT_OUTSIDE_DECLARED_SET", "the shape produced nothing to write")

    # Write into the disposable workspace via the Phase 2 patch engine.
    try:
        cw, binding, resolved, actor = _ensure_code_workspace(ctx)
    except Exception as exc:  # noqa: BLE001 - a workspace failure is a refusal
        return _refusal("WORKSPACE_UNBOUND", str(exc))

    # `patch.parse_patch` owns path safety; create one op per file. A path outside
    # the workspace or in a protected location is refused there, before any write.
    ops = []
    for rel, text in rendered.items():
        ops.append({
            "op": "create", "path": rel,
            "reason": f"scaffold kit {model.kit_id}",
            "content": text,
        })
    try:
        parsed = patch_mod.parse_patch({"operations": ops})
        result = patch_mod.apply(resolved, parsed, binding=binding, actor=actor, emitter=ctx.emitter)
    except patch_mod.PatchError as exc:
        await emit_code_event(ctx, "kit.refused", {"kitId": model.kit_id, "code": exc.code})
        return _refusal("OUTPUT_OUTSIDE_DECLARED_SET", exc.reason, data={"files": sorted(declared)})
    if not result.get("ok"):
        refused = result.get("refused") or {}
        return _refusal("OUTPUT_OUTSIDE_DECLARED_SET", refused.get("reason", "the files couldn't be written"))

    await emit_code_event(ctx, "kit.scaffolded", {
        "kitId": model.kit_id, "workspaceId": cw.id, "files": len(declared),
    })

    # Run the kit's checks through the Phase 3 broker, recording to the ledger.
    check_results: list[dict[str, Any]] = []
    for check in render_checks(model.kit_id, model.inputs or {}):
        outcome = await _run_check(ctx, check["commandClass"], check["args"], resolved.root, cw.id)
        check_results.append(outcome)
        if outcome.get("status") != "ok":
            await emit_code_event(ctx, "kit.check_failed", {
                "kitId": model.kit_id, "commandClass": check["commandClass"],
                "code": outcome.get("code"), "files": sorted(declared),
            })
            # The scaffold is KEPT for inspection — never silently deleted.
            prompt = "Want me to fix it?"
            return (
                f"REFUSED (CHECK_FAILED): I built it, but one check didn't pass. {prompt}",
                {
                    "status": "refused", "code": "CHECK_FAILED",
                    "files": sorted(declared), "checks": check_results,
                    "recovery": prompt,
                },
            )

    text = (
        f"Done — I built the {kit.manifest.title.lower()} and checked it. "
        f"{len(check_results)} check(s) passed."
    )
    data = {
        "status": "ok", "kitId": model.kit_id, "title": kit.manifest.title,
        "files": sorted(declared), "checks": check_results, "workspaceId": cw.id,
        "inert": model.kit_id == "research_workflow",
    }
    return text, data


async def _run_check(
    ctx: ToolContext, command_class: str, args: dict[str, Any], cwd: Path, workspace_id: str,
) -> dict[str, Any]:
    """Run one kit check through the Phase 3 broker. Records to the ledger."""
    from .code.commands import CommandUnavailable, build_argv, resolve_class  # noqa: PLC0415
    from .code.sandbox import RunSpec, SandboxUnavailable, build_env, run as sandbox_run  # noqa: PLC0415
    from .code.sandbox import select_backend  # noqa: PLC0415

    try:
        resolved_class = resolve_class(command_class)
        argv = build_argv(resolved_class, args or {})
    except CommandUnavailable as exc:
        return {"commandClass": command_class, "status": "refused", "code": exc.code}
    try:
        select_backend()
    except SandboxUnavailable:
        return {"commandClass": command_class, "status": "refused", "code": "SANDBOX_UNAVAILABLE"}

    spec = RunSpec(
        argv=argv, cwd=Path(cwd), env=build_env(),
        timeout_s=resolved_class.timeout_s, output_cap_bytes=resolved_class.output_cap_bytes,
        network=resolved_class.network,
    )
    raw = sandbox_run(spec)
    execution_id = ""
    store = getattr(ctx, "code_store", None)
    if store is not None:
        try:
            record = store.record_command_execution(
                run_id=str(getattr(ctx, "run_id", "")), command_class=command_class,
                argv=argv, cwd=str(cwd), exit_code=raw.exit_code, duration_ms=raw.duration_ms,
                output=raw.output, total_chars=raw.total_chars, sandbox_backend=raw.backend,
                policy_decision={"allowed": True, "code": "OK"},
                timed_out=raw.timed_out, truncated=raw.truncated,
            )
            execution_id = str(record.get("id") or "")
        except Exception:  # noqa: BLE001
            pass
    ledger = getattr(ctx, "code_ledger", None)
    if ledger is not None and raw.exit_code is not None:
        try:
            ledger.record(
                command_execution_id=execution_id, command_class=command_class,
                exit_code=int(raw.exit_code), duration_ms=raw.duration_ms, output=raw.output,
                argv=tuple(argv),
            )
        except Exception:  # noqa: BLE001
            pass
    status = "ok" if raw.exit_code == 0 else ("timed_out" if raw.timed_out else "failed")
    return {
        "commandClass": command_class, "status": status, "exitCode": raw.exit_code,
        "durationMs": raw.duration_ms, "executionId": execution_id,
    }


__all__ = ["ScaffoldKitInput", "scaffold_kit", "scaffold_schema"]
