"""Durable orchestration state on the ONE agent-memory connection.

Execution state must survive a process crash. Every execution, node, edge,
attempt, event and worker lease is persisted here — bound to
`AgentMemoryStore._db`, exactly like `execution/store.py`, `terminal/store.py` and
`workflows/store.py`. No second database is introduced.

Writes are bounded (a runaway node output cannot grow the database without limit)
and idempotent (`INSERT OR REPLACE` on stable ids), so recovery can replay safely.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import now_iso
from .models import (
    ExecutionGraph,
    ExecutionNode,
    ExecutionResult,
    ExecutionStatus,
    new_lease_id,
)

MAX_STORED_JSON = 200_000


def _row(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None
    if len(text) > MAX_STORED_JSON:
        return text[:MAX_STORED_JSON] + "\n[TRUNCATED]"
    return text


def _load(text: Any, default: Any) -> Any:
    if text in (None, ""):
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


class OrchestrationStore:
    """Persist executions, nodes, edges, attempts, events and leases."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()
        from ..execution_log import ExecutionEventLog  # noqa: PLC0415

        self._events = ExecutionEventLog(self._db)

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS OrchestrationExecution (
              id              TEXT PRIMARY KEY,
              rootTaskId      TEXT,
              status          TEXT NOT NULL,
              failurePolicy   TEXT NOT NULL,
              quorum          INTEGER NOT NULL DEFAULT 0,
              maxConcurrency  INTEGER NOT NULL DEFAULT 0,
              metadata        TEXT,
              createdAt       TEXT NOT NULL,
              startedAt       TEXT,
              completedAt     TEXT,
              updatedAt       TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_orch_exec_status ON OrchestrationExecution(status, updatedAt)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS OrchestrationNode (
              id           TEXT PRIMARY KEY,
              executionId  TEXT NOT NULL,
              kind         TEXT NOT NULL,
              status       TEXT NOT NULL,
              priority     TEXT NOT NULL,
              dependencies TEXT,
              dependents   TEXT,
              input        TEXT,
              output       TEXT,
              error        TEXT,
              retry        TEXT,
              timeoutMs    INTEGER NOT NULL,
              resources    TEXT,
              joinConfig   TEXT,
              metadata     TEXT,
              dedupKey     TEXT,
              cacheable    INTEGER NOT NULL DEFAULT 0,
              cacheTtlMs   INTEGER NOT NULL DEFAULT 0,
              attemptCount INTEGER NOT NULL DEFAULT 0,
              workerId     TEXT,
              createdAt    TEXT,
              startedAt    TEXT,
              completedAt  TEXT,
              updatedAt    TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_orch_node_exec ON OrchestrationNode(executionId, status)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS OrchestrationEdge (
              executionId TEXT NOT NULL,
              fromNode    TEXT NOT NULL,
              toNode      TEXT NOT NULL,
              PRIMARY KEY (executionId, fromNode, toNode)
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS OrchestrationAttempt (
              id          TEXT PRIMARY KEY,
              executionId TEXT NOT NULL,
              nodeId      TEXT NOT NULL,
              attempt     INTEGER NOT NULL,
              status      TEXT NOT NULL,
              error       TEXT,
              startedAt   TEXT,
              finishedAt  TEXT,
              durationMs  INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_orch_attempt_node ON OrchestrationAttempt(executionId, nodeId)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS OrchestrationEvent (
              id          TEXT PRIMARY KEY,
              executionId TEXT NOT NULL,
              nodeId      TEXT,
              type        TEXT NOT NULL,
              seq         INTEGER NOT NULL,
              at          TEXT NOT NULL,
              data        TEXT
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_orch_event_exec ON OrchestrationEvent(executionId, seq)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS OrchestrationLease (
              leaseId     TEXT PRIMARY KEY,
              executionId TEXT NOT NULL,
              nodeId      TEXT NOT NULL,
              workerId    TEXT NOT NULL,
              acquiredAt  TEXT NOT NULL,
              heartbeatAt TEXT NOT NULL,
              expiresAtMs INTEGER NOT NULL,
              released    INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_orch_lease_exec ON OrchestrationLease(executionId, released)"
        )
        self._db.commit()

    # ── Executions ────────────────────────────────────────────────────────────

    def save_execution(self, graph: ExecutionGraph) -> None:
        now = now_iso()
        self._db.execute(
            """INSERT OR REPLACE INTO OrchestrationExecution
               (id, rootTaskId, status, failurePolicy, quorum, maxConcurrency, metadata,
                createdAt, startedAt, completedAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                graph.id, graph.root_task_id or None, graph.status.value,
                graph.failure_policy.value, int(graph.quorum), int(graph.max_concurrency),
                _json(graph.metadata), now,
                _iso(graph.started_at), _iso(graph.completed_at), now,
            ),
        )
        self._db.commit()

    def update_execution(self, execution_id: str, **patch: Any) -> None:
        allowed = {"status", "startedAt", "completedAt", "metadata", "failurePolicy", "quorum", "maxConcurrency"}
        sets: list[str] = []
        params: list[Any] = []
        for key, value in patch.items():
            if key not in allowed:
                continue
            sets.append(f"{key} = ?")
            if key in ("startedAt", "completedAt"):
                params.append(_iso(value) if isinstance(value, (int, float)) else value)
            elif key == "metadata":
                params.append(_json(value))
            elif key == "status":
                params.append(value.value if isinstance(value, ExecutionStatus) else value)
            elif key == "failurePolicy":
                params.append(value.value if hasattr(value, "value") else value)
            else:
                params.append(value)
        if not sets:
            return
        sets.append("updatedAt = ?")
        params.append(now_iso())
        params.append(execution_id)
        self._db.execute(f"UPDATE OrchestrationExecution SET {', '.join(sets)} WHERE id = ?", params)
        self._db.commit()

    def get_execution(self, execution_id: str) -> Optional[ExecutionGraph]:
        row = self._db.execute(
            "SELECT * FROM OrchestrationExecution WHERE id=?", (execution_id,)
        ).fetchone()
        if row is None:
            return None
        data = _row(row)
        graph = ExecutionGraph(
            id=str(data["id"]),
            root_task_id=str(data.get("rootTaskId") or ""),
            status=ExecutionStatus(str(data.get("status") or "PENDING")),
            failure_policy=_failure_policy(data.get("failurePolicy")),
            quorum=int(data.get("quorum") or 0),
            max_concurrency=int(data.get("maxConcurrency") or 0),
            metadata=_load(data.get("metadata"), {}),
            created_at=_parse_iso(data.get("createdAt")),
            started_at=_parse_iso(data.get("startedAt")),
            completed_at=_parse_iso(data.get("completedAt")),
            updated_at=_parse_iso(data.get("updatedAt")),
        )
        for node_row in self._db.execute(
            "SELECT * FROM OrchestrationNode WHERE executionId=? ORDER BY createdAt ASC",
            (execution_id,),
        ).fetchall():
            node = self._node_from_row(node_row)
            graph.nodes[node.id] = node
        return graph

    def list_executions(self, *, limit: int = 100, status: Optional[str] = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if status:
            rows = self._db.execute(
                "SELECT * FROM OrchestrationExecution WHERE status=? ORDER BY createdAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM OrchestrationExecution ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = _row(row)
            counts = self._db.execute(
                "SELECT status AS s, COUNT(*) AS c FROM OrchestrationNode WHERE executionId=? GROUP BY status",
                (data["id"],),
            ).fetchall()
            out.append({
                "executionId": data["id"],
                "rootTaskId": data.get("rootTaskId"),
                "status": data.get("status"),
                "failurePolicy": data.get("failurePolicy"),
                "createdAt": data.get("createdAt"),
                "startedAt": data.get("startedAt"),
                "completedAt": data.get("completedAt"),
                "nodeCounts": {r["s"]: r["c"] for r in counts},
            })
        return out

    def recoverable_executions(self) -> list[str]:
        rows = self._db.execute(
            "SELECT id FROM OrchestrationExecution WHERE status IN ('PENDING','READY','RUNNING','PAUSED')"
        ).fetchall()
        return [r["id"] for r in rows]

    # ── Nodes ─────────────────────────────────────────────────────────────────

    def save_node(self, node: ExecutionNode) -> None:
        now = now_iso()
        self._db.execute(
            """INSERT OR REPLACE INTO OrchestrationNode
               (id, executionId, kind, status, priority, dependencies, dependents, input, output,
                error, retry, timeoutMs, resources, joinConfig, metadata, dedupKey, cacheable,
                cacheTtlMs, attemptCount, workerId, createdAt, startedAt, completedAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node.id, node.execution_id, node.kind.value, node.status.value, node.priority.value,
                _json(node.dependencies), _json(node.dependents), _json(node.input), _json(node.output),
                _json(node.error.to_dict() if node.error else None), _json(node.retry.to_dict()),
                int(node.timeout_ms), _json(node.resources.to_dict()),
                _json(node.join.to_dict() if node.join else None), _json(node.metadata),
                node.dedup_key, 1 if node.cacheable else 0, int(node.cache_ttl_ms),
                int(node.attempt_count), node.worker_id,
                _iso(node.created_at), _iso(node.started_at), _iso(node.completed_at), now,
            ),
        )
        self._db.commit()

    def save_nodes(self, graph: ExecutionGraph) -> None:
        for node in graph.nodes.values():
            self.save_node(node)

    def _node_from_row(self, row: Any) -> ExecutionNode:
        from .models import JoinConfig, NodeError, NodeKind, Priority, ResourceRequirements, RetryPolicy, TaskStatus

        data = _row(row)
        return ExecutionNode(
            id=str(data["id"]),
            execution_id=str(data["executionId"]),
            kind=NodeKind(str(data.get("kind") or "noop").lower()),
            status=TaskStatus(str(data.get("status") or "PENDING")),
            priority=Priority(str(data.get("priority") or "NORMAL")),
            dependencies=_load(data.get("dependencies"), []),
            dependents=_load(data.get("dependents"), []),
            input=_load(data.get("input"), {}),
            output=_load(data.get("output"), None),
            error=NodeError.from_dict(_load(data.get("error"), None)),
            retry=RetryPolicy.from_dict(_load(data.get("retry"), None)),
            timeout_ms=int(data.get("timeoutMs") or 120_000),
            resources=ResourceRequirements.from_dict(_load(data.get("resources"), None)),
            join=JoinConfig.from_dict(_load(data.get("joinConfig"), None)),
            metadata=_load(data.get("metadata"), {}),
            dedup_key=data.get("dedupKey"),
            cacheable=bool(data.get("cacheable")),
            cache_ttl_ms=int(data.get("cacheTtlMs") or 0),
            attempt_count=int(data.get("attemptCount") or 0),
            worker_id=data.get("workerId"),
            created_at=_parse_iso(data.get("createdAt")),
            started_at=_parse_iso(data.get("startedAt")),
            completed_at=_parse_iso(data.get("completedAt")),
        )

    def get_node(self, execution_id: str, node_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM OrchestrationNode WHERE id=? AND executionId=?", (node_id, execution_id)
        ).fetchone()
        return _row(row) if row else None

    # ── Edges ─────────────────────────────────────────────────────────────────

    def save_edge(self, execution_id: str, from_node: str, to_node: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO OrchestrationEdge (executionId, fromNode, toNode) VALUES (?, ?, ?)",
            (execution_id, from_node, to_node),
        )
        self._db.commit()

    def list_edges(self, execution_id: str) -> list[dict[str, str]]:
        rows = self._db.execute(
            "SELECT fromNode, toNode FROM OrchestrationEdge WHERE executionId=?", (execution_id,)
        ).fetchall()
        return [{"from": r["fromNode"], "to": r["toNode"]} for r in rows]

    # ── Attempts ──────────────────────────────────────────────────────────────

    def record_attempt(self, execution_id: str, node_id: str, attempt: int, status: str,
                       error: Optional[dict[str, Any]] = None,
                       started_at: Optional[float] = None, finished_at: Optional[float] = None,
                       duration_ms: int = 0) -> None:
        from .models import new_attempt_id

        self._db.execute(
            """INSERT OR REPLACE INTO OrchestrationAttempt
               (id, executionId, nodeId, attempt, status, error, startedAt, finishedAt, durationMs)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_attempt_id(), execution_id, node_id, int(attempt), status, _json(error),
                _iso(started_at), _iso(finished_at), int(duration_ms),
            ),
        )
        self._db.commit()

    def list_attempts(self, execution_id: str, node_id: Optional[str] = None) -> list[dict[str, Any]]:
        if node_id:
            rows = self._db.execute(
                "SELECT * FROM OrchestrationAttempt WHERE executionId=? AND nodeId=? ORDER BY startedAt ASC",
                (execution_id, node_id),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM OrchestrationAttempt WHERE executionId=? ORDER BY startedAt ASC",
                (execution_id,),
            ).fetchall()
        return [self._decode_attempt(_row(r)) for r in rows]

    def _decode_attempt(self, data: dict[str, Any]) -> dict[str, Any]:
        data["error"] = _load(data.get("error"), None)
        return data

    # ── Events ────────────────────────────────────────────────────────────────

    def append_event(self, execution_id: str, event_type: str, data: Optional[dict[str, Any]] = None,
                     *, node_id: Optional[str] = None) -> dict[str, Any]:
        from .models import new_node_id

        seq_row = self._db.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM OrchestrationEvent WHERE executionId=?",
            (execution_id,),
        ).fetchone()
        seq = int(seq_row["m"]) + 1
        event = {
            "id": new_node_id("oevt"),
            "executionId": execution_id,
            "nodeId": node_id,
            "type": event_type,
            "seq": seq,
            "at": now_iso(),
            "data": data or {},
        }
        self._db.execute(
            "INSERT INTO OrchestrationEvent (id, executionId, nodeId, type, seq, at, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event["id"], execution_id, node_id, event_type, seq, event["at"], _json(event["data"])),
        )
        self._db.commit()
        # Round 5 / C2: one canonical log, this table as the DAG projection.
        self._events.append(
            "orchestration", execution_id, event_type,
            {"nodeId": node_id, "data": event["data"]},
        )
        return event

    def list_events(self, execution_id: str, *, node_id: Optional[str] = None,
                    limit: int = 1000) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 5000))
        if node_id:
            rows = self._db.execute(
                "SELECT * FROM OrchestrationEvent WHERE executionId=? AND nodeId=? ORDER BY seq ASC LIMIT ?",
                (execution_id, node_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM OrchestrationEvent WHERE executionId=? ORDER BY seq ASC LIMIT ?",
                (execution_id, limit),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = _row(row)
            data["data"] = _load(data.get("data"), {})
            out.append(data)
        return out

    # ── Leases ────────────────────────────────────────────────────────────────

    def acquire_lease(self, execution_id: str, node_id: str, worker_id: str, ttl_ms: int) -> str:
        import time

        lease_id = new_lease_id()
        now = now_iso()
        expires = int(time.time() * 1000) + max(1000, int(ttl_ms))
        self._db.execute(
            """INSERT INTO OrchestrationLease
               (leaseId, executionId, nodeId, workerId, acquiredAt, heartbeatAt, expiresAtMs, released)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
            (lease_id, execution_id, node_id, worker_id, now, now, expires),
        )
        self._db.commit()
        return lease_id

    def heartbeat_lease(self, lease_id: str, ttl_ms: int) -> None:
        import time

        expires = int(time.time() * 1000) + max(1000, int(ttl_ms))
        self._db.execute(
            "UPDATE OrchestrationLease SET heartbeatAt=?, expiresAtMs=? WHERE leaseId=?",
            (now_iso(), expires, lease_id),
        )
        self._db.commit()

    def release_lease(self, lease_id: str) -> None:
        self._db.execute(
            "UPDATE OrchestrationLease SET released=1 WHERE leaseId=?", (lease_id,)
        )
        self._db.commit()

    def release_leases_for_node(self, execution_id: str, node_id: str) -> None:
        self._db.execute(
            "UPDATE OrchestrationLease SET released=1 WHERE executionId=? AND nodeId=? AND released=0",
            (execution_id, node_id),
        )
        self._db.commit()

    def active_leases(self, execution_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM OrchestrationLease WHERE executionId=? AND released=0", (execution_id,)
        ).fetchall()
        return [_row(r) for r in rows]

    def expired_leases(self, now_ms: Optional[int] = None) -> list[dict[str, Any]]:
        import time

        current = int(time.time() * 1000) if now_ms is None else int(now_ms)
        rows = self._db.execute(
            "SELECT * FROM OrchestrationLease WHERE released=0 AND expiresAtMs < ?", (current,)
        ).fetchall()
        return [_row(r) for r in rows]

    # ── Results / cleanup ─────────────────────────────────────────────────────

    def build_result(self, execution_id: str, *, timeline: Optional[list[dict[str, Any]]] = None,
                     critical: Optional[list[str]] = None, critical_ms: int = 0) -> Optional[ExecutionResult]:
        graph = self.get_execution(execution_id)
        if graph is None:
            return None
        return ExecutionResult.from_graph(
            graph, timeline=timeline, critical_path=critical, critical_path_ms=critical_ms,
        )

    def delete_execution(self, execution_id: str) -> None:
        for table in ("OrchestrationNode", "OrchestrationEdge", "OrchestrationAttempt",
                      "OrchestrationEvent", "OrchestrationLease"):
            self._db.execute(f"DELETE FROM {table} WHERE executionId=?", (execution_id,))
        self._db.execute("DELETE FROM OrchestrationExecution WHERE id=?", (execution_id,))
        self._db.commit()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _iso(value: Any) -> Optional[str]:
    import time

    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(float(value))) + ".000Z"
    except (TypeError, ValueError):
        return None


def _parse_iso(value: Any) -> Optional[float]:
    import calendar
    import time

    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = str(value).replace("Z", "").split(".")[0]
        return float(calendar.timegm(time.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")))
    except (TypeError, ValueError):
        return None


def _failure_policy(value: Any):
    from .models import FailurePolicy

    try:
        return FailurePolicy(str(value or "CONTINUE"))
    except ValueError:
        return FailurePolicy.CONTINUE


__all__ = ["MAX_STORED_JSON", "OrchestrationStore"]
