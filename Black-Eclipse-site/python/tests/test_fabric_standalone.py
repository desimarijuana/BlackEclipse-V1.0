"""The dedicated worker process is opt-in and takes a worker selection."""

from __future__ import annotations

from harness.fabric.standalone import _parse_args


def test_standalone_parses_a_worker_selection():
    assert _parse_args([]).workers is None
    assert _parse_args(["--workers", "graph,agent"]).workers == "graph,agent"
