"""Tests for Quant Research Intelligence.

Everything here is deterministic and offline: no provider is called, no paper is
downloaded, and every number comes from a local estimator on synthetic data.
"""

from __future__ import annotations

import math
import random
from types import SimpleNamespace

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant.research_intel.catalog import CATALOG
from harness.quant.research_intel.dossier import build_dossier
from harness.quant.research_intel.extraction import extract_method
from harness.quant.research_intel.query_planner import plan_queries
from harness.quant.research_intel.repro import reproduce_method, validate_reproduction
from harness.quant.research_intel.schema import validate_method_spec
from harness.quant.research_intel.scholarly import _dedupe
from harness.quant.research_intel.store import ResearchStore
from harness.quant.research_intel.suitability import compare_methods, score_method
from harness.quant.research_intel.tools import RESEARCH_TOOLS
from harness.quant.research_intel.visuals import build_research_figures
from harness.quant.research_intel.llm_extract import apply_proposal
from harness.quant.store import QuantStore
from harness.quant.tools import QUANT_TOOLS


@pytest.fixture()
def store(tmp_path) -> ResearchStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return ResearchStore(QuantStore(ams, artifact_root=str(tmp_path / "art")))


def _ou_series(n: int = 600, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    x = 100.0
    rows = []
    for i in range(n):
        x = 100.0 + 0.9 * (x - 100.0) + rng.gauss(0, 1.0)
        rows.append({"ts": f"2024-01-{i % 28 + 1:02d}", "close": x})
    return rows


def _intraday_series(days: int = 70, bars: int = 6, seed: int = 9) -> list[dict]:
    rng = random.Random(seed)
    price = 100.0
    rows = []
    for day in range(days):
        for bar in range(bars):
            price *= math.exp(rng.gauss(0, 0.001))
            rows.append({"ts": f"2024-{1 + day // 28:02d}-{1 + day % 28:02d}T{bar:02d}:00:00",
                         "close": price})
    return rows


def _garch_series(n: int = 900, seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    omega, alpha, beta = 0.02, 0.08, 0.9
    var = 1.0
    price = 100.0
    rows = []
    for i in range(n):
        r = rng.gauss(0, math.sqrt(max(var, 1e-9)))
        var = omega + alpha * r * r + beta * var
        price *= math.exp(r / 100.0)
        rows.append({"ts": f"2024-02-{i % 28 + 1:02d}", "close": price})
    return rows


PAPER = """
# A Simple Approximate Long-Memory Model

## 1. Objective
The objective of this paper is to estimate and forecast conditional volatility.
We study the persistence of variance in financial returns.

## 2. Assumptions
We assume returns are conditionally mean-zero and the process is stationary.
We require the variance equation to be correctly specified.

## 3. Estimation
Parameters are estimated by maximum likelihood over the sample.

$$\\sigma_t^2 = \\omega + \\alpha \\varepsilon_{t-1}^2 + \\beta \\sigma_{t-1}^2$$

## 4. Limitations
However, the model is sensitive to structural breaks and to short samples.

Bollerslev (1986) introduced this model.
"""


# ── schema / catalog ─────────────────────────────────────────────────────────

def test_every_catalog_method_is_valid():
    for spec in CATALOG:
        issues = validate_method_spec(spec)
        assert issues == [], f"{spec['methodId']}: {issues}"
        assert spec["equations"][0]["source"]["citation"]


def test_schema_rejects_equation_without_provenance():
    issues = validate_method_spec({
        "methodId": "x.bad", "name": "Bad", "family": "test", "version": "1.0.0",
        "objective": ["x"], "inputs": [{"name": "returns", "frequency": "daily"}],
        "equations": [{"latex": "y = x"}],
        "estimation": {"method": "ols"}, "outputs": ["y"],
    })
    assert any(i["code"] == "EQUATION_WITHOUT_PROVENANCE" for i in issues)


def test_schema_rejects_missing_input_frequency():
    issues = validate_method_spec({
        "methodId": "x.bad", "name": "Bad", "family": "test", "version": "1.0.0",
        "objective": ["x"], "inputs": [{"name": "returns"}],
        "equations": [{"latex": "y = x", "source": {"citation": "c"}}],
        "estimation": {"method": "ols"}, "outputs": ["y"],
    })
    assert any(i["code"] == "MISSING_INPUT_FREQUENCY" for i in issues)


# ── store ────────────────────────────────────────────────────────────────────

def test_store_roundtrip_and_seed(store):
    inserted = store.seed_catalog()
    assert inserted == len(CATALOG)
    rows = store.list_method_specs(limit=100)
    assert len(rows) >= len(CATALOG)
    garch = store.get_method_spec("volatility.garch_11")
    assert garch["spec"]["equations"]
    assert garch["spec"]["implementationStatus"] == "builtin"

    lit = store.save_literature({
        "title": "Generalized Autoregressive Conditional Heteroskedasticity",
        "doi": "10.1016/0304-4076(86)90063-1",
        "year": 1986, "url": "https://doi.org/10.1016/0304-4076(86)90063-1",
    })
    same = store.save_literature({"title": "GARCH paper", "doi": "10.1016/0304-4076(86)90063-1"})
    assert same["id"] == lit["id"]
    store.link_paper("volatility.garch_11", lit["id"])
    assert store.list_papers("volatility.garch_11")[0]["literatureId"] == lit["id"]

    rel = store.add_relationship(from_method="volatility.garch_11",
                                 to_method="volatility.egarch_11",
                                 relation="alternative")
    assert rel["relation"] == "alternative"


# ── planning / dedupe ────────────────────────────────────────────────────────

def test_query_planner_expands_the_volatility_problem():
    plan = plan_queries(
        "identify volatility expansion before directional moves",
        instrument="XAUUSD", timeframe="15m",
    )
    queries = [q["query"] for q in plan["queries"]]
    assert len(queries) >= 8
    assert any("GARCH" in q for q in queries)
    assert any("realized volatility" in q.lower() for q in queries)
    assert plan["researchDepth"] in ("deep", "comparative")


def test_dedupe_links_doi_and_title_variants():
    rows = [
        {"title": "A Paper", "doi": "10.1/ABC", "arxivId": None,
         "provider": "openalex", "abstract": "", "providers": []},
        {"title": "A Paper (preprint)", "doi": None, "arxivId": "2401.00001",
         "provider": "arxiv", "abstract": "", "providers": []},
        {"title": "A Paper", "doi": "10.1/abc", "arxivId": None,
         "provider": "crossref", "abstract": "long abstract", "providers": []},
    ]
    out = _dedupe(rows)
    assert len(out) == 2
    first = [r for r in out if r.get("doi")][0]
    assert "crossref" in first["providers"]


# ── extraction ───────────────────────────────────────────────────────────────

def test_extraction_keeps_equation_provenance(store):
    lit = store.save_literature({"title": "A Simple Approximate Long-Memory Model",
                                 "year": 2009})
    result = extract_method(
        literature_id=lit["id"], text=PAPER,
        title="A Simple Approximate Long-Memory Model",
        method_hint="volatility.garch_11",
    )
    draft = result["draft"]
    assert result["equationCount"] >= 1
    eq = draft["equations"][0]
    assert eq["source"]["literatureId"] == lit["id"]
    assert eq["source"]["page"] >= 1
    assert result["valid"], result["issues"]
    assert draft["provenance"]["literatureIds"] == [lit["id"]]


def test_extraction_names_missing_fields_instead_of_guessing(store):
    lit = store.save_literature({"title": "An Empty Abstract"})
    result = extract_method(literature_id=lit["id"], text="A short note with no method.")
    assert result["valid"] is False
    assert result["unresolved"]
    assert any(i["code"] == "NO_EQUATION" for i in result["issues"])


# ── suitability ──────────────────────────────────────────────────────────────

def test_suitability_is_explained_and_not_a_profit_claim(store):
    store.seed_catalog()
    har = store.get_method_spec("volatility.har_rv")["spec"]
    hmm = store.get_method_spec("regime.hmm")["spec"]
    constraints = {
        "objective": "forecast intraday volatility",
        "instrument": "gold",
        "frequency": "daily",
        "availableData": ["realized_variance", "returns"],
    }
    rows = compare_methods([har, hmm], constraints)
    assert rows[0]["methodId"] == "volatility.har_rv"
    assert rows[0]["score"] >= rows[1]["score"]
    assert all(f["max"] > 0 and f["reason"] for f in rows[0]["factors"])
    assert any("not a probability of profit" in c for c in rows[0]["caveats"])


def test_suitability_lowers_confidence_when_objective_is_missing(store):
    store.seed_catalog()
    row = score_method(store.get_method_spec("volatility.garch_11")["spec"], {})
    assert any("objective not stated" in w for w in row["warnings"])


# ── reproduction / validation ────────────────────────────────────────────────

def test_ou_reproduction_and_validation(store):
    store.seed_catalog()
    rep = reproduce_method(store, method_id="stats.ornstein_uhlenbeck",
                           series=_ou_series())
    assert rep["status"] == "partial"
    metrics = rep["observedMetrics"]
    assert 0 < metrics["ar1"] < 1
    assert metrics["halfLife"] > 0
    assert metrics["observations"] == 600
    validation = validate_reproduction(store, rep["id"])["validation"]
    assert validation["status"] in ("incomplete", "pass")
    assert any(c["check"] == "out_of_sample" for c in validation["checks"])


def test_reproduction_without_implementation_is_inconclusive(store):
    store.seed_catalog()
    rep = reproduce_method(store, method_id="stats.arima", series=_ou_series())
    assert rep["status"] == "inconclusive"
    assert "No runnable implementation" in rep["fidelity"]["note"]


def test_garch_reproduction_produces_admissible_parameters(store):
    store.seed_catalog()
    rep = reproduce_method(store, method_id="volatility.garch_11",
                           series=_garch_series())
    metrics = rep["observedMetrics"]
    assert metrics["alpha"] >= 0
    assert metrics["beta"] >= 0
    assert metrics["persistence"] < 1


def test_reproduction_compares_a_supplied_benchmark(store):
    store.seed_catalog()
    rep = reproduce_method(
        store, method_id="volatility.ewma", series=_ou_series(),
        published_benchmark={"lambda": 0.94},
    )
    assert rep["fidelity"]["matched"] == 1
    assert rep["status"] in ("reproduced", "partial")


# ── dossier ──────────────────────────────────────────────────────────────────

def test_dossier_is_partial_when_evidence_is_missing_and_marks_it(store):
    store.seed_catalog()
    result = build_dossier(
        store, title="Regime research", question="How should I detect regimes?",
        method_ids=["regime.hmm"], literature_ids=[], reproduction_ids=[],
    )
    assert result["status"] == "partial"
    assert "no literature reviewed" in result["missing"]
    assert "## Limitations" in result["markdown"]
    assert "A method card is not evidence" in result["markdown"]


def test_dossier_registers_an_artifact_when_available(store):
    store.seed_catalog()
    lit = store.save_literature({"title": "A Paper", "year": 2020})
    rep = reproduce_method(store, method_id="stats.ornstein_uhlenbeck",
                           series=_ou_series())
    validate_reproduction(store, rep["id"])

    class FakeArtifacts:
        def register_bytes(self, data, **kwargs):
            assert data
            return SimpleNamespace(id="art_test123")

    result = build_dossier(
        store, title="OU research", question="Is gold mean-reverting?",
        artifact_service=FakeArtifacts(),
        method_ids=["stats.ornstein_uhlenbeck"],
        literature_ids=[lit["id"]], reproduction_ids=[rep["id"]],
    )
    assert result["artifactId"] == "art_test123"
    saved = store.get_dossier(result["dossierId"])
    assert saved["artifactId"] == "art_test123"
    assert saved["dossier"]["contentHash"]


# ── tool surface ─────────────────────────────────────────────────────────────

def test_research_tools_are_declared_in_quant_tools():
    missing = [name for name in RESEARCH_TOOLS if name not in QUANT_TOOLS]
    assert missing == []
    assert len(RESEARCH_TOOLS) == len(set(RESEARCH_TOOLS))


# ── horizon-wide catalog ─────────────────────────────────────────────────────

def test_catalog_is_open_and_horizon_wide():
    assert len(CATALOG) >= 29
    horizons = set()
    for spec in CATALOG:
        assert spec.get("horizons"), spec["methodId"]
        horizons.update(spec["horizons"])
    assert {"intraday", "swing", "position", "long-term"} <= horizons


def test_suitability_never_exceeds_100_and_scores_horizon(store):
    store.seed_catalog()
    for spec in CATALOG:
        row = score_method(spec, {
            "objective": "forecast volatility", "instrument": "gold",
            "horizon": "intraday", "frequency": "15m",
            "availableData": ["returns", "realized_variance"],
        })
        assert 0 <= row["score"] <= 100, spec["methodId"]
        assert any(f["name"] == "horizon_fit" for f in row["factors"])


# ── deeper reproduction ──────────────────────────────────────────────────────

def _paired(n: int = 500, seed: int = 4) -> list[dict]:
    rng = random.Random(seed)
    base = 100.0
    rows = []
    for i in range(n):
        base = 100.0 + 0.95 * (base - 100.0) + rng.gauss(0, 0.5)
        rows.append({"ts": f"2024-04-{i % 28 + 1:02d}",
                     "y": base + rng.gauss(0, 0.2),
                     "x": base, "close": base})
    return rows


def test_har_gjr_egarch_and_evt_reproduce(store):
    store.seed_catalog()
    rows = _garch_series()
    har_rows = _intraday_series()
    for method_id, keys, sample in (
        ("volatility.har_rv", ("betaDaily", "rSquared"), har_rows),
        ("volatility.gjr_garch", ("gamma", "persistence"), rows),
        ("volatility.egarch_11", ("gamma", "persistence"), rows),
        ("risk.evt_gpd", ("xi", "var99"), rows),
    ):
        rep = reproduce_method(store, method_id=method_id, series=sample)
        assert rep["status"] in ("partial", "reproduced"), (method_id, rep)
        assert any(key in rep["observedMetrics"] for key in keys), (method_id, rep)


def test_cointegration_capm_hmm_and_execution_reproduce(store):
    store.seed_catalog()
    pairs = reproduce_method(store, method_id="statarb.cointegration",
                             series=_paired())
    assert pairs["observedMetrics"]["beta"] > 0
    assert "halfLife" in pairs["observedMetrics"]

    capm_rows = [{"asset": 0.001, "market": 0.0008}
                 for _ in range(200)]
    capm = reproduce_method(store, method_id="factor.capm", series=capm_rows)
    assert capm["observedMetrics"]["model"] == "CAPM"

    hmm = reproduce_method(store, method_id="regime.hmm", series=_garch_series())
    assert hmm["observedMetrics"]["states"] >= 2
    assert len(hmm["observedMetrics"]["transition"]) >= 2

    ac = reproduce_method(store, method_id="execution.almgren_chriss",
                          series=[], params={"order_size": 1000, "slices": 5})
    assert ac["observedMetrics"]["slices"] == 5


def test_generic_registered_implementation_runs_isolated(store):
    store.seed_catalog()
    spec = dict(CATALOG[0])
    spec["methodId"] = "research.mean_test"
    spec["name"] = "Isolated mean implementation"
    spec["implementation"] = {
        "kind": "python",
        "source": "def run(rows, params):\n"
                  "    values = [float(r['close']) for r in rows]\n"
                  "    return {'mean': sum(values) / len(values), 'observations': len(values)}\n",
        "isolation": "process",
    }
    store.save_method_spec(spec)
    rep = reproduce_method(store, method_id="research.mean_test",
                           series=_ou_series())
    assert rep["status"] == "partial"
    assert rep["observedMetrics"]["observations"] == 600
    assert abs(rep["observedMetrics"]["mean"] - 100.0) < 5


def test_generic_implementation_failure_is_honest(store):
    store.seed_catalog()
    spec = dict(CATALOG[0])
    spec["methodId"] = "research.broken_test"
    spec["name"] = "Broken implementation"
    spec["implementation"] = {"kind": "python", "source": "raise RuntimeError('boom')"}
    store.save_method_spec(spec)
    rep = reproduce_method(store, method_id="research.broken_test",
                           series=_ou_series())
    assert rep["status"] == "failed"
    assert "boom" in str(rep["fidelity"])


# ── span-checked model extraction ───────────────────────────────────────────

def test_llm_proposal_accepts_only_quoted_fields(store):
    lit = store.save_literature({"title": "A Quoted Paper"})
    draft = extract_method(literature_id=lit["id"], text=PAPER)["draft"]
    proposal = {
        "objective": ["forecast conditional volatility"],
        "assumptions": ["returns are conditionally mean-zero"],
        "family": "volatility_modeling",
        "quotes": {
            "objective": "The objective of this paper is to estimate and forecast conditional volatility",
            "assumptions": "We assume returns are conditionally mean-zero",
        },
    }
    result = apply_proposal(draft, proposal, PAPER)
    assert "objective" in result["verified"]
    assert any(item.startswith("family") for item in result["rejected"])
    assert "family" not in result["verified"]

    bad = {"name": "Invented", "quotes": {"name": "This sentence is not in the paper."}}
    result2 = apply_proposal(draft, bad, PAPER)
    assert result2["rejected"]


# ── figures ─────────────────────────────────────────────────────────────────

def test_research_figures_are_computed_and_valid(store):
    store.seed_catalog()
    methods = [store.get_method_spec("volatility.garch_11")["spec"],
               store.get_method_spec("regime.hmm")["spec"]]
    comparison = compare_methods(methods, {"objective": "forecast volatility"})
    result = build_research_figures(
        methods=methods, comparison=comparison, series=_ou_series()[:120],
        symbol="TEST",
    )
    assert len(result["blocks"]) >= 4
    for block in result["blocks"]:
        assert block["type"] == "chart"
        assert block["series"]
        assert block["source"]
    names = {figure["name"] for figure in result["figures"]}
    assert {"method_matrix", "suitability", "price", "rolling_volatility"} <= names


def test_dossier_embeds_computed_figures(store):
    store.seed_catalog()
    result = build_dossier(
        store, title="Figure research", question="What does the data look like?",
        method_ids=["volatility.garch_11", "regime.hmm"],
        series=_ou_series()[:120], symbol="TEST",
    )
    assert "## Figures" in result["markdown"]
    assert '"type":"chart"' in result["markdown"].replace(" ", "")
    assert result["dossier"]["figures"]
