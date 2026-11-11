"""Round 5 / C2.1: the run's composition objects, not a 45-kwarg function."""

from __future__ import annotations

import inspect

from harness import graph as graph_module
from harness.run_scope import RunScope, RunSpec


def test_build_graph_takes_only_the_two_composition_objects():
    parameters = list(inspect.signature(graph_module.build_graph).parameters)
    assert parameters == ["spec", "scope"], parameters


def test_run_scope_carries_the_reusable_services():
    scope = RunScope(registry="r", data_bridge="b", store="s")
    assert scope.registry == "r"
    assert scope.data_bridge == "b"
    assert scope.store == "s"
    assert scope.bus is None
    assert scope.market is None


def test_run_spec_copies_the_allowlist_so_a_run_cannot_mutate_the_caller():
    allowed = {"a", "b"}
    spec = RunSpec(request=object(), emitter=object(), allowed=allowed)
    spec.allowed.add("c")
    assert allowed == {"a", "b"}
    assert spec.allowed == {"a", "b", "c"}
