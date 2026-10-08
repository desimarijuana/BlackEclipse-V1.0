"""Offline search-evaluation gate.

Seeds the golden corpus into a throwaway index and computes Recall@K / MRR /
NDCG over the deterministic keyword path (no provider needed), then checks a
floor. A regression is a measured failure, not a vibe. Wired into
`scripts/test-evals.js` as the `search` gate.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any, Optional

# Floors sit below the measured keyword baseline (recall@10 0.908, MRR 0.265,
# NDCG@10 0.409) with margin, so noise never trips them but a real regression
# does.
THRESHOLDS: dict[str, float] = {"recallAtK": 0.80, "mrr": 0.15, "ndcg": 0.25}


def run_search_eval(*, mode: str = "keyword", k: int = 10,
                    dataset: Optional[list[Any]] = None) -> dict[str, Any]:
    from .config import SearchConfig
    from .evaluate import DATASET, run_evaluation, seed_corpus
    from .service import SearchService

    directory = tempfile.mkdtemp(prefix="be-search-eval-")
    service = SearchService(SearchConfig(db_path=os.path.join(directory, "search.db"), rerank_enabled=False))

    async def _go() -> dict[str, Any]:
        await seed_corpus(service)
        report = await run_evaluation(service, dataset or DATASET, k=k, mode=mode)
        return report.to_dict()

    try:
        return asyncio.run(_go())
    finally:
        service.close()


def check_search_thresholds(report: dict[str, Any], thresholds: Optional[dict[str, float]] = None) -> dict[str, Any]:
    floors = thresholds or THRESHOLDS
    failures = [
        f"{key}={report.get(key)} < {floor}"
        for key, floor in floors.items()
        if float(report.get(key) or 0.0) < floor
    ]
    return {"passed": not failures, "failures": failures, "thresholds": floors}


def format_search_report(report: dict[str, Any]) -> str:
    return (
        f"search retrieval ({report.get('mode')}, k={report.get('k')}, cases={report.get('cases')}): "
        f"recall@k={report.get('recallAtK')} precision@k={report.get('precisionAtK')} "
        f"mrr={report.get('mrr')} ndcg@k={report.get('ndcg')}"
    )


__all__ = ["THRESHOLDS", "check_search_thresholds", "format_search_report", "run_search_eval"]
