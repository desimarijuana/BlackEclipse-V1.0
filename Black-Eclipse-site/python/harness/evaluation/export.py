"""Export, import and verify the built-in evaluation corpus.

Our benchmark is OURS: it must be shareable without any external framework.
This module writes the corpus as a portable, self-describing bundle (one entry
per built-in dataset, with each task's own version and a content checksum), can
read such a bundle back, and can VERIFY that a bundle has not been edited —
the checksum is recomputed from the tasks themselves, so a tampered task is
detected rather than trusted.

The bundle is derived data: it carries no production data and no market data,
only the labelled tasks the repository already ships.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional

from ..persistence import now_iso
from .tasks import (
    Dataset,
    available_datasets,
    dataset_checksum,
    dataset_from_dict,
    load_builtin_dataset,
    select_tasks,
)

BUNDLE_VERSION = "1.0.0"


@dataclass
class CorpusEntry:
    name: str
    version: str
    split: str
    task_count: int
    checksum: str
    tasks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "split": self.split,
            "taskCount": self.task_count,
            "checksum": self.checksum,
            "tasks": self.tasks,
        }


def build_corpus(*, splits: Optional[tuple[str, ...]] = None) -> dict[str, Any]:
    """The whole built-in corpus as a portable bundle (in memory)."""
    entries: list[CorpusEntry] = []
    for name in available_datasets():
        dataset = load_builtin_dataset(name)
        tasks = (
            select_tasks(dataset, split=splits[0]) if splits else list(dataset.tasks)
        )
        entries.append(CorpusEntry(
            name=dataset.name,
            version=dataset.version,
            split=str((dataset.metadata or {}).get("split") or ""),
            task_count=len(tasks),
            checksum=dataset_checksum(tasks),
            tasks=[task.to_dict() for task in tasks],
        ))
    return {
        "bundleVersion": BUNDLE_VERSION,
        "exportedAt": now_iso(),
        "datasets": [entry.to_dict() for entry in entries],
        "taskCount": sum(entry.task_count for entry in entries),
    }


def write_corpus(path: str, *, splits: Optional[tuple[str, ...]] = None) -> dict[str, Any]:
    payload = build_corpus(splits=splits)
    target = os.path.abspath(path)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return payload


def read_corpus(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or "datasets" not in payload:
        raise ValueError("a corpus bundle must be an object with a 'datasets' list")
    return payload


def import_corpus(path: str) -> list[Dataset]:
    """Read a bundle back into validated datasets (the task schema is enforced)."""
    payload = read_corpus(path)
    datasets: list[Dataset] = []
    for entry in payload.get("datasets") or []:
        if not isinstance(entry, dict):
            raise ValueError("a corpus entry must be an object")
        datasets.append(dataset_from_dict(entry, source=str(path)))
    return datasets


def verify_corpus(path: str) -> dict[str, Any]:
    """Recompute every dataset checksum and report the ones that changed."""
    payload = read_corpus(path)
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for entry in payload.get("datasets") or []:
        if not isinstance(entry, dict):
            continue
        tasks = entry.get("tasks") or []
        recorded = str(entry.get("checksum") or "")
        try:
            dataset = dataset_from_dict(entry, source=str(path))
            recomputed = dataset_checksum(list(dataset.tasks))
        except Exception as exc:  # noqa: BLE001 - a broken entry is a mismatch
            mismatches.append({
                "dataset": str(entry.get("name") or "?"),
                "reason": f"invalid task: {type(exc).__name__}",
            })
            continue
        checked += 1
        if recorded and recomputed != recorded:
            mismatches.append({
                "dataset": str(entry.get("name") or "?"),
                "recorded": recorded,
                "recomputed": recomputed,
                "taskCount": len(tasks),
            })
    return {
        "ok": not mismatches,
        "checked": checked,
        "taskCount": int(payload.get("taskCount") or 0),
        "mismatches": mismatches,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m harness.evaluation.export",
        description="Export, import or verify the built-in evaluation corpus.",
    )
    parser.add_argument("--out", default="", help="write the bundle to this path")
    parser.add_argument("--verify", default="",
                        help="verify an existing bundle and exit non-zero on a mismatch")
    parser.add_argument("--split", default="",
                        help="export one split only (validation, optimization, ...)")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if args.verify:
        report = verify_corpus(args.verify)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1
    if not args.out:
        print("--out is required (or --verify <bundle>)", file=sys.stderr)
        return 2
    splits = (args.split,) if args.split else None
    payload = write_corpus(args.out, splits=splits)
    print(
        f"wrote {args.out}: {payload['taskCount']} task(s) across "
        f"{len(payload['datasets'])} dataset(s)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
