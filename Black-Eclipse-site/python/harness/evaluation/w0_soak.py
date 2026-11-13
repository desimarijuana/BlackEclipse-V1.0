"""W0 lifecycle soak.

Runs the real `graph.execute_run` loop with a scripted model against a private
temporary `agent-memory.db`, then emits the same read-only baseline artifact as
`w0_baseline`. This is a **lifecycle** measurement (every run must reach a
terminal state), not a load test and not a model-quality measurement.

Usage:
    python -m harness.evaluation.w0_soak --out docs/harness/baselines/w0.json
    python -m harness.evaluation.w0_soak --sequential 50 --concurrent 24
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import AIMessage

from .. import graph as graph_module
from ..model_runtime import get_runtime
from ..model_runtime.store import ModelRuntimeStore
from ..persistence import AgentMemoryStore
from ..schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from ..tools import DataBridge, ToolRegistry
from .w0_baseline import attach_gates, build_report, render_markdown


class ScriptedSoakModel:
    """A deterministic model with no network, tools, or hidden state."""

    def bind_tools(self, tools: Any) -> "ScriptedSoakModel":
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        return AIMessage(content="w0 soak ok")

    async def astream(self, messages: Any):
        yield await self.ainvoke(messages)


class _Bridge(DataBridge):
    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "UNAVAILABLE"}


def _request(run_id: str) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query="w0 lifecycle soak"),
        agent=AgentConfig(
            id="eclipse-agent",
            name="W0 Soak",
            systemPrompt="You are a deterministic lifecycle probe.",
            tools=[],
            maxSteps=2,
        ),
        modelSettings=ModelSettings(
            provider="ollama",
            model="w0-scripted",
            base_url="http://localhost:11434/v1",
        ),
        callbackBaseUrl="http://localhost:3000",
        liveSurface=False,
    )


async def _run_one(
    store: AgentMemoryStore,
    registry: ToolRegistry,
    bridge: _Bridge,
    run_id: str,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    async with sem:
        try:
            result = await graph_module.execute_run(
                _request(run_id), registry, bridge, store,
            )
            return {"runId": run_id, "status": result.status}
        except Exception as exc:  # noqa: BLE001 - a crash is a soak outcome
            return {"runId": run_id, "status": "crashed", "error": str(exc)[:500]}


async def run_soak(
    *,
    sequential: int = 50,
    concurrent: int = 24,
    db_path: Optional[str] = None,
    label: str = "w0-soak",
    commit: str = "",
) -> dict[str, Any]:
    """Run the soak and return a baseline report. Owns/cleans a temp DB."""
    own_db = db_path is None
    if db_path is None:
        directory = tempfile.mkdtemp(prefix="be-w0-soak-")
        db_path = os.path.join(directory, "agent-memory.db")
    else:
        directory = None

    store = AgentMemoryStore(db_path)
    original_builder = getattr(graph_module, "build_chat_model", None)
    runtime = get_runtime()
    previous_sink = getattr(runtime.usage, "_sink", None)
    runtime.install_persistence(ModelRuntimeStore(store))
    graph_module.build_chat_model = lambda settings: ScriptedSoakModel()  # type: ignore[assignment]
    registry = ToolRegistry()
    bridge = _Bridge()
    outcomes: list[dict[str, Any]] = []
    try:
        sem = asyncio.Semaphore(max(1, int(concurrent)))
        for index in range(max(0, int(sequential))):
            outcomes.append(await _run_one(store, registry, bridge, f"w0-seq-{index}", sem))
        outcomes.extend(await asyncio.gather(*[
            _run_one(store, registry, bridge, f"w0-conc-{index}", sem)
            for index in range(max(0, int(concurrent)))
        ]))
    finally:
        if original_builder is not None:
            graph_module.build_chat_model = original_builder  # type: ignore[assignment]
        runtime.usage.set_sink(previous_sink)
        store.close()

    report = build_report(db_path, label=label, commit=commit)
    report["window"]["source"] = "w0-soak"
    report["soak"] = {
        "sequential": int(sequential),
        "concurrent": int(concurrent),
        "runs": len(outcomes),
        "byStatus": _counts(outcomes),
        "crashed": [o for o in outcomes if o.get("status") == "crashed"][:20],
        "model": "scripted (no network, no provider tokens or cost)",
    }
    report.setdefault("notes", []).append(
        "Soak uses a scripted model: model latency/token/cost metrics measure wiring, not a provider."
    )
    if own_db and directory:
        shutil.rmtree(directory, ignore_errors=True)
    return report


def _counts(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        status = str(outcome.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the W0 lifecycle soak.")
    parser.add_argument("--out", required=True, help="baseline JSON output path")
    parser.add_argument("--sequential", type=int, default=50)
    parser.add_argument("--concurrent", type=int, default=24)
    parser.add_argument("--db", default="", help="optional existing DB; never modified if read-only collector")
    parser.add_argument("--label", default="w0-soak")
    parser.add_argument("--commit", default="")
    parser.add_argument("--gates", default="", help="JSON file of external gate verdicts")
    args = parser.parse_args(argv)

    report = asyncio.run(run_soak(
        sequential=args.sequential,
        concurrent=args.concurrent,
        db_path=args.db or None,
        label=args.label,
        commit=args.commit,
    ))
    if args.gates:
        try:
            gates = json.loads(Path(args.gates).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"[w0-soak] could not read --gates: {exc}")
            return 2
        attach_gates(report, gates)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    print(f"[w0-soak] wrote {out} and {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
