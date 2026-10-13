"""The `analysis_run` tool handler (Phase 8), extracted from `code/tools.py`.

Let Eclipse COMPUTE reproducibly in the Phase 3 sandbox, with the result labelled
by where it came from, so a computed number can never be mistaken for a retrieved
one. The tool is OFF per run unless the run enables it
(`RunRequest.analysisEnabled`, default False) — the same "discovery is not
activation" discipline the MCP layer applies.
"""

from __future__ import annotations

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
from .tools import ToolContext


class AnalysisRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Either a named recipe OR a source program. A recipe is preferred.
    recipe: Optional[str] = Field(default=None, max_length=64)
    source: Optional[str] = Field(default=None, max_length=20_000)
    inputs: dict[str, Any] = Field(default_factory=dict)
    purpose: str = Field(..., min_length=1, max_length=300)
    timeout_s: int = Field(120, ge=1, le=600)


def analysis_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "recipe": {
                "type": "string",
                "description": "A ready-made analysis to run (preferred). Get the list from the tool description.",
            },
            "source": {
                "type": "string",
                "description": "Only when no recipe fits: a short Python program. It reads its data from `inputs` and puts its answer in `result`. No network, no files outside its own folder.",
            },
            "inputs": {
                "type": "object",
                "description": "The data the analysis uses, keyed by input name. Passed as data, never written into the program.",
            },
            "purpose": {"type": "string", "description": "In plain words, what this works out (shown to the user)."},
            "timeout_s": {"type": "integer", "description": "How long it may run (seconds)."},
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


def _computed_text(result: AnalysisResult, purpose: str) -> str:
    """The plain, user-facing rendering — never interpreter/argv vocabulary."""
    if result.status != "ok":
        return f"I couldn't work that out ({result.status})."
    lines = ["Worked out by Eclipse.", f"What: {purpose}."]
    for key, value in list(result.outputs.items())[:12]:
        lines.append(f"  {key}: {value}")
    if result.artifacts:
        names = ", ".join(a.name for a in result.artifacts)
        lines.append(f"Saved: {names}")
    return "\n".join(lines)


async def analysis_run(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    from .code.tools import emit_code_event  # noqa: PLC0415

    model = AnalysisRunInput(**{k: v for k, v in args.items() if v is not None})

    # Default OFF per run — discovery is not activation.
    if not bool(getattr(ctx, "analysis_enabled", False)):
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

    output_dir = _artifacts_dir(ctx)
    await emit_code_event(ctx, "analysis.started", {"recipe": model.recipe or None, "purpose": model.purpose})

    try:
        if model.recipe:
            result = run_recipe(
                model.recipe, model.inputs, output_dir=output_dir, timeout_s=model.timeout_s,
            )
        else:
            request = AnalysisRequest(
                source=model.source or "",
                inputs=[
                    AnalysisInput(name=str(name), value=value, kind=_infer_kind(value))
                    for name, value in model.inputs.items()
                ],
                purpose=model.purpose,
                timeout_s=model.timeout_s,
            )
            result = run_analysis(request, output_dir=output_dir)
    except AnalysisError as exc:
        await emit_code_event(ctx, "analysis.refused", {"code": exc.code})
        return _refusal(exc.code, exc.reason)

    _record_analysis(ctx, result)
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
        "provenance": result.provenance.to_dict() if result.provenance else None,
        "outputs": result.outputs,
        "artifacts": [a.model_dump(by_alias=True) for a in result.artifacts],
        "sourceDigest": result.source_digest,
        "inputDigests": result.input_digests,
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


__all__ = ["AnalysisRunInput", "analysis_run", "analysis_schema", "list_recipes", "get_recipe"]
