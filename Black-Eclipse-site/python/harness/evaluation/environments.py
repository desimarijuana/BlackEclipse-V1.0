"""Deterministic evaluation environments.

Every task starts from a known state. An environment supports the full lifecycle
``setup / reset / snapshot / restore / seed / execute / inspect_state / teardown``
so a trial is reproducible and a state-changing task is graded on the REAL
resulting state, not on the model prose.

Environments are isolated: a filesystem environment is a private temp directory,
a database environment a private temp SQLite file, and no environment reaches the
network or a production credential. ``allow_external_side_effects`` (default OFF)
is the only way to permit a real effect, and nothing here does.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class EnvironmentError(RuntimeError):
    """An environment could not be built or driven. Never swallowed."""


class Environment(ABC):
    """The deterministic-environment contract every environment implements."""

    #: the registry key / task ``environment.type``
    kind: str = "base"

    def __init__(self, spec: Optional[dict[str, Any]] = None) -> None:
        self.spec = spec or {}
        self._setup_done = False

    # -- lifecycle ---------------------------------------------------------
    @abstractmethod
    def setup(self) -> None:
        """Allocate the private resources for the environment."""

    @abstractmethod
    def seed(self, initial_state: dict[str, Any]) -> None:
        """Populate the environment from a task's ``initial_state``."""

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        """A JSON-serializable capture of the current state."""

    @abstractmethod
    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore the environment to a previously captured snapshot."""

    @abstractmethod
    def inspect_state(self) -> dict[str, Any]:
        """A JSON-serializable, grader-facing view of the current state."""

    @abstractmethod
    def teardown(self) -> None:
        """Release every private resource. Idempotent."""

    def reset(self, initial_state: Optional[dict[str, Any]] = None) -> None:
        """Return to the task's starting state (teardown-if-needed + setup + seed)."""
        self.teardown()
        self._setup_done = False
        self.setup()
        self.seed(initial_state or {})
        self._setup_done = True

    def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """Run one deterministic action inside the environment (optional)."""
        raise EnvironmentError(f"{self.kind} environment does not execute actions")

    # -- shared helpers ----------------------------------------------------
    @staticmethod
    def _hash_bytes(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()[:32]


class FilesystemEnvironment(Environment):
    """A private temp directory of files. The basis for code/state tasks."""

    kind = "filesystem"

    def __init__(self, spec: Optional[dict[str, Any]] = None) -> None:
        super().__init__(spec)
        self.root: Optional[str] = None

    def setup(self) -> None:
        if self.root and os.path.isdir(self.root):
            return
        base = self.spec.get("base_dir") or tempfile.gettempdir()
        self.root = tempfile.mkdtemp(prefix="be-env-fs-", dir=base)

    def seed(self, initial_state: dict[str, Any]) -> None:
        if self.root is None:
            raise EnvironmentError("filesystem environment not set up")
        for rel, content in (initial_state.get("files") or {}).items():
            self.write(rel, content)

    def write(self, rel: str, content: Any) -> None:
        if self.root is None:
            raise EnvironmentError("filesystem environment not set up")
        full = os.path.realpath(os.path.join(self.root, rel))
        if os.path.commonpath([full, os.path.realpath(self.root)]) != os.path.realpath(self.root):
            raise EnvironmentError(f"path escapes the environment: {rel}")
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as handle:
            handle.write(content if isinstance(content, str) else json_dumps(content))

    def read(self, rel: str) -> Optional[str]:
        if self.root is None:
            return None
        full = os.path.join(self.root, rel)
        if not os.path.isfile(full):
            return None
        with open(full, encoding="utf-8", errors="replace") as handle:
            return handle.read()

    def snapshot(self) -> dict[str, Any]:
        if self.root is None or not os.path.isdir(self.root):
            return {"kind": self.kind, "root": self.root, "files": {}}
        files: dict[str, Any] = {}
        for dirpath, _dirs, names in os.walk(self.root):
            for name in names:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self.root)
                with open(full, "rb") as handle:
                    payload = handle.read()
                files[rel] = {
                    "sha256": self._hash_bytes(payload),
                    "size": len(payload),
                    "content_b64": base64.b64encode(payload).decode("ascii"),
                }
        return {"kind": self.kind, "root": self.root, "files": files}

    def restore(self, snapshot: dict[str, Any]) -> None:
        if self.root is None:
            self.setup()
        assert self.root is not None
        # Remove anything not in the snapshot, then write every captured file.
        wanted = set((snapshot.get("files") or {}).keys())
        for dirpath, _dirs, names in os.walk(self.root):
            for name in names:
                rel = os.path.relpath(os.path.join(dirpath, name), self.root)
                if rel not in wanted:
                    os.remove(os.path.join(dirpath, name))
        for rel, meta in (snapshot.get("files") or {}).items():
            full = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as handle:
                handle.write(base64.b64decode(meta["content_b64"]))

    def inspect_state(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {
            "kind": self.kind,
            "root": self.root,
            "files": {rel: meta["sha256"] for rel, meta in snap["files"].items()},
            "paths": sorted(snap["files"].keys()),
        }

    def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action != "run":
            raise EnvironmentError(f"filesystem: unknown action '{action}'")
        command = kwargs.get("command")
        if not command:
            raise EnvironmentError("filesystem.run requires a command")
        if isinstance(command, str):
            command = command.split()
        # `{python}` resolves to the interpreter running the harness so a check
        # is portable across a vendored and a system Python.
        command = [sys.executable if part == "{python}" else part for part in command]
        timeout = float(kwargs.get("timeout", 30))
        try:
            proc = subprocess.run(
                command, cwd=self.root, capture_output=True, text=True, timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 - a failed run is a real outcome
            return {"exit_code": -1, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}
        return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}

    def teardown(self) -> None:
        if self.root and os.path.isdir(self.root):
            shutil.rmtree(self.root, ignore_errors=True)
        self.root = None


class SqliteEnvironment(Environment):
    """A private temp SQLite database. State tasks grade the REAL rows."""

    kind = "database"

    def __init__(self, spec: Optional[dict[str, Any]] = None) -> None:
        super().__init__(spec)
        self.path: Optional[str] = None

    def setup(self) -> None:
        if self.path:
            return
        fd, self.path = tempfile.mkstemp(prefix="be-env-db-", suffix=".db")
        os.close(fd)
        conn = self._connect()
        conn.executescript(self.spec.get("schema") or "")
        conn.commit()
        conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path or ":memory:")
        conn.row_factory = sqlite3.Row
        return conn

    def seed(self, initial_state: dict[str, Any]) -> None:
        conn = self._connect()
        for statement in initial_state.get("sql") or []:
            conn.execute(statement)
        for table, rows in (initial_state.get("rows") or {}).items():
            if not rows:
                continue
            columns = list(rows[0].keys())
            placeholders = ", ".join("?" for _ in columns)
            for row in rows:
                conn.execute(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                    [row[c] for c in columns],
                )
        conn.commit()
        conn.close()

    def snapshot(self) -> dict[str, Any]:
        conn = self._connect()
        tables: dict[str, list[dict[str, Any]]] = {}
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for name in names:
            tables[name] = [dict(r) for r in conn.execute(f"SELECT * FROM {name}").fetchall()]
        conn.close()
        return {"kind": self.kind, "tables": tables}

    def restore(self, snapshot: dict[str, Any]) -> None:
        conn = self._connect()
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for name in names:
            conn.execute(f"DELETE FROM {name}")
        for table, rows in (snapshot.get("tables") or {}).items():
            for row in rows:
                columns = list(row.keys())
                placeholders = ", ".join("?" for _ in columns)
                conn.execute(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                    [row[c] for c in columns],
                )
        conn.commit()
        conn.close()

    def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action != "query":
            raise EnvironmentError(f"database: unknown action '{action}'")
        conn = self._connect()
        try:
            cursor = conn.execute(kwargs["sql"])
            rows = [dict(r) for r in cursor.fetchall()] if cursor.description else []
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}", "rows": []}
        finally:
            conn.close()
        return {"rows": rows}

    def inspect_state(self) -> dict[str, Any]:
        return self.snapshot()

    def teardown(self) -> None:
        if self.path and os.path.isfile(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass
        self.path = None


class FinanceEnvironment(Environment):
    """Deterministic fixture data for financial tasks (no I/O).

    Holds price series / fact sets the :class:`~harness.evaluation.graders.financial.FinancialGrader`
    recomputes independently. State inspection just returns the fixtures, so a
    grader never has to guess what the inputs were.
    """

    kind = "finance"

    def __init__(self, spec: Optional[dict[str, Any]] = None) -> None:
        super().__init__(spec)
        self.data: dict[str, Any] = {}

    def setup(self) -> None:
        self.data = {}

    def seed(self, initial_state: dict[str, Any]) -> None:
        self.data = dict(initial_state.get("finance") or initial_state or {})

    def snapshot(self) -> dict[str, Any]:
        return {"kind": self.kind, "data": self.data}

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.data = dict(snapshot.get("data") or {})

    def inspect_state(self) -> dict[str, Any]:
        return {"kind": self.kind, "data": self.data}

    def teardown(self) -> None:
        self.data = {}


class MemoryEnvironment(Environment):
    """A private in-process key/value memory store for memory-capability tasks."""

    kind = "memory"

    def __init__(self, spec: Optional[dict[str, Any]] = None) -> None:
        super().__init__(spec)
        self.entries: dict[str, str] = {}

    def setup(self) -> None:
        self.entries = {}

    def seed(self, initial_state: dict[str, Any]) -> None:
        self.entries = dict(initial_state.get("memory") or {})

    def snapshot(self) -> dict[str, Any]:
        return {"kind": self.kind, "entries": dict(self.entries)}

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.entries = dict(snapshot.get("entries") or {})

    def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "write":
            self.entries[kwargs["key"]] = kwargs["value"]
            return {"ok": True}
        if action == "read":
            return {"value": self.entries.get(kwargs["key"])}
        if action == "delete":
            self.entries.pop(kwargs["key"], None)
            return {"ok": True}
        raise EnvironmentError(f"memory: unknown action '{action}'")

    def inspect_state(self) -> dict[str, Any]:
        return {"kind": self.kind, "entries": dict(self.entries)}

    def teardown(self) -> None:
        self.entries = {}


class MockServiceEnvironment(Environment):
    """A map of deterministic request→response services (no real network)."""

    kind = "mock_services"

    def __init__(self, spec: Optional[dict[str, Any]] = None) -> None:
        super().__init__(spec)
        self.services: dict[str, Any] = {}
        self.calls: list[dict[str, Any]] = []

    def setup(self) -> None:
        self.services = dict(self.spec.get("services") or {})
        self.calls = []

    def seed(self, initial_state: dict[str, Any]) -> None:
        self.services.update(initial_state.get("services") or {})

    def snapshot(self) -> dict[str, Any]:
        return {"kind": self.kind, "services": self.services, "calls": list(self.calls)}

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.services = dict(snapshot.get("services") or {})
        self.calls = list(snapshot.get("calls") or [])

    def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action != "call":
            raise EnvironmentError(f"mock_services: unknown action '{action}'")
        name = kwargs["service"]
        self.calls.append({"service": name, "request": kwargs.get("request")})
        if name not in self.services:
            return {"error": "SERVICE_UNAVAILABLE", "response": None}
        return {"response": self.services[name]}

    def inspect_state(self) -> dict[str, Any]:
        return {"kind": self.kind, "services": sorted(self.services), "calls": list(self.calls)}

    def teardown(self) -> None:
        self.services = {}
        self.calls = []


class CompositeEnvironment(Environment):
    """Several environments addressed by key, e.g. ``filesystem`` + ``finance``."""

    kind = "composite"

    def __init__(self, spec: Optional[dict[str, Any]] = None) -> None:
        super().__init__(spec)
        self.parts: dict[str, Environment] = {}

    def setup(self) -> None:
        for key, part_spec in (self.spec.get("parts") or {}).items():
            self.parts[key] = build_environment(part_spec)
            self.parts[key].setup()

    def seed(self, initial_state: dict[str, Any]) -> None:
        for key, part in self.parts.items():
            part.seed(initial_state.get(key) or {})

    def snapshot(self) -> dict[str, Any]:
        return {"kind": self.kind, "parts": {k: v.snapshot() for k, v in self.parts.items()}}

    def restore(self, snapshot: dict[str, Any]) -> None:
        for key, part_snap in (snapshot.get("parts") or {}).items():
            if key in self.parts:
                self.parts[key].restore(part_snap)

    def inspect_state(self) -> dict[str, Any]:
        return {"kind": self.kind, "parts": {k: v.inspect_state() for k, v in self.parts.items()}}

    def teardown(self) -> None:
        for part in self.parts.values():
            part.teardown()
        self.parts = {}


class UiStateEnvironment(Environment):
    """The UI/task runtime's durable state, read back for grading (round 4, W3.2).

    Holds no private resources: the state lives in the invoker's trial store
    (agent-memory.db) and is BOUND IN by the invoker at invoke time (the same
    store its `UiService`/`TaskManager` write to). `inspect_state` reports the
    REAL engineering tasks/plans the `ui_*` tools created — never the model's
    prose — so a routing scenario is graded end-to-end through the real graph.
    """

    kind = "ui"

    def __init__(self, spec: Optional[dict[str, Any]] = None) -> None:
        super().__init__(spec)
        self._ui_service: Any = None
        self._task_manager: Any = None
        self._store: Any = None
        self._store_dir: Any = None

    def bind(
        self, *, ui_service: Any = None, task_manager: Any = None,
        store: Any = None, store_dir: Any = None,
    ) -> None:
        """Attach the trial's live services + store (called by the invoker).

        The invoker defers store cleanup to `teardown`: grading reads the store
        AFTER invoke returns, so closing it there would grade an empty state.
        """
        self._ui_service = ui_service
        self._task_manager = task_manager
        self._store = store
        self._store_dir = store_dir

    def setup(self) -> None:
        return

    def seed(self, initial_state: dict[str, Any]) -> None:
        return

    def snapshot(self) -> dict[str, Any]:
        return {"kind": self.kind}

    def restore(self, snapshot: dict[str, Any]) -> None:
        return

    def inspect_state(self) -> dict[str, Any]:
        tasks: list[dict[str, Any]] = []
        plans: list[dict[str, Any]] = []
        if self._task_manager is not None:
            try:
                for plan in self._task_manager.list_plans(limit=50):
                    plans.append({
                        "planId": plan.id, "name": plan.name, "status": plan.status.value,
                    })
                    for task in self._task_manager.list_tasks(plan_id=plan.id, limit=200):
                        meta = dict(task.metadata or {})
                        tasks.append({
                            "taskId": task.id, "planId": task.plan_id,
                            "status": task.status.value, "title": task.title,
                            "kind": meta.get("kind"),
                            "capabilityGap": bool(meta.get("capabilityGap", False)),
                            "acceptanceCount": len(self._task_manager.list_criteria(task.id)),
                        })
            except Exception:  # noqa: BLE001 - a state read failure yields empty, never a fake pass
                pass
        component_count = 0
        if self._ui_service is not None:
            try:
                component_count = len(self._ui_service.catalog.list())
            except Exception:  # noqa: BLE001
                component_count = 0
        return {
            "kind": self.kind,
            "ui": {
                "engineeringTaskCount": len(tasks),
                "engineeringTasks": tasks,
                "plans": plans,
                "componentCount": component_count,
            },
        }

    def teardown(self) -> None:
        self._ui_service = None
        self._task_manager = None
        store, self._store = self._store, None
        store_dir, self._store_dir = self._store_dir, None
        if store is not None:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass
        if store_dir:
            import shutil  # noqa: PLC0415

            shutil.rmtree(str(store_dir), ignore_errors=True)


_REGISTRY: dict[str, Callable[[Optional[dict[str, Any]]], Environment]] = {
    "filesystem": FilesystemEnvironment,
    "database": SqliteEnvironment,
    "finance": FinanceEnvironment,
    "memory": MemoryEnvironment,
    "mock_services": MockServiceEnvironment,
    "composite": CompositeEnvironment,
    # The UI/task runtime's durable state (round 4, W3.2): bound in by the
    # scripted invoker; a routing scenario is graded on what the tools DID.
    "ui": UiStateEnvironment,
    # A no-op environment for pure-output tasks.
    "none": lambda spec=None: FinanceEnvironment({**(spec or {}), "kind": "none"}),
}


def register_environment(kind: str, factory: Callable[[Optional[dict[str, Any]]], Environment]) -> None:
    _REGISTRY[kind] = factory


def environment_kinds() -> list[str]:
    return sorted(_REGISTRY)


def build_environment(spec: Optional[dict[str, Any]]) -> Environment:
    """Build (but do not set up) the environment described by a task spec."""
    spec = spec or {}
    kind = str(spec.get("type") or spec.get("kind") or "none")
    factory = _REGISTRY.get(kind)
    if factory is None:
        raise EnvironmentError(
            f"unknown environment '{kind}' (available: {', '.join(environment_kinds())})"
        )
    return factory(spec)


def json_dumps(value: Any) -> str:
    import json  # noqa: PLC0415

    return json.dumps(value, indent=2, sort_keys=True)


__all__ = [
    "CompositeEnvironment",
    "Environment",
    "EnvironmentError",
    "FilesystemEnvironment",
    "FinanceEnvironment",
    "MemoryEnvironment",
    "MockServiceEnvironment",
    "SqliteEnvironment",
    "UiStateEnvironment",
    "build_environment",
    "environment_kinds",
    "register_environment",
]
