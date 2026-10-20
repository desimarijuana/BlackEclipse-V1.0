"""The `analysis_run` tool handler (Phase 8), extracted from `code/tools.py`.

Let Eclipse COMPUTE reproducibly in the Phase 3 sandbox, with the result labelled
by where it came from, so a computed number can never be mistaken for a retrieved
one. The tool is OFF per run unless the run enables it
(`RunRequest.analysisEnabled`, default False) — the same "discovery is not
activation" discipline the MCP layer applies.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .code import policy
from .code.execution import (
    ANALYSIS_NOT_ENABLED,
    IMPORT_NOT_ALLOWED,
    INPUT_INVALID,
    OUTPUT_TOO_LARGE,
    SANDBOX_UNAVAILABLE,
    TIMED_OUT,
    AnalysisError,
    AnalysisInput,
    AnalysisRequest,
    AnalysisResult,
    run_analysis,
)
from .code.recipes import get_recipe, list_recipes, run_recipe
from .code.sandbox_tools import ToolResolver, tool_names
from .tools import ToolContext


class AnalysisRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Either a named recipe OR a source program. A recipe is preferred.
    recipe: Optional[str] = Field(default=None, max_length=64)
    source: Optional[str] = Field(default=None, max_length=20_000)
    inputs: dict[str, Any] = Field(default_factory=dict)
    purpose: str = Field(..., min_length=1, max_length=300)
    timeout_s: int = Field(120, ge=1, le=600)
    # Start a fresh sandbox interpreter for this session instead of reusing the
    # warm one (a recovery escape hatch; it never changes the isolation rules).
    reset: bool = False


def recipe_catalogue_text() -> str:
    """The ready-made recipes as ONE line, for the tool description.

    Built from the registry, so the description can never drift from the
    recipes that actually exist.
    """
    rows = []
    for recipe in list_recipes():
        names = ", ".join(str(i.get("name")) for i in recipe.get("inputs") or [])
        rows.append(f"{recipe.get('name')}({names}) - {recipe.get('answers')}")
    return "; ".join(rows)


def analysis_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "recipe": {
                "type": "string",
                "description": (
                    "A ready-made analysis to run (preferred). The ready-made recipes are: "
                    f"{recipe_catalogue_text()}"
                ),
            },
            "source": {
                "type": "string",
                "description": (
                    "Only when no recipe fits: a short Python program. It reads its data from "
                    "`inputs` and puts its answer in `result`. It may `import eclipse_tools` "
                    f"and call the read-only bindings {', '.join(tool_names())}; arguments are "
                    "JSON values and fetched data stays out of the conversation. No network, "
                    "no writes, no files outside its own folder."
                ),
            },
            "inputs": {
                "type": "object",
                "description": "The data the analysis uses, keyed by input name. Passed as data, never written into the program.",
            },
            "purpose": {"type": "string", "description": "In plain words, what this works out (shown to the user)."},
            "timeout_s": {"type": "integer", "description": "How long it may run (seconds)."},
            "reset": {
                "type": "boolean",
                "description": "Start a fresh sandbox interpreter for this session (use after a broken analysis).",
            },
        },
        "required": ["purpose"],
        "additionalProperties": False,
    }


def _refusal(code: str, reason: str, *, prompt: str = "") -> tuple[str, Any]:
    plain = reason if not prompt else f"{reason} {prompt}".strip()
    data = {"status": "refused", "code": code, "reason": reason, "message": plain}
    if prompt:
        data["prompt"] = prompt
    return f"REFUSED ({code}): {plain}", data


def _artifacts_dir(ctx: ToolContext) -> Optional[Path]:
    """The per-run artefact directory, or None when no root is available.

    `.black-eclipse/artifacts/<runId>/` — gitignored, scoped to the run.
    """
    from .code.workspace import default_root  # noqa: PLC0415

    root = default_root()
    if root is None:
        return None
    return Path(root) / ".black-eclipse" / "artifacts" / str(getattr(ctx, "run_id", "run"))


def _capability_root(ctx: ToolContext) -> Optional[Path]:
    root = getattr(getattr(ctx, "workspace", None), "root", None)
    if root:
        return Path(root)
    from .code.workspace import default_root  # noqa: PLC0415

    return default_root()


def _refresh_capability_recipes(ctx: ToolContext) -> list[str]:
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return []
    try:
        from .capabilities.registry import refresh_generated_recipes  # noqa: PLC0415

        return refresh_generated_recipes(store, _capability_root(ctx))
    except Exception:  # noqa: BLE001 - generated recipes are additive
        return []


async def _record_capability_usage(ctx: ToolContext, name: str, result: AnalysisResult) -> None:
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return
    try:
        from .capabilities.registry import is_generated_recipe  # noqa: PLC0415
        from .capabilities.store import CapabilityStore  # noqa: PLC0415

        if not is_generated_recipe(name):
            return
        capability_store = CapabilityStore(store)
        active = capability_store.records(capability_id=name, status="active", limit=1)
        if not active:
            return
        usage = capability_store.record_usage(
            name, str(active[0].get("version") or ""),
            ok=(result.status == "ok"), run_id=getattr(ctx, "run_id", None),
            duration_ms=result.duration_ms,
        )
        if result.status != "ok":
            try:
                from .code.evolution import record_mistake_recurrence  # noqa: PLC0415

                record_mistake_recurrence(
                    store, ["capability_failure"], run_id=getattr(ctx, "run_id", None),
                )
            except Exception:  # noqa: BLE001 - learning is additive
                pass
        if usage.get("disabled"):
            from .code.tools import emit_code_event  # noqa: PLC0415

            await emit_code_event(ctx, "capability.disabled", {
                "capabilityId": name,
                "version": str(active[0].get("version") or ""),
                "reason": "repeated failures",
                "status": "disabled",
            })
    except Exception:  # noqa: BLE001 - usage recording is additive
        pass


def _record_analysis(ctx: ToolContext, result: AnalysisResult) -> None:
    """Persist one AnalysisRecord over the ONE agent-memory connection.

    Owned HERE (like `run_lineage.py` owns its own columns) rather than in the
    ratcheted `persistence.py`. Additive + idempotent DDL; old-row-safe.
    """
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return
    try:
        import json  # noqa: PLC0415

        from .persistence import now_iso  # noqa: PLC0415

        db = store._db  # noqa: SLF001 - the one shared connection
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS AnalysisRecord (
              id           TEXT PRIMARY KEY,
              runId        TEXT NOT NULL,
              status       TEXT NOT NULL,
              purpose      TEXT,
              sourceDigest TEXT,
              result       TEXT NOT NULL,
              createdAt    TEXT NOT NULL
            )
            """
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_analysis_run ON AnalysisRecord(runId, createdAt)"
        )
        import uuid  # noqa: PLC0415

        db.execute(
            "INSERT INTO AnalysisRecord (id, runId, status, purpose, sourceDigest, result, createdAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "an_" + uuid.uuid4().hex[:16], str(getattr(ctx, "run_id", "")),
                result.status, None, result.source_digest,
                json.dumps(result.to_blob()), now_iso(),
            ),
        )
        db.commit()
    except Exception:  # noqa: BLE001 - the record is additive; never break the call
        pass


#: How many analysis records a run may carry as evidence (bounded).
MAX_RUN_ANALYSES = 20


def load_run_analyses(store: Any, run_id: str, *, limit: int = MAX_RUN_ANALYSES) -> Optional[dict[str, Any]]:
    """Read one run's recorded analyses as bounded evidence (W14).

    The rows were written by `_record_analysis` during the run; the task
    verifier reads them so a `data` task can check that a reproducible
    computation happened — never a number in prose. `None` when the table does
    not exist yet (no analysis ran) or the store is unavailable: never a
    fabricated record.
    """
    if store is None or not run_id:
        return None
    db = getattr(store, "_db", None)
    if db is None:
        return None
    try:
        rows = db.execute(
            "SELECT status, sourceDigest, result FROM AnalysisRecord WHERE runId=? "
            "ORDER BY createdAt LIMIT ?",
            (str(run_id), int(limit)),
        ).fetchall()
    except Exception:  # noqa: BLE001 - a missing table/read failure is no evidence
        return None
    records: list[dict[str, Any]] = []
    for row in rows:
        # Positional access works for both tuple rows and `sqlite3.Row`.
        status, source_digest, raw = row[0], row[1], row[2]
        try:
            blob = json.loads(raw) if raw else {}
        except Exception:  # noqa: BLE001 - a malformed row is skipped, not fatal
            blob = {}
        if not isinstance(blob, dict):
            blob = {}
        records.append({
            "status": str(blob.get("status") or status or ""),
            "sourceDigest": str(blob.get("sourceDigest") or source_digest or ""),
            "inputDigests": blob.get("inputDigests") if isinstance(blob.get("inputDigests"), dict) else {},
            "outputs": blob.get("outputs") if isinstance(blob.get("outputs"), dict) else {},
            "artifactCount": len(blob.get("artifacts") or []),
        })
    if not records:
        return None
    return {"records": records, "count": len(records)}


def _tool_resolver_for(ctx: ToolContext, deadline: float) -> Optional[ToolResolver]:
    """Bridge a SANDBOX-side (sync, worker-thread) read to the async DataBridge.

    `run_analysis` is synchronous and now runs on a worker thread, so it cannot
    call the async bridge directly. The resolver posts the coroutine back to the
    run's event loop and blocks only the worker thread, never the loop.
    """
    bridge = getattr(ctx, "data_bridge", None)
    if bridge is None:
        return None
    loop = asyncio.get_running_loop()

    def resolve(capability: str, params: dict[str, Any]) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("the analysis ran out of time while waiting for data")
        future = asyncio.run_coroutine_threadsafe(bridge.fetch(capability, params), loop)
        return future.result(timeout=remaining)

    return resolve


def _computed_text(result: AnalysisResult, purpose: str) -> str:
    """The plain, user-facing rendering — never interpreter/argv vocabulary.

    A failure carries its REASON: the model can only fix a program it can see
    the error from, so a silent "I couldn't work that out" is a dead end.
    """
    if result.status != "ok":
        detail = (result.stderr or "").strip()
        tail = f" The error was: {detail[:600]}" if detail else ""
        return f"I couldn't work that out ({result.status}).{tail}"
    lines = ["Worked out by Eclipse.", f"What: {purpose}."]
    raw = result.outputs if isinstance(result.outputs, dict) else {}
    values = [kv for kv in raw.items() if not str(kv[0]).startswith("_")]
    shown = values[:12]
    for key, value in shown:
        lines.append(f"  {key}: {value}")
    if len(values) > len(shown):
        # Say how many there are: a cut-off list must be VISIBLE as cut off, or
        # the model reports the numbers it happened to see as the result.
        lines.append(
            f"  (showing {len(shown)} of {len(values)} values — re-run for the "
            f"rest, or ask for a smaller payload)"
        )
    if result.tool_calls:
        lines.append(
            f"Data read: {len(result.tool_calls)} lookup(s); names and digests are in the run record."
        )
    if result.artifacts:
        names = ", ".join(a.name for a in result.artifacts)
        lines.append(f"Saved: {names}")
    return "\n".join(lines)


def _analysis_allowed() -> bool:
    """Whether the RUNTIME allows sandboxed computation at all (W14).

    The per-run flag is a REQUEST; the operator's setting is the DECISION. A
    client can ask for the sandbox, but it cannot switch on what the operator
    switched off. `HARNESS_ANALYSIS_ENABLED=0` turns the whole surface off.
    """
    flag = os.environ.get("HARNESS_ANALYSIS_ENABLED", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def _cancel_signal(ctx: ToolContext) -> Optional[Any]:
    """The sandbox's cancel signal, mirroring the run's own (W14).

    The runtime's cancel event is an `asyncio.Event`; the sandbox waits on a
    `threading.Event`. A watcher task bridges them, so a cancelled run kills
    the analysis process tree.
    """
    import threading  # noqa: PLC0415

    source = getattr(ctx, "cancel_event", None)
    if source is None:
        return None
    signal = threading.Event()
    try:
        loop = asyncio.get_running_loop()

        async def _watch() -> None:
            try:
                await source.wait()
            except Exception:  # noqa: BLE001 - a watcher must never raise
                return
            signal.set()

        loop.create_task(_watch())
    except Exception:  # noqa: BLE001 - no loop: the call is synchronous anyway
        return None
    return signal


async def analysis_run(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    from .code.tools import emit_code_event  # noqa: PLC0415

    model = AnalysisRunInput(**{k: v for k, v in args.items() if v is not None})

    # Default OFF per run — discovery is not activation. The request asks for
    # it; the operator's setting decides (W14).
    if not bool(getattr(ctx, "analysis_enabled", False)) or not _analysis_allowed():
        await emit_code_event(ctx, "analysis.refused", {"code": ANALYSIS_NOT_ENABLED})
        return _refusal(ANALYSIS_NOT_ENABLED, "analysis isn't turned on for this session")

    # The run must hold the analysis verb. `analysis.execute` is in
    # SAFE_PERMISSIONS (the default actor), so this is the permission gate the
    # phase names; the isolation itself is the Phase 3 sandbox (checked inside
    # `run_analysis`).
    actor = _actor(ctx)
    if not _holds_analysis(actor):
        await emit_code_event(ctx, "analysis.refused", {"code": "PROFILE_DENIED"})
        return _refusal("PROFILE_DENIED", "this session isn't set up to work things out from data")

    if not model.recipe and not model.source:
        return _refusal(INPUT_INVALID, "nothing to work out — a recipe or a program is needed")

    _refresh_capability_recipes(ctx)

    output_dir = _artifacts_dir(ctx)
    await emit_code_event(ctx, "analysis.started", {"recipe": model.recipe or None, "purpose": model.purpose})

    deadline = time.monotonic() + max(1, int(model.timeout_s))
    resolver = _tool_resolver_for(ctx, deadline)

    def _run_sync() -> AnalysisResult:
        # The persistent kernel is an execution strategy, never a second data
        # path. A spawn failure returns None and the one-shot runner is used,
        # so a missing kernel can never fail an analysis.
        from .code.kernel import (  # noqa: PLC0415
            kernel_for_context,
            release_kernel,
            reset_kernel_for_context,
        )

        if model.reset:
            reset_kernel_for_context(ctx)
        kernel = kernel_for_context(ctx)
        # The run's cancellation becomes the sandbox's: a cancelled run kills
        # its process tree instead of leaving a child behind (W14).
        cancel = _cancel_signal(ctx)
        try:
            if model.recipe:
                return run_recipe(
                    model.recipe, model.inputs, output_dir=output_dir,
                    timeout_s=model.timeout_s, tool_resolver=resolver, kernel=kernel,
                    cancel_event=cancel,
                )
            request = AnalysisRequest(
                source=model.source or "",
                inputs=[
                    AnalysisInput(name=str(name), value=value, kind=_infer_kind(value))
                    for name, value in model.inputs.items()
                ],
                purpose=model.purpose,
                timeout_s=model.timeout_s,
                allow_tools=resolver is not None,
            )
            return run_analysis(
                request, output_dir=output_dir, tool_resolver=resolver, kernel=kernel,
                cancel_event=cancel,
            )
        finally:
            release_kernel(kernel)

    try:
        # The sandbox is synchronous; run it OFF the event loop so a read-only
        # bridge call can be posted back to this loop while it waits.
        result = await asyncio.to_thread(_run_sync)
    except AnalysisError as exc:
        await emit_code_event(ctx, "analysis.refused", {"code": exc.code})
        return _refusal(exc.code, exc.reason)

    _record_analysis(ctx, result)
    if model.recipe and result.status in ("ok", "failed", "timed_out"):
        await _record_capability_usage(ctx, model.recipe, result)
    # Universal registration: every file the sandbox produced is recorded in the
    # Artifact Center (idempotent per run+digest) so it is discoverable, not just
    # mentioned in this response. Best-effort; never fails the analysis.
    try:
        from .artifacts.producers import register_run_artifacts  # noqa: PLC0415

        register_run_artifacts(
            ctx, result.artifacts, source_tool="analysis_run",
            agent_id=getattr(ctx, "agent_id", None),
        )
    except Exception:  # noqa: BLE001
        pass
    # Phase 19: verify what was produced — the recorded reference is an
    # OBSERVATION, never a claim. The records ride the run's ledger so a sentence
    # about the artifact is backed or marked UNVERIFIED. Best-effort; never fails
    # the analysis.
    ledger = getattr(ctx, "code_ledger", None)
    if ledger is not None and result.artifacts:
        try:
            from .code.verify import verify_artifacts  # noqa: PLC0415

            for record in verify_artifacts(result.artifacts, output_dir, None):
                ledger.record_artifact(record)
        except Exception:  # noqa: BLE001
            pass
    await emit_code_event(ctx, "analysis.completed", {
        "status": result.status, "code": result.code,
        "artifacts": len(result.artifacts),
        "durationMs": result.duration_ms,
        # The bounded result blob (outputs, artifacts, provenance) rides the event
        # so the chat can show what Eclipse WORKED OUT — the same shape that is
        # persisted to `AnalysisRecord`, never a second rendering contract (R3-06).
        "result": result.to_blob(),
    })

    # A missing-input refusal ASKS; it never substitutes a default.
    if result.status == "refused" and result.code == INPUT_INVALID:
        prompt = str(result.outputs.get("_prompt") or "")
        return _refusal(INPUT_INVALID, "some details I need for that aren't here yet", prompt=prompt)

    if result.status == "refused":
        reason = {IMPORT_NOT_ALLOWED: "that used something I'm not allowed to use",
                  SANDBOX_UNAVAILABLE: "I can't work things out safely on this computer right now",
                  OUTPUT_TOO_LARGE: "the result was too big to keep"}.get(result.code or "", "I couldn't work that out")
        return _refusal(result.code or "ANALYSIS_REFUSED", reason)

    text = _computed_text(result, model.purpose)
    data = {
        "status": result.status,
        "code": result.code,
        "recipe": model.recipe or None,
        "provenance": result.provenance.to_dict() if result.provenance else None,
        "outputs": result.outputs,
        "artifacts": [a.model_dump(by_alias=True) for a in result.artifacts],
        # Phase 18 (§6.1): the figure payload when a recipe drew one — drawn from
        # which recorded series, with the seed, and always the computed label.
        "figure": result.figure.to_dict() if result.figure else None,
        "sourceDigest": result.source_digest,
        "inputDigests": result.input_digests,
        # Phase 3: read-only host calls (metadata only, never the fetched value).
        "toolCalls": [call.model_dump(by_alias=True) for call in result.tool_calls],
        "interpreter": result.interpreter,
        "packageLockDigest": result.package_lock_digest,
        "durationMs": result.duration_ms,
    }
    return text, data


def _actor(ctx: ToolContext) -> Any:
    from .skills.permissions import Actor  # noqa: PLC0415

    return Actor(
        id=getattr(ctx, "user_id", None) or "local",
        operator=False,
        workspace_id=getattr(getattr(ctx, "workspace", None), "id", None),
        autonomy=getattr(ctx, "autonomy", None),
    )


def _holds_analysis(actor: Any) -> bool:
    return "analysis.execute" in actor.granted()


def _infer_kind(value: Any) -> str:
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return "table"
        return "series"
    if isinstance(value, dict):
        return "table"
    return "scalar"


__all__ = [
    "AnalysisRunInput",
    "MAX_RUN_ANALYSES",
    "analysis_run",
    "analysis_schema",
    "list_recipes",
    "get_recipe",
    "load_run_analyses",
]
