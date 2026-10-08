"""Search evaluation: a golden dataset and standard retrieval metrics.

``GOLDEN_DATASET`` is a labelled corpus shipped with the layer so a future
optimization can be checked against measurable retrieval quality. The corpus is
synthetic (deterministic, no network) but the metrics are real: Recall@K,
Precision@K, MRR and NDCG are computed against the actual index.

Run it from a test or the operator surface; a regression is an explicit,
measured failure rather than a vibe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from .contracts import SearchRequest
from .service import SearchService


@dataclass
class EvalCase:
    query: str
    relevant_documents: list[str]
    mode: str = "hybrid"
    source_type: Optional[str] = None


@dataclass
class EvalReport:
    cases: int = 0
    k: int = 10
    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    mrr: float = 0.0
    ndcg: float = 0.0
    per_case: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "hybrid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "k": self.k,
            "mode": self.mode,
            "recallAtK": round(self.recall_at_k, 4),
            "precisionAtK": round(self.precision_at_k, 4),
            "mrr": round(self.mrr, 4),
            "ndcg": round(self.ndcg, 4),
            "perCase": self.per_case,
        }


# A deterministic synthetic finance corpus: (document_id, title, source_type, text).
CORPUS: list[tuple[str, str, str, str]] = [
    ("doc-nvda-10k", "NVIDIA FY2026 10-K", "filing",
     "NVIDIA data center revenue grew sharply on AI infrastructure demand. Gross margin expanded on "
     "favorable product mix. Risk factors include supply constraints and customer concentration."),
    ("doc-nvda-call", "NVIDIA Q4 earnings call transcript", "transcript",
     "Management commentary highlighted accelerating cloud demand, data center capex, and networking. "
     "Operating margin guidance was raised."),
    ("doc-tsla-10q", "Tesla Q1 10-Q", "filing",
     "Tesla automotive gross margin declined due to pricing pressure, product mix shifts, and cost "
     "inflation. Revenue grew while operating margin compressed."),
    ("doc-tsla-note", "Tesla margin analysis note", "research",
     "Why did Tesla margins fall despite revenue growth? COGS rose, average selling prices fell, and "
     "regulatory credit revenue normalized."),
    ("doc-aapl-10k", "Apple FY2025 10-K", "filing",
     "Apple Services revenue reached a record. iPhone revenue was stable. Risk factors include "
     "regulatory pressure and foreign exchange headwinds."),
    ("doc-amzn-10k", "Amazon FY2025 10-K", "filing",
     "Amazon AWS growth reaccelerated on AI demand. North America retail operating margin improved on "
     "cost controls. Free cash flow expanded."),
    ("doc-msft-call", "Microsoft earnings call", "transcript",
     "Microsoft Azure AI revenue grew triple digits. Capital expenditure increased to meet AI demand. "
     "Copilot adoption expanded."),
    ("doc-google-10k", "Alphabet FY2025 10-K", "filing",
     "Alphabet search revenue grew on AI features. Cloud operating margin turned positive. Risk factors "
     "include competition in generative AI."),
    ("doc-meta-call", "Meta earnings call", "transcript",
     "Meta advertising revenue grew while capital expenditure guidance rose for AI infrastructure. "
     "Operating margin expanded."),
    ("doc-fed-fomc", "FOMC statement", "macro",
     "The Committee decided to maintain the target range for the federal funds rate. Inflation remains "
     "elevated. The labor market has remained strong."),
    ("doc-cpi-report", "US CPI report", "macro",
     "Consumer price inflation cooled as goods prices fell while services inflation remained sticky. "
     "Core CPI rose modestly."),
    ("doc-crypto-crypto", "Crypto market structure note", "research",
     "Bitcoin spot ETF inflows drove digital asset demand. Exchange volumes rose. Volatility stayed "
     "elevated around macro events."),
]

DATASET: list[EvalCase] = [
    EvalCase("NVIDIA data center revenue AI demand", ["doc-nvda-10k"]),
    EvalCase("NVDA gross margin product mix", ["doc-nvda-10k"]),
    EvalCase("NVIDIA supply constraints risk factors", ["doc-nvda-10k"]),
    EvalCase("NVIDIA cloud demand data center capex", ["doc-nvda-call"]),
    EvalCase("NVIDIA management commentary operating margin guidance", ["doc-nvda-call"]),
    EvalCase("Tesla gross margin pricing pressure", ["doc-tsla-10q"]),
    EvalCase("Tesla product mix cost inflation", ["doc-tsla-10q"]),
    EvalCase("why did Tesla margins fall despite revenue growth", ["doc-tsla-note"]),
    EvalCase("Tesla COGS average selling price regulatory credit", ["doc-tsla-note"]),
    EvalCase("Apple services revenue record", ["doc-aapl-10k"]),
    EvalCase("Apple regulatory pressure foreign exchange", ["doc-aapl-10k"]),
    EvalCase("Amazon AWS growth AI demand", ["doc-amzn-10k"]),
    EvalCase("Amazon retail operating margin cost controls", ["doc-amzn-10k"]),
    EvalCase("Amazon free cash flow", ["doc-amzn-10k"]),
    EvalCase("Microsoft Azure AI revenue capital expenditure", ["doc-msft-call"]),
    EvalCase("Microsoft Copilot adoption", ["doc-msft-call"]),
    EvalCase("Alphabet search revenue AI features", ["doc-google-10k"]),
    EvalCase("Alphabet cloud operating margin generative AI competition", ["doc-google-10k"]),
    EvalCase("Meta advertising revenue capital expenditure AI", ["doc-meta-call"]),
    EvalCase("Meta operating margin", ["doc-meta-call"]),
    EvalCase("federal funds rate target range", ["doc-fed-fomc"]),
    EvalCase("labor market strong inflation elevated", ["doc-fed-fomc"]),
    EvalCase("US CPI services inflation sticky", ["doc-cpi-report"]),
    EvalCase("core CPI goods prices fell", ["doc-cpi-report"]),
    EvalCase("Bitcoin spot ETF inflows", ["doc-crypto-crypto"]),
    EvalCase("crypto exchange volumes volatility", ["doc-crypto-crypto"]),
    # Cross-document / conceptual queries with more than one relevant doc.
    EvalCase("AI infrastructure demand driving revenue", ["doc-nvda-10k", "doc-msft-call", "doc-amzn-10k"]),
    EvalCase("cloud growth operating margin", ["doc-amzn-10k", "doc-google-10k", "doc-msft-call"]),
    EvalCase("margin compression cost inflation", ["doc-tsla-10q", "doc-tsla-note"]),
    EvalCase("capital expenditure AI guidance", ["doc-msft-call", "doc-meta-call"]),
    # Additional labelled cases (distinct phrases per document) — 60 total.
    EvalCase("customer concentration supply constraints", ["doc-nvda-10k"]),
    EvalCase("networking revenue data center", ["doc-nvda-call"]),
    EvalCase("automotive gross margin decline", ["doc-tsla-10q"]),
    EvalCase("average selling price COGS rose", ["doc-tsla-note"]),
    EvalCase("iPhone revenue stable", ["doc-aapl-10k"]),
    EvalCase("AWS reaccelerated AI demand", ["doc-amzn-10k"]),
    EvalCase("North America retail cost controls", ["doc-amzn-10k"]),
    EvalCase("Azure triple digit growth", ["doc-msft-call"]),
    EvalCase("search revenue generative AI competition", ["doc-google-10k"]),
    EvalCase("Alphabet cloud positive operating margin", ["doc-google-10k"]),
    EvalCase("Meta advertising capital expenditure", ["doc-meta-call"]),
    EvalCase("federal funds rate inflation", ["doc-fed-fomc"]),
    EvalCase("labor market inflation services", ["doc-fed-fomc"]),
    EvalCase("goods prices fell core CPI", ["doc-cpi-report"]),
    EvalCase("Bitcoin ETF inflows digital asset", ["doc-crypto-crypto"]),
    EvalCase("exchange volumes volatility macro", ["doc-crypto-crypto"]),
    EvalCase("AI demand cloud capex networking", ["doc-nvda-call", "doc-msft-call"]),
    EvalCase("operating margin cost controls free cash flow", ["doc-amzn-10k", "doc-aapl-10k"]),
    EvalCase("pricing pressure product mix cost inflation", ["doc-tsla-10q", "doc-tsla-note"]),
    EvalCase("risk factors regulatory pressure", ["doc-aapl-10k", "doc-google-10k"]),
    EvalCase("capital expenditure AI infrastructure", ["doc-msft-call", "doc-meta-call", "doc-nvda-call"]),
    EvalCase("revenue growth margin compression", ["doc-tsla-10q", "doc-tsla-note"]),
    EvalCase("data center revenue AI infrastructure demand", ["doc-nvda-10k", "doc-nvda-call"]),
    EvalCase("inflation sticky services goods", ["doc-cpi-report", "doc-fed-fomc"]),
    EvalCase("cloud operating margin turn positive", ["doc-google-10k", "doc-amzn-10k"]),
    EvalCase("advertising revenue operating margin", ["doc-meta-call", "doc-google-10k"]),
    EvalCase("guidance raised networking", ["doc-nvda-call"]),
    EvalCase("record services revenue", ["doc-aapl-10k"]),
    EvalCase("free cash flow expanded", ["doc-amzn-10k"]),
    EvalCase("copilot adoption capital expenditure", ["doc-msft-call"]),
]


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = set(retrieved[:k])
    return len(top & set(relevant)) / len(set(relevant))


def precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    return len([d for d in top if d in set(relevant)]) / len(top)


def reciprocal_rank(retrieved: list[str], relevant: list[str]) -> float:
    relevant_set = set(relevant)
    for index, doc in enumerate(retrieved, start=1):
        if doc in relevant_set:
            return 1.0 / index
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    relevant_set = set(relevant)
    dcg = 0.0
    for index, doc in enumerate(retrieved[:k], start=1):
        gain = 1.0 if doc in relevant_set else 0.0
        dcg += gain / math.log2(index + 1)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant_set), k) + 1))
    return dcg / ideal if ideal else 0.0


async def run_evaluation(
    service: SearchService,
    dataset: Optional[list[EvalCase]] = None,
    *,
    k: int = 10,
    mode: str = "hybrid",
    settings: Any = None,
) -> EvalReport:
    dataset = dataset or DATASET
    report = EvalReport(cases=len(dataset), k=k, mode=mode)
    if not dataset:
        return report
    totals = {"recall": 0.0, "precision": 0.0, "mrr": 0.0, "ndcg": 0.0}
    for case in dataset:
        request = SearchRequest(query=case.query, mode=case.mode or mode, top_k=k, neighbor=False)
        result = await service.search(request, settings=settings, record=False)
        retrieved = [hit.provenance.source_id or hit.document_id for hit in result.hits]
        recall = recall_at_k(retrieved, case.relevant_documents, k)
        precision = precision_at_k(retrieved, case.relevant_documents, k)
        mrr = reciprocal_rank(retrieved, case.relevant_documents)
        ndcg = ndcg_at_k(retrieved, case.relevant_documents, k)
        totals["recall"] += recall
        totals["precision"] += precision
        totals["mrr"] += mrr
        totals["ndcg"] += ndcg
        report.per_case.append({
            "query": case.query,
            "retrieved": retrieved,
            "relevant": case.relevant_documents,
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "mrr": round(mrr, 4),
            "ndcg": round(ndcg, 4),
        })
    count = len(dataset)
    report.recall_at_k = totals["recall"] / count
    report.precision_at_k = totals["precision"] / count
    report.mrr = totals["mrr"] / count
    report.ndcg = totals["ndcg"] / count
    return report


async def seed_corpus(service: SearchService) -> int:
    """Index the golden corpus (idempotent). Returns the number indexed."""
    for document_id, title, source_type, text in CORPUS:
        await service.ingest_text(
            text, title=title, source_type=source_type, source_id=document_id, namespace="evaluation",
        )
    return len(CORPUS)


__all__ = [
    "CORPUS",
    "DATASET",
    "EvalCase",
    "EvalReport",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "run_evaluation",
    "seed_corpus",
]
