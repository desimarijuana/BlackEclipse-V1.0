"""Phase 10 unit tests — task progress, cross-engine coordination, browser→claim.

The bundled SEC filing skill loads inert; a browser value becomes a verified claim
ONLY through the engine's verification path. No browser is launched.
"""

from __future__ import annotations

import pytest

from harness.browser.bridge import BrowserClaimError, claim_from_browser, evidence_from_browser
from harness.browser.task import (
    ACTIVE,
    DONE,
    PENDING,
    BrowserTaskRegistry,
    steps_from_labels,
)
from harness.research.coordination import (
    BROWSER,
    COMPUTER,
    WEB,
    SurfaceRequest,
    route,
    routing_policy,
)


# ── 10.1 Task progress ───────────────────────────────────────────────────────

def test_task_steps_are_bounded():
    steps = steps_from_labels([f"step {i}" for i in range(500)])
    assert len(steps) <= 64
    assert steps[0].label == "step 0"


def test_task_registry_progress_and_completion():
    registry = BrowserTaskRegistry()
    task = registry.create(goal="Research a filing", labels=["open EDGAR", "find filing", "download"])
    assert not task.terminal
    registry.begin(task.id, 0)
    assert task.steps[0].status == ACTIVE
    registry.complete(task.id, 0)
    assert task.steps[0].status == DONE
    assert task.current == 1
    registry.begin(task.id, 1)
    registry.complete(task.id, 1)
    registry.begin(task.id, 2)
    registry.complete(task.id, 2)
    assert task.terminal
    assert task.state == "completed"
    progress = task.progress()
    assert progress["stepsDone"] == 3
    assert progress["fraction"] == 1.0


def test_task_begin_skips_earlier_pending_steps():
    registry = BrowserTaskRegistry()
    task = registry.create(goal="g", labels=["a", "b", "c"])
    registry.begin(task.id, 2)
    assert task.steps[0].status == "skipped"
    assert task.steps[1].status == "skipped"
    assert task.steps[2].status == ACTIVE


def test_task_failure_is_terminal():
    registry = BrowserTaskRegistry()
    task = registry.create(goal="g", labels=["a", "b"])
    registry.begin(task.id, 0)
    registry.fail(task.id, note="page not found")
    assert task.state == "failed"
    assert task.steps[0].status == "failed"
    assert task.steps[0].note == "page not found"


def test_task_render_is_a_checklist():
    registry = BrowserTaskRegistry()
    task = registry.create(goal="Research a filing", labels=["open EDGAR", "download"])
    registry.begin(task.id, 0)
    text = task.render()
    assert "Research a filing" in text
    assert "open EDGAR" in text
    assert "→" in text  # active marker


def test_task_registry_emits_and_persists():
    events: list[tuple[str, dict]] = []

    class _Store:
        def __init__(self):
            self.saved = []

        def save_task(self, record):
            self.saved.append(record)

    store = _Store()
    registry = BrowserTaskRegistry(store=store, emit=lambda t, d: events.append((t, d)))
    task = registry.create(goal="g", labels=["a", "b"])
    registry.begin(task.id, 0)
    registry.complete(task.id, 0)
    registry.begin(task.id, 1)
    registry.complete(task.id, 1)
    assert any(e[0] == "browser.task.created" for e in events)
    assert any(e[0] == "browser.task.completed" for e in events)
    assert store.saved and store.saved[-1]["state"] == "completed"


def test_task_get_falls_back_to_store():
    class _Store:
        def get_task(self, task_id):
            return {
                "id": task_id, "goal": "stored", "state": "running", "current": 1,
                "steps": [{"index": 0, "label": "a", "status": "done"}, {"index": 1, "label": "b", "status": "pending"}],
            }

    registry = BrowserTaskRegistry(store=_Store())
    task = registry.get("btask_remote")
    assert task is not None and task.goal == "stored"
    assert task.steps[1].status == PENDING


# ── 10.3 Cross-engine coordination ───────────────────────────────────────────

def test_route_native_app_to_computer_use():
    routing = route(SurfaceRequest(question="read the trading terminal", native_app=True))
    assert routing.surface == COMPUTER
    assert "desktop" in routing.rationale.lower()


def test_route_login_gated_to_browser():
    routing = route(SurfaceRequest(question="read my brokerage", login_gated=True))
    assert routing.surface == BROWSER
    assert routing.evidence_path == "browser_candidate"
    assert "verify" in routing.rationale.lower()


def test_route_interactive_to_browser():
    routing = route(SurfaceRequest(question="search a portal", interactive=True))
    assert routing.surface == BROWSER


def test_route_javascript_heavy_to_browser():
    routing = route(SurfaceRequest(question="read a canvas chart", javascript_heavy=True))
    assert routing.surface == BROWSER


def test_route_default_to_web_research():
    routing = route(SurfaceRequest(question="what is the capital of France"))
    assert routing.surface == WEB
    assert routing.evidence_path == "engine"


def test_routing_policy_is_documented():
    policy = routing_policy()
    assert "search finds" in policy["summary"]
    assert set(policy["surfaces"]) == {WEB, BROWSER, COMPUTER}
    assert "claim_verify" in policy["verification"]


# ── 10.4 Browser → verified claim ────────────────────────────────────────────

def test_browser_evidence_requires_a_real_url():
    with pytest.raises(BrowserClaimError):
        evidence_from_browser(url="about:blank", text="some text")
    with pytest.raises(BrowserClaimError):
        evidence_from_browser(url="https://sec.gov/filing", text="")


def test_browser_evidence_has_untrusted_provenance():
    evidence = evidence_from_browser(
        url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany",
        text="Revenue was $10.2 billion in fiscal 2025.",
        title="10-K",
    )
    assert evidence.contentTrust == "UNTRUSTED"
    assert evidence.sourceUrl.startswith("https://")
    assert evidence.provenance.get("origin") == "browser"


def test_browser_value_becomes_a_verified_claim_only_via_engine():
    text = "Total revenue was 10.2 billion dollars in fiscal 2025, up from 9.1 billion."
    result = claim_from_browser(
        claim_text="Total revenue was 10.2 billion dollars in fiscal 2025",
        url="https://www.sec.gov/Archives/edgar/data/1/0001/10k.htm",
        observed_text=text,
        metric="revenue",
        structured_value=10_200_000_000,
        period="FY2025",
    )
    assert result["verified"] is True
    # The engine's own verifier assigned the status — not a browser shortcut.
    assert result["claim"].status in ("SUPPORTED", "PARTIALLY_SUPPORTED", "AMBIGUOUS")


def test_browser_claim_must_be_grounded_in_the_page_text():
    with pytest.raises(BrowserClaimError):
        claim_from_browser(
            claim_text="Net income was 99 billion",
            url="https://www.sec.gov/Archives/x.htm",
            observed_text="The company sells widgets in Ohio.",
        )


def test_browser_claim_never_fabricates_provenance():
    with pytest.raises(BrowserClaimError):
        claim_from_browser(
            claim_text="revenue 10",
            url="data:text/html,hi",  # not a real page
            observed_text="revenue 10 billion",
        )


# ── 10.2 Bundled SEC skill ───────────────────────────────────────────────────

def test_sec_filing_research_skill_is_bundled_and_inert():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "harness" / "skills" / "library" / "system" / "sec-filing-research"
    manifest = json.loads((root / "skill.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "system.sec-filing-research"
    assert manifest["status"] == "disabled"  # inert by default
    assert manifest["instructions"] == "SKILL.md"
    # It references only real browser/web tools.
    for tool in manifest["requiredTools"]:
        assert tool.startswith(("browser_", "web_", "company_")), tool
    assert (root / "SKILL.md").exists()
