"""The auto-run — a project acting on its own, inside a hard budget.

The policy says *when* a project may act; this is the thing that acts. It is
deliberately timid:

- it only ever runs a proposal whose action is a **compute** the policy
  allows (`AUTO_RUNNABLE_TOOLS`);
- it only ever runs **one** proposal per project per tick, and only if the
  project's budget says there is room;
- it records every attempt - the successful ones and the refusals - so the
  ledger shows what the project did while nobody was watching;
- it **never raises**: a project that cannot act is a normal outcome, not an
  error.

The auto-run is OFF for every project until someone turns it on. That is the
default and it is not negotiable: a system that spends resources on its own
initiative must be asked first.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

from .policy import AUTO_RUNNABLE_TOOLS

log = logging.getLogger("harness.projects.auto")

#: How often the loop looks for a project that is allowed to act.
DEFAULT_TICK_SECONDS = 300.0


async def tick_projects(ctx: Any, *, now: Any = None) -> dict[str, Any]:
    """One tick: let every project that is allowed to, act once.

    Returns a small report: what was considered, what ran, what was refused and
    why.
    """
    from .execute import run_project_proposal
    from .propose import propose_next

    policy_store = getattr(ctx, "auto_run_store", None)
    project_store = getattr(ctx, "project_store", None)
    quant_store = getattr(ctx, "quant_store", None)
    report: dict[str, Any] = {
        "considered": 0, "ran": [], "skipped": [], "errors": [],
    }
    if policy_store is None or project_store is None:
        return report

    for policy in policy_store.enabled_policies():
        report["considered"] += 1
        budget = policy_store.budget_state(policy, now=now)
        if not budget.get("mayRun"):
            report["skipped"].append({"projectId": policy.project_id,
                                      "reason": ",".join(budget.get("blockedBy") or [])})
            continue

        try:
            proposals = propose_next(project_store, policy.project_id,
                                     quant_store=quant_store)
        except Exception as exc:  # noqa: BLE001 - one project must not stop the tick
            report["errors"].append({"projectId": policy.project_id,
                                     "error": str(exc)[:200]})
            continue
        if not proposals.get("available"):
            report["skipped"].append({"projectId": policy.project_id,
                                      "reason": "no_such_project"})
            continue

        chosen = None
        for proposal in proposals.get("proposals") or []:
            tool = str((proposal.get("action") or {}).get("tool") or "")
            if tool and policy.may_run(tool):
                chosen = proposal
                break
        if chosen is None:
            report["skipped"].append({"projectId": policy.project_id,
                                      "reason": "no_runnable_proposal"})
            continue

        run = await run_project_proposal(ctx, policy.project_id, chosen["id"],
                                        quant_store=quant_store)
        policy_store.record_run(
            policy.project_id, chosen["id"], run.tool or "-", run.status,
            summary=run.summary, experiment_id=run.experiment_id)
        report["ran"].append({"projectId": policy.project_id,
                              "proposalId": chosen["id"], "status": run.status,
                              "tool": run.tool, "summary": run.summary})
    return report


class AutoRunLoop:
    """The background loop that ticks the auto-run."""

    def __init__(self, ctx: Any, *, interval_s: float = DEFAULT_TICK_SECONDS) -> None:
        self.ctx = ctx
        self.interval_s = max(30.0, float(interval_s))
        self._task: Optional[asyncio.Task] = None

    async def _loop(self) -> None:
        while True:
            try:
                report = await tick_projects(self.ctx)
                if report.get("ran"):
                    log.info("[harness-py] project auto-run: %s", report["ran"])
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a tick failure must not kill the loop
                log.warning("project auto-run tick failed", exc_info=True)
            await asyncio.sleep(self.interval_s)

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            self._task = asyncio.get_running_loop().create_task(self._loop())
        except RuntimeError:
            self._task = None

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


def build_context(service: Any) -> Any:
    """The context the auto-run acts in: the same tools a run would get."""
    from ..tools import ToolContext

    return ToolContext(
        run_id=f"project_auto_{uuid.uuid4().hex[:8]}",
        log=lambda *_a, **_k: None,
        quant_store=getattr(service, "quant_store", None),
        market_gateway=getattr(service, "market_gateway", None),
        data_bridge=service.server_bridge(),
        tool_registry=getattr(service, "registry", None),
        project_store=getattr(service, "project_store", None),
    )


def start_auto_loop(service: Any, *, interval_s: float = DEFAULT_TICK_SECONDS
                    ) -> dict[str, Any]:
    """Start the auto-run loop for this service. Never raises."""
    from .policy import get_auto_run_store

    if get_auto_run_store() is None:
        return {"available": False, "reason": "the project layer is not installed"}
    try:
        loop = AutoRunLoop(build_context(service), interval_s=interval_s)
        loop.start()
        service._project_auto_loop = loop
        return {"available": True}
    except Exception as exc:  # noqa: BLE001 - the auto-run must never block boot
        log.warning("project auto-run failed to start", exc_info=True)
        return {"available": False, "reason": str(exc)[:200]}


async def stop_auto_loop(service: Any) -> None:
    """Stop the auto-run loop. Never raises."""
    loop = getattr(service, "_project_auto_loop", None)
    if loop is None:
        return
    try:
        await loop.stop()
    except Exception:  # noqa: BLE001 - shutdown must never raise
        log.warning("project auto-run shutdown failed", exc_info=True)


__all__ = [
    "AutoRunLoop",
    "DEFAULT_TICK_SECONDS",
    "build_context",
    "start_auto_loop",
    "stop_auto_loop",
    "tick_projects",
]
