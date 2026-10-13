"""Phase 8 G1/G3/G5 — analysis execution, limits, reproducibility, imports.

Runs the real vendored interpreter through the Phase 3 sandbox when available; a
missing sandbox/interpreter is asserted as an honest refusal, never a pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.code import sandbox as sandbox_mod
from harness.code.execution import (
    IMPORT_NOT_ALLOWED,
    INPUT_INVALID,
    AnalysisInput,
    AnalysisRequest,
    SANDBOX_UNAVAILABLE,
    check_imports,
    input_digest,
    interpreter_path,
    run_analysis,
)


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


requires_runner = pytest.mark.skipif(not _has_runner(), reason="sandbox/interpreter unavailable")


def _req(source: str, *, inputs=None, purpose="test", timeout_s=60) -> AnalysisRequest:
    return AnalysisRequest(
        source=source, inputs=inputs or [], purpose=purpose, timeout_s=timeout_s,
    )


# ── G1: execution + limits ───────────────────────────────────────────────────


@requires_runner
def test_simple_computation_returns_outputs_and_computed_provenance():
    result = run_analysis(_req(
        "prices = inputs['prices']\n"
        "result = {'first': prices[0], 'last': prices[-1], 'change': prices[-1] - prices[0]}\n",
        inputs=[AnalysisInput(name="prices", kind="series", value=[10, 11, 12])],
        purpose="what did this do",
    ))
    assert result.status == "ok", result.stderr
    assert result.outputs["change"] == 2
    assert result.provenance is not None
    assert result.provenance.kind == "computed"
    assert result.source_digest and result.interpreter


def test_missing_input_is_input_invalid():
    # A kind mismatch is refused before any execution (INPUT_INVALID).
    request = _req("result = {}\n", inputs=[AnalysisInput(name="prices", kind="series", value="not-a-list")])
    result = run_analysis(request)
    assert result.status == "refused"
    assert result.code == INPUT_INVALID


@requires_runner
def test_failing_program_reports_failed_not_ok():
    result = run_analysis(_req("raise ValueError('boom')\n", purpose="fail on purpose"))
    assert result.status == "failed"
    assert result.provenance is None


# ── G3: reproducibility ──────────────────────────────────────────────────────


@requires_runner
def test_reproducible_same_source_and_inputs_same_digest(tmp_path):
    source = "result = {'sum': sum(inputs['xs'])}\n"
    inputs = [AnalysisInput(name="xs", kind="series", value=[1, 2, 3, 4])]
    first = run_analysis(_req(source, inputs=inputs, purpose="sum"), output_dir=tmp_path / "a")
    second = run_analysis(_req(source, inputs=inputs, purpose="sum"), output_dir=tmp_path / "b")
    assert first.status == "ok" and second.status == "ok"
    # Same source ⇒ same source digest; same inputs ⇒ same input digests.
    assert first.source_digest == second.source_digest
    assert first.input_digests == second.input_digests
    assert first.outputs == second.outputs
    # The package-lock digest is recorded so a rerun can be matched.
    assert first.package_lock_digest is not None


@requires_runner
def test_artifact_digest_is_identical_for_identical_bytes(tmp_path):
    source = "write_artifact('out.json', {'a': 1})\nresult = {'wrote': 'out.json'}\n"
    a = run_analysis(_req(source, purpose="artifact"), output_dir=tmp_path / "a")
    b = run_analysis(_req(source, purpose="artifact"), output_dir=tmp_path / "b")
    assert a.status == "ok" and b.status == "ok"
    assert len(a.artifacts) == 1 and len(b.artifacts) == 1
    assert a.artifacts[0].sha256 == b.artifacts[0].sha256
    assert a.artifacts[0].media_type == "application/json"


# ── G5: imports + network ────────────────────────────────────────────────────


def test_imports_outside_the_allowlist_are_flagged_by_ast():
    assert check_imports("import math") == []
    assert "os" in check_imports("import os")
    assert "socket" in check_imports("import socket")
    assert "subprocess" in check_imports("from subprocess import run")
    assert "numpy" not in check_imports("import numpy as np")


def test_dynamic_import_is_flagged():
    assert check_imports("__import__('os')")


def test_syntax_error_is_source_invalid():
    from harness.code.execution import SOURCE_INVALID, AnalysisError

    with pytest.raises(AnalysisError) as info:
        check_imports("def (")
    assert info.value.code == SOURCE_INVALID


def test_disallowed_import_refuses_without_running():
    result = run_analysis(_req("import os\nresult = {}\n", purpose="bad import"))
    assert result.status == "refused"
    assert result.code == IMPORT_NOT_ALLOWED


@requires_runner
def test_network_import_is_refused():
    result = run_analysis(_req("import socket\nresult = {}\n", purpose="network"))
    assert result.status == "refused"
    assert result.code == IMPORT_NOT_ALLOWED


@requires_runner
def test_timeout_is_reported():
    # A busy loop with no imports — the sandbox must kill it on the deadline.
    result = run_analysis(_req(
        "x = 0\nwhile x >= 0:\n    x += 1\n",
        purpose="spin forever", timeout_s=1,
    ))
    assert result.status == "timed_out"
    assert result.code == "TIMED_OUT"


def test_input_digest_is_stable():
    assert input_digest([1, 2, 3]) == input_digest([1, 2, 3])
    assert input_digest([1, 2, 3]) != input_digest([3, 2, 1])


# ── R3-02: reflection/network escapes and the declared limits ────────────────


@pytest.mark.parametrize(
    "source",
    [
        "x = ().__class__.__bases__[0].__subclasses__()\nresult = {}",
        "result = (lambda: 0).__globals__",
        "result = getattr(inputs, '__class__')",
        "result = globals()",
        "result = __builtins__",
        "import pandas as pd\nresult = pd.read_csv('https://example.com/x.csv')",
    ],
)
def test_escape_and_network_vectors_are_flagged(source: str) -> None:
    assert check_imports(source), source


def test_normal_analysis_source_is_clean() -> None:
    source = (
        "import numpy as np\n"
        "values = np.array(inputs['returns'])\n"
        "result = {'mean': float(values.mean())}\n"
    )
    assert check_imports(source) == []


def test_analysis_run_spec_enforces_the_declared_limits(monkeypatch):
    from harness.code import execution as ex

    captured = {}

    def fake_run(spec, *, cancel_event=None):
        captured["spec"] = spec
        from pathlib import Path as _Path

        _Path(spec.argv[3]).write_text('{"ok": true, "outputs": {}}', encoding="utf-8")
        return sandbox_mod.RawResult(
            exit_code=0, timed_out=False, killed=False, cancelled=False,
            output="", truncated=False, total_chars=0, duration_ms=1, backend="test",
        )

    monkeypatch.setattr(ex.sandbox_mod, "run", fake_run)
    monkeypatch.setattr(ex, "interpreter_path", lambda: "python")

    result = ex.run_analysis(
        ex.AnalysisRequest(source="result = {}", purpose="limits", timeout_s=30)
    )
    assert result.status == "ok"
    spec = captured["spec"]
    # The declared limits are ENFORCED (passed to the one sandbox primitive).
    assert spec.network is False
    assert spec.memory_mb == ex.DEFAULT_MEMORY_MB
    assert spec.process_limit == ex.MAX_PROCESSES
    # CPU is a total-burn guard ABOVE the wall clock (600s), so a single process
    # is still stopped by its timeout first.
    assert spec.cpu_seconds == ex.MAX_CPU_SECONDS
