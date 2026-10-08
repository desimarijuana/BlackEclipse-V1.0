"""The orchestration engine: dependency-aware scheduling and a worker pool.

The engine owns exactly one execution plane for parallel work. It validates the
DAG, computes the critical path, then drives a scheduler that runs every node
whose dependencies are satisfied concurrently, bounded by resource limits and
priority. It persists through `OrchestrationStore`, publishes on the runtime's
event bus, coalesces compatible nodes into batches, and can recover an interrupted
execution after a crash — including parking agent work until credentials arrive.

Concurrency model: one asyncio coordinator per execution. The coordinator never
blocks on a single node — it launches what fits, then waits on either a node
completion, a resource release, or cancellation. All shared state is mutated in
the single event-loop thread, so the "lock" is the cooperative scheduler itself.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import batching
from .cache import (
    MISS,
    SharedResultCache,
    compute_dedup_key,
    fingerprint,
    is_miss,
)
from .events import (
    EXECUTION_CANCELLED,
    EXECUTION_COMPLETED,
    EXECUTION_CREATED,
    EXECUTION_FAILED,
    EXECUTION_PARTIAL,
    EXECUTION_PAUSED,
    EXECUTION_RESUMED,
    EXECUTION_RETRY_ROUND,
    EXECUTION_STARTED,
    TASK_BLOCKED,
    TASK_CANCELLED,
    TASK_COMPLETED,
    TASK_CREATED,
    TASK_FAILED,
    TASK_READY,
    TASK_RETRYING,
    TASK_SKIPPED,
    TASK_STARTED,
    TASK_TIMEOUT,
)
from .graph import (
    GraphValidationError,
    Readiness,
    can_add_edge,
    can_add_node,
    critical_path,
    evaluate_readiness,
    ready_node_ids,
    validate_graph,
)
from .models import (
    ExecutionGraph,
    ExecutionNode,
    ExecutionResult,
    ExecutionStatus,
    FailurePolicy,
    JoinConfig,
    JoinPolicy,
    NodeError,
    NodeKind,
    NodeOutcome,
    Priority,
    ResourceRequirements,
    RetryPolicy,
    TaskStatus,
    new_execution_id,
    new_node_id,
    now,
)
from .resources import DEFAULT_LEASE_TTL_MS, RateLimiter, ResourceManager, limits_from_env
from .retry import backoff_ms, should_retry
from .runner import DefaultNodeRunner, NodeRunner, RuntimeContext

log = logging.getLogger("harness.orchestration.engine")


@dataclass
class EngineConfig:
    """Operational configuration. Defaults are safe for a desktop app."""

    max_concurrency: int = field(default_factory=lambda: limits_from_env()["global"])
    lease_ttl_ms: int = DEFAULT_LEASE_TTL_MS
    default_timeout_ms: int = 120_000
    retry_failed_rounds: int = 1
    critical_path_priority: bool = True
    heartbeat_interval_s: float = 5.0
    # "execution" (default) keeps identical work isolated to one execution;
    # "engine" lets nodes with a `dedupScope: engine` (or this default) share one
    # run process-wide. Sharing is always scoped by authorization (see cache.py).
    dedup_scope: str = "execution"
    limits: dict[str, int] = field(default_factory=limits_from_env)

    @classmethod
    def from_env(cls, **overrides: Any) -> "EngineConfig":
        config = cls()
        for key, value in overrides.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)
        return config


@dataclass
class _Execution:
    graph: ExecutionGraph
    runtime: Optional[RuntimeContext] = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    running: dict[str, asyncio.Task] = field(default_factory=dict)
    dedup: dict[str, asyncio.Future] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    critical: list[str] = field(default_factory=list)
    critical_ms: int = 0
    result: Optional[ExecutionResult] = None
    driver: Optional[asyncio.Task] = None
    heartbeat: Optional[asyncio.Task] = None
    retry_rounds: int = 0
    user_cancelled: bool = False

    def __post_init__(self) -> None:
        self.resume_event.set()


class OrchestrationEngine:
    """Create, schedule, execute, cancel and recover DAG executions."""

    def __init__(
        self,
        store: Any,
        runtime: RuntimeContext,
        *,
        runner: Optional[NodeRunner] = None,
        config: Optional[EngineConfig] = None,
        resource_manager: Optional[ResourceManager] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        self.store = store
        self.runtime = runtime
        self._runner = runner or DefaultNodeRunner(runtime)
        self.config = config or EngineConfig()
        self._resources = resource_manager or ResourceManager(limits=self.config.limits)
        self.rate_limiter = rate_limiter or RateLimiter()
        self._executions: dict[str, _Execution] = {}
        self._cache = SharedResultCache()
        self._inflight: dict[str, asyncio.Future] = {}
        self._callables: dict[str, Callable[..., Any]] = dict(runtime.callables)
        if hasattr(self._resources, "limits"):
            self._resources.limits.setdefault("global", self.config.max_concurrency)

    # ── construction ───────────────────────────────────────────────────────────

    def register_callable(self, name: str, fn: Callable[..., Any]) -> None:
        self._callables[str(name)] = fn
        self.runtime.callables[str(name)] = fn

    def set_runtime(self, runtime: RuntimeContext) -> None:
        """Replace the default runtime (e.g. after boot supplies credentials)."""
        self.runtime = runtime
        self._callables.update(runtime.callables)

    def create_execution(
        self,
        root_task_id: str = "",
        *,
        failure_policy: FailurePolicy | str = FailurePolicy.CONTINUE,
        quorum: int = 0,
        max_concurrency: int = 0,
        metadata: Optional[dict[str, Any]] = None,
        execution_id: Optional[str] = None,
    ) -> ExecutionGraph:
        graph = ExecutionGraph(
            id=execution_id or new_execution_id(),
            root_task_id=root_task_id,
            failure_policy=_as_failure_policy(failure_policy),
            quorum=max(0, int(quorum)),
            max_concurrency=max(0, int(max_concurrency)),
            metadata=dict(metadata or {}),
        )
        self.store.save_execution(graph)
        self._emit(graph.id, EXECUTION_CREATED, {"rootTaskId": root_task_id})
        return graph

    def create_task(
        self,
        execution_id: str,
        *,
        kind: NodeKind | str,
        node_id: Optional[str] = None,
        input: Optional[dict[str, Any]] = None,  # noqa: A002 - mirrors the contract
        dependencies: Optional[list[str]] = None,
        priority: Priority | str = Priority.NORMAL,
        retry: Optional[RetryPolicy | dict[str, Any]] = None,
        timeout_ms: Optional[int] = None,
        resources: Optional[ResourceRequirements | dict[str, Any]] = None,
        join: Optional[JoinConfig | dict[str, Any]] = None,
        dedup_key: Optional[str] = None,
        dedup: Optional[bool] = None,
        cacheable: bool = False,
        cache_ttl_ms: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ExecutionNode:
        graph = self._load(execution_id)
        node = ExecutionNode(
            id=node_id or new_node_id(),
            execution_id=execution_id,
            kind=_as_node_kind(kind),
            input=dict(input or {}),
            priority=_as_priority(priority),
            retry=retry if isinstance(retry, RetryPolicy) else RetryPolicy.from_dict(retry),
            timeout_ms=int(timeout_ms or self.config.default_timeout_ms),
            resources=(resources if isinstance(resources, ResourceRequirements)
                       else ResourceRequirements.from_dict(resources)),
            join=(join if isinstance(join, JoinConfig) else JoinConfig.from_dict(join)),
            metadata=dict(metadata or {}),
            cacheable=bool(cacheable),
            cache_ttl_ms=max(0, int(cache_ttl_ms)),
        )
        if dedup_key is None and dedup is not False:
            if dedup is True or node.kind in (NodeKind.TOOL, NodeKind.FUNCTION):
                node.dedup_key = compute_dedup_key(node)
        elif dedup_key is not None:
            node.dedup_key = str(dedup_key)
        for dep in dependencies or []:
            if dep not in graph.nodes:
                raise GraphValidationError([f"node {node.id!r} depends on missing node {dep!r}"])
            node.dependencies.append(dep)
        can_add_node(graph, node)
        graph.add_node(node)
        for dep in node.dependencies:
            graph.nodes[dep].dependents.append(node.id)
        self.store.save_node(node)
        self.store.save_execution(graph)
        for dep in node.dependencies:
            self.store.save_edge(execution_id, dep, node.id)
            self.store.save_node(graph.nodes[dep])
        self._emit(execution_id, TASK_CREATED, {"nodeId": node.id, "kind": node.kind.value},
                   node_id=node.id)
        return node

    def add_dependency(self, execution_id: str, node_id: str, depends_on: str) -> None:
        graph = self._load(execution_id)
        can_add_edge(graph, depends_on, node_id)
        graph.add_edge(depends_on, node_id)
        self.store.save_node(graph.nodes[node_id])
        self.store.save_node(graph.nodes[depends_on])
        self.store.save_edge(execution_id, depends_on, node_id)
        self.store.save_execution(graph)

    def add_node_runtime(self, execution_id: str, node: ExecutionNode) -> ExecutionNode:
        """Insert a node into a (possibly running) execution, validated.

        Safe against the scheduler because insertion is synchronous within the
        single event-loop thread; the next scheduling pass picks it up.
        """
        ex = self._executions.get(execution_id)
        graph = ex.graph if ex is not None else self._load(execution_id)
        can_add_node(graph, node)
        graph.add_node(node)
        for dep in node.dependencies:
            graph.nodes[dep].dependents.append(node.id)
        self.store.save_node(node)
        for dep in node.dependencies:
            self.store.save_edge(execution_id, dep, node.id)
            self.store.save_node(graph.nodes[dep])
        self.store.save_execution(graph)
        self._emit(execution_id, TASK_CREATED, {"nodeId": node.id, "kind": node.kind.value,
                                                "dynamic": True}, node_id=node.id)
        return node

    def build_graph(self, execution_id: str) -> ExecutionGraph:
        return self._load(execution_id)

    def validate(self, execution_id: str) -> None:
        validate_graph(self._load(execution_id))

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def schedule(self, execution_id: str, *, runtime: Optional[RuntimeContext] = None) -> asyncio.Task:
        ex = self._ensure_started(execution_id, runtime=runtime)
        assert ex.driver is not None
        return ex.driver

    async def execute(self, execution_id: str, *, timeout_ms: Optional[int] = None,
                      runtime: Optional[RuntimeContext] = None) -> ExecutionResult:
        ex = self._ensure_started(execution_id, runtime=runtime)
        if not ex.done.is_set():
            if timeout_ms:
                try:
                    await asyncio.wait_for(ex.done.wait(), timeout=max(0.001, timeout_ms / 1000))
                except asyncio.TimeoutError:
                    await self.cancel(execution_id)
            else:
                await ex.done.wait()
        if ex.result is None:
            ex.result = self._build_result(ex)
        return ex.result

    async def resume_execution(self, execution_id: str, *, runtime: Optional[RuntimeContext] = None,
                               timeout_ms: Optional[int] = None) -> ExecutionResult:
        """Resume a paused/parked execution, optionally with fresh credentials."""
        ex = self._executions.get(execution_id)
        if ex is not None and not ex.done.is_set() and ex.graph.status is ExecutionStatus.PAUSED:
            if runtime is not None:
                ex.runtime = runtime
            await self.resume(execution_id)
            return await self.execute(execution_id, timeout_ms=timeout_ms)
        return await self.execute(execution_id, timeout_ms=timeout_ms, runtime=runtime)

    async def _run(self, execution_id: str) -> None:
        await self._drive(self._executions[execution_id])

    def _ensure_started(self, execution_id: str, *, runtime: Optional[RuntimeContext] = None) -> _Execution:
        existing = self._executions.get(execution_id)
        if existing is not None:
            if runtime is not None:
                existing.runtime = runtime
            return existing
        graph = self._load(execution_id)
        validate_graph(graph)
        ex = _Execution(graph=graph, runtime=runtime)
        self._executions[execution_id] = ex
        ex.driver = asyncio.ensure_future(self._run(execution_id))
        return ex

    async def run_graph(self, graph: ExecutionGraph, *, timeout_ms: Optional[int] = None,
                        runtime: Optional[RuntimeContext] = None) -> ExecutionResult:
        validate_graph(graph)
        self.store.save_execution(graph)
        self.store.save_nodes(graph)
        for from_id, to_id in graph.edges():
            self.store.save_edge(graph.id, from_id, to_id)
        return await self.execute(graph.id, timeout_ms=timeout_ms, runtime=runtime)

    async def cancel(self, execution_id: str) -> bool:
        ex = self._executions.get(execution_id)
        if ex is None:
            graph = self.store.get_execution(execution_id)
            if graph is None:
                return False
            if graph.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
                                ExecutionStatus.CANCELLED, ExecutionStatus.PARTIAL_SUCCESS):
                return graph.status is ExecutionStatus.CANCELLED
            self.store.update_execution(execution_id, status=ExecutionStatus.CANCELLED, completedAt=now())
            self._emit(execution_id, EXECUTION_CANCELLED, {"recovered": True})
            return True
        if ex.graph.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
                               ExecutionStatus.CANCELLED, ExecutionStatus.PARTIAL_SUCCESS):
            return ex.graph.status is ExecutionStatus.CANCELLED
        ex.user_cancelled = True
        ex.cancel_event.set()
        for task in list(ex.running.values()):
            task.cancel()
        await ex.done.wait()
        return True

    async def shutdown(self) -> None:
        for ex in list(self._executions.values()):
            if ex.done.is_set():
                continue
            ex.user_cancelled = True
            ex.cancel_event.set()
            for task in list(ex.running.values()):
                task.cancel()
            if ex.driver is not None:
                ex.driver.cancel()

    async def pause(self, execution_id: str) -> bool:
        ex = self._executions.get(execution_id)
        if ex is None or ex.done.is_set():
            return False
        ex.resume_event.clear()
        return True

    async def resume(self, execution_id: str) -> bool:
        ex = self._executions.get(execution_id)
        if ex is None or ex.done.is_set():
            return False
        ex.resume_event.set()
        return True

    async def retry_node(self, execution_id: str, node_id: str, *,
                         runtime: Optional[RuntimeContext] = None) -> bool:
        ex = self._executions.get(execution_id)
        if ex is None or ex.done.is_set():
            graph = self._load(execution_id)
            node = graph.nodes.get(node_id)
            if node is None or node.status not in (TaskStatus.FAILED, TaskStatus.TIMED_OUT,
                                                   TaskStatus.SKIPPED, TaskStatus.BLOCKED):
                return False
            self._reset_node(node)
            self.store.save_node(node)
            self.store.update_execution(execution_id, status=ExecutionStatus.RUNNING)
            new_ex = _Execution(graph=graph, runtime=runtime)
            self._executions[execution_id] = new_ex
            new_ex.driver = asyncio.ensure_future(self._run(execution_id))
            return True
        node = ex.graph.nodes.get(node_id)
        if node is None or node.status not in (TaskStatus.FAILED, TaskStatus.TIMED_OUT,
                                               TaskStatus.SKIPPED, TaskStatus.BLOCKED):
            return False
        if runtime is not None:
            ex.runtime = runtime
        self._reset_node(node)
        if node.dedup_key:
            ex.dedup.pop(node.dedup_key, None)
        self.store.save_node(node)
        return True

    # ── queries ────────────────────────────────────────────────────────────────

    def get_status(self, execution_id: str) -> Optional[dict[str, Any]]:
        from .graph import graph_summary

        ex = self._executions.get(execution_id)
        graph = ex.graph if ex is not None else self.store.get_execution(execution_id)
        if graph is None:
            return None
        summary = graph_summary(graph)
        summary["active"] = ex is not None and not ex.done.is_set()
        summary["running"] = sorted(ex.running.keys()) if ex is not None else []
        summary["nodeCounts"] = summary.pop("byStatus", {})
        summary["awaitingRuntime"] = bool(graph.metadata.get("awaitingRuntime"))
        summary["nodes"] = [n.to_dict() for n in graph.nodes.values()]
        summary["timeline"] = list(ex.timeline) if ex is not None else []
        return summary

    def get_graph(self, execution_id: str) -> Optional[dict[str, Any]]:
        ex = self._executions.get(execution_id)
        graph = ex.graph if ex is not None else self.store.get_execution(execution_id)
        return graph.to_dict() if graph is not None else None

    def get_result(self, execution_id: str) -> Optional[ExecutionResult]:
        ex = self._executions.get(execution_id)
        if ex is not None and ex.result is not None:
            return ex.result
        graph = self.store.get_execution(execution_id)
        if graph is None:
            return None
        return self._build_result_for_graph(graph)

    def list_executions(self, *, limit: int = 100, status: Optional[str] = None) -> list[dict[str, Any]]:
        return self.store.list_executions(limit=limit, status=status)

    def resources(self) -> dict[str, Any]:
        return self._resources.snapshot()

    def summary(self) -> dict[str, Any]:
        active = [eid for eid, ex in self._executions.items() if not ex.done.is_set()]
        return {
            "activeExecutions": active,
            "executionCount": len(self._executions),
            "inflightDedup": len(self._inflight),
            "resources": self._resources.snapshot(),
            "maxConcurrency": self.config.max_concurrency,
            "dedupScope": self.config.dedup_scope,
        }

    # ── recovery ───────────────────────────────────────────────────────────────

    async def recover(self, runtime: Optional[RuntimeContext] = None, *,
                      timeout_ms: Optional[int] = None) -> list[str]:
        from .recovery import recover_engine

        return await recover_engine(self, runtime, timeout_ms=timeout_ms)

    async def _finalize_recovered(self, graph: ExecutionGraph) -> None:
        self._executions.pop(graph.id, None)
        self._finalize(_Execution(graph=graph))

    # ── the scheduler ──────────────────────────────────────────────────────────

    async def _drive(self, ex: _Execution) -> None:
        graph = ex.graph
        try:
            if graph.status in (ExecutionStatus.PENDING, ExecutionStatus.READY):
                graph.status = ExecutionStatus.READY
                self.store.update_execution(graph.id, status=graph.status)
                graph.status = ExecutionStatus.RUNNING
            elif graph.status is ExecutionStatus.PAUSED:
                graph.status = ExecutionStatus.RUNNING
            if graph.metadata.pop("awaitingRuntime", None) is not None:
                self.store.update_execution(graph.id, metadata=graph.metadata)
            graph.started_at = graph.started_at or now()
            self.store.update_execution(graph.id, status=ExecutionStatus.RUNNING, startedAt=graph.started_at)
            ex.critical, ex.critical_ms = critical_path(graph)
            ex.heartbeat = asyncio.ensure_future(self._heartbeat_loop(ex))
            self._emit(graph.id, EXECUTION_STARTED, {
                "totalTasks": len(graph.nodes), "criticalPath": ex.critical,
            })

            while True:
                if ex.cancel_event.is_set():
                    break
                if not ex.resume_event.is_set():
                    graph.status = ExecutionStatus.PAUSED
                    self.store.update_execution(graph.id, status=graph.status)
                    self._emit(graph.id, EXECUTION_PAUSED, {})
                    await ex.resume_event.wait()
                    if ex.cancel_event.is_set():
                        break
                    graph.status = ExecutionStatus.RUNNING
                    self.store.update_execution(graph.id, status=graph.status)
                    self._emit(graph.id, EXECUTION_RESUMED, {})

                self._launch_ready(ex)

                if ex.running:
                    await self._wait_any(ex)
                    continue

                if self._all_terminal(graph):
                    if self._maybe_retry_round(ex):
                        continue
                    break

                if self._skip_unrunnable(ex):
                    continue

                if self._has_work(graph):
                    await self._wait_capacity_or_cancel(ex)
                    continue

                self._mark_deadlocked(ex)
                break
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - the coordinator must always finalize
            log.exception("orchestration driver crashed for %s", graph.id)
            self._emit(graph.id, EXECUTION_FAILED, {"error": "driver_crash"})
        finally:
            if ex.heartbeat is not None:
                ex.heartbeat.cancel()
            for task in list(ex.running.values()):
                task.cancel()
            if ex.running:
                await asyncio.gather(*ex.running.values(), return_exceptions=True)
                ex.running.clear()
            if graph.status is ExecutionStatus.PAUSED:
                graph.status = ExecutionStatus.RUNNING
            self._finalize(ex)
            ex.done.set()

    def _launch_ready(self, ex: _Execution) -> None:
        graph = ex.graph
        ready: list[ExecutionNode] = []
        for node in graph.nodes.values():
            if node.id in ex.running:
                continue
            if node.status is TaskStatus.PENDING and evaluate_readiness(node, graph) is Readiness.READY:
                ready.append(node)
            elif node.status is TaskStatus.READY:
                ready.append(node)
        if not ready:
            return
        ready.sort(key=lambda n: self._order_key(ex, n))
        batches, _singles = batching.plan_batches(ready)
        group_of: dict[str, list[ExecutionNode]] = {}
        for group in batches:
            for member in group:
                group_of[member.id] = group
        launched_groups: set[int] = set()

        for node in ready:
            if ex.cancel_event.is_set():
                return
            group = group_of.get(node.id)
            if group is not None:
                gid = id(group)
                if gid in launched_groups:
                    continue
                launched_groups.add(gid)
                if graph.max_concurrency and len(ex.running) >= graph.max_concurrency:
                    continue
                reqs = batching.merged_requirements(group)
                for member in group:
                    self._mark_ready(ex, member)
                if not self._resources.try_acquire(reqs):
                    continue
                task = asyncio.ensure_future(batching.run_batch(self, ex, group, reqs))
                for member in group:
                    ex.running[member.id] = task
                continue
            if graph.max_concurrency and len(ex.running) >= graph.max_concurrency:
                return
            self._mark_ready(ex, node)
            cached = self._cache_get(ex, node)
            if not is_miss(cached):
                self._settle_node(ex, node, NodeOutcome(output=cached))
                continue
            registry, key = self._dedup_registry(ex, node)
            share = bool(key) and key in registry
            owner = False
            pop_on_resolve = False
            reqs: dict[str, int] = {}
            if not share:
                reqs = node.resources.effective()
                if not self._resources.try_acquire(reqs):
                    continue
                if key and key not in registry:
                    registry[key] = asyncio.get_running_loop().create_future()
                    owner = True
                    pop_on_resolve = registry is self._inflight
            node.worker_id = self._worker_id()
            self._set_task_status(node, TaskStatus.RUNNING)
            node.started_at = node.started_at or now()
            lease_id = self.store.acquire_lease(graph.id, node.id, node.worker_id, self.config.lease_ttl_ms)
            node.metadata["_leaseId"] = lease_id
            self.store.save_node(node)
            self._emit(graph.id, TASK_STARTED, {
                "nodeId": node.id, "kind": node.kind.value, "workerId": node.worker_id,
                "attempt": node.attempt_count + 1,
            }, node_id=node.id)
            dedup = {"registry": registry, "key": key, "owner": owner, "share": share,
                     "pop": pop_on_resolve} if registry is not None else None
            task = asyncio.ensure_future(self._run_node(ex, node, reqs, dedup))
            ex.running[node.id] = task

    def _mark_ready(self, ex: _Execution, node: ExecutionNode) -> None:
        if node.status is TaskStatus.PENDING:
            self._set_task_status(node, TaskStatus.READY)
            node.metadata.setdefault("_ready_at", now())
            self.store.save_node(node)
            self._emit(ex.graph.id, TASK_READY, {"nodeId": node.id}, node_id=node.id)

    async def _run_node(self, ex: _Execution, node: ExecutionNode, reqs: dict[str, int],
                        dedup: Optional[dict[str, Any]]) -> None:
        outcome: NodeOutcome
        try:
            if dedup and dedup["share"]:
                outcome = await self._await_dedup(ex, node, dedup["registry"], dedup["key"])
            else:
                outcome = await self._execute_attempts(ex, node)
                if dedup and dedup["owner"]:
                    fut = dedup["registry"].get(dedup["key"])
                    if fut is not None and not fut.done():
                        fut.set_result(outcome)
                    if dedup["pop"] or outcome.error is not None:
                        dedup["registry"].pop(dedup["key"], None)
            if ex.cancel_event.is_set() and outcome.error is None:
                outcome = NodeOutcome(error=NodeError("CANCELLED", "execution cancelled"))
            self._settle_node(ex, node, outcome)
        except asyncio.CancelledError:
            self._settle_node(ex, node, NodeOutcome(error=NodeError("CANCELLED", "node cancelled")))
        finally:
            if reqs:
                self._resources.release(reqs)
            lease_id = (node.metadata or {}).pop("_leaseId", None)
            if lease_id:
                self.store.release_lease(lease_id)
            ex.running.pop(node.id, None)

    async def _execute_attempts(self, ex: _Execution, node: ExecutionNode) -> NodeOutcome:
        policy = node.retry
        attempts = max(1, int(policy.max_attempts))
        last = NodeOutcome(error=NodeError("NODE_ERROR", "node did not run"))
        for attempt in range(1, attempts + 1):
            if ex.cancel_event.is_set():
                return NodeOutcome(error=NodeError("CANCELLED", "execution cancelled"))
            node.attempt_count = attempt
            started = now()
            self.store.record_attempt(ex.graph.id, node.id, attempt, "RUNNING", started_at=started)
            outcome: Optional[NodeOutcome] = None
            rate_key = node.input.get("rateKey") or node.metadata.get("rateKey")
            if rate_key and not await self.rate_limiter.try_acquire(str(rate_key)):
                outcome = NodeOutcome(error=NodeError(
                    "RATE_LIMITED", f"rate limit exhausted for {rate_key!r}", retryable=True,
                ))
            if outcome is None:
                try:
                    timeout_s = (node.timeout_ms / 1000) if node.timeout_ms else None
                    outcome = await asyncio.wait_for(
                        self._runner.run(node, self._effective_runtime(ex), ex.graph),
                        timeout=timeout_s,
                    )
                    if outcome is None:
                        outcome = NodeOutcome(output=None)
                except asyncio.TimeoutError:
                    outcome = NodeOutcome(error=NodeError(
                        "TASK_TIMEOUT", f"node timed out after {node.timeout_ms}ms", retryable=True,
                    ))
                except asyncio.CancelledError:
                    self.store.record_attempt(
                        ex.graph.id, node.id, attempt, "CANCELLED",
                        error={"code": "CANCELLED", "message": "cancelled"},
                        started_at=started, finished_at=now(),
                    )
                    raise
                except Exception as exc:  # noqa: BLE001 - a runner crash is a node failure
                    code = str(getattr(exc, "code", "NODE_ERROR"))
                    outcome = NodeOutcome(error=NodeError(code, f"{type(exc).__name__}: {exc}",
                                                           retryable=True))

            if outcome.error is None:
                self.store.record_attempt(
                    ex.graph.id, node.id, attempt, "COMPLETED",
                    started_at=started, finished_at=now(),
                )
                self._cache_put(ex, node, outcome.output)
                return outcome
            self.store.record_attempt(
                ex.graph.id, node.id, attempt, "FAILED", error=outcome.error.to_dict(),
                started_at=started, finished_at=now(),
            )
            last = outcome
            if not should_retry(policy, outcome.error, attempt):
                return outcome
            self._emit(ex.graph.id, TASK_RETRYING, {
                "nodeId": node.id, "attempt": attempt, "code": outcome.error.code,
                "nextAttempt": attempt + 1,
            }, node_id=node.id)
            await self._sleep_or_cancel(ex, backoff_ms(policy, attempt))
        return last

    async def _await_dedup(self, ex: _Execution, node: ExecutionNode, registry: dict,
                           key: Optional[str]) -> NodeOutcome:
        fut = registry.get(key) if key else None
        if fut is None:
            return await self._execute_attempts(ex, node)
        try:
            timeout_s = (node.timeout_ms / 1000) if node.timeout_ms else None
            outcome = await asyncio.wait_for(asyncio.shield(fut), timeout=timeout_s)
        except asyncio.TimeoutError:
            return NodeOutcome(error=NodeError("TASK_TIMEOUT", "deduplicated node timed out", retryable=True))
        except asyncio.CancelledError:
            raise
        return outcome if isinstance(outcome, NodeOutcome) else NodeOutcome(output=outcome)

    def _settle_node(self, ex: _Execution, node: ExecutionNode, outcome: NodeOutcome) -> None:
        graph = ex.graph
        if node.terminal:
            return
        error = outcome.error
        if error is not None and error.code == "CANCELLED":
            target = TaskStatus.CANCELLED
        elif error is not None and error.code == "TASK_TIMEOUT":
            target = TaskStatus.TIMED_OUT
        elif error is not None:
            target = TaskStatus.FAILED
        else:
            target = TaskStatus.COMPLETED
        if node.status is not TaskStatus.RUNNING:
            self._set_task_status(node, TaskStatus.RUNNING)
        self._set_task_status(node, target)
        node.completed_at = now()
        node.output = outcome.output if target is TaskStatus.COMPLETED else node.output
        node.error = error
        self.store.save_node(node)
        self._record_timeline(ex, node, target, error)
        event = {
            TaskStatus.COMPLETED: TASK_COMPLETED,
            TaskStatus.FAILED: TASK_FAILED,
            TaskStatus.TIMED_OUT: TASK_TIMEOUT,
            TaskStatus.CANCELLED: TASK_CANCELLED,
        }[target]
        self._emit(graph.id, event, {
            "nodeId": node.id, "status": target.value, "durationMs": node.duration_ms(),
            "attempts": node.attempt_count,
            "error": error.to_dict() if error else None,
        }, node_id=node.id)
        if target in (TaskStatus.FAILED, TaskStatus.TIMED_OUT):
            if graph.failure_policy is FailurePolicy.FAIL_FAST:
                ex.cancel_event.set()
                for task in list(ex.running.values()):
                    if task is not asyncio.current_task():
                        task.cancel()
        self._apply_join_policies(ex)

    def _apply_join_policies(self, ex: _Execution) -> None:
        graph = ex.graph
        for node in graph.nodes.values():
            if node.status is not TaskStatus.PENDING or node.join is None:
                continue
            if node.join.policy not in (JoinPolicy.ANY, JoinPolicy.FIRST_SUCCESS,
                                        JoinPolicy.QUORUM, JoinPolicy.THRESHOLD):
                continue
            if not node.join.cancel_losers:
                continue
            if evaluate_readiness(node, graph) is not Readiness.READY:
                continue
            for dep_id in node.dependencies:
                dep = graph.nodes.get(dep_id)
                if dep is None or dep.terminal:
                    continue
                if self._exclusively_needed_by(dep_id, node.id, graph):
                    if dep.status in (TaskStatus.PENDING, TaskStatus.READY):
                        self._set_task_status(dep, TaskStatus.CANCELLED)
                        dep.completed_at = now()
                        self.store.save_node(dep)
                        self._emit(graph.id, TASK_CANCELLED, {"nodeId": dep.id, "reason": "join_satisfied"},
                                   node_id=dep.id)
                    elif dep.status is TaskStatus.RUNNING:
                        task = ex.running.get(dep_id)
                        if task is not None:
                            task.cancel()

    def _exclusively_needed_by(self, dep_id: str, join_id: str, graph: ExecutionGraph) -> bool:
        dep = graph.nodes.get(dep_id)
        if dep is None:
            return False
        for dependent_id in dep.dependents:
            if dependent_id == join_id:
                continue
            dependent = graph.nodes.get(dependent_id)
            if dependent is None:
                continue
            if dependent.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING,
                                    TaskStatus.PAUSED):
                if evaluate_readiness(dependent, graph) is not Readiness.SKIPPED:
                    return False
        return True

    def _skip_unrunnable(self, ex: _Execution) -> bool:
        graph = ex.graph
        changed = False
        for node in list(graph.nodes.values()):
            if node.status is not TaskStatus.PENDING and node.status is not TaskStatus.READY:
                continue
            if node.status is TaskStatus.RUNNING or node.id in ex.running:
                continue
            if evaluate_readiness(node, graph) is Readiness.SKIPPED:
                if node.status is TaskStatus.PENDING:
                    self._set_task_status(node, TaskStatus.READY)
                self._set_task_status(node, TaskStatus.SKIPPED)
                node.completed_at = now()
                self.store.save_node(node)
                self._record_timeline(ex, node, TaskStatus.SKIPPED, None)
                self._emit(graph.id, TASK_SKIPPED, {"nodeId": node.id}, node_id=node.id)
                changed = True
        return changed

    def _mark_deadlocked(self, ex: _Execution) -> None:
        graph = ex.graph
        for node in graph.nodes.values():
            if node.status in (TaskStatus.PENDING, TaskStatus.READY):
                self._set_task_status(node, TaskStatus.BLOCKED)
                node.completed_at = now()
                self.store.save_node(node)
                self._record_timeline(ex, node, TaskStatus.BLOCKED, None)
                self._emit(graph.id, TASK_BLOCKED, {"nodeId": node.id}, node_id=node.id)

    def _maybe_retry_round(self, ex: _Execution) -> bool:
        graph = ex.graph
        if graph.failure_policy is not FailurePolicy.RETRY_FAILED:
            return False
        if ex.retry_rounds >= self.config.retry_failed_rounds:
            return False
        retryable = [n for n in graph.nodes.values()
                     if n.status in (TaskStatus.FAILED, TaskStatus.TIMED_OUT)]
        if not retryable:
            return False
        ex.retry_rounds += 1
        for node in graph.nodes.values():
            if node.status in (TaskStatus.SKIPPED, TaskStatus.BLOCKED):
                self._set_task_status(node, TaskStatus.PENDING)
                node.completed_at = None
                self.store.save_node(node)
        for node in retryable:
            self._set_task_status(node, TaskStatus.PENDING)
            node.completed_at = None
            if node.dedup_key:
                ex.dedup.pop(node.dedup_key, None)
            self.store.save_node(node)
        self._emit(graph.id, EXECUTION_RETRY_ROUND, {"round": ex.retry_rounds,
                                                     "nodes": [n.id for n in retryable]})
        return True

    async def _wait_any(self, ex: _Execution) -> None:
        if not ex.running:
            return
        waiter = asyncio.ensure_future(ex.cancel_event.wait())
        try:
            await asyncio.wait([*ex.running.values(), waiter],
                               return_when=asyncio.FIRST_COMPLETED)
        finally:
            waiter.cancel()
        if ex.cancel_event.is_set():
            for task in list(ex.running.values()):
                task.cancel()

    async def _wait_capacity_or_cancel(self, ex: _Execution) -> None:
        waiter = asyncio.ensure_future(ex.cancel_event.wait())
        release = asyncio.ensure_future(self._resources.wait_release())
        try:
            await asyncio.wait([waiter, release], return_when=asyncio.FIRST_COMPLETED)
        finally:
            waiter.cancel()
            release.cancel()

    async def _sleep_or_cancel(self, ex: _Execution, delay_ms: int) -> None:
        if delay_ms <= 0:
            await asyncio.sleep(0)
            return
        try:
            await asyncio.wait_for(ex.cancel_event.wait(), timeout=delay_ms / 1000)
        except asyncio.TimeoutError:
            return

    async def _heartbeat_loop(self, ex: _Execution) -> None:
        try:
            while not ex.done.is_set():
                await asyncio.sleep(max(1.0, self.config.heartbeat_interval_s))
                for node in ex.graph.nodes.values():
                    lease_id = (node.metadata or {}).get("_leaseId")
                    if lease_id and node.status is TaskStatus.RUNNING:
                        self.store.heartbeat_lease(lease_id, self.config.lease_ttl_ms)
        except asyncio.CancelledError:
            return

    # ── finalization ───────────────────────────────────────────────────────────

    def _all_terminal(self, graph: ExecutionGraph) -> bool:
        return all(n.terminal for n in graph.nodes.values())

    def _has_work(self, graph: ExecutionGraph) -> bool:
        for node in graph.nodes.values():
            if node.status is TaskStatus.READY:
                return True
            if node.status is TaskStatus.PENDING and \
                    evaluate_readiness(node, graph) is Readiness.READY:
                return True
        return False

    def _finalize(self, ex: _Execution) -> None:
        graph = ex.graph
        if graph.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
                            ExecutionStatus.CANCELLED, ExecutionStatus.PARTIAL_SUCCESS):
            if ex.result is None:
                ex.result = self._build_result(ex)
            return
        nodes = list(graph.nodes.values())
        failed = [n for n in nodes if n.status in (TaskStatus.FAILED, TaskStatus.TIMED_OUT)]
        completed = [n for n in nodes if n.status is TaskStatus.COMPLETED]
        if ex.user_cancelled:
            status = ExecutionStatus.CANCELLED
        elif ex.cancel_event.is_set() and graph.failure_policy is FailurePolicy.FAIL_FAST:
            status = ExecutionStatus.FAILED
        elif not failed:
            status = ExecutionStatus.COMPLETED
        else:
            policy = graph.failure_policy
            if policy is FailurePolicy.FAIL_FAST:
                status = ExecutionStatus.FAILED
            elif policy is FailurePolicy.REQUIRE_QUORUM:
                quorum = graph.quorum or (len(nodes) // 2 + 1)
                status = ExecutionStatus.COMPLETED if len(completed) >= quorum else ExecutionStatus.FAILED
            elif policy in (FailurePolicy.CONTINUE, FailurePolicy.PARTIAL_SUCCESS, FailurePolicy.RETRY_FAILED):
                status = ExecutionStatus.PARTIAL_SUCCESS if completed else ExecutionStatus.FAILED
            else:
                status = ExecutionStatus.FAILED
        graph.status = status
        graph.completed_at = now()
        self.store.update_execution(graph.id, status=status, completedAt=graph.completed_at)
        for node in nodes:
            if node.status is TaskStatus.RUNNING:
                self._set_task_status(node, TaskStatus.CANCELLED)
                node.completed_at = now()
                self.store.save_node(node)
        event = {
            ExecutionStatus.COMPLETED: EXECUTION_COMPLETED,
            ExecutionStatus.PARTIAL_SUCCESS: EXECUTION_PARTIAL,
            ExecutionStatus.FAILED: EXECUTION_FAILED,
            ExecutionStatus.CANCELLED: EXECUTION_CANCELLED,
        }.get(status, EXECUTION_FAILED)
        ex.result = self._build_result(ex)
        self._emit(graph.id, event, {
            "status": status.value, "successful": ex.result.successful_tasks,
            "failed": ex.result.failed_tasks, "coverage": ex.result.coverage,
        })

    def _build_result(self, ex: _Execution) -> ExecutionResult:
        return ExecutionResult.from_graph(
            ex.graph, timeline=list(ex.timeline), critical_path=list(ex.critical),
            critical_path_ms=ex.critical_ms,
        )

    def _build_result_for_graph(self, graph: ExecutionGraph) -> ExecutionResult:
        path, total = critical_path(graph)
        return ExecutionResult.from_graph(graph, critical_path=path, critical_path_ms=total)

    def _record_timeline(self, ex: _Execution, node: ExecutionNode, status: TaskStatus,
                         error: Optional[NodeError]) -> None:
        ex.timeline.append({
            "nodeId": node.id,
            "kind": node.kind.value,
            "status": status.value,
            "at": node.completed_at or now(),
            "durationMs": node.duration_ms(),
            "attempts": node.attempt_count,
            "error": error.code if error else None,
        })

    # ── helpers ────────────────────────────────────────────────────────────────

    def _effective_runtime(self, ex: _Execution) -> RuntimeContext:
        return ex.runtime or self.runtime

    def _load(self, execution_id: str) -> ExecutionGraph:
        ex = self._executions.get(execution_id)
        if ex is not None:
            return ex.graph
        graph = self.store.get_execution(execution_id)
        if graph is None:
            raise KeyError(f"no execution {execution_id!r}")
        return graph

    def _set_task_status(self, node: ExecutionNode, target: TaskStatus) -> None:
        from .state import require_task_transition

        if node.status is target:
            return
        require_task_transition(node.status, target)
        node.status = target

    def _reset_node(self, node: ExecutionNode) -> None:
        node.status = TaskStatus.PENDING
        node.error = None
        node.output = None
        node.worker_id = None
        node.started_at = None
        node.completed_at = None

    def _order_key(self, ex: _Execution, node: ExecutionNode) -> tuple:
        critical = 1 if (self.config.critical_path_priority and node.id in ex.critical) else 0
        ready_at = node.metadata.get("_ready_at") or node.created_at
        return (-node.priority.weight, -critical, ready_at)

    def _worker_id(self) -> str:
        return f"worker-{id(self) % 100000}-{len(self._executions)}"

    def _dedup_registry(self, ex: _Execution, node: ExecutionNode) -> tuple[Optional[dict], Optional[str]]:
        if not node.dedup_key:
            return None, None
        scope = (node.input or {}).get("dedupScope") or self.config.dedup_scope
        if scope == "engine":
            return self._inflight, fingerprint(node, self._effective_runtime(ex))
        return ex.dedup, node.dedup_key

    def _cache_get(self, ex: _Execution, node: ExecutionNode) -> Any:
        if not node.cacheable or not node.dedup_key:
            return MISS
        return self._cache.get(fingerprint(node, self._effective_runtime(ex)))

    def _cache_put(self, ex: _Execution, node: ExecutionNode, output: Any) -> None:
        if not node.cacheable or node.cache_ttl_ms <= 0 or not node.dedup_key:
            return
        self._cache.put(fingerprint(node, self._effective_runtime(ex)), output, node.cache_ttl_ms)

    def _emit(self, execution_id: str, event_type: str, data: dict[str, Any],
              *, node_id: Optional[str] = None) -> None:
        try:
            self.store.append_event(execution_id, event_type, data, node_id=node_id)
        except Exception:  # noqa: BLE001 - losing an event must not break a run
            log.error("failed to persist orchestration event %s", event_type, exc_info=True)
        bus = getattr(self._effective_runtime_safe(), "bus", None)
        if bus is not None:
            try:
                bus.publish({
                    "id": f"orch_{execution_id}_{event_type}",
                    "runId": getattr(self.runtime, "run_id", None) or execution_id,
                    "type": event_type,
                    "at": now(),
                    "data": {"executionId": execution_id, **data},
                })
            except Exception:  # noqa: BLE001 - a broken subscriber must not break a run
                pass

    def _effective_runtime_safe(self) -> RuntimeContext:
        return self.runtime


def _as_node_kind(kind: NodeKind | str) -> NodeKind:
    if isinstance(kind, NodeKind):
        return kind
    return NodeKind(str(kind).lower())


def _as_priority(priority: Priority | str) -> Priority:
    if isinstance(priority, Priority):
        return priority
    try:
        return Priority(str(priority).upper())
    except ValueError:
        return Priority.NORMAL


def _as_failure_policy(policy: FailurePolicy | str) -> FailurePolicy:
    if isinstance(policy, FailurePolicy):
        return policy
    try:
        return FailurePolicy(str(policy).upper())
    except ValueError:
        return FailurePolicy.CONTINUE


__all__ = [
    "EngineConfig",
    "OrchestrationEngine",
    "TASK_BLOCKED",
    "TASK_CANCELLED",
    "TASK_COMPLETED",
    "TASK_CREATED",
    "TASK_FAILED",
    "TASK_READY",
    "TASK_RETRYING",
    "TASK_SKIPPED",
    "TASK_STARTED",
    "TASK_TIMEOUT",
    "compute_dedup_key",
]
