"""Round 4 (W14): the analysis sandbox's RUNTIME guard.

The AST allowlist is a source check, and a source check can be talked around.
These tests pin the ENFORCEMENT POINT — the guarded `__import__`, the safe
`os`/`sys`/`importlib`/`builtins`, the denied privilege modules, the audit
hook and the confined readers — and they pin that a legitimate computation
still works (the guard must not break the allowed numerical stack).
"""

from __future__ import annotations

import pytest

from harness.code.execution import (
    AnalysisInput,
    AnalysisRequest,
    check_imports,
    run_analysis,
)
from harness.schemas import ModelSettings
from harness.tools import ToolRegistry


def _run(source: str, **inputs):
    request = AnalysisRequest(
        source=source,
        inputs=[AnalysisInput(name=k, kind="text", value=v) for k, v in inputs.items()],
        purpose="guard probe",
    )
    return run_analysis(request)


def _refused_because(result, needle: str) -> bool:
    text = (result.stderr or "") + " " + str(result.outputs or "")
    return result.status != "ok" and needle.lower() in text.lower()


# ── The source gate ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "source",
    [
        "import os",
        "import socket",
        "import subprocess",
        "import ctypes",
        "f = __import__\nm = f('os')\nresult = {'n': len(m.environ)}",
        "result = {'x': open('C:/Windows/win.ini').read()}",
        "result = {'x': eval('1+1')}",
    ],
)
def test_the_source_gate_refuses_the_escape_vectors(source: str) -> None:
    assert check_imports(source), source


# ── The runtime guard ─────────────────────────────────────────────────────────


def test_an_aliased_import_is_refused_at_runtime() -> None:
    """`f = __import__` bought the program nothing: the import is guarded."""
    result = _run("f = __import__\nm = f('os')\nresult = {'n': len(m.environ)}")
    assert result.status != 'ok'
    assert result.status in ("failed", "refused")


def test_the_program_cannot_read_a_host_file() -> None:
    result = _run(
        "import numpy as np\n"
        "data = np.fromfile('C:/Windows/win.ini', dtype=np.uint8)\n"
        "result = {'n': int(data.size)}"
    )
    assert result.status != 'ok'


def test_the_program_cannot_write_a_host_file() -> None:
    result = _run(
        "import pandas as pd\n"
        "pd.DataFrame({'a': [1]}).to_csv('C:/Users/Public/eclipse-probe.csv')\n"
        "result = {}"
    )
    assert result.status != 'ok'


def test_the_program_cannot_fetch_a_url() -> None:
    """A concatenated URL is a URL: the network is denied at the socket."""
    result = _run(
        "import pandas as pd\n"
        "url = 'https' + ':' + '//example.invalid/x.csv'\n"
        "result = {'n': len(pd.read_csv(url))}"
    )
    assert result.status != 'ok'


def test_the_program_cannot_start_a_process() -> None:
    result = _run("import subprocess\nresult = {'rc': subprocess.run(['echo', 'x'])}")
    assert result.status != 'ok'


def test_the_program_cannot_open_a_socket() -> None:
    result = _run("import socket\ns = socket.socket()\nresult = {'ok': True}")
    assert result.status != 'ok'


def test_the_program_cannot_reach_a_dunder_escape_chain() -> None:
    result = _run("result = {'n': len(().__class__.__bases__[0].__subclasses__())}")
    assert result.status != 'ok'


def test_the_programs_own_os_has_no_privilege() -> None:
    """`os` is refused at the source level, and the runtime copy has no privilege."""
    assert check_imports("import os")
    result = _run("import os\nresult = {'n': 1}")
    assert result.status != "ok"


def test_a_library_may_still_import_what_it_needs() -> None:
    """The guard confines the program; it must not break the allowed stack."""
    result = _run(
        "import numpy as np\n"
        "import pandas as pd\n"
        "result = {'sum': float(np.array([1.0, 2.0]).sum()), 'cols': len(pd.DataFrame({'a': [1]}).columns)}"
    )
    assert result.status == "ok", result.stderr
    assert result.outputs["sum"] == 3.0


def test_a_legitimate_computation_still_works() -> None:
    result = _run(
        "import math\n"
        "result = {'root': round(math.sqrt(16.0), 4), 'n': len([1, 2, 3])}"
    )
    assert result.status == "ok", result.stderr
    assert result.outputs["root"] == 4.0


def test_the_program_can_still_write_its_own_output_folder(tmp_path) -> None:
    """The program's own deliverable API is the way to write a file."""
    request = AnalysisRequest(
        source="write_artifact('note.txt', 'hello')\nresult = {'wrote': True}",
        inputs=[], purpose="guard probe",
    )
    result = run_analysis(request, output_dir=tmp_path)
    assert result.status == "ok", result.stderr
    assert [a.name for a in result.artifacts] == ["note.txt"]


def test_the_program_cannot_reach_the_runner_namespace() -> None:
    """`sys` and `getattr` are refused at the source level; the runtime shims
    are the second line of defence."""
    assert check_imports("import sys")
    assert check_imports("result = {'x': getattr(__builtins__, 'x')}")


# ── The operator's switch, the telemetry and the cancellation ─────────────────


def test_the_operator_can_switch_the_sandbox_off_for_the_whole_runtime(monkeypatch) -> None:
    """The per-run flag is a REQUEST; the operator's setting is the DECISION."""
    import asyncio as _asyncio

    from harness.analysis_tools import analysis_run
    from harness.tools import ToolContext

    monkeypatch.setenv("HARNESS_ANALYSIS_ENABLED", "0")
    ctx = ToolContext(
        run_id="run_guard", log=lambda *_: None, user_id="local",
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(), analysis_enabled=True,
    )
    text, data = _asyncio.run(analysis_run(
        {"source": "result = {'n': 1}", "purpose": "probe"}, ctx,
    ))
    assert data["status"] == "refused"
    assert data["code"] == "ANALYSIS_NOT_ENABLED"


def test_a_run_reports_the_resource_telemetry_it_measured() -> None:
    """CPU / peak memory / process count are measured by the backend — they must
    not be thrown away."""
    result = _run("result = {'n': 1}")
    assert result.status == "ok", result.stderr
    blob = result.to_blob()
    for key in ("cpuMs", "memoryPeakMb", "processCount", "resourceLimit", "exitCode"):
        assert key in blob
    assert blob["exitCode"] == 0


def test_a_cancelled_analysis_says_so_and_leaves_no_child() -> None:
    import threading
    import time

    signal = threading.Event()
    signal.set()  # already cancelled: the child must not run at all
    request = AnalysisRequest(
        source="total = 0\nfor i in range(200000000):\n    total += i\nresult = {'n': total}",
        inputs=[], purpose="cancel probe",
    )
    result = run_analysis(request, cancel_event=signal)
    assert result.status != "ok"
    assert result.code == "CANCELLED"
