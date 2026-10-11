"""Strategy ops: source inspection, approvals/deployments, multi-file projects,
and the new static validation codes."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.errors import ApprovalRequired, LiveTradingDisabled
from harness.quant.ops_tools import inspect_source
from harness.quant.store import QuantStore
from harness.quant.tools import QUANT_TOOLS, register_quant_tools
from harness.tools import ToolRegistry


def _spec(**execution):
    return S.parse_strategy({
        "strategy": {"id": "gov", "name": "Gov", "version": "1.0.0"},
        "universe": {"symbols": ["X"]},
        "indicators": [{"id": "ema", "type": "ema", "params": {"period": 5}}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "close"}, "op": ">", "right": {"ref": "ema"}}]}}, "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 50},
        "execution": execution or {},
    })


@pytest.fixture()
def store(tmp_path):
    return QuantStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "a"))


# ── Source inspection ────────────────────────────────────────────────────────

def test_inspect_flags_third_party_and_dangerous():
    r = inspect_source("import requests\nimport os\ndef f():\n    eval('1')\n")
    assert "requests" in r["thirdPartyImports"]
    codes = {f["code"] for f in r["findings"]}
    assert "THIRD_PARTY_IMPORT" in codes and "DANGEROUS_CALL" in codes
    assert "RESTRICTED_IMPORT" in codes


def test_inspect_syntax_error():
    r = inspect_source("def broken(:\n")
    assert r["ok"] is False and "syntax error" in r["error"]


# ── Governance ───────────────────────────────────────────────────────────────

def test_approval_and_paper_deployment(store):
    spec = _spec()
    store.save_strategy(spec)
    appr = store.request_approval("gov", "1.0.0", actor="analyst")
    assert appr["status"] == "requested"

    # Deployment needs approval first.
    with pytest.raises(ApprovalRequired):
        store.create_deployment("gov", "1.0.0", mode="paper")

    store.decide_approval(appr["id"], approve=True, actor="risk")
    assert store.is_approved("gov", "1.0.0") is True
    dep = store.create_deployment("gov", "1.0.0", mode="paper", note="shadow")
    assert dep["status"] == "active" and dep["liveExecution"] is False
    assert len(store.list_deployments("gov")) == 1
    stopped = store.stop_deployment(dep["id"])
    assert stopped["status"] == "stopped"


def test_live_deployment_refused(store):
    store.save_strategy(_spec())
    with pytest.raises(LiveTradingDisabled):
        store.create_deployment("gov", "1.0.0", mode="live")


# ── Validation codes ─────────────────────────────────────────────────────────

def test_ambiguous_fill_timing_warning():
    issues = S.validate_strategy(_spec(fill_at="close", latency_bars=0))
    assert any(i.code == "AMBIGUOUS_FILL_TIMING" and i.severity == "warning" for i in issues)


def test_indicator_timeframe_unordered_error():
    spec = S.parse_strategy({
        "strategy": {"id": "tf", "name": "TF", "version": "1.0.0"},
        "universe": {"symbols": ["X"]},
        "indicators": [{"id": "ema", "type": "ema", "params": {"period": 5}, "timeframe": "4h"}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "close"}, "op": ">", "right": {"value": 0}}]}}, "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 50},
    })
    assert any(i.code == "INDICATOR_TF_UNORDERED" for i in S.validate_strategy(spec))


# ── Multi-file project (isolated runtime) ────────────────────────────────────

def test_multi_file_project_runs():
    from harness.quant.sdk_runtime import run_strategy_source

    entry = (
        "from harness.quant.sdk import Strategy\n"
        "from helper import make_signal\n"
        "class P(Strategy):\n"
        "    name='proj'\n"
        "    def initialize(self, ctx):\n"
        "        ctx.declare_indicator('ema','ema',{'period':10})\n"
        "    def on_data(self, ctx, bar):\n"
        "        if ctx.position().is_flat and make_signal(ctx, bar):\n"
        "            ctx.buy(weight=0.5)\n"
    )
    helper = (
        "def make_signal(ctx, bar):\n"
        "    e = ctx.indicator('ema')\n"
        "    return e is not None and bar.close > e\n"
    )
    rows = {"TESTUSDT": F.bull_market("TESTUSDT", n=200)}
    result, err = run_strategy_source(entry, rows, symbols=["TESTUSDT"], timeout_s=60,
                                      extra_files={"helper.py": helper}, entry="main.py")
    assert err is None, err
    assert result is not None and result.status == "OK"


# ── Registration ─────────────────────────────────────────────────────────────

def test_ops_tools_registered():
    registry = ToolRegistry()
    register_quant_tools(registry)
    assert set(registry.names()) == set(QUANT_TOOLS)
    for name in ("inspect_python_strategy", "request_strategy_approval",
                 "create_strategy_deployment", "run_python_project"):
        assert name in QUANT_TOOLS
