"""Closing the loop: run a project's own proposal and record what happened.

The proposer names the next experiment. This module **runs it** — through the
same tool the agent would have called, so the policy gate, the allowlist, the
sandbox and the persistence are the agent's own path, not a second one — and
then records the outcome **back into the project**, so the next proposal is
made against a project that knows what just happened.

Three rules:

- **A proposal is only run when it names a tool and the arguments it needs.**
  A proposal that cannot be run is reported, not attempted.
- **A failure is recorded as a failure.** A refused or failed run is attached
  to the project as a note that says what went wrong - a project that hides
  its failures is a project that cannot learn.
- **Nothing is attached that did not happen.** The executor attaches the
  experiment the run really produced, by the id the run really returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ProposalRun:
    """What happened when one proposal was run."""

    project_id: str
    proposal_id: str
    status: str = "unknown"        # completed | failed | refused | not_runnable
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    experiment_id: Optional[str] = None
    summary: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    attached: Optional[dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        return self.status == "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "proposalId": self.proposal_id,
            "status": self.status,
            "tool": self.tool,
            "args": dict(self.args),
            "experimentId": self.experiment_id,
            "summary": self.summary,
            "detail": dict(self.detail),
            "attached": self.attached,
        }


def _find_proposal(report: dict[str, Any], proposal_id: str) -> Optional[dict[str, Any]]:
    for proposal in report.get("proposals") or []:
        if proposal.get("id") == proposal_id:
            return proposal
    return None


def _experiment_id_of(payload: Any) -> Optional[str]:
    """The experiment a tool result produced, if it produced one."""
    if not isinstance(payload, dict):
        return None
    for key in ("experimentId", "experiment_id"):
        value = payload.get(key)
        if value:
            return str(value)
    result = payload.get("result")
    if isinstance(result, dict):
        return _experiment_id_of(result)
    return None


def _summary_of(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("summary", "text", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:400]
    return ""


async def run_project_proposal(
    ctx: Any,
    project_id: str,
    proposal_id: str,
    *,
    quant_store: Any = None,
    firm: str = "topstep",
    firm_size: str = "50k",
) -> ProposalRun:
    """Run one of a project's proposals and record the outcome in the project."""
    from .propose import propose_next

    project_store = getattr(ctx, "project_store", None)
    if project_store is None:
        return ProposalRun(project_id=project_id, proposal_id=proposal_id,
                           status="not_runnable",
                           summary="the project store is not configured in this runtime")

    report = propose_next(project_store, project_id, quant_store=quant_store,
                          firm=firm, firm_size=firm_size)
    if not report.get("available"):
        return ProposalRun(project_id=project_id, proposal_id=proposal_id,
                           status="not_runnable",
                           summary=str(report.get("reason") or "no such project"))

    proposal = _find_proposal(report, proposal_id)
    if proposal is None:
        return ProposalRun(
            project_id=project_id, proposal_id=proposal_id, status="not_runnable",
            summary=(f"no proposal {proposal_id!r} in this project; it has "
                     f"{report.get('proposalCount', 0)} proposal(s) right now"))

    action = proposal.get("action") or {}
    tool_name = str(action.get("tool") or "")
    args = dict(action.get("args") or {})
    if not tool_name:
        return ProposalRun(project_id=project_id, proposal_id=proposal_id,
                           status="not_runnable",
                           summary="the proposal names no tool to run")

    registry = getattr(ctx, "tool_registry", None)
    if registry is None or tool_name not in set(registry.names()):
        return ProposalRun(project_id=project_id, proposal_id=proposal_id,
                           status="not_runnable", tool=tool_name, args=args,
                           summary=(f"the tool {tool_name!r} is not registered in "
                                    f"this runtime"))

    run = ProposalRun(project_id=project_id, proposal_id=proposal_id,
                      tool=tool_name, args=args)
    try:
        result = await registry.execute(
            tool_name, f"project_{project_id}_{proposal_id}", args, ctx)
    except Exception as exc:  # noqa: BLE001 - a failed run is recorded, not raised
        run.status = "failed"
        run.summary = f"the run failed: {exc}"[:400]
        _record(project_store, run, proposal)
        return run

    payload = getattr(result, "data", None)
    if not isinstance(payload, dict):
        payload = {"result": payload}
    if not getattr(result, "ok", False):
        run.status = "refused"
        run.summary = (getattr(result, "text", "") or "the tool refused the run")[:400]
        error = getattr(result, "error", None)
        run.detail = {"error": {"code": getattr(error, "code", None),
                                "message": getattr(error, "message", None)}}
    else:
        run.status = "completed"
        run.summary = _summary_of(payload) or (getattr(result, "text", "") or
                                               "the run completed")[:400]
        run.experiment_id = _experiment_id_of(payload)
        run.detail = {"result": payload}

    _record(project_store, run, proposal)
    return run


def _record(project_store: Any, run: ProposalRun, proposal: dict[str, Any]) -> None:
    """Write the outcome back into the project."""
    try:
        if run.experiment_id:
            member = project_store.attach(
                run.project_id, "experiment", run.experiment_id,
                label=f"from {run.proposal_id}",
                meta={"proposalId": run.proposal_id, "tool": run.tool,
                      "status": run.status})
            run.attached = {"kind": "experiment", "id": member.id,
                            "ref": member.ref}
        else:
            member = project_store.attach(
                run.project_id, "note", f"proposal:{run.proposal_id}",
                label=f"{run.proposal_id}: {run.status}",
                meta={"proposalId": run.proposal_id, "tool": run.tool,
                      "status": run.status, "summary": run.summary[:280]})
            run.attached = {"kind": "note", "id": member.id, "ref": member.ref}
    except Exception as exc:  # noqa: BLE001 - a bookkeeping failure must not lose the run
        run.attached = None
        run.detail = {**run.detail, "recordError": str(exc)[:200]}


__all__ = ["ProposalRun", "run_project_proposal"]
