"""Deterministic held_out rotation, with a dry-run plan and an explicit apply.

The corpus is not a fixed set forever: a held_out task that has been seen by a
candidate stops being a clean canary. Rotation is therefore deliberate and
operator-invoked:

- `plan_rotation(quarter, count)` chooses `count` optimization tasks (seeded by
  the quarter, so the plan is reproducible) to become the new held_out, and
  returns the CURRENT held_out tasks to optimization;
- `apply_rotation(plan)` writes the split back into the dataset files, bumps the
  task version, records `metadata.rotation`, and refreshes the manifest.

It never touches validation (the acceptance set) and never runs automatically.
Applying the same quarter twice is a no-op (`already_rotated`).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from typing import Any, Optional

from ..persistence import now_iso
from .tasks import DATASETS_DIR, SPLITS

MAX_ROTATION = 50
ROTATION_KEY = "rotation"


def _datasets_dir(directory: Optional[str] = None) -> str:
    return os.path.abspath(directory or DATASETS_DIR)


def _load_files(datasets_dir: str) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for name in sorted(os.listdir(datasets_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(datasets_dir, name)
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
            files[name] = payload
    return files


def _split(task: dict[str, Any], dataset_split: str) -> str:
    raw = str((task.get("metadata") or {}).get("split") or "").strip().lower()
    if raw in SPLITS:
        return raw
    fallback = str(dataset_split or "").strip().lower()
    return fallback if fallback in SPLITS else "validation"


def plan_rotation(
    *,
    quarter: str,
    count: int = 12,
    datasets_dir: Optional[str] = None,
) -> dict[str, Any]:
    """A deterministic rotation plan (no writes).

    `count` is clamped to 1..50; the seed is the quarter, so a re-run produces
    the same selection. A task already rotated in this quarter is skipped.
    """
    stamp = str(quarter or "").strip()
    if not stamp:
        raise ValueError("a rotation needs a quarter label (for example 2026Q1)")
    size = max(1, min(MAX_ROTATION, int(count)))
    directory = _datasets_dir(datasets_dir)
    files = _load_files(directory)
    optimization: list[dict[str, Any]] = []
    held_out: list[dict[str, Any]] = []
    for filename, payload in files.items():
        dataset_meta = payload.get("metadata") or {}
        if dataset_meta.get("rotationExempt") or dataset_meta.get("protected"):
            continue
        dataset_split = str(dataset_meta.get("split") or "")
        for task in payload.get("tasks") or []:
            metadata = task.get("metadata") or {}
            if metadata.get("rotationExempt") or metadata.get("protected"):
                continue
            split = _split(task, dataset_split)
            rotation = metadata.get(ROTATION_KEY) or {}
            if str(rotation.get("quarter") or "") == stamp:
                continue
            row = {
                "datasetFile": filename,
                "taskId": str(task.get("id") or ""),
                "version": int(task.get("version", 1) or 1),
            }
            if split == "optimization":
                optimization.append(row)
            elif split == "held_out":
                held_out.append(row)

    if not optimization:
        return {
            "ok": False,
            "quarter": stamp,
            "reason": "no_optimization_tasks",
            "moves": [],
        }

    seed = f"{stamp}:rotation"
    shuffled = sorted(optimization, key=lambda item: item["taskId"])
    random.Random(seed).shuffle(shuffled)
    selected = shuffled[: min(size, len(shuffled))]

    moves = [
        {**row, "from": "optimization", "to": "held_out"}
        for row in selected
    ] + [
        {**row, "from": "held_out", "to": "optimization"}
        for row in held_out
    ]
    return {
        "ok": True,
        "quarter": stamp,
        "seed": seed,
        "count": len(selected),
        "returned": len(held_out),
        "moves": moves,
        "datasetsDir": directory,
    }


def apply_rotation(
    plan: dict[str, Any],
    *,
    datasets_dir: Optional[str] = None,
    manifest_path: Optional[str] = None,
    refresh_manifest: bool = True,
    rotated_at: Optional[str] = None,
) -> dict[str, Any]:
    """Write a plan to the dataset files and (optionally) refresh the manifest.

    Every moved task bumps its `version` and records the rotation in
    `metadata.rotation`; a task already rotated in this quarter is skipped, so a
    repeated apply is a no-op rather than a second move.
    """
    if not plan.get("ok"):
        raise ValueError(str(plan.get("reason") or "the rotation plan is not applicable"))
    quarter = str(plan.get("quarter") or "")
    if not quarter:
        raise ValueError("the plan has no quarter")
    directory = _datasets_dir(datasets_dir or plan.get("datasetsDir"))
    files = _load_files(directory)
    stamp = rotated_at or now_iso()
    moved = 0
    skipped = 0
    touched: set[str] = set()

    by_file: dict[str, list[dict[str, Any]]] = {}
    for move in plan.get("moves") or []:
        filename = str(move.get("datasetFile") or "")
        if filename:
            by_file.setdefault(filename, []).append(move)

    for filename, moves in by_file.items():
        payload = files.get(filename)
        if payload is None:
            continue
        by_id = {
            str(task.get("id") or ""): task
            for task in payload.get("tasks") or []
        }
        changed = False
        for move in moves:
            task = by_id.get(str(move.get("taskId") or ""))
            if task is None:
                skipped += 1
                continue
            metadata = task.setdefault("metadata", {})
            previous = metadata.get(ROTATION_KEY) or {}
            if str(previous.get("quarter") or "") == quarter:
                skipped += 1
                continue
            metadata["split"] = str(move.get("to") or "")
            task["version"] = int(task.get("version", 1) or 1) + 1
            metadata[ROTATION_KEY] = {
                "quarter": quarter,
                "from": str(move.get("from") or ""),
                "to": str(move.get("to") or ""),
                "rotatedAt": stamp,
            }
            moved += 1
            changed = True
        if changed:
            path = os.path.join(directory, filename)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            touched.add(filename)

    manifest = None
    if refresh_manifest:
        from .corpus import write_manifest  # noqa: PLC0415 - avoid a cycle

        manifest = write_manifest(manifest_path or None)

    return {
        "applied": True,
        "quarter": quarter,
        "moved": moved,
        "skipped": skipped,
        "files": sorted(touched),
        "manifest": (
            {"taskCount": manifest["taskCount"], "bySplit": manifest["bySplit"]}
            if isinstance(manifest, dict) else None
        ),
    }


def render_plan(plan: dict[str, Any]) -> str:
    if not plan.get("ok"):
        return f"rotation: NOT APPLICABLE ({plan.get('reason')})"
    lines = [
        f"rotation {plan.get('quarter')}: "
        f"{plan.get('count')} optimization -> held_out, "
        f"{plan.get('returned')} held_out -> optimization",
        f"seed: {plan.get('seed')}",
        "",
        "| task | from | to | version |",
        "|---|---|---|---|",
    ]
    for move in plan.get("moves") or []:
        lines.append(
            f"| {move.get('taskId')} | {move.get('from')} | "
            f"{move.get('to')} | {move.get('version')} |"
        )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m harness.evaluation.rotation",
        description="Plan or apply a deterministic held_out rotation (dry-run by default).",
    )
    parser.add_argument("--quarter", required=True, help="label, for example 2026Q1")
    parser.add_argument("--count", type=int, default=12,
                        help="optimization tasks to move to held_out (1..50)")
    parser.add_argument("--apply", action="store_true",
                        help="write the plan (default is a dry run)")
    parser.add_argument("--datasets-dir", default="")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        plan = plan_rotation(
            quarter=args.quarter,
            count=args.count,
            datasets_dir=args.datasets_dir or None,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(render_plan(plan))
    if not plan.get("ok"):
        return 1
    if not args.apply:
        print("\n(dry run; re-run with --apply to write it)")
        return 0
    result = apply_rotation(
        plan,
        datasets_dir=args.datasets_dir or None,
        manifest_path=args.manifest or None,
    )
    print(
        f"\napplied: moved={result['moved']} skipped={result['skipped']} "
        f"files={len(result['files'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
