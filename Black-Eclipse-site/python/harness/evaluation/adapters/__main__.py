"""``python -m harness.evaluation.adapters`` — external adapter listing/gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .base import ADAPTERS
from .gate import run_external_gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C8.2 external benchmark adapters")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    if args.list:
        for adapter in ADAPTERS:
            info = adapter.info()
            print(f"{info.name:<16} cases={info.cases:<3} available={info.available} "
                  f"license={info.license}")
        return 0

    result = run_external_gate()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for row in result["adapters"]:
        print(f"{'PASS' if row.get('passed') else 'FAIL'}  {row['name']:<16} "
              f"cases={row.get('tasks', row.get('cases'))} "
              f"{'available' if row.get('available') else row.get('unmeasuredReason')}")
    print(f"external gate: {'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
