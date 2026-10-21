"""The scraper lane — a program that collects what the vault does not have.

These tests pin the three things that make the lane safe and honest:

  * the ANALYSIS sandbox still cannot reach the web (the web binding belongs to
    the scraper lane alone, and a URL literal is refused unless the host turned
    the web binding on);
  * the fetch the program makes is the HOST's fetch — the binding validates the
    address and the host's transport does the rest;
  * the consent is per DOMAIN: the first collection from a site asks, and the
    consent for that site is remembered afterwards.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from harness.code import sandbox_tools as st
from harness.code.execution import AnalysisRequest, check_imports, prepare_analysis
from harness.scraper import program as scraper_program
from harness.scraper.authorizers import SCRAPER_APPROVAL_KIND, domain_of, make_scraper_authorizer


class _Grants:
    def __init__(self) -> None:
        self.granted: set[tuple[str, str]] = set()
        self.added: list[tuple[str, str, str]] = []

    def matches(self, kind: str, scope: str, pattern: str):
        if (kind, scope, pattern) in self.granted:
            return {"id": "grant_1"}
        return None

    def add(self, *, kind: str, pattern: str, scope: str = "", **_kwargs) -> dict:
        self.granted.add((kind, scope, pattern))
        self.added.append((kind, scope, pattern))
        return {"id": "grant_1"}


class _Approvals:
    """A tiny in-memory stand-in for the single-use approval store."""

    def __init__(self) -> None:
        self.grants = _Grants()
        self.approved: set[str] = set()
        self.requested: list[dict] = []
        self.consumed: list[str] = []

    def consume_kind(self, *, kind: str, request_key: str, digest: str, **_kwargs):
        if request_key in self.approved:
            self.consumed.append(request_key)
            return {"id": "appr_1"}
        return None

    def request_kind(self, **kwargs) -> dict:
        self.requested.append(kwargs)
        return {"id": "appr_req"}


def _ctx(**overrides) -> SimpleNamespace:
    base = dict(
        run_id="r", pause_for_approval=False, emitter=None,
        effect_authorized_digest=None, workspace=SimpleNamespace(id="ws1"),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _tool(name: str = "scraper_run") -> SimpleNamespace:
    return SimpleNamespace(name=name, permission="write", effect="write")


# ── The web binding ──────────────────────────────────────────────────────────


def test_the_web_binding_is_not_part_of_the_analysis_sandbox():
    assert st.tool_names() == ("market_snapshot", "live_quote", "price_history")
    assert "web_page" not in st.tool_names()
    assert st.WEB_TOOL_NAMES == ("web_page",)


def test_the_web_binding_validates_its_address_and_selectors():
    capability, params = st.validate_tool_request(
        "web_page",
        {
            "url": "https://example.com/table",
            "selector": "table tbody tr",
            "fields": {"name": "td:nth-child(1)"},
            "max_rows": 50,
            "links": True,
        },
    )
    assert capability == "web_collect"
    assert params["url"] == "https://example.com/table"
    assert params["selector"] == "table tbody tr"
    assert params["fields"] == {"name": "td:nth-child(1)"}
    assert params["max_rows"] == 50
    assert params["links"] is True


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"url": "not-a-url"},
        {"url": "ftp://example.com/x"},
        {"url": "https://user:pw@example.com/x"},
        {"url": "https://example.com/x", "max_rows": 0},
        {"url": "https://example.com/x", "max_rows": 5000},
        {"url": "https://example.com/x", "selector": ""},
        {"url": "https://example.com/x", "fields": {"a": ""}},
        {"url": "https://example.com/x", "links": "yes"},
    ],
)
def test_the_web_binding_refuses_an_unusable_request(args):
    with pytest.raises(st.ToolRequestError):
        st.validate_tool_request("web_page", args)


# ── The AST gate ─────────────────────────────────────────────────────────────


def test_a_url_literal_is_refused_unless_the_web_binding_is_on():
    source = 'import eclipse_tools\nresult = eclipse_tools.web_page(url="https://example.com")'
    # The URL literal is refused by default: an analysis program may not even
    # name a web address.
    assert "URL literal (network)" in check_imports(
        source, ("eclipse_tools",), tool_names=("web_page",),
    )
    # With the web binding on, the literal is a plain string — the program
    # still cannot open a socket, so it can only be resolved by the host.
    assert check_imports(
        source, ("eclipse_tools",), tool_names=("web_page",), allow_url_literals=True,
    ) == []
    # The analysis sandbox: no web binding, so the call is refused too.
    offenders = check_imports(source, ("eclipse_tools",), tool_names=st.tool_names())
    assert any(item.startswith("eclipse_tools.") for item in offenders)


def test_the_analysis_lane_cannot_reach_the_web():
    request = AnalysisRequest(
        source='import eclipse_tools\nresult = eclipse_tools.web_page(url="https://x.example")',
        purpose="try to fetch",
        allow_tools=True,
    )
    prepared = prepare_analysis(request, tool_resolver=lambda *_: {})
    # The refusal is an AnalysisResult (not a PreparedAnalysis).
    assert getattr(prepared, "status", None) == "refused"
    assert "eclipse_tools.web_page" in str(getattr(prepared, "stderr", ""))


# ── The result contract ──────────────────────────────────────────────────────


def test_the_result_contract_accepts_rows_and_derives_the_columns():
    rows, columns, notes = scraper_program.read_result({
        "rows": [{"name": "a", "value": 1}, {"name": "b", "value": 2}],
    })
    assert [row["name"] for row in rows] == ["a", "b"]
    assert columns == ["name", "value"]
    assert notes == ""


def test_the_result_contract_refuses_a_program_that_never_answered():
    # No `rows` at all: the program never answered.
    with pytest.raises(scraper_program.ScraperProgramError) as exc:
        scraper_program.read_result({"something": 1})
    assert exc.value.code == "RESULT_MISSING"

    # A list of rows is not an answer: the contract is an object.
    with pytest.raises(scraper_program.ScraperProgramError) as exc:
        scraper_program.read_result([{"a": 1}])
    assert exc.value.code == "RESULT_INVALID"


def test_an_empty_answer_is_an_answer():
    rows, columns, notes = scraper_program.read_result({"rows": []})
    assert rows == []
    assert columns == []
    assert notes == ""


def test_the_program_is_wrapped_so_a_missing_answer_fails_loudly():
    wrapped = scraper_program.wrap_program("rows = []")
    assert "result" in wrapped
    # The wrapper reads the name with a `try` (the sandbox forbids `globals`).
    assert "globals" not in wrapped and "dir(" not in wrapped


def test_a_program_that_is_too_big_is_refused():
    with pytest.raises(scraper_program.ScraperProgramError):
        scraper_program.check_program("x" * (scraper_program.MAX_PROGRAM_CHARS + 1))


# ── The per-domain consent ───────────────────────────────────────────────────


def test_the_domain_is_read_from_the_address():
    assert domain_of("https://Example.com/table?a=1") == "example.com"
    assert domain_of("") == ""
    assert domain_of("nonsense") == ""


def test_the_first_collection_from_a_site_asks_and_the_next_one_does_not():
    approvals = _Approvals()
    authorize = make_scraper_authorizer(approvals, "run-1", "ws1", None, inner=None)
    args = {"target_url": "https://example.com/table"}

    # Not approved yet: the call is refused AND a request is raised.
    assert asyncio.run(authorize(_tool(), dict(args), _ctx())) is False
    assert approvals.requested and approvals.requested[0]["kind"] == SCRAPER_APPROVAL_KIND
    assert approvals.requested[0]["request_key"] == "example.com"

    # The operator approves that domain: the next call is authorized, and the
    # consent is remembered as a standing grant.
    approvals.approved.add("example.com")
    assert asyncio.run(authorize(_tool(), dict(args), _ctx())) is True
    assert ("scraper_domain", "ws1", "example.com") in approvals.grants.added

    # A later call needs no approval at all.
    approvals.approved.clear()
    assert asyncio.run(authorize(_tool(), dict(args), _ctx())) is True


def test_a_different_site_asks_again():
    approvals = _Approvals()
    authorize = make_scraper_authorizer(approvals, "run-1", "ws1", None, inner=None)
    approvals.approved.add("example.com")
    assert asyncio.run(authorize(_tool(), {"target_url": "https://example.com/a"}, _ctx())) is True
    assert asyncio.run(authorize(_tool(), {"target_url": "https://other.test/a"}, _ctx())) is False
    assert approvals.requested[-1]["request_key"] == "other.test"


def test_another_tool_falls_through_to_the_inner_authorizer():
    approvals = _Approvals()

    async def inner(tool, args, ctx=None):
        return True

    authorize = make_scraper_authorizer(approvals, "run-1", "ws1", None, inner=inner)
    assert asyncio.run(authorize(_tool("some_other_tool"), {}, _ctx())) is True


def test_no_approval_store_means_no_collection():
    authorize = make_scraper_authorizer(None, "run-1", "ws1", None, inner=None)
    assert asyncio.run(authorize(_tool(), {"target_url": "https://example.com/a"}, _ctx())) is False


# ── The tool, end to end (the sandbox is real; the network is not) ───────────

_PROGRAM = """
import eclipse_tools

page = eclipse_tools.web_page(
    url="https://example.com/holdings",
    selector="table tbody tr",
    fields={"name": "td:nth-child(1)", "weight": "td:nth-child(2)"},
)
result = {"rows": page.get("rows") or [], "columns": ["name", "weight"]}
"""


class _Bridge:
    """A bridge whose fetch answers with a collected page."""

    def __init__(self) -> None:
        self.fetched: list[tuple[str, dict]] = []
        self.stored: list[tuple[str, dict]] = []

    async def fetch(self, capability: str, params: dict) -> dict:
        self.fetched.append((capability, dict(params)))
        return {
            "status": "OK",
            "url": params.get("url"),
            "rows": [{"name": "ACME", "weight": "4.5"}],
            "columns": ["name", "weight"],
        }

    async def post_json(self, path: str, payload: dict) -> dict:
        self.stored.append((path, dict(payload)))
        return {
            "ok": True,
            "dataset": {"id": "ds1", "name": f"scraped_{payload.get('name')}"},
            "written": len(payload.get("rows") or []),
            "provenance": "SCRAPER",
        }


@pytest.mark.skipif(
    not __import__("harness.code.execution", fromlist=["interpreter_path"]).interpreter_path(),
    reason="the analysis interpreter is not installed",
)
def test_the_tool_collects_stores_and_saves_the_scraper(tmp_path) -> None:
    from harness.scraper.tools import scraper_run
    from harness.tools import ToolContext

    bridge = _Bridge()
    ctx = ToolContext(
        run_id="run-scraper",
        log=lambda *_: None,
        data_bridge=bridge,
        workspace=SimpleNamespace(root=str(tmp_path), id="ws1"),
    )
    text, data = asyncio.run(scraper_run({
        "name": "psx holdings",
        "purpose": "track the index weights",
        "target_url": "https://example.com/holdings",
        "code": _PROGRAM,
    }, ctx))

    # The fetch went through the bridge as a page collection.
    assert bridge.fetched and bridge.fetched[0][0] == "web_collect"
    assert bridge.fetched[0][1]["url"] == "https://example.com/holdings"
    # The rows came back, and they were stored.
    assert data["rowCount"] == 1
    assert data["columns"] == ["name", "weight"]
    assert data["stored"] is True
    assert data["provenance"] == "collected"
    assert bridge.stored and bridge.stored[0][0] == "/api/scraper/datasets"
    # The program was saved so it can be run again.
    assert (tmp_path / ".black-eclipse" / "scrapers" / "psx_holdings.json").is_file()
    assert "COLLECTED page data" in text
