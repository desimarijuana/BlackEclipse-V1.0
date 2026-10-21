"""Build a replay evaluation dataset from recorded runs.

A replay task is a REGRESSION task, not a correctness label. It records the
prompt, the tool sequence the runtime actually used and the source run, so a
later harness can be checked for the same behavior. It never invents an expected
answer and it is `live_only` (the scripted tier reports it unmeasured rather
than replaying a stale model response).

Only completed runs are included by default. Failed runs already have their own
pipeline (`evaluation/mining.py` -> an inert candidate that still needs a human
or auto step to define expected behavior).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..observability.redaction import Redactor
from ..persistence import now_iso
from .trajectory import Trajectory

DEFAULT_DATASET_NAME = "eclipse-replay"


@dataclass
class ReplayBuildResult:
    tasks: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    skipped: int = 0
    duplicates: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": self.tasks,
            "sources": self.sources,
            "skipped": self.skipped,
            "duplicates": self.duplicates,
        }


def _signature(prompt: str, tool_sequence: list[str]) -> str:
    raw = json.dumps(
        {"prompt": prompt, "tools": tool_sequence},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _query(run: dict[str, Any]) -> str:
    payload = run.get("input")
    if isinstance(payload, dict):
        for key in ("query", "prompt", "ticker"):
            value = payload.get(key)
            if value:
                return str(value)
    return ""


def build_replay_tasks(
    run_store: Any,
    *,
    limit: int = 200,
    include_failed: bool = False,
    split: str = "optimization",
) -> ReplayBuildResult:
    """Turn completed runs into deduplicated, redacted, live-only tasks."""
    result = ReplayBuildResult()
    seen: set[str] = set()
    redactor = Redactor()

    for run in run_store.list_runs(limit=limit):
        run_id = str(run.get("id") or "")
        status = str(run.get("status") or "").strip().lower()
        if not run_id or status not in ("completed", "failed"):
            result.skipped += 1
            continue
        if status == "failed" and not include_failed:
            result.skipped += 1
            continue
        prompt = " ".join(redactor.redact_text(_query(run)).split())
        if not prompt:
            result.skipped += 1
            continue
        events = run_store.list_events(run_id)
        trajectory = Trajectory.from_events(
            events,
            run_id=run_id,
            task_id=f"replay.{run_id}",
            trial_id=run_id,
            final_answer={"output": run.get("output"), "status": status},
            outcome={"status": status, "error": run.get("error")},
        )
        tool_sequence = trajectory.tool_sequence()
        if not tool_sequence:
            # A no-tool replay is just a prompt; it does not test harness
            # behavior and would be a misleading regression task.
            result.skipped += 1
            continue
        signature = _signature(prompt, tool_sequence)
        if signature in seen:
            result.duplicates += 1
            continue
        seen.add(signature)
        task = {
            "id": f"replay.{signature[:10]}",
            "version": 1,
            "name": f"Replay {signature[:8]}",
            "description": (
                f"Regression replay from production run {run_id}. Expected "
                "behavior is the recorded tool sequence, not a correctness label."
            ),
            "category": "regression",
            "difficulty": "medium",
            "input": {"prompt": prompt},
            "expected_tools": tool_sequence,
            "graders": [{"name": "tool"}],
            "limits": {"max_turns": 40, "max_tool_calls": 200},
            "metadata": {
                "tier": 2,
                "live_only": True,
                "replay": True,
                "split": split,
                "sourceRunId": run_id,
                "sourceStatus": status,
                "signature": signature,
                "originalToolSequence": tool_sequence,
                "expectedBehavior": (
                    "recorded tool sequence (regression), never an invented answer"
                ),
            },
        }
        result.tasks.append(task)
        result.sources.append(run_id)
    return result


def write_dataset(
    result: ReplayBuildResult,
    path: str,
    *,
    dataset_name: str = DEFAULT_DATASET_NAME,
) -> str:
    payload = {
        "datasetName": dataset_name,
        "datasetVersion": "1.0.0",
        "schemaVersion": 1,
        "reviewed": False,
        "notes": (
            "Generated replay tasks from recorded runs. Live-only regression "
            "replays; the expected behavior is the recorded tool sequence, not a "
            "correctness label. Review before using as optimization material."
        ),
        "metadata": {
            "generatedAt": now_iso(),
            "sources": list(result.sources),
            "skipped": result.skipped,
            "duplicates": result.duplicates,
        },
        "tasks": result.tasks,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(target)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m harness.evaluation.replay_builder",
        description="Build a replay dataset from recorded runs (live-only).",
    )
    parser.add_argument("--out", required=True, help="output dataset JSON path")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument("--split", default="optimization")
    parser.add_argument("--run-db", default="")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    from ..persistence import AgentMemoryStore  # noqa: PLC0415

    store = AgentMemoryStore(args.run_db or None)
    try:
        result = build_replay_tasks(
            store,
            limit=args.limit,
            include_failed=args.include_failed,
            split=args.split,
        )
        path = write_dataset(result, args.out)
    finally:
        store.close()
    print(
        f"wrote {path}: {len(result.tasks)} task(s), "
        f"{result.duplicates} duplicate(s), {result.skipped} skipped",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
