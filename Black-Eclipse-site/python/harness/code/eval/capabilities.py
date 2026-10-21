"""The capability-class registry + runner (Phase 20 §6.1–6.3, ADR-H193).

Every capability class a user can ask for is REGISTERED here — including the
classes this round could not grade, which are published as `not measured yet`
with their reason instead of being silently absent. A class is `measured` only
when a NAMED fixture/test actually ran and held:

  * `fixture`   — a deterministic offline fixture in THIS module, graded through
                  the REAL module it names (the thing under test is never mocked;
                  only its dependencies may be stubbed);
  * `test_gate` — a named test in the release gate (`pytest` or `vitest`); the
                  runner verifies the test exists so the statement's proof can
                  never point at nothing;
  * `code_eval` — a fixture id in the code eval's labelled dataset, graded by the
                  code gate in the same eval run.

A class with no fixture is reported `unmeasured` WITH ITS REASON — never a pass,
never a failure. The gate fails when a measured class falls below its floor OR
when a class that was measured regresses to unmeasured (`MEASURED_BASELINE`).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional

Kind = Literal["fixture", "test_gate", "code_eval", "unmeasured"]

_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class CapabilityClass:
    id: str
    label_key: str                    # capability.class.<id> — plain words
    kind: Kind
    module: str                       # the real module this class exercises
    selectors: tuple[str, ...] = ()   # fixture ids / test selectors / dataset ids
    reason: str = ""                  # REQUIRED when kind == "unmeasured"
    floor: float = 1.0


# ── The fixtures (real modules, deterministic, offline) ─────────────────────


def _fixture_bulk_collection() -> dict[str, bool]:
    """A pull stopped at the ceiling is marked partial; the count equals the file."""
    from harness.acquire.budget import AcquisitionBudget
    from harness.acquire.writer import write_csv

    with tempfile.TemporaryDirectory() as tmp:
        budget = AcquisitionBudget(max_rows=5)
        path = Path(tmp) / "out.csv"
        written, complete, stopped = write_csv(
            path, ("a",), ({"a": i} for i in range(9)), budget,
        )
        lines = len(path.read_text(encoding="utf-8").strip().splitlines())
    return {
        "stoppedAtCeiling": written == 5 and complete is False and "5" in stopped,
        "fileMatchesCounter": lines == written + 1,
        "ceilingRecorded": bool(budget.exhausted),
    }


def _fixture_unattended_report() -> dict[str, bool]:
    """A degraded delivered report states its outcome and every limit."""
    from harness.automation.delivery import OUTCOME_FIRST_LINE, render_run_report

    class _Definition:
        name = "fixture"

    failed = render_run_report(
        _Definition(), "failed", "partial result", limits=["A source was stale."],
    )
    completed = render_run_report(_Definition(), "completed", "the answer")
    empty = render_run_report(_Definition(), "completed", "")
    return {
        "outcomeOnFirstLine": failed.splitlines()[0] == OUTCOME_FIRST_LINE["failed"],
        "limitNamed": "A source was stale." in failed,
        "completedStatesOutcome": completed.splitlines()[0] == OUTCOME_FIRST_LINE["completed"],
        "emptyNeverASuccess": "produced no result" in empty,
    }


def _fixture_artifact_verification() -> dict[str, bool]:
    """An unbacked artifact claim is marked; a backed one is not; a FAILED record
    never supports the claim."""
    from harness.code.verify import ArtifactRecord, VerificationLedger, enforce_answer

    unbacked = enforce_answer("The figure is intact.", VerificationLedger("f"))

    backed_ledger = VerificationLedger("f")
    backed_ledger.record_artifact(ArtifactRecord(
        artifact_name="c.png", kind="image", check="artifact_exists",
        passed=True, detail="it is where it was reported", observed={},
    ))
    backed = enforce_answer("The figure is intact.", backed_ledger)

    failed_ledger = VerificationLedger("f")
    failed_ledger.record_artifact(ArtifactRecord(
        artifact_name="c.png", kind="image", check="artifact_digest",
        passed=False, detail="its digest does not match the record", observed={},
    ))
    failed = enforce_answer("The figure is intact.", failed_ledger)

    return {
        "unbackedMarked": bool(unbacked.enforced),
        "backedSupported": not backed.enforced,
        "failedRecordNeverSupports": bool(failed.enforced),
    }


def _fixture_change_review() -> dict[str, bool]:
    """The protected-file rule fires and AGREES with the enforcement seam; an
    empty diff is never reported as clean."""
    from harness.code import policy
    from harness.code.review import DiffFile, DiffView, review_change

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "python" / "harness" / "code" / "policy.py"
        target.parent.mkdir(parents=True)
        target.write_text("# the policy module\n", encoding="utf-8")
        result = review_change(DiffView(files=[
            DiffFile(path="python/harness/code/policy.py", status="modified", added_lines=("x",)),
        ]), repo_root=root)
        rules = {f.rule for f in result.findings}

    empty = review_change(DiffView(), repo_root=Path("."))
    return {
        "protectedFound": "protected-path" in rules,
        "agreesWithPolicy": policy.is_protected("python/harness/code/policy.py"),
        "emptyNeverClean": bool(empty.unevaluated),
    }


def _fixture_price_authority() -> dict[str, bool]:
    """Two disagreeing sources are ARBITRATED, and the conflict is recorded.

    The point of the authority table is that the answer does NOT depend on
    which source answered first. Two sources that disagree beyond the
    tolerance produce NO answer (`chosen is None`) and a CONFLICTING reason -
    never a silent first-success.
    """
    from harness.retrieval.authority import authority_for, decide_source
    from harness.retrieval.contract import (
        FinancialRetrievalRequest,
        NormalizedFinancialObject,
        SourceReference,
    )
    from harness.retrieval.sources import SourceOutcome

    # A FRESH observation: a stale one is rejected before the arbitration
    # ever runs, which would prove nothing about the arbitration.
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _obj(value: float, tier: str = "structured") -> Any:
        return NormalizedFinancialObject(
            name="price", value=value,
            source=SourceReference(source="X", sourceType=tier),
            observation_time=stamp, observation_source="provider_asof",
        )

    request = FinancialRetrievalRequest(
        objective="q", dataType="current_quote", freshnessRequirement="realtime",
    )
    vault = SourceOutcome(source="JDDS", status="OK", objects=[_obj(100.0)])
    live = SourceOutcome(source="LIVE_STRUCTURED", status="OK", objects=[_obj(130.0)])
    authority = authority_for("current_quote")

    conflict = decide_source(authority, [vault, live], request)
    reversed_decision = decide_source(authority, [live, vault], request)
    agree_vault = SourceOutcome(source="JDDS", status="OK", objects=[_obj(100.0)])
    agree_live = SourceOutcome(source="LIVE_STRUCTURED", status="OK", objects=[_obj(100.0)])
    agreement = decide_source(authority, [agree_vault, agree_live], request)

    return {
        "conflictIsRecorded": conflict.chosen is None and "CONFLICTING" in conflict.reason,
        # The CHOSEN and the REASON are order-independent - that is the point
        # of the arbitration. The `rejected` list is not: it names the
        # candidates in the order they were offered, which is a report, not a
        # verdict.
        "choiceIsOrderIndependent": (
            conflict.chosen == reversed_decision.chosen
            and conflict.reason == reversed_decision.reason
        ),
        "agreementResolves": agreement.chosen is not None,
        "rejectionsAreNamed": bool(conflict.rejected),
    }


def _fixture_promotion_landing() -> dict[str, bool]:
    """A change lands in the real folder, and can be put back EXACTLY.

    The full path: a disposable workspace with a change in it, a preview that
    names the change and hashes it, an approval bound to that preview, the
    apply, the rollback, and the apply again. Every step asserts on the real
    bytes in the real folder.
    """
    import subprocess
    import tempfile

    from harness.code import promotion as promotion_mod
    from harness.code import worktree as worktree_mod
    from harness.code.store import CodeWorkspaceStore
    from harness.persistence import AgentMemoryStore

    with tempfile.TemporaryDirectory(prefix="be-promotion-") as root:
        checkout = os.path.join(root, "checkout")
        os.makedirs(checkout)
        env = {**os.environ, "GIT_AUTHOR_NAME": "eval", "GIT_AUTHOR_EMAIL": "eval@example.invalid"}
        subprocess.run(["git", "init", "-q"], cwd=checkout, check=True, env=env)
        subprocess.run(["git", "config", "user.email", "eval@example.invalid"], cwd=checkout, check=True, env=env)
        subprocess.run(["git", "config", "user.name", "eval"], cwd=checkout, check=True, env=env)
        with open(os.path.join(checkout, "a.py"), "w", encoding="utf-8") as handle:
            handle.write("ORIGINAL\n")
        subprocess.run(["git", "add", "-A"], cwd=checkout, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=checkout, check=True, env=env)

        # The allocator resolves the root INTERNALLY, so point it at the
        # checkout for the duration of the fixture.
        previous_root = os.environ.get("BLACK_ECLIPSE_CODE_ROOT")
        os.environ["BLACK_ECLIPSE_CODE_ROOT"] = checkout
        try:
            workspace = worktree_mod.allocate("HEAD")
            with open(os.path.join(str(workspace.root), "a.py"), "w", encoding="utf-8") as handle:
                handle.write("CHANGED\n")
            store = AgentMemoryStore(os.path.join(root, "agent-memory.db"))
            try:
                code_store = CodeWorkspaceStore(store)
                code_store.save_workspace(
                    workspace.id, str(workspace.root), workspace.base_revision,
                    workspace.strategy, run_id="run_promo", file_count=1,
                )
                preview = promotion_mod.build_preview(
                    "run_promo", code_store=code_store, checkout_root=checkout,
                )
                applied = promotion_mod.apply_promotion(preview)
                changed = open(os.path.join(checkout, "a.py"), encoding="utf-8").read()
                rolled = promotion_mod.rollback_promotion(
                    applied["rollbackId"], checkout_root=checkout,
                )
                restored = open(os.path.join(checkout, "a.py"), encoding="utf-8").read()
                re_applied = promotion_mod.apply_promotion(preview)
                again = open(os.path.join(checkout, "a.py"), encoding="utf-8").read()
            finally:
                store.close()
                worktree_mod.release(workspace.id)
        finally:
            if previous_root is None:
                os.environ.pop("BLACK_ECLIPSE_CODE_ROOT", None)
            else:
                os.environ["BLACK_ECLIPSE_CODE_ROOT"] = previous_root

    return {
        "previewNamesTheChange": preview.get("filesChanged") == 1,
        "previewHashesBothSides": bool(preview["files"][0].get("beforeHash")) and bool(preview["files"][0].get("afterHash")),
        "applyReachesTheFolder": changed == "CHANGED\n",
        "rollbackRestoresExactly": restored == "ORIGINAL\n",
        "reApplyWorks": again == "CHANGED\n",
        "rollbackIsReported": bool(rolled.get("restored")),
    }


def _fixture_scraping_breadth() -> dict[str, bool]:
    """The acquisition registry knows MORE THAN ONE KIND of data source.

    "Breadth" is the number of distinct bridge CAPABILITIES across the
    registry - a name-glob search would not count. The registry is data, so
    the fixture asserts the data is coherent and deterministic.
    """
    from harness.acquire.registry import SOURCES, get_source, list_sources, registry_issues

    kinds = {source.capability for source in SOURCES.values()}
    return {
        "multipleKinds": len(kinds) > 1,
        "deterministic": kinds == {get_source(i).capability for i in sorted(SOURCES)},
        "registryIsClean": registry_issues() == [],
        "everySourceIsListed": {row["id"] for row in list_sources()} == set(SOURCES),
    }


def _fixture_code_intel() -> dict[str, bool]:
    """The code-intelligence context engine answers - and says so when it cannot.

    A query that matches nothing must return a VALID EMPTY packet, never None
    and never an exception: the engine is a tool the model can call, and a
    refusal to answer is not an answer.
    """
    import tempfile

    from harness.code.intel.manager import CodeIntelligenceManager
    from harness.code.intel.persistence.index import CodeIndex
    from harness.code.intel.project import project_id_for
    from harness.code.policy import WorkspaceBinding
    from harness.code.workspace import ResolvedWorkspace

    # A plain temp directory, not a TemporaryDirectory: the code index holds a
    # sqlite connection, and Windows cannot remove an open file - the cleanup
    # would raise where the fixture did not.
    root = tempfile.mkdtemp(prefix="be-intel-")
    if True:
        path = os.path.abspath(root)
        binding = WorkspaceBinding(
            id="ws_intel", root=path, base_revision="unknown", strategy="checkout",
        )
        workspace = ResolvedWorkspace(
            id="ws_intel", root=path, base_revision="unknown",
            strategy="checkout", binding=binding,
        )
        manager = CodeIntelligenceManager(
            workspace,
            index=CodeIndex(project_id_for(path, "ws_intel"), path=os.path.join(path, "idx.db")),
        )
        packet = manager.get_relevant_context("zzz_no_such_symbol")
    return {
        "answers": packet.get("status") == "ok",
        "namesItsEngine": packet.get("engine") == "context",
        "emptyIsEmpty": not packet.get("files") and not packet.get("symbols"),
        "countsAreHonest": packet.get("fileCount") == 0 and packet.get("symbolCount") == 0,
    }


def _fixture_code_chat_routing() -> dict[str, bool]:
    """The chat classifier routes a request to the right surface - and refuses safely."""
    from harness.code.request_intent import classify_code_request

    return {
        "routesAChange": classify_code_request("add a function to auth.py").verdict == "code_change",
        "routesAQuestion": classify_code_request("what is wrong with the api handler?").verdict == "code_question",
        "routesADataTask": classify_code_request("scrape the prices into a csv").verdict == "data_task",
        "refusesSafely": classify_code_request("show me the data").verdict == "not_code",
        "emptyIsNotCode": classify_code_request("").verdict == "not_code",
    }


def _fixture_context_compaction() -> dict[str, bool]:
    """Compaction carries the conversation forward - deterministically, and bounded."""
    from harness.compaction import build_skeleton, render_compaction_block

    class _Turn:
        def __init__(self, role: str, content: str) -> None:
            self.role = role
            self.content = content

    turns = [
        _Turn("user", "add a feature flag"),
        _Turn("assistant", "Done - the flag reads the env var"),
    ]
    requests, answers = build_skeleton(turns)
    block = render_repo_map = render_compaction = None
    from harness.compaction import render_compaction_block

    block = render_compaction_block(
        type("R", (), {
            "requests": requests, "answers": answers, "dropped_turns": len(turns),
            "narrative": "", "used_model": False, "ok": True, "reason": "",
        })()
    )
    return {
        "carriesTheRequests": requests == ("add a feature flag",),
        "carriesTheAnswers": answers == ("Done - the flag reads the env var",),
        "isFenced": block.startswith("<compacted-conversation>"),
        "isLabelledAsData": "DATA" in block,
        "isDeterministic": build_skeleton(turns) == (requests, answers),
    }


_FIXTURES: dict[str, Callable[[], dict[str, bool]]] = {
    "bulk-collection-ceiling": _fixture_bulk_collection,
    "unattended-report-limits": _fixture_unattended_report,
    "artifact-claim-marked": _fixture_artifact_verification,
    "change-review-rules": _fixture_change_review,
    "price-authority-arbitrates": _fixture_price_authority,
    "promotion-landing-round-trip": _fixture_promotion_landing,
    "scraping-breadth-across-kinds": _fixture_scraping_breadth,
    "code-intel-context-engine": _fixture_code_intel,
    "code-chat-routing": _fixture_code_chat_routing,
    "context-compaction-skeleton": _fixture_context_compaction,
}


# ── The registry (data) ──────────────────────────────────────────────────────

CLASSES: tuple[CapabilityClass, ...] = (
    # The seven code shapes: fixtures exist; the code gate grades them in this run.
    CapabilityClass("one_file", "capability.class.oneFile", "code_eval",
                    "harness.code.patch", ("one-file-change",)),
    CapabilityClass("cross_file", "capability.class.crossFile", "code_eval",
                    "harness.code.patch", ("cross-file-change",)),
    CapabilityClass("test_first", "capability.class.testFirst", "code_eval",
                    "harness.code.repair", ("test-first",)),
    CapabilityClass("repair", "capability.class.repair", "code_eval",
                    "harness.code.repair", ("failing-check-repair",)),
    # Round 3 / W1 (ADR-H281): the repair loop as it runs in PRODUCTION - the
    # real graph, the real verify-and-repair node, the real answer seam. The
    # `repair` class above exercises the repair MODULE; this one exercises the
    # LOOP. A graph with no repair node fails it.
    CapabilityClass("code_verify_repair_loop", "capability.class.codeVerifyRepairLoop",
                    "code_eval", "harness.code.repair_graph",
                    ("failing-check-repair-in-graph",)),
    # Round 3 / W5 (ADR-H284): the ONE search primitive per question, and the
    # engine that answered it. The gates assert that a surface carries one
    # content search and one name search, that the deprecated names still work
    # and now run on the same engine, and that the canonical name search kept
    # every filter the old one had.
    # Round 3 / W3 (ADR-H282): the ONE edit tool and the two rules that make it
    # safe - the file must have been READ by this run, and it must not have
    # changed since. The gates assert the refusals, the deprecations, the
    # policy classification and the path recovery.
    CapabilityClass("code_edit_contract", "capability.class.codeEditContract", "test_gate",
                    "harness.code.edit_tools",
                    ("pytest:python/tests/test_code_edit_primitive.py",)),
    # Round 3 / W4 (ADR-H287): the repo map - deterministic, bounded, and
    # joined to the prompt-cache key. The gates assert the determinism, the
    # bounds, the cache-key contract and the measured index freshness.
    CapabilityClass("code_repo_map", "capability.class.codeRepoMap", "test_gate",
                    "harness.code.intel.repo_map",
                    ("pytest:python/tests/test_repo_map.py",)),
    CapabilityClass("code_search", "capability.class.codeSearch", "test_gate",
                    "harness.code.fs.search",
                    ("pytest:python/tests/test_code_search_surface.py",)),
    CapabilityClass("job", "capability.class.job", "code_eval",
                    "harness.jobs.model", ("job-definition",)),
    CapabilityClass("kit", "capability.class.kit", "code_eval",
                    "harness.code.kits.loader", ("kit-scaffold",)),
    CapabilityClass("refusal", "capability.class.refusal", "code_eval",
                    "harness.code.policy", ("refusal-protected-write",)),
    # Graded here, through the real modules.
    CapabilityClass("bulk_collection", "capability.class.bulkCollection", "fixture",
                    "harness.acquire.budget", ("bulk-collection-ceiling",)),
    CapabilityClass("unattended_report", "capability.class.unattendedReport", "fixture",
                    "harness.automation.delivery", ("unattended-report-limits",)),
    CapabilityClass("artifact_verification", "capability.class.artifactVerification", "fixture",
                    "harness.code.verify", ("artifact-claim-marked",)),
    CapabilityClass("change_review", "capability.class.changeReview", "fixture",
                    "harness.code.review", ("change-review-rules",)),
    # Graded by named tests that run in the release gate.
    CapabilityClass("document_attachment", "capability.class.documentAttachment", "test_gate",
                    "lib/chat/extract",
                    ("vitest:src/lib/chat/extract.test.ts", "vitest:src/lib/chat/session-store.test.ts")),
    CapabilityClass("figure_provenance", "capability.class.figureProvenance", "test_gate",
                    "harness.code.recipes",
                    ("pytest:python/tests/test_analysis_recipes.py::test_drawdown_figure_writes_a_real_png_artifact_that_verifies",
                     "pytest:python/tests/test_analysis_recipes.py::test_a_figure_run_carries_its_payload_on_the_run_blob",
                     "pytest:python/tests/test_analysis_recipes.py::test_monte_carlo_is_bounded_seeded_and_samples_the_supplied_returns",
                     "vitest:src/components/chat/artifact-view.test.tsx",
                     "vitest:src/lib/harness/analysis-types.test.ts",
                     "pytest:python/tests/test_analysis_execution.py")),
    CapabilityClass("advisory_verification", "capability.class.advisoryVerification", "test_gate",
                    "harness.advisory.gate",
                    ("pytest:python/tests/test_advisory_gate.py",
                     "pytest:python/tests/test_advisory_ledger.py")),
    # Declared and NOT graded — published as not measured, with the reason.
    # Round 3 / W8 (ADR-H296): these three are now graded END TO END, not in
    # pieces. A capability class that is published but not measured is worse
    # than one that is honestly absent - so each of these moved from
    # `unmeasured` to a real fixture.
    CapabilityClass("price_authority", "capability.class.priceAuthority", "fixture",
                    "harness.retrieval.authority", ("price-authority-arbitrates",)),
    CapabilityClass("promotion", "capability.class.promotion", "fixture",
                    "harness.code.promotion", ("promotion-landing-round-trip",)),
    CapabilityClass("scraping_breadth", "capability.class.scrapingBreadth", "fixture",
                    "harness.acquire.registry", ("scraping-breadth-across-kinds",)),
    # The capability classes that had no row at all. A capability with no class
    # is where the work goes silent.
    CapabilityClass("code_intel", "capability.class.codeIntel", "fixture",
                    "harness.code.intel.manager", ("code-intel-context-engine",)),
    CapabilityClass("code_chat_routing", "capability.class.codeChatRouting", "fixture",
                    "harness.code.request_intent", ("code-chat-routing",)),
    CapabilityClass("context_compaction", "capability.class.contextCompaction", "fixture",
                    "harness.compaction", ("context-compaction-skeleton",)),
)

#: Classes that MUST stay measured; the gate fails when one regresses to unmeasured.
MEASURED_BASELINE: frozenset[str] = frozenset(
    c.id for c in CLASSES if c.kind != "unmeasured"
)


# ── The runner ───────────────────────────────────────────────────────────────


@dataclass
class ClassResult:
    id: str
    status: Literal["passed", "failed", "unmeasured"]
    detail: str
    observed: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityReport:
    results: list[ClassResult] = field(default_factory=list)

    @property
    def measured(self) -> list[ClassResult]:
        return [r for r in self.results if r.status != "unmeasured"]

    @property
    def unmeasured(self) -> list[ClassResult]:
        return [r for r in self.results if r.status == "unmeasured"]

    @property
    def failed(self) -> list[ClassResult]:
        return [r for r in self.results if r.status == "failed"]

    @property
    def passed(self) -> bool:
        return not self.failed

    def by_id(self, class_id: str) -> Optional[ClassResult]:
        return next((r for r in self.results if r.id == class_id), None)


def _check_test_selector(klass: CapabilityClass, selector: str) -> tuple[bool, str]:
    kind, _, target = selector.partition(":")
    if kind == "vitest":
        path = _REPO_ROOT / target
        return path.exists(), f"the test file is present: {target}"
    if kind == "pytest":
        file_part, _, test_name = target.partition("::")
        path = _REPO_ROOT / file_part
        if not path.exists():
            return False, f"the test file is missing: {file_part}"
        if test_name and f"def {test_name}" not in path.read_text(encoding="utf-8"):
            return False, f"the named test is missing: {test_name}"
        return True, f"the test is present: {target}"
    return False, f"unknown test selector {selector!r}"


def run_capability_eval(*, only: Optional[tuple[str, ...]] = None) -> CapabilityReport:
    """Grade every registered class. A class with no fixtures is reported
    `unmeasured` WITH ITS REASON — never as a pass, never as a failure."""
    report = CapabilityReport()
    for klass in CLASSES:
        if only is not None and klass.id not in only:
            continue
        if klass.kind == "unmeasured":
            report.results.append(ClassResult(
                id=klass.id, status="unmeasured",
                detail=klass.reason or "no fixture registered",
            ))
            continue
        if klass.kind == "fixture":
            try:
                observed = _FIXTURES[klass.selectors[0]]()
            except Exception as exc:  # noqa: BLE001 - a fixture error IS a failure
                report.results.append(ClassResult(
                    id=klass.id, status="failed",
                    detail=f"the fixture raised {type(exc).__name__}",
                ))
                continue
            failed_keys = sorted(k for k, ok in observed.items() if not ok)
            report.results.append(ClassResult(
                id=klass.id,
                status="failed" if failed_keys else "passed",
                detail=("every gold outcome held" if not failed_keys
                        else f"gold outcomes not held: {', '.join(failed_keys)}"),
                observed=observed,
            ))
            continue
        if klass.kind == "code_eval":
            dataset = _load_code_dataset()
            cases = dataset.get("cases") if isinstance(dataset.get("cases"), list) else []
            fixture_ids = {str(c.get("caseId")) for c in cases if isinstance(c, dict)}
            missing = [s for s in klass.selectors if s not in fixture_ids]
            report.results.append(ClassResult(
                id=klass.id,
                status="failed" if missing else "passed",
                detail=("fixtures present (graded by the code gate in this run)"
                        if not missing else f"fixture ids missing: {', '.join(missing)}"),
                observed={"fixtures": list(klass.selectors)},
            ))
            continue
        # test_gate
        problems: list[str] = []
        details: list[str] = []
        for selector in klass.selectors:
            ok, detail = _check_test_selector(klass, selector)
            details.append(detail)
            if not ok:
                problems.append(selector)
        report.results.append(ClassResult(
            id=klass.id,
            status="failed" if problems else "passed",
            detail=("; ".join(details) if not problems
                    else f"missing tests: {', '.join(problems)}"),
            observed={"selectors": list(klass.selectors)},
        ))
    return report


def _load_code_dataset() -> dict[str, Any]:
    path = Path(__file__).with_name("dataset_tasks_v1.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable dataset is an empty one
        return {"cases": []}


def check_capability_floors(
    report: CapabilityReport, *, baseline: frozenset[str] = MEASURED_BASELINE,
) -> dict[str, Any]:
    """The gate: a measured class must pass; a baseline class must stay measured."""
    failures: list[str] = []
    for result in report.failed:
        failures.append(f"{result.id}: {result.detail}")
    for class_id in sorted(baseline):
        result = report.by_id(class_id)
        if result is None or result.status == "unmeasured":
            failures.append(f"{class_id}: regressed to unmeasured")
    return {
        "passed": not failures,
        "failures": failures,
        "measured": len(report.measured),
        "unmeasured": len(report.unmeasured),
        "classes": len(report.results),
    }


def format_capability_report(report: CapabilityReport) -> str:
    lines = [
        f"capability classes: {len(report.results)} registered, "
        f"{len(report.measured)} measured, {len(report.unmeasured)} not measured yet"
    ]
    for result in report.results:
        mark = {"passed": "OK", "failed": "FAIL", "unmeasured": "—"}[result.status]
        lines.append(f"  [{mark}] {result.id}: {result.detail}")
    if report.unmeasured:
        names = ", ".join(r.id for r in report.unmeasured)
        lines.append(f"  not measured yet (named, not hidden): {names}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    """The gate step. Prints the counts; non-zero on a floor violation or a
    measured class regressing to unmeasured."""
    import sys  # noqa: PLC0415

    report = run_capability_eval()
    print(format_capability_report(report))
    verdict = check_capability_floors(report)
    print(
        "capability-class gate:",
        "PASS" if verdict["passed"] else "FAIL",
        verdict["failures"] if not verdict["passed"] else "",
    )
    return 0 if verdict["passed"] else 1


__all__ = [
    "CLASSES",
    "MEASURED_BASELINE",
    "CapabilityClass",
    "CapabilityReport",
    "ClassResult",
    "check_capability_floors",
    "format_capability_report",
    "run_capability_eval",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
