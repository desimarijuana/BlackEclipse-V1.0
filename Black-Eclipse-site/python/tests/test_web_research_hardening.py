"""Production-hardening regression tests for the web research engine.

Each test pins a bug that was found and fixed:

  * long-running research tools were hard-killed by the agent's generic
    `toolTimeoutMs` ceiling (they now use their own declared budget);
  * the engine must self-budget BELOW the actual per-call ceiling so it returns a
    partial result instead of being killed;
  * `update_research` must be non-destructive and return a delta;
  * raw evidence text returned to the model / API must be bounded;
  * the process-wide status/cancel maps must be bounded;
  * coverage must not overstate how many sub-questions were answered.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.research.web_contracts import Evidence, ResearchRequest, SourceType
from harness.research.web_engine import ResearchEngine
from harness.research.web_tools import register_research_engine_tools
from harness.tools import ToolContext, ToolDefinition, ToolRegistry, effective_timeout_ms


# ── timeout ceiling ──────────────────────────────────────────────────────────────


def test_long_running_tool_ignores_agent_ceiling():
    # A normal tool is shortened by the agent ceiling …
    assert effective_timeout_ms(180_000, 30_000) == 30_000
    # … a long-running tool keeps its own declared budget.
    assert effective_timeout_ms(180_000, 30_000, long_running=True) == 120_000  # clamped to global ceiling
    assert effective_timeout_ms(60_000, 30_000, long_running=True) == 60_000


def test_research_query_is_registered_long_running():
    reg = ToolRegistry()
    register_research_engine_tools(reg)
    assert reg.get("research_query").long_running is True
    assert reg.get("web_extract").long_running is True
    # A plain search tool is NOT long-running (the ceiling still applies).
    assert reg.get("web_search").long_running is False


@pytest.mark.asyncio
async def test_registry_exposes_effective_timeout_to_context():
    captured: dict[str, Any] = {}

    async def handler(args, ctx):
        captured["timeout"] = ctx.tool_timeout_ms
        return "ok"

    reg = ToolRegistry()
    reg.register(ToolDefinition(name="lr", description="d", input_schema={"type": "object", "properties": {}}, handler=handler, timeout_ms=90_000, long_running=True))
    ctx = ToolContext(run_id="r", log=lambda m, d=None: None)
    await reg.execute("lr", "c", {}, ctx, timeout_ms=20_000)
    # The handler sees its OWN budget (90s), not the caller's 20s ceiling.
    assert captured["timeout"] == 90_000


# ── engine self-budgets under the tool ceiling ────────────────────────────────────


def test_engine_budget_is_clamped_under_tool_ceiling():
    from harness.research.web_tools import _budget_under_tool

    request = ResearchRequest(question="q", maxTimeSeconds=300.0, maxSources=50)
    ctx = ToolContext(run_id="r", log=lambda m, d=None: None, tool_timeout_ms=60_000)
    clamped = _budget_under_tool(request, ctx)
    # Leaves a safety margin below the 60s ceiling.
    assert clamped.maxTimeSeconds <= 50.0
    assert clamped.maxSources <= 8
    # With no known ceiling the request is unchanged.
    ctx2 = ToolContext(run_id="r", log=lambda m, d=None: None)
    assert _budget_under_tool(ResearchRequest(question="q", maxTimeSeconds=300.0), ctx2).maxTimeSeconds == 300.0


# ── non-destructive incremental update ────────────────────────────────────────────


class _Bridge:
    def __init__(self, pages: dict[str, dict[str, Any]]) -> None:
        self._pages = pages

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        if capability == "web_search":
            return {"status": "OK", "provider": "fake", "results": [{"title": "A", "url": u, "snippet": "s", "publishedAt": "2025-03-01T00:00:00+00:00"} for u in self._pages]}
        if capability == "web_fetch":
            page = self._pages.get(params["url"])
            if page:
                return {"status": "OK", **page}
        return {"status": "UNAVAILABLE"}


@pytest.mark.asyncio
async def test_update_research_is_non_destructive_and_returns_delta(tmp_workspace):
    import os

    from harness.persistence import AgentMemoryStore
    from harness.research.web_store import EvidenceStore

    store = EvidenceStore(AgentMemoryStore(os.path.join(tmp_workspace, "m.db")))
    bridge = _Bridge({"https://a.com/x": {"url": "https://a.com/x", "title": "A", "text": "A meaningful market paragraph that is easily long enough to be material for a claim here."}})
    engine = ResearchEngine(bridge=bridge, store=store)
    first = await engine.run(ResearchRequest(question="market research question", minSources=1))
    snapshots_before = len(store.list_snapshots(first.researchId))
    evidence_before = {e["evidenceId"] for e in store.list_evidence(first.researchId)}

    updated = await engine.update_research(first.researchId)
    assert updated is not None
    # Prior evidence was NOT deleted (the idempotent upsert keeps the same rows).
    evidence_after = {e["evidenceId"] for e in store.list_evidence(first.researchId)}
    assert evidence_before <= evidence_after
    # A new snapshot was appended (history preserved).
    assert len(store.list_snapshots(first.researchId)) == snapshots_before + 1
    # The delta names what changed.
    assert updated.delta is not None
    assert "sourcesAdded" in updated.delta and "snapshotId" in updated.delta


# ── bounded payloads ───────────────────────────────────────────────────────────────


def test_public_evidence_is_bounded():
    from harness.research.web_engine import _evidence_public

    ev = Evidence(evidenceId="e", sourceId="s", sourceUrl="https://x.com", rawText="Z" * 50_000)
    public = _evidence_public(ev)
    assert len(public["rawText"]) == 8_000
    assert public["rawTextTruncated"] is True
    assert public["rawTextChars"] == 50_000
    # The stored object still holds the full text.
    assert len(ev.rawText) == 50_000


@pytest.mark.asyncio
async def test_engine_result_dict_is_bounded():
    bridge = _Bridge({"https://a.com/x": {"url": "https://a.com/x", "title": "A", "text": "Y" * 40_000}})
    engine = ResearchEngine(bridge=bridge)
    result = await engine.run(ResearchRequest(question="q", minSources=1))
    dumped = result.to_dict()
    assert all(len(e["rawText"]) <= 8_000 for e in dumped["evidence"])


# ── bounded process-wide maps ──────────────────────────────────────────────────────


def test_run_maps_are_pruned():
    from harness.research import web_engine
    from harness.research.web_contracts import ResearchStatus

    web_engine._RUN_STATUS.clear()
    web_engine._RUN_CANCELS.clear()
    for i in range(web_engine._MAX_TRACKED_RUNS + 50):
        web_engine._RUN_STATUS[f"r{i}"] = ResearchStatus(researchId=f"r{i}", state="COMPLETED")
    web_engine._prune_runs()
    assert len(web_engine._RUN_STATUS) <= web_engine._MAX_TRACKED_RUNS


# ── coverage honesty ───────────────────────────────────────────────────────────────


def test_coverage_answered_questions_is_conservative():
    from harness.research.web_contracts import ResearchDepth, ResearchIntent, SubQuestion, WebResearchMandate
    from harness.research.web_engine import _build_coverage

    mandate = WebResearchMandate(
        researchId="r", question="q", objective="q",
        intent=ResearchIntent.FACT_LOOKUP, depth=ResearchDepth.STANDARD,
        subQuestions=[
            SubQuestion(id="a", question="nvidia revenue fiscal 2025"),
            SubQuestion(id="b", question="completely unrelated topic about penguins"),
        ],
        minSources=1,
    )
    ev = Evidence(
        evidenceId="e", sourceId="s", sourceUrl="https://sec.gov/x",
        sourceType=SourceType.OFFICIAL_FILING,
        rawText="NVIDIA revenue for fiscal 2025 was 130 billion dollars.",
        claimText="revenue",
    )
    coverage = _build_coverage(mandate, [ev], [], 1, {"ok": True, "issues": [], "coverage": 1.0})
    # Only the question with a matching keyword counts as answered.
    assert coverage["answeredQuestions"] == 1
    assert coverage["questionsTotal"] == 2
    # The method is disclosed (idf offline; semantic only when embeddings exist).
    assert coverage["coverageMethod"] in ("idf", "semantic", "keyword")


def test_coverage_idf_distinguishes_distinctive_terms():
    """IDF weighting answers a question only when its distinctive terms appear."""
    from harness.research.web_contracts import ResearchDepth, ResearchIntent, SubQuestion, WebResearchMandate
    from harness.research.web_coverage import _idf_answered

    mandate = WebResearchMandate(
        researchId="r", question="q", objective="q",
        intent=ResearchIntent.FACT_LOOKUP, depth=ResearchDepth.STANDARD,
        subQuestions=[
            SubQuestion(id="a", question="nvidia data center revenue"),
            SubQuestion(id="b", question="penguin migration patterns arctic"),
        ],
        minSources=1,
    )
    ev = Evidence(
        evidenceId="e", sourceId="s", sourceUrl="https://sec.gov/x",
        sourceType=SourceType.OFFICIAL_FILING,
        rawText="NVIDIA data center revenue grew sharply this year.",
        claimText="revenue",
    )
    result = _idf_answered(mandate, [ev])
    assert result is not None
    answered, scores = result
    assert answered == 1
    assert len(scores) == 2
    assert scores[0] > scores[1]


# ── concurrent search ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_searches_run_concurrently():
    """Independent sub-question queries run in parallel, not one after another."""
    import asyncio

    from harness.research.web_contracts import ResearchDepth, ResearchIntent
    from harness.research.web_providers import SearchProviderRegistry
    from harness.research.web_contracts import SearchResponse, SearchResult

    inflight = 0
    max_inflight = 0

    class SlowProvider:
        name = "slow"
        capabilities = ("web",)

        def available(self):
            return True

        async def search(self, query, *, limit=8, **kw):
            nonlocal inflight, max_inflight
            inflight += 1
            max_inflight = max(max_inflight, inflight)
            await asyncio.sleep(0.05)
            inflight -= 1
            return SearchResponse(
                query=query, status="OK", provider=self.name,
                results=[SearchResult(resultId="r", title="T", url=f"https://x.com/{query}", snippet="s")],
            )

    reg = SearchProviderRegistry()
    reg.register(SlowProvider(), kind="web", priority=1)
    engine = ResearchEngine(bridge=None, registry=reg)
    mandate, plan = await engine.create_research(
        ResearchRequest(question="NVIDIA valuation revenue earnings fiscal analysis deep", depth=ResearchDepth.DEEP)
    )
    assert len(plan.queries) >= 2
    await engine.execute_research(mandate, plan)
    # With a bounded pool of 4 and >=2 independent queries, more than one search
    # must have overlapped — proving the loop is concurrent, not sequential.
    assert max_inflight >= 2
