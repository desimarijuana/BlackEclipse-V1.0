"""TeamService — plan, delegate, schedule, reconcile and review a bot team.

This is a composition layer, not a second runtime. It:
  * validates a team's capability/permission/budget/DAG;
  * delegates each subtask through the EXISTING A2A layer (registry, least
    privilege, budgets, durable messages) into the EXISTING Task runtime;
  * starts ONE durable plan so the EXISTING `TaskScheduler` dispatches the graph
    concurrently, honouring per-bot and per-plan concurrency limits;
  * collects results, reconciles evidence-based conflicts (`conflicts.py`) and
    runs an independent review with bounded repair (`review.py`).

Every subtask is a normal `service.run` dispatched by the scheduler with its own
agent, instructions, tools and model policy. Nothing here re-implements an agent
loop, a provider router, a memory store or a task database.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable, Optional

from ..persistence import now_iso
from .conflicts import ReconcileResult, reconcile
from .graph import map_task_status, topological_layers, validate_graph
from .model import (
    MAX_REPAIR_ATTEMPTS,
    SUBTASK_TERMINAL,
    TeamDefinition,
    TeamFinding,
    TeamMember,
    TeamRun,
    TeamRunStatus,
    TeamSubtask,
    TeamSubtaskStatus,
    new_team_run_id,
)
from .review import ReviewInput, repeat_signature, repair_plan, review
from .store import TeamStore

log = logging.getLogger("harness.team.service")

TEAM_ERROR = "TEAM_ERROR"
TEAM_INVALID = "TEAM_INVALID"
TEAM_UNAVAILABLE = "TEAM_UNAVAILABLE"
TEAM_NO_AGENT = "TEAM_NO_AGENT"
TEAM_NOT_FOUND = "TEAM_NOT_FOUND"
TEAM_APPROVAL_REQUIRED = "TEAM_APPROVAL_REQUIRED"


class TeamError(RuntimeError):
    """A structured team refusal. ``code`` is stable and testable."""

    def __init__(self, code: str, reason: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.detail = detail or {}


class TeamService:
    def __init__(self, host: Any, *, a2a: Any = None, store: Optional[TeamStore] = None) -> None:
        self._host = host
        self._a2a = a2a if a2a is not None else getattr(host, "a2a", None)
        self.store = store or TeamStore(host.store)

    # ── collaborators ───────────────────────────────────────────────────────────

    def _ensure_a2a(self) -> Any:
        if self._a2a is None:
            from ..a2a.bootstrap import install_a2a_layer  # noqa: PLC0415

            install_a2a_layer(self._host)
            self._a2a = getattr(self._host, "a2a", None)
        if self._a2a is None:
            raise TeamError(TEAM_UNAVAILABLE, "the A2A delegation layer is unavailable")
        return self._a2a

    def _task_manager(self) -> Any:
        manager = getattr(self._host, "tasks", None)
        if manager is None:
            from ..tasks.bootstrap import install_task_layer  # noqa: PLC0415

            install_task_layer(self._host)
            manager = getattr(self._host, "tasks", None)
        if manager is None:
            raise TeamError(TEAM_UNAVAILABLE, "the task runtime is unavailable")
        return manager

    def _evidence_exists(self) -> Optional[Callable[[str], bool]]:
        evidence = getattr(self._host, "evidence_store", None)
        db = getattr(getattr(evidence, "_store", None), "_db", None)
        if db is None:
            return None

        def exists(ref: str) -> bool:
            try:
                return db.execute(
                    "SELECT 1 FROM WebResearchEvidence WHERE evidenceId=? LIMIT 1", (ref,)
                ).fetchone() is not None
            except Exception:  # noqa: BLE001
                return False

        return exists

    def _publish(self, run: TeamRun, event_type: str, data: dict[str, Any]) -> None:
        bus = getattr(self._host, "bus", None)
        if bus is None:
            return
        try:
            bus.publish({
                "type": event_type, "at": now_iso(),
                "data": {"teamRunId": run.id, "planId": run.plan_id, **data},
            })
        except Exception:  # noqa: BLE001 - a live listener never breaks a write
            pass

    # ── registration ────────────────────────────────────────────────────────────

    def _member_tools(self, member: TeamMember, allow_fanout: bool) -> Optional[list[str]]:
        """A member's declared surface, plus `delegate` when the team opted in.

        Only the NAME is added: the delegation tool still enforces its own caps,
        tool narrowing and permissions, so this widens no authority by itself.
        A member with no declared surface already inherits everything.
        """
        if not allow_fanout or member.tools is None:
            return member.tools
        return member.tools if "delegate" in member.tools else [*member.tools, "delegate"]

    def _ensure_member_agent(self, member: TeamMember, *, allow_fanout: bool = False) -> None:
        """Register a member agent (and its run preset) if it is not known yet."""
        a2a = self._ensure_a2a()
        from ..a2a.model import AgentDefinition, AgentStatus  # noqa: PLC0415
        from ..a2a.registry import RegistryError  # noqa: PLC0415

        tools = self._member_tools(member, allow_fanout)
        try:
            a2a.registry.get_agent(member.agent_id)
            return
        except RegistryError:
            pass
        try:
            definition = AgentDefinition(
                id=member.agent_id, name=member.label or member.agent_id,
                description=f"Team member ({member.role})",
                role=member.role or "specialist", capabilities=list(member.capabilities),
                tools=tools, can_delegate=False, status=AgentStatus.ACTIVE,
                system_instructions=(member.instructions or
                                     f"You are {member.label or member.agent_id}, a specialist on a team."),
            )
            a2a.registry.register_agent(definition)
            a2a._install_agent_configs([{  # noqa: SLF001 - the shared preset seam
                "id": member.agent_id, "name": member.label or member.agent_id,
                "systemPrompt": definition.system_instructions,
                "tools": tools, "maxSteps": 8,
            }])
        except Exception:  # noqa: BLE001 - registration is best-effort; validation catches it
            log.warning("could not register team member %s", member.agent_id, exc_info=True)

    # ── validation ───────────────────────────────────────────────────────────────

    def _member_for(self, team: TeamDefinition, agent_id: str) -> Optional[TeamMember]:
        return next((m for m in team.members if m.agent_id == agent_id), None)

    def _team_approved(self, team: TeamDefinition) -> bool:
        """Whether a granted, single-use operator approval exists for this team.

        Uses the ONE A2A approval store; a missing store is an honest refusal,
        never a silent allow.
        """
        try:
            a2a = self._ensure_a2a()
            approvals = a2a.store.list_approvals(status="GRANTED", limit=500)
        except Exception:  # noqa: BLE001
            return False
        return any(
            str(row.get("kind")) == "team_run" and str(row.get("subject")) == team.id
            for row in approvals
        )

    def _resolve_agent(self, team: TeamDefinition, subtask: TeamSubtask) -> str:
        """Capability-based discovery restricted to the team's authorised members."""
        if subtask.assigned_agent_id:
            if self._member_for(team, subtask.assigned_agent_id) is None:
                raise TeamError(
                    TEAM_NO_AGENT,
                    f"subtask {subtask.id!r} is assigned to {subtask.assigned_agent_id!r}, "
                    "which is not a team member",
                )
            return subtask.assigned_agent_id
        if subtask.capability:
            for member in team.members:
                if subtask.capability in member.capabilities:
                    return member.agent_id
            raise TeamError(
                TEAM_NO_AGENT,
                f"no team member declares capability {subtask.capability!r} for subtask {subtask.id!r}",
            )
        if len(team.members) == 1:
            return team.members[0].agent_id
        raise TeamError(
            TEAM_NO_AGENT,
            f"subtask {subtask.id!r} names no agent and no capability to resolve one",
        )

    def validate(self, team: TeamDefinition) -> list[str]:
        """Every reason the team cannot run (empty = valid). Never raises."""
        errors: list[str] = []
        if not team.members:
            errors.append("a team needs at least one member")
        if not team.subtasks:
            errors.append("a team needs at least one subtask")
        if not team.policy.delegation_enabled:
            errors.append("delegation is disabled for this team")
        if len(team.subtasks) > team.policy.max_children:
            errors.append(
                f"{len(team.subtasks)} subtasks exceed the policy's maxChildren "
                f"({team.policy.max_children})"
            )
        errors.extend(validate_graph(team.subtasks))
        # Resolve every subtask's agent (only meaningful once the graph is sane).
        if not errors:
            for subtask in team.subtasks:
                try:
                    self._resolve_agent(team, subtask)
                except TeamError as exc:
                    errors.append(exc.reason)
        return errors

    # ── planning + dispatch ───────────────────────────────────────────────────────

    async def run(
        self, team: TeamDefinition, *, root_run_id: Optional[str] = None,
        model_settings: Optional[dict[str, Any]] = None, autostart: bool = True,
    ) -> TeamRun:
        """Validate, build the durable graph, delegate every subtask, start it."""
        errors = self.validate(team)
        if errors:
            raise TeamError(TEAM_INVALID, "; ".join(errors), detail={"errors": errors})
        if team.policy.allowed_providers and model_settings:
            provider = str(model_settings.get("provider") or "")
            if provider and provider not in team.policy.allowed_providers:
                raise TeamError(
                    TEAM_INVALID,
                    f"provider {provider!r} is not in the team's allowed providers",
                )
        if team.policy.require_approval and not self._team_approved(team):
            raise TeamError(
                TEAM_APPROVAL_REQUIRED,
                f"team {team.id!r} requires an operator approval before it can run",
                detail={"teamId": team.id, "kind": "team_run"},
            )

        a2a = self._ensure_a2a()
        manager = self._task_manager()
        root = root_run_id or ("team_" + uuid.uuid4().hex[:12])

        for member in team.members:
            self._ensure_member_agent(
                member, allow_fanout=team.policy.member_fanout,
            )

        # One budget for the whole run: each subtask (and each bounded repair)
        # consumes one agent + one task, so the caps must cover the graph.
        a2a.budgets.set_limits(
            root, max_agents=max(len(team.members) + 1, team.policy.max_tasks),
            max_depth=team.policy.max_depth, max_tasks=team.policy.max_tasks,
            max_cost=team.policy.max_cost, max_runtime_ms=team.policy.max_runtime_ms,
        )

        from ..tasks.model import CreatePlanInput, TaskPriority  # noqa: PLC0415

        plan_meta: dict[str, Any] = {
            "team": True, "teamId": team.id, "rootRunId": root,
            "maxConcurrency": team.policy.max_concurrency,
        }
        if model_settings:
            plan_meta["modelSettings"] = model_settings
        plan = manager.create_plan(CreatePlanInput(
            name=f"Team {team.name}"[:300], objective=team.objective,
            agent_id=team.agent_id, priority=TaskPriority.NORMAL, metadata=plan_meta,
        ))

        task_ids: dict[str, str] = {}
        for subtask in self._ordered(team.subtasks):
            agent_id = self._resolve_agent(team, subtask)
            member = self._member_for(team, agent_id)
            deps = [task_ids[dep] for dep in subtask.depends_on if dep in task_ids]
            handle = await a2a.delegate_task(
                sender_agent_id=team.agent_id, run_id=root, objective=subtask.objective,
                target_agent_id=agent_id, capability=subtask.capability or None,
                context=self._render_context(team, subtask),
                tool_subset=(
                    self._member_tools(member, team.policy.member_fanout)
                    if member else None
                ),
                priority=subtask.priority, root_run_id=root,
                dependencies=deps, autostart=False, plan_id=plan.id,
            )
            task_ids[subtask.id] = handle["taskId"]
            manager.update_task(handle["taskId"], {"metadata": {
                "a2a": True, "team": True, "teamRunId": "",  # set after run id below
                "teamId": team.id, "rootRunId": root, "subtaskId": subtask.id,
                "senderAgentId": team.agent_id,
                "expectedOutput": subtask.expected_output,
                "maxConcurrency": member.max_concurrency if member else 1,
            }})

        if autostart:
            manager.start_plan(plan.id)

        run = TeamRun(
            id=new_team_run_id(), team_id=team.id, name=team.name, root_run_id=root,
            plan_id=plan.id, status=TeamRunStatus.RUNNING if autostart else TeamRunStatus.PLANNING,
            subtask_task_ids=task_ids, member_agents=[m.agent_id for m in team.members],
            review_required=team.policy.require_review, created_at=now_iso(), updated_at=now_iso(),
            definition=team.model_dump(by_alias=True),
        )
        for task_id in task_ids.values():
            task = manager.get_task(task_id)
            meta = dict(task.metadata or {})
            meta["teamRunId"] = run.id
            manager.update_task(task_id, {"metadata": meta})
        self.store.save_run(run)
        self._publish(run, "team.started", {
            "subtasks": list(task_ids.keys()), "members": run.member_agents,
        })
        return run

    def _ordered(self, subtasks: list[TeamSubtask]) -> list[TeamSubtask]:
        layers = topological_layers(subtasks)
        by_id = {s.id: s for s in subtasks}
        return [by_id[sid] for layer in layers for sid in layer]

    def _render_context(self, team: TeamDefinition, subtask: TeamSubtask) -> str:
        lines = [f"Team objective: {team.objective}"] if team.objective else []
        if subtask.input_refs:
            lines.append("Inputs: " + ", ".join(subtask.input_refs))
        if subtask.depends_on:
            lines.append("Depends on: " + ", ".join(subtask.depends_on))
        if subtask.expected_output:
            lines.append("Expected output keys: " + ", ".join(sorted(subtask.expected_output.keys())))
        return "\n".join(lines)[:4_000]

    # ── status + collection ─────────────────────────────────────────────────────

    def get_run(self, run_id: str) -> TeamRun:
        run = self.store.get_run(run_id)
        if run is None:
            raise TeamError(TEAM_NOT_FOUND, f"no team run {run_id!r}")
        return run

    def list_runs(self, *, limit: int = 50, status: Optional[str] = None) -> list[TeamRun]:
        return self.store.list_runs(limit=limit, status=status)

    def _team(self, run: TeamRun) -> TeamDefinition:
        return TeamDefinition(**(run.definition or {"id": run.team_id, "name": run.name}))

    def _effective_tasks(self, run: TeamRun, manager: Any) -> dict[str, str]:
        """subtask_id -> the task that currently represents it (repair overrides)."""
        effective = dict(run.subtask_task_ids)
        for task_id in run.repair_task_ids:
            try:
                task = manager.get_task(task_id)
            except Exception:  # noqa: BLE001
                continue
            subtask_id = (task.metadata or {}).get("repairFor")
            if subtask_id:
                effective[subtask_id] = task_id
        return effective

    def status(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        manager = self._task_manager()
        effective = self._effective_tasks(run, manager)
        subtasks: list[dict[str, Any]] = []
        for subtask_id, task_id in effective.items():
            try:
                task = manager.get_task(task_id)
            except Exception:  # noqa: BLE001
                continue
            subtasks.append({
                "subtaskId": subtask_id, "taskId": task_id,
                "agentId": task.assigned_agent_id, "status": task.status.value,
                "title": task.title, "error": task.error,
            })
        return {
            "team": run.model_dump(by_alias=True),
            "subtasks": subtasks,
            "repairTaskIds": list(run.repair_task_ids),
        }

    def _statuses(self, run: TeamRun, manager: Any) -> dict[str, TeamSubtaskStatus]:
        out: dict[str, TeamSubtaskStatus] = {}
        for subtask_id, task_id in self._effective_tasks(run, manager).items():
            try:
                task = manager.get_task(task_id)
            except Exception:  # noqa: BLE001
                out[subtask_id] = TeamSubtaskStatus.PENDING
                continue
            out[subtask_id] = map_task_status(task.status)
        return out

    def _outputs(self, run: TeamRun, manager: Any) -> dict[str, str]:
        out: dict[str, str] = {}
        for subtask_id, task_id in self._effective_tasks(run, manager).items():
            try:
                task = manager.get_task(task_id)
            except Exception:  # noqa: BLE001
                continue
            out[subtask_id] = str(task.output_reference or "")
        return out

    def _collect_findings(self, run: TeamRun) -> list[TeamFinding]:
        """Gather structured findings recorded for this run's root run id."""
        a2a = self._ensure_a2a()
        task_to_subtask = {tid: sid for sid, tid in run.subtask_task_ids.items()}
        findings: list[TeamFinding] = []
        try:
            results = a2a.store.list_results(run_id=run.root_run_id, limit=500)
        except Exception:  # noqa: BLE001
            results = []
        for row in results:
            payload = row.get("result") or {}
            task_id = row.get("taskId")
            agent_id = row.get("agentId") or ""
            for raw in payload.get("findings") or []:
                if not isinstance(raw, dict) or not raw.get("claim"):
                    continue
                findings.append(TeamFinding(
                    id=str(raw.get("id") or ("fnd_" + uuid.uuid4().hex[:12])),
                    subtask_id=task_to_subtask.get(task_id),
                    task_id=task_id, agent_id=agent_id,
                    claim=str(raw["claim"])[:2_000],
                    confidence=float(raw.get("confidence") or 0.5),
                    evidence_refs=[str(r) for r in raw.get("evidenceRefs") or raw.get("evidence_refs") or []],
                    source_refs=[str(r) for r in raw.get("sourceRefs") or raw.get("source_refs") or []],
                    timestamp=(str(raw["timestamp"]) if raw.get("timestamp") is not None else None),
                    assumptions=[str(a) for a in raw.get("assumptions") or []],
                ))
        try:
            messages = a2a.store.list_messages(run_id=run.root_run_id, limit=1000)
        except Exception:  # noqa: BLE001
            messages = []
        for envelope in messages:
            if str(getattr(envelope, "type", "")).upper() not in ("MESSAGETYPE.FINDING", "FINDING"):
                continue
            payload = getattr(envelope, "payload", {}) or {}
            if not payload.get("claim"):
                continue
            findings.append(TeamFinding(
                id="fnd_" + uuid.uuid4().hex[:12],
                subtask_id=task_to_subtask.get(getattr(envelope, "task_id", None)),
                task_id=getattr(envelope, "task_id", None),
                agent_id=getattr(envelope, "sender_agent_id", "") or "",
                claim=str(payload["claim"])[:2_000],
                confidence=float(payload.get("confidence") or 0.5),
                evidence_refs=[str(r) for r in getattr(envelope, "evidence_refs", []) or []],
            ))
        # A recorded A2AResult already publishes one FINDING envelope per finding;
        # dedupe by (agent, claim) so the same claim is never counted twice.
        deduped: dict[tuple[str, str], TeamFinding] = {}
        for finding in findings:
            deduped.setdefault((finding.agent_id, finding.claim.strip()), finding)
        return list(deduped.values())

    # ── review + repair ──────────────────────────────────────────────────────────

    async def finalize(self, run_id: str, *, reviewer_agent_id: str = "qa-agent") -> dict[str, Any]:
        """Reconcile conflicts, review the result, and (bounded) queue repairs."""
        run = self.get_run(run_id)
        manager = self._task_manager()
        statuses = self._statuses(run, manager)
        if not all(status in SUBTASK_TERMINAL for status in statuses.values()):
            return {"status": "running", "teamRunId": run.id, "subtaskStatuses":
                    {k: v.value for k, v in statuses.items()}}

        team = self._team(run)
        findings = self._collect_findings(run)
        recon: ReconcileResult = reconcile(findings, evidence_exists=self._evidence_exists())

        failed_required = [
            s for s in team.subtasks
            if s.required and statuses.get(s.id) is not TeamSubtaskStatus.COMPLETED
        ]
        producers = {
            manager.get_task(tid).assigned_agent_id or ""
            for tid in run.subtask_task_ids.values()
        }

        report: Any = None
        if team.policy.require_review:
            report = review(ReviewInput(
                subtasks=team.subtasks, statuses=statuses, outputs=self._outputs(run, manager),
                findings=findings, conflicts=recon.conflicts,
                reviewer_agent_id=reviewer_agent_id, producer_agent_ids=producers,
                strictness=team.policy.review_strictness,
                optional_failure_policy=team.policy.optional_failure_policy,
                max_repair_attempts=MAX_REPAIR_ATTEMPTS,
            ), attempts=run.attempts)

        outcome_value = report.outcome.value if report is not None else None

        # ── repair path ──────────────────────────────────────────────────────────
        if report is not None and report.outcome.value == "REVISION_REQUIRED":
            signature = repeat_signature(report)
            if signature == run.last_review_signature:
                run.repeat_count += 1
            else:
                run.repeat_count = 0
                run.last_review_signature = signature
            if run.repeat_count >= 1 or run.attempts >= MAX_REPAIR_ATTEMPTS:
                # A repeated or exhausted repair is terminated honestly.
                run.status = TeamRunStatus.PARTIAL if recon.unresolved else TeamRunStatus.FAILED
                run.error = "repair did not resolve the blocking findings; stopped after " \
                            f"{run.attempts} attempt(s)"
                return self._finish(run, report, recon, findings)

            created = self._queue_repairs(run, manager, team, statuses, report)
            if created:
                run.attempts += 1
                run.status = TeamRunStatus.REPAIRING
                # A failed required task fails the plan; the scheduler refuses to
                # dispatch under a terminal plan, so reopen it for the repairs.
                self._resume_plan_for_repairs(run, manager)
                self.store.save_run(run)
                self._publish(run, "team.repair", {"taskIds": created, "attempt": run.attempts})
                return {
                    "status": "repairing", "teamRunId": run.id, "repairTaskIds": created,
                    "review": report.model_dump(by_alias=True),
                    "conflicts": [c.model_dump(by_alias=True) for c in recon.conflicts],
                }
            # Nothing repairable was found: fall through to a terminal verdict.
            run.status = TeamRunStatus.PARTIAL if recon.unresolved else TeamRunStatus.FAILED
            return self._finish(run, report, recon, findings)

        return self._finish(run, report, recon, findings, failed_required=failed_required)

    def _resume_plan_for_repairs(self, run: TeamRun, manager: Any) -> None:
        """Reopen a FAILED/BLOCKED plan so queued repair tasks can be dispatched."""
        if not run.plan_id:
            return
        from ..tasks.model import PlanStatus  # noqa: PLC0415
        from ..tasks.state import TaskOperation  # noqa: PLC0415

        try:
            plan = manager.get_plan(run.plan_id)
        except Exception:  # noqa: BLE001
            return
        if plan.status in (PlanStatus.FAILED, PlanStatus.BLOCKED):
            manager.set_plan_status(run.plan_id, PlanStatus.READY,
                                    operation=TaskOperation.RETRY.value)
            manager.start_plan(run.plan_id)

    def _queue_repairs(
        self, run: TeamRun, manager: Any, team: TeamDefinition,
        statuses: dict[str, TeamSubtaskStatus], report: Any,
    ) -> list[str]:
        from ..tasks.model import CreateTaskInput  # noqa: PLC0415

        created: list[str] = []
        for subtask_id, instruction in repair_plan(report):
            orig_task_id = run.subtask_task_ids.get(subtask_id)
            if not orig_task_id:
                continue
            try:
                orig = manager.get_task(orig_task_id)
            except Exception:  # noqa: BLE001
                continue
            member = self._member_for(team, orig.assigned_agent_id or "")
            try:
                # A repair REPLACES the failed attempt: it must not depend on the
                # failed original (a failed prerequisite would block it forever).
                repair = manager.create_task(CreateTaskInput(
                    title=f"Repair {subtask_id}"[:300],
                    objective=instruction[:4_000] or f"Repair {subtask_id}",
                    plan_id=run.plan_id, assigned_agent_id=orig.assigned_agent_id,
                    metadata={
                        "team": True, "teamRunId": run.id, "repairFor": subtask_id,
                        "repairsTaskId": orig_task_id,
                        "instruction": instruction[:2_000],
                        "maxConcurrency": member.max_concurrency if member else 1,
                    },
                ), actor_id=run.id)
                created.append(repair.id)
                run.repair_task_ids.append(repair.id)
            except Exception:  # noqa: BLE001 - a repair that cannot be queued is disclosed
                log.warning("could not queue repair for %s", subtask_id, exc_info=True)
        return created

    def _finish(
        self, run: TeamRun, report: Any, recon: ReconcileResult, findings: list[TeamFinding],
        *, failed_required: Optional[list[TeamSubtask]] = None,
    ) -> dict[str, Any]:
        outcome = report.outcome.value if report is not None else None
        if run.status is TeamRunStatus.REPAIRING:  # not overwritten by a terminal verdict
            run.status = TeamRunStatus.FAILED
        if report is not None:
            if outcome in ("APPROVED",):
                run.status = TeamRunStatus.COMPLETED
            elif outcome == "APPROVED_WITH_LIMITATIONS":
                run.status = TeamRunStatus.COMPLETED if not recon.unresolved else TeamRunStatus.PARTIAL
            else:  # REJECTED / UNABLE_TO_VERIFY
                run.status = TeamRunStatus.PARTIAL if recon.unresolved else TeamRunStatus.FAILED
        else:
            if failed_required:
                run.status = TeamRunStatus.FAILED
            elif recon.unresolved:
                run.status = TeamRunStatus.PARTIAL
            else:
                run.status = TeamRunStatus.COMPLETED
        run.finished_at = now_iso()
        self.store.save_run(run)
        self._publish(run, "team.completed", {
            "status": run.status.value, "reviewOutcome": outcome,
            "conflicts": len(recon.conflicts),
        })
        return {
            "status": run.status.value, "teamRunId": run.id, "planId": run.plan_id,
            "review": report.model_dump(by_alias=True) if report is not None else None,
            "reviewOutcome": outcome,
            "conflicts": [c.model_dump(by_alias=True) for c in recon.conflicts],
            "unresolvedConflicts": [c.model_dump(by_alias=True) for c in recon.unresolved],
            "unsupportedFindingIds": [f.id for f in recon.unsupported],
            "findings": [f.model_dump(by_alias=True) for f in findings],
        }

    # ── synthesis + cancellation ───────────────────────────────────────────────

    def synthesize(self, run_id: str) -> str:
        """A deterministic final answer from validated results (no chain-of-thought)."""
        run = self.get_run(run_id)
        manager = self._task_manager()
        team = self._team(run)
        statuses = self._statuses(run, manager)
        findings = self._collect_findings(run)
        recon = reconcile(findings, evidence_exists=self._evidence_exists())

        lines = [f"Team: {team.name}", f"Objective: {team.objective}", ""]
        for subtask in team.subtasks:
            status = statuses.get(subtask.id, TeamSubtaskStatus.PENDING).value
            agent = subtask.assigned_agent_id or "(capability-routed)"
            lines.append(f"- [{status}] {subtask.id} → {agent}: {subtask.objective[:200]}")
        if recon.supported:
            lines.append("")
            lines.append("Supported findings:")
            lines.extend(f"  • {f.claim} (evidence: {', '.join(f.evidence_refs) or 'none'})"
                         for f in recon.supported)
        if recon.unresolved:
            lines.append("")
            lines.append("Unresolved conflicts (disclosed, not averaged):")
            lines.extend(f"  ! {c.subject}: {c.detail or c.kind.value}" for c in recon.unresolved)
        if recon.unsupported:
            lines.append("")
            lines.append("Unsupported claims (no verifiable evidence):")
            lines.extend(f"  ? {f.claim}" for f in recon.unsupported)
        lines.append("")
        lines.append(f"Team status: {run.status.value}")
        return "\n".join(lines)[:20_000]

    async def cancel(self, run_id: str, *, reason: str = "cancelled by operator") -> dict[str, Any]:
        run = self.get_run(run_id)
        manager = self._task_manager()
        cancelled: list[str] = []
        for task_id in list(run.subtask_task_ids.values()) + list(run.repair_task_ids):
            try:
                manager.cancel_task(task_id, reason=reason, cascade=True)
                cancelled.append(task_id)
            except Exception:  # noqa: BLE001 - a terminal/missing task is not fatal
                continue
        run.status = TeamRunStatus.CANCELLED
        run.error = reason[:2_000]
        run.finished_at = now_iso()
        self.store.save_run(run)
        self._publish(run, "team.cancelled", {"taskIds": cancelled})
        return {"teamRunId": run.id, "cancelledTaskIds": cancelled}

    async def wait(self, run_id: str, *, timeout_s: float = 600.0, poll_s: float = 0.5) -> TeamRun:
        """Await all subtask/repair tasks reaching a terminal state."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while True:
            run = self.get_run(run_id)
            statuses = self._statuses(run, self._task_manager())
            if statuses and all(status in SUBTASK_TERMINAL for status in statuses.values()):
                return run
            if loop.time() >= deadline:
                return run
            await asyncio.sleep(poll_s)


__all__ = [
    "TEAM_ERROR",
    "TEAM_INVALID",
    "TEAM_NO_AGENT",
    "TEAM_NOT_FOUND",
    "TEAM_UNAVAILABLE",
    "TeamError",
    "TeamService",
]
