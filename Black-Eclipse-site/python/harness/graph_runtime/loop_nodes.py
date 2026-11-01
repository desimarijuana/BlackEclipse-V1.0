"""Bounded loop nodes (Graph Studio Phase 4).

A loop is a NODE with an explicit bound, never a graph cycle. The body is a
pinned saved workflow, so it is compiled with the SAME grants and runs through
the existing subworkflow executor. Every iteration gets its own durable child
run id (`<parent>:<node>:i<N>`), which doubles as the loop checkpoint: a parent
resumed after a crash reuses a succeeded child output instead of re-running it.

Three shapes, all bounded by `maxIterations` and an optional wall-clock budget:

- `flow.for_each` iterates an array; the body receives each item and the node
  returns the collected results.
- `flow.repeat` runs the body `count` times, passing the previous output on.
- `flow.while` runs while a safe numeric condition holds.
"""

from __future__ import annotations

from .model import ExecutionMode, PortDef, PortKind, PortType, SideEffect
from .registry import ConfigField, NodeDef

_ALL = tuple(ExecutionMode)
MAX_ITERATIONS = 1_000
MAX_DURATION_MS = 24 * 60 * 60 * 1_000


def _pinned_fields() -> tuple[ConfigField, ...]:
    return (
        ConfigField("workflowId", "string", "", max_length=80),
        ConfigField("version", "integer", 1, minimum=1, maximum=1_000_000),
    )


def build_loop_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="flow.for_each", version="1.0.0", label="For each",
            category="logic", orchestrated=True,
            inputs=(
                PortDef(id="in", name="Run", type=PortType.ANY, kind=PortKind.CONTROL, optional=True),
                PortDef(id="items", name="Items", type=PortType.ARRAY),
            ),
            outputs=(
                PortDef(id="results", name="Results", type=PortType.ARRAY),
                PortDef(id="iterations", name="Iterations", type=PortType.NUMBER),
                PortDef(id="stopped", name="Stopped early", type=PortType.BOOLEAN),
                PortDef(id="done", name="Done", type=PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                *_pinned_fields(),
                ConfigField("maxIterations", "integer", 100, minimum=1, maximum=MAX_ITERATIONS),
                ConfigField("maxDurationMs", "integer", 0, minimum=0, maximum=MAX_DURATION_MS),
                ConfigField("continueOnError", "boolean", False),
            ),
            capabilities=(), side_effects=SideEffect.NONE, allowed_modes=_ALL,
            timeout_ms=3_600_000,
            metadata={"docs": (
                "Runs a pinned body workflow once per array item, up to maxIterations. "
                "Each iteration is a durable child run; a resumed parent reuses a "
                "succeeded iteration. A failed iteration fails the node unless "
                "continueOnError is on."
            )},
        ),
        NodeDef(
            type="flow.repeat", version="1.0.0", label="Repeat",
            category="logic", orchestrated=True,
            inputs=(
                PortDef(id="in", name="Run", type=PortType.ANY, kind=PortKind.CONTROL, optional=True),
                PortDef(id="input", name="Input", type=PortType.ANY, optional=True),
            ),
            outputs=(
                PortDef(id="state", name="State", type=PortType.ANY),
                PortDef(id="iterations", name="Iterations", type=PortType.NUMBER),
                PortDef(id="stopped", name="Stopped early", type=PortType.BOOLEAN),
                PortDef(id="done", name="Done", type=PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                *_pinned_fields(),
                ConfigField("count", "integer", 1, minimum=1, maximum=MAX_ITERATIONS),
                ConfigField("maxDurationMs", "integer", 0, minimum=0, maximum=MAX_DURATION_MS),
                ConfigField("continueOnError", "boolean", False),
            ),
            capabilities=(), side_effects=SideEffect.NONE, allowed_modes=_ALL,
            timeout_ms=3_600_000,
            metadata={"docs": (
                "Runs a pinned body workflow `count` times, passing each output as the "
                "next input. Bounded and durable per iteration."
            )},
        ),
        NodeDef(
            type="flow.while", version="1.0.0", label="While",
            category="logic", orchestrated=True,
            inputs=(
                PortDef(id="in", name="Run", type=PortType.ANY, kind=PortKind.CONTROL, optional=True),
                PortDef(id="input", name="Initial state", type=PortType.ANY, optional=True),
            ),
            outputs=(
                PortDef(id="state", name="Final state", type=PortType.ANY),
                PortDef(id="iterations", name="Iterations", type=PortType.NUMBER),
                PortDef(id="stopped", name="Stopped early", type=PortType.BOOLEAN),
                PortDef(id="done", name="Done", type=PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                *_pinned_fields(),
                ConfigField("condition", "string", "value > 0", max_length=500),
                ConfigField("maxIterations", "integer", 100, minimum=1, maximum=MAX_ITERATIONS),
                ConfigField("maxDurationMs", "integer", 0, minimum=0, maximum=MAX_DURATION_MS),
                ConfigField("continueOnError", "boolean", False),
            ),
            capabilities=(), side_effects=SideEffect.NONE, allowed_modes=_ALL,
            timeout_ms=3_600_000,
            metadata={"docs": (
                "Runs a pinned body workflow while a safe numeric condition holds "
                "(value/index/iterations are in scope). Bounded by maxIterations and "
                "maxDurationMs; neither cap may be omitted in the UI."
            )},
        ),
    ]


__all__ = ["build_loop_nodes"]
