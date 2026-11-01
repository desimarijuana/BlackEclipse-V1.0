"""End-to-end demo of the transform nodes, runnable without a graph or a UI.

    npm run demo:transform
    python python/examples/transform_demo.py

It is self-checking: every section asserts a real value and the process exits
non-zero on any mismatch, so this doubles as a smoke test for the same executors
the test suite exercises. No network, no store, no clock.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Works with any interpreter: the harness package lives one level up.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.graph_runtime.compiler import compile_workflow  # noqa: E402
from harness.graph_runtime.executor import GraphExecutor  # noqa: E402
from harness.graph_runtime.model import ExecutionMode, WorkflowIR  # noqa: E402
from harness.graph_runtime.nodes import (  # noqa: E402
    build_default_registry,
    evaluate_formula,
    render_template,
)
from harness.graph_runtime.registry import NodeExecContext  # noqa: E402

REGISTRY = build_default_registry()
FAILURES: list[str] = []


def section(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 62 - len(title)))


def check(label: str, actual: object, expected: object) -> None:
    if actual == expected:
        print(f"  PASS  {label}")
        return
    FAILURES.append(label)
    print(f"  FAIL  {label}\n          expected: {expected!r}\n          actual:   {actual!r}")


def exec_node(node_type: str, inputs: dict, config: dict | None = None) -> dict:
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None, node_type
    return definition.executor(NodeExecContext(
        node_id="demo",
        run_id="demo",
        mode=ExecutionMode.RESEARCH,
        inputs=inputs,
        config=config or {},
    ))


# ── template ────────────────────────────────────────────────────────────────
section("template: row block, formats, escape")
rows = [
    {"symbol": "AAPL", "close": 190.4567, "ts": "2026-10-31T15:00:00Z"},
    {"symbol": "MSFT", "close": 410.0, "ts": "2026-10-31T15:00:00Z"},
]
template = (
    "{{#each a}}{{index}}. {{symbol}} {{close:.2f}} ({{ts:date}})\n{{/each}}"
    r"literal: \{{not a placeholder}}"
)
def raises(call) -> bool:
    try:
        call()
    except ValueError:
        return True
    return False


check(
    "two rows, dotted paths, .2f, ISO date, literal brace",
    render_template(template, {"a": rows}),
    "0. AAPL 190.46 (2026-10-31)\n1. MSFT 410.00 (2026-10-31)\nliteral: {{not a placeholder}}",
)
check(
    "a null required value is an error",
    raises(lambda: render_template("{{a}}", {"a": None})),
    True,
)


# ── formula ─────────────────────────────────────────────────────────────────
section("formula: guards, half-up rounding, precedence, series")
check("if() never evaluates the untaken branch", evaluate_formula("if(b != 0, a / b, 0)", {"a": 10.0, "b": 0.0}), 0.0)
check("round() is half-up, not banker's", evaluate_formula("round(2.5)", {}), 3.0)
check("power binds tighter than unary minus", evaluate_formula("-2 ** 2", {}), -4.0)
check("clamp()", evaluate_formula("clamp(x, 0, 100)", {"x": 137.0}), 100.0)
check(
    "a series payload resolves to its latest point",
    exec_node("transform.formula", {"x": {"last": 3.4}}, {"expression": "x * 2"})["result"],
    6.8,
)

# ── select / sort ───────────────────────────────────────────────────────────
section("select + sort: aliases, missing policy, numeric keys, nulls last")
nested = [
    {"symbol": "AAPL", "close": "9.5", "fundamentals": {"pe": 30.1}},
    {"symbol": "MSFT", "close": "100", "fundamentals": {}},
]
check(
    "alias=path selects a nested field",
    exec_node("transform.select", {"rows": nested}, {"fields": "symbol, pe=fundamentals.pe"})["rows"],
    [{"symbol": "AAPL", "pe": 30.1}, {"symbol": "MSFT", "pe": None}],
)
check(
    "onMissing=drop removes the incomplete row",
    exec_node(
        "transform.select", {"rows": nested},
        {"fields": "symbol, pe=fundamentals.pe", "onMissing": "drop"},
    )["dropped"],
    1,
)
check(
    "\"100\" sorts after \"9.5\" because numeric strings are numbers",
    [row["close"] for row in exec_node("transform.sort_limit", {"rows": nested}, {"field": "close"})["rows"]],
    ["9.5", "100"],
)
check(
    "nulls stay last even in desc",
    [row["v"] for row in exec_node(
        "transform.sort_limit",
        {"rows": [{"v": 2}, {"v": None}, {"v": 1}]},
        {"field": "v", "order": "desc"},
    )["rows"]],
    [2, 1, None],
)

# ── join ────────────────────────────────────────────────────────────────────
section("join: composite keys, explicit duplicates, anti, suffix")
left = [{"symbol": "AAPL", "date": "2026-01-02", "close": 100.0}]
right = [
    {"symbol": "AAPL", "date": "2026-01-02", "close": 100.5, "dividend": 0.24},
    {"symbol": "AAPL", "date": "2026-01-02", "close": 100.5, "dividend": 0.26},
    {"symbol": "MSFT", "date": "2026-01-02", "pe": 38.0},
]
dupes = exec_node(
    "transform.join", {"left": left, "right": right},
    {"leftKey": "symbol,date", "onDuplicate": "all", "suffix": "_r"},
)
check("composite key, every duplicate kept, colliding column suffixed",
      (len(dupes["rows"]), dupes["rows"][0]["close_r"]), (2, 100.5))
check(
    "anti join keeps the left row with no match",
    exec_node(
        "transform.join",
        {"left": [{"symbol": "JPM"}, {"symbol": "AAPL"}], "right": [{"symbol": "AAPL"}]},
        {"leftKey": "symbol", "how": "anti"},
    )["rows"],
    [{"symbol": "JPM"}],
)
check(
    "1 and 1.0 and \"1\" are one key",
    exec_node("transform.join", {"left": [{"id": 1}], "right": [{"id": "1.0"}]}, {"leftKey": "id"})["matched"],
    1,
)

# ── aggregate / deduplicate ─────────────────────────────────────────────────
section("aggregate + deduplicate: statistics and one identity rule")
series = [{"sector": "9", "close": 100}, {"sector": "10", "close": 300}, {"sector": "9", "close": 200}]
for op, extra, expected in [
    ("sum", {}, 600.0),
    ("median", {}, 200.0),
    ("stddev", {}, 100.0),
    ("percentile", {"percentile": 25}, 150.0),
]:
    label = f"{op}(p{extra['percentile']})" if "percentile" in extra else op
    check(label, exec_node("logic.aggregate", {"items": series},
                           {"field": "close", "op": op, **extra})["value"], expected)
grouped = exec_node("logic.aggregate", {"items": series},
                    {"field": "close", "op": "sum", "groupBy": "sector"})
check("groups sort by value (9 before 10)",
      [(group["sector"], group["value"]) for group in grouped["groups"]],
      [("9", 300.0), ("10", 300.0)])
deduped = exec_node("logic.deduplicate", {"items": [
    {"id": 1, "v": "a"}, {"id": 1.0, "v": "b"}, {"id": "1", "v": "c"}, {"id": 2, "v": "d"},
]}, {"keys": "id"})
check("1, 1.0 and \"1\" collapse", ([row["v"] for row in deduped["items"]], deduped["dropped"]), (["a", "d"], 2))

# ── control ports ───────────────────────────────────────────────────────────
section("control ports: a false branch skips the node and its chain")


def run_gated(threshold: str) -> dict:
    nodes = [
        {"id": "trig", "type": "trigger.manual", "version": "1.0.0", "config": {}, "layout": {"x": 0, "y": 0}},
        {"id": "v", "type": "data.value", "version": "1.0.0",
         "config": {"dataType": "number", "value": threshold}, "layout": {"x": 0, "y": 0}},
        {"id": "cond", "type": "logic.condition", "version": "1.0.0",
         "config": {"operator": "gt", "compareTo": "1"}, "layout": {"x": 0, "y": 0}},
        {"id": "f", "type": "transform.formula", "version": "1.0.0",
         "config": {"expression": "x * 2"}, "layout": {"x": 0, "y": 0}},
        {"id": "out", "type": "output.result", "version": "1.0.0", "config": {}, "layout": {"x": 0, "y": 0}},
    ]
    edges = [
        {"id": "e1", "source": "trig", "sourceHandle": "start", "target": "v", "targetHandle": "in"},
        {"id": "e2", "source": "v", "sourceHandle": "value", "target": "cond", "targetHandle": "value"},
        {"id": "e3", "source": "cond", "sourceHandle": "true", "target": "f", "targetHandle": "in"},
        {"id": "e4", "source": "v", "sourceHandle": "value", "target": "f", "targetHandle": "x"},
        {"id": "e5", "source": "f", "sourceHandle": "result", "target": "out", "targetHandle": "value"},
    ]
    ir = WorkflowIR.model_validate({
        "irVersion": 1, "id": "demo", "name": "demo",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    })
    run = GraphExecutor(ir, compile_workflow(ir, REGISTRY), REGISTRY, run_id="demo").execute()
    return {record.node_id: record for record in run.node_runs}


gated = run_gated("0")
check("false branch: formula skipped", gated["f"].status.value, "skipped")
check("false branch: control_not_fired", gated["f"].error_code, "control_not_fired")
check("true branch: formula runs", run_gated("5")["f"].status.value, "succeeded")

print()
if FAILURES:
    print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
    sys.exit(1)
print("All transform-node checks passed.")
