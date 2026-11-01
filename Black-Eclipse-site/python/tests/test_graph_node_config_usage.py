"""Every declared config field must be READ by the code that consumes it.

`logic.stop` declared `status: succeeded|failed` in both registries, showed it in
the inspector, and the executor never looked at it — so "stop with failure"
silently succeeded. Nothing failed, because the contract test only checked that
the two registries agreed with each other, not that either was honoured.

This test closes that class of defect for the LOGIC / CONTROL-FLOW pack: for
every such node, each declared config field name must appear as a string literal
in the source of the function that consumes it. Orchestrated nodes (subworkflow +
the three loops) are consumed by the scheduler instead of an executor, so their
fields are allowlisted explicitly.

Scope note: other packs (finance, quant, research, trading, agent) read config
through shared helpers and are not covered yet; tightening them is a separate
audit, and `IGNORED_ELSEWHERE` records the ones already known to bypass a direct
literal.
"""

from __future__ import annotations

import inspect

import pytest

from harness.graph_runtime.nodes import build_default_registry

# Fields consumed by the SCHEDULER (`GraphExecutor._run_loop` /
# `_run_subworkflow`), not by a node executor function.
SCHEDULER_FIELDS = {
    "flow.subworkflow": {"workflowId", "version"},
    "flow.for_each": {
        "workflowId", "version", "maxIterations", "maxDurationMs", "continueOnError",
    },
    "flow.repeat": {"workflowId", "version", "count", "maxDurationMs"},
    "flow.while": {
        "workflowId", "version", "condition", "maxIterations", "maxDurationMs",
    },
}

IN_SCOPE = ("logic.", "flow.")


def _consumer_source(definition) -> str:
    if definition.executor is not None:
        return inspect.getsource(definition.executor)
    # Orchestrated: the scheduler reads these keys.
    from harness.graph_runtime import executor as executor_module  # noqa: PLC0415

    return inspect.getsource(executor_module.GraphExecutor._run_loop) + inspect.getsource(
        executor_module.GraphExecutor._run_subworkflow
    )


@pytest.mark.parametrize(
    "definition",
    [
        d for d in build_default_registry().definitions()
        if d.config_fields and d.type.startswith(IN_SCOPE)
    ],
    ids=lambda d: f"{d.type}@{d.version}",
)
def test_every_declared_config_field_is_read(definition):
    source = _consumer_source(definition)
    ignored = [
        field.name
        for field in definition.config_fields
        if field.name not in SCHEDULER_FIELDS.get(definition.type, set())
        and f'"{field.name}"' not in source
    ]
    assert not ignored, (
        f"{definition.type} declares config field(s) {ignored} that its executor "
        "never reads. Either implement them or stop declaring them — a config "
        "field the user can edit and the runtime ignores is a lie."
    )


def test_known_scheduler_fields_match_the_scheduler_source():
    """The allowlist above must stay honest: the scheduler has to read them."""
    from harness.graph_runtime import executor as executor_module  # noqa: PLC0415

    source = inspect.getsource(executor_module.GraphExecutor._run_loop) + inspect.getsource(
        executor_module.GraphExecutor._run_subworkflow
    )
    for node_type, fields in SCHEDULER_FIELDS.items():
        for field in fields:
            assert f'"{field}"' in source, (
                f"{node_type}.{field} is allowlisted as scheduler-consumed, but the "
                "scheduler never reads it."
            )


def test_the_pack_is_actually_covered():
    """A new logic/flow node must not silently escape the invariant above."""
    types = {
        d.type for d in build_default_registry().definitions()
        if d.type.startswith(IN_SCOPE)
    }
    assert {
        "logic.condition", "logic.switch", "logic.merge", "logic.map",
        "logic.filter", "logic.reduce", "logic.wait", "logic.stop",
        "logic.aggregate", "logic.deduplicate", "flow.gate",
        "flow.subworkflow", "flow.for_each", "flow.repeat", "flow.while",
    } <= types
