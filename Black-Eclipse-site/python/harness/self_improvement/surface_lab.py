"""The surface lab: the loop tries to improve its OWN harness, measured.

Everything the RSL loop can change is either a code change (a worktree, a
promotion) or a SURFACE change (prompt, tool guidance, context policy,
guardrails). The surface is the cheap one: no worktree, no landing, and every
claim is measurable on the corpus.

The lab builds a few DETERMINISTIC variants from the lessons the loop already
ADOPTED, measures each one against the base on the SAME tasks, and reports the
winner. The winner is a CANDIDATE: it is staged for the operator, never landed.
A variant that regresses a critical category (safety, adversarial) is vetoed
even when its average is better - and a variant that was never measured is
never a winner.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import MAX_TOOL_GUIDANCE_CHARS, HarnessSnapshot

MAX_VARIANTS = 5
CRITICAL_CATEGORIES: tuple[str, ...] = ("safety", "adversarial")


@dataclass
class SurfaceVariant:
    name: str
    snapshot: HarnessSnapshot
    derived_from: list[str] = field(default_factory=list)
    kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "derivedFrom": self.derived_from,
            "snapshotDigest": self.snapshot.sourceDigest,
            "toolGuidance": self.snapshot.toolGuidance,
        }


def _lesson_text(lesson: dict[str, Any]) -> str:
    return " ".join(
        str(lesson.get("proposedLesson") or lesson.get("lesson") or "").split()
    )


def _lesson_cue(lesson: dict[str, Any]) -> str:
    return " ".join(str(lesson.get("cue") or "").split())


def _guidance(parts: list[str]) -> str:
    text = "\n".join(f"- {part}" for part in parts if part).strip()
    return text[:MAX_TOOL_GUIDANCE_CHARS]


def propose_variants(
    base: HarnessSnapshot,
    lessons: list[dict[str, Any]],
    *,
    limit: int = MAX_VARIANTS,
) -> list[SurfaceVariant]:
    """Deterministic surface variants derived from the ADOPTED lessons.

    With no adopted lesson there is nothing to derive from, so there is no
    variant: the lab never invents an instruction nobody verified.
    """
    usable = [
        lesson for lesson in (lessons or [])
        if _lesson_text(lesson)
    ]
    if not usable:
        return []
    variants: list[SurfaceVariant] = []
    bound = max(1, min(int(limit), MAX_VARIANTS))

    first = usable[0]
    variants.append(SurfaceVariant(
        name="lesson-1",
        kind="toolGuidance",
        derived_from=[str(first.get("id") or "")],
        snapshot=HarnessSnapshot(
            systemPrompt=base.systemPrompt,
            toolNames=base.toolNames,
            toolGuidance=_guidance([_lesson_text(first)]),
            maxSteps=base.maxSteps,
            maxToolCalls=base.maxToolCalls,
        ),
    ))
    if bound >= 2 and len(usable) > 1:
        top = usable[:3]
        variants.append(SurfaceVariant(
            name="lesson-3",
            kind="toolGuidance",
            derived_from=[str(lesson.get("id") or "") for lesson in top],
            snapshot=HarnessSnapshot(
                systemPrompt=base.systemPrompt,
                toolNames=base.toolNames,
                toolGuidance=_guidance([_lesson_text(lesson) for lesson in top]),
                maxSteps=base.maxSteps,
                maxToolCalls=base.maxToolCalls,
            ),
        ))
    if bound >= 3:
        cues = [cue for cue in (_lesson_cue(lesson) for lesson in usable[:5]) if cue]
        if cues:
            variants.append(SurfaceVariant(
                name="lesson-cues",
                kind="toolGuidance",
                derived_from=[
                    str(lesson.get("id") or "") for lesson in usable[:5]
                ],
                snapshot=HarnessSnapshot(
                    systemPrompt=base.systemPrompt,
                    toolNames=base.toolNames,
                    toolGuidance=_guidance([
                        f"Check: {cue}" for cue in cues
                    ]),
                    maxSteps=base.maxSteps,
                    maxToolCalls=base.maxToolCalls,
                ),
            ))
    # The lab searches the WHOLE surface, not only the prompt: a context policy
    # and a guardrail are surface changes too, and they are measurable.
    if bound >= 4:
        variants.append(SurfaceVariant(
            name="policy-no-manifest",
            kind="contextPolicy",
            derived_from=[],
            snapshot=HarnessSnapshot(
                systemPrompt=base.systemPrompt,
                toolNames=base.toolNames,
                skillManifest="none",
                maxSteps=base.maxSteps,
                maxToolCalls=base.maxToolCalls,
            ),
        ))
    if bound >= 5:
        variants.append(SurfaceVariant(
            name="guardrail-citation",
            kind="guardrails",
            derived_from=[],
            snapshot=HarnessSnapshot(
                systemPrompt=base.systemPrompt,
                toolNames=base.toolNames,
                guardrails=("require_citation",),
                maxSteps=base.maxSteps,
                maxToolCalls=base.maxToolCalls,
            ),
        ))
    return variants[:bound]


def compare_variants(
    base_success: Optional[float],
    rows: list[dict[str, Any]],
    *,
    critical_categories: tuple[str, ...] = CRITICAL_CATEGORIES,
) -> dict[str, Any]:
    """Rank the measured variants; a critical regression vetoes a winner."""
    critical = set(critical_categories)
    ranked: list[dict[str, Any]] = []
    for row in rows:
        record = row.get("decisionRecord") or {}
        after = record.get("targetAfter")
        before = record.get("targetBefore")
        measured = bool(record.get("measured"))
        delta = (
            float(after) - float(before)
            if measured
            and isinstance(after, (int, float))
            and isinstance(before, (int, float))
            else None
        )
        regressions = list(record.get("regressions") or [])
        critical_regressions = [
            item for item in regressions
            if str(item.get("dimension") or item.get("category") or "") in critical
            or bool(item.get("critical"))
        ]
        if not measured:
            verdict = "unmeasured"
        elif critical_regressions:
            verdict = "vetoed"
        elif delta is None:
            verdict = "unmeasured"
        elif delta > 0.001:
            verdict = "improved"
        elif delta < -0.001:
            verdict = "regressed"
        else:
            verdict = "flat"
        ranked.append({
            "name": row.get("name"),
            "kind": row.get("kind"),
            "derivedFrom": row.get("derivedFrom") or [],
            "measured": measured,
            "delta": delta,
            "verdict": verdict,
            "criticalRegressions": critical_regressions,
            "regressions": regressions,
            "runId": row.get("runId"),
        })
    ranked.sort(
        key=lambda row: (
            0 if row["verdict"] == "improved" else 1,
            -(row["delta"] or 0.0),
            str(row["name"]),
        )
    )
    winner = next((row for row in ranked if row["verdict"] == "improved"), None)
    return {
        "baseSuccess": base_success,
        "variants": ranked,
        "winner": winner["name"] if winner else None,
        "winnerSnapshot": winner,
    }


def render_markdown(lab: dict[str, Any]) -> str:
    lines = [
        "# Surface lab",
        "",
        f"- variants tried: {len(lab.get('variants') or [])}",
        f"- winner: {lab.get('winner') or 'none (nothing measured better)'}",
        "",
        "| variant | measured | delta | verdict | critical regressions |",
        "|---|---|---|---|---|",
    ]
    for row in lab.get("variants") or []:
        delta = row.get("delta")
        lines.append(
            f"| {row.get('name')} | {row.get('measured')} | "
            f"{'UNKNOWN' if delta is None else f'{delta:+.4f}'} | "
            f"{row.get('verdict')} | {len(row.get('criticalRegressions') or [])} |"
        )
    lines += [
        "",
        "> A winner is a CANDIDATE for the operator, never a landing. A variant "
        "that was not measured, or that regressed a critical category, is never "
        "a winner.",
    ]
    return "\n".join(lines)


def collect_lessons(
    memory_store: Any,
    tasks: list[Any],
    *,
    eval_store: Any = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """The adopted lessons that match the corpus (cue-matched, verified)."""
    from .lessons import select_lessons  # noqa: PLC0415

    found: dict[str, dict[str, Any]] = {}
    for task in tasks:
        cue = str((getattr(task, "input", {}) or {}).get("prompt") or getattr(task, "name", ""))
        if not cue:
            continue
        try:
            lessons = select_lessons(memory_store, cue=cue, eval_store=eval_store)
        except Exception:  # noqa: BLE001 - a lesson store miss injects nothing
            lessons = []
        for lesson in lessons:
            found.setdefault(str(lesson.get("id") or ""), lesson)
    return list(found.values())[: max(1, int(limit))]


async def run_lab(
    store: Any,
    tasks: list[Any],
    base: HarnessSnapshot,
    lessons: list[dict[str, Any]],
    *,
    limit: int = MAX_VARIANTS,
    trials: int = 1,
    split: str = "validation",
    eval_store: Any = None,
    live: bool = False,
    model_settings: Any = None,
) -> dict[str, Any]:
    """Measure every variant against the base and rank them.

    `live` runs the same path with a real provider/model: that is the only tier
    in which a PROMPT change can move the result, because a scripted answer does
    not depend on the prompt.
    """
    from ..evaluation.candidate_invoker import CandidateAgentInvoker  # noqa: PLC0415
    from ..evaluation.runner import EvaluationRunner  # noqa: PLC0415
    from ..evaluation.store import EvaluationStore  # noqa: PLC0415
    from .verifier import verify_surface  # noqa: PLC0415

    run_store = eval_store or EvaluationStore(store)
    variants = propose_variants(base, lessons, limit=limit)
    if not variants:
        return {
            "base": {"taskSuccess": None},
            "variants": [],
            "winner": None,
            "reason": "no adopted lesson to derive a variant from",
        }

    invoker = CandidateAgentInvoker(
        store, base, base=base, live=live, model_settings=model_settings,
    )
    runner = EvaluationRunner(store, invoker=invoker, eval_store=run_store)
    base_suite = await runner.run_suite(
        tasks,
        dataset_name="eclipse-benchmark",
        dataset_version="1",
        trials=max(1, int(trials)),
        tier=0,
        run_id=f"surface-lab-base-{uuid.uuid4().hex[:8]}",
        persist=True,
        split=split,
        metadata={"kind": "surface-lab", "arm": "base"},
    )
    baseline_metrics = {
        "aggregates": dict(base_suite.aggregates),
        "categories": dict(base_suite.categories),
    }

    rows: list[dict[str, Any]] = []
    for variant in variants:
        result = await verify_surface(
            store=store,
            snapshot=variant.snapshot,
            base=base,
            tasks=tasks,
            baseline_metrics=baseline_metrics,
            target_dimension="task_success",
            proposal_id=f"surface-lab-{variant.name}-{uuid.uuid4().hex[:8]}",
            eval_store=run_store,
            split=split,
            trials=max(1, int(trials)),
            metadata={"kind": "surface-lab", "variant": variant.name},
            live=live,
            model_settings=model_settings,
        )
        rows.append({
            "name": variant.name,
            "kind": variant.kind,
            "derivedFrom": variant.derived_from,
            "runId": result.get("runId"),
            "decisionRecord": result.get("decisionRecord") or {},
        })

    comparison = compare_variants(base_suite.aggregates.get("task_success"), rows)
    comparison["base"] = {
        "taskSuccess": base_suite.aggregates.get("task_success"),
        "runId": base_suite.run_id,
        "aggregates": dict(base_suite.aggregates),
    }
    return comparison


def stage_winner(
    store: Any,
    lab: dict[str, Any],
    *,
    base: HarnessSnapshot,
    task_ids: list[str],
    dataset: str = "benchmark_v1",
    dataset_name: str = "",
    dataset_version: str = "",
    split: str = "validation",
    scope: str = "global",
    trials: int = 1,
    seed: Optional[int] = None,
) -> dict[str, Any]:
    """Stage the lab's winner as an INERT surface candidate.

    The lab's measurement is EVIDENCE, not a decision: the candidate is staged
    `inert` and carries the measured delta in its problem statement. The
    operator queues it, the loop verifies it through the ONE measured path, and
    only then can it be activated (with the canary and the rollback).
    """
    from .surface_candidate import save_surface_candidate  # noqa: PLC0415

    winner = lab.get("winnerSnapshot")
    if not winner:
        return {"staged": False, "reason": "no measured winner"}
    snapshot = _snapshot_for(winner, base)
    if snapshot is None:
        return {"staged": False, "reason": "the winner's snapshot is unavailable"}
    delta = winner.get("delta")
    created = save_surface_candidate(
        store,
        base=base,
        snapshot=snapshot,
        scope=scope,
        dataset=dataset,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        task_ids=task_ids,
        split=split,
        target_dimension="task_success",
        trials=trials,
        seed=seed,
        status="inert",
        source_category="surface-lab",
        problem_statement=(
            f"Surface lab: {winner.get('name')} measured "
            f"{'+' if (delta or 0) >= 0 else ''}{winner.get('delta') if delta is not None else 'UNKNOWN'} "
            f"task success on {dataset} ({split}), derived from the adopted lessons "
            f"{', '.join(str(item) for item in (winner.get('derivedFrom') or [])) or 'none'}."
        ),
    )
    return {
        "staged": True,
        "created": created["created"],
        "candidateId": (created["candidate"] or {}).get("id"),
        "candidate": created["candidate"],
    }


def _snapshot_for(winner: dict[str, Any], base: HarnessSnapshot) -> Optional[HarnessSnapshot]:
    """Rebuild the winner's snapshot from its recorded digest + guidance."""
    guidance = str(winner.get("toolGuidance") or "")
    if not guidance:
        return None
    return HarnessSnapshot(
        systemPrompt=base.systemPrompt,
        toolNames=base.toolNames,
        toolGuidance=guidance,
        maxSteps=base.maxSteps,
        maxToolCalls=base.maxToolCalls,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m harness.self_improvement.surface_lab",
        description="Try to improve the harness prompt, measured on the corpus.",
    )
    parser.add_argument("--dataset", default="benchmark_v1")
    parser.add_argument("--split", default="validation")
    parser.add_argument("--agent", default="eclipse-agent")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--limit", type=int, default=MAX_VARIANTS)
    parser.add_argument("--out", default="", help="write the report JSON here")
    parser.add_argument("--stage", action="store_true",
                        help="stage the measured winner as an inert surface candidate")
    parser.add_argument("--live", action="store_true",
                        help="use a real model (the only tier in which a prompt "
                             "change can move the result)")
    parser.add_argument("--provider", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--run-db", default="")
    parser.add_argument("--memory-db", default="")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    import asyncio  # noqa: PLC0415

    from ..agents import get_agent  # noqa: PLC0415
    from ..evaluation.runner import _build_registry  # noqa: PLC0415
    from ..evaluation.store import EvaluationStore  # noqa: PLC0415
    from ..evaluation.tasks import load_builtin_dataset, select_tasks  # noqa: PLC0415
    from ..persistence import AgentMemoryStore  # noqa: PLC0415

    store = AgentMemoryStore(args.run_db or None)
    memory_store = None
    try:
        dataset = load_builtin_dataset(args.dataset)
        tasks = select_tasks(dataset, split=args.split)
        agent = get_agent(args.agent)
        registered = set(_build_registry().names())
        base = HarnessSnapshot(
            systemPrompt=agent.systemPrompt,
            toolNames=tuple(
                name for name in (agent.tools or ()) if name in registered
            ),
            maxSteps=min(int(agent.maxSteps or 8), 32),
            maxToolCalls=min(int(agent.maxToolCalls or 200), 200),
        )
        lessons: list[dict[str, Any]] = []
        if args.memory_db:
            from ..eclipse_memory import EclipseMemoryStore  # noqa: PLC0415

            memory_store = EclipseMemoryStore(args.memory_db)
            lessons = collect_lessons(
                memory_store, tasks, eval_store=EvaluationStore(store),
            )
        model_settings = None
        if args.live:
            if not args.provider or not args.model:
                print("--live requires --provider and --model", file=sys.stderr)
                return 2
            from ..schemas import ModelSettings  # noqa: PLC0415

            model_settings = ModelSettings(
                provider=args.provider,
                model=args.model,
                base_url=args.base_url or None,
                api_key=os.environ.get("HARNESS_EVAL_API_KEY") or None,
            )
            print(
                "LIVE tier: real model requests will be sent for every trial",
                file=sys.stderr,
            )
        lab = asyncio.run(run_lab(
            store, tasks, base, lessons,
            limit=args.limit, trials=args.trials, split=args.split,
            live=bool(args.live), model_settings=model_settings,
        ))
        if args.stage:
            lab["staged"] = stage_winner(
                store, lab,
                base=base,
                task_ids=[task.id for task in tasks],
                dataset=args.dataset,
                dataset_name=dataset.name,
                dataset_version=dataset.version,
                split=args.split,
                trials=args.trials,
            )
    finally:
        if memory_store is not None:
            memory_store.close()
        store.close()

    print(render_markdown(lab))
    if args.out:
        target = os.path.abspath(args.out)
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(lab, handle, indent=2, sort_keys=True, default=str)
        print(f"\nreport: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
