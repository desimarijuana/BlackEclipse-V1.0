"""Run-lifecycle soak: 100 sequential + 8 concurrent, no LLM, no network.

Exercises the lease, terminal fencing, effect ledger and recovery reconciliation
with a scripted model. Every run calls one read-only tool and then answers.

Usage: python scripts/soak-runs.py [--runs 100] [--concurrency 8]
Exit code 0 only when every run completed and no run was left running.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from langchain_core.messages import AIMessage  # noqa: E402

from harness import graph as graph_module  # noqa: E402
from harness.persistence import AgentMemoryStore  # noqa: E402
from harness.run_lease import RunLeaseGuard  # noqa: E402
from harness.run_recovery import fail_orphaned_runs  # noqa: E402
from harness.run_lineage import RunLineage  # noqa: E402
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest  # noqa: E402
from harness.tools import DataBridge, ToolDefinition, ToolRegistry  # noqa: E402


class ScriptedModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls % 2 == 1:
            return AIMessage(
                content="", tool_calls=[{"id": f"c{self.calls}", "name": "echo", "args": {}}]
            )
        return AIMessage(content="ok")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class _Bridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "OK"}


def registry() -> ToolRegistry:
    reg = ToolRegistry()

    async def echo(args, ctx):
        return "echo", {"status": "OK"}

    reg.register(ToolDefinition(
        name="echo", description="e", input_schema={"type": "object", "properties": {}},
        handler=echo, permission="read", risk="low",
    ))
    return reg


def request(run_id: str) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query="go"),
        agent=AgentConfig(
            id="soak", name="Soak", systemPrompt="s", tools=["echo"], maxSteps=3,
            maxToolCalls=10, maxTokens=1_000_000,
        ),
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )


async def one(store, reg, bridge, run_id: str) -> str:
    with RunLeaseGuard(store, run_id) as lease:
        if not lease.owned:
            return "lease-conflict"
        result = await graph_module.execute_run(request(run_id), reg, bridge, store)
        return result.status


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    directory = tempfile.mkdtemp(prefix="be-soak-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    reg = registry()
    bridge = _Bridge()
    graph_module.build_chat_model = lambda settings: ScriptedModel()

    started = time.monotonic()
    statuses: list[str] = []
    for i in range(args.runs):
        statuses.append(await one(store, reg, bridge, f"soak_seq_{i}"))

    batches = max(1, args.runs // max(1, args.concurrency))
    for b in range(batches):
        ids = [f"soak_par_{b}_{j}" for j in range(args.concurrency)]
        statuses.extend(await asyncio.gather(*(one(store, reg, bridge, rid) for rid in ids)))

    # Recovery: five runs with a checkpoint must become resumable, not terminal.
    lineage = RunLineage(store)
    for i in range(5):
        rid = f"soak_orphan_{i}"
        store.create_run(rid, "soak", {"query": "x"})
        store.update_run(rid, status="running")
        store.append_event(rid, "model.requested", 1, {"step": 1})
        lineage.save_checkpoint(rid, "step", {"step": 1})
    fail_orphaned_runs(store, "soak restart")

    rows = {
        r["status"]: r["n"]
        for r in store._db.execute(
            "SELECT status, COUNT(*) AS n FROM HarnessRun WHERE id LIKE 'soak_%' GROUP BY status"
        ).fetchall()
    }
    orphans = [r["id"] for r in store._db.execute(
        "SELECT id FROM HarnessRun WHERE id LIKE 'soak_orphan_%' AND status <> 'interrupted'"
    ).fetchall()]
    running = [r["id"] for r in store._db.execute(
        "SELECT id FROM HarnessRun WHERE status IN ('created','running')"
    ).fetchall()]
    elapsed = time.monotonic() - started

    print(f"runs={len(statuses)} elapsed={elapsed:.1f}s statuses={rows}")
    print(f"orphans not interrupted={orphans}")
    print(f"still running={running}")
    ok = (
        all(s == "completed" for s in statuses)
        and not running
        and not orphans
        and rows.get("interrupted", 0) == 5
    )
    store.close()
    print("SOAK PASS" if ok else "SOAK FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
