"""``python -m harness.evaluation`` — the offline evaluation gate + CLI.

With no arguments it runs the deterministic evaluation gate (the whole built-in
benchmark at the offline tier), prints the per-category report and exits non-zero
when a gate fails. Any arguments are forwarded to the ``eclipse eval`` CLI.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

from .report import to_markdown


def _run_gate() -> int:
    from .runner import EvaluationRunner, ScriptedAgentInvoker
    from .store import EvaluationStore
    from .tasks import load_all_builtin

    from ..persistence import AgentMemoryStore

    store = AgentMemoryStore()
    eval_store = EvaluationStore(store)
    runner = EvaluationRunner(store, invoker=ScriptedAgentInvoker(store), eval_store=eval_store)
    dataset = load_all_builtin()
    suite = asyncio.run(runner.run_suite(
        dataset.tasks, dataset_name=dataset.name, dataset_version=dataset.version,
        dataset_checksum=dataset.checksum, suite="", trials=1, tier=0, persist=True,
    ))
    print(to_markdown(suite))
    print()
    print("evaluation gate:", "PASS" if suite.passed else "FAIL",
          suite.thresholds.get("failures") if not suite.passed else "")
    return 0 if suite.passed else 1


def main(argv: Optional[list[str]] = None) -> int:
    try:  # a Windows console may be cp1252; never crash on a report glyph.
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _run_gate()
    from .cli import run_cli

    return run_cli(argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
