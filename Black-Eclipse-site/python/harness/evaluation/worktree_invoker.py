"""Measured code candidates in an isolated patched worktree.

The RSL code path historically ran owning tests only and recorded
`benchmark="UNMEASURED"`. This module closes that gap: apply the candidate ops to
a disposable worktree, run the SAME deterministic evaluation suite in a
subprocess whose `PYTHONPATH` points at the patched tree, and compare the result
to a baseline from the unpatched tree.

Isolation is the point:

* the patched harness is never imported into the live process;
* the subprocess gets a temp `agent-memory.db`, no provider credentials and a
  bounded wall clock;
* the worktree is released afterwards;
* the comparison uses the existing `DEFAULT_GATES` and target-dimension rule.

The candidate still cannot land itself: this module returns a decision, and the
existing operator promotion path remains the only write.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from ..code import evolution, patch, policy, worktree
from ..code.workspace import ResolvedWorkspace
from ..evaluation.config import GRADER_API_VERSION
from ..evaluation.provenance import AGENT_VERSION, repository_commit
from ..evaluation.regression import DEFAULT_GATES, detect_regressions
from ..skills.permissions import Actor

DEFAULT_TIMEOUT_S = 900.0
MAX_STDERR_CHARS = 4_000

_SAFE_ENV_KEYS = (
    "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
    "LOCALAPPDATA", "APPDATA", "COMSPEC", "PATHEXT", "PROCESSOR_ARCHITECTURE",
    "NUMBER_OF_PROCESSORS",
)


class BenchmarkError(Exception):
    """A structured benchmark failure; `code` is stable and testable."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class BenchmarkConfig:
    dataset: str = "benchmark_v1"
    task_ids: tuple[str, ...] = ()
    split: str = "validation"
    trials: int = 1
    target_dimension: str = "task_success"
    min_improvement: float = 0.0
    timeout_s: float = DEFAULT_TIMEOUT_S
    canary_split: str = ''
    canary_task_ids: tuple[str, ...] = ()
    canary_trials: int = 1
    canary_tolerance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "taskIds": list(self.task_ids),
            "split": self.split,
            "trials": int(self.trials),
            "targetDimension": self.target_dimension,
            "minImprovement": float(self.min_improvement),
            "timeoutSeconds": float(self.timeout_s),
            "canarySplit": self.canary_split or None,
            "canaryTaskIds": list(self.canary_task_ids),
            "canaryTrials": int(self.canary_trials),
            "canaryTolerance": float(self.canary_tolerance),
        }


@dataclass
class PreparedWorktree:
    id: str
    root: Path
    apply: Callable[[], dict[str, Any]]
    release: Callable[[], None]


def _app_root(root: Path) -> Path:
    """The directory that owns `python/harness` inside the worktree.

    This repository keeps the app in `Black-Eclipse-site/` inside the git
    checkout, while a disposable smoke repo may put it at the root. Resolve the
    app root FROM the tree, never from the caller.
    """
    root = Path(root)
    if (root / "python" / "harness").is_dir():
        return root
    nested = root / "Black-Eclipse-site"
    if (nested / "python" / "harness").is_dir():
        return nested
    return root


def _resolved(ws: Any, *, root: Optional[Path] = None) -> ResolvedWorkspace:
    resolved_root = Path(root) if root is not None else Path(ws.root)
    binding = getattr(ws, "binding", None)
    if binding is None or Path(binding.root) != resolved_root:
        binding = policy.WorkspaceBinding(
            id=ws.id, root=resolved_root,
            base_revision=ws.base_revision, strategy=ws.strategy,
        )
    return ResolvedWorkspace(
        id=ws.id, root=resolved_root, base_revision=ws.base_revision,
        strategy=ws.strategy, binding=binding,
    )


def _actor(workspace_id: Optional[str] = None) -> Actor:
    return Actor(
        id="rsl-benchmark", operator=False, workspace_id=workspace_id,
        autonomy="edit_verify",
    )


def prepare_worktree(candidate: Mapping[str, Any]) -> PreparedWorktree:
    """Allocate a disposable tree and expose an explicit `apply` step."""
    try:
        ws = worktree.allocate(base_revision="HEAD")
    except worktree.WorkspaceError as exc:
        raise BenchmarkError("WORKTREE_UNAVAILABLE", exc.reason) from exc
    root = _app_root(ws.root)
    resolved = _resolved(ws, root=root)
    actor = _actor(ws.id)

    def apply() -> dict[str, Any]:
        try:
            validated = evolution.propose_ops(
                dict(candidate), actor=actor,
                ops=list(candidate.get("proposedOps") or []),
            )
            parsed = patch.parse_patch({"operations": validated})
            result = patch.apply(
                resolved, parsed, binding=resolved.binding, actor=actor,
            )
            return {"ok": bool(result.get("ok")), "result": result}
        except evolution.EvolutionRefusal as exc:
            return {"ok": False, "refused": True, **exc.to_dict()}
        except patch.PatchError as exc:
            return {"ok": False, "refused": True, "code": exc.code, "detail": exc.reason}
        except Exception as exc:  # noqa: BLE001 - a failed apply is a refusal
            return {
                "ok": False, "refused": True,
                "code": "WORKTREE_APPLY_FAILED", "detail": str(exc)[:500],
            }

    def release() -> None:
        try:
            worktree.release(ws.id)
        except Exception:  # noqa: BLE001 - release is best-effort
            pass

    return PreparedWorktree(id=ws.id, root=root, apply=apply, release=release)


def _launcher_source() -> str:
    """The child program. It imports the PATCHED tree from the worktree."""
    return '''
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ["BLACK_ECLIPSE_CODE_ROOT"], "python"))

from harness.evaluation.runner import EvaluationRunner, ScriptedAgentInvoker
from harness.evaluation.store import EvaluationStore
from harness.evaluation.tasks import (
    dataset_checksum,
    load_all_builtin,
    load_builtin_dataset,
    select_tasks,
)
from harness.persistence import AgentMemoryStore


def main() -> int:
    request_path, output_path = sys.argv[1], sys.argv[2]
    with open(request_path, encoding="utf-8") as handle:
        request = json.load(handle)
    store = AgentMemoryStore(os.environ["AGENT_MEMORY_DB_PATH"])
    try:
        dataset_name = str(request.get("dataset") or "").strip()
        dataset = load_builtin_dataset(dataset_name) if dataset_name else load_all_builtin()
        tasks = select_tasks(dataset, split=request.get("split") or "validation")
        wanted = {str(task_id) for task_id in (request.get("taskIds") or []) if str(task_id)}
        if wanted:
            tasks = [task for task in tasks if task.id in wanted]
        if not tasks:
            raise RuntimeError("the benchmark selected no tasks")
        eval_store = EvaluationStore(store)
        runner = EvaluationRunner(
            store, invoker=ScriptedAgentInvoker(store), eval_store=eval_store,
        )
        suite = asyncio.run(runner.run_suite(
            tasks,
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            dataset_checksum=dataset_checksum(tasks),
            suite="rsl-code-benchmark",
            trials=int(request.get("trials") or 1),
            tier=0,
            persist=True,
            split=request.get("split") or "validation",
            metadata={"kind": "rsl-code-benchmark"},
            extra_config={"kind": "rsl-code-benchmark"},
        ))
        payload = {
            "ok": True,
            "runId": suite.run_id,
            "aggregates": suite.aggregates,
            "measuredTrials": suite.measured_trials,
            "taskResults": [
                {
                    "taskId": task.task.id,
                    "n": task.stats.n,
                    "successes": task.stats.successes,
                    "passRate": task.stats.pass_rate,
                }
                for task in suite.tasks
            ],
            "failures": suite.failures,
            "unmeasuredTasks": suite.unmeasured_tasks,
        }
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, default=str)
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        try:
            with open(sys.argv[2], "w", encoding="utf-8") as handle:
                json.dump({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:1000]}, handle)
        except Exception:
            pass
        raise SystemExit(1)
'''


def _safe_env(root: Path, db_path: Path) -> dict[str, str]:
    """A curated child environment: no provider keys, no secrets, temp DB."""
    env = {key: os.environ[key] for key in _SAFE_ENV_KEYS if key in os.environ}
    env.update({
        "PYTHONPATH": str(Path(root) / "python"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "AGENT_MEMORY_DB_PATH": str(db_path),
        "BLACK_ECLIPSE_CODE_ROOT": str(root),
        "HARNESS_RSL_MODE": "off",
        "HARNESS_SEARCH_WARM_INDEX": "0",
        "HARNESS_SEARCH_INDEX_REPO": "0",
    })
    return env


def _task_rates(payload: Mapping[str, Any]) -> dict[str, float]:
    rates: dict[str, float] = {}
    for task in payload.get("taskResults") or []:
        if not isinstance(task, Mapping):
            continue
        task_id = str(task.get("taskId") or "")
        if not task_id or int(task.get("n") or 0) <= 0:
            continue
        try:
            rates[task_id] = float(task.get("passRate") or 0.0)
        except (TypeError, ValueError):
            continue
    return rates


def run_suite_in_worktree(
    root: Path,
    config: BenchmarkConfig,
    *,
    run_fn: Optional[Callable[[Path, BenchmarkConfig], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Run one deterministic suite under the patched tree; return compact JSON."""
    if run_fn is not None:
        return dict(run_fn(root, config))
    temp_dir = Path(tempfile.mkdtemp(prefix="be-rsl-bench-"))
    try:
        launcher = temp_dir / "runner.py"
        launcher.write_text(_launcher_source(), encoding="utf-8", newline="\n")
        request_path = temp_dir / "request.json"
        request_path.write_text(json.dumps({
            "dataset": config.dataset,
            "taskIds": list(config.task_ids),
            "split": config.split,
            "trials": int(config.trials),
        }, sort_keys=True), encoding="utf-8")
        result_path = temp_dir / "result.json"
        db_path = temp_dir / "agent-memory.db"
        env = _safe_env(Path(root), db_path)
        try:
            proc = subprocess.run(
                [sys.executable, str(launcher), str(request_path), str(result_path)],
                cwd=str(root), env=env, capture_output=True, text=True,
                timeout=float(config.timeout_s),
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "BENCHMARK_TIMEOUT"}
        except OSError as exc:
            return {"ok": False, "error": f"BENCHMARK_SPAWN_FAILED: {exc}"[:1000]}
        if not result_path.is_file():
            stderr = (proc.stderr or "")[-MAX_STDERR_CHARS:]
            return {
                "ok": False,
                "error": f"BENCHMARK_NO_RESULT (exit {proc.returncode})",
                "stderr": stderr,
            }
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": f"BENCHMARK_BAD_RESULT: {exc}"[:1000]}
        payload.setdefault("ok", proc.returncode == 0)
        if proc.stderr:
            payload["stderrTail"] = proc.stderr[-MAX_STDERR_CHARS:]
        return payload
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _critical_task_ids(config: BenchmarkConfig) -> set[str]:
    """The dataset's safety/adversarial/critical task ids for this benchmark."""
    try:
        from ..evaluation.tasks import load_builtin_dataset, select_tasks  # noqa: PLC0415
        from ..self_improvement.replay import critical_task_ids  # noqa: PLC0415

        dataset = load_builtin_dataset(config.dataset)
        tasks = select_tasks(dataset, split=config.split)
        wanted = {str(task_id) for task_id in (config.task_ids or ()) if str(task_id)}
        if wanted:
            tasks = [task for task in tasks if task.id in wanted]
        return set(critical_task_ids(tasks))
    except Exception:  # noqa: BLE001 - unavailable metadata is not a veto
        return set()


def benchmark_decision(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    target_dimension: str = "task_success",
    min_improvement: float = 0.0,
    gates: Optional[tuple] = None,
    critical_tasks: Iterable[str] = (),
) -> dict[str, Any]:
    """Accept only a measured target improvement with no critical regression.

    `critical_tasks` is the per-task veto set (safety/adversarial/critical tasks);
    a measured drop on any of them rejects the candidate even when the aggregate
    target improved.
    """
    baseline_agg = dict(baseline.get("aggregates") or {})
    candidate_agg = dict(candidate.get("aggregates") or {})
    measured = int(candidate.get("measuredTrials") or 0)
    target_before = baseline_agg.get(target_dimension)
    target_after = candidate_agg.get(target_dimension)
    outcome = detect_regressions(
        {"aggregates": baseline_agg}, {"aggregates": candidate_agg},
        gates or DEFAULT_GATES,
    )
    critical_regressions = [
        item for item in outcome["regressions"]
        if any(
            gate.dimension == item.get("dimension") and gate.critical
            for gate in (gates or DEFAULT_GATES)
        )
    ]
    baseline_rates = _task_rates(baseline)
    candidate_rates = _task_rates(candidate)
    critical_deltas = []
    for task_id in sorted({str(task_id) for task_id in critical_tasks if str(task_id)}):
        before = baseline_rates.get(task_id)
        after = candidate_rates.get(task_id)
        if before is not None and after is not None and after < before:
            critical_deltas.append({
                "taskId": task_id,
                "before": before,
                "after": after,
                "delta": round(after - before, 6),
            })
    reasons: list[str] = []
    if measured <= 0:
        reasons.append("no measured trials")
    if target_before is None or target_after is None:
        reasons.append(f"target {target_dimension} is UNMEASURED")
    if critical_regressions:
        reasons.append("critical regression: " + ", ".join(
            str(item.get("dimension")) for item in critical_regressions
        ))
    if critical_deltas:
        reasons.append("critical task regressed: " + ", ".join(
            f"{item['taskId']} ({item['before']:.3f} → {item['after']:.3f})"
            for item in critical_deltas
        ))
    if not reasons and float(target_after) - float(target_before) <= float(min_improvement):
        reasons.append(
            f"target {target_dimension} did not improve "
            f"({target_before} → {target_after})"
        )
    return {
        "accepted": not reasons,
        "reasons": reasons,
        "targetDimension": target_dimension,
        "targetBefore": target_before,
        "targetAfter": target_after,
        "measured": measured,
        "regressions": outcome["regressions"],
        "warnings": outcome["warnings"],
        "criticalDeltas": critical_deltas,
    }


def _record_benchmark(
    eval_store: Any,
    candidate: Mapping[str, Any],
    *,
    config: BenchmarkConfig,
    baseline: Mapping[str, Any],
    candidate_result: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> Optional[str]:
    if eval_store is None:
        return None
    run_id = f"rsl-code-{uuid.uuid4().hex[:16]}"
    checksum = hashlib.sha256(
        json.dumps(config.to_dict(), sort_keys=True).encode("utf-8")
    ).hexdigest()[:32]
    try:
        eval_store.create_run(
            id=run_id,
            suite="rsl-code-benchmark",
            datasetName=config.dataset,
            datasetVersion="1",
            datasetChecksum=checksum,
            tier=0,
            invoker="worktree-benchmark",
            agentVersion=AGENT_VERSION,
            gitCommit=repository_commit(),
            config={
                **config.to_dict(),
                "kind": "rsl-code-benchmark",
                "graderVersion": GRADER_API_VERSION,
            },
            metadata={
                "kind": "rsl-code-benchmark",
                "candidateId": candidate.get("id"),
                "decisionRecord": dict(decision),
                "baseline": {
                    "aggregates": baseline.get("aggregates") or {},
                    "measuredTrials": baseline.get("measuredTrials"),
                },
                "candidate": {
                    "aggregates": candidate_result.get("aggregates") or {},
                    "measuredTrials": candidate_result.get("measuredTrials"),
                },
                "taskRates": _task_rates(candidate_result),
                "benchmark": "MEASURED",
            },
            status="completed",
        )
    except Exception:  # noqa: BLE001 - recording must not undo the measurement
        return None
    return run_id


def run_candidate_benchmark(
    candidate: Mapping[str, Any],
    *,
    config: Optional[BenchmarkConfig] = None,
    eval_store: Any = None,
    prepare: Optional[Callable[[Mapping[str, Any]], PreparedWorktree]] = None,
    run_suite: Optional[Callable[[Path, BenchmarkConfig], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Run baseline then candidate in ONE disposable tree; return the decision.

    `prepare` and `run_suite` are the test seams. In production the candidate is
    applied through the existing `propose_ops` + `patch.apply` guard, and the
    suite runs in a subprocess that imports the patched tree.
    """
    settings = config or BenchmarkConfig()
    prepared: Optional[PreparedWorktree] = None
    try:
        prepared = (prepare or prepare_worktree)(candidate)
        runner = run_suite or run_suite_in_worktree
        baseline = runner(prepared.root, settings)
        if not baseline.get("ok"):
            return {
                "ok": False, "benchmark": "UNMEASURED",
                "decision": "benchmark_baseline_failed",
                "detail": baseline.get("error") or baseline.get("stderr"),
            }
        canary_before = None
        if settings.canary_split:
            canary_settings = replace(
                settings,
                split=settings.canary_split,
                task_ids=tuple(settings.canary_task_ids),
                trials=max(1, int(settings.canary_trials)),
            )
            canary_before = runner(prepared.root, canary_settings)
            if not canary_before.get("ok"):
                return {
                    "ok": False, "benchmark": "UNMEASURED",
                    "decision": "canary_baseline_failed",
                    "detail": canary_before.get("error") or canary_before.get("stderr"),
                }
        applied = prepared.apply()
        if not applied.get("ok"):
            return {
                "ok": False, "refused": bool(applied.get("refused")),
                "benchmark": "UNMEASURED",
                "decision": "benchmark_apply_refused",
                "detail": applied,
            }
        candidate_result = runner(prepared.root, settings)
        if not candidate_result.get("ok"):
            return {
                "ok": False, "benchmark": "UNMEASURED",
                "decision": "benchmark_candidate_failed",
                "detail": candidate_result.get("error") or candidate_result.get("stderr"),
            }
        decision = benchmark_decision(
            baseline, candidate_result,
            target_dimension=settings.target_dimension,
            min_improvement=settings.min_improvement,
            critical_tasks=_critical_task_ids(settings),
        )
        canary = None
        if canary_before is not None:
            from .canary import assess_canary  # noqa: PLC0415

            canary_after = runner(prepared.root, replace(
                settings,
                split=settings.canary_split,
                task_ids=tuple(settings.canary_task_ids),
                trials=max(1, int(settings.canary_trials)),
            ))
            canary = assess_canary(
                canary_before, canary_after,
                target_dimension=settings.target_dimension,
                critical_tasks=_critical_task_ids(settings),
                tolerance=settings.canary_tolerance,
            )
            if not canary.get("passed"):
                decision = {
                    **decision,
                    "accepted": False,
                    "reasons": [
                        *(decision.get("reasons") or []),
                        *(canary.get("reasons") or []),
                    ],
                    "canary": canary,
                }
        run_id = _record_benchmark(
            eval_store, candidate, config=settings,
            baseline=baseline, candidate_result=candidate_result,
            decision=decision,
        )
        return {
            "ok": True,
            "passed": bool(decision["accepted"]),
            "benchmark": "MEASURED",
            "decision": "benchmark",
            "runId": run_id,
            "decisionRecord": decision,
            "baseline": baseline,
            "candidate": candidate_result,
            "canary": canary,
            "taskRates": _task_rates(candidate_result),
        }
    except BenchmarkError as exc:
        return {
            "ok": False, "benchmark": "UNMEASURED",
            "decision": exc.code, "detail": exc.to_dict(),
        }
    except Exception as exc:  # noqa: BLE001 - a benchmark failure is a decision
        return {
            "ok": False, "benchmark": "UNMEASURED",
            "decision": "benchmark_error",
            "detail": f"{type(exc).__name__}: {exc}"[:1000],
        }
    finally:
        if prepared is not None:
            prepared.release()


__all__ = [
    "BenchmarkConfig",
    "BenchmarkError",
    "PreparedWorktree",
    "benchmark_decision",
    "prepare_worktree",
    "run_candidate_benchmark",
    "run_suite_in_worktree",
]
