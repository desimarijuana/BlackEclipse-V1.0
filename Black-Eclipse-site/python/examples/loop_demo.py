"""End-to-end check of the loop demo produced by `scripts/graph-loop-demo.mts`.

    npm run demo:loop

Reads the two generated IR documents (parent + pinned body), compiles the parent
with the body supplied exactly as the front door supplies it, runs it through the
real deterministic executor, and asserts the branch outcomes. No store, no clock,
no network — this is the same code path a saved run uses.

Exits non-zero on any mismatch, so it doubles as a smoke test for `flow.repeat`,
`flow.while` and `flow.for_each`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.graph_runtime.compiler import compile_workflow  # noqa: E402
from harness.graph_runtime.executor import GraphExecutor  # noqa: E402
from harness.graph_runtime.model import NodeStatus, RunStatus, WorkflowIR  # noqa: E402
from harness.graph_runtime.nodes import build_default_registry  # noqa: E402

TMP = ROOT / ".black-eclipse" / "tmp"
FAILURES: list[str] = []


def check(label: str, actual: object, expected: object) -> None:
    if actual == expected:
        print(f"  PASS  {label}")
        return
    FAILURES.append(label)
    print(f"  FAIL  {label}\n          expected: {expected!r}\n          actual:   {actual!r}")


def load(name: str) -> dict:
    path = TMP / name
    if not path.exists():
        raise SystemExit(f"missing {path} — run `npx tsx scripts/graph-loop-demo.mts --dry` first")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    body_ir = WorkflowIR.model_validate(load("loop-body.json"))
    parent_ir = WorkflowIR.model_validate(load("loop-parent.json"))

    loop_types = {"flow.repeat", "flow.while", "flow.for_each", "flow.subworkflow"}
    loop_nodes = [n for n in parent_ir.nodes if n.type in loop_types]
    pins = {
        f"{str(n.config.get('workflowId'))}@{int(n.config.get('version', 1))}"
        for n in loop_nodes
    }
    print(f"\n-- loop demo: {len(loop_nodes)} loop node(s), pinned body(ies) {sorted(pins)} " + "-" * 10)

    subworkflows = {pin: body_ir for pin in pins}
    registry = build_default_registry()
    plan = compile_workflow(parent_ir, registry, None, subworkflows)
    check("parent compiles", plan.executable, True)
    if not plan.executable:
        for diagnostic in plan.diagnostics:
            print(f"          {diagnostic.code}: {diagnostic.message}")
        return 1

    run = GraphExecutor(
        parent_ir, plan, registry,
        run_id="grun_loop_demo",
        subworkflows=subworkflows,
    ).execute()

    check("run status", run.status, RunStatus.SUCCEEDED)
    nodes = {record.node_id: record for record in run.node_runs}
    output = run.output or {}
    for record in run.node_runs:
        if record.status == NodeStatus.FAILED:
            print(f"          failed node {record.node_id}: {record.error}")

    # repeat: 12 compounding steps, then the true branch of the target check.
    check("repeat iterations", nodes["repeat"].outputs["iterations"], 12)
    check(
        "repeat → target met",
        output.get("metOut"),
        "12 years: 2252.19 — target met",
    )
    check("repeat → miss branch skipped", nodes["missOut"].status, NodeStatus.SKIPPED)

    # while: keeps going until the balance clears the target.
    check("while iterations", nodes["while"].outputs["iterations"], 11)
    check("while stops after crossing", nodes["while"].outputs["stopped"], False)
    check(
        "while → goal text",
        output.get("whileOut"),
        "Reached 2104.85 after 11 year(s)",
    )

    # for_each: one child run per principal, results in input order.
    check(
        "for_each → projections",
        output.get("eachOut"),
        "After one year: 1070.00 1605.00 2140.00 ",
    )
    check("for_each iterations", nodes["each"].outputs["iterations"], 3)
    check("for_each results ordered", nodes["each"].outputs["results"], [1070.0, 1605.0, 2140.0])

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed")
        return 1
    print("\nAll loop checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
