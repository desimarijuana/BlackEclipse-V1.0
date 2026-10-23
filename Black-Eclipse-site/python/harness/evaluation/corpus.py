"""The corpus manifest: one source of truth for what the benchmark contains.

The task files are the authority; the manifest is a committed, checkable summary
of them. It records each dataset's checksum, task count, split counts, oracle
coverage and canary count, so a corpus change that nobody intended is visible.

The manifest is NOT a second task store: `verify` recomputes everything from the
datasets and compares. It never trusts the file it is checking.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

from ..persistence import now_iso
from .contamination import (
    has_contamination,
    has_oracle,
    is_canary,
    is_oracle_exempt,
    oracle_reason,
)
from .tasks import (
    SPLITS,
    available_datasets,
    dataset_checksum,
    load_builtin_dataset,
    task_split,
)

MANIFEST_VERSION = "1.0.0"
MANIFEST_PATH = os.path.join(
    os.path.dirname(__file__), "baselines", "corpus_manifest.json",
)


def _dataset_split(dataset: Any) -> str:
    return str((dataset.metadata or {}).get("split") or "")


def build_manifest(*, recorded_at: Optional[str] = None) -> dict[str, Any]:
    """Summarize every built-in dataset (checksums recomputed from the tasks)."""
    entries: list[dict[str, Any]] = []
    totals_by_split: dict[str, int] = {}
    total_tasks = 0
    total_oracle = 0
    total_exempt = 0
    total_canary = 0
    total_live = 0

    for name in available_datasets():
        dataset = load_builtin_dataset(name)
        dataset_split = _dataset_split(dataset)
        dataset_meta = dataset.metadata or {}
        by_split: dict[str, int] = {}
        oracle = 0
        exempt = 0
        canary = 0
        live = 0
        no_metadata: list[str] = []
        for task in dataset.tasks:
            split = task_split(task, dataset_split)
            by_split[split] = by_split.get(split, 0) + 1
            totals_by_split[split] = totals_by_split.get(split, 0) + 1
            if has_oracle(task):
                oracle += 1
            if is_oracle_exempt(task, dataset_meta):
                exempt += 1
            if is_canary(task):
                canary += 1
            if task.live_only:
                live += 1
            if not has_contamination(task, dataset_meta):
                no_metadata.append(task.id)
        entries.append({
            "name": dataset.name,
            "version": dataset.version,
            "checksum": dataset_checksum(dataset.tasks),
            "taskCount": len(dataset.tasks),
            "bySplit": dict(sorted(by_split.items())),
            "oracleCount": oracle,
            "oracleExemptCount": exempt,
            "canaryCount": canary,
            "liveOnly": live,
            "reviewed": bool(dataset.reviewed),
            "reviewer": dataset.reviewer,
            "missingContamination": no_metadata,
        })
        total_tasks += len(dataset.tasks)
        total_oracle += oracle
        total_exempt += exempt
        total_canary += canary
        total_live += live

    return {
        "manifestVersion": MANIFEST_VERSION,
        "recordedAt": recorded_at or now_iso(),
        "taskCount": total_tasks,
        "datasetCount": len(entries),
        "bySplit": dict(sorted(totals_by_split.items())),
        "oracleCount": total_oracle,
        "oracleExemptCount": total_exempt,
        "oracleCoverage": (
            round(total_oracle / total_tasks, 6) if total_tasks else 0.0
        ),
        "canaryCount": total_canary,
        "liveOnly": total_live,
        "datasets": entries,
    }


def write_manifest(path: Optional[str] = None) -> dict[str, Any]:
    payload = build_manifest()
    target = os.path.abspath(path or MANIFEST_PATH)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return payload


def read_manifest(path: Optional[str] = None) -> dict[str, Any]:
    with open(os.path.abspath(path or MANIFEST_PATH), encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or "datasets" not in payload:
        raise ValueError("a corpus manifest must be an object with a 'datasets' list")
    return payload


def verify_manifest(path: Optional[str] = None) -> dict[str, Any]:
    """Recompute the corpus and report every difference from the manifest."""
    recorded = read_manifest(path)
    current = build_manifest(recorded_at=str(recorded.get("recordedAt") or ""))
    recorded_by_name = {
        str(item.get("name") or ""): item
        for item in recorded.get("datasets") or []
        if isinstance(item, dict)
    }
    current_by_name = {
        str(item.get("name") or ""): item for item in current["datasets"]
    }
    mismatches: list[dict[str, Any]] = []

    for name in sorted(set(recorded_by_name) - set(current_by_name)):
        mismatches.append({"dataset": name, "reason": "missing_from_corpus"})
    for name in sorted(set(current_by_name) - set(recorded_by_name)):
        mismatches.append({"dataset": name, "reason": "new_in_corpus"})

    for name in sorted(set(recorded_by_name) & set(current_by_name)):
        before = recorded_by_name[name]
        after = current_by_name[name]
        for field in (
            "version", "checksum", "taskCount", "bySplit",
            "oracleCount", "oracleExemptCount", "missingContamination",
        ):
            if before.get(field) != after.get(field):
                mismatches.append({
                    "dataset": name,
                    "field": field,
                    "recorded": before.get(field),
                    "current": after.get(field),
                })

    for field in (
        "taskCount", "bySplit", "oracleCount", "oracleExemptCount", "canaryCount",
    ):
        if recorded.get(field) != current.get(field):
            mismatches.append({
                "dataset": "*",
                "field": field,
                "recorded": recorded.get(field),
                "current": current.get(field),
            })

    return {
        "ok": not mismatches,
        "checked": len(current_by_name),
        "taskCount": current["taskCount"],
        "oracleCoverage": current["oracleCoverage"],
        "canaryCount": current["canaryCount"],
        "bySplit": current["bySplit"],
        "mismatches": mismatches,
    }


def validate_tasks(*, strict: bool = False) -> dict[str, Any]:
    """Report authoring gaps: missing oracle, contamination metadata, bad split.

    Legacy tasks are reported, not failed. `strict` makes the absence of an
    oracle or contamination metadata an error, which is the rule for NEW work.
    A task (or dataset) marked `oracleExempt` with a reason is intentional, so
    strict treats it as covered: the legacy fixtures that cannot be recomputed
    are documented rather than quietly deleted.
    """
    issues: list[dict[str, Any]] = []
    counts = {
        "tasks": 0, "withOracle": 0, "oracleExempt": 0,
        "withContamination": 0, "canaries": 0,
    }
    for name in available_datasets():
        dataset = load_builtin_dataset(name)
        dataset_split = _dataset_split(dataset)
        dataset_meta = dataset.metadata or {}
        for task in dataset.tasks:
            counts["tasks"] += 1
            exempt = is_oracle_exempt(task, dataset_meta)
            if exempt:
                counts["oracleExempt"] += 1
            if has_oracle(task):
                counts["withOracle"] += 1
            elif exempt:
                if not oracle_reason(task, dataset_meta):
                    issues.append({
                        "dataset": name, "task": task.id,
                        "issue": "missing_oracle_reason",
                    })
            else:
                issues.append({
                    "dataset": name, "task": task.id, "issue": "missing_oracle",
                })
            if has_contamination(task, dataset_meta):
                counts["withContamination"] += 1
            elif not exempt:
                issues.append({
                    "dataset": name, "task": task.id,
                    "issue": "missing_contamination",
                })
            if is_canary(task):
                counts["canaries"] += 1
            split = task_split(task, dataset_split)
            if split not in SPLITS:
                issues.append({
                    "dataset": name, "task": task.id,
                    "issue": "unknown_split", "split": split,
                })
    errors = [item for item in issues if item["issue"] == "unknown_split"]
    if strict:
        errors = list(issues)
    return {"ok": not errors, "strict": bool(strict), "counts": counts, "issues": issues,
            "errors": errors}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m harness.evaluation.corpus",
        description="Build, verify or audit the built-in evaluation corpus manifest.",
    )
    parser.add_argument("--build", nargs="?", const=MANIFEST_PATH, default="",
                        help="write the manifest from the current datasets")
    parser.add_argument("--verify", nargs="?", const=MANIFEST_PATH, default="",
                        help="verify the current datasets against the manifest")
    parser.add_argument("--audit", action="store_true",
                        help="report authoring gaps (oracle/contamination/split)")
    parser.add_argument("--strict", action="store_true",
                        help="make missing oracle/contamination metadata an error")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if args.build:
        payload = write_manifest(args.build)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(
                f"wrote {args.build}: {payload['taskCount']} task(s), "
                f"{payload['datasetCount']} dataset(s), "
                f"oracle coverage {payload['oracleCoverage']:.3f}"
            )
        return 0
    if args.verify:
        report = verify_manifest(args.verify)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(
                f"corpus manifest: {'PASS' if report['ok'] else 'FAIL'} "
                f"({report['taskCount']} tasks, "
                f"{len(report['mismatches'])} mismatch(es))"
            )
            for item in report["mismatches"]:
                print(f"  - {item}")
        return 0 if report["ok"] else 1
    if args.audit:
        report = validate_tasks(strict=args.strict)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            counts = report["counts"]
            print(
                f"corpus audit: {'PASS' if report['ok'] else 'FAIL'} "
                f"tasks={counts['tasks']} oracle={counts['withOracle']} "
                f"exempt={counts['oracleExempt']} "
                f"contamination={counts['withContamination']} "
                f"canaries={counts['canaries']}"
            )
            for item in report["errors"][:20]:
                print(f"  - {item}")
        return 0 if report["ok"] else 1
    _parser().print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
