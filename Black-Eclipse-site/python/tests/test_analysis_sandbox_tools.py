"""Phase 3 — read-only `eclipse_tools` inside the analysis sandbox.

The sandbox never gets a live data pipe. A read is a request that the host
validates against the allowlist, resolves through the existing DataBridge,
memoizes, and replays. These tests pin the gate, the replay, the bounds, and the
rule that fetched payloads do not enter the model-facing result.
"""

from __future__ import annotations

import asyncio
import json
import threading

import pytest

from harness.analysis_tools import analysis_run
from harness.code import sandbox as sandbox_mod
from harness.code import sandbox_tools as st
from harness.code.execution import (
    AnalysisRequest,
    check_imports,
    interpreter_path,
    run_analysis,
)
from harness.code.recipes import (
    Recipe,
    register_dynamic_recipe,
    run_recipe,
    unregister_dynamic_recipe,
)
from harness.schemas import ModelSettings
from harness.tools import ToolContext, ToolRegistry


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


def _ctx(**overrides) -> ToolContext:
    base = dict(
        run_id="run_tools",
        log=lambda *_: None,
        user_id="local",
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(),
        memory_store=None,
        analysis_enabled=True,
    )
    base.update(overrides)
    return ToolContext(**base)


def _resolver(calls: list[tuple[str, dict]], payload: dict | None = None):
    def resolve(name: str, params: dict) -> dict:
        calls.append((name, dict(params)))
        return dict(payload or {"status": "OK", "price": 123.45, "symbol": params.get("symbol")})

    return resolve


def test_binding_set_is_read_only_and_minimal():
    assert st.tool_names() == ("market_snapshot", "live_quote", "price_history")
    # The analysis sandbox's own bindings are all data reads.
    for name in st.tool_names():
        binding = st.TOOL_BINDINGS[name]
        assert binding.capability in st.tool_names()
        assert "write" not in binding.name
        assert "search" not in binding.name
    # The web binding exists for the scraper lane ONLY: it is never part of the
    # analysis sandbox's set, so an analysis program still cannot reach the net.
    assert st.WEB_TOOL_NAMES == ("web_page",)
    assert "web_page" not in st.tool_names()
    for name in st.WEB_TOOL_NAMES:
        binding = st.TOOL_BINDINGS[name]
        assert binding.capability == "web_collect"
        assert "write" not in binding.name


def test_validate_normalizes_and_rejects_bad_requests():
    capability, params = st.validate_tool_request(
        "market_snapshot", {"symbol": " aapl ", "market": "us"},
    )
    assert capability == "market_snapshot"
    assert params == {"symbol": "AAPL", "market": "US"}

    invalid = [
        ("unknown_tool", {"symbol": "AAPL"}),
        ("market_snapshot", {}),
        ("market_snapshot", {"symbol": "AAPL", "url": "https://example.com"}),
        ("market_snapshot", {"symbol": {"nested": "AAPL"}}),
        ("price_history", {"symbol": "AAPL", "interval": "every-tick"}),
        ("price_history", {"symbol": "AAPL", "start": "2026-02-30"}),
        ("price_history", {"symbol": "AAPL", "start": "2026-03-01", "end": "2026-02-01"}),
        ("market_snapshot", {"symbol": "A" * (st.MAX_TOOL_ARGS_BYTES + 1)}),
        ("market_snapshot", "AAPL"),
    ]
    for name, args in invalid:
        with pytest.raises(st.ToolRequestError) as exc:
            st.validate_tool_request(name, args)
        assert exc.value.code in (st.TOOL_ARGS_INVALID, st.TOOL_NOT_ALLOWED)


def test_memo_key_uses_raw_arguments_not_normalized_ones():
    raw_upper = st.cache_key("market_snapshot", {"symbol": "AAPL"})
    raw_lower = st.cache_key("market_snapshot", {"symbol": "aapl"})
    assert raw_upper != raw_lower
    assert st.cache_key("x", {"a": 1, "b": 2}) == st.cache_key("x", {"b": 2, "a": 1})


def test_only_plain_import_and_allowlisted_attributes_pass_the_ast_gate():
    names = ("market_snapshot",)
    assert check_imports(
        'import eclipse_tools\nresult = eclipse_tools.market_snapshot(symbol="AAPL")',
        ("eclipse_tools",), tool_names=names,
    ) == []
    assert check_imports(
        'import eclipse_tools\nresult = eclipse_tools.web_search()',
        ("eclipse_tools",), tool_names=names,
    )
    assert check_imports(
        "from eclipse_tools import market_snapshot", ("eclipse_tools",), tool_names=names,
    )
    assert check_imports(
        "import eclipse_tools as et", ("eclipse_tools",), tool_names=names,
    )
    assert check_imports(
        'import eclipse_tools\nresult = eclipse_tools.market_snapshot(symbol="AAPL")',
        (), tool_names=(),
    )


def test_tools_are_refused_without_the_flag_or_a_resolver():
    source = 'import eclipse_tools\nresult = eclipse_tools.market_snapshot(symbol="AAPL")'
    calls: list[tuple[str, dict]] = []
    for allow, resolver in ((False, _resolver(calls)), (True, None)):
        result = run_analysis(
            AnalysisRequest(
                source=source, purpose="probe", timeout_s=60, allow_tools=allow,
            ),
            tool_resolver=resolver,
        )
        assert result.status == "refused"
        assert result.code == st.TOOL_NOT_ALLOWED
    assert calls == []


def test_reads_are_memoized_and_only_audit_metadata_is_returned():
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    calls: list[tuple[str, dict]] = []
    secret = "PAYLOAD-MUST-NOT-ENTER-CONTEXT"
    source = (
        "import eclipse_tools\n"
        'first = eclipse_tools.market_snapshot(symbol="aapl", market="us")\n'
        'second = eclipse_tools.market_snapshot(symbol="aapl", market="us")\n'
        'result = {"price": first["price"], "stable": first == second, '
        '"has_secret": bool(first.get("secret"))}\n'
    )
    result = run_analysis(
        AnalysisRequest(source=source, purpose="probe", timeout_s=60, allow_tools=True),
        tool_resolver=_resolver(calls, {"status": "OK", "price": 99.5, "secret": secret}),
    )
    assert result.status == "ok"
    assert result.outputs == {"price": 99.5, "stable": True, "has_secret": True}
    assert calls == [("market_snapshot", {"symbol": "AAPL", "market": "US"})]
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "market_snapshot"
    assert result.tool_calls[0].round == 1
    blob = json.dumps(result.to_blob())
    assert secret not in blob


def test_resolver_failure_is_reported_honestly():
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")

    def resolve(_name: str, _params: dict) -> dict:
        raise RuntimeError("bridge unavailable")

    result = run_analysis(
        AnalysisRequest(
            source='import eclipse_tools\nresult = eclipse_tools.live_quote(symbol="MSFT")',
            purpose="probe", timeout_s=60, allow_tools=True,
        ),
        tool_resolver=resolve,
    )
    assert result.status == "failed"
    assert result.code == st.TOOL_RESOLVE_FAILED
    assert result.tool_calls == []
    assert "bridge unavailable" in result.stderr


def test_the_call_budget_is_enforced_before_an_extra_read():
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    calls: list[tuple[str, dict]] = []
    lines = ["import eclipse_tools"]
    for index in range(st.MAX_TOOL_CALLS + 1):
        lines.append(f'eclipse_tools.live_quote(symbol="T{index}")')
    lines.append('result = {"done": True}')
    result = run_analysis(
        AnalysisRequest(
            source="\n".join(lines), purpose="probe", timeout_s=120, allow_tools=True,
        ),
        tool_resolver=_resolver(calls),
    )
    assert result.status == "refused"
    assert result.code == st.TOOL_LIMIT
    assert len(calls) == st.MAX_TOOL_CALLS
    assert len(result.tool_calls) == st.MAX_TOOL_CALLS


def test_oversized_arguments_are_refused_before_reading_the_request_file():
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    calls: list[tuple[str, dict]] = []
    result = run_analysis(
        AnalysisRequest(
            source=(
                "import eclipse_tools\n"
                f'result = eclipse_tools.market_snapshot(symbol="{"A" * (st.MAX_TOOL_REQUEST_BYTES + 1)}")\n'
            ),
            purpose="probe", timeout_s=60, allow_tools=True,
        ),
        tool_resolver=_resolver(calls),
    )
    assert result.status == "refused"
    assert result.code == st.TOOL_ARGS_INVALID
    assert calls == []


def test_oversized_results_are_refused():
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    calls: list[tuple[str, dict]] = []
    result = run_analysis(
        AnalysisRequest(
            source='import eclipse_tools\nresult = eclipse_tools.price_history(symbol="AAPL")',
            purpose="probe", timeout_s=60, allow_tools=True,
        ),
        tool_resolver=_resolver(calls, {"status": "OK", "blob": "x" * (st.MAX_TOOL_RESULT_BYTES + 1)}),
    )
    assert result.status == "refused"
    assert result.code == st.TOOL_RESULT_TOO_LARGE
    assert len(calls) == 1


def test_the_recipe_lane_also_receives_the_resolver():
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    recipe = Recipe(
        name="test_read_only_snapshot",
        answers="the live snapshot",
        inputs=(),
        source=(
            "import eclipse_tools\n"
            'snap = eclipse_tools.market_snapshot(symbol="AAPL")\n'
            'result = {"price": snap["price"]}\n'
        ),
    )
    register_dynamic_recipe(recipe)
    try:
        calls: list[tuple[str, dict]] = []
        result = run_recipe(recipe.name, {}, timeout_s=60, tool_resolver=_resolver(calls))
        assert result.status == "ok"
        assert result.outputs == {"price": 123.45}
        assert calls == [("market_snapshot", {"symbol": "AAPL"})]
        assert len(result.tool_calls) == 1

        without = run_recipe(recipe.name, {}, timeout_s=60)
        assert without.status == "refused"
        assert without.code == st.TOOL_NOT_ALLOWED
    finally:
        unregister_dynamic_recipe(recipe.name)


def test_analysis_run_bridges_async_without_blocking_the_loop_or_leaking_payloads():
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")

    class Bridge:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []
            self.loop_thread = threading.get_ident()
            self.fetch_thread = -1

        async def fetch(self, capability: str, params: dict) -> dict:
            self.calls.append((capability, dict(params)))
            self.fetch_thread = threading.get_ident()
            await asyncio.sleep(0)
            return {"status": "OK", "price": 321.0, "secret": "DO-NOT-LEAK"}

    bridge = Bridge()
    source = (
        "import eclipse_tools\n"
        'quote = eclipse_tools.live_quote(symbol="msft")\n'
        'result = {"price": quote["price"]}\n'
    )
    text, data = asyncio.run(analysis_run(
        {"source": source, "inputs": {}, "purpose": "quote", "timeout_s": 60},
        _ctx(data_bridge=bridge),
    ))
    assert data["status"] == "ok"
    assert data["outputs"] == {"price": 321.0}
    assert data["toolCalls"][0]["name"] == "live_quote"
    assert bridge.calls == [("live_quote", {"symbol": "MSFT"})]
    assert bridge.fetch_thread == bridge.loop_thread
    assert "DO-NOT-LEAK" not in text
    assert "DO-NOT-LEAK" not in json.dumps(data)


def test_analysis_run_without_a_bridge_refuses_the_tool_import():
    source = 'import eclipse_tools\nresult = eclipse_tools.market_snapshot(symbol="AAPL")'
    _, data = asyncio.run(analysis_run(
        {"source": source, "inputs": {}, "purpose": "quote", "timeout_s": 60},
        _ctx(),
    ))
    assert data["status"] == "refused"
    assert data["code"] == st.TOOL_NOT_ALLOWED


def test_analysis_run_still_runs_plain_source_off_the_loop():
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    _, data = asyncio.run(analysis_run(
        {
            "source": 'result = {"total": inputs["a"] + inputs["b"]}',
            "inputs": {"a": 2, "b": 40},
            "purpose": "sum",
            "timeout_s": 60,
        },
        _ctx(),
    ))
    assert data["status"] == "ok"
    assert data["outputs"] == {"total": 42}
    assert data["toolCalls"] == []
